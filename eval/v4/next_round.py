"""Measure where candidate models fail against Claude's labels, then draw the
next round so it oversamples those failures. Rerunnable for round 3 and on.

    python eval/v4/next_round.py eval/runs/*__v4.jsonl --dry-run      # failure rates + proposed allocation only
    EVAL_DB_URL=postgresql://... python eval/v4/next_round.py eval/runs/a__comment__v4.jsonl eval/runs/a__thread__v4.jsonl
    python eval/v4/next_round.py --ref same_input eval/runs/<model>__<hash>__comment__v4.jsonl
    python eval/v4/next_round.py --production ...      # also count production's stored output, if exported

The database is only read, and only when drawing (to render the new items).

1. FAILURES. Every labeled comment in every existing round (eval/v4,
   eval/v4/round2, ...) is compared with each model run given on the
   command line, using score.py's matching against Claude's labels (the
   --ref pass). A comment-mode run counts on single items, a thread-mode run
   on chunks. Several runs pool their counts, so failures several models
   share weigh most. Production's stored output can be added with
   --production, but it is not needed: production's data only served to
   pick likely-hard comments for round 1. Failure types, per comment:

     dropped_comment         the reference has a required mention, the system has none
     dropped_mention         a required reference mention is unmatched
     wrong_place             a mention is dropped AND the system named some other place
     spurious_mention        the system named a place the reference does not have, and dropped nothing
     wrong_sign              a matched aspect has the opposite sign
     scored_milder           a reference aspect at -1 or below is null or higher in the system
     missed_negative         a reference negative (any aspect <= -1) is dropped or carries no negative
     missed_negation         reference is_negated, system not
     missed_price_complaint  reference value complaint (or value < 0) dropped or not flagged
     missed_dish_complaint   a reference dish at -1 or below / avoid with no negative dish entry
     stuck_default           the system left a mention at food 0.3 only while the reference
                             scored something else

   Rates are reported per heuristic tag and per stratum, for each mode, plus
   traffic-weighted overall rates. Comments a run never processed are skipped.

2. ALLOCATION. 30% of each mode's budget is random, as in round 1. The other
   70% goes to the strata. A failure type counts when it showed up at least
   once in that mode. Each stratum s gets the score
       sum over counted types f of (c[s,f] + 0.5) / (n[s] + 1)
   where n[s] is the labeled comments carrying tag s and c[s,f] those with
   failure f, so strata where failures concentrate get more. Quotas are
   proportional to the score with a floor of 3 (comments) or one chunk's
   worth (25 comments), so no stratum goes dark.

3. DRAW. The population is every eligible comment created before
   corpus.CUTOFF (Oct 9), as in round 1. If round 1's snapshot pickle is in
   the cache it is used (fast, and exactly round 1's population). Otherwise
   the corpus is read from the live database, read-only, with the same
   cutoff, and a warning says the population may have drifted since round 1
   (late comments, deletions, extraction progress shifting heuristic tags),
   so pooled weights are approximate. Every comment in an earlier round,
   and every thread an earlier round took a chunk from, is excluded, as are
   the v1/v2 sets. The round is built in a hidden temp dir and renamed to
   round<N>/ only when complete (items.jsonl, design.json,
   failure_rates.json). Then run packets.py and batches.py with --dir, and
   label it.
"""

import argparse
import collections
import glob
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
sys.path.insert(0, HERE)
import score as S  # noqa: E402
import corpus  # noqa: E402
import design as D  # noqa: E402
import compare_v4 as CV  # noqa: E402
from extract import CHAINS  # noqa: E402

FAILURES = ["dropped_comment", "dropped_mention", "wrong_place", "spurious_mention", "wrong_sign",
            "scored_milder", "missed_negative", "missed_negation", "missed_price_complaint",
            "missed_dish_complaint", "stuck_default"]
SHORT = dict(zip(FAILURES, ["drop_cmt", "drop_mnt", "wrong_pl", "spurious", "sign", "milder",
                            "miss_neg", "negation", "price", "dish", "default"]))
RANDOM_SHARE = 0.30


