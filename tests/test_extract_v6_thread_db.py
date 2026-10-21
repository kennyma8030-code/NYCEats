"""extract_v6 thread mode against a real, disposable Postgres. The API is tests/fake_anthropic.py.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55461/threadtest python -m pytest tests

Same fixture threads as test_extract_v6_db.py. The fake answers a chunk by
reading each numbered line and returning one mention per word starting with
"Place", with that line's number as its id, so attribution is checkable.
"""

import io
import json
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

    def test_batch_errors_unrelated_to_size_resend_the_chunk_as_it_was(self):
        seen = []

        def results(cid, params):
            text = params["messages"][0]["content"]
            if numbers(text, "u1") and numbers(text, "u8"):          # the whole t3_c chunk
                seen.append(cid)
                if len(seen) == 1:
                    return {"type": "errored", "error": {"type": "error", "error": {
                        "type": "overloaded_error", "message": "busy"}}}
            _, msg = answer(params)
            return {"type": "succeeded", "message": msg}
        with F.FakeAnthropic(answer, batch_results=results) as api:
            s = self.batch(api)
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0], seen[1])                           # the same chunk, as it was
        rows = self.q("select generation, status, attempts from extract_chunks where thread_id = 't3_c'")
        self.assertEqual(rows, [(0, "done", 2)])                     # not split
        self.assertEqual(s.chunk_failures, 0)
        self.assertEqual(set(self.state()), HOME_LIVE | HOME_POSTS)
        self.assertTrue(all(v[1] == TH and v[2] and v[4] is None for v in self.state().values()))

    def test_a_chunk_that_keeps_expiring_waits_for_the_next_run(self):
        expiring = [True]

        def results(cid, params):
            text = params["messages"][0]["content"]
            if expiring[0] and numbers(text, "u1") and numbers(text, "u8"):
                return {"type": "expired"}
            _, msg = answer(params)
            return {"type": "succeeded", "message": msg}
        api = F.FakeAnthropic(answer, batch_results=results).__enter__()
        self.addCleanup(api.__exit__)
        self.batch(api)
        sent = [r["custom_id"] for r in api.batch_requests]
        rows = self.q("select id, generation, status, attempts, error from extract_chunks where thread_id = 't3_c'")
        self.assertEqual(len(rows), 1)
        cid, gen, status, attempts, error = rows[0]
        self.assertEqual((gen, status, attempts, error), (0, "queued", 2, "batch_expired"))
        self.assertEqual(sent.count(cid), 2)                         # twice in the run, then it waits
        st = self.state()
        t3c = {"t3_c"} | {f"t1_d{i}" for i in range(1, 9)}
        self.assertTrue(all(not st[i][2] and st[i][1] == TH and st[i][4] is None for i in t3c))  # due, not alone
        self.assertEqual(X.thread_candidates(self.conn)[0], "t3_c")  # a retry owed comes first
        expiring[0] = False
        self.batch(api)
        self.assertEqual([r["custom_id"] for r in api.batch_requests][len(sent):], [cid])
        self.assertEqual(self.q("select status, attempts from extract_chunks where thread_id = 't3_c'"), [("done", 3)])
        self.assertTrue(all(v[2] for v in self.state().values()))

    def test_twice_failed_half_goes_out_alone_in_its_own_batch(self):
        def results(cid, params):
            if numbers(params["messages"][0]["content"], "u1"):       # any chunk numbering t1_d1
                return {"type": "succeeded", "message": F.message('{"mentions": [', stop="max_tokens")}
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

    def test_an_answer_postgres_refuses_is_split_and_the_batch_still_collected(self):
        # A NUL in a note: jsonb refuses it, so neither the chunk's whole
        # answer nor t1_d1's mention can be stored. The batch is still marked
        # collected, the other items are stored, and t1_d1 goes out again in a
        # half, whose clean answer is stored.
        def results(cid, params):
            text = params["messages"][0]["content"]
            st, msg = answer(params)
            if numbers(text, "u1") and numbers(text, "u8"):
                body = json.loads(msg["content"][1]["text"])
                for m in body["mentions"]:
                    if m["id"] == 1:
                        m["notes"] = [{"about": "tip", "text": "nul \u0000 here"}]
                msg = F.message(json.dumps(body))
            return {"type": "succeeded", "message": msg}
        logs = []
        with F.FakeAnthropic(answer, batch_results=results) as api:
            stats = X.Stats()
            X.run_batch_threads(self.conn, AV.client("k", api.base_url), X.Budget(10), self.opts(), ids=["t3_c"],
                                log=logs.append, sleep=lambda s: None, stats=stats, poll_seconds=0)
        self.assertEqual({s for (s,) in self.q("select status from extract_batches")}, {"collected"})
        rows = self.q("select generation, status, error from extract_chunks order by 1, 2")
        self.assertEqual([r[:2] for r in rows], [(0, "failed"), (1, "done"), (1, "dropped")])
        self.assertTrue(rows[0][2].startswith("store_error"))
        st = self.state()
        self.assertTrue(all(v[2] for v in st.values()), st)
        self.assertEqual(self.q("select count(*) from mentions where comment_id = 't1_d1'"), [(1,)])
        self.assertEqual(self.q("select attempts from extraction_state where item_id = 't1_d1'"), [(2,)])
        self.assertTrue(any("could not be stored" in line for line in logs))

    def test_an_answer_postgres_refuses_direct(self):
        def ans(p):
            st, msg = answer(p)
            if is_thread(p) and numbers(F.user_text(p), "u1") and numbers(F.user_text(p), "u8"):
                body = json.loads(msg["content"][1]["text"])
                body["mentions"][0]["notes"] = [{"about": "tip", "text": "nul \u0000"}]
                msg = F.message(json.dumps(body))
            return st, msg
        with F.FakeAnthropic(ans) as api:
            s = self.direct(api, ids=["t3_c"])
        self.assertTrue(all(v[2] for v in self.state().values()))
        self.assertEqual(s.chunk_failures, 1)
        self.assertTrue(self.q("select error from extract_chunks where generation = 0")[0][0].startswith("store_error"))

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
    def halves_of_t3c(self):
        """Fail t3_c's chunk by hand, so two halves are queued, as a run would leave them."""
        jobs, _ = X.build_thread_jobs(self.conn, ["t3_c"], self.opts(), write=False, log=QUIET)
        X._chunk_failed(self.conn, jobs[0], "max_tokens: by hand", None, 0.0, QUIET)
        return {r[0]: r[1] for r in self.q("select id, members from extract_chunks where status = 'queued'")}

    def test_items_waiting_in_memory_do_not_drop_their_queued_half(self):
        halves = self.halves_of_t3c()
        self.assertEqual(len(halves), 2)
        everything = {i for ms in halves.values() for i in ms}
        # A retry rebuild while those items wait in this run's queue: nothing is
        # sent again, nothing is chunked afresh, and the halves stay queued.
        jobs, alone = X.build_thread_jobs(self.conn, ["t3_c"], self.opts(), exclude=everything, log=QUIET)
        self.assertEqual((jobs, alone), ([], []))
        self.assertEqual(self.q("select count(*) from extract_chunks where status = 'queued'"), [(2,)])
        # Held for this run (a chunk sent twice already): its items are claimed, not chunked afresh.
        held = sorted(halves)[0]
        jobs, _ = X.build_thread_jobs(self.conn, ["t3_c"], self.opts(), hold={held}, log=QUIET)
        self.assertEqual([j.id for j in jobs], [h for h in halves if h != held])
        self.assertEqual(self.q("select count(*) from extract_chunks where status = 'queued'"), [(2,)])
        # Nothing excluded: the halves go out as recorded, generation 1.
        jobs, _ = X.build_thread_jobs(self.conn, ["t3_c"], self.opts(), log=QUIET)
        self.assertEqual(sorted(j.id for j in jobs), sorted(halves))
        self.assertTrue(all(j.generation == 1 for j in jobs))

    def test_resolved_queued_chunks_are_retired(self):
        halves = self.halves_of_t3c()
        self.assertEqual(X.thread_candidates(self.conn)[0], "t3_c")      # a retry owed comes first
        ids = sorted({i for ms in halves.values() for i in ms})
        with F.FakeAnthropic() as api:                                    # comment and post mode do them all
            self.comment_direct(api, ids=ids)
        self.assertNotIn("t3_c", X.thread_candidates(self.conn))
        self.assertEqual(X.retire_chunks(self.conn, log=QUIET), 2)
        self.assertEqual(self.q("select status, count(*) from extract_chunks group by 1 order by 1"),
                         [("dropped", 2), ("failed", 1)])
        out = io.StringIO()
        with redirect_stdout(out):
            X.status(self.conn)
        self.assertNotIn("queued", out.getvalue())

    def test_going_alone_applies_once(self):
        def ans(p):
            return (200, F.message("garbage")) if is_thread(p) else F.default_answer(p)
        with F.FakeAnthropic(ans) as api:
            self.direct(api, ids=["t3_c"], opts=self.opts(posts=False))
        st = self.state()
        self.assertTrue(all(st[f"t1_d{i}"][2] and st[f"t1_d{i}"][1] == prompt_v6.PROMPT_HASH for i in range(1, 9)))
        # The failed half's row no longer routes anything: once its items are
        # reset, they are chunked again like any due comment.
        X.reset_hash(self.conn, prompt_v6.PROMPT_HASH, kinds=("comment",), yes=True, log=QUIET)
        jobs, alone = X.build_thread_jobs(self.conn, ["t3_c"], self.opts(posts=False), write=False, log=QUIET)
        self.assertEqual(alone, [])
        self.assertEqual(sorted(m for j in jobs for m in j.chunk.members), [f"t1_d{i}" for i in range(1, 9)])
        self.assertTrue(all(j.generation == 0 for j in jobs))

    def test_reset_hash_drops_that_prompts_queued_halves(self):
        self.halves_of_t3c()
        X.reset_hash(self.conn, TH, yes=True, log=QUIET)
        self.assertEqual(self.q("select count(*) from extract_chunks where status = 'queued'"), [(0,)])

    def test_a_stopped_run_counts_what_it_did_not_send(self):
        jobs, _ = X.build_thread_jobs(self.conn, ["t3_a", "t3_b", "t3_c", "t3_old"], self.opts(), write=False,
                                      log=QUIET)
        w = max(j.worst(batch=False) for j in jobs)
        out = int(w / AV.PRICES["out"]) + 1                  # each answer costs a whole worst case
        big = lambda p: (200, F.message('{"mentions": []}', usage={"output_tokens": out, "input_tokens": 0}))  # noqa
        with F.FakeAnthropic(big) as api:
            s = self.direct(api, budget=w * 1.5, workers=1)
        self.assertEqual(len(api.requests), 1)
        done = set(self.state())
        self.assertEqual(s.refused, len(HOME_LIVE | HOME_POSTS) - len(done))
        self.assertEqual(len(s.threads_open), 3)
        self.assertEqual(s.threads_left, 0)

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

    def test_schema_applies_twice_and_counts_extract_chunks_as_part_of_v6(self):
        with open(os.path.join(ROOT, "extract_v6_schema.sql"), encoding="utf-8") as f:
            sql = f.read()
        for _ in range(2):
            with self.conn.cursor() as cur:
                cur.execute(sql)
            self.conn.commit()
        self.assertEqual(self.q("select count(*) from pg_indexes where tablename = 'extract_chunks'"), [(4,)])
        self.assertTrue(X.schema_ready(self.conn))
        # Every mode collects either kind of batch, so a database without the
        # table is not ready for any v6 run.
        with self.conn.cursor() as cur:
            cur.execute("drop table extract_chunks")
        self.conn.commit()
        self.assertFalse(X.schema_ready(self.conn))
        with self.assertRaises(X.SchemaMissing):
            X.require_schema(self.conn)


