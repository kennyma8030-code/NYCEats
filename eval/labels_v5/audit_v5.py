"""Diversity audit of the v5 gold: which schema cases have enough items to measure.

    python eval/labels_v5/audit_v5.py      # writes eval/labels_v5/diversity_v5.md and .json

Counts come from the v5 gold (eval/gold_v5.jsonl, eval/v2/gold_v5.jsonl) and
the comment text. Ambiguous and out-of-scope mentions are not scored, so they
are left out of every case except "non-restaurants". A case is counted per
COMMENT (an item exercises it if any scored mention does) because that is the
unit a model is run on; mention counts are given alongside. Fewer than 15
comments in a column is flagged as a gap: a recall on so few items swings by
more than ten points from one item.

v1 is split into its single comments (comment-mode items) and the comments of
its 17 whole threads (thread-mode items). v2 counts only its 237 top-ups,
because its other 244 comments are v1 comments already counted. Some cases
rest on text heuristics (marked "~"), since the gold does not label them.

The unlabeled v4 round 1 items are audited by the same text heuristics, to
show what labeling them would add.
"""

import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import threads as th  # noqa: E402

GAP = 15
I = re.IGNORECASE
QUESTION = re.compile(r"\?")
GET_THE = re.compile(r"\b(get|try|order|grab) (the|their)\b|\bmust[- ]?(have|try|get)\b|\bis a must\b", I)
OK_FINE = re.compile(r"\b(it'?s ok|it'?s okay|just ok|fine|mid|alright|meh)\b", I)
HAVENT = re.compile(r"\b(haven'?t been|never been|on my list|haven'?t tried|been meaning to|want to try|heard)\b", I)
DOLLAR = re.compile(r"\$\s?\d|\d+\s?(bucks|dollars)", I)
PRICE_WORDS = re.compile(r"\b(cheap|expensive|pricey|pricy|overpriced|affordable|inexpensive|reasonabl[ey] priced|priced|break the bank)\b", I)
COMPARE = re.compile(r"\b(better than|worse than|over|instead|than|compared to|like [A-Z])", I)
CLOSED = re.compile(r"\b(closed|shut down|RIP|no longer open|went out of business)\b", I)
AVOID = re.compile(r"\b(skip|avoid|stay away|don'?t bother|not worth)\b", I)
EVALUATIVE = {"overrated", "tourist trap", "hidden gem", "the og", "institution", "iconic", "classic", "top rated",
              "overhyped", "underrated", "staple", "gem", "legendary", "poor quality", "expensive", "new yorker classic"}


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def bodies():
    out = {}
    for p in ("items.jsonl", os.path.join("v2", "items.jsonl")):
        for it in load(os.path.join(EVAL, p)):
            if it["kind"] == "comment":
                c = it["context"]
                out[it["comment_id"]] = dict(body=c["body"], depth=c.get("depth") or 0, title=c["thread_title"])
            else:
                for x in it["comments"]:
                    out[x["comment_id"]] = dict(body=x["body"], depth=x.get("depth") or 0,
                                                title=it["context"]["thread_title"])
    return out


def cases(g, text):
    """Case -> number of scored mentions in this comment that exercise it."""
    c = collections.Counter()
    body = text["body"]
    scored = [m for m in g["mentions"] if not m["ambiguous"] and not m["out_of_scope"]]
    for m in g["mentions"]:
        if m["out_of_scope"] or m["entity_type"] in ("grocery_market", "other"):
            c["non-restaurant (out of scope)"] += 1
    bare = [m for m in scored if not m["reference_only"] and all(v is None for v in m["aspects"].values())]
    if len(scored) >= 3 and len(bare) >= 2:
        c["bare list (3+ names, 2+ bare)"] += 1
    for m in scored:
        a = m["aspects"]
        judged = any(v is not None for v in a.values())
        if not m["reference_only"] and not judged:
            c["bare endorsement"] += 1
        if judged:
            c["judged"] += 1
        if m["reference_only"]:
            c["reference_only (all)"] += 1
            if m["closed"]:
                c["reference_only: closed"] += 1
            elif QUESTION.search(body):
                c["~reference_only: question"] += 1
            elif re.search(r"(?i)compar|yardstick|anchor|inspir|like ", m["rationale"]):
                c["~reference_only: comparison anchor"] += 1
            else:
                c["~reference_only: fact / passing"] += 1
        if "reference_only" in m["uncertain_fields"]:
            c["reference_only uncertain"] += 1
        if m["judgment_question"]:
            c["judgment-carrying question (rule 2)"] += 1
        desc = [d.lower() for d in m["descriptors"]]
        if any(d in EVALUATIVE for d in desc):
            c["~evaluative descriptor"] += 1
        if any(d not in EVALUATIVE for d in desc):
            c["factual descriptor"] += 1
        if m["dishes_liked"]:
            c["dishes_liked"] += 1
            if GET_THE.search(body):
                c["~'get the X' recommendation"] += 1
        if m["dishes_disliked"]:
            c["dishes_disliked"] += 1
        if m["dishes_mentioned"]:
            c["dishes_mentioned"] += 1
        if m["experience"] == "secondhand":
            c["experience: secondhand"] += 1
        if m["experience"] == "unclear":
            c["experience: unclear"] += 1
        if m["price"] and a["value"] is None:
            c["price without value"] += 1
        if m["price"] in ("pricey", "very_pricey") and a["value"] in ("meh", "bad", "awful"):
            c["overpriced (price pricey + value negative)"] += 1
        if DOLLAR.search(body) and not PRICE_WORDS.search(body):
            c["~dollar figure only (c7 null price)"] += 1
        for k, v in a.items():
            if v is not None:
                c[f"level {v}"] += 1
                c[f"aspect {k}"] += 1
        if "mixed" in a.values():
            c["explicit mixed"] += 1
        if OK_FINE.search(body) and "meh" in a.values():
            c["~ok/fine/mid as meh"] += 1
        if m["is_negated"]:
            c["avoid (is_negated)"] += 1
        if m["named_in"] != "comment":
            c["nameless reply (named elsewhere)"] += 1
        if m["entity_type"] == "chain":
            c["chain"] += 1
        if len((m["restaurant_raw"] or "").split()) == 1:
            c["single-word name"] += 1
        for cid in m["conventions"]:
            c[f"convention {cid}"] += 1
        if not m["resolvable_comment_mode"]:
            c["not resolvable in comment mode"] += 1
        if not m["resolvable_thread_mode"]:
            c["not resolvable in thread mode"] += 1
    if sum(1 for m in scored if m["is_negated"]) >= 2:
        c["avoid list (2+ avoids)"] += 1
    if text["depth"] >= 3:
        c["deep chain (depth 3+)"] += len(scored) or 1
    if not scored:
        c["no scored mention (precision control)"] += 1
    return c


