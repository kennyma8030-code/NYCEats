"""Score thread-slice runs on v1 and v2 against their gold labels, side by side. No API, no database.

    python eval/thread_v6/score_gold.py v1 RUN [RUN ...] [--baseline RUN ...]
    python eval/thread_v6/score_gold.py v2half RUN [--baseline RUN ...]

eval/score.py does the scoring (score.py reads a thread-slice record's
`covers` to know which comments a chunk answered). Every run is scored on
the comments ALL the runs given cover, so a comparison is always on the same
comments: a baseline that never saw some of them (an earlier comment-mode run
on another sample) narrows the set rather than skewing it. v2half's gold is
cut to the items in slices/v2half.items.txt.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
import score as S  # noqa: E402

SETS = {"v1": (os.path.join(EVAL, "gold.jsonl"), os.path.join(EVAL, "items.jsonl")),
        "v2half": (os.path.join(EVAL, "v2", "gold.jsonl"), os.path.join(EVAL, "v2", "items.jsonl"))}
SHOW = ["comments", "drop_rate", "mention_recall", "mention_precision", "negative_mention_recall",
        "value_complaint_recall", "dish_negative_recall", "sign_accuracy", "opinion_type_acc"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("set", choices=sorted(SETS))
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--baseline", nargs="*", default=[])
    args = ap.parse_args()
    gold_path, items_path = SETS[args.set]
    gold, items = S.load_jsonl(gold_path), S.load_jsonl(items_path)
    if args.set == "v1":
        threads = {it["item_id"] for it in items if it["kind"] == "thread"}
        gold = [g for g in gold if g["item_id"] in threads]
    else:
        keep = set(open(os.path.join(HERE, "slices", "v2half.items.txt"), encoding="utf-8").read().split())
        gold = [g for g in gold if g["item_id"] in keep]
    alias, excluded = S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json")
    paths = args.runs + args.baseline
    runs = {p: S.load_run(p, items) for p in paths}
    common = set.intersection(*[r[1].get(0, set()) for r in runs.values()])
    print(f"{args.set}: {len(gold)} gold comments, {len({g['comment_id'] for g in gold} & common)} covered by every run")
    print("| run | " + " | ".join(SHOW) + " |")
    print("|---|" + "---:|" * len(SHOW))
    for p, (reps, covered, stats, mode) in runs.items():
        run = (reps, {0: covered.get(0, set()) & common}, stats, mode)
        per_rep, _, _, _ = S.evaluate(gold, items, run, alias, excluded, True, None)
        o = per_rep[0].get("overall", {})
        cells = [f"{o.get(k):.3f}" if isinstance(o.get(k), float) else str(o.get(k)) for k in SHOW]
        print(f"| {os.path.basename(p)} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
