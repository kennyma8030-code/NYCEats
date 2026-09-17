"""Poll r/FoodNYC comments every 30 minutes.

When a comment arrives on a thread we've never seen, backfill that whole
thread (the post plus every comment in it) before storing the comment.
"""

import argparse
import time
import traceback

import arctic
import db

SUBREDDIT = "FoodNYC"
INTERVAL = 30 * 60


def backfill_thread(conn, bare_ids):
    """Fetch posts + all their comments. Returns thread ids touched."""
    posts = arctic.posts_by_id(bare_ids)
    found = {p["id"] for p in posts}
    if missing := set(bare_ids) - found:
        # Deleted or otherwise unavailable upstream; we can't satisfy the FK.
        print(f"  ! {len(missing)} post(s) not in archive, skipping: {sorted(missing)}")

    db.insert_threads(conn, posts)

    touched = set()
    for p in posts:
        comments = arctic.all_thread_comments(p["id"])
        n = db.insert_comments(conn, comments)
        touched.add("t3_" + p["id"])
        print(f"  backfilled t3_{p['id']}: {len(comments)} comments ({n} new) "
              f"- {p.get('title', '')[:50]}")
        time.sleep(1)
    return touched, found


def poll_once(conn):
    comments = arctic.newest_comments(SUBREDDIT)
    print(f"fetched {len(comments)} newest comments")
    if not comments:
        return

    wanted = {c["link_id"] for c in comments}
    have = db.existing_thread_ids(conn, wanted)
    missing = wanted - have

    touched = set(wanted)
    usable = have
    if missing:
        print(f"  {len(missing)} unknown thread(s), backfilling")
        _, found = backfill_thread(conn, {m[3:] for m in missing})
        usable = have | {"t3_" + f for f in found}

    # Drop comments whose post couldn't be fetched, or the FK rejects the batch.
    storable = [c for c in comments if c["link_id"] in usable]
    if len(storable) < len(comments):
        print(f"  skipping {len(comments) - len(storable)} comment(s) with no post")

    new = db.insert_comments(conn, storable)
    db.fill_tree(conn, touched & usable)
    print(f"  inserted {new} new comment(s)")


def settle_once(conn, batches=5):
    """Finalise scores for comments past 36h. ~6 requests/day at this volume."""
    total = 0
    for _ in range(batches):
        ids = db.unsettled_comment_ids(conn, limit=100)
        if not ids:
            break
        fetched = arctic.comments_by_id([i[3:] for i in ids])
        returned = {"t1_" + c["id"] for c in fetched}
        db.settle_scores(conn, fetched, missing_ids=set(ids) - returned)
        total += len(fetched)
        time.sleep(1)
    if total:
        print(f"  settled scores for {total} comment(s)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="run one cycle and exit")
    ap.add_argument("--init", action="store_true", help="create tables first")
    args = ap.parse_args()

    conn = db.connect()
    if args.init:
        db.init(conn)
        print("schema applied")

    while True:
        started = time.time()
        try:
            poll_once(conn)
            settle_once(conn)
        except Exception:
            traceback.print_exc()
            conn.rollback()

        if args.once:
            break
        sleep = max(0, INTERVAL - (time.time() - started))
        print(f"sleeping {sleep / 60:.1f} min\n")
        time.sleep(sleep)


if __name__ == "__main__":
    main()
