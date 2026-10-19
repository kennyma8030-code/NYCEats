"""Paging forward through Arctic Shift without losing a comment at a page edge,
and the boot backfill's scope and disk guard. Arctic Shift and Postgres are
faked; no network, no database.

Arctic's `after` is exclusive. Paging with after = the last page's newest
second drops every comment from that second that did not fit on the page.
"""

import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

import fakes  # noqa: F401  (puts the repo root on sys.path)

import arctic
import backfill
import subreddits


# Times are offsets from T, a real 2023 timestamp: Arctic Shift rejects an
# `after` that is not a plausible date (checked live: -1, 0 and 1 answer
# HTTP 400 "'after' must be a valid date"; 1000000000 is accepted), and the
# fakes below do the same.
T = 1_700_000_000
MIN_AFTER = 1_000_000_000


def check_after(after):
    if after is not None and after < MIN_AFTER:
        raise AssertionError(f"Arctic answers 400 for after={after}")


def item(i, t, sub="chicagofood", link="t3_x"):
    return {"id": f"c{i:05d}", "created_utc": T + t, "subreddit": sub, "link_id": link,
            "parent_id": link, "body": "b"}


class Asc:
    """search_page over a fixed list: oldest first, `after` exclusive, 100 a page."""

    def __init__(self, items):
        self.items = sorted(items, key=lambda x: (x["created_utc"], x["id"]))
        self.calls = []

    def __call__(self, after):
        check_after(after)
        self.calls.append(after)
        return [x for x in self.items
                if after is None or x["created_utc"] > after][:arctic.PAGE]


