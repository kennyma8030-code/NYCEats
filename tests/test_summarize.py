"""Place summaries without a database: which comments a place sends, how they
are labelled and laid out, when a summary is due, what counts as a usable
answer, the quality-check sample, and the poller's step failing soft.

The database half (qualification, writes, the cap and the ceiling, parking)
is test_summarize_db.py. Nothing here touches the network.
"""

import datetime as dt
import io
import json
import os
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import fakes  # noqa: F401  (puts the repo root on sys.path)

import anthropic_v6 as AV
import extract_v6 as EV
import fake_anthropic as F
import poller
import summarize as S

NOW = dt.datetime(2026, 11, 3, 12, tzinfo=dt.timezone.utc)
SINCE = NOW - dt.timedelta(days=S.WINDOW_DAYS)


def comment(i, days, reads=(("stated", 1, False),), status=None, chars=100, names=("Alpha",)):
    return S.Comment(f"t1_{i}", NOW - dt.timedelta(days=days), "Where to eat?", f"body {i}", chars,
                     list(names), list(reads), status)


class Select(unittest.TestCase):
    def test_every_recent_opinion_when_there_are_sixty_or_more(self):
        cs = [comment(i, 1 + i) for i in range(70)] + [comment(100 + i, 400 + i) for i in range(10)]
        inp = S.select("alpha", cs, SINCE)
        self.assertEqual(len(inp.comments), 70)
        self.assertTrue(all(c.created > SINCE for c in inp.comments))
        self.assertEqual((inp.recent, inp.available), (70, 80))

    def test_under_sixty_tops_up_with_older_ones_newest_first(self):
        recent = [comment(i, 10 + i) for i in range(20)]
        older = [comment(100 + i, 400 + i) for i in range(50)]
        inp = S.select("alpha", older + recent, SINCE)
        self.assertEqual(len(inp.comments), S.TARGET_COMMENTS)
        self.assertEqual([c.id for c in inp.comments[:20]], [c.id for c in recent])
        # the 40 newest of the older ones, in order; the 10 oldest are left out
        self.assertEqual([c.id for c in inp.comments[20:]], [c.id for c in older[:40]])

    def test_top_up_stops_when_nothing_is_left(self):
        inp = S.select("alpha", [comment(1, 5), comment(2, 500)], SINCE)
        self.assertEqual([c.id for c in inp.comments], ["t1_1", "t1_2"])

    def test_a_comment_with_no_opinion_is_never_sent_as_one(self):
        # The SQL gives a comment reads only for opinions that count (endorse
        # or stated, not past); one with none is not an opinion.
        inp = S.select("alpha", [comment(1, 5), comment(2, 6, reads=())], SINCE)
        self.assertEqual([c.id for c in inp.comments], ["t1_1"])

    def test_status_reports_ride_apart_and_are_not_repeated(self):
        cs = [comment(1, 5, status="closed"),                    # an opinion that says closed
              comment(2, 6, reads=(), status="closed"),          # "they closed last month"
              *[comment(10 + i, 20 + i, reads=(), status="moved") for i in range(8)]]
        inp = S.select("alpha", cs, SINCE)
        self.assertEqual([c.id for c in inp.comments], ["t1_1"])
        self.assertEqual(len(inp.reports), S.STATUS_REPORTS)
        self.assertEqual(inp.reports[0].id, "t1_2")
        self.assertNotIn("t1_1", [c.id for c in inp.reports])

    def test_budget_keeps_the_newest(self):
        cs = [comment(i, 1 + i, chars=1000) for i in range(10)]
        per = (1000 + S.COMMENT_OVERHEAD_CHARS) / S.CHARS_PER_TOKEN_BUDGET
        inp = S.select("alpha", cs, SINCE, budget_tokens=per * 3.5)
        self.assertEqual([c.id for c in inp.comments], ["t1_0", "t1_1", "t1_2"])
        self.assertEqual(inp.dropped, 7)

    def test_name_is_the_spelling_people_use_most(self):
        cs = [comment(1, 1, names=("Katz's",)), comment(2, 2, names=("Katz's", "Katzs")),
              comment(3, 3, names=("katz deli",))]
        self.assertEqual(S.select("katzs delicatessen", cs, SINCE).name, "Katz's")


class Labels(unittest.TestCase):
    def label(self, *reads):
        return comment(1, 1, reads=reads).label()

    def test_order(self):
        self.assertEqual(self.label(("endorse", 1, False), ("stated", 2, True)), "warns against it")
        self.assertEqual(self.label(("endorse", 1, False), ("stated", -1, False)), "criticism")
        self.assertEqual(self.label(("endorse", 2, False)), "recommends")
        self.assertEqual(self.label(("stated", 1, False), ("stated", -2, False)), "harsh criticism")
        self.assertEqual(self.label(("stated", 1, False), ("stated", -1, False)), "criticism")
        self.assertEqual(self.label(("stated", 0, False)), "mixed")
        self.assertEqual(self.label(("stated", None, False)), "opinion")


