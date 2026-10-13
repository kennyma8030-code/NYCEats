"""Score production, model runs and Claude's own labels on v4, against either
label set, broken down every way the design allows. No database, no model.

    python eval/v4/compare_v4.py                         # reference = full_context labels
    python eval/v4/compare_v4.py --ref same_input
    python eval/v4/compare_v4.py --ref full_context eval/runs/x__abc__thread__v4.jsonl
    python eval/v4/compare_v4.py --dirs eval/v4 eval/v4/round2      # pool rounds
    python eval/v4/compare_v4.py --self-test             # production vs itself must be perfect

Runs scored by default: production's stored output (production/*.jsonl in
each round) and every eval/runs/*__v4*.jsonl (run.py ... --items
eval/v4/items_single.jsonl --tag v4, and the same with items_thread.jsonl).
A comment-mode run is scored on single items, a thread-mode run on thread
items, production on both.

Every comment is scored with score.py's own score_comment, so the metrics
mean exactly what eval/README.md says. On top of that, per mode:

  <mode>                     unweighted, every item of that mode
  <mode> weighted            re-weighted to real traffic with each item's
                             inverse inclusion probability (Hajek: weighted
                             counts, then ratios). v1 overlap items have no
                             weight and are left out.
  <mode> weighted tuning / holdout, and unweighted tuning / holdout
  <mode> draw:<d>            random / targeted / overlap_v1
  <mode> stratum:<s>         one per stratum
  <mode> tag:<t>             one per heuristic; an item counts in every tag it carries

Ceilings, when the labels exist:

  claude self-consistency    the duplicate copy of each self-consistency
                             packet, scored against the primary copy of the
                             reference pass. How often Claude agrees with
                             itself is the most any model can agree with Claude.
  claude same_input          same_input labels scored against full_context
                             labels: what the mode's missing context costs
                             even Claude.
  claude vs v1 gold          the reference labels on the 50 overlap items,
                             scored against v1's hand gold.

Writes results/comparison_<ref>.json and .md in the first --dirs directory.
"""

import argparse
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
sys.path.insert(0, HERE)
import score as S  # noqa: E402
import corpus  # noqa: E402
import design as D  # noqa: E402
import labels as L  # noqa: E402

SHOW = ["drop_rate", "mention_recall", "negative_mention_recall", "value_complaint_recall",
        "dish_negative_recall", "sign_accuracy", "mention_precision", "comments"]


def load_jsonl(path):
    return L.load_jsonl(path)


# ---------------------------------------------------------------- items and weights
def load_rounds(dirs):
    """Items from every round, with a combined weight when rounds are pooled:
    pi = sum over rounds of the item's inclusion probability under that
    round's design (the item's stratum is recomputed from its tags with each
    round's stratum order). A good approximation because every pi is tiny."""
    items, designs = [], []
    for d in dirs:
        with open(os.path.join(d, "design.json"), encoding="utf-8") as f:
            designs.append(json.load(f)["design"])
        items += load_jsonl(os.path.join(d, "items.jsonl"))
    if len(dirs) > 1:
        for it in items:
            if it["draw"] == "overlap_v1":
                continue
            pi = 0.0
            for des in designs:
                dm = des[it["mode"]]
                s = corpus.stratum_of(set(it["tags"]), dm["strata_order"])
                pi += (D.pi_chunk(dm, s, it["chunk_size"]) if it["mode"] == "thread"
                       else D.pi_comment(dm, s))
            it["pi"], it["weight"] = pi, 1 / pi
    return items


def load_runs(paths, items):
    """Merge run files (e.g. one production export per round) into one run."""
    reps, covered = collections.defaultdict(dict), collections.defaultdict(set)
    mode = None
    for p in paths:
        r, c, _, m = S.load_run(p, items)
        for rep, preds in r.items():
            reps[rep].update(preds)
        for rep, ids in c.items():
            covered[rep] |= ids
        mode = mode or m
    return reps, covered, mode


# ---------------------------------------------------------------- scoring
def groups_for(it, cid):
    mode = it["mode"]
    tags = set(it["tags"])
    if it["kind"] == "thread":
        tags |= set(next(c["tags"] for c in it["comments"] if c["comment_id"] == cid))
    g = [mode, f"{mode} {it['split']}", f"{mode} draw:{it['draw']}", f"{mode} stratum:{it['stratum']}"]
    g += [f"{mode} tag:{t}" for t in sorted(tags)]
    return g


