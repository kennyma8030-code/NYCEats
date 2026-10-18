"""Formatting, vectors, spend accounting and the HTTP client, all stubbed.

    python -m unittest discover -s tests

No network and no database: every request goes to tests/fakes.py.
"""

import hashlib
import json
import math
import os
import sqlite3
import threading
import unittest
from unittest import mock

import requests

from fakes import FakeOpenRouter, FakeResponse, b64, fake_vector, ok_body

import embedding as E


# --- the benchmark's formatting, copied verbatim -----------------------------
# From eval/embeddings/configs.py and build_corpus.py on branch
# worktree-agent-abf6969e5737447f0. If production ever formats differently
# from these, its vectors no longer mean what the benchmark measured.

BENCH_QWEN_TASK = ("Given a search query for New York City restaurants, retrieve Reddit "
                   "comments that recommend or describe places matching it")


def bench_plain_doc(title, body):
    return f"{title}\n\n{body}"


def bench_fmt_query(q):
    return f"Instruct: {BENCH_QWEN_TASK}\nQuery:{q}"


def bench_comment(title, body):
    # build_corpus.py: "title": title or "", then fmt_doc(r["title"], r["body"])
    return bench_plain_doc(title or "", body)


def bench_thread(title, selftext):
    # build_corpus.py: title or "", selftext or "", blanked if deleted/removed,
    # cut at THREAD_SELFTEXT_CHARS = 1500, then fmt_doc(title, selftext)
    st = selftext or ""
    if st in ("[deleted]", "[removed]"):
        st = ""
    return bench_plain_doc(title or "", st[:1500])


BENCH_DIR = ("/Users/kenny/NYCEats/.claude/worktrees/agent-abf6969e5737447f0/"
             "eval/embeddings")


class Formatting(unittest.TestCase):
    CASES = [
        ("Best pizza in Brooklyn?", "L'Industrie. Get the burrata slice."),
        ("", "no title at all"),
        (None, "null title"),
        ("Café ☕ in 法拉盛", "Dumplings 🥟 at Nan Xiang\r\nso good"),
        ("t", ""),
    ]

    def test_comment_matches_benchmark(self):
        for title, body in self.CASES:
            self.assertEqual(E.format_comment(title, body), bench_comment(title, body))
        self.assertEqual(E.format_comment("Title", "Body"), "Title\n\nBody")

    def test_thread_matches_benchmark(self):
        long = "é" * 1499 + "🍕" + "x" * 2000
        for title, selftext in [("Where to eat?", "Budget $30, in the LES"),
                                ("Removed", "[removed]"), ("Deleted", "[deleted]"),
                                ("Null", None), ("Empty", ""), ("Long", long),
                                ("Mentions [deleted] inline", "it said [deleted] once")]:
            self.assertEqual(E.format_thread(title, selftext), bench_thread(title, selftext))
        self.assertEqual(E.format_thread("Removed", "[removed]"), "Removed\n\n")
        self.assertEqual(len(E.format_thread("Long", long)), len("Long\n\n") + 1500)
        self.assertTrue(E.format_thread("Long", long).endswith("🍕"))

    def test_query_matches_benchmark(self):
        self.assertEqual(E.QUERY_TASK, BENCH_QWEN_TASK)
        for q in ["cheap dumplings in flushing", "date night, not loud", "🍜"]:
            self.assertEqual(E.format_query(q), bench_fmt_query(q))
        self.assertEqual(
            E.format_query("ramen"),
            "Instruct: Given a search query for New York City restaurants, retrieve "
            "Reddit comments that recommend or describe places matching it\nQuery:ramen")

    def test_documents_carry_no_instruction(self):
        self.assertNotIn("Instruct:", E.format_comment("a", "b"))
        self.assertNotIn("Instruct:", E.format_thread("a", "b"))

    def test_input_hash_is_sha256_of_utf8(self):
        t = E.format_comment("Café", "🥟")
        self.assertEqual(E.input_hash(t), hashlib.sha256(t.encode("utf-8")).hexdigest())
        self.assertNotEqual(E.input_hash("a\n\nb"), E.input_hash("a\n\nb "))

    def test_model_key_names_model_dims_and_provider(self):
        self.assertEqual(E.MODEL_KEY, "qwen/qwen3-embedding-8b@1024:deepinfra")