class Render(unittest.TestCase):
    def test_layout(self):
        cs = [comment(1, 1, names=('The "Spot"',)), comment(2, 2, reads=(("stated", -1, False),)),
              comment(3, 3, reads=(("endorse", None, False),)),
              comment(4, 4, reads=(), status="closed")]
        text = S.render(S.select("spot", cs, SINCE), NOW)
        self.assertIn("<today>2026-11-03</today>", text)
        self.assertIn("<place>Alpha</place>", text)           # the most used spelling
        self.assertIn('count="3" praise="1" criticism="1" mixed="0" recommends="1" other="0"', text)
        self.assertIn('names="The \'Spot\'" read_as="praise"', text)
        self.assertIn("<thread_title>Where to eat?</thread_title>\nbody 2", text)
        self.assertIn('<status_reports count="1">', text)
        self.assertIn('reports="closed"', text)
        self.assertLess(text.index("body 1"), text.index("body 2"))      # newest first

    def test_no_status_section_without_reports(self):
        self.assertNotIn("status_reports", S.render(S.select("a", [comment(1, 1)], SINCE), NOW))

    def test_params(self):
        p = S.params("hi", "low")
        self.assertEqual(p["model"], "claude-haiku-5-5")
        self.assertEqual(p["thinking"], {"type": "adaptive"})
        self.assertEqual(p["output_config"]["effort"], "low")
        self.assertEqual(p["output_config"]["format"]["schema"]["required"], ["summary"])
        for banned in ("temperature", "top_p", "top_k"):
            self.assertNotIn(banned, p)


def place(**kw):
    base = dict(key="alpha", n=20, newest=NOW, opinions=10, negative=2, closed=0, fresh=0,
                has_summary=True, model=S.MODEL, prompt_hash="h", attempts=0)
    base.update(kw)
    return S.Place(**base)


class Due(unittest.TestCase):
    def reason(self, **kw):
        return S.due_reason(place(**kw), S.MODEL, "h", 5)

    def test_reasons(self):
        self.assertEqual(self.reason(has_summary=False, model=None, prompt_hash=None), "new")
        self.assertIsNone(self.reason(fresh=4))
        self.assertEqual(self.reason(fresh=5), "fresh")
        self.assertEqual(self.reason(prompt_hash="old"), "prompt")
        self.assertEqual(self.reason(model="claude-haiku-4-5"), "prompt")
        self.assertEqual(self.reason(attempts=S.MAX_ATTEMPTS, has_summary=False), "parked")
        self.assertEqual(self.reason(attempts=S.MAX_ATTEMPTS - 1, has_summary=False), "new")
        self.assertEqual(S.due_reason(place(), S.MODEL, "h", 5, force=True), "forced")

    def test_order(self):
        ps = [place(key="old", prompt_hash="x", n=500), place(key="busy", fresh=9, n=50),
              place(key="quiet", fresh=5, n=900), place(key="small", has_summary=False, n=10),
              place(key="big", has_summary=False, n=99), place(key="done", fresh=1),
              place(key="stuck", has_summary=False, attempts=3)]
        self.assertEqual([p.key for p, _ in S.due(ps, S.MODEL, "h", 5)],
                         ["big", "small", "busy", "quiet", "old"])


def answer(text, stop="end_turn"):
    return F.message(json.dumps({"summary": text}) if text is not None else None, stop=stop)


