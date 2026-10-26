"""The spend guards around extract_v6 and the redo of comments cut at 1,500.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55471/budgettest python -m pytest tests

The first classes need no database: Budget against a stand-in ceiling, the
ceiling's flag and variable, and extract_runner's checks and exit codes. The
rest run on the throwaway Postgres of test_extract_v6_db.py (skipped without
one), with tests/fake_anthropic.py as the API, so nothing is ever billed.
"""

import datetime as dt
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock


import anthropic_v6 as AV
import db
import extract_runner as R
import extract_v6 as X
import fake_anthropic as F
import pgtest
import prompt_v6
import test_extract_v6_db as base
import test_extract_v6_thread_db as TT

QUIET = base.QUIET
TH = prompt_v6.PROMPT_HASH_THREAD


class FixedCeiling:
    """A Ceiling with a fixed amount used elsewhere, no database."""

    def __init__(self, limit, used=0.0):
        self.limit, self.used = limit, used

    def room(self, run_spent_held=0.0, run_reserved=0.0):
        return self.limit - self.used - run_spent_held - run_reserved


class BudgetGates(unittest.TestCase):
    def test_the_ceiling_refuses_what_the_run_cap_would_allow(self):
        b = X.Budget(10.0, FixedCeiling(5.0, used=4.0))
        self.assertTrue(b.reserve(0.6))
        self.assertFalse(b.ceiling_hit)
        self.assertFalse(b.reserve(0.6))               # 4 + 0.6 + 0.6 > 5, though the run cap has $9.40
        self.assertTrue(b.ceiling_hit)
        self.assertAlmostEqual(b.remaining(), 0.4)
        self.assertFalse(b.admit(0.5))
        self.assertTrue(b.admit(0.3))

    def test_the_run_cap_alone_is_not_the_ceiling(self):
        b = X.Budget(1.0, FixedCeiling(50.0))
        self.assertFalse(b.reserve(1.5))
        self.assertFalse(b.ceiling_hit)
        self.assertFalse(b.ceiling_binds())
        c = FixedCeiling(1.0)
        b = X.Budget(10.0, c)
        self.assertTrue(b.ceiling_binds())             # read afresh: the ceiling leaves less than the cap
        c.limit = 50.0
        self.assertFalse(b.ceiling_binds())            # and room that comes back is seen

    def test_a_tripped_budget_lets_nothing_through(self):
        b = X.Budget(10.0)
        b.trip("test")
        self.assertFalse(b.reserve(0.01))
        self.assertFalse(b.admit(0.01))
        self.assertFalse(b.hold("x", 0.01))
        self.assertEqual(b.remaining(), 0.0)


class CeilingLimit(unittest.TestCase):
    def test_the_stricter_of_flag_and_variable_wins(self):
        self.assertIsNone(X.ceiling_limit(None, ""))
        self.assertEqual(X.ceiling_limit(25.0, ""), 25.0)
        self.assertEqual(X.ceiling_limit(None, "26.5"), 26.5)
        self.assertEqual(X.ceiling_limit(25.0, "26.5"), 25.0)
        self.assertEqual(X.ceiling_limit(30.0, "26.5"), 26.5)
        with mock.patch.dict(os.environ, {X.CEILING_ENV: "12"}):
            self.assertEqual(X.ceiling_limit(20.0), 12.0)

    def test_a_bad_value_refuses_rather_than_vanishing(self):
        for flag, env in ((None, "twenty"), (0.0, ""), (-1.0, ""), (None, "0"), (None, "nan"), (None, "inf")):
            with self.assertRaises(SystemExit):
                X.ceiling_limit(flag, env)


