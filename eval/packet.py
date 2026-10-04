"""Print a BLIND labeling packet: no risk groups, no stored or model output.

    python eval/packet.py c0051 c0060      # single-comment items in that id range
    python eval/packet.py t001             # one whole thread

Single items show the title, full body, the full ancestor chain (marking which
ancestors are inside the thread-mode chunk the model sees), the comment and
its replies. Thread items show the whole rendered tree with each comment's
chunk, so resolvability per mode can be judged.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def show_comment(it):
    c = it["context"]
    t = it["inputs"]["thread"]
    in_chunk = set(t["short_ids"].values())
    print("=" * 100)
    print(f"{it['item_id']}  {it['comment_id']}  depth={c['depth']}  "
          f"thread_comments={c['thread_eligible_comments']}  "
          f"chunk={t['chunk_index'] + 1}/{t['n_chunks']} short_id={t['short_id']}")
    print("TITLE:", c["thread_title"])
    st = (c["thread_selftext"] or "").strip()
    if st:
        print("SELFTEXT:", st[:1500] + (" [...]" if len(st) > 1500 else ""), f"(len {len(st)}; "
              f"comment mode sees the first 400)")
    for a in c["ancestors"]:
        if a.get("missing"):
            print("  [ancestor missing]")
            continue
        tag = "IN-CHUNK" if a["id"] in in_chunk else "not-in-chunk"
        print(f"  {'  ' * a['depth']}^ d{a['depth']} u/{a['author']} ({tag}): {a['body'][:1200]}")
    print(f"  {'  ' * c['depth']}>>> COMMENT u/{c['author']}: {c['body']}")
    for r in c["replies"][:6]:
        print(f"  {'  ' * r['depth']}v reply u/{r['author']}: {r['body'][:400]}")
    if len(c["replies"]) > 6:
        print(f"  ... {len(c['replies']) - 6} more replies")


def show_thread(it):
    c = it["context"]
    print("=" * 100)
    print(f"{it['item_id']}  {it['thread_id']}  {len(it['comments'])} comments, "
          f"{len(it['thread_chunks'])} chunk(s)")
    print("TITLE:", c["thread_title"])
    if (c["thread_selftext"] or "").strip():
        print("SELFTEXT:", c["thread_selftext"].strip())
    for x in it["comments"]:
        print(f"  {'  ' * x['depth']}[{x['comment_id']} chunk {x['chunk_index'] + 1} #{x['short_id']}] "
              f"u/{x['author']}: {x['body']}")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--file":
        # v2 top-ups: python eval/packet.py --file eval/v2/topup_items.jsonl START END (0-based index range)
        with open(args[1], encoding="utf-8") as f:
            items = [json.loads(l) for l in f]
        for n, it in enumerate(items[int(args[2]):int(args[3])], start=int(args[2])):
            it = {k: v for k, v in it.items() if k not in ("mined_for", "production")}  # stay blind
            it["item_id"] = f"u{n:04d}"
            show_comment(it)
        return
    with open(os.path.join(HERE, "items.jsonl"), encoding="utf-8") as f:
        items = [json.loads(l) for l in f]
    lo, hi = args[0], args[-1]
    for it in items:
        if lo <= it["item_id"] <= hi and it["item_id"][0] == lo[0]:
            (show_comment if it["kind"] == "comment" else show_thread)(it)


if __name__ == "__main__":
    main()
