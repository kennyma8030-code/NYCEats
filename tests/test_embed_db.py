"""embed.py against a real, disposable Postgres with pgvector. API stubbed.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55439/embedtest \\
        python -m pytest tests

(EMBED_TEST_DATABASE_URL works too.) Skipped without a URL, or when that
server has no pgvector. These tests DROP AND RECREATE the public schema of
that database; tests/pgtest.py has the guard that keeps them off anything
but a local throwaway. Never point it at DATABASE_URL.
"""

import dataclasses
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import psycopg2

from fakes import FakeOpenRouter, FakeResponse, ok_body, ROOT
import pgtest

import embed
import embedding as E
import subreddits

URL = pgtest.URL
_guard = pgtest.guard


NOW = datetime.now(timezone.utc)
LONG_SELFTEXT = "é" * 1499 + "🍕" + "tail " * 400
THREADS = [
    ("t3_a", "Best pizza in Brooklyn?", LONG_SELFTEXT, NOW),
    ("t3_b", "Café ☕ in 法拉盛", "[removed]", NOW),
    ("t3_c", "No selftext", None, NOW),
    ("t3_d", "Deleted post", "[deleted]", NOW),
    ("t3_e", "Quotes 'and' \\backslashes\\", "line one\r\nline \"two\"\n\n", NOW),
    ("t3_old", "Old thread", "from last year", NOW - timedelta(days=400)),
]
SPECIAL = [
    # id, thread, body, has_mention, created
    ("t1_deleted", "t3_a", "[deleted]", True, NOW),
    ("t1_removed", "t3_a", "[removed]", True, NOW),
    ("t1_nomention", "t3_a", "I have no mentions", False, NOW),
    ("t1_unicode", "t3_b", "Dumplings 🥟 at Nan Xiang 南翔, très bien", True, NOW),
    ("t1_crlf", "t3_e", "it's \\n not a newline\r\nbut this is", True, NOW),
    ("t1_old", "t3_old", "Old comment about Lucali", True, NOW - timedelta(days=30)),
]
N_BULK = 300


def bulk_id(i):
    return f"t1_bulk{i:04d}"


class DbCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not URL:
            raise unittest.SkipTest(pgtest.SKIP_REASON)
        _guard(URL)
        conn = psycopg2.connect(URL)
        try:
            if not pgtest.has_pgvector(conn):
                raise unittest.SkipTest("embedding tests skipped: the test server has no pgvector")
        finally:
            conn.close()

    def setUp(self):
        self.conn = psycopg2.connect(URL)
        with self.conn.cursor() as cur:
            cur.execute("drop schema if exists public cascade; create schema public")
        self.conn.commit()
        import db
        db.init(self.conn, os.path.join(ROOT, "schema.sql"))
        self.load_fixtures()

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def load_fixtures(self):
        with self.conn.cursor() as cur:
            for tid, title, selftext, created in THREADS:
                cur.execute("""insert into threads (id, subreddit, title, selftext, created_utc)
                               values (%s, 'FoodNYC', %s, %s, %s)""", (tid, title, selftext, created))
            rows = list(SPECIAL) + [(bulk_id(i), "t3_a", f"Comment {i} about L'Industrie",
                                     True, NOW) for i in range(N_BULK)]
            for cid, tid, body, mention, created in rows:
                cur.execute("""insert into comments (id, thread_id, parent_id, body, permalink,
                                                     created_utc)
                               values (%s, %s, %s, %s, '', %s)""", (cid, tid, tid, body, created))
                if mention:
                    # Two prompt hashes on some rows: eligibility is "any mention".
                    for ph in (["p1", "p2"] if cid.endswith("0") else ["p1"]):
                        cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key,
                                                             model_version, prompt_hash)
                                       values (%s, 'X', 'x', 'm', %s)""", (cid, ph))
        self.conn.commit()

    # helpers
    def count(self, sql, *args):
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchone()[0]

    def eligible_comments(self):
        return {c[0] for c in SPECIAL
                if c[3] and c[2] not in ("[deleted]", "[removed]")} | \
               {bulk_id(i) for i in range(N_BULK)}

    def run_embed(self, scope="both", budget=None, **kw):
        kw.setdefault("workers", 2)
        kw.setdefault("attempts", 2)
        return embed.run(self.conn, embed.KINDS[scope], budget or E.Budget(1.0),
                         log=lambda *_: None, **kw)


def todo(conn, kind, limit=10_000, since=None):
    rows, _ = embed.select_todo(conn, kind, "", limit, since)
    return rows


class SqlMirrorsFormatter(DbCase):
    def test_text_and_hash_match_python(self):
        for kind in (embed.COMMENTS, embed.THREADS):
            with self.conn.cursor() as cur:
                cur.execute(kind.candidates, {"after": "", "since": None, "limit": 10_000,
                                              "sub": subreddits.HOME})
                ids = [r[0] for r in cur.fetchall()]
                cur.execute(f"select src.id, src.a, src.b, src.txt from ({kind.source}) src",
                            {"ids": ids})
                rows = cur.fetchall()
            self.assertTrue(rows)
            for item_id, a, b, txt in rows:
                self.assertEqual(txt, kind.fmt(a, b), item_id)
            for item_id, a, b, h in todo(self.conn, kind):
                self.assertEqual(h, E.input_hash(kind.fmt(a, b)), item_id)

    def test_long_selftext_cut_at_1500_characters(self):
        [(_, a, b, _)] = [r for r in todo(self.conn, embed.THREADS) if r[0] == "t3_a"]
        self.assertTrue(E.format_thread(a, b).endswith("🍕"))


class Eligibility(DbCase):
    def test_what_gets_selected(self):
        got = {r[0] for r in todo(self.conn, embed.COMMENTS)}
        self.assertEqual(got, self.eligible_comments())
        threads = {r[0] for r in todo(self.conn, embed.THREADS)}
        self.assertEqual(threads, {t[0] for t in THREADS})

    def test_since_window(self):
        since = NOW - timedelta(days=3)
        got = {r[0] for r in todo(self.conn, embed.COMMENTS, since=since)}
        self.assertNotIn("t1_old", got)
        self.assertIn("t1_unicode", got)


class OnlyHome(DbCase):
    """The poller stores six other cities beside r/FoodNYC; none of it is embedded."""

    def setUp(self):
        super().setUp()
        with self.conn.cursor() as cur:
            cur.execute("""insert into threads (id, subreddit, title, selftext, created_utc)
                           values ('t3_chi', 'chicagofood', 'Best Italian beef?', 'go', %s)""",
                        (NOW,))
            # A mention on another city's comment cannot happen today (extraction
            # reads HOME only); this checks embedding does not lean on that alone.
            cur.execute("""insert into comments (id, subreddit, thread_id, parent_id, body,
                                                 permalink, created_utc)
                           values ('t1_chi', 'chicagofood', 't3_chi', 't3_chi',
                                   'Johnnie''s Beef, every time', '', %s)""", (NOW,))
            cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key,
                                                 model_version, prompt_hash)
                           values ('t1_chi', 'X', 'x', 'm', 'p1')""")
        self.conn.commit()

    def test_other_cities_are_not_candidates(self):
        self.assertEqual({r[0] for r in todo(self.conn, embed.COMMENTS)}, self.eligible_comments())
        self.assertEqual({r[0] for r in todo(self.conn, embed.THREADS)}, {t[0] for t in THREADS})

    def test_full_run_never_embeds_them(self):
        with FakeOpenRouter():
            self.run_embed()
        self.assertEqual(self.count("select count(*) from comment_embeddings "
                                    "where comment_id = 't1_chi'"), 0)
        self.assertEqual(self.count("select count(*) from thread_embeddings "
                                    "where thread_id = 't3_chi'"), 0)


