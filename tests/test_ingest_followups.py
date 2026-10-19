"""Review follow-ups to the late-comment and backfill work: no thread pulled
twice, a bounded first re-sweep, a board refreshed on a timer, and the
backfill's edge cases. Arctic Shift and Postgres are faked."""

import io
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

import fakes  # noqa: F401  (puts the repo root on sys.path)

import backfill
import poller
from test_ingest_paging import Asc, T, item

SUB = "FoodNYC"
HOUR = 3600
T0 = 1_700_000_000


class Store(unittest.TestCase):
    def test_a_thread_just_found_is_not_pulled_again(self):
        pending = {"t3_p1": 100, "t3_p2": 100}
        ingest = mock.Mock()
        ingest.ensure_threads.return_value = ([{"link_id": "t3_p1"}], 1, {"p1"})
        pulled = mock.Mock()
        with mock.patch.object(poller, "ingest", ingest), mock.patch.object(poller, "db"), \
                mock.patch.object(poller, "pull_threads", pulled), redirect_stdout(io.StringIO()):
            poller.store(None, [{"link_id": "t3_p1"}], pending)
        pulled.assert_called_once_with(None, {"p1"})
        self.assertEqual(pending, {"t3_p2": 100})


class Resweep(unittest.TestCase):
    def test_no_thread_pulls_and_never_before_the_oldest_held(self):
        calls, stores = [], []
        db = mock.Mock()
        db.oldest_stored_utc.return_value = T0 - HOUR

        def search_page(kind, sub, after=None):
            calls.append(after)
            return [] if len(calls) > 1 else [item(1, T0 - HOUR - T)]
        with mock.patch.object(poller, "db", db), \
                mock.patch.object(poller.arctic, "search_page", search_page), \
                mock.patch.object(poller, "store", lambda *a, **k: stores.append(k) or 0), \
                mock.patch("time.time", lambda: T0), mock.patch("time.sleep"), \
                redirect_stdout(io.StringIO()):
            poller.resweep_once(None, SUB, 48, {})
        # A city first seen an hour ago is re-read from then, not 48h back.
        self.assertEqual(calls[0], T0 - HOUR - 1)
        self.assertEqual(stores, [{"pull": False}])

    def test_an_empty_city_is_not_swept(self):
        db = mock.Mock()
        db.oldest_stored_utc.return_value = None
        search = mock.Mock()
        with mock.patch.object(poller, "db", db), \
                mock.patch.object(poller.arctic, "search_page", search):
            self.assertEqual(poller.resweep_once(None, SUB, 48, {}), 0)
        search.assert_not_called()


class RefreshTimer(unittest.TestCase):
    def chores(self, **kw):
        a = types.SimpleNamespace(extract=False, embed=False, **kw)
        refresh = mock.Mock(return_value=True)
        with mock.patch.multiple(poller, settle_once=mock.Mock(), disk_once=mock.Mock(),
                                 refresh_once=refresh), redirect_stdout(io.StringIO()):
            poller.run_chores(mock.Mock(closed=0), a)
        return refresh.call_count, a

    def test_no_timer_outside_the_main_loop(self):
        self.assertEqual(self.chores()[0], 0)

    def test_refreshes_when_the_board_is_old_then_waits(self):
        n, a = self.chores(refresh_every=6 * HOUR, refreshed_at=0.0)
        self.assertEqual(n, 1)
        self.assertGreater(a.refreshed_at, 0)
        n, _ = self.chores(refresh_every=6 * HOUR, refreshed_at=a.refreshed_at)
        self.assertEqual(n, 0)


class Backfill(unittest.TestCase):
    def test_negative_years_fail_the_boot(self):
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            backfill.scope(None, None, env={"BACKFILL_SUBREDDITS": "all",
                                            "BACKFILL_YEARS_OTHER": "-2"})

    def test_trees_are_filled_before_a_disk_stop(self):
        items = [item(i, 1_000 + i, link=f"t3_{i}") for i in range(5_000)]
        fake = Asc(items)
        db = mock.Mock()
        db.get_cursor.return_value = T + 1_000
        db.database_size_mb.side_effect = [100.0, 5_000.0]
        db.insert_comments.return_value = 100
        filled = set()
        # Copied as called: the sweep clears the set it hands over.
        db.fill_tree.side_effect = lambda conn, ids: filled.update(ids)
        with mock.patch.object(backfill.arctic, "search_page",
                               lambda kind, s, after=None: fake(after)), \
                mock.patch.object(backfill.ingest, "ensure_threads",
                                  side_effect=lambda conn, page, pause: (page, 0, set())), \
                mock.patch.object(backfill, "db", db), mock.patch.object(backfill.time, "sleep"), \
                redirect_stdout(io.StringIO()):
            with self.assertRaises(backfill.DiskBudget):
                backfill.backfill_comments(mock.Mock(), "chicagofood", 0, pause=0)
        # Every thread of the ten pages stored: 100, then 99 new a page (each
        # page after the first repeats the previous page's last second).
        self.assertEqual(len(filled), 100 + 9 * 99)


if __name__ == "__main__":
    unittest.main()
