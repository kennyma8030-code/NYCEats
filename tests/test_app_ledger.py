"""The ledger echoes every filter it ranked under, so the frontend can tell a
stale list from a current one (frontend/src/lib/fresh.ts)."""

from unittest import mock

from apptest import AppCase

from app import queries


class LedgerEcho(AppCase):
    def test_ledger_echoes_every_filter(self):
        r = self.client.get("/api/ledger?category=top&window=7&cuisine=Pizza&borough=Brooklyn"
                            "&need=value&need=value&flaw=food&topic=%20slice%20&algo=v2").json()
        self.assertEqual((r["category"], r["window_days"], r["algo"], r["topic"]),
                         ("top", 7, "v2", "slice"))
        self.assertEqual((r["cuisine"], r["borough"], r["needs"], r["flaws"]),
                         ("Pizza", "Brooklyn", ["value"], ["food"]))

    def test_no_filters_echo_as_empty(self):
        r = self.client.get("/api/ledger").json()
        self.assertEqual((r["cuisine"], r["borough"], r["needs"], r["flaws"], r["topic"]),
                         (None, None, [], [], None))

    def test_trending_is_refused_like_any_unknown_category(self):
        """Trending was removed; asking for it gets the answer a made-up
        category gets, and no category at all means the most mentioned."""
        gone = self.client.get("/api/ledger?category=trending")
        made_up = self.client.get("/api/ledger?category=nonsense")
        self.assertEqual((gone.status_code, made_up.status_code), (422, 422))
        self.assertEqual(self.client.get("/api/ledger").json()["category"], "top")

    def test_a_list_is_read_a_page_at_a_time(self):
        """Pages by offset never overlap and add up to the whole list, so the
        frontend can scroll to its last place."""
        whole = self.client.get("/api/ledger?category=top&window=7").json()
        keys = [i["entity_key"] for i in whole["items"]]
        self.assertEqual((whole["total"], whole["limit"], whole["offset"]), (len(keys), 50, 0))
        self.assertGreater(len(keys), 1)
        paged = []
        for offset in range(len(keys)):
            page = self.client.get(
                f"/api/ledger?category=top&window=7&limit=1&offset={offset}").json()
            self.assertEqual((page["total"], page["offset"]), (len(keys), offset))
            paged += [i["entity_key"] for i in page["items"]]
        self.assertEqual(paged, keys)
        past_end = self.client.get(f"/api/ledger?category=top&window=7&offset={len(keys)}").json()
        self.assertEqual((past_end["items"], past_end["total"]), ([], len(keys)))

    def test_the_pages_of_a_list_are_cut_from_one_ranking(self):
        """The window aggregation runs once per list, not once per page, and
        a list with other filters is ranked on its own."""
        with mock.patch.object(queries, "ledger_ranking", wraps=queries.ledger_ranking) as rank:
            first = self.client.get("/api/ledger?category=top&window=7&limit=1").json()
            second = self.client.get("/api/ledger?category=top&window=7&limit=1&offset=1").json()
            self.assertEqual(rank.call_count, 1)
            self.client.get("/api/ledger?category=top&window=14&limit=1")
            self.client.get("/api/ledger?category=top&window=7&limit=1&algo=v2")
            self.assertEqual(rank.call_count, 3)
        self.assertNotEqual(first["items"][0]["entity_key"], second["items"][0]["entity_key"])
        # Rows cut from the cache are the rows the uncached list returns.
        queries.LEDGER_CACHE.enabled = False
        self.addCleanup(setattr, queries.LEDGER_CACHE, "enabled", True)
        fresh = self.client.get("/api/ledger?category=top&window=7&limit=1&offset=1").json()
        self.assertEqual(fresh, second)
