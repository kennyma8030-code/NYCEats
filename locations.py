"""Write app/data/nyc_locations.json: where each New York place on the board is.

The map needs coordinates and the database has none: restaurants.py reads the
city's inspection dataset (43nn-pn8j) without its latitude and longitude
columns, and the `restaurants` table has nowhere to keep them. Until the
loader and the schema carry them, this reads the same public dataset and
writes a static lookup the API serves from (app/geo.py):

    {"katzs delicatessen": [[40.72223, -73.98743, "205 EAST HOUSTON STREET", "Manhattan"]], ...}

Keys are extract.normalize_entity of the licence name, exactly as
restaurants.py keys the `restaurants` table, so they meet the board's
entity_key the same way the official record does.

A name with several licences keeps them all, oldest licence first. Licence
ids (camis) are handed out in order, so the first is the longest-standing
location, which for most small groups is the original: Joe's Pizza on Carmine
Street, L'Industrie in Williamsburg. The map pins that one.

Only names the board holds are written, read from entity_leaderboard on a
read-only connection; without that the file would carry twenty thousand
places nobody has mentioned. --all skips the database and writes every name.

    python locations.py            # needs DATABASE_URL; writes nothing to it
    python locations.py --all      # no database
"""

import argparse
import collections
import json
import os
import time
import urllib.parse
import urllib.request

import extract          # for normalize_entity, so keys match mentions.entity_key
import subreddits

SOCRATA = "https://data.cityofnewyork.us/resource/43nn-pn8j.json"
PAGE = 50000
ACTIVE_SINCE = "2024-01-01"     # as restaurants.py: places inspected since
MAX_LOCATIONS = 20              # as restaurants.py caps addresses: a few chains have hundreds
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "data", "nyc_locations.json")


def fetch_all(pause=0.5):
    """One row per licence inspected since ACTIVE_SINCE that has coordinates."""
    seen, out, offset = set(), [], 0
    while True:
        params = {
            "$select": "camis,dba,boro,building,street,latitude,longitude,"
                       "max(inspection_date) as last",
            "$where": f"inspection_date > '{ACTIVE_SINCE}' and latitude is not null",
            "$group": "camis,dba,boro,building,street,latitude,longitude",
            "$order": "camis",
            "$limit": PAGE,
            "$offset": offset,
        }
        url = f"{SOCRATA}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=120) as r:
            rows = json.load(r)
        if not rows:
            break
        for row in rows:
            key = row.get("camis")
            if key and key not in seen:
                seen.add(key)
                out.append(row)
        print(f"  fetched {offset + len(rows):,} rows, {len(out):,} licences")
        if len(rows) < PAGE:
            break
        offset += PAGE
        time.sleep(pause)
    return out


def group_by_name(rows):
    """Licences -> {name key: [[lat, lng, address, borough], ...]}, oldest licence first."""
    groups = collections.defaultdict(list)
    for r in sorted(rows, key=lambda r: int(r["camis"])):
        key = extract.normalize_entity((r.get("dba") or "").strip())
        try:
            lat, lng = float(r["latitude"]), float(r["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        # The dataset writes an ungeocoded address as 0, 0.
        if not key or not (40 < lat < 41.5 and -75 < lng < -73):
            continue
        address = " ".join(x for x in (r.get("building"), r.get("street")) if x).strip()
        boro = (r.get("boro") or "").title()
        groups[key].append([round(lat, 5), round(lng, 5), " ".join(address.split()),
                            boro if boro != "0" else ""])
    return {k: v[:MAX_LOCATIONS] for k, v in groups.items()}


def board_keys():
    """Every New York key on the board. The session is read-only, so nothing
    this script does can write to the database it reads."""
    import db
    conn = db.connect()
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("select entity_key from entity_leaderboard where subreddit = %s",
                        (subreddits.HOME,))
            return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="write every name in the dataset, without reading the board")
    args = ap.parse_args()

    print(f"fetching NYC licences inspected since {ACTIVE_SINCE}")
    groups = group_by_name(fetch_all())
    print(f"{len(groups):,} names with coordinates")
    if not args.all:
        keys = board_keys()
        groups = {k: v for k, v in groups.items() if k in keys}
        print(f"{len(groups):,} of them are among the board's {len(keys):,} places")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(groups.items())), f, separators=(",", ":"), ensure_ascii=False)
    print(f"wrote {OUT} ({os.path.getsize(OUT) / 1024:,.0f} KB)")


if __name__ == "__main__":
    main()
