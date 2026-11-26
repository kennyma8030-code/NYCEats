"""Load the restaurant list of every city but New York, from its health department's open data.

restaurants.py does this for r/FoodNYC, into `restaurants`, which every
score and page of the NYC board joins by name alone. Another city's names
cannot go in there: "Joe's Pizza" in Los Angeles would overwrite New York's
row and answer for it. So they go into `city_restaurants`, keyed by
(subreddit, name), which nothing reads yet. When places are identified by
subreddit and name everywhere, New York's list moves in beside them.

One row per NAME per city, as in `restaurants`: a place with three branches
is one row with three addresses, and a name with CHAIN_LOCATIONS or more is
a chain. The grouping is restaurants.group_by_name itself, so a key here is
built exactly as a mention's entity_key is.

Sources, each the fullest public list found for its city (2026-11):

  chicagofood     City of Chicago food inspections (Socrata 4ijn-s7e5), the
                  places inspected since ACTIVE_SINCE whose facility type
                  serves food. City limits only: the suburbs are other health
                  departments. The city's business licences were checked as
                  an alternative and hold the same places (11,378 retail food
                  licences against 11,320 inspected restaurants).
  austinfood      Austin Public Health inspection scores (Socrata ecmv-9xxi),
                  a rolling three years. Austin, Travis County and the small
                  cities that contract with it (Cedar Park, Lakeway, ...). No
                  facility type, so school and market kitchens are in it.
  FoodLosAngeles  LA County Public Health's restaurant and market inventory
                  (ArcGIS, republished every quarter), restaurants only. The
                  whole county except Pasadena, Long Beach and Vernon, which
                  have health departments of their own.
  FoodToronto     Toronto Public Health's DineSafe (CKAN). City of Toronto
                  only, every inspected food premises: it has no facility
                  type either, and no neighbourhood.

r/FoodSanDiego and r/denverfood have no loader yet.

    python city_restaurants.py --dry-run            fetch and report, write nothing
    python city_restaurants.py                      every city above
    python city_restaurants.py --subreddit chicagofood
"""

import argparse
import csv
import io
import json
import re
import threading
import time
import urllib.parse
import urllib.request

import db
import restaurants
import subreddits

UA = {"User-Agent": "restaurant-list-loader/0.1"}
ACTIVE_SINCE = restaurants.ACTIVE_SINCE
CHAIN_LOCATIONS = restaurants.CHAIN_LOCATIONS
PAGE = 50000

# The table, here as well as in schema.sql (which creates it on boot), so a
# load can run against a database whose poller has not been redeployed yet.
# tests/test_city_restaurants.py checks the two are the same statement.
TABLE_SQL = """create table if not exists city_restaurants (
  subreddit      text not null,
  name           text not null,          -- display form, as the source lists it
  name_key       text not null,          -- normalized, matches mentions.entity_key
  category       text,                   -- the source's facility type, where it has one
  areas          text[],                 -- cities or districts its locations are in
  location_count int not null default 1,
  addresses      jsonb,
  is_chain       boolean not null default false,
  last_seen      date,                   -- most recent inspection on record
  source         text not null,
  loaded_at      timestamptz not null default now(),
  primary key (subreddit, name_key)
);
-- Subreddit and name in one index: a name is matched within its own city, and
-- with the name alone every probe read all four cities' candidates before
-- throwing three away -- 24 times slower on a list this size. btree_gin is
-- what lets a plain text column sit in a GIN index beside the trigrams. The
-- name-only index this replaces is dropped where it was built.
create extension if not exists btree_gin;
drop index if exists city_restaurants_trgm_idx;
create index if not exists city_restaurants_sub_trgm_idx
  on city_restaurants using gin (subreddit, name_key gin_trgm_ops);"""


def _get(url, attempts=4):
    """The body of a GET, with a few retries: these are one-off loads from
    public servers, where a dropped connection is the usual failure."""
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return r.read()
        except OSError as e:
            if attempt == attempts - 1:
                raise
            wait = 5 * 2 ** attempt
            print(f"    {type(e).__name__}: {e}, retrying in {wait}s")
            time.sleep(wait)


