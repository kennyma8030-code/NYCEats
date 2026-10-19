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

Forty threads and ten connections means a burst can have more requests than
connections. psycopg2's pool does not wait for one to come back: getconn
raises PoolError the moment all of them are out, which turned every burst
into a run of 500s. So checkout goes through a semaphore sized to the pool,
and a request waits up to POOL_TIMEOUT for a free connection before it is
told 503 (PoolTimeout), which a client can retry.
"""

import os
import threading
import time
from contextlib import contextmanager

import psycopg2
import psycopg2.extensions
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

import db as pipeline_db          # DATABASE_URL + the .env loader already live there

POOL_MIN = int(os.environ.get("DB_POOL_MIN", "1"))
POOL_MAX = int(os.environ.get("DB_POOL_MAX", "10"))
# How long a request waits for a connection before answering 503.
POOL_TIMEOUT = float(os.environ.get("DB_POOL_TIMEOUT", "5"))
# Every read endpoint is one statement over materialized views; one that runs
# for ten seconds is a bug or a pathological filter, and letting it run on
# holds a connection the next request needs.
STATEMENT_TIMEOUT_MS = int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "10000"))
# A connection idle in the pool longer than this is pinged before it is
# handed out. After a database restart every idle one is dead, and without
# the ping each would fail one real request on its way out of the pool.
PING_AFTER = float(os.environ.get("DB_PING_AFTER", "10"))

_pool = None
_slots = None
_lock = threading.Lock()


class PoolTimeout(Exception):
    """No connection came free within POOL_TIMEOUT. main.py answers 503."""


class _Conn(psycopg2.extensions.connection):
    """A connection that remembers when it was last known to work: when it
    was opened, then each time it went back to the pool."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.returned_at = time.monotonic()


def _options():
    """libpq `options` for every pooled connection: the statement timeout,
    on top of whatever options were already asked for.

    Passing `options` replaces PGOPTIONS rather than adding to it, and the
    local read-only run (CLAUDE.md) is PGOPTIONS='-c
    default_transaction_read_only=on'. Dropping that silently would let a
    local server write to production, so it is carried over.
    """
    dsn_opts = psycopg2.extensions.parse_dsn(pipeline_db.DATABASE_URL).get("options")
    existing = dsn_opts if dsn_opts is not None else os.environ.get("PGOPTIONS", "")
    return f"{existing} -c statement_timeout={STATEMENT_TIMEOUT_MS}".strip()


def open_pool():
    """Called once from the app lifespan. Idempotent."""
    global _pool, _slots
    with _lock:
        if _pool is None:
            if not pipeline_db.DATABASE_URL:
                raise RuntimeError(
                    "DATABASE_URL is not set (add it to .env, or set it in Railway)")
            # Keepalives as in pipeline db.connect: a proxy in front of
            # Railway's Postgres can drop an idle connection silently.
            _pool = ThreadedConnectionPool(
                POOL_MIN, POOL_MAX, pipeline_db.DATABASE_URL,
                connection_factory=_Conn, options=_options(),
                keepalives=1, keepalives_idle=30, keepalives_interval=10,
                keepalives_count=3)
            _slots = threading.BoundedSemaphore(POOL_MAX)
    return _pool


def close_pool():
    global _pool, _slots
    with _lock:
        if _pool is not None:
            _pool.closeall()
            _pool = None
            _slots = None


def _usable(conn):
    """Whether a pooled connection can still run a query.

    The local checks are free and catch a connection libpq already knows is
    broken. The ping costs a round trip, so it only runs on one that has sat
    idle long enough for the server to have gone away under it.
    """
    if conn.closed or conn.info.transaction_status == psycopg2.extensions.TRANSACTION_STATUS_UNKNOWN:
        return False
    if time.monotonic() - conn.returned_at < PING_AFTER:
        return True
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("select 1")
        return True
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        return False


def _checkout(pool):
    """A live connection from the pool, discarding dead ones on the way.

    Bounded by the pool size: every discard opens a replacement, and a pool
    of nothing but dead connections still ends after POOL_MAX tries.
    """
    for _ in range(POOL_MAX + 1):
        conn = pool.getconn()
        if _usable(conn):
            return conn
        pool.putconn(conn, close=True)
    return pool.getconn()


@contextmanager
def connection():
    """Check a connection out of the pool and always put it back.

    autocommit is on: every read endpoint is a single statement, and leaving
    an implicit transaction open would park the connection 'idle in
    transaction' until the next request reused it -- which pins a snapshot and
    makes REFRESH MATERIALIZED VIEW CONCURRENTLY wait behind it.
    """
    pool = open_pool()
    slots = _slots
    if not slots.acquire(timeout=POOL_TIMEOUT):
        raise PoolTimeout(f"no database connection free within {POOL_TIMEOUT:g}s")
    try:
        conn = _checkout(pool)
    except Exception:
        slots.release()
        raise
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
        conn.returned_at = time.monotonic()
        try:
            # A connection that died mid-request is closed rather than pooled.
            pool.putconn(conn, close=bool(conn.closed))
        finally:
            slots.release()


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
