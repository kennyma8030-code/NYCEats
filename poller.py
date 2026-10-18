"""Poll every subreddit in subreddits.py, each as often as its activity needs.

A poll takes the newest page of comments and, if that page is still all
news, keeps paging back until it reaches what we already hold. So how often
a city is polled decides how fresh it is, never whether comments are lost.
The cadence is set from each city's busiest hour of the past week: r/chicagofood
peaks above 200 comments an hour and is polled every ~15 minutes;
r/FoodSanDiego peaks near 70 and waits ~40.

When a comment arrives on a thread we've never seen, backfill that whole
thread (the post plus every comment in it) before storing the comment.

With --extract (or POLL_EXTRACT=1, which is what deploy.py sets on Railway)
the chores pass also runs the extraction prompt over the comments that just
arrived and refreshes the scoring views, so the board moves within half an
hour instead of waiting for someone to run extract.py and sync.py by hand.
Extraction only ever reads subreddits.HOME; the other cities are collected,
not scored.
"""

import argparse
import os
import time
import traceback

import arctic
import db
import ingest
import restaurants
import rss
import subreddits

# Seconds between polls of one subreddit. Sized so the busiest hour of the
# last week fills half a page per poll: headroom for a burst before paging
# back costs a second request. Clamped, because a city that went quiet for a
# week should still be looked at hourly, and a viral thread should not have
# us hammering a free archive every minute.
PAGE_TARGET = arctic.PAGE // 2
MIN_INTERVAL = 10 * 60
MAX_INTERVAL = 60 * 60
# How far back one poll will page after downtime: 2,000 comments is a few
# days of even the busiest city. Past that the backfill cursor, which every
# boot resumes, is what closes the gap.
MAX_PAGES = 20
# Settling scores and extraction run on one clock of their own, the old 30
# minutes: they are not per city, and refreshing the scoring views every time
# any city is polled would rebuild the board several times an hour.
CHORE_INTERVAL = 30 * 60


def pull_threads(conn, bare_ids):
    """Download every comment of each newly discovered thread."""
    for pid in sorted(bare_ids):
        comments = arctic.all_thread_comments(pid)
        n = db.insert_comments(conn, comments)
        print(f"  backfilled t3_{pid}: {len(comments)} comments ({n} new)")
        time.sleep(1)


def fetch_new(conn, subreddit):
    """Every comment newer than the newest one stored, plus the page it sits on.

    One page covers a normal poll. A full page whose oldest comment is still
    newer than anything we hold did not reach back far enough -- a burst, or
    the poller was down -- so page back until it does. A subreddit with
    nothing stored yet gets one page; its history is the backfill's job.
    """
    held = db.newest_stored_utc(conn, subreddit)
    got = {}
    page = arctic.newest_comments(subreddit)
    for pages in range(1, MAX_PAGES + 1):
        for c in page:
            got[c["id"]] = c
        if held is None or len(page) < arctic.PAGE:
            break
        oldest = min(c["created_utc"] for c in page)
        if oldest <= held:
            break
        if pages == MAX_PAGES:
            print(f"  r/{subreddit}: still no overlap after {pages} pages; "
                  f"the next boot's backfill will close the gap")
            return list(got.values())
        time.sleep(1)
        # +1: `before` is exclusive, and a comment posted in the same second
        # as this page's oldest would otherwise fall between the two pages.
        page = arctic.newest_comments(subreddit, before=oldest + 1)
    if pages > 1:
        print(f"  r/{subreddit}: paged back {pages} pages to reach stored comments")
    return list(got.values())


def poll_once(conn, subreddit):
    comments = fetch_new(conn, subreddit)
    print(f"r/{subreddit}: fetched {len(comments)} newest comments")
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


def interval_for(conn, subreddit):
    """Seconds until this subreddit's next poll. See PAGE_TARGET.

    A city with no week of history yet gets the shortest interval; its first
    polls are what fill the week in.
    """
    peak = db.busiest_hour(conn, subreddit)
    if not peak:
        return MIN_INTERVAL
    return max(MIN_INTERVAL, min(MAX_INTERVAL, PAGE_TARGET / peak * 3600))


def settle_once(conn, batches=5):
    """Finalise scores for comments past 36h, every city at once.

    ~3,000 comments a day across the seven cities is ~30 requests; five
    batches per chores pass is room for 240.
    """
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


def extract_once(conn, days, limit, workers):
    """Extract what arrived recently, then rebuild the board if anything landed.

    The window is the safety catch, not a tuning knob. Production holds the
    whole corpus with nothing extracted -- that backlog is done locally and
    shipped with sync.py -- so an unbounded run here would quietly start
    re-buying hundreds of thousands of extractions. Only comments younger
    than `days` are eligible, and at most `limit` per cycle.
    """
    import extract
    import refresh

    with conn.cursor() as cur:
        cur.execute("select now() - make_interval(days => %s)", (days,))
        since = cur.fetchone()[0]
    done, found = extract.run(conn, limit=limit, since=since, workers=workers)
    if not done:
        return
    print(f"  extracted {done} comment(s), {found} mention(s)")

    # Serial plan on purpose: Railway's Postgres container has a small
    # /dev/shm, and a parallel refresh of entity_leaderboard dies on it with
    # "could not resize shared memory segment".
    with conn.cursor() as cur:
        cur.execute("set max_parallel_workers_per_gather = 0")
    try:
        refresh.refresh_views(conn, verbose=False)
        print("  refreshed scoring views")
    finally:
        conn.rollback()      # a failed refresh leaves the transaction aborted
        with conn.cursor() as cur:
            cur.execute("reset max_parallel_workers_per_gather")
        conn.commit()


