"""Place summaries against a real, throwaway Postgres, with tests/fake_anthropic.py
as the API, so nothing is billed.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55439/nyceatstest python -m pytest tests

Covers who qualifies (n, the window, the v6 mentions live_mentions counts,
deleted comments, excluded names, aliases, one comment counted once), what
is sent, the write and the comments it has seen (late extraction new,
re-extraction not, counted by comment), the x-new rewrite and the share,
places with nothing to send, failure parking, whose an API failure is (the
place's, the account's or the pass's), the per-pass cap, the lifetime
ceiling, the tripwire, the deadline, a timeout's charge, the ledger
surviving a failed store or a failed worker, the legacy read mode, the
every-so-many-hours gate, the schema upgrade, the poller's step end to end,
and other cities: a place of the same name in two subreddits is two places
with a summary each. Skipped without TEST_DATABASE_URL.
"""

import datetime as dt
import json
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

import anthropic
import httpx2
import psycopg2.errors

import anthropic_v6 as AV
import db
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
                deleted=False, author=None, prompt_hash=TH, cid=None, raw=None, body=None, state_hash=None,
                sub=None):
        """One mention, on a new comment unless cid names one. state_hash is
        the hash on the comment's cursor row, the mention's own unless given
        (a different one makes the mention stale, so live_mentions drops it).
        sub puts the comment in another city's subreddit, in a thread of its own."""
        self.n += 1
        cid = cid or f"t1_s{self.n}"
        sub = sub or subreddits.HOME
        tid = "t3_s" if sub == subreddits.HOME else f"t3_{sub.lower()}"
        with self.conn.cursor() as cur:
            cur.execute("""insert into threads (id, subreddit, title, created_utc)
                           values (%s, %s, 'Where to eat?', now() - interval '900 days')
                           on conflict (id) do nothing""", (tid, sub))
            cur.execute("""insert into comments (id, subreddit, thread_id, parent_id, author, body, permalink,
                                                 created_utc, score, score_settled, was_deleted_later)
                           values (%s, %s, %s, %s, %s, %s, '/r/x', now() - make_interval(days => %s),
                                   1, true, %s)
                           on conflict (id) do nothing""",
                        (cid, sub, tid, tid, author or f"u{self.n}", body or f"about {key} #{self.n}", days,
                         deleted))
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

    def test_write_and_what_it_has_seen(self):
        stats, api, b = self.write()
        self.assertEqual(stats.written, 1)
        summary, count, last, attempts, err, sent = self.row("alpha")[0]
        self.assertEqual((count, attempts, err, sent), (10, 0, None, 10))
        self.assertTrue(summary.startswith("Commenters say"))
        self.assertEqual(last, self.q("select max(created_utc) from comments")[0][0])
        seen = self.q("select seen_comment_ids from place_summaries")[0][0]
        self.assertEqual(sorted(seen), sorted(r[0] for r in self.q("select id from comments")))
        [(key, outcome, cost)] = self.ledger()
        self.assertEqual((key, outcome), ("alpha", "written"))
        self.assertAlmostEqual(float(cost), b.spent, places=8)
        sent_req = api.requests[0]
        self.assertEqual(sent_req["model"], "claude-haiku-5-5")
        self.assertIn("<place>alpha</place>", sent_req["messages"][0]["content"])

    def test_the_seen_set_holds_every_qualifying_comment_not_only_the_ones_sent(self):
        self.many("alpha", 3, start=30, opinion="none", level=None)     # counted, never sent
        self.build()
        self.write()
        seen = self.q("select seen_comment_ids, input_comments from place_summaries")[0]
        self.assertEqual((len(seen[0]), seen[1]), (13, 10))
        self.assertEqual(self.places()["alpha"].fresh, 0)

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

    def test_a_comment_extracted_late_is_new(self):
        # Comments written months ago and only extracted now (the backlog, a
        # late comment on an old thread) were not there to be seen.
        self.write()
        for i in range(5):
            self.mention("alpha", 200 + i)
        self.build()
        self.assertEqual((self.places()["alpha"].fresh, self.reason("alpha")), (5, "fresh"))

    def test_the_same_comments_extracted_again_are_not_new(self):
        # A new prompt hash (or a failed chunk that later succeeds) puts new
        # mention rows on comments the summary has already seen.
        self.write()
        with self.conn.cursor() as cur:
            cur.execute("select id from comments")
            ids = [r[0] for r in cur.fetchall()]
            cur.execute("update extraction_state set prompt_hash = 'newhash'")
            for cid in ids:
                cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key, model_version,
                                                     prompt_hash, schema_version, kind, opinion, overall_level,
                                                     timeframe)
                               values (%s, 'alpha', 'alpha', 'm', 'newhash', 6, 'restaurant', 'stated', 1,
                                       'current')""", (cid,))
        self.conn.commit()
        self.build()
        self.assertEqual(self.q("select count(*) from live_mentions where prompt_hash = 'newhash'")[0][0], 10)
        p = self.places()["alpha"]
        self.assertEqual((p.n, p.fresh), (10, 0))
        self.assertIsNone(self.reason("alpha"))

    def test_new_is_counted_by_comment_not_by_mention(self):
        self.write()
        cid = self.mention("alpha", 0)
        self.mention("alpha x", 0, cid=cid)                             # a second spelling, same comment
        with self.conn.cursor() as cur:
            cur.execute("insert into alias_overrides (entity_key, resolved_key, note) values ('alpha x', 'alpha', 't')")
        self.conn.commit()
        for i in range(3):
            self.mention("alpha", 0)
        self.build()
        self.assertEqual(self.places()["alpha"].fresh, 4)
        self.assertIsNone(self.reason("alpha"))

    def test_share_raises_the_bar(self):
        self.write()
        for i in range(5):
            self.mention("alpha", 0)
        self.build()
        self.assertEqual(self.reason("alpha", share=0.1), "fresh")       # ceil(0.1 x 15) = 2 < 5
        self.assertIsNone(self.reason("alpha", share=0.5))               # ceil(0.5 x 15) = 8

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

    def test_a_request_too_long_for_one_place_is_that_place_s(self):
        self.many("beta", 10)
        self.build()

        def answer(p):
            if "<place>alpha</place>" in p["messages"][0]["content"]:
                return F.error(400, "invalid_request_error", "prompt is too long: 1200000 tokens > 1000000 maximum")
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

    def test_no_credit_stops_the_pass_and_marks_nothing(self):
        self.many("beta", 10)
        self.build()
        for status, kind, msg in ((400, "invalid_request_error",
                                   "Your credit balance is too low to access the Anthropic API."),
                                  (401, "authentication_error", "invalid x-api-key")):
            stats, api, b = self.write(lambda p: F.error(status, kind, msg), workers=1)
            self.assertIn("FatalAPIError", stats.stop)
            self.assertEqual(len(api.requests), 1)
            self.assertEqual(self.q("select count(*) from place_summaries")[0][0], 0)
            self.assertEqual(self.ledger(), [])
            self.assertEqual(b.spent, 0.0)

    def test_other_failures_are_charged_once_each_and_stop_the_run_after_a_few(self):
        for k in ("beta", "gamma", "delta"):
            self.many(k, 10)
        self.build()
        for answer in (lambda p: F.error(400, "invalid_request_error", "output_config.effort: bad"),
                       lambda p: F.error(500, "api_error", "internal")):
            with self.conn.cursor() as cur:
                cur.execute("delete from place_summaries")
            self.conn.commit()
            stats, api, _ = self.write(answer, workers=1)
            self.assertIn(f"{S.API_FAILURES_IN_A_ROW} calls in a row", stats.stop)
            self.assertEqual(stats.failed, S.API_FAILURES_IN_A_ROW)        # each failure counted once
            self.assertEqual(self.q("select count(*), sum(attempts) from place_summaries")[0],
                             (S.API_FAILURES_IN_A_ROW, S.API_FAILURES_IN_A_ROW))
            self.assertEqual(len({r["messages"][0]["content"] for r in api.requests}), S.API_FAILURES_IN_A_ROW)

    def test_a_comment_landing_while_a_page_is_read_is_never_marked_seen_unsent(self):
        # The seen ids are read before the inputs, so a comment committed in
        # between is sent (and seen); none is marked seen without being sent.
        real = S.qualifying_ids
        landed = []

        def ids_then_land(conn, keys, since, sub=None):
            out = real(conn, keys, since, sub)
            if not landed:
                landed.append(self.mention("alpha", 0, body="LANDED MID-READ"))
            return out
        with mock.patch.object(S, "qualifying_ids", side_effect=ids_then_land):
            _, api, _ = self.write()
        self.assertIn("LANDED MID-READ", api.requests[0]["messages"][0]["content"])   # it was sent
        seen = self.q("select seen_comment_ids from place_summaries")[0][0]
        self.assertNotIn(landed[0], seen)                               # and reads as new next time
        self.build()
        self.assertEqual(self.places()["alpha"].fresh, 1)

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

    def test_a_worker_that_raises_still_has_its_charges_recorded(self):
        # The only attempt times out (charged its worst case), then the
        # worker fails on something else before it returns: the charge it
        # already made must still reach the ledger.
        class TimesOut:
            class messages:
                @staticmethod
                def create(**p):
                    raise anthropic.APITimeoutError(request=httpx2.Request("POST", "http://x/v1/messages"))
        b = self.budget()
        todo = S.due(list(self.places().values()), S.MODEL, PH, 5)
        with mock.patch.object(S.Streak, "failed", side_effect=RuntimeError("a bug after the charge")), \
                self.assertRaises(RuntimeError):
            S.run(self.conn, TimesOut(), b, todo, workers=1, attempts=1, sleep=lambda s: None, log=QUIET,
                  connect=pgtest.connect)
        [(key, outcome, cost)] = self.ledger()
        self.assertEqual((key, outcome), ("alpha", "unseen"))
        self.assertAlmostEqual(float(cost), b.spent, places=6)
        self.assertGreater(b.spent, 0)


class Mixed:
    """A client whose calls for the named places fail with `error`, and the
    rest are answered. Dicts stand in for the SDK's messages."""

    def __init__(self, failing, error):
        self.calls = []
        outer = self

        class Messages:
            @staticmethod
            def create(**p):
                user = p["messages"][0]["content"]
                outer.calls.append(user)
                if any(f"<place>{k}</place>" in user for k in failing):
                    raise error()
                return F.message(json.dumps({"summary": "Commenters say it is fine."}))
        self.messages = Messages


