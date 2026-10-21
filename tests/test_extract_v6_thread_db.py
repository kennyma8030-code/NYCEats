"""extract_v6 thread mode against a real, disposable Postgres. The API is tests/fake_anthropic.py.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55461/threadtest python -m pytest tests

Same fixture threads as test_extract_v6_db.py. The fake answers a chunk by
reading each numbered line and returning one mention per word starting with
"Place", with that line's number as its id, so attribution is checkable.
"""

import io
import os
import re
import unittest
from contextlib import redirect_stdout
from unittest import mock

from fakes import ROOT

import anthropic_v6 as AV
import db
import extract_v6 as X
import fake_anthropic as F
import prompt_v6
import test_extract_v6_db as base

QUIET = base.QUIET
HOME_LIVE = base.HOME_LIVE
HOME_POSTS = {"t3_a", "t3_b", "t3_c", "t3_old"}
TH = prompt_v6.PROMPT_HASH_THREAD


def numbered(user):
    """{bracket: text the model should read for that item} from a rendered chunk:
    a comment's own words (not its reply marker or quoted stub), and the
    post's title and body when the post is [0]. Quoted context lines carry no
    number and are never read."""
    out, post = {}, False
    for line in user.split("\n"):
        m = re.match(r"^\s*\[(\d+)\] (.*)$", line)
        if m:
            n, rest = int(m.group(1)), m.group(2)
            if rest.startswith("POST: "):
                out[n], post = rest[6:], True
                continue
            post = False
            who, _, after = rest.partition(" ")
            out[n] = after if who.endswith(":") else after.split("): ", 1)[1]
        elif post and line:
            out[0] += " " + line
        else:
            post = False
    return out


def thread_answer(p, extra=()):
    ms = []
    for n, text in numbered(F.user_text(p)).items():
        names = [w.strip(".,!?<>/\"") for w in text.replace("\n", " ").split(" ") if w.startswith("Place")]
        ms += [dict(F.mention(x), id=n) for x in dict.fromkeys(names)]
    return F.ok(ms + list(extra))


def is_thread(p):
    return p["system"][0]["text"] == prompt_v6.SYSTEM_PROMPT_THREAD


def answer(p):
    return thread_answer(p) if is_thread(p) else F.default_answer(p)


def numbers(text, author):
    """True when `author`'s comment is a numbered item of this chunk (not a quoted line)."""
    return re.search(rf"\] u/{author}[ :]", text) is not None


class ThreadCase(base.DbCase):
    def opts(self, **kw):
        return X.ThreadOpts(**kw)

    def direct(self, api, budget=10.0, opts=None, **kw):
        stats = X.Stats()
        X.run_direct_threads(self.conn, AV.client("k", api.base_url), X.Budget(budget), opts or self.opts(),
                             log=QUIET, stats=stats, **kw)
        return stats

    def batch(self, api, budget=10.0, opts=None, **kw):
        stats = X.Stats()
        kw.setdefault("poll_seconds", 0)
        X.run_batch_threads(self.conn, AV.client("k", api.base_url), X.Budget(budget), opts or self.opts(),
                            log=QUIET, sleep=lambda s: None, stats=stats, **kw)
        return stats

    def comment_direct(self, api, **kw):
        return base.Direct.run_direct(self, api, **kw)

    def state(self):
        """{item_id: (kind, prompt_hash, done, extract_error, batch_id, cost_usd)}"""
        return {r[0]: r[1:] for r in self.q("select item_id, kind, prompt_hash, extracted_at is not null, "
                                            "extract_error, batch_id, cost_usd from extraction_state")}


