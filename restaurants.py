"""Load the real NYC restaurant list from the city's inspection data.

Source: NYC Department of Health restaurant inspections, dataset 43nn-pn8j.
Free, no key, no rate limit, updated continuously. Every food business in the
five boroughs is licensed and inspected, so this is the closest thing to a
complete list of restaurants that exist.

Locations collapse by normalized name: a place with three branches becomes one
row with three addresses. That also makes chain detection fall out for free --
a name with a dozen locations is a chain.
"""

import argparse
import collections
import json
import time
import urllib.parse
import urllib.request

import db
import extract          # for normalize_entity, so keys match mentions.entity_key

SOCRATA = "https://data.cityofnewyork.us/resource/43nn-pn8j.json"
PAGE = 50000
CHAIN_LOCATIONS = 12    # TUNE  12+ locations is a chain. At 3 this would delete
                        # L'Industrie (3) and Joe's Pizza (11).
ACTIVE_SINCE = "2024-01-01"


def fetch_all(pause=0.5):
    """Every establishment inspected since ACTIVE_SINCE, deduped by licence id."""
    seen, out, offset = set(), [], 0
    while True:
        params = {
            "$select": "camis,dba,boro,building,street,zipcode,"
                       "cuisine_description,inspection_date",
            "$where": f"inspection_date > '{ACTIVE_SINCE}'",
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
        print(f"  fetched {offset + len(rows):,} rows, {len(out):,} distinct places")
        if len(rows) < PAGE:
            break
        offset += PAGE
        time.sleep(pause)
    return out


def group_by_name(rows):
    """Collapse licences into one entry per normalized name."""
    groups = collections.defaultdict(lambda: {
        "display": None, "cuisines": collections.Counter(),
        "boroughs": set(), "addresses": [], "last": "",
    })
    for r in rows:
        name = (r.get("dba") or "").strip()
        if not name:
            continue
        key = extract.normalize_entity(name)
        if not key:
            continue
        g = groups[key]
        # Keep the shortest display name: "CHIPOTLE MEXICAN GRILL" over
        # "CHIPOTLE MEXICAN GRILL #3056".
        if g["display"] is None or len(name) < len(g["display"]):
            g["display"] = name
        if r.get("cuisine_description"):
            g["cuisines"][r["cuisine_description"]] += 1
        if r.get("boro") and r["boro"] != "0":
            g["boroughs"].add(r["boro"].title())
        addr = " ".join(x for x in (r.get("building"), r.get("street")) if x).strip()
        if addr:
            g["addresses"].append({"address": addr, "zip": r.get("zipcode"),
                                   "boro": r.get("boro")})
        d = (r.get("inspection_date") or "")[:10]
        if d > g["last"]:
            g["last"] = d
    return groups


def load(conn, groups):
    rows = []
    for key, g in groups.items():
        n = len(g["addresses"]) or 1
        rows.append((
            g["display"], key,
            g["cuisines"].most_common(1)[0][0] if g["cuisines"] else None,
            sorted(g["boroughs"]) or None,
            n,
            json.dumps(g["addresses"][:20]),     # cap: a few chains have hundreds
            n >= CHAIN_LOCATIONS,
            g["last"] or None,
        ))
    from psycopg2.extras import execute_values
    with conn.cursor() as cur:
        inserted = execute_values(cur, """
            insert into restaurants
              (name, name_key, cuisine, boroughs, location_count,
               addresses, is_chain, last_seen)
            values %s
            on conflict (name_key) do update set
              cuisine        = excluded.cuisine,
              boroughs       = excluded.boroughs,
              location_count = excluded.location_count,
              addresses      = excluded.addresses,
              is_chain       = excluded.is_chain,
              last_seen      = excluded.last_seen
            returning id
        """, rows, template="(%s,%s,%s,%s,%s,%s,%s,%s)", fetch=True)
        n = len(inserted)
    conn.commit()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="fetch and report, do not write")
    args = ap.parse_args()

    print(f"fetching NYC restaurants inspected since {ACTIVE_SINCE}")
    rows = fetch_all()
    groups = group_by_name(rows)
    chains = sum(1 for g in groups.values() if len(g["addresses"]) >= CHAIN_LOCATIONS)
    print(f"\n{len(rows):,} licences -> {len(groups):,} distinct names "
          f"({chains} chains at {CHAIN_LOCATIONS}+ locations)")

    if args.dry_run:
        top = sorted(groups.items(), key=lambda kv: -len(kv[1]["addresses"]))[:10]
        for k, g in top:
            print(f"   {len(g['addresses']):>4}  {g['display']}")
        return

    conn = db.connect()
    print(f"loaded {load(conn, groups):,} rows into restaurants")


if __name__ == "__main__":
    main()
