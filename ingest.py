"""Shared ingestion steps used by both the poller and the backfill."""

import time

import arctic
import db


def ensure_threads(conn, comments, pause=0.5):
    """Make every comment's thread exist before the comments are inserted.

    `comments.thread_id` is a real foreign key, so a comment whose post we
    have never seen would fail the insert and take the whole batch with it.
    Returns (storable_comments, newly_inserted_thread_count, discovered_ids).

    `discovered_ids` are the bare post ids fetched on this call -- the poller
    uses them to decide which threads to pull in full.
    """
    wanted = {c["link_id"] for c in comments}
    missing = db.missing_thread_ids(conn, wanted)
    if not missing:
        return comments, 0, set()

    posts = arctic.posts_by_id({m[3:] for m in missing})
    inserted = db.insert_threads(conn, posts)
    discovered = {p["id"] for p in posts}
    time.sleep(pause)

    # Posts the archive could not return (deleted, or outside its coverage).
    # Their comments can never satisfy the FK, so drop them rather than
    # failing the batch -- the caller reports the count.
    still_missing = db.missing_thread_ids(conn, wanted)
    storable = ([c for c in comments if c["link_id"] not in still_missing]
                if still_missing else comments)
    return storable, inserted, discovered
