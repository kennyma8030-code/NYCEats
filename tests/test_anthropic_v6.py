"""The v6 request is the benchmark's request, and failures sort the way the callers rely on.

No database and no paid call: the real SDK talks to tests/fake_anthropic.py
on localhost. tests/oracle_v6/anthropic_backend.py is the benchmark's backend,
copied verbatim from extraction-v6, and is the reference for the request.
"""

import importlib.util
import os
import unittest
from unittest import mock

from fakes import ROOT

import anthropic_v6 as AV
import fake_anthropic as F
import prompt_v6


def oracle():
    spec = importlib.util.spec_from_file_location(
        "oracle_backend", os.path.join(ROOT, "tests", "oracle_v6", "anthropic_backend.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


USER = "<post_title>t</post_title>\n<comment_to_extract>\nPlaceAlpha\n</comment_to_extract>"


class Request(unittest.TestCase):
    def test_params_equal_the_benchmarks_at_medium(self):
        ob = oracle()
        want = ob.params(prompt_v6.SYSTEM_PROMPT, USER, 16000, "medium", schema=prompt_v6.SCHEMA, cache=True,
                         model="claude-haiku-5-5")
        self.assertEqual(AV.params(prompt_v6.SYSTEM_PROMPT, USER), want)

    def test_request_on_the_wire(self):
        with F.FakeAnthropic() as api:
            AV.call(AV.client("k", api.base_url), AV.params(prompt_v6.SYSTEM_PROMPT, USER))
        body = api.requests[0]
        self.assertEqual(body["model"], "claude-haiku-5-5")
        self.assertEqual(body["max_tokens"], 16000)
        self.assertEqual(body["thinking"], {"type": "adaptive"})
        self.assertEqual(body["output_config"]["effort"], "medium")
        self.assertEqual(body["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(body["system"][0]["cache_control"], {"type": "ephemeral"})
        for banned in ("temperature", "top_p", "top_k"):
            self.assertNotIn(banned, body)
        self.assertNotIn("budget_tokens", body["thinking"])

    def test_strict_schema_uses_anyof_for_nullable(self):
        s = AV.OUTPUT_SCHEMA
        self.assertNotIn("$schema", s)
        self.assertNotIn("title", s)
        level = s["$defs"]["level"]
        self.assertEqual(level, {"anyOf": [{"type": "string", "enum": ["superlative_praise", "praise", "mixed",
                                                                      "knock", "extreme_knock"]},
                                           {"type": "null"}]})
        self.assertEqual(s, oracle().strict_schema(prompt_v6.SCHEMA))

    def test_cost_and_worst_case_match_the_benchmark(self):
        ob = oracle()
        u = {"input_tokens": 400, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 12000,
             "output_tokens": 900}
        for batch in (False, True):
            self.assertAlmostEqual(AV.cost(u, batch), ob.cost(u, batch))
            self.assertAlmostEqual(AV.worst_case(prompt_v6.SYSTEM_PROMPT, USER, batch),
                                   ob.worst_case(prompt_v6.SYSTEM_PROMPT, USER, 16000, batch))
        # $0.10 in, $0.50 out, $0.01 cache read, $0.125 cache write, per MTok; batch halves it.
        self.assertAlmostEqual(AV.cost({"input_tokens": 1e6}, False), 0.10)
        self.assertAlmostEqual(AV.cost({"output_tokens": 1e6}, False), 0.50)
        self.assertAlmostEqual(AV.cost({"cache_read_input_tokens": 1e6}, False), 0.01)
        self.assertAlmostEqual(AV.cost({"cache_creation_input_tokens": 1e6}, True), 0.0625)


class Key(unittest.TestCase):
    def test_only_the_dedicated_key(self):
        env = {"OPENROUTER_API_KEY": "or", "ANTHROPIC_API_KEY": "a", "EVAL_KEY": "e"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertIsNone(AV.api_key())
        with mock.patch.dict(os.environ, dict(env, EXTRACT_ANTHROPIC_API_KEY="x"), clear=True):
            self.assertEqual(AV.api_key(), "x")

    def test_client_ignores_ambient_credentials(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "ambient", "ANTHROPIC_BASE_URL": "http://evil"}):
            cl = AV.client("mine")
            self.assertNotIn("ANTHROPIC_API_KEY", os.environ)
        self.assertEqual(cl.api_key, "mine")
        self.assertEqual(cl.max_retries, 0)
        self.assertIn("api.anthropic.com", str(cl.base_url))


class Parse(unittest.TestCase):
    def code(self, msg):
        with self.assertRaises(AV.ItemError) as cm:
            AV.parse(msg)
        return cm.exception.code

    def test_answers(self):
        self.assertEqual(AV.parse(F.message('{"mentions": []}')), {"mentions": []})
        self.assertEqual(self.code(F.message('{"mentions": [', stop="max_tokens")), "max_tokens")
        self.assertEqual(self.code(dict(F.message(None, stop="refusal"), stop_details={"category": "cyber"})),
                         "refusal")
        self.assertEqual(self.code(F.message("not json")), "invalid_json")
        self.assertEqual(self.code(F.message('{"other": 1}')), "invalid_json")
        self.assertEqual(self.code(F.message('{"mentions": ["x"]}')), "invalid_json")
        self.assertEqual(self.code(F.message('{"mentions": []}', stop="pause_turn")), "stop_pause_turn")


class Errors(unittest.TestCase):
    def run_call(self, answers, attempts=3):
        seq = list(answers)

        def answer(params):
            return seq.pop(0) if seq else F.ok([])
        waits = []
        with F.FakeAnthropic(answer) as api:
            try:
                out = AV.call(AV.client("k", api.base_url), AV.params("s", "u"), attempts=attempts,
                              sleep=waits.append, log=lambda *_: None)
            except Exception as e:
                out = e
        return out, waits, len(api.requests)

    def test_400_is_fatal_with_body(self):
        out, waits, n = self.run_call([F.error(400, "invalid_request_error", "output_config.effort: bad")])
        self.assertIsInstance(out, AV.FatalAPIError)
        self.assertIn("output_config.effort: bad", str(out))
        self.assertEqual((waits, n), ([], 1))

    def test_auth_and_credit_errors_are_fatal(self):
        for st, kind in ((401, "authentication_error"), (403, "permission_error"), (404, "not_found_error"),
                         (413, "request_too_large")):
            out, _, n = self.run_call([F.error(st, kind)])
            self.assertIsInstance(out, AV.FatalAPIError, st)
            self.assertEqual(n, 1)

    def test_429_and_5xx_back_off_then_succeed(self):
        out, waits, n = self.run_call([F.error(429, "rate_limit_error"), F.error(529, "overloaded_error"),
                                       F.error(500, "api_error")], attempts=4)
        self.assertEqual(AV.parse(out), {"mentions": []})
        self.assertEqual(n, 4)
        self.assertEqual(len(waits), 3)
        self.assertEqual(waits[0], 0)            # the fake's retry-after: 0 is honoured

    def test_outlasting_the_backoff_is_transient(self):
        out, waits, n = self.run_call([F.error(503, "api_error")] * 5, attempts=3)
        self.assertIsInstance(out, AV.TransientAPIError)
        self.assertEqual((n, len(waits)), (3, 2))

    def test_connection_failure_asks_before_retrying(self):
        asked = []
        cl = AV.client("k", "http://127.0.0.1:9")          # nothing listens on the discard port
        with self.assertRaises(AV.TransientAPIError) as cm:
            AV.call(cl, AV.params("s", "u"), attempts=3, sleep=lambda s: None, log=lambda *_: None,
                    retry_ok=lambda: asked.append(1) or True)
        self.assertEqual(asked, [1, 1])                   # before each retry, not after the last
        self.assertTrue(cm.exception.maybe_billed)

    def test_no_room_to_retry_gives_up(self):
        cl = AV.client("k", "http://127.0.0.1:9")
        with self.assertRaises(AV.CapReached):
            AV.call(cl, AV.params("s", "u"), attempts=3, sleep=lambda s: None, log=lambda *_: None,
                    retry_ok=lambda: False)

    def test_status_errors_do_not_ask(self):
        # A 429/5xx answer was not billed, so retrying needs no new reservation.
        asked = []
        seq = [F.error(529, "overloaded_error")]
        with F.FakeAnthropic(lambda p: seq.pop(0) if seq else F.ok([])) as api:
            AV.call(AV.client("k", api.base_url), AV.params("s", "u"), attempts=3, sleep=lambda s: None,
                    log=lambda *_: None, retry_ok=lambda: asked.append(1) or True)
        self.assertEqual(asked, [])


class BatchCalls(unittest.TestCase):
    def test_submit_outcomes(self):
        with F.FakeAnthropic() as api:
            cl = AV.client("k", api.base_url)
            api.submit_status = F.error(400, "invalid_request_error")
            with self.assertRaises(AV.FatalAPIError):
                AV.submit(cl, [("t1_a", AV.params("s", "u"))])
            api.submit_status = F.error(429, "rate_limit_error")
            with self.assertRaises(AV.TransientAPIError):
                AV.submit(cl, [("t1_a", AV.params("s", "u"))])
            self.assertEqual(api.batches, {})
            api.accept_then_fail = F.error(500, "api_error")
            with self.assertRaises(AV.AmbiguousSubmit):
                AV.submit(cl, [("t1_a", AV.params("s", "u"))])
            self.assertEqual(len(api.batches), 1)          # it exists, and would bill
        with self.assertRaises(AV.AmbiguousSubmit):
            AV.submit(AV.client("k", "http://127.0.0.1:9"), [("t1_a", AV.params("s", "u"))])

    def test_404_is_not_found_everywhere(self):
        with F.FakeAnthropic() as api:
            cl = AV.client("k", api.base_url)
            with self.assertRaises(AV.NotFound):
                AV.retrieve(cl, "msgbatch_nope")
            bid = AV.submit(cl, [("t1_a", AV.params("s", "u"))])
            AV.retrieve(cl, bid)
            api.forgotten.add(bid)
            with self.assertRaises(AV.NotFound):
                AV.results(cl, bid)
            listed, covered = AV.recent_batches(cl)
            self.assertEqual(([b.id for b in listed], covered), ([bid], True))
            self.assertEqual(api.gets, 4)                      # a 404 is not retried

    def test_results_errors_are_mapped(self):
        waits = []
        with self.assertRaises(AV.TransientAPIError):
            AV.results(AV.client("k", "http://127.0.0.1:9"), "msgbatch_x", sleep=waits.append, log=QUIET)
        self.assertEqual(len(waits), len(AV.GET_WAITS))


QUIET = lambda *a, **k: None  # noqa: E731


class BatchReads(unittest.TestCase):
    """Reading a batch back is safe to repeat, so a multi-day run rides out
    outages there instead of stopping (finding 3 of the v6 audit)."""

    def setUp(self):
        self.api = F.FakeAnthropic().__enter__()
        self.cl = AV.client("k", self.api.base_url)
        self.bid = AV.submit(self.cl, [("t1_a", AV.params("s", "u")), ("t1_b", AV.params("s", "u"))])
        self.waits = []

    def tearDown(self):
        self.api.__exit__(None, None, None)

    def read(self, fn, *a):
        return fn(self.cl, *a, sleep=self.waits.append, log=QUIET)

    def test_5xx_429_and_resets_on_retrieve_are_retried(self):
        self.api.get_failures = [F.error(529, "overloaded_error"), F.error(500, "api_error"),
                                 F.error(429, "rate_limit_error")]
        self.assertEqual(self.read(AV.retrieve, self.bid).id, self.bid)
        self.assertEqual(len(self.waits), 3)
        self.assertEqual(self.waits[2], 0)                      # retry-after honoured

    def test_a_truncated_results_stream_is_read_again(self):
        self.api.truncate_results = 2
        got = self.read(AV.results, self.bid)
        self.assertEqual(set(got), {"t1_a", "t1_b"})
        self.assertEqual(len(self.waits), 2)

    def test_a_missing_results_url_is_transient(self):
        self.api.no_results_url = 1
        self.assertEqual(set(self.read(AV.results, self.bid)), {"t1_a", "t1_b"})
        self.assertEqual(len(self.waits), 1)

    def test_list_retries_and_pages(self):
        for _ in range(4):
            AV.submit(self.cl, [("t1_c", AV.params("s", "u"))])
        self.api.get_failures = [F.error(503, "api_error")]
        listed, covered = self.read(lambda cl, **kw: AV.recent_batches(cl, limit=2, **kw))
        self.assertEqual(len(listed), 5)
        self.assertTrue(covered)
        self.assertEqual(len(self.waits), 1)
        # Stopping short of the end, with nothing older than `until` seen, is not coverage.
        import datetime as dt
        listed, covered = self.read(lambda cl, **kw: AV.recent_batches(
            cl, until=dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc), limit=2, max_pages=2, **kw))
        self.assertEqual((len(listed), covered), (4, False))

    def test_outlasting_the_retries_is_transient(self):
        self.api.get_failures = [F.error(529, "overloaded_error")] * (len(AV.GET_WAITS) + 1)
        with self.assertRaises(AV.TransientAPIError) as cm:
            self.read(AV.retrieve, self.bid)
        self.assertIn("529", str(cm.exception))
        self.assertGreater(sum(AV.GET_WAITS), 5 * 60)          # several minutes before a run stops

    def test_4xx_is_fatal_at_once(self):
        self.api.get_failures = [F.error(401, "authentication_error")]
        with self.assertRaises(AV.FatalAPIError):
            self.read(AV.retrieve, self.bid)
        self.assertEqual(self.waits, [])


if __name__ == "__main__":
    unittest.main()
