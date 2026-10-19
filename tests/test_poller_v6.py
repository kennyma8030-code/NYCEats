"""EXTRACT_VERSION picks the chores pass's extractor; unset changes nothing.
No database and no network; every step is stubbed. tests/test_extract_v6_db.py
runs extract_v6_once itself against a throwaway Postgres.
"""

import io
import os
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import fakes  # noqa: F401  (puts the repo root on sys.path)

import poller


def args(**kw):
    base = dict(extract=True, extract_days=3, extract_limit=10, extract_workers=1, extract_max_usd=1.0,
                embed=False)
    base.update(kw)
    return types.SimpleNamespace(**base)


class Chores(unittest.TestCase):
    def run_chores(self, a):
        calls = []

        def stub(name, result=None):
            def f(*args_, **_k):
                calls.append((name, args_[1:]))
                return result
            return f
        patches = {"settle_once": stub("settle"), "extract_once": stub("legacy", 2),
                   "extract_v6_once": stub("v6", 2), "refresh_once": stub("refresh"),
                   "embed_once": stub("embed")}
        with mock.patch.multiple(poller, **patches), redirect_stdout(io.StringIO()):
            poller.run_chores(mock.Mock(closed=0), a)
        return calls

    def test_default_is_the_old_extractor(self):
        calls = self.run_chores(args())                       # no extract_version at all
        self.assertEqual([c[0] for c in calls], ["settle", "legacy", "refresh"])
        calls = self.run_chores(args(extract_version="legacy"))
        self.assertEqual([c[0] for c in calls], ["settle", "legacy", "refresh"])

    def test_v6_runs_the_v6_step_with_its_cap(self):
        calls = self.run_chores(args(extract_version="v6"))
        self.assertEqual([c[0] for c in calls], ["settle", "v6", "refresh"])
        self.assertEqual(calls[1][1], (3, 10, 1, 1.0))


class Boot(unittest.TestCase):
    def boot(self, env):
        class Stop(Exception):
            pass
        with mock.patch.dict(os.environ, env), mock.patch("sys.argv", ["poller.py", "--extract"]), \
                mock.patch.object(poller.db, "connect", side_effect=Stop), \
                redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            try:
                poller.main()
            except Stop:
                return "booted", out.getvalue()
            except SystemExit as e:
                return str(e), out.getvalue()

    def test_bad_version_fails_the_deploy(self):
        self.assertIn("is not legacy or v6", self.boot({"EXTRACT_VERSION": "v7"})[0])

    def test_v6_needs_its_own_key(self):
        env = {"EXTRACT_VERSION": "v6", "OPENROUTER_API_KEY": "x", "DEEPSEEK_API_KEY": "y",
               "ANTHROPIC_API_KEY": "z"}
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EXTRACT_ANTHROPIC_API_KEY", None)
            self.assertIn("EXTRACT_ANTHROPIC_API_KEY", self.boot(env)[0])

    def test_v6_boot_says_what_it_runs(self):
        res, out = self.boot({"EXTRACT_VERSION": "v6", "EXTRACT_ANTHROPIC_API_KEY": "k"})
        self.assertEqual(res, "booted")
        self.assertIn("inference on: v6 (claude-haiku-5-5, effort medium, prompt 979dcd6b9267/436d834d7edd)",
                      out)


if __name__ == "__main__":
    unittest.main()