def timeout():
    return anthropic.APITimeoutError(request=httpx2.Request("POST", "http://x/v1/messages"))


def server_error():
    return anthropic.InternalServerError("boom", response=httpx2.Response(
        500, request=httpx2.Request("POST", "http://x/v1/messages")), body=None)


class Failures(SummaryCase):
    """Every failure but an account-wide refusal charges its place one attempt
    when it happens; three park it for SUMMARY_PARK_HOURS, then it gets one
    more try."""

    def setUp(self):
        super().setUp()
        self.many("alpha", 12)                          # busiest: always first
        for k in ("beta", "gamma"):
            self.many(k, 10)
        self.build()

    def run_once(self, cl, keys=None, now=None, park_hours=None):
        todo = S.due(list(self.places().values()), S.MODEL, PH, 5, force=keys is not None, now=now,
                     park_hours=park_hours)
        if keys is not None:
            todo = [(p, r) for p, r in todo if p.key in keys]
        return S.run(self.conn, cl, self.budget(), todo, workers=1, attempts=2, sleep=lambda s: None, log=QUIET)

    def test_a_place_that_times_out_is_charged_at_once_parked_and_comes_back(self):
        cl = Mixed(["alpha"], timeout)
        stats = self.run_once(cl)
        self.assertEqual((stats.written, stats.failed), (2, 1))
        self.assertEqual(self.row("alpha")[0][3], 1)
        self.assertEqual(sum(1 for u in cl.calls if "<place>alpha</place>" in u), 1)   # not sent twice
        self.assertEqual([o for k, o, _ in self.ledger() if k == "alpha"], ["unseen"])  # charged once
        for attempt in (2, 3):
            stats = self.run_once(cl, keys=["alpha"])
            self.assertEqual(self.row("alpha")[0][3], attempt)
        self.assertEqual(stats.parked, 1)
        now = self.q("select now()")[0][0]
        self.assertEqual(S.due_reason(self.places()["alpha"], S.MODEL, PH, 5, now=now, park_hours=168), "parked")
        with self.conn.cursor() as cur:
            cur.execute("update place_summaries set failed_at = now() - interval '8 days' where resolved_key = 'alpha'")
        self.conn.commit()
        self.assertEqual(S.due_reason(self.places()["alpha"], S.MODEL, PH, 5, now=now, park_hours=168), "new")
        # one more try; a failure parks it for another week
        self.run_once(cl, keys=["alpha"], now=now, park_hours=168)
        self.assertEqual(self.row("alpha")[0][3], 4)
        now = self.q("select now()")[0][0]
        self.assertEqual(S.due_reason(self.places()["alpha"], S.MODEL, PH, 5, now=now, park_hours=168), "parked")

    def test_a_5xx_that_outlasts_its_retries_is_charged_the_same_way(self):
        stats = self.run_once(Mixed(["alpha"], server_error))
        self.assertEqual((stats.written, stats.failed), (2, 1))
        self.assertTrue(self.row("alpha")[0][4].startswith("api: TransientAPIError"))
        self.assertEqual([o for k, o, _ in self.ledger() if k == "alpha"], [])     # a 5xx is not billed

    def test_an_outage_charges_the_places_it_reached_and_stops(self):
        for k in ("delta", "eps"):
            self.many(k, 10)
        self.build()
        cl = Mixed(["alpha", "beta", "gamma", "delta", "eps"], timeout)
        stats = self.run_once(cl)
        self.assertIn(f"{S.API_FAILURES_IN_A_ROW} calls in a row", stats.stop)
        self.assertEqual((stats.written, stats.failed, len(cl.calls)), (0, 3, 3))
        self.assertEqual(self.q("select count(*) from place_summaries where attempts = 1")[0][0], 3)

    def test_a_place_s_own_refusals_do_not_stop_the_run(self):
        for k in ("delta", "eps"):
            self.many(k, 10)
        self.build()
        stats, api, _ = self.write(lambda p: F.error(400, "invalid_request_error",
                                                     "prompt is too long: 1200000 tokens > 1000000 maximum"),
                                   workers=1)
        self.assertIsNone(stats.stop)                                    # five in a row, no streak
        self.assertEqual((stats.failed, len(api.requests)), (5, 5))
        self.assertEqual(self.q("select count(*) from place_summaries where attempts = 1")[0][0], 5)

    def test_a_400_that_mentions_a_balance_in_passing_is_the_place_s(self):
        # Not the account's "credit balance": charged to its place, the run
        # goes on, and the place cannot stop every run from the queue's head.
        def answer(p):
            if "<place>alpha</place>" in p["messages"][0]["content"]:
                return F.error(400, "invalid_request_error", "system: the balance of this request is invalid")
            return ok()
        stats, api, _ = self.write(answer, workers=1)
        self.assertIsNone(stats.stop)
        self.assertEqual((stats.written, stats.failed, len(api.requests)), (2, 1, 3))
        self.assertEqual(self.row("alpha")[0][3], 1)
        # and the real no-credit refusal still stops the run, charging nobody
        with self.conn.cursor() as cur:
            cur.execute("delete from place_summaries")
        self.conn.commit()
        stats, api, _ = self.write(lambda p: F.error(400, "invalid_request_error",
                                                     "Your credit balance is too low to access the Anthropic API."),
                                   workers=1)
        self.assertIn("FatalAPIError", stats.stop)
        self.assertEqual((stats.failed, len(api.requests)), (0, 1))
        self.assertEqual(self.q("select count(*) from place_summaries")[0][0], 0)

    def test_an_account_refusal_outranks_a_streak_in_the_same_page(self):
        # Four calls at once: three time out (a streak) and one is refused
        # for a bad key. The run must report the account, whichever came
        # back first, and the refused place is not charged.
        self.many("delta", 10)
        self.build()
        lock, arrived = threading.Lock(), []
        barrier = threading.Barrier(4, timeout=10)

        class Client:
            class messages:
                @staticmethod
                def create(**p):
                    with lock:
                        arrived.append(p["messages"][0]["content"])
                        n = len(arrived)
                    barrier.wait()
                    if n == 4:
                        raise anthropic.AuthenticationError("bad key", response=httpx2.Response(
                            401, request=httpx2.Request("POST", "http://x")), body=None)
                    raise timeout()
        todo = S.due(list(self.places().values()), S.MODEL, PH, 5)
        stats = S.run(self.conn, Client(), self.budget(), todo, workers=4, attempts=1, log=QUIET)
        self.assertIn("FatalAPIError", stats.stop)
        self.assertIn("401", stats.stop)
        self.assertEqual(stats.failed, 3)                                # the timeouts; the 401 charges nobody
        self.assertEqual(self.q("select count(*) from place_summaries")[0][0], 3)