def evaluate(ref, items, preds, covered, run_mode, alias, excluded):
    """ref: gold lines. preds: {comment_id: [mentions]}. Returns {scope: metrics}."""
    by_item = {it["item_id"]: it for it in items}
    acc = collections.defaultdict(S.Acc)
    raw = collections.Counter()
    dish_capable = any(isinstance(m, dict) and isinstance(m.get("dish_sentiment"), list)
                       for ms in preds.values() for m in ms)
    for g in ref:
        it = by_item.get(g["item_id"])
        cid = g["comment_id"]
        if it is None or cid not in covered:
            continue
        if run_mode in ("comment", "thread") and it["mode"] != run_mode:
            continue
        a = S.score_comment(g, preds.get(cid, []), it["mode"], alias, excluded, True)
        for scope in ["all"] + groups_for(it, cid):
            acc[scope].add(a)
        if it.get("weight"):
            for scope in (f"{it['mode']} weighted", f"{it['mode']} weighted {it['split']}"):
                acc[scope].add(a, it["weight"])
                raw[scope] += 1
    out = {k: S.summarize(v, dish_capable) for k, v in acc.items()}
    for k, n in raw.items():
        # summarize's "comments" is the weighted sum here; keep it as the
        # traffic the sample stands for, and report the real count.
        out[k]["traffic_comments"] = round(out[k]["comments"])
        out[k]["comments"] = n
    return out


def score_run(name, paths, ref, items, alias, excluded, rep=0, both_modes=False):
    """both_modes: Claude's label files hold comment and thread packets
    together, so they are scored on every item rather than one mode's."""
    reps, covered, mode = load_runs(paths, items)
    if both_modes:
        mode = "labels"
    res = evaluate(ref, items, reps.get(rep, {}), covered.get(rep, set()), mode, alias, excluded)
    return {"name": name, "files": [os.path.relpath(p, EVAL) for p in paths], "mode": mode, "metrics": res}


def v1_agreement(ref_pass_dirs, ref_name, items, alias, excluded):
    """The reference labels scored against v1's hand gold on the overlap items."""
    v1 = {g["comment_id"]: g for g in load_jsonl(os.path.join(EVAL, "gold.jsonl"))}
    overlap = [it for it in items if it["draw"] == "overlap_v1" and it["comment_id"] in v1]
    if not overlap:
        return None
    runs = [os.path.join(d, "labels", ref_name + ".run.jsonl") for d in ref_pass_dirs]
    runs = [p for p in runs if os.path.exists(p)]
    if not runs:
        return None
    reps, covered, _ = load_runs(runs, items)
    acc = S.Acc()
    for it in overlap:
        cid = it["comment_id"]
        if cid in covered.get(0, set()):
            acc.add(S.score_comment(v1[cid], reps[0].get(cid, []), "comment", alias, excluded, True))
    dish = any(isinstance(m.get("dish_sentiment"), list) for ms in reps[0].values() for m in ms)
    return S.summarize(acc, dish)


# ---------------------------------------------------------------- output
def md_table(rows, scope):
    head = "| run | " + " | ".join(SHOW) + " |\n|---" * 1 + "|---" * len(SHOW) + "|"
    lines = [head]
    for r in rows:
        m = r["metrics"].get(scope)
        if not m:
            continue
        lines.append(f"| {r['name']} | " + " | ".join(S.fmt(m.get(k)) for k in SHOW) + " |")
    return "\n".join(lines) if len(lines) > 1 else "_no data_"


