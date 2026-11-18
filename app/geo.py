"""Where a place is, for the map.

The database holds no coordinates: the loader (restaurants.py) does not read
the inspection dataset's latitude and longitude, and `restaurants` has no
column for them. Until both do, locations.py writes them to a file beside
this module and they are served from memory. It is a lookup by entity key,
the same join the official record makes (queries.official_record), and only
r/FoodNYC has one: every other city's places come back without a location
and the map shows the city with no pins.

A name with several locations is pinned at the first, which locations.py
orders oldest licence first: the longest-standing branch, usually the
original. All of them are on the detail response.
"""

import json
import logging
import os

import subreddits

log = logging.getLogger("uvicorn.error")

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nyc_locations.json")


def _load(path=PATH):
    """The file as {key: [[lat, lng, address, borough], ...]}. A missing or
    broken file is a warning and an empty lookup: the lists work without
    pins, and the API should not fail to boot over a map."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        log.warning("no coordinates loaded from %s: %s", path, e)
        return {}


_LOCATIONS = _load()


def locations(sub, entity_key):
    """Every known location of a place, the one the map pins first."""
    if sub != subreddits.HOME:
        return []
    return [{"lat": lat, "lng": lng, "address": address or None, "borough": borough or None}
            for lat, lng, address, borough in _LOCATIONS.get(entity_key, ())]
