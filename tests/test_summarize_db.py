"""Place summaries against a real, throwaway Postgres, with tests/fake_anthropic.py
as the API, so nothing is billed.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55439/nyceatstest python -m pytest tests

Covers who qualifies (n, the window, the v6 mentions live_mentions counts,
deleted comments, excluded names, aliases, one comment counted once), what
is sent, the write and its watermark on when mentions were stored, the
x-new rewrite and the share, failure parking, API refusals per place and
for the account, the per-pass cap, the lifetime ceiling, the tripwire, a
timeout's charge, the ledger surviving a failed store, the legacy read mode,
the pass gate, and the poller's step end to end. Skipped without
TEST_DATABASE_URL.
"""

import datetime as dt
import json
import os
import tempfile
import time
import unittest
from unittest import mock

import anthropic
import httpx2

import anthropic_v6 as AV
import extract_v6 as EV
import fake_anthropic as F
import pgtest
import prompt_v6
import refresh
import subreddits
import summarize as S

TH = prompt_v6.PROMPT_HASH_THREAD
QUIET = lambda *a, **k: None  # noqa: E731
PH = S.Settings().prompt_hash


def ok(text="Commenters say it is good, though some find it pricey."):
    return 200, F.message(json.dumps({"summary": text}))


class SummaryCase(pgtest.PgCase):
    def setUp(self):
        super().setUp()
        self.n = 0
        with self.conn.cursor() as cur:
            cur.execute("""insert into threads (id, subreddit, title, created_utc)
                           values ('t3_s', %s, 'Where to eat?', now() - interval '900 days')""",
                        (subreddits.HOME,))
            cur.execute("update extraction_settings set read_version = 'v6'")
        self.conn.commit()

    def mention(self, key, days, opinion="stated", level=1, avoid=False, timeframe="current", status=None,
                deleted=False, author=None, prompt_hash=TH, cid=None, raw=None, body=None, state_hash=None):
        """One mention, on a new comment unless cid names one. state_hash is
        the hash on the comment's cursor row, the mention's own unless given
        (a different one makes the mention stale, so live_mentions drops it)."""
        self.n += 1
        cid = cid or f"t1_s{self.n}"
        with self.conn.cursor() as cur:
            cur.execute("""insert into comments (id, thread_id, parent_id, author, body, permalink,
                                                 created_utc, score, score_settled, was_deleted_later)
                           values (%s, 't3_s', 't3_s', %s, %s, '/r/x', now() - make_interval(days => %s),
                                   1, true, %s)
                           on conflict (id) do nothing""",
                        (cid, author or f"u{self.n}", body or f"about {key} #{self.n}", days, deleted))
            cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash, extracted_at)
                           values (%s, 'v6', 'comment', %s, now()) on conflict do nothing""",
                        (cid, state_hash or prompt_hash))
            cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key, model_version,
                                                 prompt_hash, schema_version, kind, opinion, overall_level,
                                                 avoid, timeframe, status)
                           values (%s, %s, %s, 'm', %s, 6, 'restaurant', %s, %s, %s, %s, %s)""",
                        (cid, raw or key, key, prompt_hash, opinion, level, avoid, timeframe, status))
        self.conn.commit()
        return cid

    def many(self, key, count, start=1, **kw):
        return [self.mention(key, start + i, **kw) for i in range(count)]

    def build(self):
        """entity_alias and the rest of the views, as a refresh leaves them."""
        refresh.apply_sql(self.conn, verbose=False)
        self.conn.commit()

    def places(self, n=10):
        return {p.key: p for p in S.qualifying(self.conn, n)}

    def budget(self, max_usd=1.0, ceiling=10.0):
        b = S.make_budget(max_usd, ceiling, pgtest.connect)
        self.addCleanup(b.ceiling.close)
        return b

    def write(self, answer=lambda p: ok(), max_usd=1.0, ceiling=10.0, keys=None, force=False, workers=2,
              **kw):
        todo = S.due(list(self.places().values()), S.MODEL, PH, 5, force)
        if keys is not None:
            todo = [(p, r) for p, r in todo if p.key in keys]
        b = self.budget(max_usd, ceiling)
        with F.FakeAnthropic(answer) as api:
            stats = S.run(self.conn, AV.client("k", api.base_url), b, todo, workers=workers, attempts=2,
                          sleep=lambda s: None, log=QUIET, keep=True, connect=pgtest.connect, **kw)
        return stats, api, b

    def row(self, key):
        return self.q("""select summary, mention_count, last_mention_at, attempts, error, input_comments
                         from place_summaries where resolved_key = %s""", key)

    def reason(self, key, x=5, share=0.0, force=False):
        return S.due_reason(self.places()[key], S.MODEL, PH, x, force, share)

    def ledger(self):
        return self.q("select resolved_key, outcome, cost_usd from summary_calls order by id")