class Runner(unittest.TestCase):
    ENV = {"EXTRACT_RUN_USD": "20", "EXTRACT_CEILING_USD": "25.48"}

    def test_both_caps_are_required(self):
        for env in ({}, {"EXTRACT_RUN_USD": "20"}, {"EXTRACT_CEILING_USD": "25"},
                    {"EXTRACT_RUN_USD": "", "EXTRACT_CEILING_USD": "25"},
                    {"EXTRACT_RUN_USD": "lots", "EXTRACT_CEILING_USD": "25"},
                    {"EXTRACT_RUN_USD": "0", "EXTRACT_CEILING_USD": "25"},
                    {"EXTRACT_RUN_USD": "30", "EXTRACT_CEILING_USD": "25"}):
            with self.assertRaises(SystemExit):
                R.plan(env)

    def test_the_command(self):
        self.assertEqual(R.plan(self.ENV), (20.0, 25.48))
        self.assertEqual(R.command(self.ENV, 20.0, 25.48),
                         ["--mode", "thread", "--effort", "medium", "--newest-first", "--batch",
                          "--max-usd", "20.0", "--ceiling-usd", "25.48", "--lock-wait", "900"])
        argv = R.command(dict(self.ENV, EXTRACT_REDO_CUT_BEFORE="2026-10-27T12:00", EXTRACT_LOCK_WAIT="60"),
                         20.0, 25.48)
        self.assertEqual(argv[-4:], ["--lock-wait", "60", "--redo-cut-before", "2026-10-27T12:00"])

    def run_with_room(self, room, inflight=0.0):
        """R.main with this much room above recorded spend and this much in
        flight: (status, argv it ran or None, output)."""
        seen = []
        with mock.patch.object(R, "room_left", lambda *a: (room, inflight)), \
                redirect_stdout(io.StringIO()) as out:
            code = R.main(self.ENV, run_extract=lambda argv: seen.append(argv) or 0)
        return code, (seen[0] if seen else None), out.getvalue()

    def test_the_run_cap_is_cut_to_the_room_left(self):
        code, argv, out = self.run_with_room(99.0)
        self.assertEqual((code, argv[argv.index("--max-usd") + 1]), (0, "20.0"))
        self.assertNotIn("is cut to", out)
        # A restart after the first run spent $8.25 of its $20: it resumes with what is left.
        code, argv, out = self.run_with_room(11.75)
        self.assertEqual((code, argv[argv.index("--max-usd") + 1]), (0, "11.75"))
        self.assertIn("EXTRACT_RUN_USD $20.00 is more than the $11.7500 EXTRACT_CEILING_USD $25.48 leaves", out)
        self.assertIn("this run's cap is cut to $11.7500", out)
        self.assertEqual(argv[argv.index("--ceiling-usd") + 1], "25.48")       # the ceiling is untouched

    def test_no_room_left_exits_0_without_running(self):
        for room in (0.0499, 0.0, -1.0):
            code, argv, out = self.run_with_room(room)
            self.assertEqual((code, argv), (0, None))
            self.assertIn("CEILING REACHED", out)
        code, argv, _ = self.run_with_room(0.05)
        self.assertEqual(argv[argv.index("--max-usd") + 1], "0.05")
        # No room, but batches in flight: it runs, to collect them (the ceiling inside sends nothing new).
        code, argv, out = self.run_with_room(0.0, inflight=3.0)
        self.assertEqual(argv[argv.index("--max-usd") + 1], "0.05")
        self.assertNotIn("CEILING REACHED", out)

    def test_exit_codes_for_a_restart_on_failure_policy(self):
        for got, want in ((0, 0), (None, 0), (3, 0), (X.TRIPPED, 0), (2, 2), (130, 130)):
            with mock.patch.object(R, "room_left", lambda *a: (99.0, 0.0)), redirect_stdout(io.StringIO()) as out:
                self.assertEqual(R.main(self.ENV, run_extract=lambda argv, got=got: got), want)
            if got == X.TRIPPED:
                self.assertIn("!!!!!!!! extraction run STOPPED BY A SPEND TRIPWIRE", out.getvalue())

    def test_the_price_check_runs_before_anything(self):
        called = []
        with mock.patch.dict(AV.PRICE_TABLE, {prompt_v6.MODEL: {}}), \
                mock.patch.object(R, "room_left", lambda *a: called.append(a)):
            with self.assertRaises(SystemExit):
                R.main(self.ENV, run_extract=lambda argv: called.append(argv))
        self.assertEqual(called, [])

    def test_the_railway_configs(self):
        import json
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "railway.extract.json")) as f:
            cfg = json.load(f)
        self.assertEqual(cfg["deploy"]["startCommand"], "python extract_runner.py")
        self.assertEqual(cfg["deploy"]["restartPolicyType"], "ON_FAILURE")
        self.assertLessEqual(cfg["deploy"]["restartPolicyMaxRetries"], 3)
        self.assertEqual(cfg["build"]["watchPatterns"], ["/railway.extract.json"])
        # The NYCEats service's own config still starts the poller, and only it does.
        with open(os.path.join(root, "railway.json")) as f:
            self.assertEqual(json.load(f)["deploy"]["startCommand"], "python poller.py")
        self.assertNotIn("poller", json.dumps(cfg))


# ---------------------------------------------------------------- database
def ceiling(limit):
    return X.Ceiling(limit, pgtest.connect)