def _socrata(base, select, where, order, pause=0.5):
    """Every row of a Socrata query, paged."""
    offset = 0
    while True:
        params = {"$select": select, "$where": where, "$order": order, "$limit": PAGE, "$offset": offset}
        rows = json.loads(_get(f"{base}?{urllib.parse.urlencode(params)}"))
        yield from rows
        if len(rows) < PAGE:
            return
        offset += PAGE
        time.sleep(pause)


def _row(name, area, address, zipcode, category, date, ident=None, lat=None, lng=None):
    """One location in the shape restaurants.group_by_name reads. `ident`,
    `lat` and `lng` are for locations.py, which pins these places on the map;
    group_by_name ignores them, so the table loaded from these rows is the same.
    `pin_street` is the address of the row the coordinates came from, which
    is not always the row the rest came from (see _pin)."""
    return {"dba": name, "boro": area, "building": "", "street": address, "zipcode": zipcode,
            "cuisine_description": category, "inspection_date": date,
            "id": ident, "lat": lat, "lng": lng, "pin_street": address}


def _pin(row, lat, lng, street):
    """Give a place the coordinates of an older inspection that has them, with
    that inspection's street: a coordinate must not be paired with an address
    it was not measured at. The row's own street, which the table load stores,
    stays the newest one."""
    if row["lat"] in (None, "") and lat not in (None, ""):
        row.update(lat=lat, lng=lng, pin_street=street)


# ---------------------------------------------------------------- Chicago

CHICAGO = "https://data.cityofchicago.org/resource/4ijn-s7e5.json"
# Facility types that serve food to the public. The dataset also inspects
# schools, daycares, hospitals, groceries and wholesalers, and its type is
# free text ("Restaurant", "TAVERN", "Mobile Food Preparer", "ROOFTOPS").
CHICAGO_SERVES = ("restaurant", "bakery", "mobile", "tavern", "bar", "rooftop", "kiosk", "pop-up", "coffee",
                  "cafe", "ice cream", "deli", "brewery", "paleteria", "donut")
CHICAGO_NOT = ("school", "daycare", "grocery", "shared kitchen", "barber", "herbal")


def chicago():
    seen, out, kept = set(), [], {}
    # Newest inspection first, so the row kept for a licence is its latest:
    # that one says whether the place has since gone out of business.
    for r in _socrata(CHICAGO, "license_,dba_name,aka_name,facility_type,address,zip,inspection_date,results,latitude,longitude",
                      f"inspection_date > '{ACTIVE_SINCE}'", "inspection_date DESC, inspection_id"):
        lic = r.get("license_")
        if not lic:
            continue
        if lic in seen:
            # An older inspection of a kept licence, for the coordinates its
            # newest one lacks. A licence dropped below stays dropped.
            if kept.get(lic) is not None:
                _pin(kept[lic], r.get("latitude"), r.get("longitude"), (r.get("address") or "").strip())
            continue
        seen.add(lic)
        kept[lic] = None
        kind = (r.get("facility_type") or "").strip()
        low = kind.lower()
        if not any(w in low for w in CHICAGO_SERVES) or any(w in low for w in CHICAGO_NOT):
            continue
        if (r.get("results") or "").lower() == "out of business":
            continue
        # aka_name is the name on the door ("SURF'S UP"); dba_name is often the
        # company behind it ("TJM FULFILLMENT - SURF'S UP SOUTH SHORE").
        name = (r.get("aka_name") or r.get("dba_name") or "").strip()
        kept[lic] = _row(name, "Chicago", (r.get("address") or "").strip(), r.get("zip"), kind.title(),
                         r.get("inspection_date"), lic, r.get("latitude"), r.get("longitude"))
        out.append(kept[lic])
    return out


# ---------------------------------------------------------------- Austin

AUSTIN = "https://data.austintexas.gov/resource/ecmv-9xxi.json"
# The address is one string with no break between street and city:
# "11200 Lakeline Mall Dr Cedar Park, TX 78613-1500". These are the cities
# of more than one word in the health department's area; any other city is
# the last word before the comma.
AUSTIN_CITIES = ("Cedar Park", "Round Rock", "Bee Cave", "Bee Caves", "Del Valle", "West Lake Hills",
                 "Sunset Valley", "Lago Vista", "Dripping Springs", "Point Venture", "Mustang Ridge",
                 "San Leanna", "The Hills", "Village Of The Hills", "Jonestown", "Liberty Hill")
