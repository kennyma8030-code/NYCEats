"""Write app/data/*_locations.json: where each place on a board is, for the map.

The map needs coordinates and the database has none: the loaders
(restaurants.py, city_restaurants.py) read each health department's list
without latitude and longitude, and their tables have nowhere to keep them.
Until the loaders and the schema carry them, this reads the same public
sources again and writes a static lookup per city that the API serves from
(app/geo.py):

    {"katzs delicatessen": [[40.72223, -73.98743, "205 EAST HOUSTON STREET", "Manhattan"]], ...}

The last field is the part of the city the source names: a borough in New
York, otherwise the city or town (Cedar Park, Pasadena).

Keys are extract.normalize_entity of the licence name, exactly as the
loaders key their tables, so they meet the board's entity_key the same way
the official record does. The other cities' rows come from
city_restaurants.py's own fetchers, so what counts as a place there (Chicago's
facility types, LA's restaurants only) is decided once.

A name with several licences keeps them all, oldest licence first. Licence
ids are handed out in order, so the first is the longest-standing location,
which for most small groups is the original: Joe's Pizza on Carmine Street,
L'Industrie in Williamsburg. The map pins that one.

Only names the board holds for that subreddit are written, read from
entity_leaderboard on a read-only connection; without that the files would
carry twenty thousand places nobody has mentioned. --all skips the database
and writes every name.

    python locations.py                         # needs DATABASE_URL; writes nothing to it
    python locations.py --all                   # no database
    python locations.py --subreddit chicagofood
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
from app import geo

SOCRATA = "https://data.cityofnewyork.us/resource/43nn-pn8j.json"
PAGE = 50000
ACTIVE_SINCE = "2024-01-01"     # as restaurants.py: places inspected since
MAX_LOCATIONS = 20              # as restaurants.py caps addresses: a few chains have hundreds

# A box around each city's health department area (south, north, west, east),
# to throw out the rows a source geocoded to 0, 0 or to another state. Each
# is a little looser than the metro area the subreddit covers on purpose.
BOXES = {
    subreddits.HOME: (40, 41.5, -75, -73),
    "FoodLosAngeles": (33.2, 34.95, -118.95, -117.6),   # the county, Catalina and Lancaster included
    "austinfood": (29.9, 30.8, -98.3, -97.2),           # Travis County and its neighbours
    "chicagofood": (41.6, 42.1, -88.0, -87.5),          # the city limits and the edge of its suburbs
}


def fetch_all(pause=0.5):
    """One row per New York licence inspected since ACTIVE_SINCE that has
    coordinates, in the shape city_restaurants._row gives the other cities."""
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
                address = " ".join(x for x in (row.get("building"), row.get("street")) if x)
                boro = (row.get("boro") or "").title()
                out.append({"id": key, "dba": row.get("dba"), "boro": "" if boro == "0" else boro,
                            "street": address, "lat": row.get("latitude"), "lng": row.get("longitude")})
        print(f"  fetched {offset + len(rows):,} rows, {len(out):,} licences")
        if len(rows) < PAGE:
            break
        offset += PAGE
        time.sleep(pause)
    return out


def group_by_name(rows, box):
    """Licences -> {name key: [[lat, lng, address, area], ...]}, oldest licence
    first. Rows outside `box` (south, north, west, east) are dropped."""
    south, north, west, east = box
    groups = collections.defaultdict(list)
    # Ids are numbers in New York and Chicago and "FA0012345" in LA; by length
    # and then text they order the same as by value.
    for r in sorted(rows, key=lambda r: (len(str(r.get("id") or "")), str(r.get("id") or ""))):
        key = extract.normalize_entity((r.get("dba") or "").strip())
        try:
            lat, lng = float(r["lat"]), float(r["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        # The sources write an ungeocoded address as 0, 0, or leave it out.
        if not key or not (south < lat < north and west < lng < east):
            continue
        # The address the coordinates were measured at, and the area in title
        # case whatever the source writes (LA's is upper case).
        street = r.get("pin_street") if r.get("pin_street") is not None else r.get("street")
        groups[key].append([round(lat, 5), round(lng, 5), " ".join((street or "").split()),
                            (r.get("boro") or "").strip().title()])
    return {k: v[:MAX_LOCATIONS] for k, v in groups.items()}


def _city(fetcher, **kw):
    """A city_restaurants fetcher, imported when it runs: that module imports
    db (psycopg2), which the New York fetch, --all and the tests do not need."""
    def fetch():
        import city_restaurants
        return getattr(city_restaurants, fetcher)(**kw)
    return fetch


# subreddit -> its fetcher: rows of {id, dba, boro, street, lat, lng}, with
# pin_street where the coordinates were measured at another address than street
FETCHERS = {
    subreddits.HOME: fetch_all,
    "FoodLosAngeles": _city("los_angeles", geometry=True),
    "austinfood": _city("austin"),
    "chicagofood": _city("chicago"),
}

# The fewest names with coordinates a city's source can honestly give (about
# half of what each returned in 2026-11), as city_restaurants.MIN_NAMES does
# for the loaders: an outage that answers 200 with a few rows must not
# overwrite the committed file with a map that has no pins.
MIN_NAMES = {subreddits.HOME: 10000, "FoodLosAngeles": 10000, "austinfood": 2500, "chicagofood": 3000}
MIN_ON_BOARD = 100


class TooFew(Exception):
    """A source or the board answered with too little to replace a city's file."""
assert set(FETCHERS) == set(BOXES) == set(MIN_NAMES) == set(geo.FILES)


def board_keys(subreddit):
    """Every key on a subreddit's board. The session is read-only, so nothing
    this script does can write to the database it reads."""
    import db
    conn = db.connect()
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("select entity_key from entity_leaderboard where subreddit = %s",
                        (subreddit,))
            return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


def write(subreddit, every):
    """Fetch one city, keep the board's names unless `every`, and write its file."""
    print(f"fetching r/{subreddit}")
    groups = group_by_name(FETCHERS[subreddit](), BOXES[subreddit])
    print(f"{len(groups):,} names with coordinates")
    if len(groups) < MIN_NAMES[subreddit]:
        raise TooFew(f"r/{subreddit}: its source gave {len(groups):,} names with coordinates and a real "
                     f"list has at least {MIN_NAMES[subreddit]:,}; the file was not written")
    if not every:
        keys = board_keys(subreddit)
        groups = {k: v for k, v in groups.items() if k in keys}
        print(f"{len(groups):,} of them are among the board's {len(keys):,} places")
        if len(groups) < MIN_ON_BOARD:
            raise TooFew(f"r/{subreddit}: only {len(groups):,} of the board's places matched, "
                         f"fewer than {MIN_ON_BOARD}; the file was not written")
    out = geo.FILES[subreddit]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(groups.items())), f, separators=(",", ":"), ensure_ascii=False)
    print(f"wrote {out} ({os.path.getsize(out) / 1024:,.0f} KB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="write every name in the dataset, without reading the board")
    ap.add_argument("--subreddit", action="append", choices=sorted(FETCHERS),
                    help="only this city (repeatable); default every city with a source")
    args = ap.parse_args()
    failed = []
    for sub in args.subreddit or FETCHERS:
        try:
            write(sub, args.all)
        except TooFew as e:
            print(f"REFUSED: {e}")
            failed.append(sub)
    if failed:
        raise SystemExit(f"not written: {', '.join(failed)}")


if __name__ == "__main__":
    main()