@unittest.skipUnless(os.path.isdir(os.path.join(BENCH_DIR, "data", "cache")),
                     "benchmark worktree and its local cache are not on this machine")
class ReproducesBenchmarkInputs(unittest.TestCase):
    """The strongest check available: the benchmark cached every Qwen vector
    under sha256 of the exact string it sent. If our formatters build the
    same strings, their hashes are already in that cache."""

    @staticmethod
    def cache(extra):
        key = "qwen/qwen3-embedding-8b|" + json.dumps(extra, sort_keys=True)
        path = os.path.join(BENCH_DIR, "data", "cache",
                            hashlib.sha256(key.encode()).hexdigest()[:16] + ".sqlite")
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True)

    def assert_cached(self, texts):
        con = self.cache(E.ROUTING)
        try:
            for t in texts:
                h = hashlib.sha256(t.encode("utf-8")).hexdigest()
                self.assertIsNotNone(con.execute("select 1 from v where h = ?", (h,)).fetchone(),
                                     f"not what the benchmark embedded: {t[:80]!r}")
        finally:
            con.close()

    def test_routing_is_the_benchmark_pin(self):
        self.assertEqual(E.ROUTING, {"provider": {"order": ["deepinfra"],
                                                  "allow_fallbacks": False}})

    def _rows(self, name, n):
        out = []
        with open(os.path.join(BENCH_DIR, "data", name), encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i % 50 == 0:
                    out.append(json.loads(line))
                if len(out) >= n:
                    break
        return out

    def test_comments(self):
        self.assert_cached([E.format_comment(r["title"], r["body"])
                            for r in self._rows("corpus.jsonl", 400)])

    def test_threads(self):
        self.assert_cached([E.format_thread(r["title"], r["selftext"])
                            for r in self._rows("threads.jsonl", 200)])

    def test_queries(self):
        with open(os.path.join(BENCH_DIR, "queries.jsonl"), encoding="utf-8") as f:
            qs = [json.loads(line)["text"] for line in f if line.strip()]
        self.assert_cached([E.format_query(q) for q in qs])


class Vectors(unittest.TestCase):
    def test_truncate_and_renormalize(self):
        full = fake_vector("x", 4096)
        v = E.truncate_normalize(full)
        self.assertEqual(len(v), 1024)
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in v)), 1.0, places=12)
        # same direction as the first 1024 of the original
        head = full[:1024]
        n = math.sqrt(sum(x * x for x in head))
        for a, b in zip(v, head):
            self.assertAlmostEqual(a, b / n, places=12)

    def test_already_cut_vector_is_unchanged(self):
        v = fake_vector("y", 1024)
        for a, b in zip(E.truncate_normalize(v), v):
            self.assertAlmostEqual(a, b, places=12)

    def test_rejects_unusable_vectors(self):
        for bad in ([0.1] * 512, [0.0] * 1024, [float("nan")] * 1024, [float("inf")] * 1024):
            with self.assertRaises(ValueError):
                E.truncate_normalize(bad)

    def test_decode_base64_and_list(self):
        v = [0.5, -0.25, 1.0]
        self.assertEqual(E.decode(b64(v)), v)
        self.assertEqual(E.decode(v), v)

    def test_pgvector_literal(self):
        self.assertEqual(E.to_pgvector([0.5, -0.25, 1e-5]), "[0.5,-0.25,1e-05]")


