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
FILE = {
    "katzs delicatessen": {
        "groups": [{"label": "Pastrami sandwich", "names": ["pastrami", "pastrami sandwich", "Pastrami on  Rye"]},
                   {"label": "Spare ribs", "names": ["spare ribs", "ribs"]}],
        "drop": ["sandwich", "bagels", "bread"],
    },
}


def rows(*mentions, times=1):
    return [list(m) for m in mentions for _ in range(times)]


def built(data):
    """What the module makes of a file with these contents, in a temp directory."""
    with tempfile.TemporaryDirectory() as d, mock.patch.object(dishes, "DATA", d), \
            mock.patch.dict(dishes._PLACES, clear=True):
        with open(os.path.join(d, f"dish_groups_{SUB}.json"), "w") as f:
            json.dump(data, f)
        return dishes.groups(SUB, "katzs delicatessen")


class Dishes(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.dict(dishes._PLACES, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        # Load the fixture through the real path: a file in a temp directory.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with open(os.path.join(tmp.name, f"dish_groups_{SUB}.json"), "w") as f:
            json.dump(FILE, f)
        data = mock.patch.object(dishes, "DATA", tmp.name)
        data.start()
        self.addCleanup(data.stop)

    def top(self, data, key="katzs delicatessen", sub=SUB):
        return dishes.top(data, sub, key)

    def test_plurals_fold_on_the_last_word(self):
        data = rows(["Burritos"], ["burrito"], ["BURRITOS "], ["ribs"], ["Short rib"], ["rib"],
                    ["sandwiches"], ["Sandwich"], ["sandwich"])
        got = self.top(data, "nowhere")
        self.assertEqual({d["name"].lower(): d["n"] for d in got}, {"burritos": 3, "sandwich": 3})

    def test_words_and_their_plurals_meet(self):
        for one, many in [("quiche", "quiches"), ("cookie", "cookies"), ("pie", "pies"),
                          ("patty", "patties"), ("curry", "curries"), ("sandwich", "sandwiches"),
                          ("spare rib", "spare ribs"), ("tomato", "tomatoes")]:
            self.assertEqual(dishes.fold(one), dishes.fold(many), (one, many))

    def test_what_is_not_a_plural_is_left_alone(self):
        for name in ("fries", "hummus", "couscous", "swiss", "gas", "pastrami"):
            self.assertEqual(dishes.fold(name), name)
        # The key of "tres leches" is never shown, but it must not collide with a different dish.
        self.assertNotEqual(dishes.fold("tres leches"), dishes.fold("tres"))
        got = self.top(rows(["Tres Leches"], times=3), "nowhere")
        self.assertEqual(got, [{"name": "Tres Leches", "n": 3}])

    def test_a_fallback_name_shows_as_typed_and_most_common(self):
        got = self.top(rows(["BLT"], ["BLT"], ["blts"]), "nowhere")
        self.assertEqual(got, [{"name": "BLT", "n": 3}])
        got = self.top(rows(["Big  Mac "], times=3), "nowhere")
        self.assertEqual(got, [{"name": "Big Mac", "n": 3}])
        got = self.top(rows(["Egg Rolls"], ["egg rolls"], ["egg rolls"]), "nowhere")
        self.assertEqual(got, [{"name": "egg rolls", "n": 3}])

    def test_a_group_counts_each_mention_once(self):
        # One comment naming two of the group's names is still one mention.
        data = rows(["pastrami", "pastrami sandwich"], ["pastrami on rye"], ["Pastrami"])
        self.assertEqual(self.top(data), [{"name": "Pastrami sandwich", "n": 3}])

    def test_a_new_singular_or_plural_of_a_grouped_name_joins_the_group(self):
        data = rows(["spare rib"], ["Spare Ribs"], ["rib"], ["pastrami sandwiches"])
        self.assertEqual(self.top(data), [{"name": "Spare ribs", "n": 3}])

    def test_a_new_singular_or_plural_of_a_dropped_name_is_dropped(self):
        data = rows(["bagel", "sandwiches", "breads", "knish"], times=3)
        self.assertEqual(self.top(data), [{"name": "knish", "n": 3}])

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
        got = self.top(rows(["tacos"], times=3), "x", "NoSuchCity")
        self.assertEqual(got, [{"name": "tacos", "n": 3}])

    def test_most_fifteen_and_ties_break_on_the_lowercase_key(self):
        data = rows(["Zed"], ["apple"], ["Banana"], times=3)
        self.assertEqual([d["name"] for d in self.top(data, "nowhere")], ["apple", "Banana", "Zed"])
        data = rows(*[[f"dish{i:02d}"] for i in range(20)], times=3)
        got = self.top(data, "nowhere")
        self.assertEqual(len(got), 15)
        self.assertEqual(got[0]["name"], "dish00")

    def test_a_non_string_in_the_array_is_skipped(self):
        self.assertEqual(self.top(rows(["taco", 5, None, "  "], times=3), "x"), [{"name": "taco", "n": 3}])

    def test_a_file_is_read_once(self):
        self.top(rows(["taco"]))
        with mock.patch.object(dishes.jsonfile, "load", side_effect=AssertionError("read again")):
            self.top(rows(["taco"]))


class Malformed(unittest.TestCase):
    """A file that parses but has the wrong shape costs the place its groups, not the page."""

    def test_a_top_level_that_is_not_an_object(self):
        self.assertEqual(built(["katzs delicatessen"]), ({}, set()))

    def test_an_entry_that_is_not_an_object(self):
        self.assertEqual(built({"katzs delicatessen": ["a"]}), ({}, set()))

    def test_groups_or_drop_that_are_not_lists(self):
        self.assertEqual(built({"katzs delicatessen": {"groups": {"label": "x"}}}), ({}, set()))
        self.assertEqual(built({"katzs delicatessen": {"drop": "bread"}}), ({}, set()))
        self.assertEqual(built({"katzs delicatessen": {"drop": [1]}}), ({}, set()))

    def test_a_bad_group_is_skipped_and_the_rest_kept(self):
        labels, dropped = built({"katzs delicatessen": {
            "groups": [{"label": "", "names": ["a"]}, {"label": "B", "names": "b"}, "c",
                       {"label": "Knish", "names": ["knishes"]}],
            "drop": ["bread"]}})
        self.assertEqual(labels, {"knish": "Knish"})
        self.assertEqual(dropped, {"bread"})

    def test_a_name_both_grouped_and_dropped_is_refused(self):
        # "cookie" and "cookies" are one key: top() would drop what the
        # group meant to count, so the entry is refused, not half applied.
        with self.assertLogs("uvicorn.error", "WARNING") as logs:
            got = built({"katzs delicatessen": {
                "groups": [{"label": "Chocolate chip cookie", "names": ["cookie"]}],
                "drop": ["Cookies"]}})
        self.assertEqual(got, ({}, set()))
        self.assertIn("grouped and dropped: 'cooky' (in 'Chocolate chip cookie')", logs.output[0])

    def test_a_name_in_two_groups_is_refused(self):
        with self.assertLogs("uvicorn.error", "WARNING") as logs:
            got = built({"katzs delicatessen": {
                "groups": [{"label": "Pastrami sandwich", "names": ["sandwich"]},
                           {"label": "Reuben", "names": ["sandwiches"]}]}})
        self.assertEqual(got, ({}, set()))
        self.assertIn("'Pastrami sandwich' and 'Reuben'", logs.output[0])
        # Twice in one group is only untidy.
        self.assertEqual(built({"katzs delicatessen": {
            "groups": [{"label": "Knish", "names": ["knish", "knishes"]}]}}), ({"knish": "Knish"}, set()))

    def test_a_bad_entry_does_not_take_its_neighbours_down(self):
        data = {"bad": 5, "katzs delicatessen": {"groups": [], "drop": ["bread"]}}
        self.assertEqual(built(data), ({}, {"bread"}))

    def test_a_malformed_file_still_answers_with_the_fallback(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(dishes, "DATA", d), \
                mock.patch.dict(dishes._PLACES, clear=True):
            with open(os.path.join(d, f"dish_groups_{SUB}.json"), "w") as f:
                json.dump({"x": {"groups": 3}}, f)
            self.assertEqual(dishes.top(rows(["tacos"], times=3), SUB, "x"), [{"name": "tacos", "n": 3}])


class Shipped(unittest.TestCase):
    """The files in app/data, as the loader reads them. An entry it refuses
    costs a real place its groups, so one is a failure here."""

    def test_every_entry_of_every_city_loads(self):
        import subreddits
        for sub in subreddits.SUBREDDITS:
            path = dishes._path(sub)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            with self.subTest(sub=sub), self.assertNoLogs("uvicorn.error", "WARNING"):
                self.assertEqual(len(dishes._build(path)), len(data))

    def test_the_four_names_that_were_grouped_and_dropped(self):
        def top(sub, key, *names):
            return dishes.top(rows(*[[n] for n in names], times=3), sub, key)
        with mock.patch.dict(dishes._PLACES, clear=True):
            # One cookie and one salad on the list: the bare word is that dish.
            self.assertEqual(top("FoodNYC", "from lucie", "cookies", "cookie"),
                             [{"name": "Chocolate chip cookie", "n": 6}])
            self.assertEqual(top("chicagofood", "portillos", "salads"),
                             [{"name": "Chopped salad", "n": 3}])
            # Two cookies, three chowders: the bare word is none of them.
            self.assertEqual(top("austinfood", "thorough bread", "cookie", "cookies"), [])
            self.assertEqual(top("FoodLosAngeles", "connie teds", "chowder", "chowders", "clam chowder"),
                             [{"name": "New England clam chowder", "n": 3}])


class TopDishesQuery(unittest.TestCase):
    def test_the_query_feeds_each_mentions_array_to_the_grouping(self):
        seen = {}

        def fake(conn, sql, params=()):
            seen["params"] = params
            return [{"dishes": ["tacos"]}] * 3

        with mock.patch.dict(dishes._PLACES, {SUB: {}}, clear=True):
            got = queries.top_dishes(None, SUB, "x", fake)
        self.assertEqual(got, [{"name": "tacos", "n": 3}])
        self.assertEqual(seen["params"], (SUB, "x"))


if __name__ == "__main__":
    unittest.main()