class Empty(SummaryCase):
    def test_nothing_to_send_is_recorded_and_waits_for_new_comments(self):
        self.many("quiet", 10, opinion="none", level=None)              # qualifies, nothing to send
        self.many("quiet2", 11, opinion="none", level=None)
        self.many("alpha", 10)
        self.many("beta", 10)
        self.build()
        # Busiest first would put the empty ones at the head; they must not
        # use up the limit of one.
        with self.conn.cursor() as cur:
            for i in range(5):
                cur.execute("""insert into comments (id, thread_id, parent_id, author, body, permalink,
                                                     created_utc, score, score_settled)
                               values (%s, 't3_s', 't3_s', 'q', 'x', '/r/x', now() - interval '3 days', 1, true)""",
                            (f"t1_q{i}",))
                cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash, extracted_at)
                               values (%s, 'v6', 'comment', %s, now())""", (f"t1_q{i}", TH))
                cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key, model_version,
                                                     prompt_hash, schema_version, kind, opinion)
                               values (%s, 'quiet', 'quiet', 'm', %s, 6, 'restaurant', 'none')""", (f"t1_q{i}", TH))
        self.conn.commit()
        self.build()
        todo = S.due(list(self.places().values()), S.MODEL, PH, 5)
        self.assertEqual(todo[0][0].key, "quiet")
        b = self.budget()
        with F.FakeAnthropic(lambda p: ok()) as api:
            stats = S.run(self.conn, AV.client("k", api.base_url), b, todo, workers=1, attempts=1, log=QUIET,
                          limit=1)
        self.assertEqual((stats.written, stats.empty, len(api.requests)), (1, 2, 1))
        rows = dict(self.q("select resolved_key, summary is null and written_at is not null "
                           "and cardinality(seen_comment_ids) >= 10 from place_summaries"))
        self.assertTrue(rows["quiet"] and rows["quiet2"])
        self.assertIsNone(self.reason("quiet"))                          # not due again
        for i in range(5):
            self.mention("quiet", 0)
        self.build()
        self.assertEqual(self.reason("quiet"), "fresh")                 # new discussion brings it back


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

    def test_a_lone_timeout_is_charged_its_worst_case_once_and_an_attempt(self):
        class TimesOut:
            class messages:
                @staticmethod
                def create(**p):
                    raise anthropic.APITimeoutError(request=httpx2.Request("POST", "http://x/v1/messages"))
        todo = S.due(list(self.places().values()), S.MODEL, PH, 5)[:1]
        b = self.budget()
        stats = S.run(self.conn, TimesOut(), b, todo, workers=1, attempts=2, sleep=lambda s: None, log=QUIET)
        self.assertIsNone(stats.stop)                                    # one call; the pass goes on
        self.assertEqual(stats.failed, 1)
        rows = self.ledger()
        self.assertEqual([o for _, o, _ in rows], ["unseen"])            # not sent again this run
        self.assertAlmostEqual(sum(float(c) for _, _, c in rows), b.spent, places=6)
        [(summary, attempts, err)] = self.q("select summary, attempts, error from place_summaries")
        self.assertEqual((summary, attempts), (None, 1))
        self.assertIn("TimedOut", err)

    def test_an_outage_stops_after_a_few_calls(self):
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
        # the places it reached are charged; they come back after SUMMARY_PARK_HOURS at worst
        self.assertEqual(self.q("select count(*) from place_summaries where attempts = 1")[0][0],
                         S.API_FAILURES_IN_A_ROW)

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

    def test_dry_run_limit_counts_only_places_with_something_to_send(self):
        # quiet heads the queue with nothing to send; --limit 1 must still
        # price one real call, as run() would make.
        self.conn.set_session(readonly=False)
        self.many("quiet", 15, opinion="none", level=None)
        self.build()
        self.conn.set_session(readonly=True)
        lines = []
        todo, _ = S.dry_run(self.conn, S.Settings(), limit=1, print_input=True, log=lines.append)
        self.assertEqual([p.key for p, _ in todo], ["quiet", "alpha"])
        self.assertIn("due now: 2, of which 1 have nothing to send", lines)
        self.assertTrue(any("estimated cost $" in l for l in lines))
        self.assertTrue(any("ALPHA TEXT" in l for l in lines))
        self.assertFalse(any("BETA TEXT" in l for l in lines))

    def test_dry_run_limit_reads_only_as_far_as_it_needs(self):
        self.many("quiet", 15, opinion="none", level=None)
        self.build()
        self.conn.set_session(readonly=True)
        read = []
        real = S.read_inputs

        def counted(conn, keys, *a, **k):
            read.extend(keys)
            return real(conn, keys, *a, **k)
        with mock.patch.object(S, "DRY_PAGE", 1), mock.patch.object(S, "read_inputs", side_effect=counted):
            todo, _ = S.dry_run(self.conn, S.Settings(), limit=1, log=QUIET)
        self.assertEqual(read, ["quiet", "alpha"])                       # beta never read
        # and the real run takes the same places: quiet recorded, alpha sent
        self.conn.set_session(readonly=False)
        stats, api, _ = self.write(workers=4, limit=1)
        self.assertEqual((stats.empty, stats.written, len(api.requests)), (1, 1, 1))
        self.assertEqual(sorted(r[0] for r in self.q("select resolved_key from place_summaries")),
                         sorted(p.key for p, _ in todo))


