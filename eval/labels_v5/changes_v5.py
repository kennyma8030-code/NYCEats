"""Count every class of change between the v1/v2 gold and the v5 gold.

    python eval/labels_v5/changes_v5.py     # prints a markdown table for gold_changes.md

Counted over unique comments (v2's 244 v1 comments are counted once). The
level map, the bare predicate, the firsthand mapping and the override keys
come from convert_gold_v5.py, so this table can never describe a different
conversion than the one that ran.
"""

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
import convert_gold_v5 as cv  # noqa: E402


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def main():
    old, new = {}, {}
    for a, b in (("gold.jsonl", "gold_v5.jsonl"), (os.path.join("v2", "gold.jsonl"), os.path.join("v2", "gold_v5.jsonl"))):
        for g in load(os.path.join(EVAL, a)):
            old.setdefault(g["comment_id"], g)
        for g in load(os.path.join(EVAL, b)):
            new.setdefault(g["comment_id"], g)
    ovs = cv.merged_overrides()
    c = collections.Counter()
    for cid, g in old.items():
        for m, n, key in zip(g["mentions"], new[cid]["mentions"], cv.mention_keys(g)):
            c["mentions"] += 1
            a = m["aspects"]
            o = ovs.get(key)
            f = o["fields"] if o else {}
            if o:
                c["mentions with an override"] += 1
            food1_alone = a.get("food") == 1 and all(a[k] is None for k in a if k != "food") and not m["closed"]
            if food1_alone:
                c["old food +1 alone"] += 1
                if cv.is_bare(m):
                    c["food +1, no dish verdict (v1 'named as an answer')"] += 1
                    if n["reference_only"]:
                        c["  -> reference_only"] += 1
                    elif n["aspects"]["food"] is None:
                        c["  -> bare endorsement (food null)"] += 1
                    else:
                        c["  -> kept as a mild judgment"] += 1
                else:
                    c["food +1 with a dish verdict"] += 1
                    if "c1" in n["conventions"]:
                        c["  -> judges only dishes: food from the dishes (c1)"] += 1
                    else:
                        c["  -> an overall food verdict: label kept"] += 1
            if all(v is None for v in a.values()):
                c["old all-null"] += 1
                if n["reference_only"]:
                    c["  -> reference_only "] += 1
                else:
                    c["  -> not a reference (avoid, comparison loser, dish verdict)"] += 1
            if n["reference_only"] and m["closed"]:
                c["closed -> reference_only"] += 1
            if "reference_only" in n["uncertain_fields"]:
                c["reference_only marked uncertain"] += 1
            if n["judgment_question"]:
                c["judgment_question set"] += 1
            for k, v in a.items():
                if v is not None and not food1_alone and n["aspects"][k] != cv.LEVEL[v] and "c1" not in n["conventions"]:
                    c[f"aspect level changed by review ({k})"] += 1
            if "meh" in n["aspects"].values() and -1 not in a.values():
                c["became meh (fine/ok/alright, comparison loser, disliked dish)"] += 1
            for cid_ in n["conventions"]:
                c[f"convention {cid_}"] += 1
            if m["expensiveness"] is not None:
                c["price nulled: dollar figure only (c7)" if n["price"] is None else "price kept (stated in words)"] += 1
            old_fh = cv.FIRSTHAND[m["is_firsthand"]]
            if n["experience"] != old_fh:
                c[f"experience {old_fh} -> {n['experience']}"] += 1
            for d in m["dish_sentiment"]:
                if d["level"] == 0:
                    c["dish level 0 -> mentioned (no mixed-dish list)"] += 1
            if "dishes_liked" in f:
                mech = {d["dish"] for d in m["dish_sentiment"] if cv.dish_verdict(d) == "liked"}
                if set(f["dishes_liked"]) - mech:
                    c["dishes moved to liked by the review (meal-level praise)"] += 1
            if o and (o["add_desc"] or o["drop_desc"] or "descriptors" in f):
                c["descriptors edited by review"] += 1
            if m["ambiguous"] or m["out_of_scope"]:
                c["(not scored: ambiguous or out of scope)"] += 1
    c["override entries"] = len(cv.ov.OVERRIDES)
    order = ["mentions", "override entries", "mentions with an override", "(not scored: ambiguous or out of scope)",
             "old food +1 alone", "food +1, no dish verdict (v1 'named as an answer')",
             "  -> bare endorsement (food null)", "  -> kept as a mild judgment", "  -> reference_only",
             "food +1 with a dish verdict", "  -> judges only dishes: food from the dishes (c1)",
             "  -> an overall food verdict: label kept", "old all-null", "  -> reference_only ",
             "  -> not a reference (avoid, comparison loser, dish verdict)", "closed -> reference_only",
             "reference_only marked uncertain", "judgment_question set"]
    print("| change | mentions |")
    print("|---|---:|")
    for k in order + sorted(k for k in c if k not in order):
        label = k.replace("  -> ", "&nbsp;&nbsp;-> ").rstrip()
        print(f"| {label} | {c[k]} |")


if __name__ == "__main__":
    main()