class Direct(ThreadCase):
    def test_every_due_item_once_with_the_thread_hash(self):
        with F.FakeAnthropic(answer) as api:
            s = self.direct(api)
        st = self.state()
        self.assertEqual(set(st), HOME_LIVE | HOME_POSTS)
        self.assertTrue(all(v[2] and v[1] == TH for v in st.values()))
        self.assertEqual({k for k, v in st.items() if v[0] == "post"}, HOME_POSTS)
        self.assertTrue(all(is_thread(r) for r in api.requests))
        self.assertEqual(len(api.requests), 4)                 # one chunk per thread here
        self.assertTrue(all(r == AV.params(r["system"][0]["text"], r["messages"][0]["content"], effort="medium",
                                           max_tokens=32000, schema=AV.OUTPUT_SCHEMA_THREAD) for r in api.requests))
        self.assertEqual(api.requests[0]["max_tokens"], 32000)
        self.assertEqual(api.requests[0]["output_config"]["effort"], "medium")
        self.assertEqual(api.requests[0]["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertIn("id", api.requests[0]["output_config"]["format"]["schema"]["$defs"]["mention"]["required"])
        # Attribution: each comment's own places, under its own id.
        got = {(c, k) for c, k in self.q("select comment_id, entity_key from mentions where comment_id is not null")}
        self.assertIn(("t1_top", "placealpha"), got)
        self.assertIn(("t1_ondel", "placedelta"), got)
        self.assertIn(("t1_d4", "placedeep4"), got)
        self.assertFalse({k for c, k in got if c in ("t1_plus", "t1_r2")})   # "+1" and "keens" name no Place
        # The post's mentions are written as post mode writes them.
        post = self.q("select comment_id, thread_id, entity_key, prompt_hash, schema_version from mentions "
                      "where thread_id is not null")
        self.assertIn((None, "t3_c", "placepost", TH, 6), post)
        self.assertTrue(all(r[0] is None for r in post))
        # Chunks: whole answers kept, cost shared out exactly.
        ch = self.q("select id, thread_id, status, cardinality(members), cost_usd, output is not null "
                    "from extract_chunks")
        self.assertEqual(len(ch), 4)
        self.assertTrue(all(r[2] == "done" and r[5] for r in ch))
        total = sum(float(r[4]) for r in ch)
        self.assertAlmostEqual(total, sum(float(v[5]) for v in st.values()), places=7)
        self.assertAlmostEqual(total, s.cost, places=7)
        self.assertEqual(s.done, len(HOME_LIVE) + 4)
        self.assertEqual(s.chunks, 4)
        out = self.q("select output from extraction_state where item_id = 't1_top'")[0][0]
        self.assertTrue(out["chunk_id"].startswith("ch-"))
        self.assertEqual([m["name"] for m in out["mentions"]], ["PlaceAlpha"])
        # Nothing left: a second run sends nothing, and comment mode finds nothing due.
        with F.FakeAnthropic(answer) as api2:
            self.direct(api2)
        self.assertEqual(api2.requests, [])
        self.assertEqual(X.candidate_ids(self.conn, "comment"), [])
        self.assertEqual(X.candidate_ids(self.conn, "post"), [])

    def test_post_done_in_post_mode_is_context_only(self):
        with F.FakeAnthropic(answer) as api:
            self.comment_direct(api, kinds=("post",))
            self.assertEqual(len(api.requests), 4)
            self.direct(api)
        thread_reqs = [r for r in api.requests if is_thread(r)]
        self.assertEqual(len(thread_reqs), 4)
        self.assertTrue(all(F.user_text(r).startswith("POST: ") for r in thread_reqs))
        self.assertEqual({k: v[1] for k, v in self.state().items() if v[0] == "post"},
                         {t: prompt_v6.PROMPT_HASH_POST for t in HOME_POSTS})
        self.assertEqual(self.q("select count(*) from mentions where thread_id is not null and prompt_hash = %s",
                                (TH,)), [(0,)])

    def test_scope_comments_keeps_posts_as_context(self):
        with F.FakeAnthropic(answer) as api:
            self.direct(api, opts=self.opts(posts=False))
        self.assertEqual(set(self.state()), HOME_LIVE)
        self.assertTrue(all(F.user_text(r).startswith("POST: ") for r in api.requests))

    def test_comments_done_in_comment_mode_are_context_not_items(self):
        with F.FakeAnthropic(answer) as api:
            self.comment_direct(api, ids=["t1_top", "t1_r1"], kinds=("comment",))
            n = len(api.requests)
            self.direct(api)
        a = next(F.user_text(r) for r in api.requests[n:] if "Best dumplings" in F.user_text(r))
        self.assertIn(prompt_v6.thread.CONTEXT_HEADER, a)
        self.assertIn('u/alice: "PlaceAlpha is great"', a)
        self.assertNotIn("] u/alice: PlaceAlpha", a)     # t1_top is quoted, not numbered
        st = self.state()
        self.assertEqual((st["t1_top"][1], st["t1_r1"][1], st["t1_r2"][1]),
                         (prompt_v6.PROMPT_HASH, prompt_v6.PROMPT_HASH, TH))
        members = {m for (ms,) in self.q("select members from extract_chunks") for m in ms}
        self.assertFalse(members & {"t1_top", "t1_r1"})
        ctx = {m for (ms,) in self.q("select context_ids from extract_chunks") for m in ms}
        self.assertTrue({"t1_top", "t1_r1"} <= ctx)

    def test_bad_ids_are_dropped_and_logged(self):
        extra = [dict(F.mention("PlaceBad"), id=99), dict(F.mention("PlaceTrue"), id=True),
                 dict(F.mention("PlaceStr"), id="1"), dict(F.mention("PlaceNeg"), id=-1),
                 dict(F.mention("PlaceNone"), id=None)]
        logs = []
        with F.FakeAnthropic(lambda p: thread_answer(p, extra)) as api:
            stats = X.Stats()
            X.run_direct_threads(self.conn, AV.client("k", api.base_url), X.Budget(10), self.opts(posts=False),
                                 ids=["t3_c"], log=logs.append, stats=stats)
        self.assertEqual(stats.bad_ids, 5)
        self.assertTrue(any("5 mention(s) dropped" in line for line in logs))
        keys = {k for (k,) in self.q("select entity_key from mentions")}
        self.assertFalse(keys & {"placebad", "placetrue", "placestr", "placeneg", "placenone"})
        self.assertEqual(self.q("select bad_ids from extract_chunks"), [(5,)])
        # The whole answer, bad ids included, is still in the chunk's row.
        self.assertEqual(len(self.q("select output from extract_chunks")[0][0]["mentions"]), 8 + 5)
        # Id 0 when the post was context names nothing either.
        with F.FakeAnthropic(lambda p: thread_answer(p, [dict(F.mention("PlaceZero"), id=0)])) as api:
            s = self.direct(api, opts=self.opts(posts=False), ids=["t3_a"])
        self.assertEqual(s.bad_ids, 1)
        self.assertEqual(self.q("select count(*) from mentions where entity_key = 'placezero'"), [(0,)])

    def test_duplicate_spellings_in_one_item_are_one_row(self):
        extra = [dict(F.mention("PlaceDeep1"), id=1), dict(F.mention("placedeep1!"), id=1)]
        with F.FakeAnthropic(lambda p: thread_answer(p, extra)) as api:
            self.direct(api, opts=self.opts(posts=False), ids=["t3_c"])
        self.assertEqual(self.q("select count(*) from mentions where entity_key = 'placedeep1'"), [(1,)])
        out = self.q("select output from extraction_state where item_id = 't1_d1'")[0][0]
        self.assertEqual(len(out["mentions"]), 3)       # every spelling kept in the item's output

    def test_failed_chunk_splits_then_falls_back_to_comment_mode(self):
        def ans(p):
            if is_thread(p):
                if numbers(F.user_text(p), "u1"):          # every chunk numbering t1_d1 overflows
                    return 200, F.message('{"mentions": [', stop="max_tokens")
                return thread_answer(p)
            return F.default_answer(p)
        with F.FakeAnthropic(ans) as api:
            s = self.direct(api, ids=["t3_c"])
        rows = self.q("select generation, status, fallback, cardinality(members) from extract_chunks "
                      "order by generation, status")
        # 9 items (the post and 8 comments) fail whole, then as halves of 5 and
        # 4; the half with t1_d1 fails again and its items go out alone; the
        # other half is answered.
        self.assertEqual(rows, [(0, "failed", False, 9), (1, "done", False, 4), (1, "failed", True, 5)])
        st = self.state()
        self.assertTrue(all(v[2] for v in st.values()))
        alone = sorted(i for i, v in st.items() if v[1] != TH)
        self.assertEqual(alone, sorted(["t3_c", "t1_d1", "t1_d2", "t1_d3", "t1_d4"]))
        self.assertEqual(st["t3_c"][1], prompt_v6.PROMPT_HASH_POST)
        self.assertEqual(st["t1_d1"][1], prompt_v6.PROMPT_HASH)
        self.assertEqual(s.chunk_failures, 2)
        self.assertGreater(float(self.q("select sum(cost_usd) from extract_chunks where status = 'failed'")[0][0]), 0)
        err = self.q("select error from extract_chunks where generation = 0")[0][0]
        self.assertTrue(err.startswith("max_tokens: stopped at 32000"))

    def test_fallback_items_fail_twice_and_park(self):
        def ans(p):
            if is_thread(p) or "PlaceDeep1" in F.user_text(p).split("<comment_to_extract>")[-1]:
                return 200, F.message("garbage")
            return F.default_answer(p)
        with F.FakeAnthropic(ans) as api:
            self.direct(api, ids=["t3_c"], opts=self.opts(posts=False))
            # The chunk, both halves, then each item alone in comment mode,
            # where t1_d1 fails once and is owed a retry, as comment mode does.
            st = self.state()
            self.assertEqual((st["t1_d1"][2], st["t1_d1"][3]), (False, None))
            self.assertEqual(self.q("select attempts from extraction_state where item_id = 't1_d1'"), [(1,)])
            self.assertEqual(sum(1 for r in api.requests if is_thread(r)), 3)
            self.assertEqual(sum(1 for r in api.requests if not is_thread(r)), 8)
            # The next run sends it alone again (not in a chunk): parked with its reason.
            self.direct(api, ids=["t3_c"], opts=self.opts(posts=False))
            self.assertEqual(sum(1 for r in api.requests if is_thread(r)), 3)
            self.assertEqual(sum(1 for r in api.requests if not is_thread(r)), 9)
        st = self.state()
        self.assertTrue(st["t1_d1"][3].startswith("invalid_json"))
        # No due item is left without a row saying what happened.
        self.assertEqual({i for i, v in st.items() if v[2]}, {f"t1_d{i}" for i in range(2, 9)})

    def test_cap_is_never_exceeded(self):
        jobs, _ = X.build_thread_jobs(self.conn, ["t3_a", "t3_b", "t3_c", "t3_old"], self.opts(), write=False,
                                      log=QUIET)
        j = jobs[0]
        self.assertAlmostEqual(j.worst(batch=False), ((len(j.system) + len(j.user)) / 1.5 + 2500) * 0.125e-6
                               + 32000 * 0.5e-6)
        self.assertAlmostEqual(j.worst(batch=True), j.worst(batch=False) / 2)
        ws = [x.worst(batch=False) for x in jobs]
        with F.FakeAnthropic(answer) as api:
            s = self.direct(api, budget=min(ws) * 0.99, workers=1)
        self.assertEqual(len(api.requests), 0)                       # not even one chunk's worst case fits
        self.assertGreater(s.refused, 0)
        # Answers that each cost most of a worst case: whatever is sent, held
        # plus spent never passes the cap at any moment.
        out = int(0.6 * max(ws) / AV.PRICES["out"])
        big = lambda p: (200, F.message('{"mentions": []}', usage={"output_tokens": out, "input_tokens": 0}))  # noqa
        cap = max(ws) * 1.5
        budget = X.Budget(cap)
        seen, real = [], budget.reserve

        def reserve(amount):
            ok = real(amount)
            seen.append(budget.spent + budget.reserved + sum(budget.held.values()))
            return ok
        budget.reserve = reserve
        with F.FakeAnthropic(big) as api:
            X.run_direct_threads(self.conn, AV.client("k", api.base_url), budget, self.opts(), workers=1,
                                 log=QUIET, stats=X.Stats())
        self.assertGreaterEqual(len(api.requests), 1)
        self.assertLess(len(api.requests), 4)
        self.assertTrue(all(x <= cap + 1e-12 for x in seen))
        self.assertLessEqual(budget.spent, cap)


class Batches(ThreadCase):
    def test_one_request_per_chunk(self):
        with F.FakeAnthropic(answer, polls_until_ended=1) as api:
            s = self.batch(api, batch_size=2, max_inflight=1)
        self.assertEqual(set(self.state()), HOME_LIVE | HOME_POSTS)
        self.assertTrue(all(v[2] and v[4] is None for v in self.state().values()))
        self.assertTrue(all(r["custom_id"].startswith("ch-") for r in api.batch_requests))
        self.assertEqual(len(api.batch_requests), 4)
        b = self.q("select requests, status from extract_batches order by created_at")
        self.assertEqual(b, [(2, "collected"), (2, "collected")])
        self.assertEqual(self.q("select count(*) from extract_chunks where status = 'done' and batch_id is not null"),
                         [(4,)])
        self.assertAlmostEqual(s.cost, sum(float(c) for (c,) in self.q("select cost_usd from extract_chunks")),
                               places=7)
        self.assertAlmostEqual(s.cost, 4 * AV.cost(F.USAGE, True), places=7)

    def test_batch_holds_fit_the_cap(self):
        jobs, _ = X.build_thread_jobs(self.conn, ["t3_a", "t3_b", "t3_c", "t3_old"], self.opts(), write=False,
                                      log=QUIET)
        ws = sorted(j.worst(batch=True) for j in jobs)
        cap = ws[-1] + ws[-2] * 0.5       # never the two biggest at once
        seen = []
        real = X._submit_chunks

        def spy(conn, cl, budget, js, log):
            seen.append((sum(j.worst(batch=True) for j in js), budget.spent + sum(budget.held.values())))
            return real(conn, cl, budget, js, log)
        with F.FakeAnthropic(answer) as api, mock.patch.object(X, "_submit_chunks", spy):
            self.batch(api, budget=cap)
        self.assertGreater(len(seen), 1)
        self.assertTrue(all(h + used <= cap + 1e-12 for h, used in seen))
        held = [float(h) for (h,) in self.q("select hold_usd from extract_batches")]
        self.assertAlmostEqual(sum(held), sum(h for h, _ in seen), places=5)
        self.assertEqual(set(self.state()), HOME_LIVE | HOME_POSTS)

    def interrupted_once(self):
        real = X._collect_chunks
        calls = []

        def interrupted(*a, **k):
            calls.append(1)
            if len(calls) == 1:
                raise KeyboardInterrupt
            return real(*a, **k)
        return mock.patch.object(X, "_collect_chunks", interrupted)

    def test_reattach_after_a_restart(self):
        with F.FakeAnthropic(answer) as api:
            with self.interrupted_once():
                with self.assertRaises(KeyboardInterrupt):
                    self.batch(api)
                self.assertEqual(self.q("select status from extract_batches"), [("submitted",)])
                sent = len(api.batch_requests)
                self.assertEqual(X.thread_candidates(self.conn), [])         # all in flight
                self.assertEqual(X.candidate_ids(self.conn, "comment"), [])  # comment mode cannot take them
                self.assertEqual(X.candidate_ids(self.conn, "post"), [])
                self.batch(api)
        self.assertEqual(len(api.batch_requests), sent)                      # nothing resubmitted
        self.assertEqual(set(self.state()), HOME_LIVE | HOME_POSTS)
        self.assertTrue(all(v[2] and v[4] is None for v in self.state().values()))

    def test_comment_mode_run_collects_a_thread_batch(self):
        with F.FakeAnthropic(answer) as api:
            with self.interrupted_once():
                with self.assertRaises(KeyboardInterrupt):
                    self.batch(api)
                sent = len(api.batch_requests)
                base.Batches.run_batch(self, api)       # comment mode re-attaches and stores the chunks
        self.assertEqual(len(api.batch_requests), sent)
        self.assertEqual(set(self.state()), HOME_LIVE | HOME_POSTS)
        self.assertTrue(all(v[1] == TH for v in self.state().values()))

    def test_errored_chunk_splits_and_retries_in_the_same_run(self):
        def results(cid, params):
            text = params["messages"][0]["content"]
            if numbers(text, "u1") and numbers(text, "u8"):     # the whole t3_c chunk errors
                return {"type": "errored", "error": {"type": "error", "error": {"type": "overloaded_error",
                                                                                 "message": "busy"}}}
            _, msg = answer(params)
            return {"type": "succeeded", "message": msg}
        with F.FakeAnthropic(answer, batch_results=results) as api:
            self.batch(api)
        rows = self.q("select generation, status, error from extract_chunks where thread_id = 't3_c' order by 1, 2")
        self.assertEqual([r[:2] for r in rows], [(0, "failed"), (1, "done"), (1, "done")])
        self.assertTrue(rows[0][2].startswith("batch_errored"))
        self.assertEqual(set(self.state()), HOME_LIVE | HOME_POSTS)
        self.assertTrue(all(v[2] and v[4] is None for v in self.state().values()))

    def test_twice_failed_half_goes_out_alone_in_its_own_batch(self):
        def results(cid, params):
            if numbers(params["messages"][0]["content"], "u1"):       # any chunk numbering t1_d1
                return {"type": "expired"}
            _, msg = answer(params)
            return {"type": "succeeded", "message": msg}
        with F.FakeAnthropic(answer, batch_results=results) as api:
            self.batch(api, ids=["t3_c"])
        rows = self.q("select generation, status, fallback from extract_chunks order by 1, 2")
        self.assertEqual(rows, [(0, "failed", False), (1, "done", False), (1, "failed", True)])
        alone = [r for r in api.batch_requests if not r["custom_id"].startswith("ch-")]
        self.assertEqual(sorted(r["custom_id"] for r in alone), ["t1_d1", "t1_d2", "t1_d3", "t1_d4", "t3_c"])
        self.assertTrue(all(not is_thread(r["params"]) for r in alone))
        st = self.state()
        self.assertTrue(all(v[2] and v[4] is None for v in st.values()))
        self.assertEqual(st["t3_c"][1], prompt_v6.PROMPT_HASH_POST)

    def test_pending_none_requeues_chunks_as_recorded(self):
        with F.FakeAnthropic(answer) as api:
            api.accept_then_fail = (500, {"type": "error", "error": {"type": "api_error", "message": "x"}})
            with self.assertRaises(AV.AmbiguousSubmit):
                self.batch(api, ids=["t3_c"])
        pid = self.q("select id from extract_batches")[0][0]
        self.assertTrue(pid.startswith("pending-"))
        self.assertEqual(self.q("select status, batch_id from extract_chunks"), [("batched", pid)])
        X.resolve_pending(self.conn, pid, "none")
        self.assertEqual(self.q("select status, batch_id from extract_chunks"), [("queued", None)])
        cid = self.q("select id from extract_chunks")[0][0]
        with F.FakeAnthropic(answer) as api:
            self.batch(api, ids=["t3_c"])
        self.assertEqual([r["custom_id"] for r in api.batch_requests], [cid])   # the queued row, as recorded
        self.assertEqual(self.q("select status from extract_chunks"), [("done",)])


class Modes(ThreadCase):
    def test_reset_hash_undoes_thread_rows_only(self):
        with F.FakeAnthropic(answer) as api:
            self.comment_direct(api, ids=["t1_top", "t1_r1"], kinds=("comment",))
            self.direct(api)
        before = self.q("select count(*) from mentions where prompt_hash = %s", (prompt_v6.PROMPT_HASH,))
        self.assertGreater(before[0][0], 0)
        X.reset_hash(self.conn, TH, yes=True, log=QUIET)
        self.assertEqual(set(self.state()), {"t1_top", "t1_r1"})
        self.assertEqual(self.q("select count(*) from mentions where prompt_hash = %s", (TH,)), [(0,)])
        self.assertEqual(self.q("select count(*) from mentions where prompt_hash = %s", (prompt_v6.PROMPT_HASH,)),
                         before)
        self.assertEqual(len(X.thread_candidates(self.conn)), 4)

    def test_live_mentions_counts_thread_rows_under_v6(self):
        with F.FakeAnthropic(answer) as api:
            self.direct(api)
        with redirect_stdout(io.StringIO()):
            X.set_read_version(self.conn, "v6", refresh_views=False)
        live = {k for (k,) in self.q("select entity_key from live_mentions")}
        self.assertIn("placealpha", live)
        self.assertNotIn("placepost", live)          # post mentions stay off the board, as in post mode

    def test_dry_run_writes_nothing_and_prices_both_efforts(self):
        logs = []
        out = X.dry_run_threads(self.conn, self.opts(), log=logs.append, show=1)
        self.assertEqual(self.q("select count(*) from extraction_state"), [(0,)])
        self.assertEqual(self.q("select count(*) from extract_chunks"), [(0,)])
        self.assertEqual((out["threads"], out["chunks"], out["items"], out["posts"]), (4, 4, len(HOME_LIVE) + 4, 4))
        text = "\n".join(logs)
        for word in ("effort medium", "effort low", "worst case", "items per chunk", "quoted context"):
            self.assertIn(word, text)

    def test_cli(self):
        with mock.patch.object(db, "DATABASE_URL", base.URL), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(AV.KEY_VAR, None)
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(X.main(["--mode", "thread", "--dry-run", "--newest-first", "--limit", "2"]), 0)
                X.main(["--status"])
            self.assertIn("threads: 2", out.getvalue())
            for bad in (["--mode", "thread", "--scope", "posts", "--dry-run"], ["--effort", "low", "--dry-run"],
                        ["--mode", "thread", "--max-chars", "5", "--dry-run"]):
                with self.assertRaises(SystemExit):
                    X.main(bad)
            with self.assertRaises(SystemExit) as cm:
                X.main(["--mode", "thread", "--max-usd", "1"])
            self.assertIn(AV.KEY_VAR, str(cm.exception))
            real = AV.client
            with F.FakeAnthropic(answer) as api, mock.patch.dict(os.environ, {AV.KEY_VAR: "k"}), \
                    mock.patch.object(AV, "client", lambda key, base_url=None: real(key, api.base_url)), \
                    redirect_stdout(io.StringIO()) as out:
                self.assertEqual(X.main(["--mode", "thread", "--max-usd", "1", "--effort", "low",
                                         "--chunk-comments", "3"]), 0)
                X.main(["--status"])
            self.assertTrue(all(r["output_config"]["effort"] == "low" for r in api.requests))
            self.assertGreater(len(api.requests), 4)
            self.assertIn("thread chunks answered, effort low", out.getvalue())
            self.assertIn("(thread mode)", out.getvalue())
        self.assertEqual(set(self.state()), HOME_LIVE | HOME_POSTS)

    def test_newest_first_orders_threads(self):
        self.assertEqual(X.thread_candidates(self.conn, newest_first=True)[-1], "t3_old")
        self.assertEqual(X.thread_candidates(self.conn)[0], "t3_old")
        self.assertEqual(len(X.thread_candidates(self.conn, limit=2)), 2)

    def test_schema_applies_twice_and_comment_mode_needs_no_chunks_table(self):
        with open(os.path.join(ROOT, "extract_v6_schema.sql"), encoding="utf-8") as f:
            sql = f.read()
        for _ in range(2):
            with self.conn.cursor() as cur:
                cur.execute(sql)
            self.conn.commit()
        self.assertEqual(self.q("select count(*) from pg_indexes where tablename = 'extract_chunks'"), [(3,)])
        with self.conn.cursor() as cur:
            cur.execute("drop table extract_chunks")
        self.conn.commit()
        X.require_schema(self.conn)
        with self.assertRaises(X.SchemaMissing):
            X.require_schema(self.conn, thread=True)
        with F.FakeAnthropic() as api:
            self.comment_direct(api, kinds=("comment",), ids=["t1_top"])
            base.Batches.run_batch(self, api, kinds=("comment",), ids=["t1_r1"])
        self.assertEqual(len(api.requests) + len(api.batch_requests), 2)


if __name__ == "__main__":
    unittest.main()
