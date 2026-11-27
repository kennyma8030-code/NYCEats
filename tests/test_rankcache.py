"""The ranking cache behind the ledger's pages (app/rankcache.py), and how
ledger_page uses it. No database: the queries are faked."""

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
        self.cache = RankCache(ttl=60, max_entries=3, wait=5, clock=self.clock)
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

    def test_peek_never_computes_and_clear_empties(self):
        self.assertIsNone(self.cache.peek("a"))
        self.cache.get("a", self.compute(1))
        self.assertEqual(self.cache.peek("a"), 1)
        self.clock.now += 60
        self.assertIsNone(self.cache.peek("a"))
        self.cache.get("b", self.compute(2))
        self.cache.clear()
        self.assertEqual((len(self.cache), self.calls), (0, [1, 2]))

    def test_a_zero_ttl_keeps_nothing(self):
        cache = RankCache(ttl=0, max_entries=3, wait=5)
        cache.get("a", self.compute(1))
        cache.get("a", self.compute(2))
        self.assertEqual((self.calls, len(cache)), ([1, 2], 0))

    def test_a_failure_is_not_cached(self):
        def boom():
            raise RuntimeError("statement timeout")
        with self.assertRaises(RuntimeError):
            self.cache.get("a", boom)
        self.assertEqual(self.cache.get("a", self.compute(1)), 1)


class InFlight(unittest.TestCase):
    """Requests for a list being ranked share that one computation."""

    N = 8

    def crowd(self, cache, compute, key="k"):
        """N threads asking for `key` at once; their results or errors."""
        out, lock = [], threading.Lock()

        def ask():
            try:
                r = ("ok", cache.get(key, compute))
            except Exception as e:
                r = ("error", e)
            with lock:
                out.append(r)
        threads = [threading.Thread(target=ask) for _ in range(self.N)]
        for t in threads:
            t.start()
        return threads, out

    def gate(self, then):
        """A compute that waits for release() and then calls then(); it
        counts its runs and how many were ever running at once."""
        state = {"runs": 0, "active": 0, "most": 0}
        started, release, lock = threading.Event(), threading.Event(), threading.Lock()

        def compute():
            with lock:
                state["runs"] += 1
                state["active"] += 1
                state["most"] = max(state["most"], state["active"])
            started.set()
            try:
                release.wait(5)
                return then()
            finally:
                with lock:
                    state["active"] -= 1
        return compute, started, release, state

    def settle(self, cache, threads, key="k"):
        """Wait until every thread but the leader is waiting on its flight."""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if all(t.is_alive() for t in threads) and key in cache._flights:
                time.sleep(0.1)
                return
            time.sleep(0.01)

    def test_concurrent_requests_for_one_list_run_its_query_once(self):
        cache = RankCache(ttl=60, max_entries=8, wait=5)
        compute, started, release, state = self.gate(lambda: "ranked")
        threads, out = self.crowd(cache, compute)
        started.wait(5)
        self.settle(cache, threads)
        # Another list is not held up by the one being computed.
        t0 = time.monotonic()
        self.assertEqual(cache.get("other", lambda: "other"), "other")
        self.assertLess(time.monotonic() - t0, 1)
        release.set()
        for t in threads:
            t.join(5)
        self.assertEqual((state["runs"], out), (1, [("ok", "ranked")] * self.N))

    def test_every_waiter_gets_the_one_failure_and_none_runs_it_again(self):
        cache = RankCache(ttl=60, max_entries=8, wait=5)
        failure = RuntimeError("canceling statement due to statement timeout")

        def fail():
            raise failure
        compute, started, release, state = self.gate(fail)
        threads, out = self.crowd(cache, compute)
        started.wait(5)
        self.settle(cache, threads)
        release.set()
        for t in threads:
            t.join(5)
        self.assertEqual(state["runs"], 1)
        self.assertEqual(out, [("error", failure)] * self.N)
        # A request after the failure starts a fresh computation, alone.
        compute, started, release, state = self.gate(lambda: "ranked")
        threads, out = self.crowd(cache, compute)
        started.wait(5)
        self.settle(cache, threads)
        release.set()
        for t in threads:
            t.join(5)
        self.assertEqual((state["runs"], state["most"]), (1, 1))
        self.assertEqual(out, [("ok", "ranked")] * self.N)

    def test_a_waiter_gives_up_after_its_wait(self):
        class Busy(Exception):
            pass
        cache = RankCache(ttl=60, max_entries=8, wait=0.1, timeout_error=Busy)
        compute, started, release, state = self.gate(lambda: "ranked")
        leader = threading.Thread(target=lambda: cache.get("k", compute))
        leader.start()
        started.wait(5)
        t0 = time.monotonic()
        with self.assertRaises(Busy):
            cache.get("k", compute)
        self.assertLess(time.monotonic() - t0, 2)
        release.set()
        leader.join(5)
        self.assertEqual((state["runs"], cache.peek("k")), (1, "ranked"))

    def test_the_ledgers_waiters_time_out_as_a_query_does(self):
        """main.py answers QueryCanceled with a 503 and Retry-After."""
        self.assertIsInstance(queries.LEDGER_CACHE.timeout_error(), queries.QueryCanceled)
        self.assertLess(queries.LEDGER_CACHE_WAIT, queries.LEDGER_CACHE_TTL)


PLACES = 6