def write(out_dir, ref_name, out):
    os.makedirs(out_dir, exist_ok=True)
    jp = os.path.join(out_dir, f"comparison_{ref_name}.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)
    rows = out["runs"] + out["ceilings"]
    scopes = sorted({s for r in rows for s in r["metrics"]})
    main = [s for s in ("comment weighted", "comment", "comment weighted tuning", "comment weighted holdout",
                        "thread weighted", "thread", "thread weighted tuning", "thread weighted holdout")
            if s in scopes]
    lines = [f"# v4 comparison, reference = {ref_name} labels", "",
             f"Reference: {out['reference']['comments']} comments, "
             f"{out['reference']['with_mention']} with a required mention. "
             "'weighted' is re-weighted to real traffic; ceilings are Claude against itself.", ""]
    for s in main:
        lines += [f"## {s}", "", md_table(rows, s), ""]
    lines += ["## By draw, stratum and heuristic", ""]
    for s in scopes:
        if s in main or s == "all":
            continue
        lines += [f"### {s}", "", md_table(rows, s), ""]
    if out.get("v1_overlap_agreement"):
        m = out["v1_overlap_agreement"]
        lines += ["## Claude vs v1 hand gold (overlap items)", "",
                  "| " + " | ".join(SHOW) + " |", "|---" * len(SHOW) + "|",
                  "| " + " | ".join(S.fmt(m.get(k)) for k in SHOW) + " |", ""]
    mp = os.path.join(out_dir, f"comparison_{ref_name}.md")
    with open(mp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return jp, mp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*", help="extra run files (default: production exports + eval/runs/*__v4*.jsonl)")
    ap.add_argument("--ref", choices=L.PASSES, default="full_context")
    ap.add_argument("--dirs", nargs="*", default=None,
                    help="round directories to pool (default: eval/v4 and every eval/v4/round*)")
    ap.add_argument("--self-test", action="store_true",
                    help="use production's stored output as the reference; it must score perfectly")
    args = ap.parse_args()
    dirs = args.dirs or [HERE] + sorted(glob.glob(os.path.join(HERE, "round*")))
    items = load_rounds(dirs)
    alias, excluded = S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json")
    prod = [p for d in dirs for p in sorted(glob.glob(os.path.join(d, "production", "*.jsonl")))]

    if args.self_test:
        reps, covered, _ = load_runs(prod, items)
        ref = L.gold_lines(items, {c: reps[0].get(c, []) for c in covered[0]}, alias, excluded, "production")
        r = score_run("production", prod, ref, items, alias, excluded)["metrics"]["all"]
        print(json.dumps({k: r.get(k) for k in SHOW}, indent=1))
        assert r["drop_rate"] == 0 and r["mention_recall"] == 1 and r["mention_precision"] == 1, r
        assert r["sign_accuracy"] in (1, None) and r["negative_mention_recall"] in (1, None), r
        print("self-test ok")
        return

    ref_paths = [os.path.join(d, "labels", args.ref + ".gold.jsonl") for d in dirs]
    ref_paths = [p for p in ref_paths if os.path.exists(p)]
    if not ref_paths:
        raise SystemExit(f"no {args.ref} labels yet: run labels.py export --pass {args.ref}")
    ref = [g for p in ref_paths for g in load_jsonl(p)]

    runs = []
    if prod:
        runs.append(score_run("production (stored)", prod, ref, items, alias, excluded))
    extra = args.runs or sorted(glob.glob(os.path.join(EVAL, "runs", "*__v4*.jsonl")))
    for p in extra:
        runs.append(score_run(os.path.basename(p).removesuffix(".jsonl"), [p], ref, items, alias, excluded))

    ceilings = []
    own = [os.path.join(d, "labels", args.ref + ".run.jsonl") for d in dirs]
    own = [p for p in own if os.path.exists(p)]
    if own:
        ceilings.append(score_run(f"claude self-consistency ({args.ref})", own, ref, items, alias, excluded,
                                  rep=1, both_modes=True))
    if args.ref == "full_context":
        si = [os.path.join(d, "labels", "same_input.run.jsonl") for d in dirs]
        si = [p for p in si if os.path.exists(p)]
        if si:
            ceilings.append(score_run("claude same_input vs full_context", si, ref, items, alias, excluded,
                                      both_modes=True))

    out = {"reference": {"pass": args.ref, "files": [os.path.relpath(p, EVAL) for p in ref_paths],
                         "comments": len(ref), "with_mention": sum(g["has_mention"] for g in ref)},
           "dirs": [os.path.relpath(d, EVAL) for d in dirs],
           "runs": runs, "ceilings": ceilings,
           "v1_overlap_agreement": v1_agreement(dirs, args.ref, items, alias, excluded)}
    jp, mp = write(os.path.join(dirs[0], "results"), args.ref, out)
    print(jp)
    print(mp)
    for s in ("comment weighted", "thread weighted"):
        print(f"\n== {s}")
        for r in runs + ceilings:
            m = r["metrics"].get(s)
            if m:
                print(f"  {r['name'][:50]:50} " + " ".join(f"{k}={S.fmt(m.get(k))}" for k in SHOW[:4]))


if __name__ == "__main__":
    main()
