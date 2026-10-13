"""Write the two labeling packets for every item. No database, no model.

    python eval/v4/packets.py                 # round 1: eval/v4/items.jsonl -> eval/v4/packets.jsonl
    python eval/v4/packets.py --dir eval/v4/round2

same_input     exactly the user message production sends for this unit: the
               comment-mode message for a single item, the chunk for a thread
               item. Byte-for-byte the string in items.jsonl.
full_context   the same unit with everything a careful reader would use: the
               full title and body, the whole ancestor chain and the replies
               for a single comment; the whole thread in reply order for a
               chunk (or, past 150 comments, the chunk's comments with all
               their ancestors and direct replies). Nothing is truncated.
               Bracket numbers match the chunk's, so labels from both passes
               use the same ids.

Packets carry no strata, tags, weights, item ids or production output. The
labeling batches (batches.py) add opaque packet ids on top.
"""

import argparse
import json
import os

HERE = os.path.dirname(os.path.realpath(__file__))


def ind(depth):
    return "  " * max(depth, 0)


def full_context_single(it):
    c = it["context"]
    out = [f"POST TITLE: {(c['thread_title'] or '').strip()}"]
    st = (c["thread_selftext"] or "").strip()
    out.append(f"POST BODY: {st}" if st else "POST BODY: (none)")
    out.append("")
    out.append("CONVERSATION ABOVE THE COMMENT, oldest first:" if c["ancestors"] else
               "The comment is a top-level reply to the post.")
    for a in c["ancestors"]:
        if a.get("missing"):
            out.append("  [the next comment up is missing from the archive]")
            continue
        out.append(f"{ind(a['depth'])}u/{a['author'] or '?'}: {a['body'].strip()}")
    out.append("")
    out.append(f">>> COMMENT TO LABEL (u/{c['author'] or '?'}):")
    out.append(c["body"].strip())
    out.append("")
    if c["replies"]:
        out.append("REPLIES TO IT (context only):")
        for r in c["replies"]:
            out.append(f"  u/{r['author'] or '?'}: {r['body'].strip()}")
    else:
        out.append("REPLIES TO IT: none")
    return "\n".join(out)


def tree_order(rows):
    """Depth-first reply order, children by time: the order a reader sees on
    Reddit. A comment whose parent is absent is treated as a root."""
    ids = {r["id"] for r in rows}
    kids, roots = {}, []
    for r in rows:
        if r["parent"] in ids:
            kids.setdefault(r["parent"], []).append(r)
        else:
            roots.append(r)
    out, stack = [], list(reversed(roots))
    while stack:
        r = stack.pop()
        out.append(r)
        stack.extend(reversed(kids.get(r["id"], [])))
    return out


def full_context_thread(it):
    c = it["context"]
    sid = {x["comment_id"]: x["short_id"] for x in it["comments"]}
    rows = c["rows"]
    out = [f"POST TITLE: {(c['thread_title'] or '').strip()}"]
    st = (c["thread_selftext"] or "").strip()
    out.append(f"POST BODY: {st}" if st else "POST BODY: (none)")
    out.append("")
    out.append("THREAD, in reply order. Label ONLY the comments with a bracket number [n]. "
               "Lines marked (context) are there to read, not to label.")
    for r in tree_order(rows):
        body = (r["body"] or "").strip()
        who = f"u/{r['author'] or '?'}"
        if r["id"] in sid:
            out.append(f"{ind(r['depth'])}[{sid[r['id']]}] {who}: {body}")
        elif body in ("[deleted]", "[removed]") or len(r["body"] or "") <= 15:
            out.append(f"{ind(r['depth'])}(context, deleted or too short to be sent) {who}: {body}")
        else:
            out.append(f"{ind(r['depth'])}(context) {who}: {body}")
    if not c.get("rows_complete", True):
        out.append("")
        out.append(f"(The thread is long: shown are only the numbered comments, their ancestors "
                   f"and their direct replies, {len(rows)} of {c['thread_rows_total']} comments.)")
    return "\n".join(out)


def packets_for(it):
    if it["kind"] == "comment":
        return {"item_id": it["item_id"], "mode": "comment",
                "same_input": it["inputs"]["comment"]["user_message"],
                "full_context": full_context_single(it)}
    return {"item_id": it["item_id"], "mode": "thread",
            "short_ids": it["thread_chunks"][0]["short_ids"],
            "same_input": it["thread_chunks"][0]["user_message"],
            "full_context": full_context_thread(it)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=HERE)
    args = ap.parse_args()
    with open(os.path.join(args.dir, "items.jsonl"), encoding="utf-8") as f:
        items = [json.loads(l) for l in f]
    path = os.path.join(args.dir, "packets.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(packets_for(it), ensure_ascii=False) + "\n")
    print(f"{len(items)} items -> {path}")


if __name__ == "__main__":
    main()
