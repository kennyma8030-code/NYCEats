"""Print each extracted fact as JSON, as it lands.

Reads the database directly rather than the API, so it works whether or not
api.py is running.

    python watch.py             one JSON object per line, newest as they arrive
    python watch.py --pretty    indented
    python watch.py --n 20      show the last 20 first, then follow
"""

import argparse
import json
import time

import db

SQL = """
    select m.id, m.restaurant_raw, m.entity_key, m.aspects, m.dishes,
           m.descriptors, m.is_negated, m.is_firsthand, m.neighborhood_hint,
           m.expensiveness, c.author, c.body, c.permalink, c.created_utc,
           a.resolved_key, t.title as thread_title
    from mentions m
    join comments c on c.id = m.comment_id
    join threads  t on t.id = c.thread_id
    left join entity_alias a on a.entity_key = m.entity_key
    where m.id > %s
    order by m.id
    limit 500
"""


def jsonable(o):
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return float(o) if hasattr(o, "as_tuple") else str(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pretty", action="store_true")
    ap.add_argument("--n", type=int, default=5, help="how many existing rows to show first")
    ap.add_argument("--interval", type=float, default=3.0)
    args = ap.parse_args()

    conn = db.connect()
    with conn.cursor() as cur:
        cur.execute("select coalesce(max(id), 0) from mentions")
        cursor = max(cur.fetchone()[0] - args.n, 0)

    try:
        while True:
            with conn.cursor() as cur:
                cur.execute(SQL, (cursor,))
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
            for r in rows:
                cursor = r[0]
                print(json.dumps(dict(zip(cols, r)), default=jsonable,
                                 indent=2 if args.pretty else None), flush=True)
            # Nothing new is normal: a call covers 25 comments and takes minutes.
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
