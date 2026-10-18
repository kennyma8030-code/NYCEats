"""Score every system against the pooled judgments.

    python metrics.py --scope full --tag comments

Relevance: grade >= 1 counts as relevant for recall, MRR and P@10; nDCG@10
uses the grades as linear gains (2/1/0), with the ideal ranking built from all
judged documents for the query. Unjudged documents count as non-relevant (the
TREC convention); judged coverage of each system's top 10 is reported so a
system that drifts outside the pool is visible.

Confidence intervals come from a bootstrap over queries (2000 resamples, seeded).
For each system the paired bootstrap against the best system gives the
difference and how often the best stays ahead, which is what decides whether a
gap is real or noise.

The restaurant view follows the search plan: a system's top 50 comments are
grouped by the restaurants they mention, skipping is_negated mentions and
excluded_entities (the plan also drops `reference_only` mentions, but no such
column exists in production yet, so nothing is skipped for it). Restaurants are
ranked by distinct people (comment authors), ties broken by the best comment
rank; similarity decides which comments count, never the order. A restaurant is
relevant if at least one of its grouped comments was judged >= 1.

Writes RESULTS_TABLES_<tag>.md and data/metrics_<tag>.json. Comments lead
with @10/@20 metrics (pooled to depth 20); threads lead with @5 metrics,
their only fully judged depth.
"""

import argparse
import json
import math
import random
from collections import defaultdict

import numpy as np

from common import DATA, HERE, read_jsonl

B = 2000
SEED = 99


def load_qrels(path):
    qrels = defaultdict(dict)
    opp = defaultdict(set)
    for r in read_jsonl(path):
        qrels[r["qid"]][r["doc_id"]] = r["grade"]
        if r["grade"] == 0 and r.get("opposite"):
            opp[r["qid"]].add(r["doc_id"])
    return qrels, opp


