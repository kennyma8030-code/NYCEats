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


if __name__ == "__main__":
    unittest.main()
