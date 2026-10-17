"""Embed queries, comments and threads for every model, in budget order.

    python run_embed.py --dry-run            # projected cost, no calls
    python run_embed.py --stage queries      # then core, full, threads

Stages run in this order so that a budget stop still leaves a usable
comparison: every model finishes the queries and the core corpus before any
model grows to the full corpus, and threads (secondary) come last. Within a
stage the cheap models go first.

Each stage writes one matrix per model to data/vecs/<model>__<stage>.npy
(float16, L2-normalised, rows in corpus.jsonl / threads.jsonl order), which
is what retrieval reads. All API traffic goes through openrouter.py, so the
cache and the $4.50 cap apply.
"""

import argparse

import numpy as np

from common import DATA, read_jsonl
from configs import MODELS
from openrouter import CAP_USD, PRICE, SAFETY, BudgetExceeded, Cache, count_tokens, embed_cached, ledger

VECS = DATA / "vecs"
VECS.mkdir(exist_ok=True)
STAGES = ["queries", "core", "full", "threads"]
ORDER = sorted(MODELS, key=lambda m: PRICE[m.model])


def texts_for(m, stage):
    if stage == "queries":
        return m.query_cfg, [m.fmt_query(q["text"]) for q in read_jsonl(DATA.parent / "queries.jsonl")]
    if stage in ("core", "full"):
        rows = read_jsonl(DATA / "corpus.jsonl")
        if stage == "core":
            rows = [r for r in rows if r["tier"] == "core"]
        return m.doc_cfg, [m.fmt_doc(r["title"], r["body"]) for r in rows]
    if stage == "threads":
        rows = read_jsonl(DATA / "threads.jsonl")
        return m.doc_cfg, [m.fmt_doc(r["title"], r["selftext"]) for r in rows]
    raise ValueError(stage)


def dry_run():
    """Projection counts each text once: the core is a subset of the full
    corpus, so texts an earlier stage will have cached are not charged again."""
    total = 0.0
    planned = {m.name: set() for m in ORDER}
    print(f"{'stage':8} {'model':16} {'texts':>7} {'uncached':>8} {'tokens':>10} {'x1.3 $':>8}")
    for stage in STAGES:
        for m in ORDER:
            cfg, texts = texts_for(m, stage)
            cache = Cache(cfg.cache_key)
            hs = [Cache.h(t) for t in texts]
            have = cache.get_many(list(set(hs)))
            todo = {h: t for h, t in zip(hs, texts) if h not in have and h not in planned[m.name]}
            planned[m.name].update(todo)
            toks = sum(count_tokens(t) for t in todo.values())
            cost = toks * SAFETY * PRICE[m.model]
            total += cost
            print(f"{stage:8} {m.name:16} {len(texts):7} {len(todo):8} {toks:10,} {cost:8.3f}")
    print(f"projected remaining ${total:.3f}; already spent ${ledger().spent:.4f}; cap ${CAP_USD:.2f}")


def run(stage, only=None):
    for m in ORDER:
        if only and m.name not in only:
            continue
        cfg, texts = texts_for(m, stage)
        try:
            mat = embed_cached(cfg, texts, purpose=stage,
                               batch=16 if stage == "queries" else (96 if "gemini" in m.model else 128),
                               workers=8)
        except BudgetExceeded as e:
            print(f"BUDGET STOP at {stage}/{m.name}: {e}")
            return False
        mat /= np.linalg.norm(mat, axis=1, keepdims=True)
        np.save(VECS / f"{m.name}__{stage}.npy", mat.astype(np.float16))
        print(f"{stage}/{m.name}: {mat.shape}, ledger ${ledger().spent:.4f}")
    return True


def run_parallel(stages):
    """One process per model within a stage, and a barrier between stages, so
    the budget order (every model finishes a stage before any starts the
    next) holds while the slow providers don't serialise the run. Stops at the
    first stage where any model hits the cap."""
    import subprocess
    import sys

    for stage in stages:
        procs = {m.name: subprocess.Popen([sys.executable, "-u", __file__, "--stage", stage, "--only", m.name],
                                          stdout=open(DATA / f"run_{stage}_{m.name}.log", "w"),
                                          stderr=subprocess.STDOUT)
                 for m in ORDER}
        failed = [n for n, p in procs.items() if p.wait() != 0]
        logs = {n: (DATA / f"run_{stage}_{n}.log").read_text() for n in procs}
        stopped = [n for n, t in logs.items() if "BUDGET STOP" in t]
        print(f"stage {stage} done; ledger ${ledger().spent:.4f}; failed {failed}; budget-stopped {stopped}",
              flush=True)
        if failed or stopped:
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stage", choices=STAGES)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--parallel", nargs="*", choices=STAGES,
                    help="run these stages in order, models in parallel within each")
    a = ap.parse_args()
    if a.dry_run:
        dry_run()
    elif a.parallel:
        run_parallel(a.parallel)
    elif a.stage:
        run(a.stage, a.only)


if __name__ == "__main__":
    main()
