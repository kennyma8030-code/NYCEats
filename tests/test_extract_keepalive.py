"""The extractor keeping its lock's connection alive while it waits on the
API, by time passed rather than by what the wait returned. No database, no
network: the connection and the API call are stand-ins."""

import threading
import time
import unittest
from unittest import mock

import fakes  # noqa: F401  (puts the repo root on sys.path)

import anthropic_v6 as AV
import extract_v6 as X


class Req:
    stream = False

    def __init__(self, name, seconds):
        self.id, self.seconds = name, seconds

    def worst(self, batch):
        return 0.01

    def params(self):
        return self


class DirectRun(unittest.TestCase):
    def test_answers_that_write_nothing_do_not_stand_in_for_a_ping(self):
        # Three requests out at once, failing one after another, each inside
        # the keep-alive interval of the one before. Every wait returned an
        # answer, so the ping that fired only on an empty wait never did,
        # though no answer here touches the database.
        def call(cl, req, **kw):
            time.sleep(req.seconds)
            raise AV.TransientAPIError("overloaded")
        pings, unsent = [], []
        with mock.patch.object(X, "KEEPALIVE_SECONDS", 0.25), mock.patch.object(X.AV, "call", call), \
                mock.patch.object(X, "keep_alive", lambda conn: pings.append(time.monotonic())):
            started = time.monotonic()
            with self.assertRaises(AV.TransientAPIError):
                X._send_direct(None, X.Budget(10), [Req("a", 0.15), Req("b", 0.3), Req("c", 0.45)], 3,
                               threading.Event(), threading.Event(), lambda *_: None,
                               lambda *a: self.fail("nothing was answered"),
                               lambda req, why: unsent.append(req.id), X.Pulse("conn").beat)
        self.assertEqual(unsent, ["a", "b", "c"])
        self.assertTrue(pings, "0.45 s went by with no query on the connection")
        self.assertLess(pings[0] - started, 0.44)

    def test_a_pulse_pings_by_the_clock_and_not_more_often(self):
        pings = []
        now = [100.0]
        with mock.patch.object(X, "keep_alive", pings.append), \
                mock.patch.object(X.time, "monotonic", lambda: now[0]):
            pulse = X.Pulse("conn")
            for at in (110, 159.9, 160, 161, 219.9, 220.5):
                now[0] = at
                pulse.beat()
                self.assertEqual(len(pings), {110: 0, 159.9: 0, 160: 1, 161: 1, 219.9: 1, 220.5: 2}[at], at)
        self.assertEqual(pings, ["conn", "conn"])


class LongCall(unittest.TestCase):
    def test_a_long_api_call_is_pinged_from_beside_it_and_not_after(self):
        pings = []
        with mock.patch.object(X, "KEEPALIVE_SECONDS", 0.03), \
                mock.patch.object(X, "keep_alive", lambda conn: pings.append(threading.current_thread().name)):
            with X._kept_alive("conn"):
                time.sleep(0.2)
            during = len(pings)
            time.sleep(0.1)
        self.assertGreaterEqual(during, 2)
        self.assertEqual(len(pings), during)                    # the thread ended with the call
        self.assertEqual(set(pings), {"extract-keepalive"})

    def test_a_short_call_is_not_pinged_and_a_dead_connection_is_left_to_the_caller(self):
        with mock.patch.object(X, "keep_alive", side_effect=AssertionError("pinged")):
            with X._kept_alive("conn"):
                pass
        # The ping that finds the connection gone ends the thread; the block
        # itself raises nothing, and what it raises is still its own.
        dead = mock.Mock(side_effect=OSError("server closed the connection"))
        with mock.patch.object(X, "KEEPALIVE_SECONDS", 0.01), mock.patch.object(X, "keep_alive", dead):
            with X._kept_alive("conn"):
                time.sleep(0.08)
            with self.assertRaises(KeyError):
                with X._kept_alive("conn"):
                    raise KeyError("the call's own error")
        self.assertEqual(dead.call_count, 1)


if __name__ == "__main__":
    unittest.main()