_AUSTIN_ADDR = re.compile(r"^(.*?),\s*TX\s+(\d{5})", re.S)


def austin_address(raw):
    """(street, city, zip) from Austin's one-string address; city and zip None when it does not parse."""
    text = " ".join((raw or "").split())
    m = _AUSTIN_ADDR.match(text)
    if not m:
        return text, None, None
    head = m.group(1)
    for city in sorted(AUSTIN_CITIES, key=len, reverse=True):
        if head.lower().endswith(" " + city.lower()):
            return head[:-len(city)].strip(), city.title(), m.group(2)
    street, _, city = head.rpartition(" ")
    return street.strip(), city.title(), m.group(2)


def austin():
    # Newest inspection first, so a place's row is its latest. That row can
    # lack lat and lng (the dataset geocodes some inspections and not
    # others), so the coordinates, and the street they were measured at, come
    # from the newest row that has them.
    places = {}
    for r in _socrata(AUSTIN, "facility_id,restaurant_name,address,inspection_date,lat,lng",
                      "facility_id is not null", "inspection_date DESC, facility_id"):
        fid = r.get("facility_id")
        if fid in places:
            _pin(places[fid], r.get("lat"), r.get("lng"), austin_address(r.get("address"))[0])
            continue
        street, city, zipcode = austin_address(r.get("address"))
        places[fid] = _row((r.get("restaurant_name") or "").strip(), city, street, zipcode, None,
                           r.get("inspection_date"), fid, r.get("lat"), r.get("lng"))
    return list(places.values())


# ---------------------------------------------------------------- Los Angeles

ARCGIS_SEARCH = "https://www.arcgis.com/sharing/rest/search"
LA_TITLE = "Environmental Health Restaurant and Market Inventory"
LA_OWNER = "ph.lacounty.gov"


def la_service():
    """The feature layer of the county's newest inventory. It is republished
    every quarter under a new title and address ("... Inventory 09/30/26"),
    so it is looked up by title and publisher, newest first."""
    q = urllib.parse.urlencode({"f": "json", "num": 20, "sortField": "modified", "sortOrder": "desc",
                                "q": f'title:"{LA_TITLE}" type:"Feature Service"'})
    for item in json.loads(_get(f"{ARCGIS_SEARCH}?{q}")).get("results", []):
        if item.get("title", "").startswith(LA_TITLE) and LA_OWNER in item.get("owner", "") and item.get("url"):
            print(f"  LA County inventory: {item['title']}")
            return item["url"].rstrip("/") + "/0"
    raise SystemExit(f"no '{LA_TITLE}' published by {LA_OWNER} was found on ArcGIS")


def los_angeles(geometry=False):
    """`geometry` asks for each place's coordinates too: only locations.py
    wants them, and the boot load (ensure_loaded) would throw them away."""
    layer, out, offset, size = la_service(), [], 0, 2000
    while True:
        q = urllib.parse.urlencode({
            "f": "json", "where": "PE_DESCRIPTION LIKE 'RESTAURANT%'", "returnGeometry": str(geometry).lower(), "outSR": 4326,
            "outFields": "FACILITY_ID,FACILITY_NAME,FACILITY_ADDRESS,FACILITY_CITY,FACILITY_ZIP",
            "orderByFields": "ObjectId", "resultOffset": offset, "resultRecordCount": size})
        page = json.loads(_get(f"{layer}/query?{q}"))
        if page.get("error"):
            raise SystemExit(f"LA County inventory: {page['error']}")
        feats = page.get("features", [])
        for f in feats:
            a, g = f["attributes"], f.get("geometry") or {}
            # The inventory is the places permitted now; it carries no inspection date.
            out.append(_row((a.get("FACILITY_NAME") or "").strip(), (a.get("FACILITY_CITY") or "").strip(),
                            (a.get("FACILITY_ADDRESS") or "").strip(), (a.get("FACILITY_ZIP") or "")[:5] or None,
                            "Restaurant", None, a.get("FACILITY_ID"), g.get("y"), g.get("x")))
        if len(feats) < size and not page.get("exceededTransferLimit"):
            return out
        offset += len(feats)
        time.sleep(0.2)