class PollerStep(SummaryCase):
    def poll(self, cl, limit=10, settings=None, log=QUIET):
        return S.poll_once(self.conn, limit, settings=settings or S.Settings(every_hours=0), connect=pgtest.connect,
                           cl=cl, log=log, sleep=lambda s: None)

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
            self.assertIsNone(self.poll(cl, log=lines.append))
            self.assertIn("holds the lock", lines[-1])
            S.unlock(other)
            self.assertEqual(self.poll(cl, limit=1).written, 1)          # the limit
            self.assertEqual(self.poll(cl).written, 1)
            self.assertEqual(self.poll(cl).written, 0)
        self.assertEqual(len(api.requests), 2)
        self.assertTrue(S.try_lock(self.conn))                           # released
        S.unlock(self.conn)

    def test_at_most_once_every_so_many_hours_across_restarts(self):
        self.many("alpha", 10)
        self.build()
        six = S.Settings(every_hours=6)
        with F.FakeAnthropic(lambda p: ok()) as api:
            cl = AV.client("k", api.base_url)
            self.assertEqual(self.poll(cl, settings=six).written, 1)
            ran = self.q("select last_pass_at from summary_state")[0][0]
            self.assertIsNotNone(ran)
            for i in range(5):                                           # due again, but not yet time
                self.mention("alpha", 0)
            self.build()
            self.assertTrue(self.poll(cl, settings=six).skipped)
            self.assertTrue(self.poll(cl, settings=six).skipped)         # a new process reads the same row
            with self.conn.cursor() as cur:
                cur.execute("update summary_state set last_pass_at = now() - interval '7 hours'")
            self.conn.commit()
            self.assertEqual(self.poll(cl, settings=six).written, 1)
        self.assertEqual(len(api.requests), 2)

    def test_retry_errors_is_seen_at_the_next_run(self):
        self.many("alpha", 10)
        self.build()
        with self.conn.cursor() as cur:
            cur.execute("insert into place_summaries (resolved_key, attempts, error) values ('alpha', 3, 'x')")
        self.conn.commit()
        with F.FakeAnthropic(lambda p: ok()) as api:
            cl = AV.client("k", api.base_url)
            self.assertEqual(self.poll(cl).written, 0)                   # parked
            S.retry_errors(self.conn)
            self.assertEqual(self.poll(cl).written, 1)

    def test_missing_tables_skip(self):
        with self.conn.cursor() as cur:
            cur.execute("drop table place_summaries")
        self.conn.commit()
        lines = []
        with mock.patch.dict(os.environ, {S.KEY_VAR: "k"}):
            self.assertIsNone(S.poll_once(self.conn, 10, log=lines.append))
        self.assertIn("tables missing", lines[0])