class Paging(DbCase):
    """#5 and #6: pages are bounded by candidate ids, sized from the run."""

    def test_page_of_finished_rows_is_empty_but_moves_on(self):
        with FakeOpenRouter():
            self.run_embed(scope="comments", limit=100, batch=50)
        rows, after = embed.select_todo(self.conn, embed.COMMENTS, "", 10)
        self.assertEqual(rows, [])
        self.assertEqual(after, bulk_id(9))
        rows, after = embed.select_todo(self.conn, embed.COMMENTS, bulk_id(99), 10)
        self.assertEqual([r[0] for r in rows], [bulk_id(i) for i in range(100, 110)])
        self.assertEqual(after, bulk_id(109))
        self.assertEqual(embed.select_todo(self.conn, embed.COMMENTS, "t1_zzz", 10), ([], None))

    def test_only_candidates_are_hashed(self):
        # The second statement must be restricted to the candidate ids, not
        # hash every remaining row and filter afterwards.
        seen = []
        real = self.conn

        class Conn:
            def cursor(self):
                return Spy(real.cursor())

            def commit(self):
                real.commit()

        class Spy:
            def __init__(self, cur):
                self.cur = cur

            def __enter__(self):
                self.cur.__enter__()
                return self

            def __exit__(self, *a):
                return self.cur.__exit__(*a)

            def execute(self, sql, params=None):
                seen.append((sql, params))
                return self.cur.execute(sql, params)

            def __getattr__(self, name):
                return getattr(self.cur, name)

        rows, _ = embed.select_todo(Conn(), embed.COMMENTS, "", 7)
        self.assertEqual(len(rows), 7)
        hash_sql, hash_params = seen[1]
        self.assertIn("any(%(ids)s)", hash_sql)
        self.assertEqual(len(hash_params["ids"]), 7)

    def test_resume_walks_past_finished_pages_with_a_small_page(self):
        with FakeOpenRouter():
            self.run_embed(scope="comments", limit=100, batch=50)
        limits = []
        real = embed.select_todo

        def spy(conn, kind, after, limit, *a, **k):
            limits.append(limit)
            return real(conn, kind, after, limit, *a, **k)
        with FakeOpenRouter() as api, mock.patch.object(embed, "select_todo", spy):
            stats = self.run_embed(scope="comments", batch=5, workers=1)
        self.assertEqual(stats.embedded["comment"], len(self.eligible_comments()) - 100)
        self.assertEqual(len(api.inputs), len(self.eligible_comments()) - 100)
        self.assertEqual(set(limits), {embed.page_size(5, 1)})     # 10, not the import-time 1024
        self.assertGreater(len(limits), 10)


class FullRun(DbCase):
    def test_embeds_everything_once(self):
        b = E.Budget(1.0)
        with FakeOpenRouter() as api:
            stats = self.run_embed(budget=b, batch=64)
        self.assertIsNone(stats.stop)
        self.assertEqual(stats.embedded, {"comment": len(self.eligible_comments()),
                                          "thread": len(THREADS)})
        self.assertEqual(len(api.inputs), len(self.eligible_comments()) + len(THREADS))
        self.assertTrue(all(len(r["payload"]["input"]) <= 64 for r in api.requests))
        self.assertEqual(self.count("select count(*) from comment_embeddings where model = %s",
                                    E.MODEL_KEY), len(self.eligible_comments()))
        # stored as unit-length halfvec(1024)
        with self.conn.cursor() as cur:
            cur.execute("""select min(vector_dims(embedding)), max(vector_dims(embedding)),
                                  min(l2_norm(embedding)), max(l2_norm(embedding))
                           from comment_embeddings""")
            dmin, dmax, nmin, nmax = cur.fetchone()
        self.assertEqual((dmin, dmax), (1024, 1024))
        self.assertAlmostEqual(nmin, 1.0, places=2)
        self.assertAlmostEqual(nmax, 1.0, places=2)
        self.conn.rollback()

        with FakeOpenRouter() as again:
            stats = self.run_embed()
        self.assertEqual(again.requests, [])
        self.assertEqual(sum(stats.embedded.values()), 0)

    def test_stored_hash_is_of_the_embedded_text(self):
        with FakeOpenRouter() as api:
            self.run_embed(scope="comments")
        sent = {E.input_hash(t) for t in api.inputs}
        with self.conn.cursor() as cur:
            cur.execute("select input_hash from comment_embeddings")
            stored = {r[0] for r in cur.fetchall()}
        self.assertEqual(stored, sent)


