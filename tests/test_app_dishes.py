"""The dish list of a place page (app/dishes.py): groups from a file, the
plural fallback for everything else, and counting by distinct mention.
No database: the grouping is pure, and the query is faked."""

import json
import os
import tempfile
import unittest
from unittest import mock

from fakes import ROOT  # noqa: F401  (puts the repo root on sys.path)

from app import dishes, queries

SUB = "FoodNYC"
FILE = {"katzs delicatessen": {
    "groups": [{"label": "Pastrami sandwich", "names": ["pastrami", "pastrami sandwich", "Pastrami on  Rye"]}],
    "drop": ["sandwich", "bread"],
}}


def rows(*mentions, times=1):
    return [list(m) for m in mentions for _ in range(times)]


class Dishes(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.dict(dishes._GROUPS, {SUB: FILE}, clear=True)
        patch.start()
        self.addCleanup(patch.stop)

    def top(self, data, key="katzs delicatessen"):
        return dishes.top(data, SUB, key)

    def test_plurals_fold_on_the_last_word(self):
        data = rows(["Burritos"], ["burrito"], ["BURRITOS "], ["ribs"], ["Short rib"], ["rib"],
                    ["sandwiches"], ["Sandwich"], ["sandwich"])
        got = self.top(data, "nowhere")
        self.assertEqual({d["name"]: d["n"] for d in got}, {"burritos": 3, "sandwich": 3})

    def test_what_is_not_a_plural_is_left_alone(self):
        for name in ("fries", "swiss", "hummus", "gas", "pastrami"):
            self.assertEqual(dishes.fold(name), name)
        self.assertEqual(dishes.fold("ribs"), "rib")
        self.assertEqual(dishes.fold("pork buns"), "pork bun")
        self.assertEqual(dishes.fold("sandwiches"), "sandwich")

    def test_a_fallback_name_shows_as_its_commonest_spelling(self):
        got = self.top(rows(["Egg Rolls"], ["egg rolls"], ["egg roll"]), "nowhere")
        self.assertEqual(got, [{"name": "egg rolls", "n": 3}])

    def test_a_group_counts_each_mention_once(self):
        # One comment naming two of the group's names is still one mention.
        data = rows(["pastrami", "pastrami sandwich"], ["pastrami on rye"], ["Pastrami"])
        self.assertEqual(self.top(data), [{"name": "Pastrami sandwich", "n": 3}])

    def test_a_dropped_name_is_not_counted(self):
        data = rows(["sandwich", "bread", "knish"], times=4)
        self.assertEqual(self.top(data), [{"name": "knish", "n": 4}])

    def test_a_dish_needs_three_mentions(self):
        data = rows(["knish"], ["knish"], ["latke"], ["latke"], ["latke"])
        self.assertEqual(self.top(data), [{"name": "latke", "n": 3}])

    def test_a_place_without_an_entry_uses_the_fallback(self):
        data = rows(["sandwich", "pastrami"], times=3)
        self.assertEqual({d["name"] for d in self.top(data, "other place")}, {"sandwich", "pastrami"})

    def test_a_missing_file_is_the_fallback_alone(self):
        dishes._GROUPS.clear()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(dishes, "DATA", d):
            got = dishes.top(rows(["tacos"], times=3), "NoSuchCity", "x")
        self.assertEqual(got, [{"name": "tacos", "n": 3}])

    def test_a_file_is_read_from_the_data_directory(self):
        dishes._GROUPS.clear()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(dishes, "DATA", d):
            with open(os.path.join(d, "dish_groups_FoodNYC.json"), "w") as f:
                json.dump(FILE, f)
            got = dishes.top(rows(["pastrami", "bread"], times=3), SUB, "katzs delicatessen")
        self.assertEqual(got, [{"name": "Pastrami sandwich", "n": 3}])

    def test_most_fifteen_and_ties_are_stable(self):
        data = rows(*[[f"dish{i:02d}"] for i in range(20)], times=3)
        got = self.top(data, "nowhere")
        self.assertEqual(len(got), 15)
        self.assertEqual(got[0]["name"], "dish00")

    def test_a_non_string_in_the_array_is_skipped(self):
        self.assertEqual(self.top(rows(["taco", 5, None], times=3), "x"), [{"name": "taco", "n": 3}])


class TopDishesQuery(unittest.TestCase):
    def test_the_query_feeds_each_mentions_array_to_the_grouping(self):
        seen = {}

        def fake(conn, sql, params=()):
            seen["params"] = params
            return [{"dishes": ["tacos"]}] * 3

        with mock.patch.dict(dishes._GROUPS, {SUB: {}}, clear=True):
            got = queries.top_dishes(None, SUB, "x", fake)
        self.assertEqual(got, [{"name": "tacos", "n": 3}])
        self.assertEqual(seen["params"], (SUB, "x"))


if __name__ == "__main__":
    unittest.main()
