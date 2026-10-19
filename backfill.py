"""Backfill every subreddit in subreddits.py, all of its history by default.

Two bulk passes over each subreddit rather than one request per thread:
posts first (so the foreign key is satisfiable), then comments. That is
~7,600 requests for 5 years instead of ~40,000 thread-by-thread.

Resumable. Progress is a created_utc cursor per (subreddit, pass), written
after every page, so killing this and restarting picks up where it stopped. Every insert
is `on conflict do nothing`, so re-running costs nothing but the fetch.
"""

import argparse
import os
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
MAX_TRIES = 3        # failures in a row before a city goes to the back of the queue
DISK_EVERY = 10      # pages between database size checks while sweeping another city


class DiskBudget(RuntimeError):
    """The database is past BACKFILL_MAX_DB_MB: stop sweeping other cities."""


def max_db_mb():
    """BACKFILL_MAX_DB_MB, default 3,500 of the Railway volume's 5,000.

    The volume also holds WAL, which a long sweep writes as fast as it
    inserts, so the line sits well below the volume's size.
    """
    return float(os.environ.get("BACKFILL_MAX_DB_MB", "3500"))


def check_disk(conn, subreddit):
    """Refuse to keep sweeping another city's history once the database is too big.

    HOME is never stopped: its sweep is the board's own gap-fill, a few pages
    after downtime, and stopping it would cost the board comments.
    """
    if subreddit == subreddits.HOME:
        return
    size, limit = db.database_size_mb(conn), max_db_mb()
    if size > limit:
        raise DiskBudget(f"database is {size:,.0f} MB, over BACKFILL_MAX_DB_MB={limit:,.0f}; "
                         f"not sweeping r/{subreddit} any further")


def _search(kind, subreddit):
    return lambda after: arctic.search_page(kind, subreddit, after=after)


def backfill_posts(conn, subreddit, start_utc, pause=PAUSE):
    """Every post since start_utc. Cheap: ~40k posts = ~400 requests."""
    cursor = db.get_cursor(conn, subreddit, "posts", start_utc)
    total = new = pages = 0
    check_disk(conn, subreddit)
    # A short page is NOT the end -- the API returns fewer than `limit` for
    # sparse ranges. Only an empty page, a page with nothing new, or reaching
    # the present means we're done (arctic.forward).
    for fresh, page in arctic.forward(_search("posts", subreddit), cursor, pause):
        new += db.insert_threads(conn, fresh)
        total += len(fresh)
        cursor = max(p["created_utc"] for p in page)
        db.set_cursor(conn, subreddit, "posts", cursor)
        pages += 1
        if pages % LOG_EVERY == 0:
            print(f"  {subreddit} posts: {total:>7,} seen  {new:>7,} new   at {time.strftime('%Y-%m-%d', time.gmtime(cursor))}", flush=True)
        if pages % DISK_EVERY == 0:
            check_disk(conn, subreddit)
        if cursor >= time.time() - 60:
            break
    return total, new


def backfill_comments(conn, subreddit, start_utc, pause=PAUSE):
    """Every comment since start_utc, fetching any post we're missing first."""
    cursor = db.get_cursor(conn, subreddit, "comments", start_utc)
    pending, touched = set(), set()
    check_disk(conn, subreddit)
    try:
        total, new = _sweep_comments(conn, subreddit, cursor, pause, pending, touched)
    except DiskBudget:
        # Stored comments whose reply trees have not been filled yet: fill
        # them before giving up, or their depth stays null until a rescan.
        if pending:
            db.fill_tree(conn, pending)
        raise

    if pending:
        db.fill_tree(conn, pending)
    return total, new, touched


def _sweep_comments(conn, subreddit, cursor, pause, pending, touched):
    """backfill_comments' page loop. Returns (comments stored, of them new)."""
    total = new = rescued = pages = 0
    for fresh, page in arctic.forward(_search("comments", subreddit), cursor, pause):
        # From the page as fetched, before comments with no post are dropped:
        # a page whose every comment is orphaned must still move the cursor,
        # or the sweep would fetch it again forever.
        newest = max(c["created_utc"] for c in page)

        # Rare after the posts pass: a post older than the window, or one the
        # archive skipped.
        stored, got, _ = ingest.ensure_threads(conn, fresh, pause)
        rescued += got

        new += db.insert_comments(conn, stored)
        total += len(stored)

        # fill_tree is a recursive CTE; running it per page doubles wall time.
        # Batch it -- late-arriving parents are picked up by the next flush.
        pending.update(c["link_id"] for c in stored)
        touched.update(c["link_id"] for c in stored)
        if len(pending) >= TREE_BATCH:
            db.fill_tree(conn, pending)
            pending.clear()

        cursor = newest
        db.set_cursor(conn, subreddit, "comments", cursor)
        pages += 1
        if pages % LOG_EVERY == 0:
            print(f"  {subreddit} comments: {total:>8,} seen  {new:>8,} new  {rescued:>4} posts rescued"
                  f"   at {time.strftime('%Y-%m-%d', time.gmtime(cursor))}", flush=True)
        if pages % DISK_EVERY == 0:
            check_disk(conn, subreddit)
        if cursor >= time.time() - 60:
            break                        # caught up to the present
    return total, new


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