OLD_CHUNKS = """create table extract_chunks (
  id           text primary key,
  version      text not null,
  thread_id    text not null,
  prompt_hash  text not null,
  effort       text not null,
  post_item    boolean not null default false,
  members      text[] not null,
  context_ids  text[] not null default '{}',
  generation   smallint not null default 0,
  split_from   text,
  status       text not null default 'queued'
               check (status in ('queued', 'batched', 'done', 'failed', 'dropped')),
  fallback     boolean not null default false,
  batch_id     text,
  error        text,
  bad_ids      int,
  output       jsonb,
  usage        jsonb,
  cost_usd     numeric(12, 8),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  finished_at  timestamptz
)"""


class Review2(ThreadCase):
    def comment_batch(self, api, **kw):
        stats = X.Stats()
        X.run_batch(self.conn, AV.client("k", api.base_url), X.Budget(10), kinds=("comment",), log=QUIET,
                    sleep=lambda s: None, stats=stats, poll_seconds=0, **kw)
        return stats

    def assert_not_alone(self, ids):
        st = self.state()
        self.assertTrue(ids and all(st[i][1] == prompt_v6.PROMPT_HASH and not st[i][2] and st[i][4] is None
                                    for i in ids), {i: st.get(i) for i in ids})
        jobs, alone = X.build_thread_jobs(self.conn, ["t3_c"], self.opts(posts=False), write=False, log=QUIET)
        self.assertEqual(alone, [])
        self.assertEqual(sorted(m for j in jobs for m in j.chunk.members), sorted(ids))

    def test_comment_hash_without_a_thread_failure_is_not_alone_refused_submit(self):
        ids = [f"t1_d{i}" for i in range(1, 9)]
        with F.FakeAnthropic() as api:
            api.submit_status = (429, {"type": "error", "error": {"type": "rate_limit_error", "message": "slow"}})
            with self.assertRaises(AV.TransientAPIError):
                self.comment_batch(api, ids=ids)
        self.assert_not_alone(ids)

    def test_comment_hash_without_a_thread_failure_is_not_alone_dropped_batch(self):
        ids = [f"t1_d{i}" for i in range(1, 9)]
        with F.FakeAnthropic() as api, mock.patch.object(X, "_collect", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.comment_batch(api, ids=ids)
        bid = self.q("select id from extract_batches")[0][0]
        X.drop_batch(self.conn, bid)
        self.assert_not_alone(ids)

    def test_comment_hash_without_a_thread_failure_is_not_alone_pending_none(self):
        ids = [f"t1_d{i}" for i in range(1, 9)]
        with F.FakeAnthropic() as api:
            api.accept_then_fail = (500, {"type": "error", "error": {"type": "api_error", "message": "x"}})
            with self.assertRaises(AV.AmbiguousSubmit):
                self.comment_batch(api, ids=ids)
        X.resolve_pending(self.conn, self.q("select id from extract_batches")[0][0], "none")
        self.assert_not_alone(ids)

    def test_comment_mode_run_logs_no_false_retry_for_a_thread_batch(self):
        logs = []
        real = X._collect_chunks
        calls = []

        def interrupted(*a, **k):
            calls.append(1)
            if len(calls) == 1:
                raise KeyboardInterrupt
            return real(*a, **k)
        with F.FakeAnthropic(answer) as api:
            with mock.patch.object(X, "_collect_chunks", interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    self.batch(api)
                X.run_batch(self.conn, AV.client("k", api.base_url), X.Budget(10), log=logs.append,
                            sleep=lambda s: None, stats=X.Stats(), poll_seconds=0)
        self.assertFalse([line for line in logs if "owe a retry" in line], logs)

    def test_comment_mode_run_logs_the_real_retry_count(self):
        logs = []
        real = X._collect_chunks
        calls = []

        def interrupted(*a, **k):
            calls.append(1)
            if len(calls) == 1:
                raise KeyboardInterrupt
            return real(*a, **k)

        def ans(p):
            if is_thread(p) and numbers(F.user_text(p), "u1"):
                return 200, F.message('{"mentions": [', stop="max_tokens")
            return answer(p)
        with F.FakeAnthropic(ans) as api:
            with mock.patch.object(X, "_collect_chunks", interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    self.batch(api)
                X.run_batch(self.conn, AV.client("k", api.base_url), X.Budget(10), log=logs.append,
                            sleep=lambda s: None, stats=X.Stats(), poll_seconds=0)
        self.assertEqual([line.strip() for line in logs if "owe a retry" in line][0].split(": ")[1][:23],
                         "1 thread(s) owe a retry")

    def test_batch_run_stopped_by_an_error_counts_what_it_did_not_send(self):
        with F.FakeAnthropic(answer) as api:
            api.submit_status = (400, {"type": "error", "error": {"type": "invalid_request_error", "message": "no"}})
            stats = X.Stats()
            with self.assertRaises(AV.FatalAPIError):
                X.run_batch_threads(self.conn, AV.client("k", api.base_url), X.Budget(10), self.opts(),
                                    log=QUIET, sleep=lambda s: None, stats=stats, poll_seconds=0)
        self.assertEqual(stats.refused, len(HOME_LIVE | HOME_POSTS))
        self.assertEqual(stats.threads_open, HOME_POSTS)
        self.assertEqual(self.q("select count(*) from extract_batches"), [(0,)])
        self.assertEqual(self.q("select count(*) from extraction_state where batch_id is not null"), [(0,)])

    def test_direct_run_stopped_while_items_go_alone_counts_the_built_chunks(self):
        # Every t3_c item was handed over to go alone; the other threads' chunks
        # are built in the same page, and the first alone request is refused.
        jobs, _ = X.build_thread_jobs(self.conn, ["t3_c"], self.opts(), write=False, log=QUIET)
        X._chunk_failed(self.conn, jobs[0], "max_tokens: by hand", None, 0.0, QUIET)
        for half in X.build_thread_jobs(self.conn, ["t3_c"], self.opts(), log=QUIET)[0]:
            X._chunk_failed(self.conn, half, "max_tokens: by hand", None, 0.0, QUIET)
        others, _ = X.build_thread_jobs(self.conn, ["t3_a", "t3_b", "t3_old"], self.opts(), write=False, log=QUIET)
        with F.FakeAnthropic(lambda p: F.error(401, "authentication_error")) as api:
            stats = X.Stats()
            with self.assertRaises(AV.FatalAPIError):
                X.run_direct_threads(self.conn, AV.client("k", api.base_url), X.Budget(10), self.opts(),
                                     workers=1, log=QUIET, stats=stats)
        self.assertTrue(all(not is_thread(r) for r in api.requests))
        self.assertEqual(stats.refused, sum(len(j.chunk) for j in others))
        self.assertEqual(stats.threads_open, {"t3_a", "t3_b", "t3_old"})

    def test_a_direct_send_adds_one_to_attempts(self):
        jobs, _ = X.build_thread_jobs(self.conn, ["t3_c"], self.opts(), write=False, log=QUIET)
        X._chunk_failed(self.conn, jobs[0], "max_tokens: by hand", None, 0.0, QUIET)
        first = sorted(r[0] for r in self.q("select id from extract_chunks where status = 'queued'"))[0]
        self.q("update extract_chunks set attempts = 1 where id = %s returning id", (first,))   # sent once already
        with F.FakeAnthropic(answer) as api:
            self.direct(api, ids=["t3_c"])
        got = dict(self.q("select id, attempts from extract_chunks where generation = 1"))
        self.assertEqual(got[first], 2)
        self.assertEqual(sorted(got.values()), [1, 2])

    def test_one_chunks_refused_write_is_not_repeated_as_it_was(self):
        def ans(p):
            st, msg = answer(p)
            if is_thread(p) and numbers(F.user_text(p), "u1") and numbers(F.user_text(p), "u8"):
                body = json.loads(msg["content"][1]["text"])
                body["mentions"][0]["notes"] = [{"about": "tip", "text": "nul \u0000"}]
                msg = F.message(json.dumps(body))
            return st, msg
        real, together = X.write, []

        def spy(conn, entries, before=None):
            if before is not None and len(entries) == 9:
                together.append(1)
            return real(conn, entries, before)
        with F.FakeAnthropic(ans) as api, mock.patch.object(X, "write", spy):
            self.direct(api, ids=["t3_c"])
        self.assertEqual(len(together), 1)
        self.assertTrue(all(v[2] for v in self.state().values()))

    def test_schema_upgrades_a_table_of_the_first_shape(self):
        with self.conn.cursor() as cur:
            cur.execute("drop table extract_chunks")
            cur.execute(OLD_CHUNKS)
        self.conn.commit()
        self.assertFalse(X.schema_ready(self.conn))          # no attempts column: not ready
        with self.assertRaises(X.SchemaMissing):
            X.require_schema(self.conn)
        with open(os.path.join(ROOT, "extract_v6_schema.sql"), encoding="utf-8") as f:
            sql = f.read()
        for _ in range(2):
            with self.conn.cursor() as cur:
                cur.execute(sql)
            self.conn.commit()
        self.assertTrue(X.schema_ready(self.conn))
        self.assertEqual(self.q("select column_default, is_nullable from information_schema.columns "
                                "where table_name = 'extract_chunks' and column_name = 'attempts'"), [("0", "NO")])
        with F.FakeAnthropic(answer) as api:
            self.direct(api, ids=["t3_c"])
        self.assertEqual(self.q("select attempts from extract_chunks"), [(1,)])

if __name__ == "__main__":
    unittest.main()
