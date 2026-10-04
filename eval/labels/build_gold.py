"""Regenerate eval/gold.jsonl from every labels/batchNN.py (each defines L), then
apply the post-adjudication corrections in labels/adjudication.py.

    python eval/labels/build_gold.py

L maps item_id -> (mentions, note) for single comments, and
"<thread item_id>/<comment_id>" -> (mentions, note) for thread comments.
"""

import glob
import importlib.util
import json
import os

import adjudication
from common import EVAL

LABELER = "claude-opus-5.5 (manual, blind)"


def main():
    with open(os.path.join(EVAL, "items.jsonl"), encoding="utf-8") as f:
        items = {json.loads(l)["item_id"]: json.loads(l) for l in f}
    labels, source = {}, {}
    for path in sorted(glob.glob(os.path.join(EVAL, "labels", "batch*.py"))):
        spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for lid, entry in mod.L.items():
            assert lid not in labels, f"duplicate label {lid}"
            labels[lid] = entry
            source[lid] = os.path.basename(path)[:-3]
    patched = {p[0] for p in adjudication.PATCHES}
    n_patch = adjudication.apply(labels)

    out = []
    for lid, (ms, note) in labels.items():
        keys = [m["canonical_key"] for m in ms]
        assert len(keys) == len(set(keys)), f"duplicate canonical key in {lid}: {keys}"
        if "/" in lid:
            iid, cid = lid.split("/")
            it = items[iid]
            assert any(c["comment_id"] == cid for c in it["comments"]), lid
        else:
            iid, it = lid, items[lid]
            cid = it["comment_id"]
        out.append({
            "item_id": iid, "comment_id": cid, "thread_id": it["thread_id"],
            "label_version": 2, "labeler": LABELER, "labeled_at": "2026-10-04",
            "batch": source[lid], "adjudicated": lid in patched,
            "has_mention": any(not m["ambiguous"] and not m["out_of_scope"] for m in ms),
            "mentions": ms, "note": note,
        })
    order = {k: i for i, k in enumerate(items)}
    out.sort(key=lambda g: (order[g["item_id"]], g["comment_id"]))
    with open(os.path.join(EVAL, "gold.jsonl"), "w", encoding="utf-8") as f:
        for g in out:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    n_single = sum(1 for g in out if g["item_id"].startswith("c"))
    print(f"{len(out)} comments ({n_single} single, {len(out) - n_single} thread), "
          f"{sum(len(g['mentions']) for g in out)} mentions, "
          f"{sum(g['has_mention'] for g in out)} with a required mention; {n_patch} adjudication patches")


if __name__ == "__main__":
    main()