class Keys(unittest.TestCase):
    def test_dedicated_key_wins(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "shared",
                                          "EMBED_OPENROUTER_API_KEY": "own"}):
            self.assertEqual(E.api_key(), "own")
            self.assertEqual(E.api_key_var(), "EMBED_OPENROUTER_API_KEY")

    def test_falls_back_to_extraction_key(self):
        env = {k: v for k, v in os.environ.items() if k not in E.KEY_VARS}
        env["OPENROUTER_API_KEY"] = "shared"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(E.api_key(), "shared")

    def test_no_key(self):
        env = {k: v for k, v in os.environ.items() if k not in E.KEY_VARS}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertIsNone(E.api_key_var())
            with self.assertRaises(E.ServiceError):
                E.api_key()

    def test_session_is_reused_per_thread(self):
        with mock.patch.dict(os.environ, {"EMBED_OPENROUTER_API_KEY": "k"}):
            E._tls.__dict__.pop("session", None)
            a, b = E._session(), E._session()
            self.assertIs(a, b)
            self.assertEqual(a.headers["Authorization"], "Bearer k")
            other = []
            t = threading.Thread(target=lambda: other.append(E._session()))
            t.start()
            t.join()
            self.assertIsNot(other[0], a)
            E._tls.__dict__.pop("session", None)


class Budgeting(unittest.TestCase):
    def test_refuses_before_passing_cap(self):
        b = E.Budget(1.0)
        b.reserve(0.6)
        with self.assertRaises(E.BudgetExceeded):
            b.reserve(0.5)
        b.settle(0.6, 0.3)
        b.reserve(0.5)                       # 0.3 spent + 0.5 fits now
        self.assertAlmostEqual(b.reserved, 0.5)
        b.release(0.5)
        self.assertAlmostEqual(b.reserved, 0.0)
        self.assertAlmostEqual(b.spent, 0.3)

    def test_no_cap(self):
        b = E.Budget(None)
        b.reserve(1e9)


NOSLEEP = {"sleep": lambda s: None}


def assert_close(tc, a, b, tol=1e-6):
    """Vectors cross the wire as float32, so compare to float32 precision."""
    tc.assertEqual(len(a), len(b))
    tc.assertLess(max(abs(x - y) for x, y in zip(a, b)), tol)


