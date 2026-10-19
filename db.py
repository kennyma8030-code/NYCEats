"""Postgres writes. Everything is idempotent: re-running inserts nothing new."""

import os
import time
import traceback

import psycopg2
import psycopg2.errors
from psycopg2.extras import Json, execute_values

import subreddits

def _load_dotenv(path=".env"):
    """Minimal .env reader so local runs don't need an exported variable."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")


def connect():
    if not DATABASE_URL:
        raise SystemExit(
            "DATABASE_URL is not set.\n"
            "  Railway: add a variable DATABASE_URL = ${{Postgres.DATABASE_URL}}\n"
            "  Local:   export DATABASE_URL=postgresql://postgres:dev@localhost:5433/foodnyc"
        )
    # TCP keepalives, because the poller's one connection sits idle for
    # minutes at a time -- between polls, and while extraction or embedding
    # waits on an API -- and a proxy in front of Railway's Postgres can drop
    # an idle connection silently. Probing every 30s keeps it open, and a
    # dead one is noticed within a minute instead of hanging the next query.
    return psycopg2.connect(DATABASE_URL, keepalives=1, keepalives_idle=30,
                            keepalives_interval=10, keepalives_count=3)


def has_column(conn, table, column):
    """Whether a column exists, for scripts that must run on either side of a
    migration (extract_v6_schema.sql adds mentions.schema_version/thread_id)."""
    return bool(_read(conn, """select 1 from information_schema.columns
                               where table_schema = current_schema()
                                 and table_name = %s and column_name = %s""", (table, column)))


# How long a boot's DDL may wait for a lock before giving up, and how long it
# then waits before trying again. A worker that is still running the old code
# can sit "idle in transaction" holding a lock on comments for minutes; with
# no timeout the boot would queue behind it forever, and every board read of
# comments would queue behind the boot. Giving up after 5 s and retrying
# keeps the board readable, and the retries outlast a short holdup. If the
# holder never lets go the boot fails loudly and Railway restarts it.
LOCK_TIMEOUT = "5s"
LOCK_RETRY_WAITS = (10, 30, 60, 120)


def _lock_holders(conn):
    """The oldest other open transactions, for the log line on a lock timeout.

    By the time this runs our own transaction has rolled back, so there is
    no waiting lock left to ask pg_blocking_pids about. The holder is almost
    always the oldest open transaction -- an old worker idle in one, or a
    long refresh -- so that is what gets named.
    """
    try:
        rows = _read(conn, """
            select pid, state, coalesce(application_name, ''),
                   extract(epoch from now() - xact_start)::int
            from pg_stat_activity
            where datname = current_database() and pid <> pg_backend_pid()
              and xact_start is not null
            order by xact_start limit 3""", ())
    except Exception:
        conn.rollback()
        return "unknown"
    return ", ".join(f"pid {p} {s} for {age}s {app}".strip() for p, s, app, age in rows) or "none now"


def with_lock_retry(conn, what, fn, waits=LOCK_RETRY_WAITS, log=print):
    """Run fn(cursor) in one transaction with LOCK_TIMEOUT, retrying on a lock timeout.

    The transaction is all or nothing, so a timeout leaves nothing half
    applied, and the retry starts from scratch. Anything other than a lock
    timeout is raised at once: retrying a broken file would only hide it.
    """
    for attempt in range(len(waits) + 1):
        try:
            with conn.cursor() as cur:
                cur.execute("select set_config('lock_timeout', %s, true)", (LOCK_TIMEOUT,))
                fn(cur)
            conn.commit()
            return
        except psycopg2.errors.LockNotAvailable as e:
            conn.rollback()
            if attempt == len(waits):
                log(f"{what}: still waiting for a lock after {attempt + 1} tries, giving up. "
                    f"Holders: {_lock_holders(conn)}")
                raise
            # The first CONTEXT line names the statement that waited.
            lines = str(e).strip().splitlines()
            where = next((ln.replace("CONTEXT:", "").strip() for ln in lines
                          if ln.startswith("CONTEXT:")), lines[0] if lines else "")
            log(f"{what}: lock wait over {LOCK_TIMEOUT} at {where[:160]}; "
                f"holders: {_lock_holders(conn)}; retrying in {waits[attempt]}s")
            time.sleep(waits[attempt])


def init(conn, schema_path="schema.sql", waits=LOCK_RETRY_WAITS):
    """Apply schema.sql (or another schema file) in one transaction.

    schema.sql runs on every boot, so it is written to take no lock on
    comments, threads or mentions once the database is current. A boot that
    does need one (the first after a migration) waits at most LOCK_TIMEOUT
    for it and retries, rather than hanging behind an older worker.
    """
    with open(schema_path, encoding="utf-8") as f:
        sql = f.read()
    with_lock_retry(conn, f"apply {os.path.basename(schema_path)}",
                    lambda cur: cur.execute(sql), waits)


def recover(conn, log=print):
    """A clean connection after a failed step: rolled back, or a new one.

    A step can fail because the connection itself went (a Postgres restart,
    a dropped proxy). Rolling back a closed connection raises, and raising
    here would end the poller, the backfill thread or the RSS thread over
    something the next cycle can survive. So reconnect instead; if even that
    fails, hand back the dead one (or None) and let the next step try again.
    Never raises.
    """
    try:
        if conn is not None and not conn.closed:
            conn.rollback()
            return conn
    except Exception:
        traceback.print_exc()
    log("  database connection lost -- reconnecting")
    try:
        return connect()
    except Exception:
        traceback.print_exc()
        log("  reconnect failed; the next step will try again")
        return conn


def database_size_mb(conn):
    """The database's size on disk, in MB, as Postgres counts it (no WAL)."""
    return float(_read(conn, "select pg_database_size(current_database()) / 1048576.0", ())[0][0])