class Qualifies(SummaryCase):
    def test_n_in_the_window_counting_every_kind_of_mention(self):
        self.many("alpha", 6)
        self.many("alpha", 4, start=10, opinion="none", level=None)    # questions, passing names count
        self.many("beta", 9)
        self.many("beta", 3, start=400)                                # over a year old: not counted
        self.build()
        ps = self.places()
        self.assertEqual(set(ps), {"alpha"})
        self.assertEqual(ps["alpha"].n, 10)
        self.assertEqual(ps["alpha"].opinions, 6)

    def test_what_does_not_count(self):
        self.many("gamma", 9)
        self.mention("gamma", 2, deleted=True)
        self.mention("gamma", 3, author="AutoModerator")
        self.mention("gamma", 4, state_hash="newer")                   # stale: live_mentions drops it
        self.many("whole foods", 12)
        with self.conn.cursor() as cur:
            cur.execute("insert into excluded_entities (entity_key, note) values ('whole foods', 'grocery')")
        self.conn.commit()
        self.build()
        self.assertEqual(self.places(), {})

    def test_the_mentions_the_board_counts_comment_mode_fallbacks_included(self):
        # A thread chunk that failed is re-extracted one item at a time in
        # comment mode; live_mentions counts those rows, and so must we.
        self.many("delta", 7)
        cids = self.many("delta", 3, start=20, prompt_hash=prompt_v6.PROMPT_HASH, body="FALLBACK")
        self.build()
        self.assertEqual(self.places()["delta"].n, 10)
        live = self.q("""select count(distinct comment_id) from live_mentions where entity_key = 'delta'""")[0][0]
        self.assertEqual(live, 10)
        _, since = S._since(self.conn)
        sent = [c.id for c in S.read_inputs(self.conn, ["delta"], since)["delta"].comments]
        self.assertTrue(set(cids) <= set(sent))

    def test_nothing_while_the_board_reads_legacy(self):
        self.many("alpha", 12)
        self.build()
        with self.conn.cursor() as cur:
            cur.execute("update extraction_settings set read_version = 'legacy'")
        self.conn.commit()
        lines = []
        with F.FakeAnthropic(lambda p: ok()) as api:
            self.assertIsNone(S.poll_once(self.conn, 10, settings=S.Settings(), cl=AV.client("k", api.base_url),
                                          connect=pgtest.connect, log=lines.append))
        self.assertIn("legacy", lines[0])
        self.assertEqual(api.requests, [])

    def test_aliases_share_one_place_and_a_comment_counts_once(self):
        self.many("katzs", 5)
        cids = self.many("katzs delicatessen", 4)
        self.mention("katzs", 1, cid=cids[0])                           # same comment, both spellings
        self.mention("katz", 7)
        with self.conn.cursor() as cur:
            cur.execute("""insert into alias_overrides (entity_key, resolved_key, note)
                           values ('katzs', 'katzs delicatessen', 't'), ('katz', 'katzs delicatessen', 't')""")
        self.conn.commit()
        self.build()
        ps = self.places()
        self.assertEqual(set(ps), {"katzs delicatessen"})
        self.assertEqual(ps["katzs delicatessen"].n, 10)

    def test_settings_move_the_line(self):
        self.many("alpha", 12)
        self.build()
        self.assertEqual(len(S.qualifying(self.conn, 12)), 1)
        self.assertEqual(len(S.qualifying(self.conn, 13)), 0)
        self.assertEqual([p.key for p in S.qualifying(self.conn, 10, keys=["alpha", "zzz"])], ["alpha"])
        self.assertEqual(S.qualifying(self.conn, 10, keys=[]), [])


