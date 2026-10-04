"""Re-derive mentions from the raw output already stored in run files. No API calls.

Run files written before run.py learned to strip a ```json fence recorded those
calls as unparsed. Their raw text is kept, so this recomputes json_ok,
json_ok_strict and mentions_by_comment in place for every record that lacks
json_ok_strict (i.e. was written by the old parser).

    python eval/reparse.py eval/runs/*.jsonl
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def id_maps(mode):
    items = run.load_items(os.path.join(HERE, "items.jsonl"))
    return {j["call_key"]: j["id_map"] for j in run.build_jobs(items, mode, None)}


def mentions_by_comment(mentions, mode, id_map):
    out, bad = {}, 0
    for m in mentions or []:
        if not isinstance(m, dict):
            continue
        key = None
        if mode == "thread":
            try:
                key = int(m.get("id"))
            except (TypeError, ValueError):
                key = -1
        cid = id_map.get(key)
        if cid is None:
            bad += 1
            continue
        out.setdefault(cid, []).append(m)
    return out, bad


def main(paths):
    maps = {}
    for path in paths:
        recs = [json.loads(l) for l in open(path, encoding="utf-8")]
        fixed = 0
        for r in recs:
            if "json_ok_strict" in r or r.get("raw") is None:
                continue
            mode = r["mode"]
            if mode not in maps:
                maps[mode] = id_maps(mode)
            ok, mentions = run.parse(r["raw"])
            strict = ok and run.unfence(r["raw"]) == r["raw"].strip()
            r["json_ok"], r["json_ok_strict"] = ok, strict
            r["mentions_by_comment"], r["bad_ids"] = mentions_by_comment(
                mentions, mode, maps[mode].get(r["call_key"], {}))
            fixed += 1
        with open(path, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        print(f"{os.path.basename(path)}: {fixed} records re-parsed")


if __name__ == "__main__":
    main(sys.argv[1:])