class FakeDb:
    """fetch_all / fetch_value for ledger_page. The whole ranking is PLACES
    places p0..p5; a first page is the ranking statement with a LIMIT; the
    rows query returns leaderboard columns for the keys asked for, except
    any in `gone` (a place merged away since it was ranked)."""

    def __init__(self):
        self.version = 1
        self.rankings, self.first_pages = [], []
        self.gone = set()

    def fetch_value(self, conn, sql, params=(), default=None):
        assert "mention_weights" in sql
        return self.version

    def fetch_all(self, conn, sql, params=()):
        if "= any(%(keys)s)" in sql:
            return [{"entity_key": k, "official_name": k.upper()}
                    for k in params["keys"] if k not in self.gone]
        places = [{"entity_key": f"p{i}", "current": PLACES - i, "previous": i, "people": None,
                   "rank_value": float(PLACES - i)} for i in range(PLACES)]
        if "limit %(limit)s" in sql:
            self.first_pages.append(params)
            return [dict(p, official_name=p["entity_key"].upper(), total=PLACES)
                    for p in places[:params["limit"]]]
        self.rankings.append(params)
        return places


class LedgerPage(unittest.TestCase):
    BASE = dict(sub="FoodNYC", category="top", window=30, cuisine=None, borough=None,
                needs=[], flaws=[], algo="v1", topic=None)
    VARIANTS = dict(sub="FoodLosAngeles", category="gems", window=7, cuisine="Pizza",
                    borough="Brooklyn", needs=["value"], flaws=["wait"], algo="v2",
                    topic="omakase")

    def setUp(self):
        queries.LEDGER_CACHE.clear()
        self.addCleanup(queries.LEDGER_CACHE.clear)
        self.db = FakeDb()

    def page(self, limit=2, offset=0, **args):
        a = dict(self.BASE, **args)
        rows, total = queries.ledger_page(
            None, a["sub"], a["category"], a["window"], a["cuisine"], a["borough"], a["needs"],
            a["flaws"], limit, self.db.fetch_all, self.db.fetch_value,
            algo=a["algo"], topic=a["topic"], offset=offset)
        return [r["entity_key"] for r in rows], total

    def test_a_first_page_is_one_limited_query_and_caches_nothing(self):
        self.assertEqual(self.page(), (["p0", "p1"], PLACES))
        self.assertEqual(self.page(), (["p0", "p1"], PLACES))
        self.assertEqual((len(self.db.first_pages), len(self.db.rankings)), (2, 0))
        self.assertEqual(len(queries.LEDGER_CACHE), 0)

    def test_scrolling_ranks_once_and_every_page_is_cut_from_it(self):
        first = queries.ledger_page(None, "FoodNYC", "top", 30, None, None, [], [], 2,
                                    self.db.fetch_all, self.db.fetch_value)
        self.assertEqual(self.page(offset=2), (["p2", "p3"], PLACES))
        self.assertEqual(len(queries.LEDGER_CACHE), 1)
        self.assertEqual(self.page(offset=4), (["p4", "p5"], PLACES))
        # Past the end: no rows, but the real size of the list.
        self.assertEqual(self.page(offset=10), ([], PLACES))
        # With the entry there, the first page comes from it too, and has
        # the rows the limited query gave.
        cached = queries.ledger_page(None, "FoodNYC", "top", 30, None, None, [], [], 2,
                                     self.db.fetch_all, self.db.fetch_value)
        self.assertEqual(cached, first)
        self.assertEqual((len(self.db.rankings), len(self.db.first_pages)), (1, 1))

    def test_every_argument_that_changes_the_list_has_its_own_entry(self):
        self.assertEqual(set(self.VARIANTS), set(self.BASE),
                         "a ledger_page argument has no variant here")
        self.page(offset=1)
        for name, value in self.VARIANTS.items():
            before = len(self.db.rankings)
            self.page(offset=1, **{name: value})
            self.assertEqual(len(self.db.rankings), before + 1,
                             f"{name}={value!r} was served another list's ranking")
        # Each now hits its own entry, never the base one.
        before = len(self.db.rankings)
        for name, value in self.VARIANTS.items():
            self.page(offset=1, **{name: value})
        self.page(offset=1)
        self.assertEqual(len(self.db.rankings), before)

    def test_a_refresh_starts_every_list_afresh(self):
        self.page(offset=2)
        self.db.version = 2
        self.page(offset=2)
        self.assertEqual(len(self.db.rankings), 2)
        # And a first page after the next one is the limited query again.
        self.db.version = 3
        self.page()
        self.assertEqual(len(self.db.first_pages), 1)

    def test_the_order_of_needs_and_flaws_does_not_split_a_list(self):
        self.page(offset=1, needs=["value", "service"], flaws=["wait", "food"])
        self.page(offset=1, needs=["service", "value"], flaws=["food", "wait"])
        self.assertEqual(len(self.db.rankings), 1)

    def test_a_page_is_topped_up_past_places_gone_from_the_board(self):
        self.page(offset=2)
        self.db.gone = {"p2", "p3"}
        # Full though both of its own places are gone: filled from after it.
        self.assertEqual(self.page(offset=2), (["p4", "p5"], PLACES))
        self.db.gone = {"p1"}
        self.assertEqual(self.page(offset=0, limit=3), (["p0", "p2", "p3"], PLACES))
        # Short only where the ranking runs out.
        self.db.gone = {"p4"}
        self.assertEqual(self.page(offset=3, limit=3), (["p3", "p5"], PLACES))
        self.assertEqual(len(self.db.rankings), 1)


if __name__ == "__main__":
    unittest.main()
