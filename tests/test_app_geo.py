"""Where the map pins a place: the static lookup behind the API (app/geo.py)
and the script that writes it (locations.py). No database: the lookup is a file."""

import json
import os
import tempfile
import unittest
from unittest import mock

from fakes import ROOT  # noqa: F401  (puts the repo root on sys.path)

import locations
import subreddits
from app import geo

PLACES = {
    subreddits.HOME: {
        "joes pizza": [[40.73058, -74.00213, "7 CARMINE STREET", "Manhattan"],
                       [40.71692, -73.95899, "216 BEDFORD AVENUE", "Brooklyn"]],
        "no address": [[40.7, -73.9, "", ""]],
    },
    "chicagofood": {"joes pizza": [[41.88, -87.63, "1 W MADISON ST", "Chicago"]]},
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

    def test_a_city_is_looked_up_in_its_own_file(self):
        self.assertEqual(geo.locations("chicagofood", "joes pizza"),
                         [{"lat": 41.88, "lng": -87.63, "address": "1 W MADISON ST", "borough": "Chicago"}])

    def test_the_same_name_in_another_city_is_another_place(self):
        # A city with no entry for a name must not answer with New York's.
        self.assertEqual(geo.locations("austinfood", "joes pizza"), [])
        self.assertEqual(geo.locations("FoodLosAngeles", "joes pizza"), [])
        self.assertNotEqual(geo.locations("chicagofood", "joes pizza")[0]["lat"],
                            geo.locations(subreddits.HOME, "joes pizza")[0]["lat"])
        self.assertEqual(geo.locations("chicagofood", "no address"), [])

    def test_an_unknown_subreddit_has_no_location(self):
        self.assertEqual(geo.locations("nowhere", "joes pizza"), [])

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

    def test_a_city_whose_file_is_missing_has_no_pins_and_the_others_keep_theirs(self):
        with tempfile.TemporaryDirectory() as d:
            ny = os.path.join(d, "ny.json")
            with open(ny, "w", encoding="utf-8") as f:
                json.dump({"joes pizza": [[40.7, -73.9, "1 A ST", "Queens"]]}, f)
            files = {subreddits.HOME: ny, "austinfood": os.path.join(d, "absent.json")}
            loaded = {sub: geo._load(path) for sub, path in files.items()}
            with mock.patch.object(geo, "_LOCATIONS", loaded):
                self.assertEqual(len(geo.locations(subreddits.HOME, "joes pizza")), 1)
                self.assertEqual(geo.locations("austinfood", "joes pizza"), [])

    def test_every_city_has_a_file_of_its_own(self):
        self.assertEqual(len(set(geo.FILES.values())), len(geo.FILES))
        self.assertTrue(set(geo.FILES) <= set(subreddits.SUBREDDITS))

    def test_the_committed_files_load_and_are_shaped_as_the_lookup_reads_them(self):
        for sub, path in geo.FILES.items():
            with self.subTest(sub=sub):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self.assertGreater(len(data), 500)
                south, north, west, east = locations.BOXES[sub]
                for rows in data.values():
                    for lat, lng, address, area in rows:
                        self.assertTrue(south < lat < north and west < lng < east)
                        self.assertIsInstance(address, str)
                        self.assertIsInstance(area, str)


class Grouping(unittest.TestCase):
    """locations.group_by_name: the keys and the pin order."""

    BOX = (41.6, 42.1, -88.0, -87.5)

    @staticmethod
    def rows():
        def r(i, name, lat, lng, street="1 MAIN ST", boro="Chicago"):
            return {"id": i, "dba": name, "boro": boro, "street": street, "lat": lat, "lng": lng}
        return [r("200", "Joe's Pizza", "41.9", "-87.7", "2 B ST"),
                r("30", "JOES PIZZA", "41.8", "-87.6", "1 A ST"),
                r("5", "Nowhere", "0", "0"),
                r("6", "Far Away", "34.05", "-118.2"),
                r("7", "No Coordinates", None, None),
                r("8", "", "41.9", "-87.7")]

    def test_keys_are_the_boards_and_the_oldest_licence_is_first(self):
        out = locations.group_by_name(self.rows(), self.BOX)
        self.assertEqual(list(out), ["joes pizza"])
        self.assertEqual(out["joes pizza"][0], [41.8, -87.6, "1 A ST", "Chicago"])
        self.assertEqual(len(out["joes pizza"]), 2)

    def test_ungeocoded_and_out_of_area_rows_are_dropped(self):
        out = locations.group_by_name(self.rows(), locations.BOXES["FoodLosAngeles"])
        self.assertEqual(list(out), ["far away"])


if __name__ == "__main__":
    unittest.main()
