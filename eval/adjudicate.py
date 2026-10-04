"""List every disagreement between gold and a run, with proposed weakness tags.

    python eval/adjudicate.py eval/baseline/production__stored__all.jsonl --out eval/baseline/disagreements.jsonl

Used AFTER labeling is final: each disagreement is re-read; gold errors are
fixed in labels/batchNN.py (and logged in gold_changes.md), and confirmed
model failures keep their weakness tags (eval/v2/taxonomy.md).
"""

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import score  # noqa: E402


def propose(g, gold_line, m, mode, n_req):
    """Weakness tags for one required gold mention (m = matched model mention or None)."""
    tags = []
    gap = g.get(f"resolvable_{mode}_mode") is False
    if m is None:
        if gap:
            tags.append("context_gap")
        elif g["closed"]:
            tags.append("closed_place")
        elif g["named_in"] != "comment":
            tags.append("dropped_nameless_reply")
        elif not any(v is not None for v in g["aspects"].values()):
            tags.append("dropped_reference_mention")
        elif n_req >= 3:
            tags.append("dropped_in_list")
        else:
            tags.append("dropped_named_mention")
        if score.gold_negative(g) and not gap:
            tags.append("missed_negative")
        if g.get("value_complaint"):
            tags.append("missed_value_complaint")
        return tags
    asp = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
    if score.gold_negative(g) and not score.model_negative(m):
        pos = any((score.bucket(asp.get(x)) or 0) > 0 for x in score.ASPECTS)
        tags.append("negative_softened_to_positive" if pos else "missed_negative")
    for name in score.ASPECTS:
        gv = g["aspects"].get(name)
        ok = {gv, *g["aspect_alternatives"].get(name, [])}
        mv = score.bucket(asp.get(name))
        if mv is not None and gv is not None and mv > gv and gv < 0 and mv not in ok:
            tags.append("softened_negative")
        if mv is not None and None in ok and gv is None and not any(x is not None and abs(x - mv) <= 0 for x in ok):
            tags.append("inferred_aspect")
        if name == "food" and score.fnum(asp.get("food")) == 0.3 and 1 not in ok:
            tags.append("default_0.3")
        if mv is not None and gv is not None and mv * gv < 0 and mv not in ok:
            tags.append("wrong_sign")
    if g.get("value_complaint") and not score.model_value_complaint(m):
        tags.append("missed_value_complaint")
    if "is_negated" not in g["uncertain_fields"] and bool(m.get("is_negated")) != bool(g["is_negated"]):
        tags.append("negation_scope")
    return sorted(set(tags))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--out", required=True)
    ap.add_argument("--gold", default=os.path.join(HERE, "gold.jsonl"))
    ap.add_argument("--items", default=os.path.join(HERE, "items.jsonl"))
    args = ap.parse_args()
    gold = score.load_jsonl(args.gold)
    items = {it["item_id"]: it for it in score.load_jsonl(args.items)}
    alias, excluded = score.load_map("alias_overrides.json"), score.load_map("excluded_entities.json")
    reps, covered, _, mode = score.load_run(args.run, list(items.values()))
    preds = reps[0]
    out, counts = [], collections.Counter()
    for gl in gold:
        it = items[gl["item_id"]]
        cid = gl["comment_id"]
        if it["kind"] == "comment":
            body, prod = it["context"]["body"], it["production"]
        else:
            c = next(c for c in it["comments"] if c["comment_id"] == cid)
            body, prod = c["body"], c["production"]
        m_mode = score.PROD_MODE.get(prod.get("prompt_hash")) or "thread" if mode == "stored" else mode
        ms, seen = [], set()
        for m in preds.get(cid, []):
            if not isinstance(m, dict):
                continue
            m = dict(m, _key=score.model_key(m, alias))
            if m["_key"] and m["_key"] not in seen:
                seen.add(m["_key"])
                ms.append(m)
        pairs, fps = score.match(gl["mentions"], ms)
        matched = {id(g): m for g, m, _ in pairs}
        req = [g for g in gl["mentions"] if score.is_required(g)]
        rows = []
        for g in req:
            m = matched.get(id(g))
            tags = propose(g, gl, m, m_mode, len(req))
            dneg = [d["dish"] for d in g["dish_sentiment"] if (d["level"] or 0) <= -1 or d["avoid"]]
            if dneg:
                tags.append("missed_dish_negative")
            if tags:
                rows.append({"gold": g["canonical_key"], "gold_aspects": g["aspects"], "alt": g["aspect_alternatives"],
                             "neg": g["is_negated"], "vc": g["value_complaint"], "dish_neg": dneg,
                             "model": None if m is None else {"raw": m["restaurant_raw"], "aspects": m.get("aspects"),
                                                              "neg": m.get("is_negated")},
                             "tags": tags})
        for m in fps:
            if m["_key"] in excluded:
                continue
            rows.append({"gold": None, "model": {"raw": m["restaurant_raw"], "aspects": m.get("aspects")},
                         "tags": ["false_positive"]})
        if rows:
            for r in rows:
                counts.update(r["tags"])
            out.append({"item_id": gl["item_id"], "comment_id": cid, "mode": m_mode, "body": body[:600],
                        "disagreements": rows})
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print(len(out), "comments with disagreements")
    for k, v in counts.most_common():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
