"""Where a place is, for the map.

The database holds no coordinates: the loaders (restaurants.py,
city_restaurants.py) do not read the inspection datasets' latitude and
longitude, and their tables have no column for them. Until both do,
locations.py writes them to a file per city beside this module and they are
served from memory. It is a lookup by entity key, the same join the official
record makes (queries.official_record), made within the subreddit: "Joe's
Pizza" in Chicago is not the one on Carmine Street. A city whose file is
missing comes back without a location and the map shows it with no pins.

A name with several locations is pinned at the first, which locations.py
orders oldest licence first: the longest-standing branch, usually the
original. All of them are on the detail response.
"""

import json
import logging
import os

import subreddits

log = logging.getLogger("uvicorn.error")

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
# subreddit -> its file. New York's keeps the name it had before there were
# other cities.
FILES = {
    subreddits.HOME: os.path.join(DATA, "nyc_locations.json"),
    "FoodLosAngeles": os.path.join(DATA, "la_locations.json"),
    "austinfood": os.path.join(DATA, "austin_locations.json"),
    "chicagofood": os.path.join(DATA, "chicago_locations.json"),
}


def _load(path):
    """One file as {key: [[lat, lng, address, borough], ...]}. A missing or
    broken file is a warning and an empty lookup: the lists work without
    pins, and the API should not fail to boot over a map."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        log.warning("no coordinates loaded from %s: %s", path, e)
        return {}


# {subreddit: {key: rows}}, kept apart so one city's name never answers for another's.
_LOCATIONS = {sub: _load(path) for sub, path in FILES.items()}


def locations(sub, entity_key):
    """Every known location of a place in a subreddit, the one the map pins first."""
    return [{"lat": lat, "lng": lng, "address": address or None, "borough": borough or None}
            for lat, lng, address, borough in _LOCATIONS.get(sub, {}).get(entity_key, ())]
