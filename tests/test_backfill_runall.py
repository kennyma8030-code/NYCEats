"""The background sweep: one bad city must not stall the rest, --once must
finish, and nothing may kill the thread silently. Arctic Shift and Postgres
are faked; no network, no database."""

import io
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import fakes  # noqa: F401  (puts the repo root on sys.path)

import backfill


class RunAll(unittest.TestCase):
    def run_all(self, failures, names=("FoodNYC", "chicagofood", "denverfood"), **kw):
        """failures: name -> how many calls fail before one succeeds (-1: always)."""
        calls = []
        left = dict(failures)

        def run(conn, name, years=None):
            calls.append(name)
            n = left.get(name, 0)
            if n:
                left[name] = n - 1
                raise RuntimeError(f"{name} page broke")
        conn = mock.Mock(closed=0)
        with mock.patch.object(backfill, "run", run), \
                mock.patch.object(backfill.time, "sleep"), \
                redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            failed = backfill.run_all(conn, list(names), retry_after=0, **kw)
        return calls, failed, out.getvalue()

    def test_transient_failure_is_retried_in_place(self):
        calls, failed, _ = self.run_all({"FoodNYC": 1})
        self.assertEqual(calls, ["FoodNYC", "FoodNYC", "chicagofood", "denverfood"])
        self.assertEqual(failed, [])

    def test_persistent_failure_moves_to_the_back(self):
        calls, failed, out = self.run_all({"FoodNYC": 3})
        self.assertEqual(calls, ["FoodNYC"] * 3 + ["chicagofood", "denverfood", "FoodNYC"])
        self.assertEqual(failed, [])
        self.assertIn("r/FoodNYC FAILED 3 times in a row -- moving on", out)

    def test_once_gives_up_instead_of_hanging(self):
        calls, failed, out = self.run_all({"chicagofood": -1}, rounds=2)
        self.assertEqual(failed, ["chicagofood"])
        self.assertEqual(calls.count("chicagofood"), 2 * backfill.MAX_TRIES)
        self.assertEqual(calls[-1], "chicagofood")
        self.assertIn("denverfood", calls)
        self.assertIn("not caught up: chicagofood", out)

    def test_lost_connection_is_replaced(self):
        dead, fresh = mock.Mock(closed=2), mock.Mock(closed=0)
        seen = []

        def run(conn, name, years=None):
            seen.append(conn)
            if conn is dead:
                raise RuntimeError("gone")
        with mock.patch.object(backfill, "run", run), \
                mock.patch.object(backfill.db, "connect", return_value=fresh), \
                mock.patch.object(backfill.time, "sleep"), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            backfill.run_all(dead, ["FoodNYC"], retry_after=0)
        self.assertEqual(seen, [dead, fresh])

    def test_failed_reconnect_counts_as_a_failure_not_a_crash(self):
        dead = mock.Mock(closed=2)

        def run(conn, name, years=None):
            raise RuntimeError("gone")
        with mock.patch.object(backfill, "run", run), \
                mock.patch.object(backfill.db, "connect", side_effect=Exception("down")), \
                mock.patch.object(backfill.time, "sleep"), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(backfill.run_all(dead, ["FoodNYC"], retry_after=0, rounds=1),
                             ["FoodNYC"])


class Background(unittest.TestCase):
    def test_connect_failure_does_not_kill_the_thread(self):
        done = threading.Event()
        connects = mock.Mock(side_effect=[Exception("db is restarting"), mock.Mock(closed=0)])

        def run_all(conn, names, years, retry_after):
            done.set()
        with mock.patch.object(backfill.db, "connect", connects), \
                mock.patch.object(backfill, "run_all", run_all), \
                mock.patch.object(backfill.time, "sleep"), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            t = backfill.start_background(["FoodNYC"], retry_after=0)
            t.join(5)
        self.assertTrue(done.is_set())
        self.assertEqual(connects.call_count, 2)


class OrphanPage(unittest.TestCase):
    def test_cursor_moves_past_a_page_whose_posts_are_all_missing(self):
        # Every comment on the page sits under a post the archive cannot
        # return, so ensure_threads keeps none of them. The cursor must still
        # move to the page's newest, or the sweep fetches it forever.
        page = [{"id": f"c{i}", "created_utc": 1_000 + i, "link_id": "t3_gone",
                 "parent_id": "t3_gone", "subreddit": "chicagofood"} for i in range(5)]
        pages = iter([page, []])
        db = mock.Mock()
        db.get_cursor.return_value = 500
        db.insert_comments.return_value = 0
        db.database_size_mb.return_value = 900.0
        with mock.patch.object(backfill.arctic, "search_page", lambda *a, **k: next(pages)), \
                mock.patch.object(backfill.ingest, "ensure_threads", return_value=([], 0, set())), \
                mock.patch.object(backfill, "db", db), \
                mock.patch.object(backfill.time, "sleep"), redirect_stdout(io.StringIO()):
            backfill.backfill_comments(mock.Mock(), "chicagofood", 0, pause=0)
        db.set_cursor.assert_called_once_with(mock.ANY, "chicagofood", "comments", 1_004)


if __name__ == "__main__":
    unittest.main()
