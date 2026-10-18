"""The poller's embed step must fail soft: nothing in it may block extraction
or the refresh. No database and no network; every step is stubbed."""

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


class Cycle(unittest.TestCase):
    def run_cycle(self, a, **steps):
        calls = []

        def stub(name, result=None, exc=None):
            def f(*_a, **_k):
                calls.append(name)
                if exc:
                    raise exc
                return result
            return f
        patches = {
            "poll_once": stub("poll"), "settle_once": stub("settle"),
            "extract_once": stub("extract", result=5), "embed_once": stub("embed", result=3),
            "refresh_once": stub("refresh"),
        }
        for name, (result, exc) in steps.items():
            patches[name] = stub(name.replace("_once", ""), result, exc)
        conn = mock.Mock()
        with mock.patch.multiple(poller, **patches), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            poller.run_cycle(conn, a)
        return calls, conn

    def test_order(self):
        calls, _ = self.run_cycle(args())
        self.assertEqual(calls, ["poll", "settle", "extract", "embed", "refresh"])

    def test_embed_failure_does_not_block_refresh(self):
        calls, conn = self.run_cycle(
            args(), embed_once=(None, embedding.ServiceError("OpenRouter is down")))
        self.assertEqual(calls, ["poll", "settle", "extract", "embed", "refresh"])
        conn.rollback.assert_called()

    def test_any_embed_exception_is_contained(self):
        for exc in (RuntimeError("bug"), embedding.BudgetExceeded("cap"),
                    ConnectionError("reset"), ValueError("bad vector")):
            calls, _ = self.run_cycle(args(), embed_once=(None, exc))
            self.assertIn("refresh", calls, exc)

    def test_extract_failure_still_embeds(self):
        calls, _ = self.run_cycle(args(), extract_once=(None, RuntimeError("deepseek down")))
        self.assertEqual(calls, ["poll", "settle", "extract", "embed"])

    def test_poll_failure_still_extracts_and_embeds(self):
        calls, _ = self.run_cycle(args(), poll_once=(None, RuntimeError("arctic down")))
        self.assertEqual(calls, ["poll", "extract", "embed", "refresh"])

    def test_nothing_extracted_means_no_refresh(self):
        calls, _ = self.run_cycle(args(), extract_once=(0, None))
        self.assertEqual(calls, ["poll", "settle", "extract", "embed"])

    def test_embed_off(self):
        calls, _ = self.run_cycle(args(embed=False))
        self.assertNotIn("embed", calls)

    def test_embed_without_extract(self):
        calls, _ = self.run_cycle(args(extract=False))
        self.assertEqual(calls, ["poll", "settle", "embed"])


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

    def test_off_by_default(self):
        out = self.boot({"EMBED_OPENROUTER_API_KEY": "k"}, [])
        self.assertNotIn("embedding", out)


if __name__ == "__main__":
    unittest.main()
