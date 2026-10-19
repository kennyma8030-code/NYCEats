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

With --embed (or POLL_EMBED=1) the chores pass also embeds the newly
extracted r/FoodNYC rows for semantic search, last, after the refresh. That
step is optional by design: without a key it is switched off at boot, and
any failure in it is logged and skipped, never allowed to hold up the board.
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


def fetch_new(subreddit, held):
    """Every comment newer than `held`, plus the page it sits on.

    `held` is the newest created_utc the previous poll of this subreddit saw
    (None if nothing has been seen). One page covers a normal poll. A full
    page whose oldest comment is still newer than `held` did not reach back
    far enough -- a burst, or the poller was down -- so page back until it
    does. A subreddit with nothing held yet gets one page; its history is
    the backfill's job.
    """
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


def poll_once(conn, subreddit, seen):
    """Fetch, store, and move this subreddit's overlap point forward.

    `seen` maps subreddit -> newest created_utc a poll has fetched. It is
    the poller's own memory, not max(created_utc) in the table, because other
    writers move that: pulling a newly found thread stores replies newer than
    the poll's page, and the background backfill pages up to the present.
    Paging back only to their newest would skip whatever arrived elsewhere
    in between. At boot there is no memory yet, so the first poll starts
    from the table; the boot backfill is what closes a gap from before it.
    It moves only after the insert, so a poll that fails pages back again.
    """
    if subreddit not in seen:
        seen[subreddit] = db.newest_stored_utc(conn, subreddit)
    comments = fetch_new(subreddit, seen[subreddit])
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
    newest = max(c["created_utc"] for c in comments)
    seen[subreddit] = newest if seen[subreddit] is None else max(seen[subreddit], newest)


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


def _since(conn, days):
    with conn.cursor() as cur:
        cur.execute("select now() - make_interval(days => %s)", (days,))
        since = cur.fetchone()[0]
    conn.commit()
    return since


def extract_once(conn, days, limit, workers):
    """Extract what arrived recently. Returns how many comments were done.

    The window is the safety catch, not a tuning knob. Production holds the
    whole corpus with nothing extracted -- that backlog is done locally and
    shipped with sync.py -- so an unbounded run here would quietly start
    re-buying hundreds of thousands of extractions. Only comments younger
    than `days` are eligible, and at most `limit` per cycle.
    """
    import extract

    done, found = extract.run(conn, limit=limit, since=_since(conn, days), workers=workers)
    if done:
        print(f"  extracted {done} comment(s), {found} mention(s)")
    return done


def embed_once(conn, days, limit, max_usd, scope, workers):
    """Embed r/FoodNYC's recent rows: comments with mentions, and threads by scope.

    Same window idea as extract_once: the backlog is embedded by hand with
    embed.py, and this only keeps up with what arrives. It runs after
    extraction, because a comment is only eligible once it has a mention,
    and after the refresh, so it can never delay the board.

    It is bounded too, so it cannot hold up the polls for long: few retries,
    a short timeout, a per-pass spend cap, and a deadline after which no new batch
    starts. An OpenRouter outage costs one batch's retries.
    """
    import embed
    import embedding

    if not embed.tables_exist(conn):
        conn.commit()
        print("  embed: tables missing -- apply embed_schema.sql; skipping")
        return 0
    budget = embedding.Budget(max_usd)
    stats = embed.run(conn, embed.KINDS[scope], budget, limit=limit,
                      since=_since(conn, days), workers=workers,
                      attempts=EMBED_ATTEMPTS, timeout=EMBED_TIMEOUT,
                      deadline=time.monotonic() + EMBED_DEADLINE, log=lambda *_: None)
    n, failed = sum(stats.embedded.values()), sum(stats.failed.values())
    if n or failed or stats.stop:
        print(f"  embedded {n} row(s), {failed} failed, ${budget.spent:.4f}"
              + (f" -- stopped: {stats.stop}" if stats.stop else ""))
    return n


def refresh_once(conn):
    """Rebuild the board after new mentions landed."""
    import refresh

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


# The embed step's bounds inside one chores pass. Worst case on an outage is
# one batch's attempts at the timeout, about three minutes. The polls wait
# behind it, which costs freshness, never comments: the next poll pages back.
EMBED_ATTEMPTS = 3
EMBED_TIMEOUT = 60
EMBED_DEADLINE = 5 * 60


def _recover(conn):
    """A clean connection after a failed step: rolled back, or a new one.

    A step can fail because the connection itself went (a Postgres restart,
    a dropped proxy). Rolling back a closed connection raises, and raising
    here would end the poller over something the next cycle can survive. So
    reconnect instead; if even that fails, keep the dead one and let the
    next step try again, rather than exit.
    """
    try:
        if not conn.closed:
            conn.rollback()
            return conn
    except Exception:
        traceback.print_exc()
    print("  database connection lost -- reconnecting")
    try:
        return db.connect()
    except Exception:
        traceback.print_exc()
        print("  reconnect failed; the next step will try again")
        return conn


def _step(name, fn, conn, *args):
    """Run one step so that its failure is only its own.

    Returns (result, conn). On failure prints the traceback, returns None,
    and a connection the next step can use -- the same one rolled back, or a
    new one if it was lost.
    """
    try:
        return fn(conn, *args), conn
    except Exception:
        print(f"  {name} failed:")
        traceback.print_exc()
        return None, _recover(conn)


def _idle(conn):
    """End any open transaction before the loop sleeps.

    Every read helper commits already; this is the backstop, so nothing a
    step left open can sit "idle in transaction" through a sleep of up to
    an hour, holding a lock on comments and a snapshot back from vacuum.
    """
    _, conn = _step("commit", lambda c: c.commit(), conn)
    return conn