# ---------------------------------------------------------------- Toronto

TORONTO = ("https://ckan0.cf.opendata.inter.prod-toronto.ca/datastore/dump/"
           "75dbb3ff-8281-4f03-9de2-bd1214761302")
_TORONTO_ADDR = re.compile(r"^(.*?)\s+([A-Z]\d[A-Z]\s?\d[A-Z]\d)$")


def toronto_address(raw):
    """(street, postal code) from DineSafe's "1871 O'Connor Dr None M4A 1X1";
    "None" stands where a unit number would be."""
    text = " ".join((raw or "").split())
    m = _TORONTO_ADDR.match(text)
    street, postal = (m.group(1), m.group(2)) if m else (text, None)
    return re.sub(r"\s+None$", "", street), postal


def toronto():
    # One row per infraction or inspection; a place is its estId, at its latest inspection.
    latest = {}
    for r in csv.DictReader(io.StringIO(_get(TORONTO).decode("utf-8-sig"))):
        eid, date = r.get("estId"), r.get("inspectionDate") or ""
        if eid and (eid not in latest or date > latest[eid]["inspectionDate"]):
            latest[eid] = dict(r, inspectionDate=date)
    out = []
    for r in latest.values():
        if r["inspectionDate"] < ACTIVE_SINCE or (r.get("inspectionStatus") or "").lower() == "closed":
            continue
        street, postal = toronto_address(r.get("address"))
        out.append(_row((r.get("estName") or "").strip(), "Toronto", street, postal, None, r["inspectionDate"]))
    return out


# subreddit -> (what the source is called in the `source` column, its fetcher)
SOURCES = {
    "chicagofood": ("City of Chicago food inspections", chicago),
    "austinfood": ("Austin Public Health inspection scores", austin),
    "FoodLosAngeles": ("LA County Public Health restaurant inventory", los_angeles),
    "FoodToronto": ("Toronto Public Health DineSafe", toronto),
}
assert set(SOURCES) <= set(subreddits.SUBREDDITS) - {subreddits.HOME}


def rows_for(subreddit, source, groups):
    out = []
    for key, g in groups.items():
        n = len(g["addresses"]) or 1
        out.append((subreddit, g["display"], key,
                    g["cuisines"].most_common(1)[0][0] if g["cuisines"] else None,
                    sorted(g["boroughs"]) or None, n,
                    json.dumps(g["addresses"][:20]),     # cap: a few chains have hundreds
                    n >= CHAIN_LOCATIONS, g["last"] or None, source))
    return out


