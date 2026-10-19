"""Build and refresh the scoring layer.

Until this existed, scoring.sql and resolve.sql were applied by hand. That is
why production has no scoring views at all and why mention_weights sat at
13,328 rows against 13,651 in mentions -- the numbers on the board were a
snapshot of whenever someone last remembered.

Two jobs, deliberately separate:

  apply    re-run the view definitions. Safe any time: every statement is
           create-or-replace or guarded, so it is how a fresh database gets
           a scoring layer and how a changed scoring.sql reaches an old one.
           A file whose views already carry its hash is skipped, so a boot
           with nothing changed rebuilds nothing.
  refresh  recompute the three materialized views from current data.

Order is not optional. mention_weights reads entity_alias, and the momentum
views read mention_weights, so refreshing out of order silently scores new
mentions against yesterday's identities.

    python refresh.py            -> refresh the materialized views
    python refresh.py --apply    -> re-run the SQL that changed, then refresh
    python refresh.py --apply --force  -> re-run all of it, then refresh
"""

import argparse
import hashlib
import os
import re
import time

import db

HERE = os.path.dirname(os.path.abspath(__file__))

# Applied in order: resolve.sql's view reads restaurants, scoring.sql's views
# read each other, and scoring_v2.sql reads scoring.sql's -- which drop with
# CASCADE and take v2 along, so v2 must be re-applied after them every time.
SQL_FILES = ("scoring.sql", "scoring_v2.sql", "resolve.sql")

# (name, can_refresh_concurrently). CONCURRENTLY needs a unique index and
# keeps the view readable while it rebuilds; momentum_windows has no unique
# key to give it one, and it is small, so it takes the lock.
#
# entity_leaderboard comes after everything it reads, so refreshing it first
# would serve the API a board built from the previous run's identities and
# weights. entity_leaderboard_v2 reads it, so it is the one that is last.
VIEWS = (("entity_alias", True),
         ("mention_weights", True),
         ("mention_v2", True),
         ("momentum_windows", False),
         ("mention_resolution", True),
         ("entity_leaderboard", True),
         ("entity_leaderboard_v2", True))


_CREATES = re.compile(r"\bcreate\s+(?:or\s+replace\s+)?(?:materialized\s+)?view\s+"
                      r"(?:if\s+not\s+exists\s+)?([a-z_][a-z0-9_]*)", re.I)


def created_views(sql):
    """Every view and materialized view a file creates, in order."""
    names = _CREATES.findall(re.sub(r"--[^\n]*", "", sql))
    return list(dict.fromkeys(n.lower() for n in names))


def marker(name, sql):
    """The comment each view a file creates carries once that file is applied.

    Kept on the object itself rather than in a table of its own, so whatever
    rebuilds a view some other way -- an older worker's boot, a file run by
    hand, a CASCADE from the file before -- drops the marker with it, and the
    next apply notices and rebuilds.
    """
    return f"nyceats {name} sha256:{hashlib.sha256(sql.encode('utf-8')).hexdigest()[:16]}"


def _current(conn, name, sql):
    """Whether every view this file creates exists and carries its marker."""
    views = created_views(sql)
    found = dict(db._read(conn, """
        select c.relname, obj_description(c.oid, 'pg_class')
        from pg_class c
        where c.relnamespace = current_schema()::regnamespace and c.relname = any(%s)
    """, (views,)))
    return all(found.get(v) == marker(name, sql) for v in views)


def apply_sql(conn, verbose=True, force=False, waits=db.LOCK_RETRY_WAITS):
    """Re-run the view definitions that changed. Idempotent. Returns the files run.

    Every poller boot calls this. Rebuilding everything each time held the
    board's views dropped for over two minutes on production-sized data, so
    a file is skipped when every view it creates carries its current hash.
    From the first file that is not current on, every later file is re-run
    too: they read its views, which its re-run drops with CASCADE.

    The files that do run go in ONE transaction, so a view dropped in one
    file and recreated in the next is never missing as far as a reader can
    tell: board reads wait for the commit instead of failing with "relation
    does not exist". Lock waits are capped (db.LOCK_TIMEOUT) and the whole
    transaction retried, so a long refresh elsewhere delays a boot instead of
    freezing the board behind a DDL lock queued on it.
    """
    files = []
    for name in SQL_FILES:
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            files.append((name, f.read()))
    start = 0 if force else next(
        (i for i, (name, sql) in enumerate(files) if not _current(conn, name, sql)), len(files))
    todo = files[start:]
    if not todo:
        if verbose:
            print(f"  scoring SQL unchanged ({', '.join(SQL_FILES)}); nothing rebuilt", flush=True)
        return []

    def run(cur):
        for name, sql in todo:
            began = time.time()
            cur.execute(sql)
            cur.execute("""select relname, relkind from pg_class
                           where relnamespace = current_schema()::regnamespace
                             and relname = any(%s)""", (created_views(sql),))
            for view, kind in cur.fetchall():
                what = "materialized view" if kind == "m" else "view"
                cur.execute(f"comment on {what} {view} is %s", (marker(name, sql),))
            if verbose:
                print(f"  applied {name} ({time.time() - began:.1f}s)", flush=True)

    began = time.time()
    db.with_lock_retry(conn, "apply scoring SQL", run, waits)
    if verbose:
        print(f"  committed {len(todo)} scoring file(s) ({time.time() - began:.1f}s)", flush=True)
    return [name for name, _ in todo]


def refresh_views(conn, verbose=True):
    """Recompute the materialized views, in dependency order."""
    for name, concurrent in VIEWS:
        began = time.time()
        with conn.cursor() as cur:
            # A view that has never been populated cannot refresh CONCURRENTLY.
            cur.execute("select ispopulated from pg_matviews where matviewname = %s",
                        (name,))
            row = cur.fetchone()
            if row is None:
                if verbose:
                    print(f"  {name}: missing -- run --apply first", flush=True)
                continue
            how = "concurrently " if concurrent and row[0] else ""
            cur.execute(f"refresh materialized view {how}{name}")
        conn.commit()
        if verbose:
            print(f"  refreshed {name} ({time.time() - began:.1f}s)", flush=True)


def run(conn, apply_first=False, verbose=True, force=False):
    """What extract.py calls when a run finishes and the numbers have moved."""
    if apply_first:
        apply_sql(conn, verbose, force=force)
    refresh_views(conn, verbose)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="re-run whichever scoring files changed before refreshing")
    ap.add_argument("--force", action="store_true",
                    help="with --apply: re-run every scoring file, changed or not")
    args = ap.parse_args()

    conn = db.connect()
    began = time.time()
    run(conn, apply_first=args.apply, force=args.force)

    with conn.cursor() as cur:
        # live_mentions, not mentions: with two extractions side by side the
        # weights only ever cover the one the board reads.
        cur.execute("""select (select count(*) from live_mentions),
                              (select count(*) from mention_weights),
                              (select count(*) from entity_alias),
                              (select count(distinct resolved_key) from entity_alias),
                              (select count(*) from entity_leaderboard)""")
        m, w, a, r, lb = cur.fetchone()
    print(f"\nmentions {m:,} -> weights {w:,}"
          f"{'  <- STALE' if m != w else ''}")
    print(f"{a:,} typed names -> {r:,} restaurants ({a - r:,} merged)")
    print(f"leaderboard: {lb:,} rows   ({time.time() - began:.1f}s total)")


if __name__ == "__main__":
    main()