def failures(g, preds, alias, excluded):
    ms = S.model_mentions(preds, alias, True)
    gms = [x for x in g["mentions"] if x["canonical_key"] not in CHAINS]
    required = [x for x in gms if S.is_required(x)]
    pairs, fps = S.match(gms, ms)
    fps = [m for m in fps if m["_key"] not in excluded]
    matched = {id(x): m for x, m, _ in pairs}
    F = set()
    if required and not [m for m in ms if m["_key"] not in excluded]:
        F.add("dropped_comment")
    missed = [x for x in required if id(x) not in matched]
    if missed:
        F.add("dropped_mention")
        if fps:
            F.add("wrong_place")
    elif fps:
        F.add("spurious_mention")
    for x in required:
        m = matched.get(id(x))
        dish_negs = [d for d in x.get("dish_sentiment", []) if (d["level"] is not None and d["level"] <= -1) or d["avoid"]]
        if m is None:
            if S.gold_negative(x):
                F.add("missed_negative")
            if x.get("value_complaint"):
                F.add("missed_price_complaint")
            if dish_negs:
                F.add("missed_dish_complaint")
            continue
        asp = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
        for a in S.ASPECTS:
            gv, mv = x["aspects"].get(a), S.bucket(asp.get(a))
            if gv is not None and mv is not None and gv != 0 and mv != 0 and S.sign(gv) != S.sign(mv):
                F.add("wrong_sign")
            if gv is not None and gv <= -1 and (mv is None or mv > gv):
                F.add("scored_milder")
        if S.gold_negative(x) and not S.model_negative(m):
            F.add("missed_negative")
        if x["is_negated"] and not m.get("is_negated"):
            F.add("missed_negation")
        if x.get("value_complaint") and not S.model_value_complaint(m):
            F.add("missed_price_complaint")
        if dish_negs:
            ents = S.model_dish_entries(m) or []
            if not all(any(isinstance(e, dict) and S.lenient_same(e.get("dish"), d["dish"])
                           and ((S.bucket(e.get("level")) or 0) < 0 or e.get("avoid")) for e in ents)
                       for d in dish_negs):
                F.add("missed_dish_complaint")
        if corpus.is_default(m):
            others = [v for k, v in x["aspects"].items() if k != "food" and v is not None]
            if others or x["aspects"].get("food") not in (1, None):
                F.add("stuck_default")
    return F


def measure(items, ref, runs, alias, excluded):
    """Per mode: {tag: {"n": .., f: count}}, plus weighted overall rates.

    runs: [(preds, covered, run_mode)]. A comment-mode run counts on single
    items and a thread-mode run on chunks (as in compare_v4); any other mode,
    such as production's "stored", counts on both. Runs pool: a comment
    scored by two runs counts twice."""
    by_item = {it["item_id"]: it for it in items}
    per = {"comment": collections.defaultdict(collections.Counter),
           "thread": collections.defaultdict(collections.Counter)}
    wsum = {"comment": collections.Counter(), "thread": collections.Counter()}
    for g, it, preds in ((g, by_item.get(g["item_id"]), preds) for preds, covered, run_mode in runs
                         for g in ref if g["comment_id"] in covered
                         and (run_mode not in ("comment", "thread") or by_item[g["item_id"]]["mode"] == run_mode)):
        F = failures(g, preds.get(g["comment_id"], []), alias, excluded)
        mode = it["mode"]
        tags = set(it["tags"]) | {f"stratum:{it['stratum']}", "all"}
        if it["kind"] == "thread":
            tags |= set(next(c["tags"] for c in it["comments"] if c["comment_id"] == g["comment_id"]))
        for t in tags:
            per[mode][t]["n"] += 1
            per[mode][t].update(F)
        if it.get("weight"):
            wsum[mode]["n"] += it["weight"]
            for f in F:
                wsum[mode][f] += it["weight"]
    weighted = {m: {f: (w[f] / w["n"] if w["n"] else None) for f in FAILURES} for m, w in wsum.items()}
    return per, weighted