class Client(unittest.TestCase):
    TEXTS = ["Title\n\nfirst", "Title\n\nsecond"]

    def test_success_payload_and_cost(self):
        b = E.Budget(1.0)
        with FakeOpenRouter() as api:
            out = E.embed_batch(self.TEXTS, b, **NOSLEEP)
        p = api.requests[0]["payload"]
        self.assertEqual(p["model"], "qwen/qwen3-embedding-8b")
        self.assertEqual(p["provider"], {"order": ["deepinfra"], "allow_fallbacks": False})
        self.assertEqual(p["dimensions"], 1024)
        self.assertEqual(p["encoding_format"], "base64")
        self.assertNotIn("input_type", p)
        self.assertEqual(p["input"], self.TEXTS)
        self.assertEqual([len(v) for v, _ in out], [1024, 1024])
        self.assertTrue(all(err is None for _, err in out))
        tokens = sum(len(t.encode()) // 4 for t in self.TEXTS)
        self.assertAlmostEqual(b.spent, tokens * E.PRICE_PER_TOKEN)
        self.assertEqual((b.calls, b.possibly_billed, b.reserved), (1, 0, 0))

    def test_full_size_response_is_cut_the_same_way(self):
        b = E.Budget(1.0)
        with mock.patch.object(E, "SEND_DIMENSIONS", False), FakeOpenRouter() as api:
            [(v, _)] = E.embed_batch(["Title\n\nfirst"], b, **NOSLEEP)
        self.assertNotIn("dimensions", api.requests[0]["payload"])
        assert_close(self, v, E.truncate_normalize(fake_vector("Title\n\nfirst", 4096)))

    def test_order_follows_index_not_arrival(self):
        def handler(p):
            body = ok_body(p)
            body["data"].reverse()
            return FakeResponse(200, body)
        with FakeOpenRouter(handler):
            out = E.embed_batch(self.TEXTS, E.Budget(1.0), **NOSLEEP)
        assert_close(self, out[0][0], E.truncate_normalize(fake_vector(self.TEXTS[0], 1024)))

    def _flaky(self, failure, then_ok=True):
        calls = []

        def handler(p):
            calls.append(1)
            if len(calls) == 1 or not then_ok:
                return failure
            return FakeResponse(200, ok_body(p))
        return handler

    def test_possibly_billed_retries_are_charged_at_estimate(self):
        for failure in (FakeResponse(500, None, "upstream error"),
                        FakeResponse(502, None, "bad gateway"),
                        FakeResponse(429, None, "slow down"),
                        requests.Timeout("read timed out"),
                        requests.ConnectionError("connection reset"),
                        FakeResponse(200, {"error": {"message": "provider hiccup"}}),
                        FakeResponse(200, None, "<html>")):
            b = E.Budget(1.0)
            sleeps = []
            with FakeOpenRouter(self._flaky(failure)) as api:
                out = E.embed_batch(self.TEXTS, b, sleep=sleeps.append)
            est = sum(E.estimate_tokens(t) for t in self.TEXTS) * E.RESERVE_FACTOR \
                * E.PRICE_PER_TOKEN
            real = sum(len(t.encode()) // 4 for t in self.TEXTS) * E.PRICE_PER_TOKEN
            self.assertEqual(len(api.requests), 2, failure)
            self.assertEqual(b.possibly_billed, 1, failure)
            self.assertAlmostEqual(b.spent, est + real, msg=failure)
            self.assertEqual(b.reserved, 0)
            self.assertEqual(len(sleeps), 1)
            self.assertEqual(len(out), 2)

    def test_count_mismatch_is_retried_and_charged(self):
        calls = []

        def handler(p):
            calls.append(1)
            body = ok_body(p)
            if len(calls) == 1:
                body["data"] = body["data"][:1]
            return FakeResponse(200, body)
        b = E.Budget(1.0)
        with FakeOpenRouter(handler) as api:
            out = E.embed_batch(self.TEXTS, b, **NOSLEEP)
        self.assertEqual(len(api.requests), 2)
        self.assertEqual(b.calls, 2)
        self.assertEqual(len(out), 2)

    def test_gives_up_after_attempts(self):
        b = E.Budget(1.0)
        with FakeOpenRouter(lambda p: FakeResponse(503, None, "down")) as api:
            with self.assertRaises(E.ServiceError):
                E.embed_batch(self.TEXTS, b, attempts=3, **NOSLEEP)
        self.assertEqual(len(api.requests), 3)
        self.assertEqual(b.possibly_billed, 3)
        self.assertEqual(b.reserved, 0)

    def test_rejected_input_is_not_billed_or_retried(self):
        for code in (400, 413, 422):
            b = E.Budget(1.0)
            with FakeOpenRouter(lambda p: FakeResponse(code, None, "bad input")) as api:
                with self.assertRaises(E.InputRejected):
                    E.embed_batch(self.TEXTS, b, **NOSLEEP)
            self.assertEqual(len(api.requests), 1)
            self.assertEqual((b.spent, b.reserved, b.possibly_billed), (0, 0, 0))

    def test_auth_and_credit_errors_stop_without_retry(self):
        for code in (401, 402, 403, 404):
            b = E.Budget(1.0)
            with FakeOpenRouter(lambda p: FakeResponse(code, None, "no")) as api:
                with self.assertRaises(E.ServiceError) as cm:
                    E.embed_batch(self.TEXTS, b, **NOSLEEP)
            self.assertNotIsInstance(cm.exception, E.InputRejected)
            self.assertEqual(len(api.requests), 1)
            self.assertEqual((b.spent, b.reserved), (0, 0))

    def test_other_provider_is_refused_but_paid_for(self):
        b = E.Budget(1.0)
        with FakeOpenRouter(lambda p: FakeResponse(200, ok_body(p, provider="Nebius"))):
            with self.assertRaises(E.ServiceError):
                E.embed_batch(self.TEXTS, b, **NOSLEEP)
        self.assertGreater(b.spent, 0)
        self.assertEqual(b.reserved, 0)

    def test_missing_provider_field_is_accepted(self):
        def handler(p):
            body = ok_body(p)
            del body["provider"]
            return FakeResponse(200, body)
        with FakeOpenRouter(handler):
            out = E.embed_batch(self.TEXTS, E.Budget(1.0), **NOSLEEP)
        self.assertEqual(len(out), 2)

    def test_unusable_vector_fails_only_its_row(self):
        def handler(p):
            body = ok_body(p)
            body["data"][1]["embedding"] = b64([0.0] * 1024)
            return FakeResponse(200, body)
        with FakeOpenRouter(handler):
            out = E.embed_batch(self.TEXTS, E.Budget(1.0), **NOSLEEP)
        self.assertIsNotNone(out[0][0])
        self.assertIsNone(out[1][0])
        self.assertIn("unusable vector", out[1][1])

    def test_cap_refuses_before_sending(self):
        b = E.Budget(1e-12)
        with FakeOpenRouter() as api:
            with self.assertRaises(E.BudgetExceeded):
                E.embed_batch(self.TEXTS, b, **NOSLEEP)
        self.assertEqual(api.requests, [])
        self.assertEqual((b.spent, b.reserved), (0, 0))

    def test_cap_stops_retries_too(self):
        est = sum(E.estimate_tokens(t) for t in self.TEXTS) * E.RESERVE_FACTOR \
            * E.PRICE_PER_TOKEN
        b = E.Budget(est * 2.5)               # room for two possibly-billed attempts
        with FakeOpenRouter(lambda p: FakeResponse(500, None, "x")) as api:
            with self.assertRaises(E.BudgetExceeded):
                E.embed_batch(self.TEXTS, b, **NOSLEEP)
        self.assertEqual(len(api.requests), 2)
        self.assertLessEqual(b.spent, b.cap)
        self.assertEqual(b.reserved, 0)

    def test_reservation_released_when_something_unexpected_raises(self):
        b = E.Budget(1.0)
        with mock.patch.object(E, "_post_once", side_effect=RuntimeError("bug")):
            with self.assertRaises(RuntimeError):
                E.embed_batch(self.TEXTS, b, **NOSLEEP)
        self.assertEqual(b.reserved, 0)

    def test_unreported_cost_falls_back_to_tokens(self):
        with FakeOpenRouter(lambda p: FakeResponse(200, ok_body(p, cost=False))):
            b = E.Budget(1.0)
            E.embed_batch(self.TEXTS, b, **NOSLEEP)
        self.assertEqual(b.unpriced, 1)
        self.assertGreater(b.spent, 0)


class Query(unittest.TestCase):
    def test_embed_query(self):
        with FakeOpenRouter() as api:
            v = E.embed_query("  cheap dumplings in flushing ")
        r = api.requests[0]
        self.assertEqual(r["payload"]["input"], [bench_fmt_query("cheap dumplings in flushing")])
        self.assertEqual(r["payload"]["provider"]["order"], ["deepinfra"])
        self.assertEqual(r["payload"]["dimensions"], 1024)
        self.assertEqual(r["timeout"], E.QUERY_TIMEOUT)
        self.assertEqual(len(v), 1024)
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in v)), 1.0, places=9)
        assert_close(self, v, E.truncate_normalize(
            fake_vector(bench_fmt_query("cheap dumplings in flushing"), 1024)))

    def test_query_and_document_vectors_differ(self):
        with FakeOpenRouter():
            q = E.embed_query("ramen")
            [(d, _)] = E.embed_batch([E.format_comment("", "ramen")], E.Budget(), **NOSLEEP)
        self.assertNotEqual(q, d)

    def test_query_retries_less(self):
        with mock.patch("time.sleep"), \
                FakeOpenRouter(lambda p: FakeResponse(503, None, "down")) as api:
            with self.assertRaises(E.ServiceError):
                E.embed_query("ramen")
        self.assertEqual(len(api.requests), E.QUERY_ATTEMPTS)

    def test_empty_query(self):
        with self.assertRaises(ValueError):
            E.embed_query("   ")

    def test_uses_the_shared_session(self):
        with FakeOpenRouter() as api:
            E.embed_query("a")
            E.embed_query("b")
        self.assertEqual(len(api.requests), 2)    # both through the one patched session


if __name__ == "__main__":
    unittest.main()
