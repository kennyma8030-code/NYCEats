"""Build the v2 diagnostic set from confirmed original-extraction failures + blind top-ups.

    python eval/v2/build_v2.py

Inputs
  eval/baseline/disagreements.jsonl   every gold-vs-original disagreement (eval/adjudicate.py),
                                      all re-read; gold errors were fixed via labels/adjudication.py
  eval/items.jsonl, eval/gold.jsonl   v1
  eval/v2/topup_items.jsonl           comments mined per weakness (eval/v2/mine_topups.py)
  eval/v2/labels/topup_*.py           their blind labels (same M() schema)
Outputs
  eval/v2/items.jsonl   one comment per item, runnable by run.py, with weaknesses + split
  eval/v2/gold.jsonl    gold lines for those comments
  eval/v2/counts.json   items per weakness and split

v2 is diagnostic only: it leans toward the original model's failures. The headline
comparison stays on v1 (reweighted). No v2 comment may be used as a prompt example.
"""

import collections
import glob
import hashlib
import importlib.util
import json
import os
import sys

V2 = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(V2)
sys.path.insert(0, os.path.join(EVAL, "labels"))

TAXONOMY = ["dropped_nameless_reply", "dropped_in_list", "dropped_named_mention", "dropped_reference_mention",
            "closed_place", "context_gap", "missed_negative", "negative_softened_to_positive", "softened_negative",
            "wrong_sign", "missed_value_complaint", "missed_dish_negative", "negation_scope", "inferred_aspect",
            "default_0.3", "hallucinated_place", "dish_as_place", "wrong_target"]
TOPUP_MIN = 25

# False positives, retagged after re-reading (comment_id, model raw) -> weakness
FP_TAGS = {
    ("t1_oo5dnbd", "the one on 46th and 6th"): "hallucinated_place",
    ("t1_ohc2x6k", "Cart on 61st and 8th ave"): "hallucinated_place",
    ("t1_owwu0q6", "Malaysian jerky place on mott street"): "hallucinated_place",
    ("t1_omzxv6c", "parm"): "wrong_target",
    ("t1_oxfe4z8", "the one on 23rd st"): "hallucinated_place",
    ("t1_oxhp4t5", "the one in Williamsburg"): "hallucinated_place",
    ("t1_p68y8e7", "the site"): "hallucinated_place",
    ("t1_o2548ih", "factor foods"): "hallucinated_place",
}


def h(x):
    return hashlib.md5(("nyceats-v2" + x).encode()).hexdigest()


def load_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def weaknesses_of(row, gold_line):
    """Final weakness tags for one disagreement row (already re-read)."""
    closed = {m["canonical_key"] for m in gold_line["mentions"] if m["closed"]}
    tags = set()
    for d in row["disagreements"]:
        t = set(d["tags"])
        if d.get("gold") in closed and d.get("model"):
            t -= {"inferred_aspect", "default_0.3"}
            t.add("closed_place")
        if "false_positive" in t:
            t.discard("false_positive")
            raw = d["model"]["raw"]
            tag = FP_TAGS.get((row["comment_id"], raw))
            if tag is None:
                tag = "dish_as_place" if raw.lower().startswith(("their ", "great ")) or any(
                    raw.lower() == x for x in ("gorgonzola pear", "bodega bacon egg & cheese")) else "hallucinated_place"
            t.add(tag)
        tags |= t
    return sorted(tags & set(TAXONOMY))


def comment_item(v1_item, cid):
    """A v2 item (kind=comment) for one comment of a v1 item, runnable by run.py."""
    if v1_item["kind"] == "comment":
        it = dict(v1_item)
        it.pop("risk_groups", None)
        return it
    c = next(x for x in v1_item["comments"] if x["comment_id"] == cid)
    ch = v1_item["thread_chunks"][c["chunk_index"]]
    return {
        "kind": "comment", "modes": ["comment", "thread"], "comment_id": cid, "thread_id": v1_item["thread_id"],
        "production": c["production"],
        "inputs": {"comment": {"user_message": c["comment_input"]},
                   "thread": {"chunk_index": c["chunk_index"], "n_chunks": len(v1_item["thread_chunks"]),
                              "short_id": c["short_id"], "short_ids": ch["short_ids"], "user_message": ch["user_message"]}},
        "context": {"thread_id": v1_item["thread_id"], "permalink": c["permalink"],
                    "thread_title": v1_item["context"]["thread_title"],
                    "thread_selftext": v1_item["context"]["thread_selftext"],
                    "depth": c["depth"], "author": c["author"], "body": c["body"], "ancestors": [], "replies": [],
                    "from_v1_thread_item": v1_item["item_id"]},
    }


