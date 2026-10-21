"""Thread-mode jobs for eval/run.py, from a slice file, with production's chunker and renderer.

Imported, not copied: thread_chunks.py (what goes in a chunk) and
prompt_v6 (the thread prompt, its hash, its schema and render_chunk), so the
head-to-head runs exactly what extract_v6.py --mode thread would send, without
touching the database (each production comment can only hold one v6 state
row, so a comparison has to run here).

Offline everything is due: every comment that is not [deleted]/[removed]/
blank, and the post, which is item [0] of each thread's first chunk unless
post_item is False. Only chunks that hold a graded item are sent: in a slice
with targets, the chunk(s) holding a target (and, when the slice grades the
post, the first chunk); in a whole-thread slice, every chunk.
"""

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import prompt_v6  # noqa: E402
import thread_chunks as T  # noqa: E402

SYSTEM_PROMPT = prompt_v6.SYSTEM_PROMPT_THREAD
SCHEMA = prompt_v6.SCHEMA_THREAD
PROMPT_HASH = prompt_v6.PROMPT_HASH_THREAD
POST_CHARS = prompt_v6.thread.POST_ITEM_CHARS


def load_slice(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def thread_chunks(th, soft_comments=T.SOFT_COMMENTS, soft_tokens=T.SOFT_TOKENS, max_comments=T.MAX_COMMENTS,
                  post_item=True):
    """(tree, chunks) for one slice thread, everything due."""
    comments = th["comments"]
    due = {c["comment_id"] for c in comments if not T.is_gone(c.get("body"))}
    ptoks = T.text_tokens(f"{th.get('title') or ''} {th.get('selftext') or ''}", POST_CHARS) if post_item else 0.0
    return T.Tree(comments), T.chunk_thread(th["thread_id"], comments, due, post_item, ptoks, soft_comments,
                                            soft_tokens, max_comments)


def jobs(path, soft_comments=T.SOFT_COMMENTS, soft_tokens=T.SOFT_TOKENS, max_comments=T.MAX_COMMENTS,
         post_item=True, all_chunks=False):
    """run.py jobs for a slice: {call_key, item_ids, user, id_map, rendered, strict_ids, chunk, covers}.

    item_ids are the graded items in the chunk (run.py's records carry them);
    covers is every item it numbered. call_key names the thread and a digest
    of the chunk's content, so a run with other chunk sizes never resumes from
    this one's records."""
    out = []
    for th in load_slice(path):
        tid = th["thread_id"]
        tree, chunks = thread_chunks(th, soft_comments, soft_tokens, max_comments, post_item)
        targets = None if th.get("targets") is None else set(th["targets"])
        graded_post = bool(th.get("post_target")) and post_item
        for n, ch in enumerate(chunks):
            comments = ch.members
            # A chunk is sent for its targets; the post, where it is item [0]
            # of a chunk that is sent anyway, is graded too, never sent for.
            mine = comments if targets is None else [c for c in comments if c in targets]
            if not mine and not all_chunks and not (targets is None and ch.post_item and graded_post):
                continue
            graded = ([tid] if graded_post and ch.post_item else []) + mine
            user, ids, ctx = T.render(ch, th.get("title"), th.get("selftext"), th["comments"], tree)
            members = [ids[k] for k in sorted(ids)]
            digest = hashlib.sha1(json.dumps([members, ctx, ch.post_item]).encode()).hexdigest()[:12]
            out.append({"call_key": f"chunk:{tid}:{digest}", "item_ids": graded, "user": user, "id_map": ids,
                        "rendered": True, "strict_ids": True, "covers": members,
                        "chunk": {"thread_id": tid, "index": n, "of": len(chunks), "post_item": ch.post_item,
                                  "members": members, "context_ids": ctx}})
    return out