class ChangedText(DbCase):
    def test_edited_comment_is_embedded_again(self):
        with FakeOpenRouter():
            self.run_embed()
        with self.conn.cursor() as cur:
            cur.execute("update comments set body = 'edited: now about Lucali' where id = 't1_unicode'")
        self.conn.commit()
        with FakeOpenRouter() as api:
            stats = self.run_embed()
        self.assertEqual(api.inputs, [E.format_comment("Café ☕ in 法拉盛", "edited: now about Lucali")])
        self.assertEqual(stats.embedded, {"comment": 1, "thread": 0})
        self.assertEqual(self.count("select count(*) from comment_embeddings where comment_id = 't1_unicode'"), 1)
        self.assertEqual(
            self.count("select input_hash from comment_embeddings where comment_id = 't1_unicode'"),
            E.input_hash(api.inputs[0]))

    def test_changed_title_reembeds_its_thread_and_comments(self):
        with FakeOpenRouter():
            self.run_embed()
        with self.conn.cursor() as cur:
            cur.execute("update threads set title = 'Café renamed' where id = 't3_b'")
        self.conn.commit()
        with FakeOpenRouter() as api:
            stats = self.run_embed()
        self.assertEqual(stats.embedded, {"comment": 1, "thread": 1})
        self.assertEqual(len(api.inputs), 2)

    def test_other_model_rows_are_left_alone(self):
        with FakeOpenRouter():
            self.run_embed(scope="comments")
        with self.conn.cursor() as cur:
            cur.execute("update comment_embeddings set model = 'old-model@1024:other'")
        self.conn.commit()
        with FakeOpenRouter() as api:
            self.run_embed(scope="comments")
        n = len(self.eligible_comments())
        self.assertEqual(len(api.inputs), n)        # new model: everything is due
        self.assertEqual(self.count("select count(*) from comment_embeddings"), 2 * n)


