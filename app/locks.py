"""The Postgres advisory lock that serialises scoring-view refreshes.

A threading.Lock only stops two refreshes in one process, and production
runs two uvicorn workers. Today ONLY /api/admin/refresh takes this lock, so
what it guarantees is one admin refresh at a time across the web workers.
It does not yet hold off refresh.py, extract_v6.py or the poller, which
refresh without it; wiring them to the same key belongs to the branch that
owns those scripts.

Kept free of app imports so those scripts can take it with
`from app.locks import REFRESH_LOCK_KEY, try_lock, unlock` once they do.
"""

# The ASCII bytes "nycRefsh": 0x6E796352_65667368 = 7960503021893743464.
# Keep this value stable: it is shared by every process that refreshes, and
# two processes holding different keys would each think they ran alone.
REFRESH_LOCK_KEY = 0x6E796352_65667368


def try_lock(conn, key=REFRESH_LOCK_KEY):
    """Take a session-level advisory lock without waiting. True if taken.

    Session-level, not transaction-level, because a refresh commits after
    every view and must keep the lock across all of them.
    """
    with conn.cursor() as cur:
        cur.execute("select pg_try_advisory_lock(%s)", (key,))
        ok = cur.fetchone()[0]
    if not conn.autocommit:
        conn.commit()
    return ok


def unlock(conn, key=REFRESH_LOCK_KEY):
    if not conn.autocommit:
        conn.rollback()       # a failed statement may have left the transaction aborted
    with conn.cursor() as cur:
        cur.execute("select pg_advisory_unlock(%s)", (key,))
    if not conn.autocommit:
        conn.commit()
