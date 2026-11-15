"""db.recover, the one reconnect helper the poller, the backfill thread and
the RSS thread share, and the RSS thread surviving a database that is down.
No network, no database."""

import io
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import fakes  # noqa: F401  (puts the repo root on sys.path)

import db
import rss


class Recover(unittest.TestCase):
    def recover(self, conn, connect):
        with mock.patch.object(db, "connect", connect), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return db.recover(conn)

    def test_live_connection_is_rolled_back(self):
        conn = mock.Mock(closed=0)
        self.assertIs(self.recover(conn, mock.Mock(side_effect=AssertionError)), conn)
        conn.rollback.assert_called_once()

    def test_none_or_closed_reconnects(self):
        fresh = mock.Mock(closed=0)
        self.assertIs(self.recover(None, mock.Mock(return_value=fresh)), fresh)
        self.assertIs(self.recover(mock.Mock(closed=2), mock.Mock(return_value=fresh)), fresh)

    def test_never_raises(self):
        conn = mock.Mock(closed=0)
        conn.rollback.side_effect = Exception("connection already closed")
        got = self.recover(conn, mock.Mock(side_effect=Exception("db is restarting")))
        self.assertIs(got, conn)
        self.assertIsNone(self.recover(None, mock.Mock(side_effect=Exception("down"))))


def http(code):
    return urllib.error.HTTPError("https://www.reddit.com/r/x/comments/.rss", code, "refused", {}, None)


