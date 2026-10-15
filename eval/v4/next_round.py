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
   on chunks. Run files are grouped by model (run.py's recorded model, else
   the file name's first field) and every model weighs the same: failure
   rates are averaged across models, so a model with many run files does not
   dominate. A path that does not exist stops the run with a message.
   Production's stored output can be added with --production as one more
   model, but it is not needed: production's data only served to pick
   likely-hard comments for round 1. Failure types, per comment:

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
   failure f (both on one model's scale: the models' mean n and mean rate),
   so strata where failures concentrate get more. Quotas are proportional
   to the score with a floor of 3 (comments) or one chunk's worth (25
   comments), so no stratum goes dark. A mode that no run covered falls back
   to a uniform allocation, with a warning and "allocation_basis" in
   failure_rates.json saying so; --modes limits the draw to the modes
   wanted (e.g. --modes comment when only comment-mode runs exist).

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


MODES = ("comment", "thread")


def new_tally():
    return ({m: collections.defaultdict(collections.Counter) for m in MODES},
            {m: collections.Counter() for m in MODES})


def measure_file(by_item, ref, path, items, alias, excluded, per, wsum):
    """Add one run file's failures to per / wsum. Mirrors compare_v4.evaluate:
    a comment-mode run counts on single items, a thread-mode run on chunks,
    any other mode (production's "stored") on both. Returns how many gold
    lines name an item that is not loaded (skipped, never fatal)."""
    reps, covered, run_mode = CV.load_runs([path], items)
    preds, covered = reps.get(0, {}), covered.get(0, set())
    missing = 0
    for g in ref:
        it = by_item.get(g["item_id"])
        cid = g["comment_id"]
        if it is None:
            missing += 1
            continue
        if cid not in covered:
            continue
        if run_mode in MODES and it["mode"] != run_mode:
            continue
        F = failures(g, preds.get(cid, []), alias, excluded)
        mode = it["mode"]
        tags = set(it["tags"]) | {f"stratum:{it['stratum']}", "all"}
        if it["kind"] == "thread":
            tags |= set(next(c["tags"] for c in it["comments"] if c["comment_id"] == cid))
        for t in tags:
            per[mode][t]["n"] += 1
            per[mode][t].update(F)
        if it.get("weight"):
            wsum[mode]["n"] += it["weight"]
            for f in F:
                wsum[mode][f] += it["weight"]
    return missing


def model_of(path):
    """The model a run file belongs to: run.py's recorded model, else the
    file name's first field (<model>__<prompthash>__<mode>...)."""
    for r in CV.load_jsonl(path):
        if r.get("model"):
            return r["model"]
    return os.path.basename(path).split("__", 1)[0]


