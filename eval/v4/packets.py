"""Write the two labeling packets for every item. No database, no model.

    python eval/v4/packets.py                 # round 1: eval/v4/items.jsonl -> eval/v4/packets.jsonl
    python eval/v4/packets.py --dir eval/v4/round2
    python eval/v4/packets.py --renderer production   # the pre-v6 same_input packets

same_input     exactly the user message the candidate model gets for this unit.
               With --renderer v6 (the default, matching the v6 prompts):
               a single item is production's comment-mode message, which
               v6_comment.py keeps unchanged, and a thread item is the chunk
               as v6_thread.render_chunk draws it from the committed
               items_thread.thread_rows.jsonl (depth-first, explicit parent
               markers, quoted outside parents). The renderer renumbers the
               comments, so the packet carries its own same_input_short_ids.
               Both are checked against the user messages eval/run.py builds
               for the v6 prompts, so the labels see exactly what a run sends.
               With --renderer production, a thread item is production's
               stored chunk (time-ordered, indentation only), byte for byte
               the string in items.jsonl.
full_context   the same unit with everything a careful reader would use: the
               full title and body, the whole ancestor chain and the replies
               for a single comment; the whole thread in reply order for a
               chunk (or, past 150 comments, the chunk's comments with all
               their ancestors and direct replies). Nothing is truncated.
               Bracket numbers are production's (short_ids). Under v6 the
               same_input pass numbers the chunk its own way, so each pass's
               key maps its own numbers back to comment ids.

Packets carry no strata, tags, weights, item ids or production output. The
labeling batches (batches.py) add opaque packet ids on top.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
import prompt_modules as PM  # noqa: E402


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


def chunk_key(it):
    return f"thread:{it['thread_id']}:{it['thread_chunks'][0]['chunk_index']}"


def v6_same_input(it, rows, pt):
    """A thread item's chunk as v6 draws it, with the bracket numbers v6
    gives it. rows is the item's sidecar record; it must hold the same
    comments as production's chunk, or the two passes would label different
    comments."""
    rec = rows.get(chunk_key(it))
    if rec is None or rec["short_ids"] != it["thread_chunks"][0]["short_ids"]:
        raise SystemExit(f"{it['item_id']}: no matching raw rows for {chunk_key(it)}")
    text, id_map = pt.render_chunk(rec["title"], rec["selftext"], rec["rows"], rec["outside"])
    return text, {str(n): cid for n, cid in id_map.items()}


def packets_for(it, renderer="production", rows=None, pt=None):
    """Both packets for one item. same_input_renderer names how same_input
    was drawn, so batches.py can record it in the key and labels.py can refuse
    labels made against another rendering."""
    if it["kind"] == "comment":
        return {"item_id": it["item_id"], "mode": "comment", "same_input_renderer": renderer,
                "same_input": it["inputs"]["comment"]["user_message"],
                "full_context": full_context_single(it)}
    p = {"item_id": it["item_id"], "mode": "thread", "same_input_renderer": renderer,
         "short_ids": it["thread_chunks"][0]["short_ids"],
         "same_input": it["thread_chunks"][0]["user_message"],
         "full_context": full_context_thread(it)}
    if renderer == "v6":
        p["same_input"], p["same_input_short_ids"] = v6_same_input(it, rows, pt)
    return p


def check_against_run(d, packets):
    """Every same_input packet must equal the user message eval/run.py builds
    for the v6 prompts from the split item files, with the same id map. That
    is what a candidate model run sends, so labels and runs see one input."""
    sys.path.insert(0, EVAL)
    import run  # noqa: E402  (no API is touched: build_jobs only renders)
    by_item = {p["item_id"]: p for p in packets}
    n = 0
    for mode, items_file in (("comment", "items_single.jsonl"), ("thread", "items_thread.jsonl")):
        path = os.path.join(d, items_file)
        pmod = PM.load("v6_" + mode)
        rows = None
        if mode == "thread":
            with open(os.path.splitext(path)[0] + ".thread_rows.jsonl", encoding="utf-8") as f:
                rows = {r["call_key"]: r for r in map(json.loads, f)}
        jobs = run.build_jobs(run.load_items(path), mode, pmod, custom=True, thread_rows=rows)
        for j in jobs:
            for iid in j["item_ids"]:
                p = by_item[iid]
                if p["same_input"] != j["user"]:
                    raise SystemExit(f"{iid}: same_input differs from run.py's {mode}-mode message")
                if mode == "thread" and p["same_input_short_ids"] != {str(k): v for k, v in j["id_map"].items()}:
                    raise SystemExit(f"{iid}: bracket numbers differ from run.py's id map")
                n += 1
    if n != len(packets):
        raise SystemExit(f"run.py renders {n} of {len(packets)} packets")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=HERE)
    ap.add_argument("--renderer", choices=("v6", "production"), default="v6",
                    help="how a thread item's same_input chunk is drawn (single items are the same either way)")
    args = ap.parse_args()
    with open(os.path.join(args.dir, "items.jsonl"), encoding="utf-8") as f:
        items = [json.loads(l) for l in f]
    rows = pt = None
    if args.renderer == "v6":
        pt = PM.load("v6_thread")
        side = os.path.join(args.dir, "items_thread.thread_rows.jsonl")
        if not os.path.exists(side):
            raise SystemExit(f"{side} is missing: v6 draws chunks from raw rows. next_round.py writes it "
                             "for a new round; for an older one run eval/build_thread_rows.py (read-only) "
                             "on items_single.jsonl and items_thread.jsonl")
        with open(side, encoding="utf-8") as f:
            rows = {r["call_key"]: r for r in map(json.loads, f)}
    packets = [packets_for(it, args.renderer, rows, pt) for it in items]
    if args.renderer == "v6":
        print(f"{check_against_run(args.dir, packets)} same_input packets identical to eval/run.py's v6 inputs")
    path = os.path.join(args.dir, "packets.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for p in packets:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"{len(items)} items -> {path} (same_input renderer: {args.renderer})")


if __name__ == "__main__":
    main()