class Clock:
    """A clock that only the loop's own sleeps move."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class RssThread(unittest.TestCase):
    def test_survives_a_database_that_is_down(self):
        """Down at start, back, lost mid-poll, back: the loop never raises."""

        class Stop(BaseException):
            pass
        good, again = mock.Mock(closed=0), mock.Mock(closed=0)
        connects = mock.Mock(side_effect=[Exception("down"), good, Exception("still down"), again])
        polls = mock.Mock(side_effect=[Exception("server closed the connection"), (1, 2), (0, 0)])
        sleeps = []

        def sleep(s):
            sleeps.append(s)
            if len(sleeps) == 4:
                raise Stop

        def lost_rollback():
            good.closed = 2
            raise Exception("connection already closed")
        good.rollback.side_effect = lost_rollback
        init = mock.Mock()
        with mock.patch.object(rss.db, "connect", connects), \
                mock.patch.object(rss.db, "init", init), \
                mock.patch.object(rss, "poll_once", polls), \
                mock.patch.object(rss.time, "sleep", sleep), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(Stop):
                rss.run_forever(interval=0)
        self.assertEqual(connects.call_count, 4)
        self.assertEqual(polls.call_count, 3)
        init.assert_called_once()           # the schema once, on the first good connection

    def loop(self, poll, turns, names=("FoodNYC", "chicagofood", "austinfood"), interval=300, clock=None):
        """run_forever for `turns` sleeps: (the feeds read, the sleeps)."""
        class Stop(BaseException):
            pass
        polled, sleeps = [], []

        def poll_once(conn, subreddit, retries=None):
            self.assertEqual(retries, 0)            # the loop spaces its own requests
            polled.append(subreddit)
            return poll(subreddit, len(polled))

        def sleep(s):
            sleeps.append(s)
            if isinstance(clock, Clock):
                clock.now += s
            if len(sleeps) == turns:
                raise Stop

        conn = mock.Mock(closed=0)
        with mock.patch.object(rss.db, "connect", return_value=conn), \
                mock.patch.object(rss.db, "init"), \
                mock.patch.object(rss.db, "recover", return_value=conn), \
                mock.patch.object(rss, "poll_once", poll_once), \
                mock.patch.object(rss.time, "sleep", sleep), \
                mock.patch.object(rss.time, "time", clock or mock.Mock(return_value=1000.0)), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(Stop):
                rss.run_forever(interval=interval, names=names)
        return polled, sleeps

    def test_feeds_take_turns_spread_across_the_interval(self):
        polled, sleeps = self.loop(lambda sub, n: (0, 1), 7)
        self.assertEqual(polled, ["FoodNYC", "chicagofood", "austinfood"] * 2 + ["FoodNYC"])
        self.assertEqual(sleeps, [100.0] * 7)       # one request every 100 s: each feed every 300

    def test_a_broken_feed_costs_its_own_turn_and_the_others_keep_their_times(self):
        def poll(sub, n):
            if sub == "chicagofood":
                raise http(404)
            return 0, 1
        polled, sleeps = self.loop(poll, 7)
        # A private or missing subreddit: no second try, no slower loop, no
        # extra read of anything else.
        self.assertEqual(polled, ["FoodNYC", "chicagofood", "austinfood"] * 2 + ["FoodNYC"])
        self.assertEqual(sleeps, [100.0] * 7)

    def test_the_home_feed_failing_alone_does_not_starve_the_others(self):
        # Its own rows will not go in, every time. The loop used to read
        # only this feed until it worked, which was never.
        def poll(sub, n):
            if sub == "FoodNYC":
                raise ValueError("null value in column violates not-null constraint")
            return 0, 1
        polled, sleeps = self.loop(poll, 8)
        self.assertEqual(polled, ["FoodNYC", "FoodNYC", "chicagofood", "austinfood"] * 2)
        # One more try 10 s later, and the next feed still goes out on time.
        self.assertEqual(sleeps, [10, 100.0, 100.0, 100.0] * 2)

    def test_one_feed_that_fails_once_is_read_again_at_once_not_an_interval_later(self):
        clock = Clock()

        def poll(sub, n):
            if n == 2:
                raise http(503)
            return 0, 1
        polled, sleeps = self.loop(poll, 4, names=("FoodNYC",), clock=clock)
        self.assertEqual(polled, ["FoodNYC"] * 4)
        # Read at 0, failed at 300, read at 310, and the turn after is still
        # the one due at 600: 310 s between good reads, not 600.
        self.assertEqual(sleeps, [300.0, 10, 290.0, 300.0])

    def test_a_database_error_is_tried_again_and_does_not_slow_the_loop(self):
        def poll(sub, n):
            if n in (2, 3):
                raise Exception("server closed the connection unexpectedly")
            return 0, 1
        polled, sleeps = self.loop(poll, 5)
        self.assertEqual(polled, ["FoodNYC", "chicagofood", "chicagofood", "austinfood", "FoodNYC"])
        self.assertEqual(sleeps, [100.0, 10, 100.0, 100.0, 100.0])      # Reddit refused nothing

    def test_a_429_spaces_the_requests_out_and_the_rotation_carries_on(self):
        def poll(sub, n):
            if n <= 5:
                raise http(429)
            return 0, 1
        polled, sleeps = self.loop(poll, 7)
        # No feed is read twice running and none is skipped for good.
        self.assertEqual(polled, ["FoodNYC", "chicagofood", "austinfood"] * 2 + ["FoodNYC"])
        # A minute more, then doubling, never more than an interval on top
        # of the turn; the first read that works puts the pace back.
        self.assertEqual(sleeps, [160.0, 220.0, 340.0, 400.0, 400.0, 100.0, 100.0])
        self.assertGreaterEqual(min(sleeps), rss.MIN_GAP)

    def test_a_429_on_one_feed_does_not_double_its_wait(self):
        polled, sleeps = self.loop(lambda sub, n: (_ for _ in ()).throw(http(429)) if n == 1 else (0, 1), 2,
                                   names=("FoodNYC",))
        self.assertEqual(sleeps, [360.0, 300.0])

    def test_a_slow_turn_still_leaves_a_gap_before_the_next_request(self):
        # Seven feeds are a turn of about 43 s. A request that took longer
        # than its turn used to be followed at once by the next feed's.
        ticks = iter(range(0, 10_000, 60))          # every look at the clock is a minute later
        polled, sleeps = self.loop(lambda sub, n: (0, 1), 3, names=tuple("abcdefg"),
                                   clock=lambda: next(ticks))
        self.assertEqual(sleeps, [rss.MIN_GAP] * 3)

    def test_a_feeds_rows_carry_its_subreddit(self):
        xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
            <id>t1_abc</id><author><name>/u/someone</name></author>
            <link href="https://www.reddit.com/r/austinfood/comments/1xyz/best_tacos/abc/"/>
            <updated>2026-11-10T01:02:03+00:00</updated>
            <title>/u/someone on Best tacos?</title>
            <content type="html">&lt;p&gt;Veracruz.&lt;/p&gt;</content></entry></feed>"""
        [row] = rss.parse(xml, "austinfood")
        self.assertEqual((row["subreddit"], row["thread_id"], row["thread_title"], row["body"]),
                         ("austinfood", "t3_1xyz", "Best tacos?", "Veracruz."))
        self.assertEqual(row["thread_permalink"], "https://www.reddit.com/r/austinfood/comments/1xyz/best_tacos/")
        self.assertEqual(rss.feed_url("austinfood"), "https://www.reddit.com/r/austinfood/comments/.rss?limit=25")


if __name__ == "__main__":
    unittest.main()