def _read(conn, sql, params):
    """Run one read and end its transaction before returning the rows.

    psycopg2 opens a transaction on the first statement and keeps it until a
    commit. The poller reads, then sleeps for up to an hour; left open, that
    read parks the connection "idle in transaction", holding a lock on
    comments and a snapshot that holds back vacuum and makes a concurrent
    refresh wait. Every read helper the long-lived loops call goes through
    here so none of them can leave one behind.
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.commit()
    return rows


def existing_thread_ids(conn, thread_ids):
    if not thread_ids:
        return set()
    rows = _read(conn, "select id from threads where id = any(%s)", (list(thread_ids),))
    return {r[0] for r in rows}


def insert_threads(conn, posts):
    if not posts:
        return 0
    rows = [(
        "t3_" + p["id"],
        p["subreddit"],
        p.get("title") or "",
        p.get("selftext"),
        p.get("author"),
        p["created_utc"],
        p.get("score"),
        p.get("upvote_ratio"),
        p.get("num_comments"),
        p.get("retrieved_on"),
    # Sorted so two writers inserting overlapping batches take row locks in the
    # same order. The poller and its background backfill both insert threads,
    # and unsorted batches can deadlock each other.
    ) for p in sorted(posts, key=lambda p: p["id"])]
    with conn.cursor() as cur:
        inserted = execute_values(cur, """
            insert into threads
              (id, subreddit, title, selftext, author, created_utc,
               score, upvote_ratio, num_comments, retrieved_on)
            values %s
            on conflict (id) do nothing
            returning id
        """, rows, template="(%s,%s,%s,%s,%s,to_timestamp(%s),%s,%s,%s,to_timestamp(%s))",
            fetch=True)
        # execute_values pages internally, so cur.rowcount would only report the
        # last page. RETURNING + fetch gives the true total.
        n = len(inserted)
    conn.commit()
    return n


def insert_comments(conn, comments):
    if not comments:
        return 0
    rows = []
    # Sorted for the same reason as insert_threads: a consistent lock order.
    for c in sorted(comments, key=lambda c: c["id"]):
        parent = c["parent_id"]
        rows.append((
            "t1_" + c["id"],
            c["subreddit"],
            c["link_id"],                                  # already t3_-prefixed
            parent,
            parent if parent.startswith("t1_") else None,   # null when top-level
            c.get("author"),
            c.get("body") or "",
            c.get("permalink") or "",
            c["created_utc"],
            c.get("retrieved_on"),
            c.get("score"),
            c.get("controversiality"),
            c["created_utc"],
        ))
    with conn.cursor() as cur:
        inserted = execute_values(cur, """
            insert into comments
              (id, subreddit, thread_id, parent_id, parent_comment_id, author, body,
               permalink, created_utc, retrieved_on, score, controversiality,
               score_settled)
            values %s
            on conflict (id) do nothing
            returning id
        """, rows,
            # A comment already past 36h when it arrives came from the archive,
            # whose score has had its 36h -- there is nothing left to settle.
            template="(%s,%s,%s,%s,%s,%s,%s,%s,to_timestamp(%s),to_timestamp(%s),%s,%s,"
                     "to_timestamp(%s) < now() - interval '36 hours')",
            fetch=True)
        n = len(inserted)
    conn.commit()
    return n


ASPECTS = ("food", "value", "service", "atmosphere", "wait")


def _score(v):
    """A -1..1 number, or None. The model is asked for one and mostly obliges.

    It does not always: a run died on `"expensiveness": "cheaper"`, because
    that column is a real and Postgres rejected the word. The prompt cannot be
    made to guarantee a type, so the writer enforces it. Out-of-range values
    are clamped rather than dropped -- 1.5 means emphatic, not missing.
    """
    if v is None or isinstance(v, bool):
        return None
    try:
        return max(-1.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None


def insert_mentions(conn, comment_id, mentions, model_version, prompt_hash):
    """One comment's extraction. `entity_key` is set by the caller -- extract.py
    owns normalization, this only writes what it is handed.

    No conflict clause: `mentions` is append-only and has no natural key, so a
    re-extraction is meant to add rows, not replace them.
    """
    if not mentions:
        return 0
    rows = []
    for m in mentions:
        aspects = m.get("aspects") or {}
        rows.append((
            comment_id,
            m["restaurant_raw"],
            m["entity_key"],
            m.get("neighborhood_hint"),
            Json(m.get("dishes") or []),
            Json(m.get("descriptors") or []),
            # Pin the five keys so a model that invents a sixth, or drops one,
            # still produces the same shape for every row downstream reads.
            Json({k: _score(aspects.get(k)) for k in ASPECTS}),
            _score(m.get("expensiveness")),
            m.get("is_firsthand"),
            bool(m.get("is_negated")),
            model_version,
            prompt_hash,
        ))
    with conn.cursor() as cur:
        inserted = execute_values(cur, """
            insert into mentions
              (comment_id, restaurant_raw, entity_key, neighborhood_hint,
               dishes, descriptors, aspects, expensiveness, is_firsthand,
               is_negated, model_version, prompt_hash)
            values %s
            -- Must match mentions_unique_idx exactly. Keyed on entity_key,
            -- not restaurant_raw: one comment can spell a name three ways
            -- ("l'industrie", "l’industrie", "L'industrie") and those are
            -- one mention, not three.
            on conflict (comment_id, entity_key, prompt_hash) do nothing
            returning id
        """, rows, fetch=True)
        n = len(inserted)
    conn.commit()
    return n


def fill_tree(conn, thread_ids):
    """Recompute root_comment_id + depth for the threads we just touched.

    Run after inserting, so replies whose parent arrived in the same batch
    (or a later one) still get correct values.
    """
    if not thread_ids:
        return 0
    with conn.cursor() as cur:
        cur.execute("""
            with recursive tree as (
                select id, id as root, 0 as depth
                from comments
                where thread_id = any(%s) and parent_comment_id is null
              union all
                select c.id, t.root, t.depth + 1
                from comments c
                join tree t on c.parent_comment_id = t.id
                where c.thread_id = any(%s)
            )
            update comments c
            set root_comment_id = t.root, depth = t.depth
            from tree t
            where c.id = t.id
              and (c.root_comment_id is distinct from t.root
                   or c.depth is distinct from t.depth)
        """, (list(thread_ids), list(thread_ids)))
        n = cur.rowcount
    conn.commit()
    return n


def unsettled_comment_ids(conn, limit=100):
    """Comments past the 36h mark whose score we haven't finalised yet."""
    rows = _read(conn, """
        select id from comments
        where not score_settled
          and created_utc < now() - interval '36 hours'
        order by created_utc
        limit %s
    """, (limit,))
    return [r[0] for r in rows]