class Inputs(SummaryCase):
    def test_what_is_sent(self):
        keep = self.many("alpha", 5, body="good")
        self.many("alpha", 3, start=10, opinion="none", level=None, body="QUESTION")
        self.mention("alpha", 2, timeframe="past", body="USED TO BE")
        self.mention("alpha", 3, deleted=True, body="DELETED")
        closed = self.mention("alpha", 4, opinion="none", level=None, timeframe="past", status="closed",
                              body="they closed")
        older = self.many("alpha", 3, start=500, body="older")          # the top-up
        self.build()
        _, since = S._since(self.conn)
        inp = S.read_inputs(self.conn, ["alpha"], since)["alpha"]
        self.assertEqual([c.id for c in inp.comments], keep + older)
        self.assertEqual([c.id for c in inp.reports], [closed])
        text = S.render(inp, dt.date(2026, 11, 3))
        for gone in ("QUESTION", "USED TO BE", "DELETED"):
            self.assertNotIn(gone, text)

    def test_a_comment_about_two_places_says_which(self):
        cid = self.mention("alpha", 1, raw="Alpha Bar", body="Alpha Bar is great, Beta Cafe is not")
        self.mention("beta cafe", 1, cid=cid, level=-1, raw="Beta Cafe")
        self.build()
        _, since = S._since(self.conn)
        got = S.read_inputs(self.conn, ["alpha", "beta cafe"], since)
        a, b = S.render(got["alpha"], dt.date.today()), S.render(got["beta cafe"], dt.date.today())
        self.assertIn('<place>Alpha Bar</place>', a)
        self.assertIn('names="Alpha Bar" read_as="praise"', a)
        self.assertIn('<place>Beta Cafe</place>', b)
        self.assertIn('names="Beta Cafe" read_as="criticism"', b)