def main():
    v1_items = {it["item_id"]: it for it in load_jsonl(os.path.join(EVAL, "items.jsonl"))}
    v1_gold = {(g["item_id"], g["comment_id"]): g for g in load_jsonl(os.path.join(EVAL, "gold.jsonl"))}
    rows = load_jsonl(os.path.join(EVAL, "baseline", "disagreements.jsonl"))

    items, gold = [], []
    for r in rows:
        g = v1_gold[(r["item_id"], r["comment_id"])]
        w = weaknesses_of(r, g)
        if not w:
            continue
        it = comment_item(v1_items[r["item_id"]], r["comment_id"])
        it.update({"source": "v1_failure", "v1_item_id": r["item_id"], "weaknesses": w})
        items.append(it)
        gold.append(g)

    # blind top-ups for thin weaknesses
    topup_path = os.path.join(V2, "topup_items.jsonl")
    topups = {it["comment_id"]: it for it in load_jsonl(topup_path)} if os.path.exists(topup_path) else {}
    for path in sorted(glob.glob(os.path.join(V2, "labels", "topup_*.py"))):
        spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for cid, (ms, note) in mod.L.items():
            keys = [m["canonical_key"] for m in ms]
            assert len(keys) == len(set(keys)), f"duplicate canonical key in {cid}: {keys}"
            it = dict(topups[cid])
            it.update({"source": "topup", "weaknesses": [it["mined_for"]]})
            items.append(it)
            gold.append({"item_id": None, "comment_id": cid, "thread_id": it["thread_id"], "label_version": 2,
                         "labeler": "claude-opus-5.5 (manual, blind)", "labeled_at": "2026-10-04",
                         "batch": os.path.basename(path)[:-3], "adjudicated": False,
                         "has_mention": any(not m["ambiguous"] and not m["out_of_scope"] for m in ms),
                         "mentions": ms, "note": note})

    # Did the ORIGINAL extraction actually fail these comments? (eval/adjudicate.py run over v2;
    # written after the first build, so this is filled in on the second build)
    dis_path = os.path.join(EVAL, "baseline", "disagreements_v2.jsonl")
    if os.path.exists(dis_path):
        dis = {r["comment_id"]: r for r in load_jsonl(dis_path)}
        for it, g in zip(items, gold):
            row = dis.get(it["comment_id"])
            tags = weaknesses_of(row, g) if row else []
            it["original_failures"] = tags
            it["confirmed"] = any(w in tags for w in it["weaknesses"])

    # ids + stratified dev/test split (by first weakness, md5 order, alternate)
    by_w = collections.defaultdict(list)
    for i, it in enumerate(items):
        by_w[it["weaknesses"][0]].append(i)
    split = {}
    for w, idx in by_w.items():
        for k, i in enumerate(sorted(idx, key=lambda i: h(items[i]["comment_id"]))):
            split[i] = "dev" if k % 2 == 0 else "test"
    for n, (it, g) in enumerate(zip(items, gold), start=1):
        it["item_id"] = f"v{n:04d}"
        it["split"] = split[n - 1]
        g["item_id"] = it["item_id"]

    with open(os.path.join(V2, "items.jsonl"), "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    with open(os.path.join(V2, "gold.jsonl"), "w", encoding="utf-8") as f:
        for g in gold:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    counts = {w: {"total": 0, "v1_failure": 0, "topup": 0, "dev": 0, "test": 0, "topup_confirmed": 0} for w in TAXONOMY}
    for it in items:
        for w in it["weaknesses"]:
            c = counts[w]
            c["total"] += 1
            c[it["source"]] += 1
            c[it["split"]] += 1
            if it["source"] == "topup" and it.get("confirmed"):
                c["topup_confirmed"] += 1
    summary = {"items": len(items), "dev": sum(1 for i in items if i["split"] == "dev"),
               "test": sum(1 for i in items if i["split"] == "test"), "per_weakness": counts,
               "below_min": [w for w, c in counts.items() if c["total"] < TOPUP_MIN]}
    with open(os.path.join(V2, "counts.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != "per_weakness"}))
    for w, c in counts.items():
        print(f"  {w:32s} {c}")


if __name__ == "__main__":
    main()
