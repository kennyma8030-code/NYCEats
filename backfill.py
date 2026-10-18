"""Backfill every subreddit in subreddits.py, all of its history by default.

Two bulk passes over each subreddit rather than one request per thread:
posts first (so the foreign key is satisfiable), then comments. That is
~7,600 requests for 5 years instead of ~40,000 thread-by-thread.

Resumable. Progress is a created_utc cursor per (subreddit, pass), written
after every page, so killing this and restarting picks up where it stopped. Every insert
is `on conflict do nothing`, so re-running costs nothing but the fetch.
"""

import argparse
import threading
import time
import traceback

import arctic
import db
import ingest
import subreddits

PAUSE = 0.5          # politeness delay between requests
PAGE = 100
TREE_BATCH = 400     # threads to accumulate before rebuilding reply trees
EPOCH = 1104537600   # 2005-01-01, before Reddit existed. "All time" floor.
LOG_EVERY = 25       # pages between progress lines (keeps long runs quiet)
RETRY_AFTER = 5 * 60 # seconds before a failed sweep resumes from its cursor


def backfill_posts(conn, subreddit, start_utc, pause=PAUSE):
    """Every post since start_utc. Cheap: ~40k posts = ~400 requests."""
    cursor = db.get_cursor(conn, subreddit, "posts", start_utc)
    total = new = pages = 0
    while True:
        page = arctic.search_page("posts", subreddit, after=cursor)
        if not page:
            break
        new += db.insert_threads(conn, page)
        total += len(page)
        newest = max(p["created_utc"] for p in page)
        # A short page is NOT the end -- the API returns fewer than `limit`
        # for sparse ranges. Only an empty page, no forward progress, or
        # reaching the present means we're done.
        if newest <= cursor:
            break
        cursor = newest
        db.set_cursor(conn, subreddit, "posts", cursor)
        pages += 1
        if pages % LOG_EVERY == 0:
            print(f"  {subreddit} posts: {total:>7,} seen  {new:>7,} new   at {time.strftime('%Y-%m-%d', time.gmtime(cursor))}", flush=True)
        if cursor >= time.time() - 60:
            break
        time.sleep(pause)
    return total, new


def backfill_comments(conn, subreddit, start_utc, pause=PAUSE):
    """Every comment since start_utc, fetching any post we're missing first."""
    cursor = db.get_cursor(conn, subreddit, "comments", start_utc)
    total = new = rescued = pages = 0
    pending, touched = set(), set()
    while True:
        page = arctic.search_page("comments", subreddit, after=cursor)
        if not page:
            break

        # Rare after the posts pass: a post older than the window, or one the
        # archive skipped.
        page, got, _ = ingest.ensure_threads(conn, page, pause)
        rescued += got

        new += db.insert_comments(conn, page)
        total += len(page)

        # fill_tree is a recursive CTE; running it per page doubles wall time.
        # Batch it -- late-arriving parents are picked up by the next flush.
        pending.update(c["link_id"] for c in page)
        touched.update(c["link_id"] for c in page)
        if len(pending) >= TREE_BATCH:
            db.fill_tree(conn, pending)
            pending.clear()

        newest = max(c["created_utc"] for c in page)
        if newest <= cursor:
            break                        # no forward progress
        cursor = newest
        db.set_cursor(conn, subreddit, "comments", cursor)
        pages += 1
        if pages % LOG_EVERY == 0:
            print(f"  {subreddit} comments: {total:>8,} seen  {new:>8,} new  {rescued:>4} posts rescued"
                  f"   at {time.strftime('%Y-%m-%d', time.gmtime(cursor))}", flush=True)
        if cursor >= time.time() - 60:
            break                        # caught up to the present
        time.sleep(pause)

    if pending:
        db.fill_tree(conn, pending)
    return total, new, touched


