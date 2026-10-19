"""Poll every subreddit in subreddits.py, each as often as its activity needs.

A poll takes the newest page of comments and keeps paging back until it is
LAG hours behind the newest comment the previous poll saw. So how often a
city is polled decides how fresh it is, never whether comments are lost.
The lag is there because Arctic Shift does not publish in order: a comment
can turn up hours after newer ones (p99 8.8h on r/FoodNYC), and a poll that
stopped at what it last saw would step over it. What even that misses, the
chores pass catches by sweeping each city's last 48 hours again.
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
not scored. EXTRACT_VERSION=v6 swaps the old extractor for the benchmarked v6
one (extract_v6.py), which also extracts new posts; unset, nothing changes.

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
# How far behind the previous poll's newest comment each poll pages back.
# Arctic Shift makes comments visible out of order -- measured on r/FoodNYC,
# p99 8.8 hours after newer ones -- so stopping at the previous newest lost
# about 1% of comments. Eight hours is two or three pages per poll at
# today's rates; the chores re-sweep below catches the tail beyond it.
LAG = float(os.environ.get("POLL_LAG_HOURS", "8")) * 3600
# A comment can also arrive before its post does (up to ~20h), and it cannot
# be stored without it. Its thread is remembered and looked for again on
# every later poll of that city, for up to two days. Bounded, because a
# post deleted for good is never coming.
ORPHAN_TTL = 48 * 3600
ORPHAN_MAX = 1000
# The chores pass re-reads each polled city's last RESWEEP_HOURS forward
# from the archive, every RESWEEP_EVERY. Late comments past the poll's lag
# and orphans whose post finally appeared land here. About 6,000 comments
# across the seven cities, ~60 requests, so it runs a few times a day, not
# every half hour.
RESWEEP_HOURS = float(os.environ.get("POLL_RESWEEP_HOURS", "48"))
RESWEEP_EVERY = float(os.environ.get("POLL_RESWEEP_EVERY_HOURS", "6")) * 3600


def pull_threads(conn, bare_ids):
    """Download every comment of each newly discovered thread."""
    for pid in sorted(bare_ids):
        comments = arctic.all_thread_comments(pid)
        n = db.insert_comments(conn, comments)
        print(f"  backfilled t3_{pid}: {len(comments)} comments ({n} new)")
        time.sleep(1)


def fetch_new(subreddit, held, lag=None):
    """Every comment created after `held - lag`, each once.

    `held` is the newest created_utc the previous poll of this subreddit saw
    (None if nothing has been seen). A full page whose oldest comment is
    still newer than `held - lag` did not reach back far enough, so page
    back until it does. The lag (LAG) is what catches comments the archive
    published late; the overlap costs a page or two and is deduped here and
    by the insert. A subreddit with nothing held yet gets one page; its
    history is the backfill's job.
    """
    lag = LAG if lag is None else lag
    got = {}
    page = arctic.newest_comments(subreddit)
    for pages in range(1, MAX_PAGES + 1):
        for c in page:
            got[c["id"]] = c
        if held is None or len(page) < arctic.PAGE:
            break
        oldest = min(c["created_utc"] for c in page)
        if oldest <= held - lag:
            break
        if pages == MAX_PAGES:
            print(f"  r/{subreddit}: still no overlap after {pages} pages; "
                  f"the re-sweep or the next boot's backfill will close the gap")
            return list(got.values())
        time.sleep(1)
        # +1: `before` is exclusive, and a comment posted in the same second
        # as this page's oldest would otherwise fall between the two pages.
        page = arctic.newest_comments(subreddit, before=oldest + 1)
    if pages > 1:
        print(f"  r/{subreddit}: paged back {pages} pages, to {lag / 3600:g}h before the last poll")
    return list(got.values())


def remember_orphans(pending, link_ids, now=None):
    """Note threads whose post the archive did not have yet. Bounded: oldest go."""
    now = time.time() if now is None else now
    for lid in link_ids:
        pending.setdefault(lid, now)
    for lid in sorted(pending, key=pending.get)[:max(0, len(pending) - ORPHAN_MAX)]:
        del pending[lid]


def store(conn, comments, pending=None):
    """Store fetched comments, pulling in any thread we have never seen.

    Comments whose post the archive cannot return yet are dropped (they
    cannot satisfy the foreign key) and their threads go into `pending`,
    to be looked for again. Returns how many comments were new.
    """
    if not comments:
        return 0
    storable, got, discovered = ingest.ensure_threads(conn, comments)
    if got:
        print(f"  {got} unknown thread(s), backfilling")
        pull_threads(conn, discovered)
    if len(storable) < len(comments):
        dropped = {c["link_id"] for c in comments} - {c["link_id"] for c in storable}
        print(f"  skipping {len(comments) - len(storable)} comment(s) with no post yet "
              f"({len(dropped)} thread(s), will look again)")
        if pending is not None:
            remember_orphans(pending, dropped)
    new = db.insert_comments(conn, storable)
    db.fill_tree(conn, {c["link_id"] for c in storable})
    return new


def retry_orphans(conn, pending, now=None):
    """Look again for the posts of threads whose comments were dropped.

    A post that has turned up -- in the archive, or in our table by another
    route -- gets its whole thread pulled, which brings back the comments
    dropped earlier. One request per 50 threads still missing. Threads
    still missing after ORPHAN_TTL are given up; the boot backfill and the
    re-sweep are the last chances. Returns how many threads were recovered.
    """
    if not pending:
        return 0
    now = time.time() if now is None else now
    for lid in [lid for lid, t in pending.items() if now - t > ORPHAN_TTL]:
        print(f"  giving up on {lid}: no post after {ORPHAN_TTL // 3600}h")
        del pending[lid]
    if not pending:
        return 0
    found = db.existing_thread_ids(conn, pending)
    missing = set(pending) - found
    if missing:
        posts = arctic.posts_by_id(sorted(m[3:] for m in missing))
        if posts:
            db.insert_threads(conn, posts)
            found |= {"t3_" + p["id"] for p in posts}
    if not found:
        return 0
    print(f"  {len(found)} late post(s) arrived; pulling their threads")
    pull_threads(conn, {f[3:] for f in found})
    db.fill_tree(conn, found)
    for lid in found:
        pending.pop(lid, None)
    return len(found)


def poll_once(conn, subreddit, seen, orphans=None):
    """Fetch, store, and move this subreddit's overlap point forward.

    `seen` maps subreddit -> newest created_utc a poll has fetched. It is
    the poller's own memory, not max(created_utc) in the table, because other
    writers move that: pulling a newly found thread stores replies newer than
    the poll's page, and the background backfill pages up to the present.
    Paging back only to their newest would skip whatever arrived elsewhere
    in between. At boot there is no memory yet, so the first poll starts
    from the table; the boot backfill is what closes a gap from before it.
    It moves only after the insert, so a poll that fails pages back again.

    `orphans` maps subreddit -> {thread id: when first dropped}, the threads
    whose post had not reached the archive yet; each poll looks for them again.
    """
    if subreddit not in seen:
        seen[subreddit] = db.newest_stored_utc(conn, subreddit)
    pending = None if orphans is None else orphans.setdefault(subreddit, {})
    comments = fetch_new(subreddit, seen[subreddit])
    print(f"r/{subreddit}: fetched {len(comments)} newest comments")
    if comments:
        new = store(conn, comments, pending)
        print(f"  inserted {new} new comment(s)")
        newest = max(c["created_utc"] for c in comments)
        seen[subreddit] = newest if seen[subreddit] is None else max(seen[subreddit], newest)
    # After the overlap point moved: a failure here is the orphans' alone.
    if pending:
        retry_orphans(conn, pending)


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


def resweep_once(conn, subreddit, hours=None, pending=None):
    """Read this city's last `hours` again, oldest first, and store what is missing.

    The poll's lag covers most late arrivals; this is for the rest, and for
    comments dropped because their post was late. Pages forward with
    arctic.forward, so no same-second comment falls between pages. Returns
    how many comments were new -- in the log, that is the poll's loss rate.
    """
    hours = RESWEEP_HOURS if hours is None else hours
    start = int(time.time() - hours * 3600)
    fetched = new = 0

    def fetch(after):
        return arctic.search_page("comments", subreddit, after=after)
    for fresh, page in arctic.forward(fetch, start, pause=1.0):
        fetched += len(fresh)
        new += store(conn, fresh, pending)
        if max(c["created_utc"] for c in page) >= time.time() - 60:
            break
    print(f"  re-swept r/{subreddit}'s last {hours:g}h: {fetched} comment(s), {new} were missing")
    return new


def disk_once(conn):
    """Log the database's size every chores pass, and warn past the backfill's limit.

    The Railway volume is 5,000 MB and holds the WAL too. Past
    BACKFILL_MAX_DB_MB the backfill stops sweeping other cities (backfill.py);
    polling goes on, because missing comments are worse than a full disk
    warning, and a person has to decide what gives.
    """
    import backfill

    size, limit = db.database_size_mb(conn), backfill.max_db_mb()
    flag = "  <- OVER BACKFILL_MAX_DB_MB; other cities' backfill is stopped" if size > limit else ""
    print(f"  database {size:,.0f} MB (backfill limit {limit:,.0f} MB){flag}")
    return size


class Resweep:
    """Which cities the chores pass re-sweeps, and when each was last done."""

    def __init__(self, names, orphans, hours=None, every=None):
        self.names, self.orphans = list(names), orphans
        self.hours = RESWEEP_HOURS if hours is None else hours
        self.every = RESWEEP_EVERY if every is None else every
        self.last = {}

    def due(self, now=None):
        now = time.time() if now is None else now
        return [n for n in self.names if now - self.last.get(n, 0) >= self.every]


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


def extract_v6_once(conn, days, limit, workers, max_usd):
    """extract_once for EXTRACT_VERSION=v6: new r/FoodNYC comments, then posts,
    through the benchmarked v6 prompt with direct calls at effort medium.

    Same window and limit as the old path, plus a spend cap per pass. A
    request the API refuses outright (a 4xx other than 429: a bad parameter,
    a dead key, no credit) stops the pass loudly and marks nothing, and so
    does an outage that outlasts the backoff; the next pass tries again.
    Whatever was stored before the stop still counts.
    """
    import anthropic_v6
    import extract_v6

    if not extract_v6.schema_ready(conn):
        print("  extract v6: tables missing -- apply extract_v6_schema.sql; skipping")
        return 0
    if not extract_v6.try_lock(conn):
        # A manual extract_v6.py run (the backfill, say) holds it; both would
        # pick the same due items and pay for them twice.
        print("  extract v6: another v6 run holds the lock; skipping this pass")
        return 0
    budget = extract_v6.Budget(max_usd)
    stats = extract_v6.Stats()
    cl = anthropic_v6.client(anthropic_v6.api_key())
    since = _since(conn, days)
    # Posts first, with a tenth of the limit: a busy hour of comments would
    # otherwise take the whole limit every pass and posts would never run.
    post_limit = max(1, limit // 10)
    try:
        extract_v6.run_direct(conn, cl, budget, kinds=("post",), limit=post_limit, since=since,
                              workers=workers, stats=stats)
        extract_v6.run_direct(conn, cl, budget, kinds=("comment",), limit=max(limit - stats.done, 0),
                              since=since, workers=workers, stats=stats)
    except anthropic_v6.FatalAPIError as e:
        print(f"  EXTRACTION STOPPED -- the API rejected the request itself, nothing was marked: {e}")
    except anthropic_v6.TransientAPIError as e:
        print(f"  extract v6 stopped early, will retry next pass: {e}")
    finally:
        extract_v6.unlock(conn)
    if stats.done or stats.failed or stats.refused:
        print(f"  extract v6: {stats.line()}")
    return stats.done


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
    """A clean connection after a failed step (db.recover): rolled back, or new."""
    return db.recover(conn)


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


def poll_due(conn, names, due, seen, orphans=None):
    """Poll every subreddit whose time has come, then set its next due time.

    A failed poll still gets a next time, the shortest one: retrying at once
    would spin on an outage, and waiting a full interval would leave a busy
    city stale. Returns the connection to carry on with.
    """
    for name in names:
        if due[name] > time.time():
            continue
        extra = () if orphans is None else (orphans,)
        _, conn = _step(f"poll r/{name}", poll_once, conn, name, seen, *extra)
        wait, conn = _step(f"interval r/{name}", interval_for, conn, name)
        due[name] = time.time() + (wait or MIN_INTERVAL)
    return conn


def run_chores(conn, args):
    """The 30-minute pass: log the disk, settle, re-sweep, extract, refresh, embed.

    Each step gets its own try. A failed extraction must not look like a
    failed settle, and a failed settle still leaves earlier arrivals worth
    extracting. Embedding is strictly optional, so it goes last: the board
    is refreshed before it starts, and an embedding error or a slow
    OpenRouter can never delay extraction or the refresh.

    Every step here is r/FoodNYC's except settling and the re-sweep, which
    are every polled city's:
    extraction reads HOME only, and embedding reads what extraction wrote
    plus HOME's threads, so the other cities' history is never billed.
    Returns the connection to carry on with.
    """
    _, conn = _step("disk", disk_once, conn)
    _, conn = _step("settle", settle_once, conn)
    resweep = getattr(args, "resweep", None)
    if resweep is not None:
        for name in resweep.due():
            _, conn = _step(f"re-sweep r/{name}", resweep_once, conn, name, resweep.hours,
                            resweep.orphans.setdefault(name, {}))
            # Failed or not, wait a full interval: retrying at once would
            # spin on an archive outage, and the next poll pages back anyway.
            resweep.last[name] = time.time()
    extracted = 0
    if args.extract and getattr(args, "extract_version", "legacy") == "v6":
        extracted, conn = _step("extract", extract_v6_once, conn, args.extract_days,
                                args.extract_limit, args.extract_workers, args.extract_max_usd)
    elif args.extract:
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
                    help="poll only this one, and backfill it if BACKFILL_SUBREDDITS and "
                         "BACKFILL_YEARS_OTHER allow (repeatable; default: $POLL_SUBREDDITS)")
    ap.add_argument("--no-rss", action="store_true",
                    help="do not run the RSS fallback collector")
    ap.add_argument("--no-backfill", action="store_true",
                    help="start polling immediately, skipping the catch-up sweep")
    ap.add_argument("--backfill-years", type=float, default=0,
                    help="limit r/FoodNYC's catch-up sweep to the last N years (default: all "
                         "time); other cities take $BACKFILL_YEARS_OTHER (backfill.scope)")
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
    ap.add_argument("--extract-max-usd", type=float,
                    default=float(os.environ.get("POLL_EXTRACT_MAX_USD", "1.00")),
                    help="v6 only: spend cap per 30-min pass ($POLL_EXTRACT_MAX_USD, default 1.00)")
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

    # Which extractor the chores pass runs. Unset means the old one, so
    # deploying the v6 code changes nothing until the owner sets
    # EXTRACT_VERSION=v6 (docs/handoffs/extraction-v6.md).
    args.extract_version = os.environ.get("EXTRACT_VERSION", "").strip().lower() or "legacy"
    if args.extract_version not in ("legacy", "v6"):
        raise SystemExit(f"EXTRACT_VERSION={args.extract_version!r} is not legacy or v6")

    if args.extract and args.extract_version == "v6":
        import anthropic_v6
        import prompt_v6
        # Fail the deploy, like the old path: without a key every pass would
        # stop on its first request.
        if not anthropic_v6.api_key():
            raise SystemExit(f"EXTRACT_VERSION=v6 needs {anthropic_v6.KEY_VAR}")
        print(f"inference on: v6 ({prompt_v6.MODEL}, effort {prompt_v6.EFFORT}, prompt "
              f"{prompt_v6.PROMPT_HASH}/{prompt_v6.PROMPT_HASH_POST}), r/{subreddits.HOME} comments "
              f"and posts from the last {args.extract_days}d, <= {args.extract_limit}/cycle, "
              f"<= ${args.extract_max_usd:.2f}/cycle, {args.extract_workers} workers")
    elif args.extract:
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

    if args.extract and args.extract_version == "v6":
        import extract_v6
        if extract_v6.read_version(conn) != "v6":
            # Legal, but it means the board gets no new mentions: the old
            # extractor is off and the board still reads the old rows.
            print("WARNING: EXTRACT_VERSION=v6 but the board still reads legacy mentions, so new "
                  "comments will not reach it until `extract_v6.py --read v6`")

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

    # Which cities are polled, and which are swept. Polling a city stores
    # what it says from now on, ~2,500 comments a day for the six beyond
    # r/FoodNYC (about 2.3 MB a day, under 1 GB a year). Sweeping its history
    # is ~3.5M comments for the six, which the volume cannot hold today, so
    # that is opt-in (backfill.scope).
    names = args.subreddit or subreddits.parse(os.environ.get("POLL_SUBREDDITS"),
                                               subreddits.SUBREDDITS)
    print(f"polling {', '.join('r/' + n for n in names)}")
    orphans = {}

    if not args.no_backfill:
        import backfill
        sweep, years = backfill.scope(args.backfill_years or None, only=args.subreddit)
        depth = [f"r/{n} ({years[n] or 'all'} years)" for n in sweep]
        print(f"backfill: {', '.join(depth) or 'none'}; "
              f"stops other cities past {backfill.max_db_mb():,.0f} MB")
        if args.rescan:
            db.clear_cursors(conn, sweep)
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
            backfill.run_all(conn, sweep, years, rounds=2)
            conn = _recover(conn)        # run_all may have had to replace it
        else:
            backfill.start_background(sweep, years)
            print(f"backfill sweeping {len(sweep)} subreddit(s) in the background")

    # Everything is due at boot.
    due = dict.fromkeys(names, 0.0)
    seen = {}
    # The re-sweep waits one interval after boot. r/FoodNYC's backfill and
    # every city's first polls already read the recent hours, and for a city
    # new to the table a sweep now would pull every thread of its last two
    # days at once, holding up the polls behind it.
    args.resweep = Resweep(names, orphans)
    args.resweep.last = dict.fromkeys(names, time.time())
    chores_due = 0.0
    while True:
        conn = poll_due(conn, names, due, seen, orphans)
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