def ties(n, per_second=3, start=1_000):
    """n items, `per_second` to a second, so page edges (every 100) fall inside a second."""
    return [item(i, start + i // per_second) for i in range(n)]


class Forward(unittest.TestCase):
    def collect(self, items, start):
        fake = Asc(items)
        with redirect_stdout(io.StringIO()):
            got = [x for fresh, _ in arctic.forward(fake, start) for x in fresh]
        return got, fake

    def test_same_second_ties_at_every_page_edge(self):
        items = ties(350)
        got, fake = self.collect(items, T + 1_000)
        self.assertEqual(sorted(x["id"] for x in got), sorted(x["id"] for x in items))
        self.assertEqual(len(got), len({x["id"] for x in got}), "an item came back twice")

    def test_the_old_exclusive_cursor_lost_them(self):
        # What backfill.py and arctic.all_thread_comments did: after = newest.
        items, fake, seen, after = ties(350), None, set(), T + 999
        fake = Asc(items)
        while True:
            page = fake(after)
            if not page:
                break
            seen |= {x["id"] for x in page}
            newest = max(x["created_utc"] for x in page)
            if newest <= after:
                break
            after = newest
        self.assertLess(len(seen), 350)

    def test_start_is_inclusive(self):
        got, fake = self.collect([item(1, 1_000), item(2, 1_001)], T + 1_000)
        self.assertEqual([x["id"] for x in got], ["c00001", "c00002"])
        self.assertEqual(fake.calls[0], T + 999)

    def test_open_start_sends_no_after(self):
        got, fake = self.collect([item(1, 1_000), item(2, 1_001)], None)
        self.assertEqual(len(got), 2)
        self.assertIsNone(fake.calls[0])

    def test_fake_rejects_what_arctic_rejects(self):
        for bad in (-1, 0, 1):
            with self.assertRaises(AssertionError):
                Asc([])(bad)

    def test_more_than_a_page_in_one_second_ends(self):
        # 150 items in one second: the first 100 are reachable, the rest are
        # not (the API pages by time only). It must move on, not spin.
        items = [item(i, 2_000) for i in range(150)] + [item(1_000 + i, 2_001 + i) for i in range(5)]
        got, fake = self.collect(items, T + 1_000)
        ids = {x["id"] for x in got}
        self.assertEqual(len(ids), 105)
        self.assertTrue({f"c{1_000 + i:05d}" for i in range(5)} <= ids)
        self.assertLess(len(fake.calls), 10)

    def test_whole_page_in_one_second_then_more(self):
        # Exactly a page in the boundary second, then the next second.
        items = [item(i, 2_000) for i in range(100)] + [item(500 + i, 2_001) for i in range(30)]
        got, _ = self.collect(items, T + 2_000)
        self.assertEqual(len({x["id"] for x in got}), 130)

    def test_all_thread_comments_keeps_ties(self):
        items = ties(250)
        sent = []

        def get(path, params):
            sent.append(dict(params))
            return Asc(items)(params.get("after"))
        with mock.patch.object(arctic, "_get", get), mock.patch.object(arctic.time, "sleep"):
            got = arctic.all_thread_comments("x")
        self.assertEqual(len(got), 250)
        # The first request asks from the thread's beginning by leaving
        # `after` out: any small number there is a 400.
        self.assertEqual(sent[0], {"link_id": "x", "limit": arctic.PAGE, "sort": "asc"})
        self.assertTrue(all(p["after"] >= MIN_AFTER for p in sent[1:]))


class BackfillComments(unittest.TestCase):
    """The sweep itself: every tie stored, the cursor at the newest, resumable."""

    def sweep(self, items, cursor, sub="FoodNYC"):
        fake = Asc(items)
        stored = {}
        db = mock.Mock()
        db.get_cursor.return_value = cursor
        db.database_size_mb.return_value = 100.0
        db.insert_comments.side_effect = lambda conn, cs: (stored.update({c["id"]: c for c in cs}),
                                                            len(cs))[1]
        with mock.patch.object(backfill.arctic, "search_page",
                               lambda kind, s, after=None: fake(after)), \
                mock.patch.object(backfill.ingest, "ensure_threads",
                                  side_effect=lambda conn, page, pause: (page, 0, set())), \
                mock.patch.object(backfill, "db", db), mock.patch.object(backfill.time, "sleep"), \
                redirect_stdout(io.StringIO()):
            backfill.backfill_comments(mock.Mock(), sub, 0, pause=0)
        return stored, db, fake

    def test_every_tie_is_stored(self):
        items = ties(350)
        stored, db, _ = self.sweep(items, T + 1_000)
        self.assertEqual(set(stored), {x["id"] for x in items})
        self.assertEqual(db.set_cursor.call_args.args[-1], max(x["created_utc"] for x in items))

    def test_resume_rereads_the_cursor_second(self):
        # A run stopped with cursor 1_010; comments at 1_010 that the last
        # page did not hold must still come in.
        items = ties(60)
        stored, _, fake = self.sweep(items, T + 1_010)
        self.assertEqual(fake.calls[0], T + 1_009)
        self.assertTrue({x["id"] for x in items if x["created_utc"] >= T + 1_010} <= set(stored))

    def test_posts_pass_keeps_ties_too(self):
        items = ties(250)
        fake = Asc(items)
        stored = {}
        db = mock.Mock()
        db.get_cursor.return_value = T + 1_000
        db.insert_threads.side_effect = lambda conn, ps: (stored.update({p["id"]: p for p in ps}),
                                                           len(ps))[1]
        with mock.patch.object(backfill.arctic, "search_page",
                               lambda kind, s, after=None: fake(after)), \
                mock.patch.object(backfill, "db", db), mock.patch.object(backfill.time, "sleep"), \
                redirect_stdout(io.StringIO()):
            backfill.backfill_posts(mock.Mock(), "FoodNYC", 0, pause=0)
        self.assertEqual(len(stored), 250)


class Scope(unittest.TestCase):
    def scope(self, env, home_years=None, only=None):
        with redirect_stdout(io.StringIO()) as out:
            got = backfill.scope(home_years, only, env=env)
        return got, out.getvalue()

    def test_default_is_home_only(self):
        (names, years), _ = self.scope({})
        self.assertEqual(names, [subreddits.HOME])
        self.assertEqual(years, {subreddits.HOME: None})

    def test_listing_a_city_is_not_enough_without_years(self):
        (names, _), out = self.scope({"BACKFILL_SUBREDDITS": "all"})
        self.assertEqual(names, [subreddits.HOME])
        self.assertIn("BACKFILL_YEARS_OTHER is 0", out)

    def test_opted_in(self):
        (names, years), _ = self.scope({"BACKFILL_SUBREDDITS": "chicagofood, FoodNYC",
                                        "BACKFILL_YEARS_OTHER": "2"}, home_years=5)
        self.assertEqual(names, ["FoodNYC", "chicagofood"])
        self.assertEqual(years, {"FoodNYC": 5, "chicagofood": 2.0})
        (_, years), _ = self.scope({"BACKFILL_SUBREDDITS": "all", "BACKFILL_YEARS_OTHER": "all"})
        self.assertIsNone(years["FoodToronto"])

    def test_subreddit_flag_narrows(self):
        (names, _), _ = self.scope({"BACKFILL_SUBREDDITS": "all", "BACKFILL_YEARS_OTHER": "1"},
                                   only=["denverfood"])
        self.assertEqual(names, ["denverfood"])

    def test_bad_values_fail_the_boot(self):
        with self.assertRaises(SystemExit):
            self.scope({"BACKFILL_SUBREDDITS": "FoodBoston"})
        with self.assertRaises(SystemExit):
            self.scope({"BACKFILL_YEARS_OTHER": "lots"})


class Parse(unittest.TestCase):
    def test_defaults_all_and_spelling(self):
        self.assertEqual(subreddits.parse(None, ("x",)), ["x"])
        self.assertEqual(subreddits.parse("  ", ("x",)), ["x"])
        self.assertEqual(subreddits.parse("ALL", ()), list(subreddits.SUBREDDITS))
        # Our spelling and our order, whatever was typed.
        self.assertEqual(subreddits.parse("r/AustinFood,foodnyc", ()), ["FoodNYC", "austinfood"])


class Disk(unittest.TestCase):
    def test_home_is_never_stopped(self):
        db = mock.Mock()
        db.database_size_mb.return_value = 10_000.0
        with mock.patch.object(backfill, "db", db):
            backfill.check_disk(None, subreddits.HOME)
        db.database_size_mb.assert_not_called()

    def test_other_city_stops_past_the_limit(self):
        db = mock.Mock()
        db.database_size_mb.return_value = 3_600.0
        with mock.patch.object(backfill, "db", db), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BACKFILL_MAX_DB_MB", None)
            with self.assertRaises(backfill.DiskBudget):
                backfill.check_disk(None, "chicagofood")
            with mock.patch.dict(os.environ, {"BACKFILL_MAX_DB_MB": "4000"}):
                backfill.check_disk(None, "chicagofood")

    def test_sweep_checks_while_it_goes(self):
        # Fine at the start, over the line ten pages in: the sweep stops there.
        items = [item(i, 1_000 + i) for i in range(5_000)]
        fake = Asc(items)
        db = mock.Mock()
        db.get_cursor.return_value = T + 1_000
        db.database_size_mb.side_effect = [100.0, 5_000.0]
        db.insert_comments.return_value = 100
        db.fill_tree.return_value = 0
        with mock.patch.object(backfill.arctic, "search_page",
                               lambda kind, s, after=None: fake(after)), \
                mock.patch.object(backfill.ingest, "ensure_threads",
                                  side_effect=lambda conn, page, pause: (page, 0, set())), \
                mock.patch.object(backfill, "db", db), mock.patch.object(backfill.time, "sleep"), \
                redirect_stdout(io.StringIO()):
            with self.assertRaises(backfill.DiskBudget):
                backfill.backfill_comments(mock.Mock(), "chicagofood", 0, pause=0)
        self.assertEqual(len(fake.calls), backfill.DISK_EVERY)

    def test_run_all_stops_other_cities_but_not_home(self):
        calls = []

        def run(conn, name, years=None):
            calls.append(name)
            if name == "chicagofood":
                raise backfill.DiskBudget("database is 3,600 MB")
        with mock.patch.object(backfill, "run", run), mock.patch.object(backfill.time, "sleep"), \
                redirect_stdout(io.StringIO()) as out:
            failed = backfill.run_all(mock.Mock(closed=0), ["chicagofood", "FoodNYC", "denverfood"],
                                      retry_after=0)
        self.assertEqual(calls, ["chicagofood", "FoodNYC"])
        self.assertEqual(failed, ["chicagofood", "denverfood"])
        self.assertIn("STOPPED", out.getvalue())

    def test_years_per_city(self):
        got = []
        with mock.patch.object(backfill, "run", lambda c, n, y=None: got.append((n, y))), \
                redirect_stdout(io.StringIO()):
            backfill.run_all(mock.Mock(), ["FoodNYC", "chicagofood"],
                             {"FoodNYC": None, "chicagofood": 2.0}, retry_after=0)
        self.assertEqual(got, [("FoodNYC", None), ("chicagofood", 2.0)])


if __name__ == "__main__":
    unittest.main()