def ndcg(ranked, rel, k=10):
    dcg = sum(rel.get(d, 0) / math.log2(i + 2) for i, d in enumerate(ranked[:k]))
    ideal = sorted(rel.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg > 0 else None


def per_query(ranked, rel, opp):
    relset = {d for d, g in rel.items() if g >= 1}
    m = {}
    m["ndcg@10"] = ndcg(ranked, rel)
    # Threads are pooled only to depth 5, so @5 is their only fully judged depth.
    m["ndcg@5"] = ndcg(ranked, rel, k=5)
    m["p@5"] = sum(1 for d in ranked[:5] if rel.get(d, 0) >= 1) / 5
    m["p@5_strict"] = sum(1 for d in ranked[:5] if rel.get(d, 0) == 2) / 5
    if relset:
        m["recall@20"] = len(relset & set(ranked[:20])) / len(relset)
        m["recall@50"] = len(relset & set(ranked[:50])) / len(relset)
        rr = 0.0
        for i, d in enumerate(ranked):
            if d in relset:
                rr = 1.0 / (i + 1)
                break
        m["mrr"] = rr
    m["p@10"] = sum(1 for d in ranked[:10] if rel.get(d, 0) >= 1) / 10
    m["p@10_strict"] = sum(1 for d in ranked[:10] if rel.get(d, 0) == 2) / 10
    # Every system's top 20 is in the pool, so P@20 is fully judged for all of
    # them. Recall@20 is not a fair separator here: with ~73 relevant comments
    # per query, its ceiling is ~28 for everyone.
    m["p@20"] = sum(1 for d in ranked[:20] if rel.get(d, 0) >= 1) / 20
    m["opposite@10"] = sum(1 for d in ranked[:10] if d in opp)
    m["judged@10"] = sum(1 for d in ranked[:10] if d in rel) / 10
    m["judged@50"] = sum(1 for d in ranked[:50] if d in rel) / max(1, min(50, len(ranked)))
    return m


def restaurant_view(ranked, rel, docs, k_comments=50, k_rest=10):
    groups = {}
    for i, d in enumerate(ranked[:k_comments]):
        doc = docs.get(d)
        if not doc:
            continue
        for m in doc["mentions"]:
            if m["is_negated"] or m["excluded"]:
                continue
            g = groups.setdefault(m["resolved_key"], {"people": set(), "best": i, "rel": False, "judged": False})
            g["people"].add(doc["author"] if doc["author"] not in (None, "[deleted]") else d)
            g["best"] = min(g["best"], i)
            if d in rel:
                g["judged"] = True
                if rel[d] >= 1:
                    g["rel"] = True
    top = sorted(groups.items(), key=lambda kv: (-len(kv[1]["people"]), kv[1]["best"]))[:k_rest]
    if not top:
        return None, None
    return (sum(g["rel"] for _, g in top) / len(top),
            sum(g["judged"] for _, g in top) / len(top))


def boot(values, rng):
    v = np.array(values, dtype=float)
    n = len(v)
    idx = rng.integers(0, n, size=(B, n))
    means = v[idx].mean(axis=1)
    return float(v.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def paired(a, b, rng):
    a, b = np.array(a, float), np.array(b, float)
    n = len(a)
    idx = rng.integers(0, n, size=(B, n))
    d = (a[idx] - b[idx]).mean(axis=1)
    return float((a - b).mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5)), float((d > 0).mean())


def fmt_ci(t, scale=100):
    m, lo, hi = t
    return f"{m*scale:.1f} [{lo*scale:.1f}, {hi*scale:.1f}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="full")
    ap.add_argument("--tag", default="comments")
    a = ap.parse_args()
    queries = read_jsonl(HERE / "queries.jsonl")
    qmeta = {q["qid"]: q for q in queries}
    qrels, opp = load_qrels(HERE / f"judgments_{a.tag}.jsonl")
    kind = "threads" if a.scope == "threads" else "comments"
    docs = {} if kind == "threads" else {r["id"]: r for r in read_jsonl(DATA / "corpus.jsonl")}
    rundir = DATA / "runs" / a.scope
    runs = {p.stem: json.loads(p.read_text()) for p in sorted(rundir.glob("*.json"))}

    qids = [q["qid"] for q in queries if q["qid"] in qrels]
    # Lead with metrics the pool fully judges for every system: comments were
    # pooled to depth 20, threads only to depth 5.
    if kind == "threads":
        metrics_names = ["ndcg@5", "p@5", "p@5_strict", "mrr", "ndcg@10", "p@10"]
        paired_metrics = ("ndcg@5", "p@5")
        h2h_metrics = ("ndcg@5", "p@5")
    else:
        metrics_names = ["ndcg@10", "p@20", "recall@20", "recall@50", "mrr", "p@10", "p@10_strict"]
        paired_metrics = ("ndcg@10", "p@20", "recall@20", "recall@50")
        h2h_metrics = ("ndcg@10", "p@20", "p@10_strict")
    lead = metrics_names[0]
    labels = {"ndcg@10": "nDCG@10", "ndcg@5": "nDCG@5", "p@20": "P@20", "p@5": "P@5", "p@5_strict": "P@5 (grade 2)",
              "recall@20": "recall@20", "recall@50": "recall@50", "mrr": "MRR", "p@10": "P@10",
              "p@10_strict": "P@10 (grade 2)"}
    per = {}
    for s, run in runs.items():
        per[s] = {}
        for qid in qids:
            ranked = [d for d, _ in run.get(qid, [])]
            m = per_query(ranked, qrels[qid], opp[qid])
            if kind == "comments":
                share, cov = restaurant_view(ranked, qrels[qid], docs)
                m["rest_rel@10"], m["rest_judged@10"] = share, cov
            per[s][qid] = m

    # Queries with no relevant document at all can't contribute to recall/MRR;
    # nDCG is undefined for them too. They're listed rather than silently kept.
    usable = [q for q in qids if any(g >= 1 for g in qrels[q].values())]
    empty = [q for q in qids if q not in usable]

    rng = np.random.default_rng(SEED)
    summary = {}
    for s in runs:
        row = {}
        for mn in metrics_names + ["rest_rel@10", "rest_judged@10", "opposite@10", "judged@10", "judged@50"]:
            vals = [per[s][q].get(mn) for q in usable]
            vals = [v for v in vals if v is not None]
            if vals:
                row[mn] = boot(vals, rng)
        row["queries_with_opposite@10"] = sum(1 for q in usable if per[s][q]["opposite@10"] > 0)
        summary[s] = row

    order = sorted(summary, key=lambda s: -summary[s][lead][0])
    best = order[0]
    comp = {}
    for s in order:
        comp[s] = {}
        for mn in paired_metrics:
            ref = best if mn == lead else max(summary, key=lambda x: summary[x][mn][0])
            av = [per[ref][q][mn] for q in usable]
            bv = [per[s][q][mn] for q in usable]
            comp[s][mn] = (ref,) + paired(av, bv, rng)

    lines = [f"# Results tables ({a.tag}, scope {a.scope})\n",
             f"{len(usable)} queries with at least one relevant judged document"
             + (f"; {len(empty)} with none, excluded: {', '.join(empty)}" if empty else "") + ".",
             f"Mean with 95% bootstrap CI over queries, x100. Bootstrap {B} resamples.\n",
             "| system | " + " | ".join(labels[m] for m in metrics_names) + " | judged@10 | judged@50 |",
             "|---|" + "---|" * (len(metrics_names) + 2)]
    for s in order:
        r = summary[s]
        lines.append(f"| {s} | " + " | ".join(fmt_ci(r[m]) for m in metrics_names) +
                     f" | {r['judged@10'][0]*100:.0f}% | {r['judged@50'][0]*100:.0f}% |")

    lines += ["\n## Paired differences vs the leader\n",
              "Leader minus system, x100, with 95% CI and the share of bootstrap resamples in which the "
              "leader stays ahead. A CI that includes 0 means the gap is within noise.\n",
              "| system | " + " | ".join(f"{labels[m]} vs leader" for m in paired_metrics) + " |",
              "|---|" + "---|" * len(paired_metrics)]
    for s in order:
        cells = []
        for mn in paired_metrics:
            ref, d, lo, hi, p = comp[s][mn]
            cells.append("leader" if ref == s else f"{d*100:+.1f} [{lo*100:+.1f}, {hi*100:+.1f}] ({p*100:.0f}%) vs {ref}")
        lines.append(f"| {s} | " + " | ".join(cells) + " |")

    # Head-to-head between the dense models themselves (no hybrids), on the
    # metrics every system is fully judged on. The leader table above only
    # compares against one system; choosing a model needs the pairs.
    dense = [s for s in ("qwen3-8b", "oai-3-large", "gemini-2", "oai-3-small", "voyage-4-large",
                         "qwen3-8b@1024", "oai-3-large@1024", "gemini-2@1024") if s in per]
    lines += ["\n## Head-to-head between dense models\n",
              "Row minus column on the same queries, x100, 95% paired bootstrap CI. **Bold** when the CI "
              "excludes 0. Only metrics that are fully judged for every system.\n"]
    for mn in h2h_metrics:
        lines += [f"\n**{mn}**\n", "| | " + " | ".join(dense) + " |", "|---|" + "---|" * len(dense)]
        for a_ in dense:
            cells = []
            for b_ in dense:
                if a_ == b_:
                    cells.append("")
                    continue
                d, lo, hi, _ = paired([per[a_][q][mn] for q in usable], [per[b_][q][mn] for q in usable], rng)
                txt = f"{d*100:+.1f} [{lo*100:+.1f}, {hi*100:+.1f}]"
                cells.append(f"**{txt}**" if lo > 0 or hi < 0 else txt)
            lines.append(f"| {a_} | " + " | ".join(cells) + " |")

    # Per category and holdout split, on the lead metric.
    L = labels[lead]
    second = "recall@50" if kind == "comments" else "p@5"
    cats = sorted({qmeta[q]["category"] for q in usable})
    lines += [f"\n## {L} by query category (x100)\n",
              "| system | " + " | ".join(f"{c} (n={sum(qmeta[q]['category']==c for q in usable)})" for c in cats) + " |",
              "|---|" + "---|" * len(cats)]
    catmean = {s: {c: float(np.mean([per[s][q][lead] for q in usable if qmeta[q]["category"] == c]))
                   for c in cats} for s in order}
    for s in order:
        lines.append(f"| {s} | " + " | ".join(
            (f"**{catmean[s][c]*100:.1f}**" if catmean[s][c] == max(catmean[x][c] for x in order)
             else f"{catmean[s][c]*100:.1f}") for c in cats) + " |")
    lines += [f"\nCategory winners ({L}): " + "; ".join(
        f"{c}: {max(order, key=lambda s: catmean[s][c])}" for c in cats)]

    lines += [f"\n## Holdout vs tuning queries ({L}, {labels[second]}, x100 with 95% CI)\n",
              "Nothing was tuned on any queries (RRF k=60, prompts and stopwords were fixed in advance), "
              "so the split is a check that conclusions don't hinge on a subset.\n",
              f"| system | tuning {L} | holdout {L} | tuning {labels[second]} | holdout {labels[second]} |",
              "|---|---|---|---|---|"]
    for s in order:
        cells = []
        for mn in (lead, second):
            for h in (False, True):
                vals = [per[s][q][mn] for q in usable if qmeta[q]["holdout"] == h]
                cells.append(fmt_ci(boot(vals, rng)))
        lines.append(f"| {s} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |")

    lines += ["\n## Negation check\n",
              "Opposite comments are judged 0 *and* flagged as on-topic but negated or opposite "
              "(\"don't bring a date here\" for *date night*). Mean count in the top 10 per query, and the "
              "number of queries with at least one.\n",
              "| system | opposite in top 10 (mean/query) | queries with >=1 |", "|---|---|---|"]
    for s in sorted(order, key=lambda s: summary[s]["opposite@10"][0]):
        r = summary[s]
        lines.append(f"| {s} | {r['opposite@10'][0]:.2f} [{r['opposite@10'][1]:.2f}, {r['opposite@10'][2]:.2f}] "
                     f"| {r['queries_with_opposite@10']} / {len(usable)} |")

    if kind == "comments":
        lines += ["\n## Restaurant-level view\n",
                  "Top 50 comments grouped by restaurant (negated and excluded mentions skipped), ranked by "
                  "distinct people. Share of the top 10 restaurants backed by at least one comment judged >= 1, "
                  "x100 with 95% CI. `judged` is the share of those restaurants with any judged comment; "
                  "comments below each system's top 20 are judged only if another system pooled them.\n",
                  "| system | relevant restaurants in top 10 | judged |", "|---|---|---|"]
        for s in sorted(order, key=lambda s: -summary[s]["rest_rel@10"][0]):
            r = summary[s]
            lines.append(f"| {s} | {fmt_ci(r['rest_rel@10'])} | {r['rest_judged@10'][0]*100:.0f}% |" if "rest_judged@10" in r
                         else f"| {s} | {fmt_ci(r['rest_rel@10'])} | |")

    (HERE / f"RESULTS_TABLES_{a.tag}.md").write_text("\n".join(lines) + "\n")
    (DATA / f"metrics_{a.tag}.json").write_text(json.dumps(
        {"summary": summary, "per_query": per, "paired": comp, "category": catmean}, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
