"""Where the map pins a place: the static lookup behind the API (app/geo.py).
No database: the lookup is a file."""

import json
import os
import tempfile
import unittest
from unittest import mock

from fakes import ROOT  # noqa: F401  (puts the repo root on sys.path)

import subreddits
from app import geo

PLACES = {
    "joes pizza": [[40.73058, -74.00213, "7 CARMINE STREET", "Manhattan"],
                   [40.71692, -73.95899, "216 BEDFORD AVENUE", "Brooklyn"]],
    "no address": [[40.7, -73.9, "", ""]],
}


class Locations(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(geo, "_LOCATIONS", PLACES)
        patch.start()
        self.addCleanup(patch.stop)

    def test_the_first_location_is_the_pin(self):
        found = geo.locations(subreddits.HOME, "joes pizza")
        self.assertEqual(found[0], {"lat": 40.73058, "lng": -74.00213,
                                    "address": "7 CARMINE STREET", "borough": "Manhattan"})
        self.assertEqual(len(found), 2)

    def test_an_unknown_place_has_no_location(self):
        self.assertEqual(geo.locations(subreddits.HOME, "nowhere"), [])

    def test_only_new_york_has_coordinates(self):
        # The same name in another city is another place.
        self.assertEqual(geo.locations("austinfood", "joes pizza"), [])

    def test_blank_fields_are_null(self):
        self.assertEqual(geo.locations(subreddits.HOME, "no address"),
                         [{"lat": 40.7, "lng": -73.9, "address": None, "borough": None}])


class Loading(unittest.TestCase):
    def test_a_missing_or_broken_file_is_an_empty_lookup(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(geo._load(os.path.join(d, "absent.json")), {})
            broken = os.path.join(d, "broken.json")
            with open(broken, "w", encoding="utf-8") as f:
                f.write("{not json")
            self.assertEqual(geo._load(broken), {})

    def test_the_committed_file_loads_and_is_shaped_as_the_lookup_reads_it(self):
        with open(geo.PATH, encoding="utf-8") as f:
            data = json.load(f)
        self.assertGreater(len(data), 1000)
        for rows in list(data.values())[:200]:
            for lat, lng, address, borough in rows:
                self.assertTrue(40 < lat < 41.5 and -75 < lng < -73)
                self.assertIsInstance(address, str)
                self.assertIsInstance(borough, str)


if __name__ == "__main__":
    unittest.main()
