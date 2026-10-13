"""Check that v4's model inputs are byte-for-byte what production sends.
Read-only: it calls production's own SELECT functions on a read-only
connection and never calls a model.

    EVAL_DB_URL=postgresql://... python eval/v4/verify_inputs.py [--show 2]

Three checks:

1. comment mode, live queue: extract.next_batch() returns the next 200
   comments production would extract; extract.fetch_one builds each message
   with prompt.build_user_message. render.comment_inputs must produce the
   same strings for the same ids.
2. comment mode, v4 items: every single item's stored message must equal a
   fresh render (the corpus has not drifted since the build).
3. thread mode: for every v4 thread item whose thread has nothing extracted
   and nothing posted after the cutoff, extract_threads.thread_rows() (the
   production function, whose pending filter is then a no-op) is chunked and
   numbered the way fetch_chunk does it, and the item's chunk must match.
   The same is done for the biggest pending threads in production's queue.

It also reports how many v1 overlap items now render differently from what
v1 stored, which is drift in the database (edits, deletions, late parents).
"""

import difflib
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import corpus  # noqa: E402
import render  # noqa: E402
import extract  # noqa: E402
import extract_threads  # noqa: E402
import prompt  # noqa: E402
import prompt_thread  # noqa: E402


def prod_chunks(conn, tid):
    """Exactly extract_threads.run + fetch_chunk's rendering, minus the API call."""
    head, rows = extract_threads.thread_rows(conn, tid)
    out = []
    for chunk in extract_threads.chunks(rows):
        nodes = [(i, depth, author, body) for i, (cid, depth, author, body) in enumerate(chunk, start=1)]
        out.append(prompt_thread.build_message(head[0], head[1], nodes))
    return out


def diff(a, b, label):
    return "\n".join(difflib.unified_diff(a.splitlines(), b.splitlines(), "production", label, lineterm=""))


def main():
    show = int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 0
    conn = corpus.connect()
    cur = conn.cursor()
    report = {}

    # 1. live comment-mode queue
    rows = extract.next_batch(conn, 200)
    prod = {r[0]: prompt.build_user_message(r[1], r[2], r[3], r[4]) for r in rows}
    ours = render.comment_inputs(cur, list(prod))
    bad = [cid for cid in prod if prod[cid] != ours.get(cid)]
    report["comment_queue"] = {"checked": len(prod), "identical": len(prod) - len(bad), "differ": bad}
    for cid in bad[:3]:
        print(diff(prod[cid], ours.get(cid, ""), "v4"))
    for cid in list(prod)[:show]:
        print(f"--- comment mode, production queue {cid} (identical: {cid not in bad})\n{prod[cid][:700]}\n")

    # 2. v4 single items
    with open(os.path.join(HERE, "items.jsonl"), encoding="utf-8") as f:
        items = [json.loads(l) for l in f]
    singles = [it for it in items if it["kind"] == "comment"]
    fresh = render.comment_inputs(cur, [it["comment_id"] for it in singles])
    bad = [it["item_id"] for it in singles if it["inputs"]["comment"]["user_message"] != fresh[it["comment_id"]]]
    report["comment_items"] = {"checked": len(singles), "identical": len(singles) - len(bad), "differ": bad}

    # 3. thread mode: v4 thread items that production's pending query renders whole
    def clean(tid):
        cur.execute("""select count(*) filter (where extracted_at is not null or extract_error is not null),
                              count(*) filter (where created_utc >= %s)
                       from comments where thread_id = %s
                         and body not in ('[deleted]', '[removed]') and length(body) > 15""",
                    (corpus.CUTOFF, tid))
        done, late = cur.fetchone()
        return done == 0 and late == 0
    checked, bad, skipped = 0, [], []
    for it in items:
        if it["kind"] != "thread":
            continue
        if not clean(it["thread_id"]):
            skipped.append(it["item_id"])
            continue
        pc = prod_chunks(conn, it["thread_id"])
        mine = it["thread_chunks"][0]
        checked += 1
        if pc[mine["chunk_index"]] != mine["user_message"]:
            bad.append(it["item_id"])
            print(diff(pc[mine["chunk_index"]], mine["user_message"], it["item_id"]))
        elif show:
            print(f"--- thread mode {it['item_id']} chunk {mine['chunk_index']} identical\n{mine['user_message'][:900]}\n")
    report["thread_items"] = {"checked": checked, "identical": checked - len(bad), "differ": bad,
                              "not_checkable_partly_extracted_or_late_comments": skipped}

    # 3b. the biggest threads in production's own pending queue
    checked, bad = 0, []
    for tid, _ in extract_threads.pending_threads(conn, limit=40):
        if not clean(tid):
            continue
        pc = prod_chunks(conn, tid)
        _, ours = render.thread_chunks(cur, tid)
        checked += 1
        if [c["user_message"] for c in ours] != pc:
            bad.append(tid)
        if checked >= 5:
            break
    report["thread_queue"] = {"threads_checked": checked, "identical": checked - len(bad), "differ": bad}

    # v1 overlap drift
    with open(os.path.join(corpus.EVAL, "items.jsonl"), encoding="utf-8") as f:
        v1 = {json.loads(l)["item_id"]: json.loads(l) for l in f}
    drift = [it["item_id"] for it in singles if it.get("v1_item_id")
             and v1[it["v1_item_id"]]["inputs"]["comment"]["user_message"] != it["inputs"]["comment"]["user_message"]]
    report["v1_overlap_input_drift"] = {"overlap_items": sum(1 for it in singles if it.get("v1_item_id")),
                                        "renders_differently_than_v1": drift}
    conn.close()
    print(json.dumps(report, indent=1))
    with open(os.path.join(HERE, "verify_inputs.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
