"""Backfill r/FoodNYC for the past N years.

Two bulk passes over the subreddit rather than one request per thread:
posts first (so the foreign key is satisfiable), then comments. That is
~7,600 requests for 5 years instead of ~40,000 thread-by-thread.

Resumable. Progress is a created_utc cursor per pass, written after every
page, so killing this and restarting picks up where it stopped. Every insert
is `on conflict do nothing`, so re-running costs nothing but the fetch.
"""

import argparse
import time
import traceback

import arctic
import db

SUBREDDIT = "FoodNYC"
PAUSE = 0.5          # politeness delay between requests
PAGE = 100
TREE_BATCH = 400     # threads to accumulate before rebuilding reply trees


def backfill_posts(conn, start_utc, pause=PAUSE):
    """Every post since start_utc. Cheap: ~40k posts = ~400 requests."""
    cursor = db.get_cursor(conn, "posts", start_utc)
    total = new = 0
    while True:
        page = arctic.search_page("posts", SUBREDDIT, after=cursor)
        if not page:
            break
        new += db.insert_threads(conn, page)
        total += len(page)
        newest = max(p["created_utc"] for p in page)
        if newest == cursor and len(page) < PAGE:
            break                        # no forward progress, nothing left
        cursor = newest
        db.set_cursor(conn, "posts", cursor)
        print(f"  posts: {total:>7,} seen  {new:>7,} new   at {time.strftime('%Y-%m-%d', time.gmtime(cursor))}")
        if len(page) < PAGE:
            break
        time.sleep(pause)
    return total, new


def backfill_comments(conn, start_utc, pause=PAUSE):
    """Every comment since start_utc, fetching any post we're missing first."""
    cursor = db.get_cursor(conn, "comments", start_utc)
    total = new = rescued = 0
    pending = set()
    while True:
        page = arctic.search_page("comments", SUBREDDIT, after=cursor)
        if not page:
            break

        # A comment on a thread we don't have would violate the FK. This should
        # be rare after the posts pass -- it means a post outside the window, or
        # one the archive skipped.
        missing = db.missing_thread_ids(conn, {c["link_id"] for c in page})
        if missing:
            posts = arctic.posts_by_id({m[3:] for m in missing})
            rescued += db.insert_threads(conn, posts)
            have = db.missing_thread_ids(conn, {c["link_id"] for c in page})
            if have:
                page = [c for c in page if c["link_id"] not in have]
            time.sleep(pause)

        new += db.insert_comments(conn, page)
        total += len(page)

        # fill_tree is a recursive CTE; running it per page doubles wall time.
        # Batch it -- late-arriving parents are picked up by the next flush.
        pending.update(c["link_id"] for c in page)
        if len(pending) >= TREE_BATCH:
            db.fill_tree(conn, pending)
            pending.clear()

        newest = max(c["created_utc"] for c in page)
        if newest == cursor and len(page) < PAGE:
            break
        cursor = newest
        db.set_cursor(conn, "comments", cursor)
        print(f"  comments: {total:>8,} seen  {new:>8,} new  {rescued:>4} posts rescued"
              f"   at {time.strftime('%Y-%m-%d', time.gmtime(cursor))}")
        if len(page) < PAGE:
            break
        time.sleep(pause)

    if pending:
        db.fill_tree(conn, pending)
    return total, new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=5.0)
    ap.add_argument("--restart", action="store_true",
                    help="ignore saved progress and start from the beginning")
    ap.add_argument("--posts-only", action="store_true")
    ap.add_argument("--repair", action="store_true",
                    help="only rebuild reply trees over every thread, then exit")
    args = ap.parse_args()

    start_utc = int(time.time() - args.years * 365.25 * 86400)
    conn = db.connect()
    db.init(conn)

    if args.restart:
        with conn.cursor() as cur:
            cur.execute("delete from backfill_progress")
        conn.commit()
        print("progress reset")

    if args.repair:
        with conn.cursor() as cur:
            cur.execute("select id from threads")
            ids = [r[0] for r in cur.fetchall()]
        print(f"rebuilding reply trees over {len(ids):,} threads")
        print(f"  updated {db.fill_tree(conn, ids):,} rows")
        return

    print(f"backfilling from {time.strftime('%Y-%m-%d', time.gmtime(start_utc))}\n")
    began = time.time()

    try:
        print("phase 1: posts")
        seen, new = backfill_posts(conn, start_utc)
        print(f"  done: {seen:,} posts, {new:,} new\n")

        if not args.posts_only:
            print("phase 2: comments")
            seen, new = backfill_comments(conn, start_utc)
            print(f"  done: {seen:,} comments, {new:,} new\n")
    except KeyboardInterrupt:
        print("\ninterrupted -- progress saved, re-run to resume")
    except Exception:
        traceback.print_exc()
        conn.rollback()
        print("\nfailed -- progress saved, re-run to resume")

    with conn.cursor() as cur:
        cur.execute("select (select count(*) from threads), (select count(*) from comments)")
        t, c = cur.fetchone()
    print(f"database now: {t:,} threads, {c:,} comments  "
          f"({(time.time()-began)/60:.1f} min this run)")


if __name__ == "__main__":
    main()