def poll_due(conn, names, due, seen):
    """Poll every subreddit whose time has come, then set its next due time.

    A failed poll still gets a next time, the shortest one: retrying at once
    would spin on an outage, and waiting a full interval would leave a busy
    city stale. Returns the connection to carry on with.
    """
    for name in names:
        if due[name] > time.time():
            continue
        _, conn = _step(f"poll r/{name}", poll_once, conn, name, seen)
        wait, conn = _step(f"interval r/{name}", interval_for, conn, name)
        due[name] = time.time() + (wait or MIN_INTERVAL)
    return conn


def run_chores(conn, args):
    """The 30-minute pass: settle, then extract, then refresh, then embed.

    Each step gets its own try. A failed extraction must not look like a
    failed settle, and a failed settle still leaves earlier arrivals worth
    extracting. Embedding is strictly optional, so it goes last: the board
    is refreshed before it starts, and an embedding error or a slow
    OpenRouter can never delay extraction or the refresh.

    Every step here is r/FoodNYC's except settling, which is every city's:
    extraction reads HOME only, and embedding reads what extraction wrote
    plus HOME's threads, so the other cities' history is never billed.
    Returns the connection to carry on with.
    """
    _, conn = _step("settle", settle_once, conn)
    extracted = 0
    if args.extract:
        extracted, conn = _step("extract", extract_once, conn, args.extract_days,
                                args.extract_limit, args.extract_workers)
    if extracted:
        _, conn = _step("refresh", refresh_once, conn)
    if args.embed:
        _, conn = _step("embed", embed_once, conn, args.embed_days, args.embed_limit,
                        args.embed_max_usd, args.embed_scope, args.embed_workers)
    return conn


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
                    help="also run extraction on new comments every 30 min ($POLL_EXTRACT)")
    ap.add_argument("--extract-days", type=int,
                    default=int(os.environ.get("POLL_EXTRACT_DAYS", "3")),
                    help="only extract comments from the last N days ($POLL_EXTRACT_DAYS, default 3)")
    ap.add_argument("--extract-limit", type=int,
                    default=int(os.environ.get("POLL_EXTRACT_LIMIT", "1000")),
                    help="at most N extractions per 30-min pass ($POLL_EXTRACT_LIMIT, default 1000)")
    ap.add_argument("--extract-workers", type=int,
                    default=int(os.environ.get("POLL_EXTRACT_WORKERS", "8")),
                    help="concurrent API calls ($POLL_EXTRACT_WORKERS, default 8)")
    ap.add_argument("--embed", action="store_true", default=_env_flag("POLL_EMBED"),
                    help="also embed new r/FoodNYC rows for semantic search every 30 min ($POLL_EMBED)")
    ap.add_argument("--embed-days", type=int,
                    default=int(os.environ.get("POLL_EMBED_DAYS", "3")),
                    help="only embed rows from the last N days ($POLL_EMBED_DAYS, default 3)")
    ap.add_argument("--embed-limit", type=int,
                    default=int(os.environ.get("POLL_EMBED_LIMIT", "2000")),
                    help="at most N rows embedded per 30-min pass ($POLL_EMBED_LIMIT, default 2000)")
    ap.add_argument("--embed-max-usd", type=float,
                    default=float(os.environ.get("POLL_EMBED_MAX_USD", "0.05")),
                    help="spend cap per 30-min pass ($POLL_EMBED_MAX_USD, default 0.05)")
    ap.add_argument("--embed-scope", choices=("comments", "threads", "both"),
                    default=os.environ.get("POLL_EMBED_SCOPE", "comments"),
                    help="what to embed ($POLL_EMBED_SCOPE, default comments)")
    ap.add_argument("--embed-workers", type=int,
                    default=int(os.environ.get("POLL_EMBED_WORKERS", "2")),
                    help="concurrent embedding requests ($POLL_EMBED_WORKERS, default 2)")
    args = ap.parse_args()

    if args.embed:
        import embedding
        # Unlike extraction, a missing key turns embedding off rather than
        # failing the deploy: search is optional, the board is not.
        if not embedding.api_key_var():
            print(f"embedding OFF: --embed needs {' or '.join(embedding.KEY_VARS)}")
            args.embed = False
        elif args.embed_scope not in ("comments", "threads", "both"):
            # argparse checks choices on the command line, not on a default
            # taken from the environment, so a typo here would otherwise
            # raise in every cycle.
            print(f"embedding OFF: POLL_EMBED_SCOPE={args.embed_scope!r} is not "
                  f"comments, threads or both")
            args.embed = False
        else:
            print(f"embedding on: {embedding.MODEL_KEY} (key from {embedding.api_key_var()}), "
                  f"{args.embed_scope} from the last {args.embed_days}d, "
                  f"<= {args.embed_limit}/cycle, <= ${args.embed_max_usd:.2f}/cycle")

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
        # the sweep runs first, the way it always did. Two rounds, not
        # forever: a city that keeps failing is reported and the run goes on.
        if args.once:
            backfill.run_all(conn, names, args.backfill_years or None, rounds=2)
            conn = _recover(conn)        # run_all may have had to replace it
        else:
            backfill.start_background(names, args.backfill_years or None)
            print(f"backfill sweeping {len(names)} subreddit(s) in the background")

    # Everything is due at boot.
    due = dict.fromkeys(names, 0.0)
    seen = {}
    chores_due = 0.0
    while True:
        conn = poll_due(conn, names, due, seen)
        if time.time() >= chores_due:
            conn = run_chores(conn, args)
            chores_due = time.time() + CHORE_INTERVAL
        conn = _idle(conn)

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
