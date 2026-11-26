"""The ranking cache behind the ledger's pages (app/rankcache.py), and the
key ledger_page files each list under. No database: the queries are faked."""

import threading
import time
import unittest

from fakes import ROOT  # noqa: F401  (puts the repo root on sys.path)

from app import queries
from app.rankcache import RankCache


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Cache(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.cache = RankCache(ttl=60, max_entries=3, clock=self.clock)
        self.calls = []

    def compute(self, value):
        def run():
            self.calls.append(value)
            return value
        return run

    def test_a_value_is_computed_once_until_it_expires(self):
        self.assertEqual(self.cache.get("a", self.compute(1)), 1)
        self.clock.now += 59
        self.assertEqual(self.cache.get("a", self.compute(2)), 1)
        self.clock.now += 1
        self.assertEqual(self.cache.get("a", self.compute(3)), 3)
        self.assertEqual(self.calls, [1, 3])

    def test_it_keeps_at_most_max_entries_dropping_the_least_recently_used(self):
        for k in "abc":
            self.cache.get(k, self.compute(k))
        self.cache.get("a", self.compute("a again"))      # a is now the most recent
        self.cache.get("d", self.compute("d"))
        self.assertEqual(len(self.cache), 3)
        self.assertEqual(self.cache.get("a", self.compute("x")), "a")
        self.assertEqual(self.cache.get("b", self.compute("b2")), "b2")   # b was evicted

    def test_expired_entries_go_before_live_ones(self):
        self.cache.get("old", self.compute("old"))
        self.clock.now += 30
        self.cache.get("b", self.compute("b"))
        self.cache.get("c", self.compute("c"))
        self.clock.now += 31                                 # old has expired, b and c not
        self.cache.get("d", self.compute("d"))
        self.assertEqual(len(self.cache), 3)
        self.cache.get("b", self.compute("b2"))
        self.cache.get("c", self.compute("c2"))
        self.assertEqual(self.calls, ["old", "b", "c", "d"])

    def test_a_failure_is_not_cached(self):
        def boom():
            raise RuntimeError("statement timeout")
        with self.assertRaises(RuntimeError):
            self.cache.get("a", boom)
        self.assertEqual(self.cache.get("a", self.compute(1)), 1)

    def test_clear_forget_and_disable(self):
        self.cache.get("a", self.compute(1))
        self.cache.get("b", self.compute(2))
        self.cache.forget("a")
        self.assertEqual(self.cache.get("a", self.compute(3)), 3)
        self.cache.clear()
        self.assertEqual(len(self.cache), 0)
        self.cache.enabled = False
        self.cache.get("c", self.compute(4))
        self.cache.get("c", self.compute(5))
        self.assertEqual(self.calls, [1, 2, 3, 4, 5])
        self.assertEqual(len(self.cache), 0)

    def test_concurrent_requests_for_one_list_run_its_query_once(self):
        cache = RankCache(ttl=60, max_entries=8)
        started, release = threading.Event(), threading.Event()
        runs = []

        def slow():
            runs.append(1)
            started.set()
            release.wait(5)
            return "ranked"
        results = []
        threads = [threading.Thread(target=lambda: results.append(cache.get("k", slow)))
                   for _ in range(8)]
        for t in threads:
            t.start()
        started.wait(5)
        # Another list is not held up by the one being computed.
        t0 = time.monotonic()
        self.assertEqual(cache.get("other", lambda: "other"), "other")
        self.assertLess(time.monotonic() - t0, 1)
        release.set()
        for t in threads:
            t.join(5)
        self.assertEqual((len(runs), results), (1, ["ranked"] * 8))


def fake_db(rank_calls):
    """fetch_all for ledger_page: the ranking query is logged and returns
    three places; the rows query returns leaderboard columns for whatever
    keys it is asked for."""
    def fetch_all(conn, sql, params=()):
        if "= any(%(keys)s)" in sql:
            return [{"entity_key": k, "official_name": k.upper()} for k in params["keys"]]
        rank_calls.append(params)
        return [{"entity_key": f"p{i}", "current": 3 - i, "previous": i, "people": None}
                for i in range(3)]
    return fetch_all


class LedgerKey(unittest.TestCase):
    """Every argument that changes a list is part of its key; limit and
    offset, which only cut a page from it, are not."""

    BASE = dict(sub="FoodNYC", category="top", window=30, cuisine=None, borough=None,
                needs=[], flaws=[], algo="v1", topic=None)
    VARIANTS = dict(sub="FoodLosAngeles", category="gems", window=7, cuisine="Pizza",
                    borough="Brooklyn", needs=["value"], flaws=["wait"], algo="v2",
                    topic="omakase")

    def setUp(self):
        queries.LEDGER_CACHE.clear()
        self.addCleanup(queries.LEDGER_CACHE.clear)
        self.rank_calls = []
        self.fetch_all = fake_db(self.rank_calls)

    def page(self, limit=50, offset=0, **args):
        a = dict(self.BASE, **args)
        return queries.ledger_page(None, a["sub"], a["category"], a["window"], a["cuisine"],
                                   a["borough"], a["needs"], a["flaws"], limit, self.fetch_all,
                                   algo=a["algo"], topic=a["topic"], offset=offset)

    def test_the_pages_of_one_list_share_one_ranking(self):
        rows, total = self.page(limit=2)
        self.assertEqual(([r["entity_key"] for r in rows], total), (["p0", "p1"], 3))
        rows, total = self.page(limit=2, offset=2)
        self.assertEqual(([r["entity_key"] for r in rows], total), (["p2"], 3))
        self.assertEqual(rows[0]["official_name"], "P2")
        # Past the end: no rows, but the real size of the list.
        self.assertEqual(self.page(offset=10), ([], 3))
        self.assertEqual(len(self.rank_calls), 1)

    def test_every_argument_that_changes_the_list_has_its_own_entry(self):
        self.page()
        self.assertEqual(set(self.VARIANTS), set(self.BASE),
                         "a ledger_page argument has no variant here")
        for name, value in self.VARIANTS.items():
            before = len(self.rank_calls)
            self.page(**{name: value})
            self.assertEqual(len(self.rank_calls), before + 1,
                             f"{name}={value!r} was served another list's ranking")
        # Each now hits its own entry, never the base one.
        before = len(self.rank_calls)
        for name, value in self.VARIANTS.items():
            self.page(**{name: value})
        self.page()
        self.assertEqual(len(self.rank_calls), before)

    def test_the_order_of_needs_and_flaws_does_not_split_a_list(self):
        self.page(needs=["value", "service"], flaws=["wait", "food"])
        self.page(needs=["service", "value"], flaws=["food", "wait"])
        self.assertEqual(len(self.rank_calls), 1)

    def test_a_place_gone_from_the_board_makes_it_rank_again(self):
        self.page()
        real = self.fetch_all

        def board_lost_p1(conn, sql, params=()):
            rows = real(conn, sql, params)
            if "= any(%(keys)s)" in sql and len(self.rank_calls) == 1:
                rows = [r for r in rows if r["entity_key"] != "p1"]
            return rows
        self.fetch_all = board_lost_p1
        rows, total = self.page()
        self.assertEqual(([r["entity_key"] for r in rows], total), (["p0", "p1", "p2"], 3))
        self.assertEqual(len(self.rank_calls), 2)


if __name__ == "__main__":
    unittest.main()