def allocate(per_mode, strata, total, floor):
    seen = [f for f in FAILURES if per_mode.get("all", {}).get(f)]
    score = {}
    for s in strata:
        c = per_mode.get(s, collections.Counter())
        score[s] = sum((c[f] + 0.5) / (c["n"] + 1) for f in seen) if seen else 1.0
    tot = sum(score.values()) or 1
    q = {s: max(floor, round(total * score[s] / tot)) for s in strata}
    while sum(q.values()) > total and any(v > floor for v in q.values()):
        s = max((s for s in q if q[s] > floor), key=lambda s: q[s] / score[s])
        q[s] -= 1
    return q, seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", choices=("same_input", "full_context"), default="full_context")
    ap.add_argument("runs", nargs="*", help="candidate model run files (run.py output) to find failures in")
    ap.add_argument("--production", action="store_true",
                    help="also count production's stored output (needs export_production.py first)")
    ap.add_argument("--round", type=int, help="round number to build (default: next)")
    ap.add_argument("--comments-per-mode", type=int, default=250)
    ap.add_argument("--dry-run", action="store_true", help="report failures and allocation; draw nothing")
    ap.add_argument("--base", default=HERE, help="round 1 directory; later rounds live in <base>/round<N>")
    args = ap.parse_args()

    base = args.base
    dirs = CV.round_dirs(base)
    round_no = args.round or len(dirs) + 1
    items = CV.load_rounds(dirs)
    ref = [g for d in dirs for p in [os.path.join(d, "labels", args.ref + ".gold.jsonl")]
           if os.path.exists(p) for g in CV.load_jsonl(p)]
    if not ref:
        raise SystemExit(f"no {args.ref} labels yet: run labels.py export --pass {args.ref}")
    groups = [[p] for p in args.runs]           # each model run file is its own system
    if args.production:
        prod = [p for d in dirs for p in glob.glob(os.path.join(d, "production", "*.jsonl"))]
        if not prod:
            raise SystemExit("--production: no production export (export_production.py) in any round")
        groups.append(prod)                     # one export per round, merged into one system
    if not groups:
        raise SystemExit("pass one or more model run files (run.py output) to find failures in")
    system = [p for g in groups for p in g]
    runs = []
    for g in groups:
        reps, covered, mode = CV.load_runs(g, items)
        runs.append((reps.get(0, {}), covered.get(0, set()), mode))
    alias, excluded = S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json")
    per, weighted = measure(items, ref, runs, alias, excluded)

    budget = args.comments_per_mode
    tgt = round(budget * (1 - RANDOM_SHARE))
    q_c, seen_c = allocate(per["comment"], corpus.COMMENT_STRATA, tgt, 3)
    q_t, seen_t = allocate(per["thread"], corpus.CHUNK_STRATA, tgt, 25)
    spec = {"comment": {"random": budget - tgt, "strata": q_c},
            "thread": {"random_comments": budget - tgt, "strata_comments": q_t},
            "overlap_v1": 0}
    report = {"round": round_no, "reference": args.ref, "system": [os.path.relpath(p, EVAL) for p in system],
              "failures_counted": {"comment": seen_c, "thread": seen_t},
              "weighted_rates": weighted,
              "by_tag": {m: {t: {"n": c["n"], **{f: c[f] for f in FAILURES if c[f]},
                                 **{f + "_rate": round(c[f] / c["n"], 3) for f in FAILURES if c[f]}}
                             for t, c in sorted(per[m].items())} for m in per},
              "spec": spec}
    for m in ("comment", "thread"):
        print(f"\n== {m} mode: failure rate by heuristic (n = labeled comments the system processed)")
        print(f"  {'tag':34} {'n':>4} " + " ".join(f"{SHORT[f]:>8}" for f in FAILURES))
        for t, c in sorted(per[m].items(), key=lambda x: -x[1]["n"]):
            print(f"  {t[:34]:34} {c['n']:>4} " + " ".join(
                f"{(c[f] / c['n'] if c['n'] else 0):>8.2f}" for f in FAILURES))
        print("  weighted to traffic: " + ", ".join(f"{f}={v:.3f}" for f, v in weighted[m].items() if v))
    print("\nallocation:", json.dumps(spec, indent=1))
    out_dir = os.path.join(base, f"round{round_no}")
    if args.dry_run:
        return
    if os.path.exists(out_dir):
        raise SystemExit(f"{out_dir} already exists; remove it or pass --round")

    # Round 1's snapshot is the fast path and exactly round 1's population.
    # Without it the corpus comes from the live database (read-only, same
    # cutoff), which may have drifted since.
    with open(os.path.join(base, "design.json"), encoding="utf-8") as f:
        snapshot_at = json.load(f)["snapshot_at"]
    cp = corpus.cached_corpus()
    if cp.snapshot_at != snapshot_at:
        print(f"WARNING: drawing from snapshot {cp.snapshot_at}, not round 1's {snapshot_at}. The population "
              f"(comments before {corpus.CUTOFF:%Y-%m-%d}) may have drifted since: deletions, late comments, "
              "and extraction progress moving heuristic tags. Weights pooled across rounds are approximate.",
              file=sys.stderr)

    seed = f"nyceats-eval-v4-r{round_no}"
    prior = set()
    prior_threads = set()
    for it in items:
        if it["kind"] == "comment":
            prior.add(it["comment_id"])
        else:
            prior.update(c["comment_id"] for c in it["comments"])
            prior_threads.add(it["thread_id"])
    chunks, stratum_t, d_t = D.draw_threads(cp, spec["thread"], seed, cp.old_ids | prior,
                                            cp.old_threads | prior_threads)
    in_chunks = {c for key, _ in chunks for c in cp.chunks[key]["comment_ids"]}
    singles, stratum_c, d_c = D.draw_comments(cp, spec["comment"], seed, cp.old_ids | prior | in_chunks)
    design = {"thread": d_t, "comment": d_c}
    conn = corpus.connect()
    new, mismatches = D.build_items(conn, cp, singles, chunks, stratum_c, stratum_t, design, round_no, seed)
    conn.close()
    D.assign_splits(new, seed)
    meta = D.summarize(cp, new, design, mismatches, round_no, seed, spec)
    # Build in a hidden temp dir and rename at the end: a draw that fails
    # leaves no half-written round<N>/ for load_rounds to pick up.
    tmp = tempfile.mkdtemp(prefix=f".round{round_no}-", dir=base)
    try:
        D.write_round(tmp, new, meta)
        with open(os.path.join(tmp, "failure_rates.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1)
        os.rename(tmp, out_dir)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    print(json.dumps(meta["counts"], indent=1))
    print(f"\nnext: python eval/v4/packets.py --dir {out_dir} && python eval/v4/batches.py --dir {out_dir}")
    print("      label both passes, then labels.py export --dir ... for each pass")
    print(f"      run the candidate models on {out_dir}/items_single.jsonl and items_thread.jsonl, then compare_v4.py")


if __name__ == "__main__":
    main()