def _env_flag(name):
    return os.environ.get(name, "0").strip().lower() not in ("", "0", "false", "no")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="poll each subreddit once, run the chores, and exit")
    ap.add_argument("--subreddit", action="append", choices=subreddits.SUBREDDITS,
                    help="poll and backfill only this one (repeatable; default: all)")
    ap.add_argument("--no-rss", action="store_true",
                    help="do not run the RSS fallback collector")
    ap.add_argument("--no-backfill", action="store_true",
                    help="start polling immediately, skipping the catch-up sweep")
    ap.add_argument("--backfill-years", type=float, default=0,
                    help="limit the catch-up sweep to the last N years (default: all time)")
    ap.add_argument("--rescan", action="store_true",
                    help="throw away the saved cursor and re-sweep from the beginning; "
                         "the only way to recover comments lost from behind the cursor")
    # Defaults come from the environment so Railway can switch inference on
    # and off with a variable (deploy.py) instead of a start-command edit.
    ap.add_argument("--extract", action="store_true", default=_env_flag("POLL_EXTRACT"),
                    help="also run extraction on new comments each cycle ($POLL_EXTRACT)")
    ap.add_argument("--extract-days", type=int,
                    default=int(os.environ.get("POLL_EXTRACT_DAYS", "3")),
                    help="only extract comments from the last N days ($POLL_EXTRACT_DAYS, default 3)")
    ap.add_argument("--extract-limit", type=int,
                    default=int(os.environ.get("POLL_EXTRACT_LIMIT", "1000")),
                    help="at most N extractions per cycle ($POLL_EXTRACT_LIMIT, default 1000)")
    ap.add_argument("--extract-workers", type=int,
                    default=int(os.environ.get("POLL_EXTRACT_WORKERS", "8")),
                    help="concurrent API calls ($POLL_EXTRACT_WORKERS, default 8)")
    args = ap.parse_args()

    if args.extract:
        import extract
        # Fail the deploy, not every comment: a missing key would otherwise
        # stamp each new comment with the same extract_error.
        if not os.environ.get(extract.API_KEY_VAR):
            raise SystemExit(f"--extract needs {extract.API_KEY_VAR} "
                             f"(the key for {extract.API_URL})")
        print(f"inference on: {extract.MODEL} via {extract.API_URL}, "
              f"last {args.extract_days}d, <= {args.extract_limit}/cycle, "
              f"{args.extract_workers} workers")

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

    # Its own thread, like the backfill below: the fallback should keep
    # collecting whatever the main path is busy with. r/FoodNYC only -- it is
    # insurance for the board, and seven feeds every five minutes is the kind
    # of traffic Reddit answers with a 429.
    if not args.no_rss:
        rss.start_background()
        print(f"rss fallback polling every {rss.INTERVAL // 60} min")

    names = args.subreddit or list(subreddits.SUBREDDITS)

    if not args.no_backfill:
        import backfill
        if args.rescan:
            db.clear_cursors(conn, names)
            print("cursors cleared -- re-sweeping from the beginning")
        # Runs on every boot, and that is the point: after downtime it resumes
        # at the last comment we stored and pages forward to now, filling the
        # gap the polls would have skipped straight over. Caught up, it costs
        # one empty page per city. A city never swept starts from its first
        # post, which is hours -- hence a thread beside the polls, not a step
        # before them.
        # --once exits after one pass and a daemon dies with it, so there
        # the sweep runs first, the way it always did.
        if args.once:
            backfill.run_all(conn, names, args.backfill_years or None)
        else:
            backfill.start_background(names, args.backfill_years or None)
            print(f"backfill sweeping {len(names)} subreddit(s) in the background")

    # Everything is due at boot.
    due = dict.fromkeys(names, 0.0)
    chores_due = 0.0
    while True:
        for name in names:
            if due[name] > time.time():
                continue
            try:
                poll_once(conn, name)
            except Exception:
                traceback.print_exc()
                conn.rollback()
            try:
                wait = interval_for(conn, name)
            except Exception:
                traceback.print_exc()
                conn.rollback()
                wait = MIN_INTERVAL
            due[name] = time.time() + wait

        if time.time() >= chores_due:
            try:
                settle_once(conn)
            except Exception:
                traceback.print_exc()
                conn.rollback()

            # Separate try: a failed extraction must not look like a failed
            # settle, and earlier arrivals are still worth extracting.
            if args.extract:
                try:
                    extract_once(conn, args.extract_days, args.extract_limit,
                                 args.extract_workers)
                except Exception:
                    traceback.print_exc()
                    conn.rollback()
            chores_due = time.time() + CHORE_INTERVAL

        if args.once:
            break
        nxt = min(due, key=due.get)
        wake = min(due[nxt], chores_due)
        sleep = max(0, wake - time.time())
        label = f"r/{nxt}" if due[nxt] <= chores_due else "chores"
        print(f"sleeping {sleep / 60:.1f} min (next: {label})\n")
        time.sleep(sleep)


if __name__ == "__main__":
    main()