class Guards(TT.ThreadCase):
    def seed_spend(self, usd, item="t1_old"):
        """Spend recorded by an earlier run: a done comment-mode item that cost usd."""
        with self.conn.cursor() as cur:
            cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash, model, attempts,
                             extracted_at, output, cost_usd)
                           values (%s, 'v6', 'comment', %s, %s, 1, now(), '{"mentions": []}', %s)""",
                        (item, prompt_v6.PROMPT_HASH, prompt_v6.MODEL, usd))
        self.conn.commit()

    def test_unlock_on_a_closed_connection_returns_quietly(self):
        c = pgtest.connect()
        self.assertTrue(X.try_lock(c))
        c.close()
        X.unlock(c)                                       # no InterfaceError
        self.assertTrue(X.try_lock(self.conn))            # a dropped session let go of the lock
        X.unlock(self.conn)

    def test_spend_on_record_counts_items_failed_chunks_lost_batches_and_batches_in_flight(self):
        self.seed_spend(1.25)
        with self.conn.cursor() as cur:
            # ch-y's cost is on its items (seed_spend stands for them); ch-z's
            # batch cost $0.25 more than the chunks it stored (a stray answer).
            cur.execute("""insert into extract_chunks (id, version, thread_id, prompt_hash, effort, members, status,
                             cost_usd, batch_id) values
                             ('ch-x', 'v6', 't3_a', %s, 'medium', '{t1_top}', 'failed', 0.5, null),
                             ('ch-y', 'v6', 't3_a', %s, 'medium', '{t1_top}', 'done', 9, null),
                             ('ch-z', 'v6', 't3_a', %s, 'medium', '{t1_r1}', 'done', 0.75, 'msgbatch_4')""",
                        (TH, TH, TH))
            cur.execute("""insert into extract_batches (id, version, requests, hold_usd, status, cost_usd) values
                             ('pending-1', 'v6', 1, 2, 'pending', null), ('msgbatch_1', 'v6', 1, 3, 'submitted', null),
                             ('msgbatch_2', 'v6', 1, 4, 'collected', 0.1), ('msgbatch_3', 'v6', 1, 5, 'lost', null),
                             ('msgbatch_4', 'v6', 1, 2, 'collected', 1.0)""")
        self.conn.commit()
        c = ceiling(20.0)
        try:
            # 1.25 items + 0.5 failed chunk + 5 lost hold + 0.25 unstored; 2 pending + 3 submitted in flight.
            # msgbatch_2 is a comment-mode batch: its cost is on its items.
            recorded, inflight = c.read()
            self.assertAlmostEqual(recorded, 7.0)
            self.assertEqual(inflight, 5.0)
            self.assertAlmostEqual(c.room(), 20.0 - 12.0)
            # This run's own view counts when it is the larger: spend not stored yet.
            self.assertAlmostEqual(c.room(run_spent_held=8.0, run_reserved=1.0), 20.0 - (7.0 + 8.0) - 1.0)
        finally:
            c.close()

    def test_a_batch_left_in_flight_by_another_process_blocks_a_direct_call(self):
        """A restarted process starts with an empty Budget: only the database
        knows the batch the last one submitted."""
        jobs, _ = X.build_thread_jobs(self.conn, ["t3_a"], self.opts(), write=False, log=QUIET)
        w = jobs[0].worst(batch=False)
        with self.conn.cursor() as cur:
            cur.execute("insert into extract_batches (id, version, requests, hold_usd) "
                        "values ('pending-9', 'v6', 1, 1)")
        self.conn.commit()
        self.seed_spend(0.5)
        b = X.Budget(10.0, ceiling(1.5 + w * 0.9))
        with F.FakeAnthropic(TT.answer) as api:
            X.run_direct_threads(self.conn, AV.client("k", api.base_url), b, self.opts(), ids=["t3_a"],
                                 log=QUIET, stats=X.Stats())
        self.assertEqual(api.requests, [])
        self.assertTrue(b.ceiling_hit)
        # With room for it, it goes.
        b = X.Budget(10.0, ceiling(1.5 + w * 1.1))
        with F.FakeAnthropic(TT.answer) as api:
            X.run_direct_threads(self.conn, AV.client("k", api.base_url), b, self.opts(), ids=["t3_a"],
                                 log=QUIET, stats=X.Stats())
        self.assertEqual(len(api.requests), 1)

    def test_the_ceiling_stops_batch_submissions(self):
        self.seed_spend(1.0)
        b = X.Budget(10.0, ceiling(1.0 + 0.001))
        s = X.Stats()
        with F.FakeAnthropic(TT.answer) as api:
            X.run_batch_threads(self.conn, AV.client("k", api.base_url), b, self.opts(), log=QUIET,
                                sleep=lambda s: None, stats=s, poll_seconds=0)
        self.assertEqual(api.batch_requests, [])
        self.assertTrue(b.ceiling_binds())
        self.assertGreater(s.refused, 0)
        self.assertEqual(self.q("select count(*) from extract_batches"), [(0,)])

    def test_main_exits_0_at_the_ceiling(self):
        self.seed_spend(1.0)
        real = AV.client
        with F.FakeAnthropic(TT.answer) as api, mock.patch.object(db, "DATABASE_URL", base.URL), \
                mock.patch.dict(os.environ, {AV.KEY_VAR: "k", X.CEILING_ENV: "5"}), \
                mock.patch.object(AV, "client", lambda key, base_url=None: real(key, api.base_url)), \
                redirect_stdout(io.StringIO()) as out:
            code = X.main(["--mode", "thread", "--batch", "--max-usd", "10", "--ceiling-usd", "1.001",
                           "--poll-seconds", "0"])
        self.assertEqual(code, 0)
        self.assertEqual(api.batch_requests, [])
        self.assertIn("CEILING REACHED", out.getvalue())
        self.assertIn("ceiling $1.00: $1.0000 recorded", out.getvalue())

    def big(self, p):
        """An answer that costs far more than any worst case: the price table, say, was wrong."""
        msg = TT.thread_answer(p)[1]
        msg["usage"] = {"input_tokens": 10, "output_tokens": 10_000_000}
        return 200, msg

    def test_tripwire_a_batch_that_cost_more_than_its_hold(self):
        b = X.Budget(10.0)
        with F.FakeAnthropic(self.big) as api:
            with self.assertRaises(X.Tripped):
                X.run_batch_threads(self.conn, AV.client("k", api.base_url), b, self.opts(), batch_size=1,
                                    max_inflight=1, log=QUIET, sleep=lambda s: None, poll_seconds=0,
                                    stats=X.Stats())
        self.assertEqual(len(api.batches), 1)               # nothing more was submitted after it
        self.assertIn("held for it", b.tripped)
        self.assertEqual(self.q("select status from extract_batches"), [("collected",)])   # and it was stored

    def test_tripwire_a_direct_call_that_cost_more_than_its_reservation(self):
        b = X.Budget(10.0, ceiling(100.0))
        with F.FakeAnthropic(self.big) as api:
            with self.assertRaises(X.Tripped):
                X.run_direct_threads(self.conn, AV.client("k", api.base_url), b, self.opts(), workers=1,
                                     log=QUIET, stats=X.Stats())
        self.assertEqual(len(api.requests), 1)

    def test_without_a_ceiling_a_direct_overrun_is_logged_and_the_run_goes_on(self):
        """The poller runs without a ceiling: its pass must not end in a traceback."""
        logs = []
        b = X.Budget(100.0)
        with F.FakeAnthropic(self.big) as api:
            X.run_direct_threads(self.conn, AV.client("k", api.base_url), b, self.opts(), workers=1,
                                 log=logs.append, stats=X.Stats())
        self.assertEqual(len(api.requests), 4)                 # every thread's chunk
        self.assertIsNone(b.tripped)
        self.assertEqual(sum("WORST CASE EXCEEDED" in line for line in logs), 4)
        self.assertGreater(b.spent, 4 * 5.0 - 0.01)            # each counted at what it cost

    def test_tripwire_recorded_spend_over_the_ceiling(self):
        """Something spent that no gate counted (here another writer, while the
        batch ran): the collection that sees it stops the run."""
        def results(cid, params):
            with pgtest.connect() as other:
                with other.cursor() as cur:
                    cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash, attempts,
                                     extracted_at, cost_usd) values ('t1_x', 'v6', 'comment', 'zz', 1, now(), 50)""")
            other.close()
            return {"type": "succeeded", "message": TT.thread_answer(params)[1]}
        b = X.Budget(10.0, ceiling(20.0))
        with F.FakeAnthropic(TT.answer, batch_results=results) as api:
            with self.assertRaises(X.Tripped):
                X.run_batch_threads(self.conn, AV.client("k", api.base_url), b, self.opts(), batch_size=1,
                                    max_inflight=1, log=QUIET, sleep=lambda s: None, poll_seconds=0,
                                    stats=X.Stats())
        self.assertEqual(len(api.batches), 1)
        self.assertIn("over the ceiling", b.tripped)

    def test_main_exits_tripped_and_the_runner_exits_0(self):
        real = AV.client
        with F.FakeAnthropic(self.big) as api, mock.patch.object(db, "DATABASE_URL", base.URL), \
                mock.patch.dict(os.environ, {AV.KEY_VAR: "k", "EXTRACT_RUN_USD": "5", X.CEILING_ENV: "30",
                                             "EXTRACT_LOCK_WAIT": "0"}), \
                mock.patch.object(AV, "client", lambda key, base_url=None: real(key, api.base_url)), \
                redirect_stdout(io.StringIO()) as out:
            codes = []

            def run(argv):
                codes.append(X.main(argv + ["--poll-seconds", "0", "--batch-size", "1", "--max-inflight", "1"]))
                return codes[-1]
            self.assertEqual(R.main(run_extract=run), 0)
        self.assertEqual(codes, [X.TRIPPED])
        self.assertIn("SPEND TRIPWIRE", out.getvalue())
        self.assertEqual(len(api.batches), 1)

    def test_runner_cuts_its_cap_to_what_the_ceiling_leaves_above_recorded_spend(self):
        """Not also minus the batches in flight: the run re-attaches them and
        holds them against its own cap, so taking them off here too would
        count them twice."""
        self.seed_spend(6.0)
        with self.conn.cursor() as cur:
            cur.execute("insert into extract_batches (id, version, requests, hold_usd) "
                        "values ('pending-9', 'v6', 1, 0.5)")
        self.conn.commit()
        seen = []
        run = lambda argv: seen.append(argv) or 0       # noqa: E731
        with redirect_stdout(io.StringIO()) as out:
            free, inflight = R.room_left(25.48, pgtest.connect)
            self.assertAlmostEqual(free, 19.48)
            self.assertEqual(inflight, 0.5)
            self.assertEqual(R.main({"EXTRACT_RUN_USD": "20", "EXTRACT_CEILING_USD": "25.48"}, pgtest.connect,
                                    run_extract=run), 0)
            self.assertAlmostEqual(float(seen[0][seen[0].index("--max-usd") + 1]), 19.48)
            seen.clear()
            # $0.03 above recorded spend, but a batch to collect: it runs at the minimum cap.
            self.assertEqual(R.main({"EXTRACT_RUN_USD": "5", "EXTRACT_CEILING_USD": "6.03"}, pgtest.connect,
                                    run_extract=run), 0)
            self.assertEqual(seen[0][seen[0].index("--max-usd") + 1], "0.05")
            seen.clear()
            self.q("delete from extract_batches returning 1")
            self.assertEqual(R.main({"EXTRACT_RUN_USD": "5", "EXTRACT_CEILING_USD": "6.03"}, pgtest.connect,
                                    run_extract=run), 0)
        self.assertEqual(seen, [])                                   # $0.03 left, nothing in flight: not started
        self.assertIn("$6.0000 recorded, $0.5000 held for batches in flight", out.getvalue())
        self.assertIn("CEILING REACHED", out.getvalue())


