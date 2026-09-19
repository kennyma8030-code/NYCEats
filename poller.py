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
import rss

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
    ap.add_argument("--no-rss", action="store_true",
                    help="do not run the RSS fallback collector")
    ap.add_argument("--no-backfill", action="store_true",
                    help="start polling immediately, skipping the catch-up sweep")
    ap.add_argument("--backfill-years", type=float, default=0,
                    help="limit the catch-up sweep to the last N years (default: all time)")
    ap.add_argument("--rescan", action="store_true",
                    help="throw away the saved cursor and re-sweep from the beginning; "
                         "the only way to recover comments lost from behind the cursor")
    args = ap.parse_args()

    conn = db.connect()
    # schema.sql is all "create ... if not exists", so this is safe every boot
    # and means a fresh Railway deploy needs no manual setup step.
    db.init(conn)

    # First boot on a fresh database: pull the NYC restaurant list. No-op after.
    n = restaurants.ensure_loaded(conn)
    if n:
        print(f"loaded {n:,} NYC restaurants")

    # scoring.sql and resolve.sql were applied by hand until now, which is
    # why production has no scoring views. Every statement in them is
    # create-or-replace, so this is safe on every boot.
    import refresh
    refresh.apply_sql(conn)

    # Before the backfill, not after: a first-boot sweep runs for hours and
    # the fallback should be collecting through all of it.
    if not args.no_rss:
        rss.start_background()
        print(f"rss fallback polling every {rss.INTERVAL // 60} min")

    if not args.no_backfill:
        import backfill
        if args.rescan:
            with conn.cursor() as cur:
                cur.execute("delete from backfill_progress")
            conn.commit()
            print("cursor cleared -- re-sweeping from the beginning")
        # Runs on every boot, and that is the point: after downtime it resumes
        # at the last comment we stored and pages forward to now, filling the
        # gap the 30-minute poll would have skipped straight over. Caught up,
        # it costs one empty page.
        backfill.run(conn, args.backfill_years or None)

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