class Writes(SummaryCase):
    def setUp(self):
        super().setUp()
        self.many("alpha", 10)
        self.build()

    def test_write_and_watermark(self):
        stats, api, b = self.write()
        self.assertEqual(stats.written, 1)
        summary, count, last, attempts, err, sent = self.row("alpha")[0]
        self.assertEqual((count, attempts, err, sent), (10, 0, None, 10))
        self.assertTrue(summary.startswith("Commenters say"))
        newest = self.q("select max(created_utc) from comments")[0][0]
        self.assertEqual(last, newest)
        [(key, outcome, cost)] = self.ledger()
        self.assertEqual((key, outcome), ("alpha", "written"))
        self.assertAlmostEqual(float(cost), b.spent, places=8)
        sent_req = api.requests[0]
        self.assertEqual(sent_req["model"], "claude-haiku-5-5")
        self.assertIn("<place>alpha</place>", sent_req["messages"][0]["content"])

    def test_rewritten_only_after_x_new(self):
        self.write()
        for i in range(4):
            self.mention("alpha", 0)
        self.build()
        self.assertIsNone(self.reason("alpha"))
        self.mention("alpha", 0)
        self.build()
        p = self.places()["alpha"]
        self.assertEqual((p.fresh, self.reason("alpha")), (5, "fresh"))
        stats, _, _ = self.write(lambda p: ok("Commenters now say it changed."))
        self.assertEqual(stats.written, 1)
        self.assertEqual(self.row("alpha")[0][1], 15)
        self.assertEqual(self.places()["alpha"].fresh, 0)

    def test_a_mention_extracted_late_is_new(self):
        # Comments written months ago and only extracted now (the backlog, a
        # late comment on an old thread): their mentions are stored after the
        # summary, so they count, though every comment is older than the
        # newest one the summary saw.
        self.write()
        seen = self.q("select seen_through from place_summaries")[0][0]
        self.assertEqual(seen, self.q("select max(created_at) from mentions")[0][0])
        for i in range(5):
            self.mention("alpha", 200 + i)
        self.build()
        self.assertEqual((self.places()["alpha"].fresh, self.reason("alpha")), (5, "fresh"))

    def test_share_raises_the_bar(self):
        self.write()
        for i in range(5):
            self.mention("alpha", 0)
        self.build()
        self.assertEqual(self.reason("alpha", share=0.1), "fresh")       # ceil(0.1 x 15) = 2 < 5
        self.assertIsNone(self.reason("alpha", share=0.5))               # ceil(0.5 x 15) = 8

    def test_old_comments_falling_out_do_not_hide_new_ones(self):
        # The count stays at 10 while 5 new comments arrive, because 5 old ones
        # leave the window; the date watermark still sees the 5 new ones.
        with self.conn.cursor() as cur:
            cur.execute("update comments set created_utc = now() - interval '360 days' where id in "
                        "(select id from comments order by created_utc limit 5)")
        self.conn.commit()
        self.build()
        self.write()
        with self.conn.cursor() as cur:
            cur.execute("update comments set created_utc = now() - interval '370 days' where "
                        "created_utc < now() - interval '300 days'")
        self.conn.commit()
        for i in range(5):
            self.mention("alpha", 0)
        self.build()
        p = self.places()["alpha"]
        self.assertEqual((p.n, p.fresh), (10, 5))

    def test_a_prompt_change_rewrites(self):
        self.write()
        with mock.patch.object(S, "FORMAT_VERSION", "next"):
            self.assertEqual(S.due_reason(self.places()["alpha"], S.MODEL, S.Settings().prompt_hash, 5),
                             "prompt")

    def test_failure_keeps_the_summary_counts_and_parks(self):
        self.write()
        self.mention("alpha", 0)
        self.build()
        for attempt in range(1, S.MAX_ATTEMPTS + 1):
            stats, _, _ = self.write(lambda p: ok("  "), force=True, keys=["alpha"])
            self.assertEqual(stats.failed, 1)
            summary, _, _, attempts, err, _ = self.row("alpha")[0]
            self.assertEqual(attempts, attempt)
            self.assertTrue(summary.startswith("Commenters say"))        # the last good one stays
            self.assertEqual(err, "empty_summary")
        self.assertEqual(stats.parked, 1)
        self.assertEqual(self.reason("alpha", force=True), "parked")
        self.assertEqual([o for _, o, _ in self.ledger()], ["written"] + ["empty_summary"] * S.MAX_ATTEMPTS)
        self.assertEqual(S.retry_errors(self.conn), 1)
        self.assertEqual(self.row("alpha")[0][3], 0)

    def test_a_new_place_that_fails_has_no_summary_and_is_retried(self):
        self.write(lambda p: (200, F.message("not json")))
        summary, _, _, attempts, err, _ = self.row("alpha")[0]
        self.assertEqual((summary, attempts), (None, 1))
        self.assertTrue(err.startswith("invalid_json"))
        self.assertEqual(self.reason("alpha"), "new")

    def test_a_place_the_api_refuses_counts_an_attempt_and_the_pass_goes_on(self):
        self.many("beta", 10)
        self.build()

        def answer(p):
            if "<place>alpha</place>" in p["messages"][0]["content"]:
                return F.error(400, "invalid_request_error", "this one is too odd")
            return ok()
        for attempt in range(1, S.MAX_ATTEMPTS + 1):
            stats, api, b = self.write(answer, workers=1, keys=["alpha", "beta"] if attempt == 1 else ["alpha"])
            self.assertIsNone(stats.stop)
            _, _, _, attempts, err, _ = self.row("alpha")[0]
            self.assertEqual(attempts, attempt)
            self.assertTrue(err.startswith("api: FatalAPIError: http 400"))
        self.assertEqual(self.row("beta")[0][3], 0)                      # beta was written all the same
        self.assertTrue(self.row("beta")[0][0])
        self.assertEqual(self.reason("alpha"), "parked")
        self.assertEqual([o for _, o, _ in self.ledger()], ["written"])   # a refusal is not billed

    def test_a_refusal_every_call_would_get_stops_the_pass_and_marks_nothing(self):
        self.many("beta", 10)
        self.build()
        stats, api, b = self.write(lambda p: F.error(401, "authentication_error", "bad key"), workers=1)
        self.assertIn("FatalAPIError", stats.stop)
        self.assertEqual(len(api.requests), 1)
        self.assertEqual(self.q("select count(*) from place_summaries")[0][0], 0)
        self.assertEqual(self.ledger(), [])
        self.assertEqual(b.spent, 0.0)

    def test_failures_in_a_row_stop_the_pass(self):
        for k in ("beta", "gamma", "delta"):
            self.many(k, 10)
        self.build()
        stats, api, _ = self.write(lambda p: F.error(400, "invalid_request_error", "bad param"), workers=1)
        self.assertIn(f"{S.API_FAILURES_IN_A_ROW} places in a row", stats.stop)
        self.assertEqual(len(api.requests), S.API_FAILURES_IN_A_ROW)
        self.assertEqual(stats.failed, S.API_FAILURES_IN_A_ROW)

    def test_paid_answers_reach_the_ledger_even_when_storing_fails(self):
        self.many("beta", 10)
        self.build()
        with mock.patch.object(S, "store", side_effect=RuntimeError("disk full")), \
                self.assertRaises(RuntimeError):
            self.write(workers=2)
        rows = self.ledger()
        self.assertEqual(len(rows), 2)                                   # both answers were paid for
        self.assertEqual({o for _, o, _ in rows} - {"written", "unstored"}, set())
        self.assertEqual(self.q("select count(*) from place_summaries where summary is not null")[0][0], 0)

    def test_a_broken_connection_flushes_on_a_fresh_one(self):
        self.many("beta", 10)
        self.build()
        real = S.record_calls
        def flaky(conn, *a, **k):
            if conn is self.conn:
                raise RuntimeError("connection lost")
            return real(conn, *a, **k)
        with mock.patch.object(S, "record_calls", side_effect=flaky), self.assertRaises(RuntimeError):
            self.write(workers=2)
        self.assertEqual(sorted(o for _, o, _ in self.ledger()), ["unstored", "unstored"])