def audit_v4():
    """Text heuristics over the unlabeled v4 round 1 comments (minus the v1 overlap)."""
    out = collections.Counter()
    n = 0
    for it in load(os.path.join(EVAL, "v4", "items.jsonl")):
        if it.get("stratum") == "overlap_v1":
            continue
        title = it["context"]["thread_title"]
        comments = [it["context"]] if it["kind"] == "comment" else it["comments"]
        for x in comments:
            b = x.get("body") or ""
            n += 1
            out["thread-mode comment" if it["kind"] == "thread" else "comment-mode comment"] += 1
            if QUESTION.search(b):
                out["~question in comment"] += 1
            if CLOSED.search(b):
                out["~closed wording"] += 1
            if GET_THE.search(b):
                out["~'get the X' wording"] += 1
            if HAVENT.search(b):
                out["~haven't been / heard"] += 1
            if OK_FINE.search(b):
                out["~ok/fine/mid wording"] += 1
            if DOLLAR.search(b) and not PRICE_WORDS.search(b):
                out["~dollar figure only"] += 1
            if PRICE_WORDS.search(b):
                out["~price in words"] += 1
            if AVOID.search(b):
                out["~avoid wording"] += 1
            if re.search(r"(?i)overrated|overhyped|worst|letdown|disappoint|tourist trap|nasty|terrible", title):
                out["~judgment-carrying title"] += 1
        for t in it.get("tags") or []:
            out[f"tag {t}"] += 1
    return n, out


def main():
    text = bodies()
    cols = collections.OrderedDict()
    v1 = load(os.path.join(EVAL, "gold_v5.jsonl"))
    v2 = load(os.path.join(EVAL, "v2", "gold_v5.jsonl"))
    v1_ids = {g["comment_id"] for g in v1}
    groups = {
        "v1 comment mode": [g for g in v1 if g["item_id"].startswith("c")],
        "v1 thread mode": [g for g in v1 if g["item_id"].startswith("t")],
        "v2 top-ups": [g for g in v2 if g["comment_id"] not in v1_ids],
    }
    for name, gs in groups.items():
        items = collections.Counter()
        mentions = collections.Counter()
        for g in gs:
            c = cases(g, text[g["comment_id"]])
            for k, v in c.items():
                items[k] += 1
                mentions[k] += v
        cols[name] = dict(n=len(gs), items=items, mentions=mentions)
    keys = sorted({k for col in cols.values() for k in col["items"]})
    total = collections.Counter()
    for col in cols.values():
        total.update(col["items"])
    judgment_threads = {k: v for k, v in th.THREADS.items()}
    v4n, v4 = audit_v4()

    lines = ["# v5 gold diversity audit", "",
             "Generated by `eval/labels_v5/audit_v5.py`. Cells are comments (mentions in parentheses).",
             f"**Bold** marks a gap: fewer than {GAP} comments in the combined v1+v2 total.",
             "`~` marks a case found by text heuristics rather than by a gold field.", "",
             "| case | " + " | ".join(f"{k} (n={v['n']})" for k, v in cols.items()) + " | total |",
             "|---|" + "---:|" * (len(cols) + 1)]
    for k in keys:
        cells = [f"{c['items'][k]} ({c['mentions'][k]})" for c in cols.values()]
        t = total[k]
        name = f"**{k}**" if t < GAP else k
        lines.append(f"| {name} | " + " | ".join(cells) + f" | {'**%d**' % t if t < GAP else t} |")
    lines += ["", f"Threads whose question carries a judgment, classified in `threads.py`: {len(judgment_threads)}.", ""]
    lines += ["## Unlabeled v4 round 1 (text heuristics only)", "",
              f"{v4n} comments outside the v1 overlap. Labeling them would add roughly:", "",
              "| heuristic | comments |", "|---|---:|"]
    for k, v in sorted(v4.items(), key=lambda kv: (not kv[0].startswith("~"), -kv[1])):
        lines.append(f"| {k} | {v} |")
    path = os.path.join(HERE, "diversity_v5.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(HERE, "diversity_v5.json"), "w", encoding="utf-8") as f:
        json.dump(dict(columns={k: dict(n=v["n"], items=v["items"], mentions=v["mentions"]) for k, v in cols.items()},
                       total=total, v4=dict(n=v4n, counts=v4)), f, indent=1, sort_keys=True)
    print(path)


if __name__ == "__main__":
    main()
