"""The poller's embed step must fail soft: nothing in it may block extraction
or the refresh. No database and no network; every step is stubbed.

Embedding runs in the 30-minute chores pass (run_chores), beside settling and
extraction, not in the per-city polls (poll_due)."""

import io
import os
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import fakes  # noqa: F401  (puts the repo root on sys.path)

import embedding
import poller


def args(**kw):
    base = dict(extract=True, extract_days=3, extract_limit=10, extract_workers=1,
                embed=True, embed_days=3, embed_limit=10, embed_max_usd=0.05,
                embed_scope="comments", embed_workers=1)
    base.update(kw)
    return types.SimpleNamespace(**base)


class Chores(unittest.TestCase):
    def run_chores(self, a, **steps):
        calls = []

        def stub(name, result=None, exc=None):
            def f(*_a, **_k):
                calls.append(name)
                if exc:
                    raise exc
                return result
            return f
        patches = {
            "settle_once": stub("settle"),
            "extract_once": stub("extract", result=5), "embed_once": stub("embed", result=3),
            "refresh_once": stub("refresh"),
        }
        for name, (result, exc) in steps.items():
            patches[name] = stub(name.replace("_once", ""), result, exc)
        conn = mock.Mock()
        with mock.patch.multiple(poller, **patches), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            poller.run_chores(conn, a)
        return calls, conn

    def test_order(self):
        calls, _ = self.run_chores(args())
        self.assertEqual(calls, ["settle", "extract", "refresh", "embed"])

    def test_embed_failure_does_not_block_refresh(self):
        calls, conn = self.run_chores(
            args(), embed_once=(None, embedding.ServiceError("OpenRouter is down")))
        self.assertEqual(calls, ["settle", "extract", "refresh", "embed"])
        conn.rollback.assert_called()

    def test_any_embed_exception_is_contained(self):
        for exc in (RuntimeError("bug"), embedding.BudgetExceeded("cap"),
                    ConnectionError("reset"), ValueError("bad vector")):
            calls, _ = self.run_chores(args(), embed_once=(None, exc))
            self.assertIn("refresh", calls, exc)

    def test_extract_failure_still_embeds(self):
        calls, _ = self.run_chores(args(), extract_once=(None, RuntimeError("deepseek down")))
        self.assertEqual(calls, ["settle", "extract", "embed"])

    def test_settle_failure_still_extracts_and_embeds(self):
        calls, _ = self.run_chores(args(), settle_once=(None, RuntimeError("arctic down")))
        self.assertEqual(calls, ["settle", "extract", "refresh", "embed"])

    def test_nothing_extracted_means_no_refresh(self):
        calls, _ = self.run_chores(args(), extract_once=(0, None))
        self.assertEqual(calls, ["settle", "extract", "embed"])

    def test_embed_off(self):
        calls, _ = self.run_chores(args(embed=False))
        self.assertNotIn("embed", calls)

    def test_embed_without_extract(self):
        calls, _ = self.run_chores(args(extract=False))
        self.assertEqual(calls, ["settle", "embed"])

    def test_refresh_runs_before_embed_even_when_embed_hangs(self):
        # #4: the board is rebuilt before embedding starts, so nothing in
        # embedding can delay it.
        calls, _ = self.run_chores(args(), embed_once=(None, TimeoutError("slow")))
        self.assertLess(calls.index("refresh"), calls.index("embed"))

    def test_ctrl_c_in_embed_stops_the_poller(self):
        # #8: _step contains Exception, not KeyboardInterrupt.
        with self.assertRaises(KeyboardInterrupt):
            self.run_chores(args(), embed_once=(None, KeyboardInterrupt()))


class Polls(unittest.TestCase):
    """The per-city polls never run the chores, and a failed one is rescheduled."""

    def poll(self, names, due, fail=(), interval=None):
        calls = []

        def poll_once(_c, name):
            calls.append(name)
            if name in fail:
                raise RuntimeError("arctic down")

        def interval_for(_c, name):
            if interval is None:
                raise RuntimeError("db hiccup")
            return interval
        conn = mock.Mock()
        with mock.patch.multiple(poller, poll_once=poll_once, interval_for=interval_for,
                                 extract_once=mock.Mock(side_effect=AssertionError),
                                 embed_once=mock.Mock(side_effect=AssertionError)), \
                mock.patch.object(poller.time, "time", return_value=1000.0), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            poller.poll_due(conn, names, due)
        return calls, conn

    def test_only_due_cities_are_polled(self):
        due = {"FoodNYC": 0.0, "chicagofood": 5000.0}
        calls, _ = self.poll(list(due), due, interval=900)
        self.assertEqual(calls, ["FoodNYC"])
        self.assertEqual(due, {"FoodNYC": 1900.0, "chicagofood": 5000.0})

    def test_failed_poll_is_rolled_back_and_retried_soon(self):
        due = {"FoodNYC": 0.0, "chicagofood": 0.0}
        calls, conn = self.poll(list(due), due, fail={"FoodNYC"}, interval=None)
        self.assertEqual(calls, ["FoodNYC", "chicagofood"])
        conn.rollback.assert_called()
        self.assertEqual(set(due.values()), {1000.0 + poller.MIN_INTERVAL})


class Boot(unittest.TestCase):
    class Stop(Exception):
        pass

    def boot(self, env, argv):
        out = io.StringIO()
        clean = {k: v for k, v in os.environ.items()
                 if k not in embedding.KEY_VARS and not k.startswith("POLL_")}
        clean.update(env)
        with mock.patch.dict(os.environ, clean, clear=True), \
                mock.patch("sys.argv", ["poller.py", "--no-rss", "--no-backfill", "--once"] + argv), \
                mock.patch.object(poller.db, "connect", side_effect=self.Stop), \
                redirect_stdout(out):
            with self.assertRaises(self.Stop):      # got past the key checks
                poller.main()
        return out.getvalue()

    def test_missing_key_turns_embedding_off_instead_of_failing_boot(self):
        out = self.boot({}, ["--embed"])
        self.assertIn("embedding OFF", out)

    def test_env_switch_and_dedicated_key(self):
        out = self.boot({"POLL_EMBED": "1", "EMBED_OPENROUTER_API_KEY": "k",
                         "OPENROUTER_API_KEY": "shared", "POLL_EMBED_MAX_USD": "0.02"}, [])
        self.assertIn("embedding on: qwen/qwen3-embedding-8b@1024:deepinfra", out)
        self.assertIn("EMBED_OPENROUTER_API_KEY", out)
        self.assertIn("$0.02/cycle", out)

    def test_invalid_scope_turns_embedding_off_at_boot(self):
        # #9: a default from the environment skips argparse's choices.
        out = self.boot({"POLL_EMBED": "1", "EMBED_OPENROUTER_API_KEY": "k",
                         "POLL_EMBED_SCOPE": "comment"}, [])
        self.assertIn("embedding OFF: POLL_EMBED_SCOPE='comment'", out)
        self.assertNotIn("embedding on", out)

    def test_off_by_default(self):
        out = self.boot({"EMBED_OPENROUTER_API_KEY": "k"}, [])
        self.assertNotIn("embedding", out)


if __name__ == "__main__":
    unittest.main()