class Resume(DbCase):
    def _kill_on_second_store(self, exc):
        real = embed.store_vectors
        calls = []

        def store(conn, kind, done):
            calls.append(1)
            if len(calls) == 2:
                raise exc
            return real(conn, kind, done)
        return mock.patch.object(embed, "store_vectors", store)

    def test_hard_kill_mid_run_then_resume(self):
        with FakeOpenRouter(), self._kill_on_second_store(SystemExit("killed")):
            with self.assertRaises(SystemExit):
                self.run_embed(scope="comments", batch=50, workers=1)
        self.conn.rollback()
        first = self.count("select count(*) from comment_embeddings")
        self.assertEqual(first, 50)
        with self.conn.cursor() as cur:
            cur.execute("select comment_id from comment_embeddings")
            done = {r[0] for r in cur.fetchall()}
        self.conn.commit()

        with FakeOpenRouter() as api:
            stats = self.run_embed(scope="comments", batch=50)
        self.assertIsNone(stats.stop)
        resent = {i for i in self.eligible_comments()}
        self.assertEqual(len(api.inputs), len(resent) - first)
        self.assertEqual(self.count("select count(*) from comment_embeddings"), len(resent))
        # nothing that was committed before the kill was paid for twice
        with self.conn.cursor() as cur:
            cur.execute("select c.id, t.title, c.body from comments c join threads t on t.id = c.thread_id "
                        "where c.id = any(%s)", (list(done),))
            done_texts = {E.format_comment(t, b) for _, t, b in cur.fetchall()}
        self.assertFalse(done_texts & set(api.inputs))

    def test_ctrl_c_keeps_finished_batches_and_re_raises(self):
        # #8: the interrupt propagates, so a poller under Ctrl-C stops.
        stats = embed.Stats()
        with FakeOpenRouter(), self._kill_on_second_store(KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                self.run_embed(scope="comments", batch=50, workers=1, stats=stats)
        self.assertIn("interrupted", stats.stop)
        stored = self.count("select count(*) from comment_embeddings")
        # the first batch, plus any that had already come back when it hit
        self.assertGreaterEqual(stored, 50)
        self.assertLess(stored, len(self.eligible_comments()))
        self.assertEqual(stored, stats.embedded["comment"])


class PerRowErrors(DbCase):
    POISON = "t1_bulk0123"

    def poison_handler(self, p):
        if any("Comment 123 " in t for t in p["input"]):
            return FakeResponse(400, None, '{"error": "input rejected"}')
        return FakeResponse(200, ok_body(p))

    def test_bad_input_is_isolated_and_recorded(self):
        with FakeOpenRouter(self.poison_handler) as api:
            stats = self.run_embed(scope="comments", batch=128)
        self.assertIsNone(stats.stop)
        n = len(self.eligible_comments())
        self.assertEqual(stats.embedded["comment"], n - 1)
        self.assertEqual(stats.failed["comment"], 1)
        # bisection: the batch holding the poison was split down to it
        self.assertGreater(len(api.requests), -(-n // 128))
        with self.conn.cursor() as cur:
            cur.execute("select item_id, kind, model, error, failures from embedding_errors")
            [(item, kind, model, err, failures)] = cur.fetchall()
        self.conn.commit()
        self.assertEqual((item, kind, model, failures), (self.POISON, "comment", E.MODEL_KEY, 1))
        self.assertIn("rejected", err)

        # skipped while the text is unchanged
        with FakeOpenRouter(self.poison_handler) as api:
            self.run_embed(scope="comments")
        self.assertEqual(api.requests, [])

        # --retry-errors clears it, it fails again, and the count says so
        with self.conn.cursor() as cur:
            cur.execute("delete from embedding_errors where model = %s", (E.MODEL_KEY,))
        self.conn.commit()
        with FakeOpenRouter(self.poison_handler) as api:
            self.run_embed(scope="comments")
        # the row itself, and the canary that proves the request shape is fine
        self.assertEqual(sorted(api.inputs),
                         sorted([embed.CANARY, E.format_comment("Best pizza in Brooklyn?",
                                                                "Comment 123 about L'Industrie")]))
        self.assertEqual(self.count("select failures from embedding_errors"), 1)

        # an edit makes it due on its own, and success clears the error
        with self.conn.cursor() as cur:
            cur.execute("update comments set body = 'fixed' where id = %s", (self.POISON,))
        self.conn.commit()
        with FakeOpenRouter(self.poison_handler) as api:
            stats = self.run_embed(scope="comments")
        self.assertEqual(stats.embedded["comment"], 1)
        self.assertEqual(self.count("select count(*) from embedding_errors"), 0)

    def test_repeat_failures_are_counted(self):
        def handler(p):
            if any("Comment 123 " in t for t in p["input"]):
                body = ok_body(p)
                for d in body["data"]:
                    if "Comment 123 " in p["input"][d["index"]]:
                        d["embedding"] = [0.0] * 1024
                return FakeResponse(200, body)
            return FakeResponse(200, ok_body(p))
        with FakeOpenRouter(handler):
            self.run_embed(scope="comments")
        with self.conn.cursor() as cur:
            cur.execute("update embedding_errors set input_hash = 'stale'")
        self.conn.commit()
        with FakeOpenRouter(handler):
            self.run_embed(scope="comments")
        with self.conn.cursor() as cur:
            cur.execute("select failures, error from embedding_errors")
            [(failures, err)] = cur.fetchall()
        self.assertEqual(failures, 2)
        self.assertIn("unusable vector", err)

    def test_outage_stops_the_run_without_stamping_rows(self):
        with FakeOpenRouter(lambda p: FakeResponse(503, None, "down")):
            stats = self.run_embed(attempts=2)
        self.assertIn("ServiceError", stats.stop)
        self.assertEqual(self.count("select count(*) from embedding_errors"), 0)
        self.assertEqual(self.count("select count(*) from comment_embeddings"), 0)
        with FakeOpenRouter() as api:
            self.run_embed()
        self.assertEqual(len(api.inputs), len(self.eligible_comments()) + len(THREADS))

    def test_formatter_drift_is_recorded_not_rebought(self):
        drifted = dataclasses.replace(embed.COMMENTS, fmt=lambda a, b: f"{a}\n{b}")
        with FakeOpenRouter() as api, mock.patch.dict(embed.KINDS, {"comments": [drifted]}):
            stats = self.run_embed(scope="comments")
            self.assertEqual(api.requests, [])
            self.assertEqual(stats.failed["comment"], len(self.eligible_comments()))
            stats = self.run_embed(scope="comments")
        self.assertEqual(sum(stats.failed.values()), 0)
        self.assertIn("drift", self.count("select min(error) from embedding_errors"))


class RequestLevelRejections(DbCase):
    """#2: a 400 about the request must not stamp the backlog."""

    def test_request_level_400_stops_without_marking_rows(self):
        with FakeOpenRouter(lambda p: FakeResponse(
                400, None, '{"error": {"message": "dimensions is not supported"}}')) as api:
            stats = self.run_embed(scope="comments", batch=128, workers=2)
        self.assertIn("ServiceError", stats.stop)
        self.assertIn("canary", stats.stop)
        self.assertEqual(self.count("select count(*) from embedding_errors"), 0)
        self.assertEqual(self.count("select count(*) from comment_embeddings"), 0)
        self.assertLess(len(api.requests), 40)          # one descent per worker, not 300 rows
        self.assertEqual(len(todo(self.conn, embed.COMMENTS)), len(self.eligible_comments()))

    def test_rejected_rows_are_capped_per_run(self):
        def handler(p):
            if p["input"] == [embed.CANARY]:
                return FakeResponse(200, ok_body(p))
            return FakeResponse(400, None, "bad input")
        with mock.patch.object(embed, "MAX_REJECTED", 5), FakeOpenRouter(handler):
            stats = self.run_embed(scope="comments", batch=16, workers=1)
        self.assertIn("more than 5 inputs rejected", stats.stop)
        self.assertEqual(self.count("select count(*) from embedding_errors"), 5)


class KeepsWhatWasPaidFor(DbCase):
    def test_left_half_survives_a_failure_in_the_right_half(self):
        # #1: the first batch (bulk0000-0127) is refused whole; its left half
        # succeeds; its right half hits an auth error that stops the run.
        def handler(p):
            if len(p["input"]) == 128:
                return FakeResponse(400, None, "one of these is bad")
            if any("Comment 0 about" in t for t in p["input"]):
                return FakeResponse(200, ok_body(p))
            return FakeResponse(401, None, "key revoked")
        with FakeOpenRouter(handler):
            stats = self.run_embed(scope="comments", batch=128, workers=1)
        self.assertIn("ServiceError", stats.stop)
        self.assertEqual(self.count("select count(*) from comment_embeddings"), 64)
        self.assertEqual(stats.embedded["comment"], 64)
        self.assertEqual(self.count("select count(*) from embedding_errors"), 0)

    def test_malformed_response_stops_run_but_keeps_other_batches(self):
        # #7: the second batch comes back with duplicate indexes.
        def handler(p):
            body = ok_body(p)
            if any("Comment 200 about" in t for t in p["input"]):
                for d in body["data"]:
                    d["index"] = 0
            return FakeResponse(200, body)
        with FakeOpenRouter(handler):
            stats = self.run_embed(scope="comments", batch=128, workers=1)
        self.assertIn("malformed response", stats.stop)
        self.assertEqual(self.count("select count(*) from comment_embeddings"), 128)
        self.assertEqual(self.count("select count(*) from embedding_errors"), 0)


class Deadline(DbCase):
    def test_deadline_is_checked_per_batch(self):
        # #4: one page holds many batches; once the deadline passes, no new
        # batch starts even though the page is not finished.
        import time as _time

        def slow(p):
            _time.sleep(0.3)
            return FakeResponse(200, ok_body(p))
        with FakeOpenRouter(slow) as api:
            stats = self.run_embed(scope="comments", batch=50, workers=1,
                                   deadline=_time.monotonic() + 0.1)
        self.assertEqual(len(api.requests), 1)
        self.assertEqual(self.count("select count(*) from comment_embeddings"), 50)
        self.assertIn("out of time", stats.stop)


class BootSchemaNeverFails(DbCase):
    def test_any_failure_in_the_embedding_block_is_skipped(self):
        # #3: a clash (here a stray `halfvec` type) makes create extension
        # fail. Before, only insufficient_privilege was caught and the whole
        # boot schema aborted.
        import db
        with self.conn.cursor() as cur:
            cur.execute("drop schema public cascade; create schema public")
            cur.execute("create domain public.halfvec as int")
        self.conn.commit()
        db.init(self.conn, os.path.join(ROOT, "schema.sql"))
        notices = " ".join(self.conn.notices)
        self.assertIn("embedding tables skipped", notices)
        self.assertEqual(self.count("select to_regclass('comments') is not null"), True)
        self.assertEqual(self.count("select to_regclass('restaurant_images') is not null"), True)
        self.assertEqual(self.count("select to_regclass('comment_embeddings') is null"), True)
        self.assertEqual(self.count("select count(*) from pg_extension where extname = 'vector'"), 0)


class Cli(DbCase):
    def main(self, *argv):
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with mock.patch.object(embed.db, "connect", return_value=self.conn), \
                mock.patch("sys.argv", ["embed.py", *argv]), redirect_stdout(out):
            embed.main()
        return out.getvalue()

    def test_since_days_zero_is_a_window(self):
        # #10: 0 days means "nothing older than now", not "no window".
        out = self.main("--dry-run", "--scope", "comments", "--since-days", "0")
        self.assertRegex(out, r"comments\s+0 ")
        out = self.main("--dry-run", "--scope", "comments")
        self.assertRegex(out, rf"comments\s+{len(self.eligible_comments())} ")


class SpendCap(DbCase):
    def test_stops_before_the_cap(self):
        # The reservation for one 50-row batch of these comments:
        texts = [E.format_comment("Best pizza in Brooklyn?", f"Comment {i} about L'Industrie")
                 for i in range(50)]
        per_batch = sum(E.estimate_tokens(t) for t in texts) * E.RESERVE_FACTOR * E.PRICE_PER_TOKEN
        cap = per_batch * 2.5
        b = E.Budget(cap)
        with FakeOpenRouter() as api:
            stats = self.run_embed(scope="comments", budget=b, batch=50, workers=1)
        self.assertIn("BudgetExceeded", stats.stop)
        self.assertLessEqual(b.spent, cap)
        self.assertEqual(b.reserved, 0)
        stored = self.count("select count(*) from comment_embeddings")
        self.assertEqual(stored, len(api.inputs))       # everything paid for was kept
        self.assertGreater(stored, 0)
        self.assertLess(stored, len(self.eligible_comments()))

    def test_failed_attempts_count_toward_the_cap(self):
        b = E.Budget(1e-6)
        with FakeOpenRouter(lambda p: FakeResponse(502, None, "bad gateway")) as api:
            stats = self.run_embed(scope="comments", budget=b, batch=128, workers=1,
                                   attempts=50)
        self.assertIn("BudgetExceeded", stats.stop)
        self.assertLess(len(api.requests), 50)
        self.assertLessEqual(b.spent, b.cap)
        self.assertEqual(b.possibly_billed, len(api.requests))


class DryRun(DbCase):
    def test_no_call_no_write_on_a_read_only_connection(self):
        with FakeOpenRouter() as api:
            self.conn.set_session(readonly=True)
            totals = embed.dry_run(self.conn, embed.KINDS["both"], log=lambda *_: None)
            self.conn.set_session(readonly=False)
        self.assertEqual(api.requests, [])
        self.assertEqual(dict((s, n) for s, n, _, _ in totals),
                         {"comments": len(self.eligible_comments()), "threads": len(THREADS)})
        self.assertEqual(self.count("select count(*) from comment_embeddings"), 0)

    def test_counts_only_what_is_left(self):
        with FakeOpenRouter():
            self.run_embed(scope="comments", limit=100, batch=50)
        totals = embed.dry_run(self.conn, embed.KINDS["comments"], log=lambda *_: None)
        self.assertEqual(totals[0][1], len(self.eligible_comments()) - 100)

    def test_before_the_migration(self):
        with self.conn.cursor() as cur:
            cur.execute("drop table comment_embeddings, thread_embeddings, embedding_errors")
        self.conn.commit()
        totals = embed.dry_run(self.conn, embed.KINDS["both"], log=lambda *_: None)
        self.assertEqual(totals[0][1], len(self.eligible_comments()))


class Index(DbCase):
    def test_build_index_and_search_uses_it(self):
        with FakeOpenRouter():
            self.run_embed()
            q = E.embed_query("pizza")
        embed.build_index(self.conn, "64MB", log=lambda *_: None)
        embed.build_index(self.conn, "64MB", log=lambda *_: None)      # idempotent
        for kind in (embed.COMMENTS, embed.THREADS):
            self.assertTrue(self.count("""select i.indisvalid from pg_index i
                                          join pg_class c on c.oid = i.indexrelid
                                          where c.relname = %s""", embed.index_name(kind)))
        with self.conn.cursor() as cur:
            cur.execute("set hnsw.iterative_scan = relaxed_order")
            cur.execute("set enable_seqscan = off")
            cur.execute("""explain select comment_id from comment_embeddings
                           where model = %s
                           order by embedding <=> %s::halfvec(1024) limit 5""",
                        (E.MODEL_KEY, E.to_pgvector(q)))
            plan = "\n".join(r[0] for r in cur.fetchall())
            cur.execute("""select comment_id from comment_embeddings where model = %s
                           order by embedding <=> %s::halfvec(1024) limit 5""",
                        (E.MODEL_KEY, E.to_pgvector(q)))
            self.assertEqual(len(cur.fetchall()), 5)
        self.conn.rollback()
        self.assertIn(embed.index_name(embed.COMMENTS), plan)

    def test_index_names_fit(self):
        for kind in (embed.COMMENTS, embed.THREADS):
            self.assertLessEqual(len(embed.index_name(kind)), 63)
            self.assertTrue(embed.index_name(kind).startswith(
                f"{kind.table}_hnsw_qwen3_embedding_8b_1024"), embed.index_name(kind))

    def test_keys_that_differ_only_at_the_end_get_different_indexes(self):
        # The endpoint and quantization are the tail of the key; a plain
        # 63-byte cut would give both of these one name, and the second
        # build would be skipped as "already exists".
        names = set()
        for key in (E.MODEL_KEY, E.MODEL_KEY.replace(":unknown", ":bf16"),
                    E.MODEL_KEY.replace("deepinfra/us", "deepinfra/us-east")):
            with mock.patch.object(E, "MODEL_KEY", key):
                names.add(embed.index_name(embed.COMMENTS))
        self.assertEqual(len(names), 3)
        self.assertTrue(all(len(n) <= 63 for n in names))


class Schema(DbCase):
    def test_schema_sql_is_idempotent(self):
        import db
        db.init(self.conn, os.path.join(ROOT, "schema.sql"))
        self.assertEqual(self.count("select count(*) from threads"), len(THREADS))

    def test_migration_matches_schema_sql(self):
        def columns():
            with self.conn.cursor() as cur:
                cur.execute("""select a.attrelid::regclass::text, a.attname,
                                      format_type(a.atttypid, a.atttypmod), a.attnotnull,
                                      pg_get_expr(d.adbin, d.adrelid)
                               from pg_attribute a
                               left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
                               where a.attrelid::regclass::text in ('comment_embeddings',
                                     'thread_embeddings', 'embedding_errors')
                                 and a.attnum > 0 and not a.attisdropped
                               order by 1, 2""")
                cols = cur.fetchall()
                cur.execute("""select conrelid::regclass::text, pg_get_constraintdef(oid)
                               from pg_constraint
                               where conrelid::regclass::text in ('comment_embeddings',
                                     'thread_embeddings', 'embedding_errors')
                               order by 1, 2""")
                return cols, cur.fetchall()
        from_schema = columns()
        with self.conn.cursor() as cur:
            cur.execute("drop table comment_embeddings, thread_embeddings, embedding_errors")
            cur.execute("drop extension vector")
        self.conn.commit()
        with open(os.path.join(ROOT, "embed_schema.sql"), encoding="utf-8") as f:
            sql = f.read()
        with self.conn.cursor() as cur:
            cur.execute(sql)
        self.conn.commit()
        self.assertEqual(columns(), from_schema)
        self.assertEqual(len(from_schema[0]), 17)


class PollerStep(DbCase):
    def test_embed_once_covers_the_window_only(self):
        import poller
        with FakeOpenRouter() as api:
            n = poller.embed_once(self.conn, 3, 10_000, 0.05, "comments", 2)
        self.assertEqual(n, len(self.eligible_comments()) - 1)        # not t1_old
        self.assertFalse(any("Lucali" in t for t in api.inputs))
        self.assertTrue(all(r["timeout"] == poller.EMBED_TIMEOUT for r in api.requests))

    def test_embed_once_skips_without_tables(self):
        import poller
        with self.conn.cursor() as cur:
            cur.execute("drop table comment_embeddings, thread_embeddings, embedding_errors")
        self.conn.commit()
        with FakeOpenRouter() as api:
            self.assertEqual(poller.embed_once(self.conn, 3, 100, 0.05, "comments", 2), 0)
        self.assertEqual(api.requests, [])


if __name__ == "__main__":
    unittest.main()