# ---------------------------------------------------------------- redo
LIST = " ".join(f"PlaceL{i:03d} rocks." for i in range(300))       # 5,099 characters, 300 places


class Redo(TT.ThreadCase):
    def load(self):
        super().load()
        with self.conn.cursor() as cur:
            cur.execute("""insert into comments (id, subreddit, thread_id, parent_id, parent_comment_id, author, body,
                             permalink, created_utc, first_seen_at)
                           select 't1_list', subreddit, id, id, null, 'lister', %s, '/r/x/t1_list',
                                  created_utc + interval '30 minutes', created_utc + interval '30 minutes'
                           from threads where id = 't3_a'""", (LIST,))
            # The fixture's other long comment, made short, so t1_list is the one comment cut.
            cur.execute("update comments set body = 'level 7 talk about PlaceDeep7' where id = 't1_d7'")
        self.conn.commit()

    def first_answer(self, p):
        """What thread mode answered before: and one place the new answer will not name."""
        extra = [dict(F.mention("PlaceGhost"), id=n) for n, text in TT.numbered(F.user_text(p)).items()
                 if text.startswith("PlaceL000")]
        return TT.thread_answer(p, extra)

    def old_run(self):
        """Thread mode as it was: members cut at 1,500, and no member_chars in the output."""
        with mock.patch.object(prompt_v6.thread, "MEMBER_CHARS", 1500), F.FakeAnthropic(self.first_answer) as api:
            self.direct(api)
        self.q("update extraction_state set output = output - 'member_chars' returning 1")
        return api

    def places(self, cid="t1_list"):
        return {k for (k,) in self.q("select entity_key from mentions where comment_id = %s and prompt_hash = %s",
                                     (cid, TH))}

    def redo(self, api, before, batch=False, budget=None, **kw):
        stats = X.Stats()
        X.run_redo(self.conn, AV.client("k", api.base_url), budget or X.Budget(10.0, ceiling(50.0)), self.opts(),
                   before, batch=batch, poll_seconds=0, log=QUIET, sleep=lambda s: None, stats=stats, **kw)
        return stats

    def test_redo_replaces_the_cut_comments_mentions_once(self):
        self.old_run()
        old = self.places()
        self.assertIn("placeghost", old)
        self.assertIn("placel000", old)
        self.assertNotIn("placel299", old)                      # lost past the 1,500-character cut
        cost0, at0 = self.q("select cost_usd, extracted_at from extraction_state where item_id = 't1_list'")[0]
        others = self.q("select item_id, extracted_at, output from extraction_state where item_id <> 't1_list' "
                        "order by 1")
        before = dt.datetime.now(dt.timezone.utc)
        self.assertEqual(X.redo_candidates(self.conn, before), {"t3_a": ["t1_list"]})
        self.assertEqual(X.redo_candidates(self.conn, at0), {})     # finished at T is not before T
        with F.FakeAnthropic(TT.answer) as api:
            s = self.redo(api, before)
        self.assertEqual(len(api.requests), 1)
        user = F.user_text(api.requests[0])
        self.assertEqual(list(TT.numbered(user)), [1])            # only the cut comment is an item
        self.assertIn("PlaceL299 rocks.", user)                     # drawn whole now
        self.assertTrue(api.requests[0]["stream"])
        new = self.places()
        self.assertEqual(new, {f"placel{i:03d}" for i in range(300)})   # the ghost is gone
        cost1, at1, out = self.q("select cost_usd, extracted_at, output from extraction_state "
                                 "where item_id = 't1_list'")[0]
        self.assertGreater(at1, before)
        self.assertGreater(cost1, cost0)                             # the redo's cost adds to what it cost
        self.assertEqual(out["member_chars"], 6000)
        self.assertTrue(out["chunk_id"].startswith("rd-"))
        self.assertEqual(s.done, 1)
        self.assertEqual(self.q("select item_id, extracted_at, output from extraction_state "
                                "where item_id <> 't1_list' order by 1"), others)   # nothing else touched
        # Idempotent: the same command again buys nothing.
        with F.FakeAnthropic(TT.answer) as api:
            self.redo(api, before)
        self.assertEqual(api.requests, [])
        self.assertEqual(self.places(), new)

    def test_redo_through_a_batch_and_after_a_restart(self):
        self.old_run()
        before = dt.datetime.now(dt.timezone.utc)
        # A restart while the redo's batch is in flight: its items are in a
        # batch, so a second selection does not take them again.
        api = F.FakeAnthropic(TT.answer, polls_until_ended=10**6).__enter__()
        try:
            b = X.Budget(10.0, ceiling(50.0))
            jobs = X.build_redo_jobs(self.conn, X.redo_candidates(self.conn, before), self.opts())
            bid = X._submit(self.conn, AV.client("k", api.base_url), b, jobs, QUIET)
            self.assertIsNotNone(bid)
            self.assertEqual(X.redo_candidates(self.conn, before), {})
        finally:
            api.__exit__(None, None, None)
        with F.FakeAnthropic(TT.answer) as api:
            s = self.redo(api, before, batch=True)
        self.assertEqual(api.batch_requests, [])           # the fresh fake does not know it: lost, not resent
        self.assertEqual(self.q("select status from extract_batches where id = %s", (bid,)), [("lost",)])
        # Dropped by hand once the Console shows it gone, its done items are
        # detached, and the next redo sends them in a batch of its own.
        self.assertEqual(X.drop_batch(self.conn, bid), 1)
        with F.FakeAnthropic(TT.answer) as api:
            api._n = 100                                   # its ids must not repeat the lost batch's
            s = self.redo(api, before, batch=True)
        self.assertEqual(len(api.batch_requests), 1)
        self.assertEqual(s.done, 1)
        self.assertEqual(self.places(), {f"placel{i:03d}" for i in range(300)})
        self.assertEqual(X.redo_candidates(self.conn, dt.datetime.now(dt.timezone.utc)), {})

    def test_a_failed_redo_keeps_the_old_extraction_and_is_tried_once_more(self):
        self.old_run()
        old = self.places()
        before = dt.datetime.now(dt.timezone.utc)
        cut = lambda p: (200, F.message('{"mentions": [', stop="max_tokens"))   # noqa: E731
        for _ in range(2):
            with F.FakeAnthropic(cut) as api:
                self.redo(api, before)
            self.assertEqual(len(api.requests), 1)
            self.assertEqual(self.places(), old)
        ch = self.q("select status, fallback, cardinality(alone) from extract_chunks where id like 'rd-%%'")
        self.assertEqual(ch, [("failed", False, 0)] * 2)        # neither split nor sent alone
        self.assertEqual(self.q("select count(*) from extract_chunks where status = 'queued'"), [(0,)])
        self.assertEqual(X.redo_candidates(self.conn, before), {})   # two failures: left as it was
        st = self.q("select extracted_at is not null, extract_error from extraction_state where item_id = 't1_list'")
        self.assertEqual(st, [(True, None)])

    def test_a_redo_that_cannot_be_stored_keeps_the_earlier_extraction(self):
        self.old_run()
        old = self.places()
        cols = "extracted_at, extract_error, attempts, output, prompt_hash, batch_id"
        before_row = self.q(f"select {cols}, cost_usd from extraction_state where item_id = 't1_list'")[0]
        before = dt.datetime.now(dt.timezone.utc)

        def bad(p):
            # A mention the database refuses (mentions_v6_chk): the answer cannot be stored.
            return TT.thread_answer(p, [dict(F.mention("PlaceBad", named_in="bogus"), id=1)])
        logs = []
        for batch in (False, True):
            with F.FakeAnthropic(bad) as api:
                api._n = 10 * (1 + batch)
                X.run_redo(self.conn, AV.client("k", api.base_url), X.Budget(10.0, ceiling(50.0)), self.opts(),
                           before, batch=batch, poll_seconds=0, log=logs.append, sleep=lambda s: None,
                           stats=X.Stats())
            self.assertEqual(self.places(), old)
            row = self.q(f"select {cols}, cost_usd from extraction_state where item_id = 't1_list'")[0]
            self.assertEqual(row[:-1], before_row[:-1])              # exactly as it was, out of any batch
            self.assertGreater(row[-1], before_row[-1])              # but what the redo cost is counted
            before_row = row
        self.assertTrue(any("its earlier extraction is kept" in line for line in logs))

    def test_the_backlog_runs_after_a_redo_the_ceiling_held_back(self):
        """Mid-run, a batch in flight can leave no room under the ceiling;
        room comes back when it is collected, so the backlog still runs, and
        the run's exit is not taken for the ceiling's."""
        with self.conn.cursor() as cur:
            cur.execute("""insert into comments (id, subreddit, thread_id, parent_id, author, body, permalink,
                             created_utc, first_seen_at)
                           select 't1_list2', subreddit, id, id, 'l2', %s, '/r/x/t1_list2', created_utc, created_utc
                           from threads where id = 't3_b'""", (LIST.replace("PlaceL", "PlaceK"),))
        self.conn.commit()
        self.old_run()
        before = dt.datetime.now(dt.timezone.utc)
        with self.conn.cursor() as cur:
            cur.execute("""insert into comments (id, subreddit, thread_id, parent_id, author, body, permalink,
                             created_utc, first_seen_at)
                           select 't1_new', subreddit, id, id, 'nu', 'PlaceNew now', '/r/x/t1_new', now(), now()
                           from threads where id = 't3_c'""")
        self.conn.commit()
        jobs = X.build_redo_jobs(self.conn, X.redo_candidates(self.conn, before), self.opts())
        self.assertEqual(len(jobs), 2)
        w = max(j.worst(batch=True) for j in jobs)
        c = ceiling(1.0)
        recorded = c.read()[0]
        c.close()
        real = AV.client
        with F.FakeAnthropic(TT.answer) as api, mock.patch.object(db, "DATABASE_URL", base.URL), \
                mock.patch.dict(os.environ, {AV.KEY_VAR: "k"}), \
                mock.patch.object(AV, "client", lambda key, base_url=None: real(key, api.base_url)), \
                redirect_stdout(io.StringIO()) as out:
            code = X.main(["--mode", "thread", "--batch", "--batch-size", "1", "--max-inflight", "2",
                           "--poll-seconds", "0", "--max-usd", "5", "--ceiling-usd", repr(recorded + 1.5 * w),
                           "--redo-cut-before", before.isoformat()])
        self.assertEqual(code, 0)
        self.assertEqual(len(api.batches), 3)                         # both redo chunks, then the new comment
        self.assertIn("placenew", self.places("t1_new"))
        self.assertNotIn("CEILING REACHED", out.getvalue())

    def test_redo_is_under_the_ceiling(self):
        self.old_run()
        before = dt.datetime.now(dt.timezone.utc)
        c = ceiling(1.0)
        recorded = c.read()[0]
        c.close()
        b = X.Budget(10.0, ceiling(recorded + 0.0001))
        with F.FakeAnthropic(TT.answer) as api:
            s = self.redo(api, before, budget=b)
        self.assertEqual(api.requests, [])
        self.assertTrue(b.ceiling_hit)
        self.assertEqual(s.refused, 1)

    def test_a_future_time_is_refused(self):
        with F.FakeAnthropic(TT.answer) as api, self.assertRaises(SystemExit):
            self.redo(api, dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1))

    def test_main_redoes_first_then_runs_the_backlog(self):
        self.old_run()
        before = dt.datetime.now(dt.timezone.utc)
        with self.conn.cursor() as cur:            # something new to extract after the redo
            cur.execute("""insert into comments (id, subreddit, thread_id, parent_id, author, body, permalink,
                             created_utc, first_seen_at)
                           select 't1_new', subreddit, id, id, 'nu', 'PlaceNew now', '/r/x/t1_new', now(), now()
                           from threads where id = 't3_b'""")
        self.conn.commit()
        real = AV.client
        with F.FakeAnthropic(TT.answer) as api, mock.patch.object(db, "DATABASE_URL", base.URL), \
                mock.patch.dict(os.environ, {AV.KEY_VAR: "k"}), \
                mock.patch.object(AV, "client", lambda key, base_url=None: real(key, api.base_url)), \
                redirect_stdout(io.StringIO()) as out:
            code = X.main(["--mode", "thread", "--max-usd", "2", "--ceiling-usd", "40",
                           "--redo-cut-before", before.isoformat()])
        self.assertEqual(code, 0)
        self.assertEqual(len(api.requests), 2)
        self.assertIn("PlaceL299", F.user_text(api.requests[0]))
        self.assertIn("PlaceNew", F.user_text(api.requests[1]))
        self.assertIn("redo of comments cut", out.getvalue())
        self.assertIn("placel299", self.places())
        self.assertIn("placenew", self.places("t1_new"))


