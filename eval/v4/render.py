"""Render the model inputs for sampled comments and chunks, straight from the
database, with production's own SQL and builders. Read-only.

Comment mode copies extract.next_batch's SELECT (restricted to the ids we
want instead of the pending queue) and feeds the row to
prompt.build_user_message, exactly as extract.fetch_one does.

Thread mode copies extract_threads.thread_rows' SELECT and ORDER BY without
the pending filter: it renders the thread as a full re-extraction would see
it, after --reset, when every eligible comment is pending again. Chunks come
from extract_threads.chunks and the nodes are numbered as fetch_chunk numbers
them. Comments created after corpus.CUTOFF are left out, so the rendering is
the thread as of the snapshot.

verify_inputs.py checks these renderings against production's functions
called directly.
"""

import corpus
import extract_threads
import prompt
import prompt_thread

COMMENT_SQL = """
    select c.id, c.body, t.title, t.selftext, p.body
    from comments c
    join threads t on t.id = c.thread_id
    left join comments p on p.id = c.parent_comment_id
    where c.id = any(%s)
"""

THREAD_HEAD_SQL = "select title, selftext from threads where id = %s"

# extract_threads.thread_rows, minus "extracted_at is null and extract_error is
# null", with the snapshot cutoff in place of production's optional `since`.
THREAD_ROWS_SQL = """
    select c.id, coalesce(c.depth, 0), c.author, c.body
    from comments c
    where c.thread_id = %s
      and c.body not in ('[deleted]', '[removed]')
      and length(c.body) > 15
      and c.created_utc < %s
    order by coalesce(c.root_comment_id, c.id), c.created_utc
"""


def comment_inputs(cur, ids):
    """comment_id -> the user message production's comment mode sends."""
    cur.execute(COMMENT_SQL, (list(ids),))
    return {cid: prompt.build_user_message(body, title, selftext, parent)
            for cid, body, title, selftext, parent in cur.fetchall()}


def thread_chunks(cur, thread_id):
    """Every chunk of a thread as production's thread mode would send it.

    Returns (head, [{chunk_index, short_ids, user_message, rows}])."""
    cur.execute(THREAD_HEAD_SQL, (thread_id,))
    head = cur.fetchone()
    cur.execute(THREAD_ROWS_SQL, (thread_id, corpus.CUTOFF))
    rows = cur.fetchall()
    out = []
    for ci, part in enumerate(extract_threads.chunks(rows)):
        nodes, short = [], {}
        for i, (cid, depth, author, body) in enumerate(part, start=1):
            nodes.append((i, depth, author, body))
            short[i] = cid
        out.append({"chunk_index": ci, "short_ids": {str(k): v for k, v in short.items()},
                    "user_message": prompt_thread.build_message(head[0], head[1], nodes),
                    "rows": part})
    return head, out


def thread_context(cur, thread_id):
    """Every comment in the thread (eligible or not, up to the cutoff), for
    the full-context packets. Deleted and too-short comments are kept as
    context: they are part of the conversation even though no mode sends them."""
    cur.execute("""
        select id, parent_comment_id, coalesce(depth, 0), author, body, created_utc, permalink,
               was_deleted_later
        from comments where thread_id = %s and created_utc < %s
        order by created_utc""", (thread_id, corpus.CUTOFF))
    return [{"id": r[0], "parent": r[1], "depth": r[2], "author": r[3], "body": r[4],
             "created_utc": r[5].isoformat(), "permalink": r[6], "was_deleted_later": r[7]}
            for r in cur.fetchall()]


def ancestors_and_replies(rows_by_id, cid):
    """Full ancestor chain (root first, untruncated) and the direct replies."""
    chain, seen = [], set()
    p = rows_by_id[cid]["parent"]
    while p and p not in seen:
        seen.add(p)
        a = rows_by_id.get(p)
        if a is None:
            chain.append({"id": p, "missing": True})
            break
        chain.append({k: a[k] for k in ("id", "depth", "author", "body")})
        p = a["parent"]
    replies = [{k: r[k] for k in ("id", "depth", "author", "body")}
               for r in rows_by_id.values() if r["parent"] == cid]
    return list(reversed(chain)), replies
