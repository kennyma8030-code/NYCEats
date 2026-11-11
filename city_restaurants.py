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


def _row(name, area, address, zipcode, category, date):
    """One location in the shape restaurants.group_by_name reads."""
    return {"dba": name, "boro": area, "building": "", "street": address, "zipcode": zipcode,
            "cuisine_description": category, "inspection_date": date}


# ---------------------------------------------------------------- Chicago

CHICAGO = "https://data.cityofchicago.org/resource/4ijn-s7e5.json"
# Facility types that serve food to the public. The dataset also inspects
# schools, daycares, hospitals, groceries and wholesalers, and its type is
# free text ("Restaurant", "TAVERN", "Mobile Food Preparer", "ROOFTOPS").
CHICAGO_SERVES = ("restaurant", "bakery", "mobile", "tavern", "bar", "rooftop", "kiosk", "pop-up", "coffee",
                  "cafe", "ice cream", "deli", "brewery", "paleteria", "donut")
CHICAGO_NOT = ("school", "daycare", "grocery", "shared kitchen", "barber", "herbal")


def chicago():
    seen, out = set(), []
    # Newest inspection first, so the row kept for a licence is its latest:
    # that one says whether the place has since gone out of business.
    for r in _socrata(CHICAGO, "license_,dba_name,aka_name,facility_type,address,zip,inspection_date,results",
                      f"inspection_date > '{ACTIVE_SINCE}'", "inspection_date DESC, inspection_id"):
        lic = r.get("license_")
        if not lic or lic in seen:
            continue
        seen.add(lic)
        kind = (r.get("facility_type") or "").strip()
        low = kind.lower()
        if not any(w in low for w in CHICAGO_SERVES) or any(w in low for w in CHICAGO_NOT):
            continue
        if (r.get("results") or "").lower() == "out of business":
            continue
        # aka_name is the name on the door ("SURF'S UP"); dba_name is often the
        # company behind it ("TJM FULFILLMENT - SURF'S UP SOUTH SHORE").
        name = (r.get("aka_name") or r.get("dba_name") or "").strip()
        out.append(_row(name, "Chicago", (r.get("address") or "").strip(), r.get("zip"), kind.title(),
                        r.get("inspection_date")))
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
    seen, out = set(), []
    for r in _socrata(AUSTIN, "facility_id,restaurant_name,address,inspection_date", "facility_id is not null",
                      "inspection_date DESC, facility_id"):
        fid = r.get("facility_id")
        if fid in seen:
            continue
        seen.add(fid)
        street, city, zipcode = austin_address(r.get("address"))
        out.append(_row((r.get("restaurant_name") or "").strip(), city, street, zipcode, None,
                        r.get("inspection_date")))
    return out


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


def los_angeles():
    layer, out, offset, size = la_service(), [], 0, 2000
    while True:
        q = urllib.parse.urlencode({
            "f": "json", "where": "PE_DESCRIPTION LIKE 'RESTAURANT%'", "returnGeometry": "false",
            "outFields": "FACILITY_ID,FACILITY_NAME,FACILITY_ADDRESS,FACILITY_CITY,FACILITY_ZIP",
            "orderByFields": "ObjectId", "resultOffset": offset, "resultRecordCount": size})
        page = json.loads(_get(f"{layer}/query?{q}"))
        if page.get("error"):
            raise SystemExit(f"LA County inventory: {page['error']}")
        feats = page.get("features", [])
        for f in feats:
            a = f["attributes"]
            # The inventory is the places permitted now; it carries no inspection date.
            out.append(_row((a.get("FACILITY_NAME") or "").strip(), (a.get("FACILITY_CITY") or "").strip(),
                            (a.get("FACILITY_ADDRESS") or "").strip(), (a.get("FACILITY_ZIP") or "")[:5] or None,
                            "Restaurant", None))
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
            print(f"  loaded {load(conn, sub, source, groups):,} rows into city_restaurants")


if __name__ == "__main__":
    main()
