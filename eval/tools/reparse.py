"""Re-derive mentions from the raw output already stored in run files. No API calls.

Run files written before run.py learned to strip a ```json fence recorded those
calls as unparsed. Their raw text is kept, so this recomputes json_ok,
json_ok_strict and mentions_by_comment in place for every record that lacks
json_ok_strict (i.e. was written by the old parser).

    python eval/tools/reparse.py eval/runs/*.jsonl
    python eval/tools/reparse.py --items eval/v4/items_single.jsonl eval/runs/*__v4.jsonl

The comment ids in a call are only known from the items file the run was made
on, so each run needs its own. Without --items it is taken from the run file's
tag: no tag is v1 and `__v2` is v2. Any other tag needs --items. A record whose
call is not in that items file is left exactly as it was, never rewritten
with empty mentions.
"""

import argparse
import json
import os
import sys

EVAL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EVAL)
import _paths  # noqa: E402,F401  (adds eval/lib)
import run  # noqa: E402

SETS = {"": "v1", "v2": "v2"}


def items_for(path):
    """The items file a run was made on, from its `<model>__<hash>__<mode>[__<tag>]` name."""
    parts = os.path.basename(path).removesuffix(".jsonl").split("__")
    tag = parts[3] if len(parts) > 3 else ""
    if tag not in SETS:
        sys.exit(f"{path}: cannot tell which items file tag {tag!r} belongs to; pass --items")
    return os.path.join(EVAL, SETS[tag], "items.jsonl")


def id_maps(items_path, mode):
    items = run.load_items(items_path)
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


def main(paths, items_path=None):
    for path in paths:
        recs = [json.loads(l) for l in open(path, encoding="utf-8")]
        todo = [r for r in recs if "json_ok_strict" not in r and r.get("raw") is not None]
        if not todo:
            print(f"{os.path.basename(path)}: 0 records re-parsed")
            continue
        src = items_path or items_for(path)
        maps = {}
        fixed = skipped = 0
        for r in todo:
            mode = r["mode"]
            if mode not in maps:
                maps[mode] = id_maps(src, mode)
            if r["call_key"] not in maps[mode]:
                skipped += 1
                continue
            ok, mentions = run.parse(r["raw"])
            strict = ok and run.unfence(r["raw"]) == r["raw"].strip()
            r["json_ok"], r["json_ok_strict"] = ok, strict
            r["mentions_by_comment"], r["bad_ids"] = mentions_by_comment(
                mentions, mode, maps[mode][r["call_key"]])
            fixed += 1
        if fixed:
            with open(path, "w", encoding="utf-8") as f:
                for r in recs:
                    f.write(json.dumps(r) + "\n")
        note = f", {skipped} left alone: call not in {os.path.relpath(src, EVAL)}" if skipped else ""
        print(f"{os.path.basename(path)}: {fixed} records re-parsed{note}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--items", help="the items file these runs were made on (default: from each run's tag)")
    a = ap.parse_args()
    main(a.runs, a.items)
