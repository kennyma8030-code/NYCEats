"""Correct recall@50 for the depth-20 pool, by sampling.

The pool covers each system's top 20. Ranks 21-50 are judged only when another
system happened to rank the same comment in its own top 20, so a system whose
deeper results are *different* from everyone else's (Qwen: 62% of its top 50
judged, vs 75% for OpenAI-large) has more unjudged comments counted as
non-relevant. Recall@50 is the metric that matters most for this search
design (similarity picks which comments count; restaurants are then ranked by
distinct people), so the bias has to be measured rather than footnoted.

Judging every unjudged top-50 comment would be 10,530 more pairs. Instead:

    python depth50.py sample      # 150 unjudged pairs per system -> blind batches
    #   judges grade data/judging/comments_d50/batch_NNN.md per GUIDELINES.md
    python merge_judgments.py --tag comments_d50
    python depth50.py estimate    # -> DEPTH50.md

The estimator. Each system's 150 were drawn uniformly from its own unjudged
top 50 (U_s), independently of the other systems. So a comment that is unjudged
for several systems could be drawn by any of them, and its inclusion
probability is

    pi_p = 1 - prod over systems s with p in U_s of (1 - 150 / |U_s|)

Comments sitting in one system's U_s alone are drawn at that system's rate;
comments in the overlaps are drawn more often. Weighting every judged sample
by 1/pi_p (Horvitz-Thompson) accounts for exactly that, rather than applying
one plain mean to a union whose make-up is skewed toward the systems with the
largest unique unjudged sets.

For each system:
  relevant in top 50 = first-pass judged relevant
                     + real grades of every sampled comment in U_s (from any system's draw)
                     + estimate for the rest of U_s: sum over sampled p in U_s of y_p (1/pi_p - 1)
and the denominator is the pool's relevant count plus the same estimate over
the union of all U_s. The last term is the Horvitz-Thompson total minus what
was actually observed, so judged comments count once, at their real grade.

Intervals come from a bootstrap over queries (2,000 resamples), which carries
both the query sampling and the judging sample, since every sampled pair
belongs to one query.
"""

import json
import random
import sys
from collections import defaultdict

from common import DATA, HERE, read_jsonl
from pool import write_batches

SYSTEMS = ["qwen3-8b", "oai-3-large", "gemini-2", "oai-3-small", "voyage-4-large", "bm25"]
PER_SYSTEM = 150
SEED = 5050
TAG = "comments_d50"


def unjudged_top50():
    judged = {(r["qid"], r["doc_id"]) for r in read_jsonl(HERE / "judgments_comments.jsonl")}
    out = {}
    for s in SYSTEMS:
        run = json.loads((DATA / "runs" / "full" / f"{s}.json").read_text())
        out[s] = sorted({(q, d) for q, lst in run.items() for d, _ in lst[:50] if (q, d) not in judged})
    return judged, out


def sample():
    rng = random.Random(SEED)
    _, unj = unjudged_top50()
    chosen = {s: rng.sample(unj[s], min(PER_SYSTEM, len(unj[s]))) for s in SYSTEMS}
    (HERE / "depth50_sample.json").write_text(json.dumps(chosen, indent=0))
    pairs = sorted({p for ps in chosen.values() for p in ps})
    queries = {q["qid"]: q for q in read_jsonl(HERE / "queries.jsonl")}
    docs = {r["id"]: r for r in read_jsonl(DATA / "corpus.jsonl")}
    outdir = DATA / "judging" / TAG
    outdir.mkdir(parents=True, exist_ok=True)
    n = write_batches(pairs, 240, "batch", outdir, queries, docs, "comments", rng)
    print(f"{len(pairs)} distinct pairs in {n} batches -> {outdir}")


B = 2000
BOOT_SEED = 99


