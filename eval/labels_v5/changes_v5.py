"""Count every class of change between the v1/v2 gold and the v5 gold.

    python eval/labels_v5/changes_v5.py     # prints a markdown table for gold_changes.md

Counted over unique comments (v2's 244 v1 comments are counted once).
"""

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import overrides as ov  # noqa: E402


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def main():
    old, new = {}, {}
    for a, b in (("gold.jsonl", "gold_v5.jsonl"), (os.path.join("v2", "gold.jsonl"), os.path.join("v2", "gold_v5.jsonl"))):
        for g in load(os.path.join(EVAL, a)):
            old.setdefault(g["comment_id"], g)
        for g in load(os.path.join(EVAL, b)):
            new.setdefault(g["comment_id"], g)
    keyed = collections.defaultdict(list)
    for e in ov.OVERRIDES:
        keyed[(e["comment_id"], e["name"])].append(e)
    c = collections.Counter()
    for cid, g in old.items():
        for m, n in zip(g["mentions"], new[cid]["mentions"]):
            c["mentions"] += 1
            a = m["aspects"]
            o = keyed.get((cid, m["canonical_name"]), [])
            f = {}
            for e in o:
                f.update(e["fields"])
            bare_old = a.get("food") == 1 and all(a[k] is None for k in a if k != "food") and not m["closed"]
            if bare_old:
                c["old food +1 alone (v1 'named as an answer')"] += 1
                if n["aspects"]["food"] is None and not n["reference_only"]:
                    c["food +1 -> bare endorsement (food null)"] += 1
                elif n["reference_only"]:
                    c["food +1 -> reference_only"] += 1
                elif "c1" in n["conventions"]:
                    c["food +1 -> food from the dishes (c1)"] += 1
                else:
                    c["food +1 -> kept as a mild judgment (decent or other)"] += 1
            all_null = all(v is None for v in a.values())
            if all_null:
                c["old all-null"] += 1
                if n["reference_only"]:
                    c["all-null -> reference_only"] += 1
                else:
                    c["all-null -> not reference (avoid, comparison loser, dish verdict)"] += 1
            if n["reference_only"] and m["closed"]:
                c["closed -> reference_only"] += 1
            if "reference_only" in n["uncertain_fields"]:
                c["reference_only marked uncertain"] += 1
            for k, v in a.items():
                lv = {3: "rave", 2: "good", 1: "decent", 0: "mixed", -1: "meh", -2: "bad", -3: "awful"}.get(v)
                if v is not None and n["aspects"][k] != lv and not bare_old:
                    c[f"aspect level changed by review ({k})"] += 1
            if any(x == "meh" for x in n["aspects"].values()) and not any(v == -1 for v in a.values()):
                c["became meh (fine/ok/alright, comparison loser c5)"] += 1
            for cv in n["conventions"]:
                c[f"convention {cv} decided a field"] += 1
            if m["expensiveness"] is not None and n["price"] is None:
                c["price nulled: dollar figure only (c7)"] += 1
            if m["expensiveness"] is not None and n["price"] is not None:
                c["price kept (stated in words)"] += 1
            old_fh = {True: "ate_there", False: "secondhand", None: "unclear"}[m["is_firsthand"]]
            if n["experience"] != old_fh:
                c[f"experience {old_fh} -> {n['experience']}"] += 1
            if n["judgment_question"]:
                c["judgment_question set"] += 1
            for d in m["dish_sentiment"]:
                if d["level"] == 0:
                    c["dish level 0 -> mentioned (no mixed-dish list)"] += 1
            if "dishes_liked" in f and not any((d["level"] or 0) > 0 for d in m["dish_sentiment"]):
                c["dishes moved to liked by meal-level praise"] += 1
            if any(k in f for k in ("add_desc", "drop_desc")) or any("add_desc" in e["fields"] or "drop_desc" in e["fields"] for e in o):
                c["descriptor edited by review"] += 1
            if m["ambiguous"] or m["out_of_scope"]:
                c["(not scored: ambiguous or out of scope)"] += 1
    c["override entries"] = len(ov.OVERRIDES)
    c["mentions with an override"] = len(keyed)
    order = ["mentions", "override entries", "mentions with an override", "(not scored: ambiguous or out of scope)",
             "old food +1 alone (v1 'named as an answer')", "food +1 -> bare endorsement (food null)",
             "food +1 -> kept as a mild judgment (decent or other)", "food +1 -> food from the dishes (c1)",
             "food +1 -> reference_only", "old all-null", "all-null -> reference_only",
             "all-null -> not reference (avoid, comparison loser, dish verdict)", "closed -> reference_only",
             "reference_only marked uncertain", "judgment_question set"]
    print("| change | mentions |")
    print("|---|---:|")
    for k in order + sorted(k for k in c if k not in order):
        print(f"| {k} | {c[k]} |")


if __name__ == "__main__":
    main()