class ReadSummary(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(S.read_summary(answer("Commenters  love it.\n Some find it pricey.")),
                         "Commenters love it. Some find it pricey.")

    def test_unusable(self):
        cases = {"empty_summary": answer("  "), "names_user": answer("u/foodie says it is great."),
                 "too_long": answer("x" * 1600), "max_tokens": answer("cut", stop="max_tokens"),
                 "refusal": answer(None, stop="refusal"), "invalid_json": F.message("not json")}
        for code, msg in cases.items():
            with self.assertRaises(AV.ItemError, msg=code) as cm:
                S.read_summary(msg)
            self.assertEqual(cm.exception.code, code)

    def test_a_slash_in_a_name_is_not_a_user(self):
        self.assertTrue(S.read_summary(answer("Commenters like the 1/2 price menu and Chu/Lou's.")))


class Settings(unittest.TestCase):
    def test_defaults_and_overrides(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in (S.MIN_MENTIONS_ENV, S.NEW_MENTIONS_ENV, S.RUN_ENV, S.CEILING_ENV):
                os.environ.pop(k, None)
            self.assertEqual(S.setting(S.MIN_MENTIONS_ENV, int), 10)
            self.assertEqual(S.setting(S.NEW_MENTIONS_ENV, int), 5)
            self.assertEqual(S.setting(S.RUN_ENV), 1.0)
            self.assertEqual(S.setting(S.CEILING_ENV), 10.0)
            os.environ[S.MIN_MENTIONS_ENV] = "15"
            self.assertEqual(S.setting(S.MIN_MENTIONS_ENV, int), 15)
            for bad in ("0", "-1", "ten"):
                os.environ[S.CEILING_ENV] = bad
                with self.assertRaises(SystemExit):
                    S.setting(S.CEILING_ENV)

    def test_prompt_hash_moves_with_what_shapes_the_answer(self):
        self.assertEqual(S.prompt_hash("low"), S.prompt_hash("low"))
        self.assertNotEqual(S.prompt_hash("low"), S.prompt_hash("medium"))
        before = S.prompt_hash("low")
        for name, value in (("SYSTEM_PROMPT", S.SYSTEM_PROMPT + " "), ("FORMAT_VERSION", "x"),
                            ("TARGET_COMMENTS", 61), ("MAX_TOKENS", 4001)):
            with mock.patch.object(S, name, value):
                self.assertNotEqual(S.prompt_hash("low"), before, name)

    def test_bad_effort_refuses(self):
        with mock.patch.dict(os.environ, {S.EFFORT_ENV: "max"}):
            with self.assertRaises(SystemExit):
                S.effort()


class Sample(unittest.TestCase):
    def test_mix(self):
        ps = [place(key=f"p{i}", n=10 + i, opinions=10 + i // 2, negative=(i % 7) * 2,
                    closed=1 if i % 40 == 0 else 0) for i in range(400)]
        out = S.pick_sample(ps, 50)
        self.assertEqual(len(out), 50)
        self.assertEqual(len({p.key for p, _ in out}), 50)
        why = [w for _, w in out]
        for kind in ("busiest", "complaints", "closed or moved", "just qualifying", "middle"):
            self.assertIn(kind, why)
        self.assertEqual([p.key for p, w in out if w == "busiest"][:2], ["p399", "p398"])
        self.assertTrue(all(p.n <= 12 for p, w in out if w == "just qualifying"))
        self.assertEqual(out, S.pick_sample(ps, 50))        # the same sample every time


def chores_args(**kw):
    base = dict(extract=False, embed=False, summarize=True, summarize_limit=10, summarize_workers=1)
    base.update(kw)
    return types.SimpleNamespace(**base)


class Poller(unittest.TestCase):
    def run_chores(self, a, summarize_exc=None):
        calls = []

        def stub(name, exc=None):
            def f(*_a, **_k):
                calls.append(name)
                if exc:
                    raise exc
            return f
        conn = mock.Mock(closed=0)
        with mock.patch.multiple(poller, settle_once=stub("settle"), refresh_once=stub("refresh"),
                                 embed_once=stub("embed"),
                                 summarize_once=stub("summarize", summarize_exc)), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            poller.run_chores(conn, a)
        return calls

    def test_last_and_contained(self):
        self.assertEqual(self.run_chores(chores_args(embed=True, embed_days=3, embed_limit=1,
                                                     embed_max_usd=0.01, embed_scope="comments",
                                                     embed_workers=1)),
                         ["settle", "embed", "summarize"])
        self.assertEqual(self.run_chores(chores_args(), RuntimeError("bug")), ["settle", "summarize"])

    def test_off(self):
        self.assertEqual(self.run_chores(chores_args(summarize=False)), ["settle"])
        a = types.SimpleNamespace(extract=False, embed=False)       # an args from before summaries
        self.assertEqual(self.run_chores(a), ["settle"])

    def test_boot_without_a_key_turns_it_off(self):
        lines = []
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(S.KEY_VAR, None)
            self.assertFalse(poller.summarize_boot(log=lines.append))
        self.assertIn(S.KEY_VAR, lines[0])

    def test_boot_with_a_bad_setting_turns_it_off_not_the_poller(self):
        lines = []
        with mock.patch.dict(os.environ, {S.KEY_VAR: "k", S.RUN_ENV: "lots"}):
            self.assertFalse(poller.summarize_boot(log=lines.append))
        self.assertIn("OFF", lines[0])

    def test_boot_with_a_key(self):
        lines = []
        with mock.patch.dict(os.environ, {S.KEY_VAR: "k"}):
            for k in (S.RUN_ENV, S.CEILING_ENV, S.EFFORT_ENV):
                os.environ.pop(k, None)
            self.assertTrue(poller.summarize_boot(log=lines.append))
        self.assertIn("summaries on", lines[0])
        self.assertIn("$1.00/cycle, $10.00 ceiling", lines[0])

    def test_a_tripwire_switches_it_off(self):
        a = chores_args()
        with mock.patch.object(S, "poll_once", side_effect=EV.Tripped("over")), \
                redirect_stdout(io.StringIO()) as out:
            self.assertEqual(poller.summarize_once(mock.Mock(), a), 0)
        self.assertFalse(a.summarize)
        self.assertIn("SUMMARIES OFF", out.getvalue())

    def test_missing_key_skips_without_a_call(self):
        lines = []
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(S.KEY_VAR, None)
            conn = mock.Mock()
            self.assertIsNone(S.poll_once(conn, 10, log=lines.append))
        self.assertIn("no SUMMARY_ANTHROPIC_API_KEY", lines[0])
        conn.cursor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