class Spend(SummaryCase):
    def setUp(self):
        super().setUp()
        for k in ("alpha", "beta", "gamma"):
            self.many(k, 10)
        self.build()

    def test_the_cap_stops_before_a_call_that_would_not_fit(self):
        stats, api, b = self.write(max_usd=0.001)                       # under one worst case
        self.assertEqual(api.requests, [])
        self.assertEqual(stats.written, 0)
        self.assertIn("per-pass cap", stats.stop)
        self.assertEqual(b.refused_by, "cap")

    def test_the_cap_lets_some_through(self):
        # Room for one worst case and a sliver: one call goes, and once it is
        # settled at its real (smaller) cost there is still no room for a
        # second worst case, so the pass stops there, loudly.
        _, worst = self.one_worst()
        stats, api, b = self.write(max_usd=worst * 1.05)
        self.assertEqual((stats.written, len(api.requests)), (1, 1))
        self.assertIn("per-pass cap", stats.stop)
        self.assertLessEqual(b.spent, worst * 1.05)

    def one_worst(self):
        _, since = S._since(self.conn)
        inp = S.read_inputs(self.conn, ["alpha"], since)["alpha"]
        user = S.render(inp, dt.date.today())
        return user, S.worst(user)

    def test_the_ceiling_counts_spend_on_record(self):
        _, worst = self.one_worst()
        with self.conn.cursor() as cur:
            cur.execute("""insert into summary_calls (resolved_key, model, prompt_hash, outcome, cost_usd)
                           values ('earlier', %s, 'h', 'written', %s)""", (S.MODEL, 10.0 - worst / 2))
        self.conn.commit()
        stats, api, b = self.write(max_usd=1.0, ceiling=10.0)
        self.assertEqual(api.requests, [])
        self.assertIn("lifetime ceiling", stats.stop)
        self.assertEqual(b.refused_by, "ceiling")

    def test_a_call_over_its_worst_case_trips(self):
        huge = dict(F.USAGE, output_tokens=50_000_000)
        with self.assertRaises(EV.Tripped):
            self.write(lambda p: (200, F.message(json.dumps({"summary": "Fine."}), usage=huge)))
        self.assertTrue(any(o == "written" for _, o, _ in self.ledger()))    # its cost is on record

    def test_recorded_spend_over_the_ceiling_trips(self):
        b = self.budget(1.0, 10.0)
        with self.conn.cursor() as cur:
            cur.execute("""insert into summary_calls (resolved_key, model, prompt_hash, outcome, cost_usd)
                           values ('elsewhere', %s, 'h', 'written', 11)""", (S.MODEL,))
        self.conn.commit()
        todo = S.due(list(self.places().values()), S.MODEL, PH, 5)
        with F.FakeAnthropic(lambda p: ok()) as api, self.assertRaises(EV.Tripped):
            S.run(self.conn, AV.client("k", api.base_url), b, todo, workers=1, attempts=1, log=QUIET)

    def test_a_timeout_is_charged_its_worst_case_and_counts_an_attempt(self):
        class TimesOut:
            class messages:
                @staticmethod
                def create(**p):
                    raise anthropic.APITimeoutError(request=httpx2.Request("POST", "http://x/v1/messages"))
        todo = S.due(list(self.places().values()), S.MODEL, PH, 5)[:1]
        b = self.budget()
        stats = S.run(self.conn, TimesOut(), b, todo, workers=1, attempts=2, sleep=lambda s: None, log=QUIET)
        self.assertIsNone(stats.stop)                                    # one place; the pass goes on
        self.assertEqual(stats.failed, 1)
        rows = self.ledger()
        self.assertEqual([o for _, o, _ in rows], ["unseen", "unseen"])      # both attempts
        self.assertAlmostEqual(sum(float(c) for _, _, c in rows), b.spent, places=6)
        [(summary, attempts, err)] = self.q("select summary, attempts, error from place_summaries")
        self.assertEqual((summary, attempts), (None, 1))
        self.assertIn("TransientAPIError", err)

    def test_an_outage_stops_after_a_few_places_not_all_of_them(self):
        class Down:
            calls = 0

            class messages:
                @staticmethod
                def create(**p):
                    Down.calls += 1
                    raise anthropic.APIConnectionError(request=httpx2.Request("POST", "http://x/v1/messages"))
        for k in ("delta", "eps"):
            self.many(k, 10)
        self.build()
        todo = S.due(list(self.places().values()), S.MODEL, PH, 5)
        stats = S.run(self.conn, Down(), self.budget(), todo, workers=1, attempts=1, sleep=lambda s: None,
                      log=QUIET)
        self.assertIn("in a row", stats.stop)
        self.assertEqual(Down.calls, S.API_FAILURES_IN_A_ROW)

    def test_no_call_starts_after_the_deadline(self):
        stats, api, _ = self.write(deadline=0.0)                       # long past
        self.assertEqual(api.requests, [])
        self.assertIn("out of time", stats.stop)

    def test_the_deadline_is_checked_before_each_call_not_just_each_page(self):
        # One worker, a page of two: the first call outlasts the deadline, so
        # the second, already queued on the same page, never starts.
        def slow(p):
            time.sleep(0.6)
            return ok()
        stats, api, _ = self.write(slow, workers=1, deadline=time.monotonic() + 0.3)
        self.assertEqual((len(api.requests), stats.written), (1, 1))
        self.assertIn("out of time", stats.stop)


