"""TREC-style pooling and blind judging batches.

    python pool.py --scope full --depth 20
    python pool.py --scope threads --depth 10 --tag threads

For each query, the pool is the union of the top `depth` documents from every
system run (dense, truncated, BM25, hybrids). Each (query, document) pair gets
an opaque pair_id, and pairs are written to judging batches with no system
information. Pairs are grouped by query (the judge reads the query and its
intent once per block) but shuffled within the block, and the blocks themselves
are shuffled, so position says nothing about which system found a document or
how highly.

A seeded ~10% sample is written a second time, re-shuffled into different
batches, for an independent re-judge pass that measures judge consistency.

Outputs:
  pools_<tag>.json                 committed: {qid: [doc ids]} (no text)
  data/judging/<tag>/batch_NNN.md  the text a judge reads
  data/judging/<tag>/batch_NNN.keys.json  pair_id -> [qid, doc_id]
  data/judging/<tag>/rj_NNN.md / .keys.json   the re-judge batches
"""

import argparse
import hashlib
import json
import random
from collections import defaultdict

from common import DATA, HERE, read_jsonl

SEED = 1017
BODY_CHARS = 3000


def pair_id(qid, doc):
    return hashlib.sha1(f"{qid}|{doc}".encode()).hexdigest()[:10]


def render(batch, queries, docs, kind):
    out = [f"# Judging batch ({len(batch)} pairs)\n",
           "Grade each pair 0/1/2 with the `opposite` flag, per GUIDELINES.md.\n"]
    byq = defaultdict(list)
    order = []
    for qid, doc in batch:
        if qid not in byq:
            order.append(qid)
        byq[qid].append(doc)
    for qid in order:
        q = queries[qid]
        out.append(f"\n## Query: \"{q['text']}\"\nIntent: {q['intent']}\n")
        for doc in byq[qid]:
            d = docs[doc]
            if kind == "threads":
                body = (d["selftext"] or "(no text)")[:BODY_CHARS]
                out.append(f"### pair {pair_id(qid, doc)}\nThread title: {d['title']}\nPost text: {body}\n")
            else:
                body = d["body"][:BODY_CHARS]
                out.append(f"### pair {pair_id(qid, doc)}\nThread title: {d['title']}\nComment: {body}\n")
    return "\n".join(out)


def write_batches(pairs, size, prefix, outdir, queries, docs, kind, rng):
    byq = defaultdict(list)
    for qid, doc in pairs:
        byq[qid].append(doc)
    blocks = []
    for qid, ds in byq.items():
        ds = ds[:]
        rng.shuffle(ds)
        # Split very large pools so one batch is never a single query's 150 docs.
        for i in range(0, len(ds), size // 2):
            blocks.append([(qid, d) for d in ds[i:i + size // 2]])
    rng.shuffle(blocks)
    batches, cur = [], []
    for b in blocks:
        if cur and len(cur) + len(b) > size:
            batches.append(cur)
            cur = []
        cur += b
    if cur:
        batches.append(cur)
    for n, b in enumerate(batches):
        (outdir / f"{prefix}_{n:03d}.md").write_text(render(b, queries, docs, kind))
        (outdir / f"{prefix}_{n:03d}.keys.json").write_text(
            json.dumps({pair_id(q, d): [q, d] for q, d in b}))
    return len(batches)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="full")
    ap.add_argument("--depth", type=int, default=20)
    ap.add_argument("--tag", default="comments")
    ap.add_argument("--batch", type=int, default=240)
    ap.add_argument("--rejudge", type=float, default=0.10)
    a = ap.parse_args()
    rng = random.Random(SEED)
    queries = {q["qid"]: q for q in read_jsonl(HERE / "queries.jsonl")}
    kind = "threads" if a.scope == "threads" else "comments"
    src = DATA / ("threads.jsonl" if kind == "threads" else "corpus.jsonl")
    docs = {r["id"]: r for r in read_jsonl(src)}

    pool = defaultdict(set)
    rundir = DATA / "runs" / a.scope
    systems = sorted(p.stem for p in rundir.glob("*.json"))
    for s in systems:
        run = json.loads((rundir / f"{s}.json").read_text())
        for qid, lst in run.items():
            pool[qid].update(d for d, _ in lst[:a.depth])
    pools = {qid: sorted(pool[qid]) for qid in sorted(pool)}
    (HERE / f"pools_{a.tag}.json").write_text(json.dumps(
        {"depth": a.depth, "systems": systems, "pools": pools}, indent=0))
    pairs = [(q, d) for q, ds in pools.items() for d in ds]
    print(f"{len(systems)} systems, {len(pairs)} pairs, "
          f"mean pool {len(pairs) / len(pools):.1f}/query")

    outdir = DATA / "judging" / a.tag
    outdir.mkdir(parents=True, exist_ok=True)
    n = write_batches(pairs, a.batch, "batch", outdir, queries, docs, kind, rng)
    rj = rng.sample(pairs, round(len(pairs) * a.rejudge))
    m = write_batches(rj, a.batch, "rj", outdir, queries, docs, kind, rng)
    print(f"{n} judging batches, {m} re-judge batches ({len(rj)} pairs) in {outdir}")


if __name__ == "__main__":
    main()