def load(conn, subreddit, source, groups):
    """Replace one city's list with `groups`, in one transaction: a refresh
    drops the places that have closed, and a failed one leaves the old list."""
    from psycopg2.extras import execute_values
    rows = rows_for(subreddit, source, groups)
    with conn.cursor() as cur:
        cur.execute("delete from city_restaurants where subreddit = %s", (subreddit,))
        execute_values(cur, """
            insert into city_restaurants
              (subreddit, name, name_key, category, areas, location_count, addresses, is_chain, last_seen, source)
            values %s""", rows, template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", page_size=2000)
    conn.commit()
    return len(rows)


# The fewest distinct names a city's list can honestly have. Each source
# above lists several thousand (Chicago's about 11,000 places), so a fetch
# that comes back with less than this is an outage or a changed dataset that
# answered 200 with nothing in it, not a city with no restaurants. Loading it
# would mark the city as loaded with a list that matches nothing.
MIN_NAMES = 1000


class TooFew(Exception):
    """A source answered with too few names to be the city's list."""


def checked(groups):
    """`groups` if it can be a city's list, else TooFew."""
    if len(groups) < MIN_NAMES:
        raise TooFew(f"its source returned {len(groups):,} distinct names, and a real list has "
                     f"at least {MIN_NAMES:,}; nothing was loaded")
    return groups


def missing(conn, names):
    """The subreddits of `names` that have a source and no rows yet."""
    with conn.cursor() as cur:
        cur.execute("select distinct subreddit from city_restaurants")
        have = {r[0] for r in cur.fetchall()}
    conn.commit()
    return [sub for sub in names if sub in SOURCES and sub not in have]


def _close(conn):
    try:
        if conn is not None:
            conn.close()
    except Exception:
        pass


def ensure_loaded(names, connect=None, log=print):
    """Load the list of each subreddit in `names` that has a source and no
    rows yet, as restaurants.ensure_loaded does for New York: once, on the
    first boot that collects the city, and never again by itself (run this
    file by hand to refresh one). Returns {subreddit: rows loaded}.

    Never raises, and never touches the caller's connection. It opens its
    own, one for the look at what is missing and one for each city's load,
    and holds none while a source is being downloaded: a download can take
    many minutes, long enough for the proxy to drop an idle connection, and
    a dead connection handed back to the poller is what this must not do.

    A source that cannot be reached, or that answers with too few names to
    be the city's list (MIN_NAMES), is logged and left for the next boot,
    which tries once more. A city without its list is still collected and
    scored, its names just unmatched. The sources raise SystemExit as well
    as Exception (los_angeles), so both are caught.
    """
    connect = connect or db.connect
    loaded = {}
    conn = None
    try:
        conn = connect()
        todo = missing(conn, names)
    except Exception as e:
        log(f"city_restaurants: could not see which lists are missing ({type(e).__name__}: {e}); "
            f"the next boot tries again")
        return loaded
    finally:
        _close(conn)
    for sub in todo:
        source, fetch = SOURCES[sub]
        log(f"city_restaurants has no rows for r/{sub}, loading {source}")
        conn = None
        try:
            groups = checked(restaurants.group_by_name(fetch()))
            conn = connect()
            loaded[sub] = load(conn, sub, source, groups)
            log(f"loaded {loaded[sub]:,} restaurants for r/{sub}")
        except (Exception, SystemExit) as e:
            log(f"  r/{sub}: LIST NOT LOADED ({type(e).__name__}: {e}); the next boot tries again")
        finally:
            _close(conn)
    return loaded


def start_background(names, log=print):
    """ensure_loaded beside the poller rather than before it, like the
    backfill and the RSS fallback: four full downloads from public servers,
    each allowed minutes of retries, must not hold the first poll back.
    Daemon: it dies with its host, and a list that did not load is tried
    again on the next boot."""
    thread = threading.Thread(target=ensure_loaded, args=(tuple(names),), kwargs={"log": log},
                              name="city-restaurants", daemon=True)
    thread.start()
    return thread


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subreddit", action="append", choices=sorted(SOURCES),
                    help="load only this city (repeatable; default: every city with a source)")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report, do not write")
    args = ap.parse_args()

    conn = None
    if not args.dry_run:
        conn = db.connect()
        with conn.cursor() as cur:
            cur.execute(TABLE_SQL)
        conn.commit()
    for sub in args.subreddit or [s for s in subreddits.SUBREDDITS if s in SOURCES]:
        source, fetch = SOURCES[sub]
        print(f"r/{sub}: fetching {source}")
        places = fetch()
        groups = restaurants.group_by_name(places)
        chains = sorted((g for g in groups.values() if len(g["addresses"]) >= CHAIN_LOCATIONS),
                        key=lambda g: -len(g["addresses"]))
        print(f"  {len(places):,} places -> {len(groups):,} distinct names "
              f"({len(chains)} chains at {CHAIN_LOCATIONS}+ locations)")
        for g in chains[:5]:
            print(f"   {len(g['addresses']):>5}  {g['display']}")
        if conn is not None:
            try:
                checked(groups)
            except TooFew as e:
                # The old list is better than a truncated one: load() replaces it whole.
                print(f"  NOT LOADED: {e}")
                continue
            print(f"  loaded {load(conn, sub, source, groups):,} rows into city_restaurants")


if __name__ == "__main__":
    main()