class Review(SummaryCase):
    """The quality check's file and the dry run, which the orchestrator runs by hand."""

    def setUp(self):
        super().setUp()
        self.many("alpha", 12, body="ALPHA TEXT")
        self.many("beta", 10, level=-1, body="BETA TEXT")
        self.build()
        fd, self.path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        self.addCleanup(os.remove, self.path)

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def test_each_summary_beside_exactly_what_it_was_given(self):
        stats, api, _ = self.write(lambda p: ok("Commenters like alpha.") if "<place>alpha" in
                                   p["messages"][0]["content"] else (200, F.message("not json")))
        results = [(req, "asked for", s, c, e) for req, s, c, e in stats.results]
        S.write_review(self.path, results, ["header line"], log=QUIET)
        text = self.read()
        self.assertIn("> Commenters like alpha.", text)
        self.assertIn("**No summary**: invalid_json", text)
        sent = {r["messages"][0]["content"] for r in api.requests}
        for user in sent:
            self.assertIn(user, text)                                    # byte for byte what was sent

    def test_review_only_reads_stored_summaries_and_calls_nothing(self):
        self.write()
        args = mock.Mock(sample=None, keys=["alpha", "beta", "nope"], review=self.path)
        S.review_only(self.conn, args, S.Settings(), log=QUIET)
        text = self.read()
        self.assertEqual(text.count("> Commenters say it is good"), 2)
        self.assertIn("ALPHA TEXT", text)
        self.assertIn("BETA TEXT", text)

    def test_dry_run_reads_only(self):
        lines = []
        self.conn.set_session(readonly=True)
        todo, inputs = S.dry_run(self.conn, S.Settings(), log=lines.append)
        self.assertEqual({p.key for p, _ in todo}, {"alpha", "beta"})
        self.assertIn("2 places qualify", lines[0])
        self.assertTrue(any("estimated cost $" in l for l in lines))
        lines.clear()
        S.dry_run(self.conn, S.Settings(), keys=["beta"], print_input=True, log=lines.append)
        self.assertTrue(any("BETA TEXT" in l and "<place>beta</place>" in l for l in lines))