def settle_scores(conn, comments, missing_ids=()):
    with conn.cursor() as cur:
        if comments:
            execute_values(cur, """
                update comments c
                set score = v.score,
                    controversiality = v.controversiality,
                    score_settled = true
                from (values %s) as v(id, score, controversiality)
                where c.id = v.id
            """, [("t1_" + c["id"], c.get("score"), c.get("controversiality"))
                  for c in comments])
        # Asked for but not returned = gone from the archive. Mark settled and
        # flag it, so the UI never links a permalink that 404s.
        if missing_ids:
            cur.execute("""
                update comments
                set score_settled = true, was_deleted_later = true
                where id = any(%s)
            """, (list(missing_ids),))
    conn.commit()


def get_cursor(conn, subreddit, kind, default):
    rows = _read(conn, "select cursor_utc from backfill_cursors where subreddit=%s and kind=%s",
                 (subreddit, kind))
    return rows[0][0] if rows else default


def set_cursor(conn, subreddit, kind, value):
    with conn.cursor() as cur:
        cur.execute("""
            insert into backfill_cursors (subreddit, kind, cursor_utc) values (%s, %s, %s)
            on conflict (subreddit, kind) do update
              set cursor_utc = excluded.cursor_utc, updated_at = now()
        """, (subreddit, kind, int(value)))
    conn.commit()


