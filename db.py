"""Postgres writes. Everything is idempotent: re-running inserts nothing new."""

import os

import psycopg2
from psycopg2.extras import Json, execute_values

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
    return psycopg2.connect(DATABASE_URL)


def init(conn, schema_path="schema.sql"):
    with open(schema_path, encoding="utf-8") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def existing_thread_ids(conn, thread_ids):
    if not thread_ids:
        return set()
    with conn.cursor() as cur:
        cur.execute("select id from threads where id = any(%s)", (list(thread_ids),))
        return {r[0] for r in cur.fetchall()}


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
    ) for p in posts]
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
    for c in comments:
        parent = c["parent_id"]
        rows.append((
            "t1_" + c["id"],
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
        ))
    with conn.cursor() as cur:
        inserted = execute_values(cur, """
            insert into comments
              (id, thread_id, parent_id, parent_comment_id, author, body,
               permalink, created_utc, retrieved_on, score, controversiality)
            values %s
            on conflict (id) do nothing
            returning id
        """, rows, template="(%s,%s,%s,%s,%s,%s,%s,to_timestamp(%s),to_timestamp(%s),%s,%s)",
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
    with conn.cursor() as cur:
        cur.execute("""
            select id from comments
            where not score_settled
              and created_utc < now() - interval '36 hours'
            order by created_utc
            limit %s
        """, (limit,))
        return [r[0] for r in cur.fetchall()]


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


def get_cursor(conn, kind, default):
    with conn.cursor() as cur:
        cur.execute("select cursor_utc from backfill_progress where kind=%s", (kind,))
        row = cur.fetchone()
        return row[0] if row else default


def set_cursor(conn, kind, value):
    with conn.cursor() as cur:
        cur.execute("""
            insert into backfill_progress (kind, cursor_utc) values (%s, %s)
            on conflict (kind) do update
              set cursor_utc = excluded.cursor_utc, updated_at = now()
        """, (kind, int(value)))
    conn.commit()


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
