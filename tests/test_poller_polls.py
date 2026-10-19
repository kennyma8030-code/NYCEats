"""The multi-city poll: paging back to what the last poll saw, the interval,
and surviving a lost database connection. Arctic Shift and Postgres are
faked; no network, no database."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import fakes  # noqa: F401  (puts the repo root on sys.path)

import arctic
import poller


def comment(i, t, sub="chicagofood", link="t3_x"):
    return {"id": f"c{i:05d}", "created_utc": t, "subreddit": sub, "link_id": link,
            "parent_id": link, "body": "b"}


class FakeArctic:
    """newest_comments over a fixed list, newest first, `before` exclusive."""

    def __init__(self, comments):
        self.comments = sorted(comments, key=lambda c: (-c["created_utc"], c["id"]))
        self.calls = []

    def __call__(self, subreddit, limit=arctic.PAGE, before=None):
        self.calls.append(before)
        rows = [c for c in self.comments if before is None or c["created_utc"] < before]
        return rows[:limit]


class FetchNew(unittest.TestCase):
    def fetch(self, comments, held):
        fake = FakeArctic(comments)
        with mock.patch.object(poller.arctic, "newest_comments", fake), \
                mock.patch.object(poller.time, "sleep"), redirect_stdout(io.StringIO()):
            got = poller.fetch_new("chicagofood", held)
        return {c["id"] for c in got}, fake

    def test_pages_back_across_ties_and_misses_nothing(self):
        # 320 comments newer than held, three to a second, so every page
        # boundary (100 per page) falls inside a second.
        held = 1_000
        old = [comment(i, held - i) for i in range(50)]
        new = [comment(1000 + i, held + 1 + i // 3) for i in range(320)]
        got, fake = self.fetch(old + new, held)
        self.assertTrue({c["id"] for c in new} <= got, "a newer comment was missed")
        self.assertEqual(len(fake.calls), 4)
        self.assertIsNone(fake.calls[0])

    def test_one_page_when_it_reaches_what_was_seen(self):
        held = 1_000
        got, fake = self.fetch([comment(i, held - 50 + i) for i in range(150)], held)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(len(got), 100)

    def test_nothing_held_takes_one_page(self):
        got, fake = self.fetch([comment(i, 10_000 + i) for i in range(500)], None)
        self.assertEqual(len(fake.calls), 1)

    def test_page_cap(self):
        held = 0
        got, fake = self.fetch([comment(i, 10 + i) for i in range(5_000)], held)
        self.assertEqual(len(fake.calls), poller.MAX_PAGES)
        # Each page after the first repeats one comment: `before` is the
        # previous oldest + 1, so the tie second is fetched twice.
        self.assertEqual(len(got), poller.MAX_PAGES * arctic.PAGE - (poller.MAX_PAGES - 1))


class Interval(unittest.TestCase):
    def interval(self, peak):
        with mock.patch.object(poller.db, "busiest_hour", return_value=peak):
            return poller.interval_for(None, "chicagofood")

    def test_half_a_page_in_the_busiest_hour(self):
        self.assertEqual(self.interval(100), 30 * 60)            # 50/100 of an hour
        self.assertAlmostEqual(self.interval(211), 50 / 211 * 3600)

    def test_clamped(self):
        self.assertEqual(self.interval(10_000), poller.MIN_INTERVAL)
        self.assertEqual(self.interval(1), poller.MAX_INTERVAL)

    def test_no_history_polls_soon(self):
        self.assertEqual(self.interval(0), poller.MIN_INTERVAL)


class Seen(unittest.TestCase):
    """The overlap point is the poll's own memory, not max(created_utc)."""

    def poll(self, seen, page, stored=500, insert_fails=False):
        db = mock.Mock()
        db.newest_stored_utc.return_value = stored
        if insert_fails:
            db.insert_comments.side_effect = RuntimeError("db down")
        fetch = mock.Mock(return_value=page)
        ingest = mock.Mock()
        ingest.ensure_threads.return_value = (page, 0, set())
        with mock.patch.multiple(poller, db=db, fetch_new=fetch, ingest=ingest), \
                redirect_stdout(io.StringIO()):
            try:
                poller.poll_once(mock.Mock(), "chicagofood", seen)
            except RuntimeError:
                pass
        return fetch, db

    def test_seeded_from_the_table_once(self):
        seen = {}
        fetch, db = self.poll(seen, [comment(1, 600)])
        fetch.assert_called_once_with("chicagofood", 500)
        self.assertEqual(seen, {"chicagofood": 600})
        fetch, db = self.poll(seen, [comment(2, 700)], stored=9_999)
        db.newest_stored_utc.assert_not_called()
        fetch.assert_called_once_with("chicagofood", 600)

    def test_other_writers_cannot_move_it(self):
        # A thread pull or the backfill stored something newer: the table's
        # max moves, the poll's memory does not.
        seen = {"chicagofood": 600}
        fetch, _ = self.poll(seen, [comment(1, 650)], stored=10_000)
        fetch.assert_called_once_with("chicagofood", 600)
        self.assertEqual(seen["chicagofood"], 650)

    def test_failed_insert_does_not_move_it(self):
        seen = {"chicagofood": 600}
        self.poll(seen, [comment(1, 900)], insert_fails=True)
        self.assertEqual(seen["chicagofood"], 600)

    def test_never_moves_backwards(self):
        seen = {"chicagofood": 600}
        self.poll(seen, [comment(1, 590)])
        self.assertEqual(seen["chicagofood"], 600)


