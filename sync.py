"""Push locally-extracted results up to Railway.

Extraction runs locally -- it is easier to watch, interrupt and restart there,
and it is where the API key lives. Production collects comments, and with
inference switched on (deploy.py) extracts only the last few days of them. So
the backlog's extraction output is what has to travel, not the corpus:

    mentions              what the model found
    comments.extracted_at which comments are done, so nothing is redone
    alias_overrides       the identity decisions a person made

Comments themselves are NOT copied. Both databases fill from Arctic Shift and
the backfill cursor makes them converge on their own -- copying 750k rows
across the public proxy to reach the same state is work for nothing.

This talks to both databases with psycopg2 rather than shelling out to
pg_dump, which sidesteps the client-version problem entirely: local Postgres
is 16 and Railway is 18, and pg_dump refuses to read a newer server.

    python sync.py --dry-run     say what would move
    python sync.py               move it, then rebuild the views
"""

import argparse
import os
import time

import psycopg2
from psycopg2.extras import Json, execute_values

import db

BATCH = 5000

MENTION_COLS = ("comment_id", "restaurant_raw", "entity_key", "entity_id",
                "neighborhood_hint", "dishes", "descriptors", "aspects",
                "expensiveness", "is_firsthand", "is_negated",
                "model_version", "prompt_hash")


def remote_url(explicit=None):
    url = explicit or os.environ.get("RAILWAY_DATABASE_URL")
    if not url:
        raise SystemExit(
            "No destination. Pass --to '<url>' or set RAILWAY_DATABASE_URL.\n"
            "  railway variable list --service Postgres --kv | grep DATABASE_PUBLIC_URL")
    return url


def counts(cur):
    cur.execute("""select (select count(*) from comments),
                          (select count(*) from comments where extracted_at is not null),
                          (select count(*) from mentions)""")
    return cur.fetchone()


def push_mentions(loc, rem, dry_run):
    """id is deliberately not sent -- production assigns its own.

    The unique index on (comment_id, entity_key, prompt_hash) is what makes
    this idempotent, so re-running after a bigger extraction only adds the new
    rows. Carrying local ids across would invite a collision for no benefit.

    Comments production has already extracted are skipped. The poller can run
    inference itself now (poller.py --extract), and the model is not
    deterministic: the same comment extracted on both sides can come back as
    "katzs" here and "katzs deli" there, which the unique index would let
    through as two mentions of one opinion. Whichever side got there first
    owns the comment.
    """
    lc, rc = loc.cursor(), rem.cursor()
    rc.execute("select id from comments where extracted_at is not null")
    owned = {r[0] for r in rc.fetchall()}
    lc.execute(f"select {', '.join(MENTION_COLS)} from mentions order by id")
    total = new = skipped = 0
    while True:
        rows = lc.fetchmany(BATCH)
        if not rows:
            break
        total += len(rows)
        kept = [r for r in rows if r[0] not in owned]
        skipped += len(rows) - len(kept)
        rows = kept
        if dry_run or not rows:
            continue
        rows = [tuple(Json(v) if isinstance(v, (dict, list)) and c == "aspects" else v
                      for c, v in zip(MENTION_COLS, r)) for r in rows]
        inserted = execute_values(rc, f"""
            insert into mentions ({', '.join(MENTION_COLS)})
            values %s
            on conflict (comment_id, entity_key, prompt_hash) do nothing
            returning id
        """, rows, fetch=True)
        new += len(inserted)
        rem.commit()
        print(f"  mentions {total:,} sent, {new:,} new", flush=True)
    return total, new, skipped


def push_flags(loc, rem, dry_run):
    """Which comments are already extracted.

    Without these production would treat every comment as pending, and any
    extraction run started there would pay for work already done.
    """
    lc, rc = loc.cursor(), rem.cursor()
    lc.execute("select id, extracted_at, extracted_with from comments "
               "where extracted_at is not null order by id")
    total = 0
    if not dry_run:
        rc.execute("""create temp table _flags (
                        id text primary key, extracted_at timestamptz,
                        extracted_with text) on commit drop""")
    while True:
        rows = lc.fetchmany(BATCH)
        if not rows:
            break
        total += len(rows)
        if not dry_run:
            execute_values(rc, "insert into _flags (id, extracted_at, extracted_with) "
                               "values %s on conflict (id) do nothing", rows)
    if not dry_run and total:
        # Only comments production actually has; the two corpora drift by a few
        # hundred rows and a missing one is not an error, just not there yet.
        rc.execute("""update comments c
                      set extracted_at = f.extracted_at,
                          extracted_with = f.extracted_with,
                          extract_error = null
                      from _flags f
                      where c.id = f.id and c.extracted_at is null""")
        updated = rc.rowcount
        rem.commit()
        return total, updated
    return total, 0


def push_overrides(loc, rem, dry_run):
    lc, rc = loc.cursor(), rem.cursor()
    lc.execute("select entity_key, resolved_key, note from alias_overrides")
    rows = lc.fetchall()
    if rows and not dry_run:
        execute_values(rc, """
            insert into alias_overrides (entity_key, resolved_key, note)
            values %s
            on conflict (entity_key) do update
              set resolved_key = excluded.resolved_key, note = excluded.note
        """, rows)
        rem.commit()
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", metavar="URL", help="destination (default: $RAILWAY_DATABASE_URL)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-refresh", action="store_true",
                    help="skip rebuilding the scoring views afterwards")
    args = ap.parse_args()

    loc = db.connect()
    rem = psycopg2.connect(remote_url(args.to))
    began = time.time()

    lcm, lex, lmn = counts(loc.cursor())
    rcm, rex, rmn = counts(rem.cursor())
    print(f"{'':10s}{'comments':>12s}{'extracted':>12s}{'mentions':>12s}")
    print(f"{'local':10s}{lcm:>12,}{lex:>12,}{lmn:>12,}")
    print(f"{'railway':10s}{rcm:>12,}{rex:>12,}{rmn:>12,}\n")

    if not args.dry_run:
        # schema.sql is create-if-not-exists throughout, and the mentions
        # unique index has to exist before ON CONFLICT can name it.
        db.init(rem, os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql"))

    sent, new, skipped = push_mentions(loc, rem, args.dry_run)
    print(f"mentions:  {sent:,} local, {new:,} new, "
          f"{skipped:,} skipped (comment already extracted on railway)")
    fsent, fupd = push_flags(loc, rem, args.dry_run)
    print(f"flags:     {fsent:,} sent, {fupd:,} comments marked extracted")
    print(f"overrides: {push_overrides(loc, rem, args.dry_run)}")

    if args.dry_run:
        print("\ndry run -- nothing written")
        return

    if not args.no_refresh:
        print("\nrebuilding the scoring layer on railway")
        import refresh
        refresh.apply_sql(rem)
        refresh.refresh_views(rem)

    rcm, rex, rmn = counts(rem.cursor())
    print(f"\nrailway now: {rcm:,} comments, {rex:,} extracted, {rmn:,} mentions "
          f"({(time.time() - began) / 60:.1f} min)")


if __name__ == "__main__":
    main()
