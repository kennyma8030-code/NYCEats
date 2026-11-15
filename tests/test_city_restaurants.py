"""The other cities' restaurant lists: parsing, grouping, and the load at
boot (which needs the throwaway database, tests/pgtest.py). No network."""

import os
import unittest
from unittest import mock

from fakes import ROOT
import pgtest

import city_restaurants as C
import restaurants
import subreddits


class Table(unittest.TestCase):
    def test_schema_sql_creates_the_table_the_loader_creates(self):
        with open(os.path.join(ROOT, "schema.sql"), encoding="utf-8") as f:
            self.assertIn(C.TABLE_SQL, f.read().replace("\r\n", "\n"))

    def test_new_york_is_not_loaded_here(self):
        self.assertNotIn(subreddits.HOME, C.SOURCES)
        for sub in C.SOURCES:
            subreddits.city(sub)


class Addresses(unittest.TestCase):
    def test_austin_splits_street_city_and_zip(self):
        self.assertEqual(C.austin_address("4301 W William Cannon Dr Ste B180 Austin, TX 78749-1480"),
                         ("4301 W William Cannon Dr Ste B180", "Austin", "78749"))
        self.assertEqual(C.austin_address("11200 Lakeline Mall Dr Cedar Park, TX 78613-1500"),
                         ("11200 Lakeline Mall Dr", "Cedar Park", "78613"))
        self.assertEqual(C.austin_address("8500 E US 290 HWY WB SVRD AUSTIN, TX 78754"),
                         ("8500 E US 290 HWY WB SVRD", "Austin", "78754"))
        self.assertEqual(C.austin_address("somewhere unparsed"), ("somewhere unparsed", None, None))

    def test_toronto_drops_the_unit_placeholder_and_keeps_the_postal_code(self):
        self.assertEqual(C.toronto_address("1871 O'Connor Dr None M4A 1X1"), ("1871 O'Connor Dr", "M4A 1X1"))
        self.assertEqual(C.toronto_address("100 Queen St W 2 M5H 2N2"), ("100 Queen St W 2", "M5H 2N2"))
        self.assertEqual(C.toronto_address("no postal code"), ("no postal code", None))


class Rows(unittest.TestCase):
    def test_branches_collapse_to_one_name_and_a_dozen_is_a_chain(self):
        places = [C._row("Joe's Pizza", "Chicago", f"{n} W Madison St", "60601", "Restaurant", "2026-01-0%d" % (n % 9 + 1))
                  for n in range(C.CHAIN_LOCATIONS)] + [C._row("JOES PIZZA #2", "Evanston", "1 Main St", "60201", "Restaurant", None),
                                                        C._row("Solo Cafe", "Chicago", "5 State St", "60601", None, "2025-05-05")]
        rows = {r[2]: r for r in C.rows_for("chicagofood", "test", restaurants.group_by_name(places))}
        self.assertEqual(set(rows), {"joes pizza", "joes pizza 2", "solo cafe"})
        sub, name, key, category, areas, n, _addresses, chain, last, source = rows["joes pizza"]
        self.assertEqual((sub, name, category, areas, n, chain, last, source),
                         ("chicagofood", "Joe's Pizza", "Restaurant", ["Chicago"], C.CHAIN_LOCATIONS, True, "2026-01-09", "test"))
        self.assertEqual(rows["solo cafe"][3:9], (None, ["Chicago"], 1, rows["solo cafe"][6], False, "2025-05-05"))
        self.assertIsNone(rows["joes pizza 2"][8])                    # no inspection date is no date, not ""


class EnsureLoaded(pgtest.PgCase):
    """The poller's boot loads a city's list once, and never fetches for a
    city that has one. The sources are always faked."""

    def test_only_cities_with_a_source_and_no_rows_are_loaded(self):
        calls = []

        def source(sub, fail=False):
            def fetch():
                calls.append(sub)
                if fail:
                    raise OSError("source is down")
                return [C._row(f"{sub} Diner", "Somewhere", "1 Main St", "00000", "Restaurant", "2026-01-01")]
            return ("test source", fetch)

        fake = {"chicagofood": source("chicagofood"), "austinfood": source("austinfood", fail=True),
                "FoodLosAngeles": source("FoodLosAngeles")}
        self.q("""insert into city_restaurants (subreddit, name, name_key, source)
                  values ('FoodLosAngeles', 'Already Here', 'already here', 'earlier') returning 1""")
        lines = []
        names = ["FoodNYC", "FoodLosAngeles", "FoodSanDiego", "austinfood", "chicagofood"]
        with mock.patch.object(C, "SOURCES", fake):
            self.assertEqual(C.ensure_loaded(self.conn, names, log=lines.append), {"chicagofood": 1})
            # Los Angeles has rows, San Diego and New York have no source here, Austin's is down.
            self.assertEqual(calls, ["austinfood", "chicagofood"])
            self.assertTrue(any("r/austinfood: could not load" in line for line in lines))
            self.assertEqual(C.ensure_loaded(self.conn, ["chicagofood", "FoodLosAngeles"], log=lines.append), {})
            self.assertEqual(calls, ["austinfood", "chicagofood"])       # nothing fetched again
        self.assertEqual(sorted(self.q("select subreddit, name from city_restaurants")),
                         [("FoodLosAngeles", "Already Here"), ("chicagofood", "chicagofood Diner")])


if __name__ == "__main__":
    unittest.main()