LA, CHI = "FoodLosAngeles", "chicagofood"


class Cities(SummaryCase):
    """A place is (subreddit, name): the same design in every city, each on
    its own comments, with nothing of one city's reaching another's."""

    def places_in(self, sub, n=10):
        return {p.key: p for p in S.qualifying(self.conn, n, sub=sub)}

    def run_city(self, sub, answer=lambda p: ok(), **kw):
        settings = S.Settings()
        todo = S.due(list(self.places_in(sub).values()), S.MODEL, settings.hash_for(sub), 5)
        b = self.budget()
        with F.FakeAnthropic(answer) as api:
            stats = S.run(self.conn, AV.client("k", api.base_url), b, todo, settings, workers=2, attempts=2,
                          sleep=lambda s: None, log=QUIET, connect=pgtest.connect, **kw)
        return stats, api

    def rows(self):
        return sorted(self.q("""select subreddit, resolved_key, summary, prompt_hash, mention_count,
                                       cardinality(seen_comment_ids)
                                from place_summaries"""))

    def test_the_same_name_in_two_cities_is_two_places(self):
        self.many("alpha", 12)                                           # New York's alpha
        la = self.many("alpha", 10, sub=LA, body="the LA alpha is great")
        self.many("beta", 9, sub=LA)                                     # 9 in LA and
        self.many("beta", 9)                                             # 9 in New York: neither has 10
        self.build()
        self.assertEqual({k: p.n for k, p in self.places().items()}, {"alpha": 12})
        self.assertEqual({k: (p.n, p.sub) for k, p in self.places_in(LA).items()}, {"alpha": (10, LA)})
        self.assertEqual(self.places_in(CHI), {})                        # a city nobody extracted
        _, since = S._since(self.conn)
        sent = S.read_inputs(self.conn, ["alpha"], since, sub=LA)["alpha"].comments
        self.assertEqual(sorted(c.id for c in sent), sorted(la))         # LA's comments and no others
        self.assertEqual(len(S.read_inputs(self.conn, ["alpha"], since)["alpha"].comments), 12)
        self.assertEqual(S.qualifying_ids(self.conn, ["alpha"], since, LA), {"alpha": sorted(la)})

    def test_each_city_is_written_under_its_own_prompt_and_key(self):
        self.many("alpha", 12)
        self.many("alpha", 10, sub=LA)
        self.build()
        stats, api = self.run_city(LA, lambda p: ok("Angelenos like it."))
        self.assertEqual((stats.written, stats.sent), (1, 1))
        system = api.requests[0]["system"][0]["text"]
        self.assertIn("r/FoodLosAngeles, the Los Angeles food subreddit", system)
        self.assertNotIn("New York", system)
        ph_la = S.Settings().hash_for(LA)
        self.assertEqual(self.rows(), [(LA, "alpha", "Angelenos like it.", ph_la, 10, 10)])
        # New York's alpha is still new, and writing it leaves LA's alone.
        self.assertEqual(self.reason("alpha"), "new")
        stats, api, _ = self.write(lambda p: ok("New Yorkers like it."))
        self.assertEqual(stats.written, 1)
        self.assertEqual(api.requests[0]["system"][0]["text"], S.SYSTEM_PROMPT)
        self.assertEqual(self.rows(), sorted([(LA, "alpha", "Angelenos like it.", ph_la, 10, 10),
                                              (subreddits.HOME, "alpha", "New Yorkers like it.", PH, 12, 12)]))
        self.assertEqual(self.q("select subreddit, resolved_key, prompt_hash, outcome from summary_calls order by id"),
                         [(LA, "alpha", ph_la, "written"), (subreddits.HOME, "alpha", PH, "written")])
        # Each is current under its own hash, and neither under the other's.
        self.assertIsNone(self.reason("alpha"))
        la = self.places_in(LA)["alpha"]
        self.assertIsNone(S.due_reason(la, S.MODEL, ph_la, 5))
        self.assertEqual(S.due_reason(la, S.MODEL, PH, 5), "prompt")

    def test_new_comments_in_one_city_are_not_new_to_the_other(self):
        self.many("alpha", 12)
        self.many("alpha", 10, sub=LA)
        self.build()
        self.run_city(LA)
        self.write()
        self.many("alpha", 5, start=0, sub=LA)
        self.build()
        self.assertEqual(self.places_in(LA)["alpha"].fresh, 5)
        self.assertEqual(self.places()["alpha"].fresh, 0)
        self.assertIsNone(self.reason("alpha"))

    def test_exclusions_and_failures_are_a_city_s_own(self):
        self.many("alpha", 12)
        self.many("alpha", 10, sub=LA)
        self.build()
        with self.conn.cursor() as cur:
            cur.execute("insert into excluded_entities (subreddit, entity_key) values (%s, 'alpha')", (LA,))
        self.conn.commit()
        self.assertEqual(self.places_in(LA), {})                         # excluded in LA,
        self.assertEqual(list(self.places()), ["alpha"])                 # not in New York
        with self.conn.cursor() as cur:
            cur.execute("delete from excluded_entities")
        self.conn.commit()
        stats, _ = self.run_city(LA, lambda p: (200, F.message("not json")))
        self.assertEqual(stats.failed, 1)
        self.assertEqual(self.places_in(LA)["alpha"].attempts, 1)
        self.assertEqual(self.places()["alpha"].attempts, 0)             # New York's was not charged
        with self.conn.cursor() as cur:
            cur.execute("update place_summaries set attempts = 3")
        self.conn.commit()
        self.assertEqual(S.retry_errors(self.conn, [subreddits.HOME]), 0)    # only the cities named
        self.assertEqual(S.retry_errors(self.conn, [LA]), 1)

    def test_the_step_walks_every_city_home_first_under_one_limit_and_cap(self):
        self.many("alpha", 12)
        self.many("beta", 10)
        self.many("alpha", 10, sub=LA)
        self.many("gamma", 10, sub="austinfood")
        self.build()
        settings = S.Settings(every_hours=0)

        def poll(cl, limit=10, settings=settings, log=QUIET, **kw):
            return S.poll_once(self.conn, limit, settings=settings, connect=pgtest.connect, cl=cl, log=log,
                               sleep=lambda s: None, **kw)
        with F.FakeAnthropic(lambda p: ok()) as api:
            cl = AV.client("k", api.base_url)
            self.assertEqual(poll(cl, limit=3).written, 3)               # one limit across the cities
            self.assertEqual([r[:2] for r in self.rows()],
                             sorted([(LA, "alpha"), (subreddits.HOME, "alpha"), (subreddits.HOME, "beta")]))
            lines = []
            self.assertEqual(poll(cl, log=lines.append).written, 1)      # the rest: Austin's
            self.assertIn("(1 due: r/austinfood 1)", lines[-1])
            self.assertEqual(poll(cl).written, 0)
        self.assertEqual(len(api.requests), 4)
        self.assertEqual(sorted(self.q("select subreddit, count(*) from summary_calls group by 1")),
                         sorted([(LA, 1), (subreddits.HOME, 2), ("austinfood", 1)]))
        # One ceiling for every city: what New York spent counts against LA.
        self.many("delta", 10, sub=LA)
        self.build()
        spent = float(self.q("select sum(cost_usd) from summary_calls")[0][0])
        with F.FakeAnthropic(lambda p: ok()) as api:
            stats = poll(AV.client("k", api.base_url), ceiling_usd=spent + 1e-9)
        self.assertEqual((stats.written, len(api.requests)), (0, 0))
        self.assertIn("lifetime ceiling", stats.stop)

    def test_only_the_cities_the_setting_names(self):
        self.many("alpha", 12)
        self.many("alpha", 10, sub=LA)
        self.build()
        with F.FakeAnthropic(lambda p: ok()) as api:
            stats = S.poll_once(self.conn, 10, settings=S.Settings(every_hours=0, subs=(LA,)),
                                connect=pgtest.connect, cl=AV.client("k", api.base_url), log=QUIET)
        self.assertEqual(stats.written, 1)
        self.assertEqual([r[:2] for r in self.rows()], [(LA, "alpha")])

    def test_dry_run_and_status_are_per_city(self):
        self.many("alpha", 12)
        self.many("alpha", 10, sub=LA)
        self.build()
        self.run_city(LA)
        lines = []
        todo, _ = S.dry_run(self.conn, S.Settings(), log=lines.append, sub=LA)
        self.assertEqual(todo, [])                                       # LA's is written
        self.assertTrue(lines[0].startswith("r/FoodLosAngeles: 1 places qualify"))
        todo, _ = S.dry_run(self.conn, S.Settings(), log=QUIET)
        self.assertEqual([(p.key, p.sub) for p, _ in todo], [("alpha", subreddits.HOME)])
        lines = []
        S.status(self.conn, S.Settings(), log=lines.append)
        text = " | ".join(lines)
        self.assertIn(f"r/FoodNYC (prompt {PH}): 0 written", text)
        self.assertIn(f"r/FoodLosAngeles (prompt {S.Settings().hash_for(LA)}): 1 written (1 current)", text)
        self.assertNotIn("r/chicagofood", text)                          # nothing on record: no line