def scope(home_years=None, only=None, env=None):
    """Which subreddits the boot sweep covers, and how far back each one starts.

    Safe by default: r/FoodNYC only. The six other cities' full history is
    ~3.5M comments, about 3.1 GB plus the WAL to write it, on a 5 GB volume
    that holds 1.3 GB today -- so it waits for the owner to opt in:

      BACKFILL_SUBREDDITS   comma list or "all"; default FoodNYC
      BACKFILL_YEARS_OTHER  years of history for a city other than HOME:
                            0 (default) = none, the city is not swept;
                            N = the last N years; "all" = all time

    HOME's depth is --backfill-years (0 = all time), as before; its sweep
    is the board's gap-fill after downtime and is never skipped. `only`
    (--subreddit) narrows the list further. Once a city has a cursor, the
    cursor wins over its years. Returns (names, {name: years or None}).
    """
    env = os.environ if env is None else env
    names = subreddits.parse(env.get("BACKFILL_SUBREDDITS"), (subreddits.HOME,))
    if only:
        names = [n for n in names if n in only]
    raw = (env.get("BACKFILL_YEARS_OTHER") or "0").strip().lower()
    try:
        other = None if raw == "all" else float(raw)
    except ValueError:
        other = -1
    if other is not None and other < 0:
        raise SystemExit(f"BACKFILL_YEARS_OTHER={raw!r} is not 'all' or a number of years >= 0")
    out, years = [], {}
    for name in names:
        if name != subreddits.HOME and other == 0:
            print(f"[backfill] r/{name} is in BACKFILL_SUBREDDITS but BACKFILL_YEARS_OTHER is 0; "
                  f"not sweeping it", flush=True)
            continue
        out.append(name)
        years[name] = home_years if name == subreddits.HOME else other
    return out, years


def _years(years, name):
    return years.get(name) if isinstance(years, dict) else years


def run_all(conn, names, years=None, retry_after=RETRY_AFTER, tries=MAX_TRIES,
            rounds=None):
    """Sweep each subreddit in turn until every one has caught up to now.

    A failure is logged and the same subreddit retried after a pause: the
    cursor makes the retry resume, not restart. After `tries` failures in a
    row the city goes to the back of the queue, loudly, so one bad page or
    an outage on one name cannot stall every city after it. Order is
    otherwise the caller's, which is how r/FoodNYC's short gap-fill goes
    first and never waits behind a new city's twelve years.

    `rounds` caps how many times one city is queued: None keeps cycling
    (the background thread, which should outlast any outage), a number
    lets --once finish. Returns the subreddits that never caught up.

    `years` is one depth for every city or a {name: years} map (scope()).
    A city that finds the database past BACKFILL_MAX_DB_MB is not retried,
    and no other city but HOME is swept after it: more history would only
    fill the disk faster.
    """
    queue = [(name, 1) for name in names]
    failed = []
    while queue:
        name, round_ = queue.pop(0)
        for attempt in range(1, tries + 1):
            try:
                run(conn, name, _years(years, name))
                break
            except DiskBudget as e:
                print(f"[backfill] STOPPED: {e}. Raise BACKFILL_MAX_DB_MB or grow the "
                      f"volume to go on; cursors are kept.", flush=True)
                stopped = [name] + [n for n, _ in queue if n != subreddits.HOME]
                queue = [(n, r) for n, r in queue if n == subreddits.HOME]
                failed += stopped
                break
            except Exception:
                traceback.print_exc()
                conn = db.recover(conn)
                if attempt < tries:
                    print(f"[backfill] r/{name} failed -- retrying in {retry_after // 60} min",
                          flush=True)
                    time.sleep(retry_after)
        else:
            if rounds is not None and round_ >= rounds:
                print(f"[backfill] r/{name} FAILED {tries} times in round {round_} -- "
                      f"giving up until the next run; its cursor is kept", flush=True)
                failed.append(name)
            else:
                print(f"[backfill] r/{name} FAILED {tries} times in a row -- moving on, "
                      f"will retry it after the others", flush=True)
                queue.append((name, round_ + 1))
                time.sleep(retry_after)
    if failed:
        print(f"[backfill] not caught up: {', '.join(failed)}", flush=True)
    else:
        print("[backfill] every subreddit caught up", flush=True)
    return failed


def start_background(names, years=None, retry_after=RETRY_AFTER):
    """Run the sweeps beside the poller rather than before it.

    A new city's full history is hours of requests, and a poller that waits
    for it lets every city, r/FoodNYC included, go dark for the whole time.
    Own connection: psycopg2 connections are not thread-safe. Daemon: it dies
    with its host, and the cursors mean the next boot carries on. Nothing
    may end it silently: a failed connect or anything run_all lets escape is
    logged and the sweep starts over from the cursors after a pause.
    """
    def target():
        while True:
            try:
                run_all(db.connect(), names, years, retry_after)
                return
            except Exception:
                traceback.print_exc()
                print(f"[backfill] thread error -- restarting in {retry_after // 60} min",
                      flush=True)
                time.sleep(retry_after)
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
