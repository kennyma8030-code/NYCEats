"""The ledger echoes every filter it ranked under, so the frontend can tell a
stale list from a current one (frontend/src/lib/fresh.ts)."""

from apptest import AppCase


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