def estimate():
    import numpy as np

    rel = defaultdict(dict)
    for r in read_jsonl(HERE / "judgments_comments.jsonl"):
        rel[r["qid"]][r["doc_id"]] = r["grade"]
    y = {(r["qid"], r["doc_id"]): int(r["grade"] >= 1) for r in read_jsonl(HERE / f"judgments_{TAG}.jsonl")}
    chosen = {s: [tuple(p) for p in ps] for s, ps in json.loads((HERE / "depth50_sample.json").read_text()).items()}
    _, unj = unjudged_top50()
    U = {s: set(unj[s]) for s in SYSTEMS}
    sampled = set().union(*[set(chosen[s]) for s in SYSTEMS])
    missing = sampled - set(y)
    if missing:
        sys.exit(f"{len(missing)} sampled pairs have no grade; merge {TAG} first")

    # Inclusion probability of each sampled pair under the actual design.
    draw = {s: len(chosen[s]) / len(U[s]) for s in SYSTEMS}
    pi = {}
    for p in sampled:
        miss = 1.0
        for s in SYSTEMS:
            if p in U[s]:
                miss *= 1 - draw[s]
        pi[p] = 1 - miss

    qids = sorted({q["qid"] for q in read_jsonl(HERE / "queries.jsonl")})
    qi = {q: i for i, q in enumerate(qids)}
    nq = len(qids)

    # Per-query parts, so the bootstrap can resample queries.
    R_pool = np.zeros(nq)
    for q in qids:
        R_pool[qi[q]] = sum(1 for g in rel[q].values() if g >= 1)
    union_est = np.zeros(nq)          # HT total over the union of all U_s
    for p in sampled:
        union_est[qi[p[0]]] += y[p] / pi[p]
    parts = {}
    for s in SYSTEMS:
        run = json.loads((DATA / "runs" / "full" / f"{s}.json").read_text())
        J = np.zeros(nq)              # first-pass judged relevant in top 50
        K = np.zeros(nq)              # real grades of sampled comments in U_s
        H = np.zeros(nq)              # estimate for the unsampled rest of U_s
        n_top = np.zeros(nq)
        for q, lst in run.items():
            for d, _ in lst[:50]:
                n_top[qi[q]] += 1
                if rel[q].get(d, 0) >= 1:
                    J[qi[q]] += 1
        for p in sampled & U[s]:
            K[qi[p[0]]] += y[p]
            H[qi[p[0]]] += y[p] * (1 / pi[p] - 1)
        parts[s] = (J, K, H, n_top)

    def stats(idx):
        den = (R_pool[idx] + union_est[idx]).sum()
        out = {}
        for s, (J, K, H, n_top) in parts.items():
            num = (J[idx] + K[idx] + H[idx]).sum()
            out[s] = (num / den, num / n_top[idx].sum(), J[idx].sum() / R_pool[idx].sum())
        return out

    point = stats(np.arange(nq))
    rng = np.random.default_rng(BOOT_SEED)
    boots = [stats(rng.integers(0, nq, nq)) for _ in range(B)]

    def ci(s, k):
        v = np.array([b[s][k] for b in boots])
        return np.percentile(v, 2.5), np.percentile(v, 97.5)

    # Paired: each system vs the best corrected recall, on the same resamples.
    best = max(SYSTEMS, key=lambda s: point[s][0])
    R_total = (R_pool + union_est).sum()
    lines = ["# Recall@50 corrected for pool depth\n",
             "Generated by `depth50.py estimate`. The depth-20 pool leaves part of each system's top 50 "
             "unjudged, and those comments count as non-relevant in RESULTS_TABLES_comments.md. A random 150 "
             "of each system's unjudged top-50 comments (884 distinct pairs) were judged blind with the same "
             "guidelines. Sampled comments count at their real grade; only the unsampled remainder of each "
             "system's unjudged set is estimated, Horvitz-Thompson weighted by each comment's true inclusion "
             "probability (comments unjudged for several systems could be drawn by any of them). "
             "95% intervals: bootstrap over queries, 2,000 resamples. Micro-averaged over 110 queries.\n",
             f"Pool relevant (judged >= 1): {int(R_pool.sum()):,}; estimated relevant among the "
             f"{len(set().union(*U.values())):,} unjudged top-50 comments: {union_est.sum():,.0f}; "
             f"estimated total {R_total:,.0f} (~{R_total / nq:.0f} per query). A perfect top 50 would reach "
             f"recall@50 of about {100 * 50 * nq / R_total:.0f}, so est. precision@50 is the easier column to read.\n",
             "| system | top-50 judged in first pass | unjudged in top 50 | of which sampled (real grades) | "
             "sampled judged >= 1 | recall@50 as scored | **recall@50 corrected** [95% CI] | "
             f"vs {best} [95% CI] | est. precision@50 [95% CI] |",
             "|---|---|---|---|---|---|---|---|---|"]
    for s in SYSTEMS:
        J, K, H, n_top = parts[s]
        n_unj = len(U[s])
        n_s = len(sampled & U[s])
        rec, prec, as_scored = point[s]
        lo, hi = ci(s, 0)
        plo, phi = ci(s, 1)
        diffs = np.array([b[best][0] - b[s][0] for b in boots])
        dcell = "leader" if s == best else (
            f"{(point[best][0] - rec) * 100:+.1f} [{np.percentile(diffs, 2.5) * 100:+.1f}, "
            f"{np.percentile(diffs, 97.5) * 100:+.1f}]")
        lines.append(f"| {s} | {1 - n_unj / n_top.sum():.0%} | {n_unj:,} | {n_s} | "
                     f"{K.sum() / n_s * 100:.0f}% | {as_scored * 100:.1f} | **{rec * 100:.1f}** "
                     f"[{lo * 100:.1f}, {hi * 100:.1f}] | {dcell} | {prec * 100:.0f}% [{plo * 100:.0f}, {phi * 100:.0f}] |")
    lines.append("\n`vs leader` is the leader's corrected recall minus this system's on the same resamples; "
                 "a CI that includes 0 is within noise. The as-scored column is micro-averaged against the "
                 "pool's relevant count, so it differs slightly from the per-query mean in the main table.")
    (HERE / "DEPTH50.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    {"sample": sample, "estimate": estimate}[sys.argv[1]]()