def combine(tallies):
    """Average models with equal weight, however many run files each has.

    For every (mode, tag) the combined failure rate is the mean of the
    models' rates (over the models that covered it), and the combined n is
    their mean n, so allocate() sees counts on one model's scale."""
    per, weighted = {m: collections.defaultdict(collections.Counter) for m in MODES}, {}
    for m in MODES:
        tags = {t for p, _ in tallies for t in p[m]}
        for t in tags:
            cov = [p[m][t] for p, _ in tallies if p[m][t]["n"]]
            n = sum(c["n"] for c in cov) / len(cov)
            per[m][t]["n"] = n
            for f in FAILURES:
                rate = sum(c[f] / c["n"] for c in cov) / len(cov)
                if rate:
                    per[m][t][f] = rate * n
        ws = [w[m] for _, w in tallies if w[m]["n"]]
        weighted[m] = {f: (sum(w[f] / w["n"] for w in ws) / len(ws) if ws else None) for f in FAILURES}
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
    ap.add_argument("--modes", default=",".join(MODES),
                    help="comma-separated modes to draw (default comment,thread); "
                         "e.g. --modes comment when only comment-mode runs exist")
    ap.add_argument("--round", type=int, help="round number to build (default: next)")
    ap.add_argument("--comments-per-mode", type=int, default=250)
    ap.add_argument("--dry-run", action="store_true", help="report failures and allocation; draw nothing")
    ap.add_argument("--base", default=HERE, help="round 1 directory; later rounds live in <base>/round<N>")
    args = ap.parse_args()
    args.modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    if not args.modes or set(args.modes) - set(MODES):
        raise SystemExit(f"--modes takes a comma-separated subset of {','.join(MODES)}")

    base = args.base
    dirs = CV.round_dirs(base)
    round_no = args.round or len(dirs) + 1
    items = CV.load_rounds(dirs)
    ref = [g for d in dirs for p in [os.path.join(d, "labels", args.ref + ".gold.jsonl")]
           if os.path.exists(p) for g in CV.load_jsonl(p)]
    if not ref:
        raise SystemExit(f"no {args.ref} labels yet: run labels.py export --pass {args.ref}")
    absent = [p for p in args.runs if not os.path.isfile(p)]
    if absent:
        raise SystemExit(f"run file(s) not found: {', '.join(absent)} "
                         "(an unexpanded glob matches nothing; check eval/runs/)")
    models = collections.defaultdict(list)      # model -> its run files, weighted equally
    for p in args.runs:
        models[model_of(p)].append(p)
    if args.production:
        prod = [p for d in dirs for p in glob.glob(os.path.join(d, "production", "*.jsonl"))]
        if not prod:
            raise SystemExit("--production: no production export (export_production.py) in any round")
        models["production (stored)"] = prod    # one export per round
    if not models:
        raise SystemExit("pass one or more model run files (run.py output) to find failures in")
    alias, excluded = S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json")
    by_item = {it["item_id"]: it for it in items}
    tallies, missing = [], 0
    for paths in models.values():
        per_m, wsum_m = new_tally()
        for p in paths:
            missing = max(missing, measure_file(by_item, ref, p, items, alias, excluded, per_m, wsum_m))
        tallies.append((per_m, wsum_m))
    if missing:
        print(f"warning: {missing} labeled comment(s) belong to items that are not loaded; skipped",
              file=sys.stderr)
    per, weighted = combine(tallies)

    budget = args.comments_per_mode
    tgt = round(budget * (1 - RANDOM_SHARE))
    basis = {}
    for m in MODES:
        if m not in args.modes:
            basis[m] = "not drawn (--modes)"
        elif not per[m].get("all", {}).get("n"):
            basis[m] = "uniform: no run covered this mode"
            print(f"WARNING: no run covered {m} mode, so its strata get a uniform allocation. "
                  f"Pass a {m}-mode run, or --modes {','.join(x for x in MODES if x != m)} "
                  f"to skip drawing it.", file=sys.stderr)
        else:
            basis[m] = "model failures"
    q_c, seen_c = allocate(per["comment"], corpus.COMMENT_STRATA, tgt, 3)
    q_t, seen_t = allocate(per["thread"], corpus.CHUNK_STRATA, tgt, 25)
    if "comment" not in args.modes:
        q_c = {s: 0 for s in q_c}
    if "thread" not in args.modes:
        q_t = {s: 0 for s in q_t}
    spec = {"comment": {"random": (budget - tgt) if "comment" in args.modes else 0, "strata": q_c},
            "thread": {"random_comments": (budget - tgt) if "thread" in args.modes else 0,
                       "strata_comments": q_t},
            "overlap_v1": 0}
    report = {"round": round_no, "reference": args.ref,
              "models": {k: [os.path.relpath(p, EVAL) for p in v] for k, v in models.items()},
              "model_weighting": "equal per model: failure rates averaged across models",
              "allocation_basis": basis, "skipped_unloaded_gold_lines": missing,
              "failures_counted": {"comment": seen_c, "thread": seen_t},
              "weighted_rates": weighted,
              "by_tag": {m: {t: {"n": round(c["n"], 1),
                                 **{f + "_rate": round(c[f] / c["n"], 3) for f in FAILURES if c[f]}}
                             for t, c in sorted(per[m].items())} for m in per},
              "spec": spec}
    print(f"models (equal weight): {', '.join(f'{k} ({len(v)} file(s))' for k, v in models.items())}")
    for m in MODES:
        print(f"\n== {m} mode ({basis[m]}): failure rate by heuristic, averaged over models "
              f"(n = labeled comments per model)")
        print(f"  {'tag':34} {'n':>6} " + " ".join(f"{SHORT[f]:>8}" for f in FAILURES))
        for t, c in sorted(per[m].items(), key=lambda x: -x[1]["n"]):
            print(f"  {t[:34]:34} {c['n']:>6.0f} " + " ".join(
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
