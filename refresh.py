"""Build and refresh the scoring layer.

Until this existed, scoring.sql and resolve.sql were applied by hand. That is
why production has no scoring views at all and why mention_weights sat at
13,328 rows against 13,651 in mentions -- the numbers on the board were a
snapshot of whenever someone last remembered.

Two jobs, deliberately separate:

  apply    re-run the view definitions. Safe any time: every statement is
           create-or-replace or guarded, so it is how a fresh database gets
           a scoring layer and how a changed scoring.sql reaches an old one.
  refresh  recompute the three materialized views from current data.

Order is not optional. mention_weights reads entity_alias, and the momentum
views read mention_weights, so refreshing out of order silently scores new
mentions against yesterday's identities.

    python refresh.py            -> refresh the materialized views
    python refresh.py --apply    -> re-run the SQL, then refresh
"""

import argparse
import os
import time

import db

HERE = os.path.dirname(os.path.abspath(__file__))

# Applied in order: resolve.sql's view reads restaurants, scoring.sql's views
# read each other. Both are create-or-replace throughout.
SQL_FILES = ("scoring.sql", "resolve.sql")

# (name, can_refresh_concurrently). CONCURRENTLY needs a unique index and
# keeps the view readable while it rebuilds; momentum_windows has no unique
# key to give it one, and it is small, so it takes the lock.
#
# entity_leaderboard is LAST and must stay last: it reads every other view in
# this tuple, so refreshing it first would serve the API a board built from
# the previous run's identities and weights.
VIEWS = (("entity_alias", True),
         ("mention_weights", True),
         ("momentum_windows", False),
         ("mention_resolution", True),
         ("entity_leaderboard", True))


def apply_sql(conn, verbose=True):
    """Re-run the view definitions. Idempotent."""
    for name in SQL_FILES:
        path = os.path.join(HERE, name)
        began = time.time()
        with open(path, encoding="utf-8") as f:
            sql = f.read()
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        if verbose:
            print(f"  applied {name} ({time.time() - began:.1f}s)", flush=True)


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


def run(conn, apply_first=False, verbose=True):
    """What extract.py calls when a run finishes and the numbers have moved."""
    if apply_first:
        apply_sql(conn, verbose)
    refresh_views(conn, verbose)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="re-run scoring.sql and resolve.sql before refreshing")
    args = ap.parse_args()

    conn = db.connect()
    began = time.time()
    run(conn, apply_first=args.apply)

    with conn.cursor() as cur:
        cur.execute("""select (select count(*) from mentions),
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
