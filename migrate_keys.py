"""Re-key stored rows after a normalize_entity change. Run once per change.

entity_key is derived, not source data -- mentions.restaurant_raw and
restaurants.name are what people and the city actually wrote. So when the
normalizer changes, every stored key is stale and has to be recomputed from
the text it came from, or old rows keep matching by the old rules while new
ones match by the new ones.

Two collision cases, both real:

  mentions        one comment can name a place twice with different spellings
                  that now collapse to one key. The unique index would reject
                  the second, so the duplicate row is deleted instead.
  restaurants     two licences whose names now normalize the same are one
                  restaurant. The table is rebuilt from the city list rather
                  than patched, because merging location counts and borough
                  arrays by hand is how you get a wrong answer quietly.

    python migrate_keys.py --dry-run     see what would change
    python migrate_keys.py               do it
"""

import argparse
import collections

import db
import extract
import restaurants


def plan_mentions(conn):
    """Which mention rows change key, and which become duplicates."""
    with conn.cursor() as cur:
        cur.execute("select id, comment_id, restaurant_raw, entity_key, prompt_hash "
                    "from mentions order by id")
        rows = cur.fetchall()

    seen, updates, deletes = {}, [], []
    for mid, comment_id, raw, old_key, prompt_hash in rows:
        new_key = extract.normalize_entity(raw)
        if not new_key:
            continue
        slot = (comment_id, new_key, prompt_hash)
        if slot in seen:
            deletes.append(mid)          # same comment, same place, two spellings
            continue
        seen[slot] = mid
        if new_key != old_key:
            updates.append((new_key, mid))
    return updates, deletes


def migrate_mentions(conn, dry_run=False):
    updates, deletes = plan_mentions(conn)
    print(f"mentions: {len(updates):,} re-keyed, {len(deletes):,} duplicates removed")
    if dry_run or not (updates or deletes):
        return
    with conn.cursor() as cur:
        # Deletes first: they are what frees the key the updates want.
        if deletes:
            cur.execute("delete from mentions where id = any(%s)", (deletes,))
        for new_key, mid in updates:
            cur.execute("update mentions set entity_key = %s where id = %s",
                        (new_key, mid))
    conn.commit()


def migrate_restaurants(conn, dry_run=False):
    """Re-key in place from restaurants.name -- no refetch.

    The city list is already stored, and `name` is the source text the key is
    derived from, so this needs no network. That matters: the Socrata endpoint
    answered 503 the first time this ran, and a migration that depends on a
    third party being up is a migration that half-finishes.

    Two licences whose names now normalize the same are one restaurant, so a
    collision merges: locations add, boroughs and addresses union, is_chain is
    true if either was. The longest name wins as the display name -- it is the
    one that carries "DELICATESSEN" rather than dropping it.
    """
    with conn.cursor() as cur:
        cur.execute("select id, name, name_key, cuisine, boroughs, location_count, "
                    "addresses, is_chain, closed, last_seen from restaurants")
        rows = cur.fetchall()

    merged = {}
    for (rid, name, _old, cuisine, boroughs, count, addresses,
         is_chain, closed, last_seen) in rows:
        key = extract.normalize_entity(name)
        if not key:
            continue
        cur_row = merged.get(key)
        if cur_row is None:
            merged[key] = [rid, name, key, cuisine, list(boroughs or []), count or 0,
                           list(addresses or []), bool(is_chain), closed, last_seen]
            continue
        if len(name) > len(cur_row[1]):
            cur_row[0], cur_row[1], cur_row[3] = rid, name, cuisine or cur_row[3]
        cur_row[4] = sorted(set(cur_row[4]) | set(boroughs or []))
        cur_row[5] += count or 0
        cur_row[6] = (cur_row[6] + list(addresses or []))[:50]
        cur_row[7] = cur_row[7] or bool(is_chain)

    print(f"restaurants: {len(rows):,} rows -> {len(merged):,} under the new keys "
          f"({len(rows) - len(merged):,} merged)")
    if dry_run:
        return
    from psycopg2.extras import Json, execute_values
    with conn.cursor() as cur:
        cur.execute("delete from restaurants")
        execute_values(cur, """
            insert into restaurants
              (id, name, name_key, cuisine, boroughs, location_count,
               addresses, is_chain, closed, last_seen)
            values %s
        """, [(r[0], r[1], r[2], r[3], r[4], r[5], Json(r[6]), r[7], r[8], r[9])
              for r in merged.values()])
    conn.commit()


def report(conn):
    with conn.cursor() as cur:
        cur.execute("""select count(*) filter (where entity_key ~ '(^| )[a-z]( |$)'),
                              count(*) filter (where entity_key like '% and %')
                       from (select distinct entity_key from mentions) x""")
        stranded, anded = cur.fetchone()
    print(f"\nremaining: {stranded} keys with a stranded letter, "
          f"{anded} containing ' and '")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mentions-only", action="store_true",
                    help="skip refetching the city list")
    args = ap.parse_args()

    conn = db.connect()
    migrate_mentions(conn, args.dry_run)
    if not args.mentions_only:
        migrate_restaurants(conn, args.dry_run)
    if not args.dry_run:
        report(conn)
        print("\nnow run: python refresh.py --apply")


if __name__ == "__main__":
    main()