def clear_cursors(conn, names):
    """Forget where these subreddits' sweeps stopped, so the next starts over.

    r/FoodNYC's old cursor goes too. schema.sql copies it into
    backfill_cursors whenever the row is missing, so leaving it would let the
    next boot quietly put back the very cursor this was asked to clear.
    """
    with conn.cursor() as cur:
        cur.execute("delete from backfill_cursors where subreddit = any(%s)", (list(names),))
        if subreddits.HOME in names:
            cur.execute("delete from backfill_progress")
    conn.commit()


def newest_stored_utc(conn, subreddit):
    """Unix time of the newest comment we hold for this subreddit, or None.

    The poller pages back until it reaches this, so one poll can never leave
    a hole however busy the hour was.
    """
    return _read(conn, """select extract(epoch from max(created_utc))::bigint
                          from comments where subreddit = %s""", (subreddit,))[0][0]


def oldest_stored_utc(conn, subreddit):
    """Unix time of the oldest comment we hold for this subreddit, or None."""
    return _read(conn, """select extract(epoch from min(created_utc))::bigint
                          from comments where subreddit = %s""", (subreddit,))[0][0]


def busiest_hour(conn, subreddit, days=7):
    """Most comments this subreddit posted in any one hour of the last `days`.

    Rides comments_sub_created_idx: a week is a few thousand rows per city.
    """
    return _read(conn, """
        select max(n) from (
          select count(*) as n from comments
          where subreddit = %s and created_utc > now() - make_interval(days => %s)
          group by date_trunc('hour', created_utc)
        ) h
    """, (subreddit, days))[0][0] or 0


def missing_thread_ids(conn, thread_ids):
    """Which of these t3_ ids are NOT in threads yet."""
    return set(thread_ids) - existing_thread_ids(conn, thread_ids)


# --- RSS fallback -----------------------------------------------------------
# Separate tables, separate functions. These exist so a Reddit-side record
# survives an Arctic Shift outage; nothing downstream reads them.

def insert_rss_threads(conn, threads):
    """threads: (id, title, permalink) tuples. Deduped by primary key."""
    if not threads:
        return 0
    with conn.cursor() as cur:
        inserted = execute_values(cur, """
            insert into rss_threads (id, title, permalink)
            values %s
            on conflict (id) do nothing
            returning id
        """, threads, fetch=True)
        n = len(inserted)
    conn.commit()
    return n


def insert_rss_comments(conn, comments):
    """The feed re-sends the same 25 comments every cycle; the key drops them."""
    if not comments:
        return 0
    rows = [(c["id"], c["thread_id"], c["author"], c["body"],
             c["created_utc"], c["permalink"]) for c in comments]
    with conn.cursor() as cur:
        inserted = execute_values(cur, """
            insert into rss_comments
              (id, thread_id, author, body, created_utc, permalink)
            values %s
            on conflict (id) do nothing
            returning id
        """, rows, fetch=True)
        n = len(inserted)
    conn.commit()
    return n