class LongMembers(TT.ThreadCase):
    """With members up to 6,000 characters, a chunk that runs out of tokens
    is still split, and its worst case still grows with what is sent."""

    def load(self):
        super().load()
        with self.conn.cursor() as cur:
            # m0 before t1_chain and m1 after it, so the halves part them: [post, m0] and [chain, m1].
            for n, minutes in ((0, 1), (1, 40)):
                body = " ".join(f"PlaceM{n}x{i:03d} fine." for i in range(400))      # 7,199 characters
                cur.execute("""insert into comments (id, subreddit, thread_id, parent_id, author, body, permalink,
                                 created_utc, first_seen_at)
                               select %s, subreddit, id, id, %s, %s, '/r/x/' || %s,
                                      created_utc + %s * interval '1 minute', created_utc
                               from threads where id = 't3_b'""", (f"t1_m{n}", f"m{n}", body, f"t1_m{n}", minutes))
        self.conn.commit()

    def opts(self, **kw):
        return X.ThreadOpts(soft_tokens=10000, **kw)      # one chunk, though each member is ~1,500 tokens now

    def test_a_cut_off_chunk_of_long_members_is_split_and_both_halves_land(self):
        jobs, _ = X.build_thread_jobs(self.conn, ["t3_b"], self.opts(), write=False, log=QUIET)
        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertIn("PlaceM1x300", j.user)                 # past the old cut, inside the new one
        self.assertNotIn("PlaceM1x399", j.user)              # past 6,000
        short = X.build_thread_jobs(self.conn, ["t3_c"], self.opts(), write=False, log=QUIET)[0][0]
        self.assertGreater(j.worst(batch=True) - short.worst(batch=True),
                           (len(j.user) - len(short.user)) / AV.CHARS_PER_TOKEN_UPPER * AV.PRICES["cache_write"] / 2
                           * 0.99)

        def answer(p):
            text = F.user_text(p)
            if TT.is_thread(p) and "] u/m0" in text and "] u/m1" in text:
                return 200, F.message('{"mentions": [', stop="max_tokens")
            return TT.answer(p)
        with F.FakeAnthropic(answer) as api:
            s = self.direct(api, ids=["t3_b"])
        self.assertEqual(s.chunk_failures, 1)
        self.assertEqual(len(api.requests), 3)               # the chunk, then its two halves
        st = self.state()
        self.assertTrue(all(v[2] and v[1] == TH for v in st.values()))
        got = {k for (k,) in self.q("select entity_key from mentions where comment_id = 't1_m1'")}
        self.assertIn("placem1x300", got)
        self.assertNotIn("placem1x399", got)


if __name__ == "__main__":
    unittest.main()