def stale_thread_ids(conn, subreddit):
    """Threads holding a comment whose depth was never computed.

    Phase 2 fills trees as it goes, so sweeping every thread afterwards is a
    recursive CTE over the whole corpus to change nothing. These are the only
    threads that can still be wrong: a reply stored in an earlier run than the
    parent it hangs off.
    """
    with conn.cursor() as cur:
        cur.execute("select distinct thread_id from comments "
                    "where subreddit = %s and depth is null", (subreddit,))
        return {r[0] for r in cur.fetchall()}


def run(conn, subreddit, years=None, posts_only=False):
    """Both phases plus the tree sweep for one subreddit. Safe to call repeatedly.

    years=None sweeps from the beginning of the subreddit. The cursor wins
    over `years` once it exists: a sweep only ever moves forward.
    """
    start_utc = EPOCH if not years else int(time.time() - years * 365.25 * 86400)
    print(f"backfilling r/{subreddit} from {time.strftime('%Y-%m-%d', time.gmtime(start_utc))}")

    print(f"phase 1: r/{subreddit} posts")
    seen, new = backfill_posts(conn, subreddit, start_utc)
    print(f"  done: {seen:,} posts, {new:,} new\n")
    if posts_only:
        return

    print(f"phase 2: r/{subreddit} comments")
    seen, new, touched = backfill_comments(conn, subreddit, start_utc)
    print(f"  done: {seen:,} comments, {new:,} new\n")

    print(f"phase 3: r/{subreddit} reply trees")
    ids = touched | stale_thread_ids(conn, subreddit)
    print(f"  {len(ids):,} thread(s) to check")
    print(f"  updated {db.fill_tree(conn, ids):,} rows\n")


def run_all(conn, names, years=None, retry_after=RETRY_AFTER):
    """Sweep each subreddit in turn until every one has caught up to now.

    A failure is logged and the same subreddit retried after a pause: the
    cursor makes the retry resume, not restart, and moving on would leave a
    hole that only the next boot would notice. Order is the caller's, which
    is how r/FoodNYC's short gap-fill goes first and never waits behind a
    new city's twelve years.
    """
    for name in names:
        while True:
            try:
                run(conn, name, years)
                break
            except Exception:
                traceback.print_exc()
                try:
                    conn.rollback()
                except Exception:
                    conn = db.connect()          # the connection itself went
                print(f"[backfill] r/{name} failed -- retrying in {retry_after // 60} min",
                      flush=True)
                time.sleep(retry_after)
    print("[backfill] every subreddit caught up", flush=True)


def start_background(names, years=None):
    """Run the sweeps beside the poller rather than before it.

    A new city's full history is hours of requests, and a poller that waits
    for it lets every city, r/FoodNYC included, go dark for the whole time.
    Own connection: psycopg2 connections are not thread-safe. Daemon: it dies
    with its host, and the cursors mean the next boot carries on.
    """
    def target():
        run_all(db.connect(), names, years)
    thread = threading.Thread(target=target, name="backfill", daemon=True)
    thread.start()
    return thread


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subreddit", action="append", choices=subreddits.SUBREDDITS,
                    help="sweep only this one (repeatable; default: every subreddit)")
    ap.add_argument("--years", type=float, default=0,
                    help="limit to the last N years (default: all time)")
    ap.add_argument("--restart", action="store_true",
                    help="ignore saved progress and start from the beginning")
    ap.add_argument("--posts-only", action="store_true")
    ap.add_argument("--repair", action="store_true",
                    help="only rebuild reply trees over every thread, then exit")
    args = ap.parse_args()

    conn = db.connect()
    db.init(conn)

    names = args.subreddit or list(subreddits.SUBREDDITS)
    if args.restart:
        db.clear_cursors(conn, names)
        print(f"progress reset for {', '.join(names)}")

    if args.repair:
        with conn.cursor() as cur:
            cur.execute("select id from threads")
            ids = [r[0] for r in cur.fetchall()]
        print(f"rebuilding reply trees over {len(ids):,} threads")
        print(f"  updated {db.fill_tree(conn, ids):,} rows")
        return

    began = time.time()
    try:
        for name in names:
            run(conn, name, args.years or None, posts_only=args.posts_only)
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
