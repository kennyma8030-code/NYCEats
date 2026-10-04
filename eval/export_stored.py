"""Export the production extraction for every eval comment as a run file.

    EVAL_DB_URL=postgresql://... python eval/export_stored.py

Writes eval/baseline/production__stored__all.jsonl in run.py's format (one line
per comment, rep 0), so score.py can grade the original model exactly like a
fresh run. Read-only connection. Do NOT run this until labeling is finished
for the items you will score -- looking at stored output biases labels.

Stored rows already went through production post-processing: chains were
dropped (chains.txt) and names normalised. Score with --drop-chains so fresh
runs get the same treatment when comparing against this file.
"""

import json
import os

import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    url = os.environ.get("EVAL_DB_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("set EVAL_DB_URL or DATABASE_URL")
    conn = psycopg2.connect(url)
    conn.set_session(readonly=True)
    cur = conn.cursor()

    cids = {}
    with open(os.path.join(HERE, "items.jsonl"), encoding="utf-8") as f:
        for line in f:
            it = json.loads(line)
            if it["kind"] == "comment":
                cids.setdefault(it["comment_id"], []).append(it["item_id"])
            else:
                for c in it["comments"]:
                    cids.setdefault(c["comment_id"], []).append(it["item_id"])

    cur.execute("select id, extracted_with from comments where id = any(%s)", (list(cids),))
    ew = dict(cur.fetchall())
    cur.execute("""
        select comment_id, restaurant_raw, entity_key, neighborhood_hint, dishes,
               descriptors, aspects, expensiveness, is_firsthand, is_negated, prompt_hash
        from mentions where comment_id = any(%s) order by id""", (list(cids),))
    by = {}
    for (cid, raw, key, hood, dishes, desc, aspects, exp, first, neg, ph) in cur.fetchall():
        by.setdefault(cid, []).append({
            "restaurant_raw": raw, "entity_key": key, "neighborhood_hint": hood,
            "dishes": dishes or [], "descriptors": desc or [], "aspects": aspects or {},
            "expensiveness": exp, "is_firsthand": first, "is_negated": neg, "prompt_hash": ph})

    out_dir = os.environ.get("EVAL_BASELINE_DIR", os.path.join(HERE, "baseline"))
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "production__stored__all.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for cid, item_ids in cids.items():
            model, _, ph = (ew.get(cid) or "").rpartition(":")
            f.write(json.dumps({
                "call_key": f"stored:{cid}", "rep": 0, "item_ids": item_ids,
                "model": model or None, "prompt_hash": ph or None, "mode": "stored",
                "json_ok": ew.get(cid) is not None, "error": None if ew.get(cid) else "not extracted",
                "mentions_by_comment": {cid: by.get(cid, [])},
            }, ensure_ascii=False) + "\n")
    print(f"{len(cids)} comments -> {out}")


if __name__ == "__main__":
    main()
