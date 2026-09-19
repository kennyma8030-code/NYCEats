"""Poll r/FoodNYC comments every 30 minutes.

When a comment arrives on a thread we've never seen, backfill that whole
thread (the post plus every comment in it) before storing the comment.
"""

import argparse
import time
import traceback

import arctic
import db
import ingest
import restaurants

SUBREDDIT = "FoodNYC"
INTERVAL = 30 * 60


def pull_threads(conn, bare_ids):
    """Download every comment of each newly discovered thread."""
    for pid in sorted(bare_ids):
        comments = arctic.all_thread_comments(pid)
        n = db.insert_comments(conn, comments)
        print(f"  backfilled t3_{pid}: {len(comments)} comments ({n} new)")
        time.sleep(1)


def poll_once(conn):
    comments = arctic.newest_comments(SUBREDDIT)
    print(f"fetched {len(comments)} newest comments")
    if not comments:
        return

    storable, got, discovered = ingest.ensure_threads(conn, comments)
    if got:
        print(f"  {got} unknown thread(s), backfilling")
        pull_threads(conn, discovered)
    if len(storable) < len(comments):
        print(f"  skipping {len(comments) - len(storable)} comment(s) with no post")

    new = db.insert_comments(conn, storable)
    db.fill_tree(conn, {c["link_id"] for c in storable})
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
    ap.add_argument("--backfill-years", type=float, default=0,
                    help="run the backfill first, then poll (resumable, safe to repeat)")
    args = ap.parse_args()

    conn = db.connect()
    # schema.sql is all "create ... if not exists", so this is safe every boot
    # and means a fresh Railway deploy needs no manual setup step.
    db.init(conn)

    # First boot on a fresh database: pull the NYC restaurant list. No-op after.
    n = restaurants.ensure_loaded(conn)
    if n:
        print(f"loaded {n:,} NYC restaurants")

    if args.backfill_years:
        import backfill
        # Resumable and idempotent: a restart mid-run picks up at its cursor,
        # and a completed backfill costs one empty page on the next boot.
        backfill.run(conn, args.backfill_years)

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
