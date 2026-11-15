"""The other cities' restaurant lists: parsing, grouping, and the load the
poller starts (which needs the throwaway database, tests/pgtest.py). No network."""

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


def source(sub, calls, n=1, fail=None):
    """A faked source for `sub`: n places, or `fail` raised."""
    def fetch():
        calls.append(sub)
        if fail:
            raise fail
        return [C._row(f"{sub} Diner {i}", "Somewhere", "1 Main St", "00000", "Restaurant", "2026-01-01")
                for i in range(n)]
    return ("test source", fetch)


class EnsureLoaded(pgtest.PgCase):
    """The poller loads a city's list once, and never fetches for a city
    that has one. The sources are always faked."""

    def test_only_cities_with_a_source_and_no_rows_are_loaded(self):
        calls = []
        # SystemExit is what the Los Angeles source raises when its layer is gone.
        fake = {"chicagofood": source("chicagofood", calls), "FoodLosAngeles": source("FoodLosAngeles", calls),
                "austinfood": source("austinfood", calls, fail=OSError("source is down")),
                "FoodToronto": source("FoodToronto", calls, fail=SystemExit("no inventory was found"))}
        self.q("""insert into city_restaurants (subreddit, name, name_key, source)
                  values ('FoodLosAngeles', 'Already Here', 'already here', 'earlier') returning 1""")
        lines = []
        names = ["FoodNYC", "FoodLosAngeles", "FoodSanDiego", "austinfood", "chicagofood", "FoodToronto"]
        with mock.patch.object(C, "SOURCES", fake), mock.patch.object(C, "MIN_NAMES", 1):
            self.assertEqual(C.ensure_loaded(names, connect=pgtest.connect, log=lines.append), {"chicagofood": 1})
            # Los Angeles has rows, San Diego and New York have no source here, Austin's and Toronto's are down.
            self.assertEqual(calls, ["austinfood", "chicagofood", "FoodToronto"])
            for sub in ("austinfood", "FoodToronto"):
                self.assertTrue(any(f"r/{sub}: LIST NOT LOADED" in line for line in lines), sub)
            self.assertEqual(C.ensure_loaded(["chicagofood", "FoodLosAngeles"], connect=pgtest.connect,
                                             log=lines.append), {})
            self.assertEqual(calls, ["austinfood", "chicagofood", "FoodToronto"])       # nothing fetched again
        self.assertEqual(sorted(self.q("select subreddit, name from city_restaurants")),
                         [("FoodLosAngeles", "Already Here"), ("chicagofood", "chicagofood Diner 0")])

    def test_a_list_too_short_to_be_a_city_is_not_loaded(self):
        # A source that answers with nothing, or a page of it, is a failure:
        # loaded, it would count as the city's list on every later boot.
        calls, lines = [], []
        fake = {"chicagofood": source("chicagofood", calls, n=0), "austinfood": source("austinfood", calls, n=3)}
        with mock.patch.object(C, "SOURCES", fake), mock.patch.object(C, "MIN_NAMES", 5):
            self.assertEqual(C.ensure_loaded(["chicagofood", "austinfood"], connect=pgtest.connect,
                                             log=lines.append), {})
        self.assertEqual(self.q("select count(*) from city_restaurants"), [(0,)])
        self.assertEqual(sum("LIST NOT LOADED (TooFew" in line for line in lines), 2)

    def test_the_callers_connection_is_never_used(self):
        # The poller's own connection is not passed in at all; the ones
        # opened here are closed again, none held across a download.
        opened = []

        def connect():
            opened.append(pgtest.connect())
            return opened[-1]

        def fetch():
            self.assertTrue(all(c.closed for c in opened))
            return [C._row("A Diner", "Somewhere", "1 Main St", "00000", None, None)]
        with mock.patch.object(C, "SOURCES", {"chicagofood": ("test source", fetch)}), \
                mock.patch.object(C, "MIN_NAMES", 1):
            self.assertEqual(C.ensure_loaded(["chicagofood"], connect=connect, log=lambda _: None),
                             {"chicagofood": 1})
        self.assertEqual(len(opened), 2)
        self.assertTrue(all(c.closed for c in opened))


class Unreachable(unittest.TestCase):
    """No database: the load must survive one that cannot be reached."""

    def test_a_database_that_is_down_is_logged_and_nothing_is_fetched(self):
        calls, lines = [], []

        def connect():
            raise OSError("connection refused")
        with mock.patch.object(C, "SOURCES", {"chicagofood": source("chicagofood", calls)}):
            self.assertEqual(C.ensure_loaded(["chicagofood"], connect=connect, log=lines.append), {})
        self.assertEqual(calls, [])
        self.assertIn("could not see which lists are missing", lines[0])

    def test_a_connection_lost_before_the_load_costs_only_that_city(self):
        calls, lines = [], []
        conns = [mock.MagicMock()]
        conns[0].cursor.return_value.__enter__.return_value.fetchall.return_value = []

        def connect():
            if conns:
                return conns.pop()
            raise OSError("connection refused")
        fake = {"chicagofood": source("chicagofood", calls), "austinfood": source("austinfood", calls)}
        with mock.patch.object(C, "SOURCES", fake), mock.patch.object(C, "MIN_NAMES", 1):
            self.assertEqual(C.ensure_loaded(["chicagofood", "austinfood"], connect=connect, log=lines.append), {})
        self.assertEqual(calls, ["chicagofood", "austinfood"])
        self.assertEqual(sum("LIST NOT LOADED (OSError" in line for line in lines), 2)


if __name__ == "__main__":
    unittest.main()
