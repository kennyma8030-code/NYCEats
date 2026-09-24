"""Connection pooling and row helpers for the API.

The old api.py opened a fresh Postgres connection on every request and closed
it again -- a TCP handshake, a TLS negotiation and a backend fork per
leaderboard load, which over a network link is most of the response time.

Pools are PER PROCESS. `uvicorn --workers N` forks N separate processes, each
with its own pool, so the real connection count against Postgres is
N * POOL_MAX. Size that against the database's max_connections with room left
for poller.py and an extract.py run, both of which want connections too.

Endpoints are sync `def`, not `async def`. Starlette runs those in its anyio
threadpool (40 by default), and psycopg2 releases the GIL while it waits
inside libpq -- so the threads genuinely overlap instead of queueing. An
`async def` holding a blocking psycopg2 call would stall the whole event loop
and every other request sharing the process.
"""

import os
from contextlib import contextmanager

from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

import db as pipeline_db          # DATABASE_URL + the .env loader already live there

POOL_MIN = int(os.environ.get("DB_POOL_MIN", "1"))
POOL_MAX = int(os.environ.get("DB_POOL_MAX", "10"))

_pool = None


def open_pool():
    """Called once from the app lifespan. Idempotent."""
    global _pool
    if _pool is None:
        if not pipeline_db.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not set (add it to .env, or set it in Railway)")
        _pool = ThreadedConnectionPool(POOL_MIN, POOL_MAX, pipeline_db.DATABASE_URL)
    return _pool


def close_pool():
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def connection():
    """Check a connection out of the pool and always put it back.

    autocommit is on: every read endpoint is a single statement, and leaving
    an implicit transaction open would park the connection 'idle in
    transaction' until the next request reused it -- which pins a snapshot and
    makes REFRESH MATERIALIZED VIEW CONCURRENTLY wait behind it.
    """
    pool = open_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        yield conn
    except Exception:
        # Under autocommit a failed statement leaves the session usable, but
        # roll back anyway so a half-open explicit transaction cannot leak
        # back into the pool for the next request to inherit.
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        pool.putconn(conn)


def get_conn():
    """FastAPI dependency. Yields a pooled connection for one request."""
    with connection() as conn:
        yield conn


def fetch_all(conn, sql, params=()):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def fetch_one(conn, sql, params=()):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_value(conn, sql, params=(), default=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else default
