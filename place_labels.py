"""Load place_labels: the cuisine and neighborhood of the other cities' places.

The health departments of Chicago, Los Angeles and Austin say what kind of
premises a licence is, not what it serves, so those boards had no cuisine to
filter by. place_labels.json fills that in for the places that are on a board
and pinned on the map (app/data/*_locations.json):

    ["chicagofood", "lou malnatis pizzeria", "Pizza", "River North"]

The cuisine is Claude's reading of the licence name and of the dishes and
descriptors commenters attached to the place, in New York's vocabulary
(the city's cuisine_description) plus Vietnamese and Bar, and null where the
place is not a restaurant or nothing says what it serves. It was labeled
once, without a second pass, so it is a good guess and not a record; a wrong
one is fixed by editing the file and loading it again.

The neighborhood is the one the place's first pin falls in: the City of
Chicago's neighborhoods, the Los Angeles Times' for the city of Los Angeles
(the town's name outside it), and the City of Austin's.

The file is the whole table: a load upserts every row in it and deletes the
rows it no longer has, in one transaction. The board picks the cuisine up
through the `places` view at its next refresh (refresh.py).

    python place_labels.py             # needs DATABASE_URL
    python place_labels.py --dry-run   # count what the file holds, write nothing
"""

import argparse
import collections
import json
import os

import db

HERE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(HERE, "place_labels.json")

# The table, here as well as in schema.sql (which creates it on boot), so a
# load does not depend on a boot having happened first.
TABLE_SQL = """
create table if not exists place_labels (
  subreddit      text not null,
  name_key       text not null,
  cuisine        text,
  neighborhood   text,
  labeled_at     timestamptz not null default now(),
  primary key (subreddit, name_key)
);
"""


def read(path=FILE):
    """The file's rows as (subreddit, name_key, cuisine, neighborhood)."""
    with open(path, encoding="utf-8") as f:
        return [tuple(r) for r in json.load(f)]


def load(conn, rows):
    """Make the table hold exactly `rows`. Returns how many it wrote.

    labeled_at moves only for a row whose label changed, so it says when a
    place got the label it has now rather than when the file was last loaded.
    """
    from psycopg2.extras import execute_values
    with conn.cursor() as cur:
        cur.execute(TABLE_SQL)
        cur.execute("create temp table incoming (like place_labels including defaults) on commit drop")
        execute_values(cur, "insert into incoming (subreddit, name_key, cuisine, neighborhood) values %s",
                       rows, page_size=2000)
        cur.execute("""
            delete from place_labels p
            where not exists (select 1 from incoming i
                              where i.subreddit = p.subreddit and i.name_key = p.name_key)""")
        cur.execute("""
            insert into place_labels (subreddit, name_key, cuisine, neighborhood)
            select subreddit, name_key, cuisine, neighborhood from incoming
            on conflict (subreddit, name_key) do update
              set cuisine = excluded.cuisine, neighborhood = excluded.neighborhood, labeled_at = now()
              where (place_labels.cuisine, place_labels.neighborhood)
                    is distinct from (excluded.cuisine, excluded.neighborhood)""")
    conn.commit()
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="count the file's rows and write nothing")
    args = ap.parse_args()
    rows = read()
    by_sub = collections.Counter(r[0] for r in rows)
    for sub, n in sorted(by_sub.items()):
        cuisines = sum(1 for r in rows if r[0] == sub and r[2])
        hoods = sum(1 for r in rows if r[0] == sub and r[3])
        print(f"r/{sub}: {n:,} places, {cuisines:,} with a cuisine, {hoods:,} with a neighborhood")
    if args.dry_run:
        return
    conn = db.connect()
    print(f"loaded {load(conn, rows):,} rows into place_labels")


if __name__ == "__main__":
    main()