class Connection(unittest.TestCase):
    """A lost connection is replaced, never allowed to end the poller."""

    def step(self, conn, connect):
        def boom(_c):
            raise RuntimeError("server closed the connection unexpectedly")
        with mock.patch.object(poller.db, "connect", connect), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return poller._step("poll", boom, conn)

    def test_live_connection_is_rolled_back_and_kept(self):
        conn = mock.Mock(closed=0)
        new = mock.Mock(side_effect=AssertionError("should not reconnect"))
        result, got = self.step(conn, new)
        self.assertIsNone(result)
        self.assertIs(got, conn)
        conn.rollback.assert_called_once()

    def test_closed_connection_is_replaced(self):
        conn = mock.Mock(closed=2)
        fresh = mock.Mock(closed=0)
        _, got = self.step(conn, mock.Mock(return_value=fresh))
        self.assertIs(got, fresh)
        conn.rollback.assert_not_called()

    def test_rollback_that_raises_is_replaced(self):
        conn = mock.Mock(closed=0)
        conn.rollback.side_effect = Exception("connection already closed")
        fresh = mock.Mock(closed=0)
        _, got = self.step(conn, mock.Mock(return_value=fresh))
        self.assertIs(got, fresh)

    def test_failed_reconnect_keeps_going(self):
        conn = mock.Mock(closed=2)
        _, got = self.step(conn, mock.Mock(side_effect=Exception("db is restarting")))
        self.assertIs(got, conn)

    def test_poll_due_carries_the_new_connection_on(self):
        dead, fresh = mock.Mock(closed=2), mock.Mock(closed=0)
        used = []

        def poll_once(c, name, seen):
            used.append((name, c))
            if c is dead:
                raise RuntimeError("gone")

        due = {"FoodNYC": 0.0, "chicagofood": 0.0}
        with mock.patch.multiple(poller, poll_once=poll_once,
                                 interval_for=mock.Mock(return_value=900)), \
                mock.patch.object(poller.db, "connect", return_value=fresh), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            got = poller.poll_due(dead, list(due), due, {})
        self.assertIs(got, fresh)
        self.assertEqual(used, [("FoodNYC", dead), ("chicagofood", fresh)])


if __name__ == "__main__":
    unittest.main()