class PollerStep(SummaryCase):
    def test_end_to_end_and_the_lock(self):
        self.many("alpha", 10)
        self.many("beta", 10)
        self.build()
        with F.FakeAnthropic(lambda p: ok()) as api, mock.patch.dict(os.environ, {S.KEY_VAR: "k"}):
            cl = AV.client("k", api.base_url)
            other = pgtest.connect()
            self.addCleanup(other.close)
            self.assertTrue(S.try_lock(other))                           # a manual run holds it
            lines = []
            self.assertIsNone(S.poll_once(self.conn, 10, connect=pgtest.connect, cl=cl, log=lines.append))
            self.assertIn("holds the lock", lines[-1])
            S.unlock(other)
            stats = S.poll_once(self.conn, 1, connect=pgtest.connect, cl=cl, log=QUIET, sleep=lambda s: None)
            self.assertEqual(stats.written, 1)                           # the limit
            stats = S.poll_once(self.conn, 10, connect=pgtest.connect, cl=cl, log=QUIET)
            self.assertEqual(stats.written, 1)
            self.assertEqual(S.poll_once(self.conn, 10, connect=pgtest.connect, cl=cl, log=QUIET).written, 0)
        self.assertEqual(len(api.requests), 2)
        self.assertTrue(S.try_lock(self.conn))                           # released
        S.unlock(self.conn)

    def test_the_gate_skips_a_pass_with_nothing_new(self):
        self.many("alpha", 10)
        self.build()
        gate = S.Gate()
        reads = []
        real = S.qualifying

        def counted(*a, **k):
            reads.append(1)
            return real(*a, **k)
        with F.FakeAnthropic(lambda p: ok()) as api, mock.patch.object(S, "qualifying", side_effect=counted):
            cl = AV.client("k", api.base_url)

            def poll():
                return S.poll_once(self.conn, 10, settings=S.Settings(), connect=pgtest.connect, cl=cl,
                                   log=QUIET, gate=gate)
            self.assertEqual(poll().written, 1)
            self.assertEqual(len(reads), 1)
            self.assertTrue(poll().skipped)                              # nothing new: no year-wide read
            self.assertEqual(len(reads), 1)
            for i in range(5):                                           # new mentions open it again
                self.mention("alpha", 0)
            self.build()
            self.assertEqual(poll().written, 1)
            self.assertEqual(len(reads), 2)
            self.assertTrue(poll().skipped)
            with self.conn.cursor() as cur:                              # so does a change from elsewhere
                cur.execute("update place_summaries set attempts = 0, updated_at = now()")
            self.conn.commit()
            self.assertFalse(poll().skipped)
            self.assertEqual(len(reads), 3)
            # and other settings are another pass
            self.assertFalse(S.poll_once(self.conn, 10, settings=S.Settings(x=6), connect=pgtest.connect, cl=cl,
                                         log=QUIET, gate=gate).skipped)
        self.assertEqual(len(api.requests), 2)

    def test_the_gate_stays_open_while_work_is_left(self):
        for k in ("alpha", "beta"):
            self.many(k, 10)
        self.build()
        gate = S.Gate()
        with F.FakeAnthropic(lambda p: ok()) as api:
            cl = AV.client("k", api.base_url)
            run = lambda: S.poll_once(self.conn, 1, settings=S.Settings(), connect=pgtest.connect,  # noqa: E731
                                      cl=cl, log=QUIET, gate=gate)
            self.assertEqual(run().written, 1)                           # the limit left one behind
            self.assertEqual(run().written, 1)
            self.assertTrue(run().skipped)

    def test_missing_tables_skip(self):
        with self.conn.cursor() as cur:
            cur.execute("drop table place_summaries")
        self.conn.commit()
        lines = []
        with mock.patch.dict(os.environ, {S.KEY_VAR: "k"}):
            self.assertIsNone(S.poll_once(self.conn, 10, log=lines.append))
        self.assertIn("tables missing", lines[0])


if __name__ == "__main__":
    unittest.main()
