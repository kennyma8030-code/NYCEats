"""Postgres writes. Everything is idempotent: re-running inserts nothing new."""

import os

import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/foodnyc")


def connect():
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
