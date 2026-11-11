"""db.recover, the one reconnect helper the poller, the backfill thread and
the RSS thread share, and the RSS thread surviving a database that is down.
No network, no database."""

import io
import unittest
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

    def test_feeds_take_turns_spread_across_the_interval(self):
        class Stop(BaseException):
            pass
        polled, sleeps = [], []

        def poll(conn, subreddit):
            polled.append(subreddit)
            if subreddit == "chicagofood":
                raise Exception("429")              # costs its own turn only
            return 0, 1

        def sleep(s):
            sleeps.append(s)
            if len(sleeps) == 7:
                raise Stop

        conn = mock.Mock(closed=0)
        with mock.patch.object(rss.db, "connect", return_value=conn),                 mock.patch.object(rss.db, "init"),                 mock.patch.object(rss.db, "recover", return_value=conn),                 mock.patch.object(rss, "poll_once", poll),                 mock.patch.object(rss.time, "sleep", sleep),                 mock.patch.object(rss.time, "time", return_value=1000.0),                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(Stop):
                rss.run_forever(interval=300, names=("FoodNYC", "chicagofood", "austinfood"))
        self.assertEqual(polled, ["FoodNYC", "chicagofood", "austinfood"] * 2 + ["FoodNYC"])
        self.assertEqual(sleeps, [100.0] * 7)       # one request every 100 s: each feed every 300

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
