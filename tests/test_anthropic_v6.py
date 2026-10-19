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
        waits, lost = [], []
        with F.FakeAnthropic(answer) as api:
            try:
                out = AV.call(AV.client("k", api.base_url), AV.params("s", "u"), attempts=attempts,
                              sleep=waits.append, log=lambda *_: None, on_lost=lost.append)
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

    def test_connection_failure_counts_as_possibly_billed(self):
        lost = []
        cl = AV.client("k", "http://127.0.0.1:9")          # nothing listens on the discard port
        with self.assertRaises(AV.TransientAPIError):
            AV.call(cl, AV.params("s", "u"), attempts=2, sleep=lambda s: None, log=lambda *_: None,
                    on_lost=lost.append)
        self.assertEqual(lost, [1, 1])


if __name__ == "__main__":
    unittest.main()
