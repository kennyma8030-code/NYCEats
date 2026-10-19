"""Postgres advisory locks shared between the API and the pipeline.

A threading.Lock only stops two refreshes in one process. Production runs
two uvicorn workers and a poller that refreshes after every extraction, so
the one lock that means "a refresh is running" has to live in the database.

Kept free of app imports so a pipeline script (poller.py, refresh.py) can
take the same lock with `from app.locks import ...` -- the key is defined
here and nowhere else.
"""

# "nycR" "efsh": any 64-bit constant works, as long as everything that
# refreshes the scoring views uses this one.
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