class SchemaUpgrade(SummaryCase):
    def test_reapplying_the_file_gives_a_table_from_before_cities_its_city(self):
        # As production has it: summaries and calls keyed by name alone.
        with self.conn.cursor() as cur:
            cur.execute("drop table place_summaries; drop table summary_calls")
            cur.execute("""create table place_summaries (
                             resolved_key text primary key, summary text, model text, prompt_hash text,
                             mention_count int, last_mention_at timestamptz, seen_comment_ids text[],
                             input_comments int, input_chars int, written_at timestamptz,
                             cost_usd numeric(12, 8), usage jsonb, attempts int not null default 0, error text,
                             failed_at timestamptz, updated_at timestamptz not null default now())""")
            cur.execute("""create table summary_calls (
                             id bigserial primary key, resolved_key text not null, model text not null,
                             prompt_hash text not null, outcome text not null, cost_usd numeric(12, 8) not null,
                             usage jsonb, called_at timestamptz not null default now())""")
            cur.execute("""insert into place_summaries (resolved_key, summary, prompt_hash, seen_comment_ids)
                           values ('alpha', 'old summary', %s, '{t1_a}')""", (PH,))
            cur.execute("""insert into summary_calls (resolved_key, model, prompt_hash, outcome, cost_usd)
                           values ('alpha', 'm', %s, 'written', 0.5)""", (PH,))
        self.conn.commit()
        self.assertFalse(S.tables_exist(self.conn))
        for _ in range(2):                                               # and again: a no-op
            db.init(self.conn, os.path.join(pgtest.ROOT, "summary_schema.sql"))
        self.assertTrue(S.tables_exist(self.conn))
        # What was there is New York's, untouched, and its spend still counts.
        self.assertEqual(self.q("select subreddit, resolved_key, summary, prompt_hash from place_summaries"),
                         [(subreddits.HOME, "alpha", "old summary", PH)])
        self.assertEqual(self.q("select subreddit, cost_usd from summary_calls"), [(subreddits.HOME, 0.5)])
        # The key now takes the same name once per city, and only once.
        with self.conn.cursor() as cur:
            cur.execute("insert into place_summaries (subreddit, resolved_key) values (%s, 'alpha')", (LA,))
            with self.assertRaises(psycopg2.errors.UniqueViolation):
                cur.execute("insert into place_summaries (subreddit, resolved_key) values (%s, 'alpha')", (LA,))
        self.conn.rollback()
        # schema.sql, which every boot applies, carries the same upgrade.
        db.init(self.conn, os.path.join(pgtest.ROOT, "schema.sql"))
        self.assertTrue(S.tables_exist(self.conn))


    def test_reapplying_the_file_upgrades_a_first_version_table(self):
        with self.conn.cursor() as cur:
            cur.execute("drop table place_summaries; drop table summary_state")
            cur.execute("""create table place_summaries (
                             resolved_key text primary key, summary text, model text, prompt_hash text,
                             mention_count int, last_mention_at timestamptz, input_comments int,
                             input_chars int, written_at timestamptz, cost_usd numeric(12, 8), usage jsonb,
                             attempts int not null default 0, error text, failed_at timestamptz,
                             updated_at timestamptz not null default now())""")
            cur.execute("insert into place_summaries (resolved_key, summary) values ('kept', 'old summary')")
        self.conn.commit()
        self.assertFalse(S.tables_exist(self.conn))
        for _ in range(2):                                               # and again: a no-op
            db.init(self.conn, os.path.join(pgtest.ROOT, "summary_schema.sql"))
        self.assertTrue(S.tables_exist(self.conn))
        self.assertEqual(self.q("select summary, seen_comment_ids from place_summaries"), [("old summary", None)])


if __name__ == "__main__":
    unittest.main()
