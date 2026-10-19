"""extract_v6 against a real, disposable Postgres. The API is tests/fake_anthropic.py.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55447/extracttest python -m pytest tests

Skipped without a URL. These tests DROP AND RECREATE the public schema of that
database; tests/pgtest.py has the guard that keeps them off anything but a
throwaway local server. No pgvector needed.
"""

import datetime as dt
import importlib.util
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

import psycopg2

from fakes import ROOT

import anthropic_v6 as AV
import db
import extract_v6 as X
import fake_anthropic as F
import pgtest
import prompt_v6
import refresh
import subreddits

URL = pgtest.URL
QUIET = lambda *a, **k: None  # noqa: E731


NOW = dt.datetime.now(dt.timezone.utc)
HOME = subreddits.HOME
THREADS = [
    # id, subreddit, title, selftext, author, created
    ("t3_a", HOME, "Best dumplings in Queens?", "Looking for spots like PlaceAlpha. " * 50, "op", NOW),
    ("t3_b", HOME, "Is PlaceGamma closed?", "[removed]", "[deleted]", NOW),
    ("t3_c", HOME, "PlacePost worth it?", None, "poster", NOW),
    ("t3_chi", "chicagofood", "PlaceChicago?", "deep dish", "x", NOW),
    ("t3_old", HOME, "Old thread", "from last year", "y", NOW - dt.timedelta(days=400)),
]
COMMENTS = [
    # id, thread, parent comment, author, body, created offset (min)
    ("t1_top", "t3_a", None, "alice", "PlaceAlpha is great", 1),
    ("t1_r1", "t3_a", "t1_top", "op", "> PlaceAlpha is great\n\nagree, PlaceBeta too", 2),
    ("t1_r2", "t3_a", "t1_r1", "alice", "keens", 3),
    ("t1_plus", "t3_a", "t1_top", "bob", "+1", 4),
    ("t1_del", "t3_a", None, "[deleted]", "[deleted]", 5),
    ("t1_rem", "t3_a", None, "carol", "[removed]", 6),
    ("t1_blank", "t3_a", None, "dan", "   ", 7),
    ("t1_ondel", "t3_a", "t1_del", "erin", "reply to deleted, PlaceDelta", 8),
    ("t1_orphan", "t3_a", "t1_missing", "fay", "PlaceEps orphan", 9),
    ("t1_chain", "t3_b", None, "gus", "Starbucks and PlaceZeta", 10),
    ("t1_chi", "t3_chi", None, "hal", "PlaceChicago is great", 11),
    ("t1_old", "t3_old", None, "ivy", "PlaceOld was fine", 12),
] + [(f"t1_d{i}", "t3_c", f"t1_d{i - 1}" if i > 1 else None, "op" if i % 3 == 0 else f"u{i}",
      f"level {i} talk about PlaceDeep{i} " + ("long " * 400 if i == 7 else ""), 20 + i) for i in range(1, 9)]
HOME_LIVE = {c[0] for c in COMMENTS if c[0] not in ("t1_del", "t1_rem", "t1_blank", "t1_chi")}


class DbCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not URL:
            raise unittest.SkipTest(pgtest.SKIP_REASON)
        pgtest.guard(URL)
        if URL == db.DATABASE_URL:
            raise SystemExit("the test database URL equals DATABASE_URL")

    def setUp(self):
        self.conn = pgtest.connect()
        pgtest.reset(self.conn)
        self.load()

    def tearDown(self):
        self.conn.close()

    def load(self):
        with self.conn.cursor() as cur:
            for tid, sub, title, selftext, author, created in THREADS:
                cur.execute("""insert into threads (id, subreddit, title, selftext, author, created_utc)
                               values (%s, %s, %s, %s, %s, %s)""", (tid, sub, title, selftext, author, created))
            for cid, tid, parent, author, body, off in COMMENTS:
                sub = next(t[1] for t in THREADS if t[0] == tid)
                created = next(t[5] for t in THREADS if t[0] == tid) + dt.timedelta(minutes=off)
                cur.execute("""insert into comments (id, subreddit, thread_id, parent_id, parent_comment_id,
                                 author, body, permalink, created_utc)
                               values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                            (cid, sub, tid, parent or tid, parent, author, body, f"/r/x/{cid}", created))
        self.conn.commit()
        db.fill_tree(self.conn, [t[0] for t in THREADS])

    def q(self, sql, params=()):
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        self.conn.commit()
        return rows

    def done_ids(self):
        return {r[0] for r in self.q("select item_id from extraction_state where extracted_at is not null")}


# ---------------------------------------------------------------- schema
class Schema(DbCase):
    def test_migration_on_a_pre_v6_database_keeps_old_rows(self):
        with open(os.path.join(ROOT, "schema.sql"), encoding="utf-8") as f:
            old = f.read().split("-- v6-extraction-schema:begin")[0]
        with self.conn.cursor() as cur:
            cur.execute("drop schema public cascade; create schema public")
            cur.execute(old)
        self.conn.commit()
        self.load()
        db.insert_mentions(self.conn, "t1_top", [{"restaurant_raw": "PlaceAlpha", "entity_key": "placealpha"}],
                           "old-model", "oldhash")
        self.assertEqual(self.q("select attnotnull from pg_attribute where attrelid = 'mentions'::regclass "
                                "and attname = 'comment_id'"), [(True,)])
        with open(os.path.join(ROOT, "extract_v6_schema.sql"), encoding="utf-8") as f:
            sql = f.read()
        for _ in range(2):
            with self.conn.cursor() as cur:
                cur.execute(sql)
            self.conn.commit()
        self.assertEqual(self.q("select attnotnull from pg_attribute where attrelid = 'mentions'::regclass "
                                "and attname = 'comment_id'"), [(False,)])
        self.assertEqual(self.q("select entity_key, schema_version from live_mentions"), [("placealpha", None)])
        self.assertEqual(self.q("select read_version from extraction_settings"), [("legacy",)])
        # And the boot schema on top of it changes nothing.
        db.init(self.conn, os.path.join(ROOT, "schema.sql"))
        self.assertEqual(self.q("select count(*) from mentions"), [(1,)])

    def test_source_check(self):
        with self.assertRaises(psycopg2.errors.CheckViolation):
            with self.conn.cursor() as cur:
                cur.execute("""insert into mentions (comment_id, thread_id, restaurant_raw, entity_key,
                               model_version, prompt_hash) values ('t1_top', 't3_a', 'x', 'x', 'm', 'h')""")
        self.conn.rollback()


# ---------------------------------------------------------------- rendering
class Rendering(DbCase):
    def oracle(self):
        spec = importlib.util.spec_from_file_location(
            "oracle_rows", os.path.join(ROOT, "tests", "oracle_v6", "build_comment_rows.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_rows_and_rendering_match_the_benchmark_builder(self):
        ids = sorted(c[0] for c in COMMENTS)
        mine = prompt_v6.fetch_comment_rows(self.conn, ids)
        theirs = self.oracle().fetch_rows(self.conn, ids)
        self.assertEqual(mine, theirs)
        for cid in ids:
            # build_user_message is the vendored benchmark function; the rows are what differ, if anything.
            self.assertEqual(prompt_v6.render("comment", mine[cid])[1], prompt_v6.build_user_message(theirs[cid]))

    def test_rendered_shapes(self):
        rows = prompt_v6.fetch_comment_rows(self.conn, ["t1_r2", "t1_ondel", "t1_orphan", "t1_d8"])
        r2 = prompt_v6.build_user_message(rows["t1_r2"])
        self.assertIn("[1] you, earlier: PlaceAlpha is great", r2)
        self.assertIn("[2] OP: > PlaceAlpha is great agree, PlaceBeta too", r2)
        self.assertIn("<comment_to_extract>\nkeens\n</comment_to_extract>", r2)
        self.assertIn("(a deleted comment)", prompt_v6.build_user_message(rows["t1_ondel"]))
        self.assertIn("(a comment that is not available)", prompt_v6.build_user_message(rows["t1_orphan"]))
        d8 = prompt_v6.build_user_message(rows["t1_d8"])
        self.assertIn("(2 earlier comments not shown)", d8)
        self.assertEqual(rows["t1_d8"]["ancestors_total"], 7)


# ---------------------------------------------------------------- candidates
class Candidates(DbCase):
    def test_home_only_short_included_gone_excluded(self):
        got = X.candidate_ids(self.conn, "comment")
        self.assertEqual(set(got), HOME_LIVE)
        self.assertIn("t1_r2", got)        # "keens"
        self.assertIn("t1_plus", got)      # "+1"
        self.assertEqual(set(X.candidate_ids(self.conn, "post")), {"t3_a", "t3_b", "t3_c", "t3_old"})

    def test_filters(self):
        since = NOW - dt.timedelta(days=30)
        self.assertNotIn("t1_old", X.candidate_ids(self.conn, "comment", since=since))
        self.assertNotIn("t3_old", X.candidate_ids(self.conn, "post", since=since))
        self.assertEqual(X.candidate_ids(self.conn, "comment", ids=["t1_r2", "t1_chi", "t1_del"]), ["t1_r2"])
        self.assertEqual(set(X.candidate_ids(self.conn, "comment", max_chars=5)), {"t1_r2", "t1_plus"})
        self.assertEqual(len(X.candidate_ids(self.conn, "comment", limit=3)), 3)

    def test_state_decides_what_is_due(self):
        it = X.Item("comment", "t1_r2", None, None, prompt_v6.PROMPT_HASH)
        X.record_failure(self.conn, it, "max_tokens")             # first failure: owed a retry
        self.assertIn("t1_r2", X.candidate_ids(self.conn, "comment"))
        X.record_failure(self.conn, it, "max_tokens: again")      # second: parked
        self.assertNotIn("t1_r2", X.candidate_ids(self.conn, "comment"))
        self.assertEqual(self.q("select extract_error, attempts from extraction_state"),
                         [("max_tokens: again", 2)])

    def test_old_extraction_does_not_hide_comments_from_v6(self):
        with self.conn.cursor() as cur:
            cur.execute("update comments set extracted_at = now(), extracted_with = 'old'")
        self.conn.commit()
        self.assertEqual(set(X.candidate_ids(self.conn, "comment")), HOME_LIVE)


# ---------------------------------------------------------------- writer
OUTPUT = {"mentions": [
    F.mention("PlaceAlpha", aspects={"taste": "superlative_praise", "value": "knock", "service": None,
                                     "atmosphere": "mixed", "wait": "extreme_knock"},
              overall="praise", experience="secondhand", price="cheap", tags=["sichuan", "date night"],
              dishes=[{"dish": "soup dumplings", "level": "praise", "avoid": False},
                      {"dish": "noodles", "level": None, "avoid": True}],
              notes=[{"about": "tip", "text": "go early"}], location="Flushing", avoid=True),
    F.mention("Placealpha"),                                        # same key: one row
    F.mention("Whole Foods", kind="grocery", opinion="none", overall=None, experience="none",
              aspects={"taste": None, "value": None, "service": None, "atmosphere": None, "wait": None}),
    F.mention("Starbucks", kind="cafe"),
    F.mention("PlaceClosed", status="closed", timeframe="past", tags=["closed"]),
    F.mention("  "),                                                # nothing to key
    F.mention("PlaceEndorse", opinion="endorse", overall="praise",
              aspects={"taste": None, "value": None, "service": None, "atmosphere": None, "wait": None}),
]}


class Writer(DbCase):
    def item(self, kind="comment", iid="t1_top"):
        return X.Item(kind, iid, None, None, prompt_v6.PROMPT_HASH if kind == "comment" else
                      prompt_v6.PROMPT_HASH_POST)

    def rows(self):
        with self.conn.cursor() as cur:
            cur.execute("select * from mentions order by id")
            cols = [d[0] for d in cur.description]
            out = [dict(zip(cols, r)) for r in cur.fetchall()]
        self.conn.commit()
        return {r["entity_key"]: r for r in out}

    def test_round_trip(self):
        n = X.store(self.conn, self.item(), OUTPUT, {"input_tokens": 1}, 0.001)
        self.assertEqual(n, 5)
        r = self.rows()
        self.assertEqual(set(r), {"placealpha", "whole foods", "starbucks", "placeclosed", "placeendorse"})
        a = r["placealpha"]
        self.assertEqual((a["comment_id"], a["thread_id"], a["restaurant_raw"]), ("t1_top", None, "PlaceAlpha"))
        self.assertEqual((a["schema_version"], a["model_version"], a["prompt_hash"]),
                         (6, "claude-haiku-5-5", "979dcd6b9267"))
        self.assertEqual(a["raw"], OUTPUT["mentions"][0])
        # v6 columns
        self.assertEqual((a["overall_level"], a["taste_level"], a["value_level"], a["service_level"],
                          a["atmosphere_level"], a["wait_level"]), (1, 2, -1, None, 0, -2))
        self.assertEqual((a["kind"], a["named_in"], a["experience"], a["opinion"], a["avoid"]),
                         ("restaurant", "comment", "secondhand", "stated", True))
        self.assertEqual(a["dish_opinions"], [{"dish": "soup dumplings", "level": 1, "avoid": False},
                                              {"dish": "noodles", "level": None, "avoid": True}])
        self.assertEqual(a["notes"], [{"about": "tip", "text": "go early"}])
        self.assertEqual(a["tags"], ["sichuan", "date night"])
        self.assertEqual((a["price_level"], a["timeframe"], a["trend"], a["status"], a["is_chain"]),
                         (-1, "current", None, None, False))
        # legacy columns, through the benchmark's adapter
        self.assertEqual(a["aspects"], {"food": 1.0, "value": -0.67, "service": None, "atmosphere": 0.0,
                                        "wait": -1.0})
        self.assertEqual((a["neighborhood_hint"], a["dishes"], a["descriptors"]),
                         ("Flushing", ["soup dumplings", "noodles"], ["sichuan", "date night"]))
        self.assertAlmostEqual(a["expensiveness"], -0.67, places=5)
        self.assertEqual((a["is_firsthand"], a["is_negated"]), (False, True))
        # kinds and chains are stored, flagged
        self.assertEqual(r["whole foods"]["kind"], "grocery")
        self.assertTrue(r["starbucks"]["is_chain"])
        c = r["placeclosed"]
        self.assertEqual(c["aspects"], dict.fromkeys(db.ASPECTS))
        self.assertEqual(c["descriptors"], ["closed"])
        self.assertEqual(r["placeendorse"]["aspects"]["food"], 0.33)
        # the whole answer is kept, the duplicate and the blank name included
        st = self.q("select output, usage, cost_usd, attempts, extract_error, prompt_hash, model "
                    "from extraction_state where item_id = 't1_top'")[0]
        self.assertEqual(st[0], OUTPUT)
        self.assertEqual((st[1], float(st[2]), st[3], st[4], st[5], st[6]),
                         ({"input_tokens": 1}, 0.001, 1, None, "979dcd6b9267", "claude-haiku-5-5"))

    def test_store_is_idempotent_and_leaves_old_rows(self):
        db.insert_mentions(self.conn, "t1_top", [{"restaurant_raw": "PlaceAlpha", "entity_key": "placealpha"}],
                           "deepseek", "oldhash")
        X.store(self.conn, self.item(), OUTPUT, {}, 0.0)
        X.store(self.conn, self.item(), OUTPUT, {}, 0.0)
        self.assertEqual(self.q("select count(*) from mentions where schema_version = 6"), [(5,)])
        self.assertEqual(self.q("select count(*) from mentions where prompt_hash = 'oldhash'"), [(1,)])

    def test_post_mentions_name_the_thread(self):
        X.store(self.conn, self.item("post", "t3_c"), {"mentions": [F.mention("PlacePost")]}, {}, 0.0)
        X.store(self.conn, self.item("post", "t3_c"), {"mentions": [F.mention("PlacePost")]}, {}, 0.0)
        self.assertEqual(self.q("select comment_id, thread_id, prompt_hash from mentions"),
                         [(None, "t3_c", "436d834d7edd")])

    def test_a_refused_row_parks_the_item_not_the_run(self):
        bad = {"mentions": [F.mention("PlaceBad", named_in="elsewhere")]}
        stats = X.Stats()
        X._handle(self.conn, self.item(), F.message(__import__("json").dumps(bad)), 0.0, stats, log=QUIET)
        X._handle(self.conn, self.item(), F.message(__import__("json").dumps(bad)), 0.0, stats, log=QUIET)
        self.assertEqual(stats.parked, 1)
        err = self.q("select extract_error from extraction_state")[0][0]
        self.assertTrue(err.startswith("store_error: CheckViolation"), err)
        self.assertEqual(self.q("select count(*) from mentions"), [(0,)])


# ---------------------------------------------------------------- the switch
class Switch(DbCase):
    def setUp(self):
        super().setUp()
        db.insert_mentions(self.conn, "t1_top", [{"restaurant_raw": "PlaceAlpha", "entity_key": "placealpha"}],
                           "deepseek", "oldhash")
        X.store(self.conn, X.Item("comment", "t1_top", None, None, prompt_v6.PROMPT_HASH), OUTPUT, {}, 0.0)
        X.store(self.conn, X.Item("post", "t3_c", None, None, prompt_v6.PROMPT_HASH_POST),
                {"mentions": [F.mention("PlacePost")]}, {}, 0.0)

    def live(self):
        return sorted((k, v) for k, v in self.q("select entity_key, schema_version from live_mentions"))

    def test_legacy_by_default_then_v6(self):
        self.assertEqual(self.live(), [("placealpha", None)])
        with redirect_stdout(io.StringIO()):
            X.set_read_version(self.conn, "v6", refresh_views=False)
        # restaurant kinds only, no chains.txt names, no post mentions (scoring can't place them yet)
        self.assertEqual(self.live(), [("placealpha", 6), ("placeclosed", 6), ("placeendorse", 6)])
        with redirect_stdout(io.StringIO()):
            X.set_read_version(self.conn, "legacy", refresh_views=False)
        self.assertEqual(self.live(), [("placealpha", None)])

    def test_scoring_reads_the_switch(self):
        with redirect_stdout(io.StringIO()):
            refresh.apply_sql(self.conn)
            refresh.refresh_views(self.conn)
        legacy_ids = {r[0] for r in self.q("select id from mentions where schema_version is null")}
        self.assertEqual({r[0] for r in self.q("select mention_id from mention_weights")}, legacy_ids)
        with redirect_stdout(io.StringIO()):
            X.set_read_version(self.conn, "v6")            # refreshes
        v6_ids = {r[0] for r in self.q("select id from live_mentions")}
        self.assertEqual(len(v6_ids), 3)
        self.assertEqual({r[0] for r in self.q("select mention_id from mention_weights")}, v6_ids)
        self.assertEqual({r[0] for r in self.q("select entity_key from entity_alias")},
                         {"placealpha", "placeclosed", "placeendorse"})

    def test_app_queries_read_live_mentions(self):
        import app.queries as Q
        from app.db import fetch_one
        with redirect_stdout(io.StringIO()):
            refresh.apply_sql(self.conn)
            refresh.refresh_views(self.conn)
        from psycopg2.extras import RealDictCursor  # noqa: F401  (fetch_one uses it)
        self.assertEqual(Q.stats(self.conn, fetch_one)["mentions"], 1)
        with redirect_stdout(io.StringIO()):
            X.set_read_version(self.conn, "v6")
        s = Q.stats(self.conn, fetch_one)
        self.assertEqual((s["mentions"], s["models"], s["extracted"]), (3, "claude-haiku-5-5", 1))


# ---------------------------------------------------------------- direct path
class Direct(DbCase):
    def run_direct(self, api, budget=10.0, **kw):
        stats = X.Stats()
        cl = AV.client("k", api.base_url)
        X.run_direct(self.conn, cl, X.Budget(budget), log=QUIET, stats=stats, **kw)
        return stats

    def test_extracts_home_comments_and_posts(self):
        with F.FakeAnthropic() as api:
            s = self.run_direct(api, workers=4)
        self.assertEqual(self.done_ids(), HOME_LIVE | {"t3_a", "t3_b", "t3_c", "t3_old"})
        self.assertEqual(s.done, len(HOME_LIVE) + 4)
        sent = {r["messages"][0]["content"] for r in api.requests}
        self.assertFalse(any("PlaceChicago" in u for u in sent))
        rows = prompt_v6.fetch_comment_rows(self.conn, ["t1_r2"])
        self.assertIn(prompt_v6.build_user_message(rows["t1_r2"]), sent)
        posts = [r for r in api.requests if r["system"][0]["text"] == prompt_v6.SYSTEM_PROMPT_POST]
        self.assertEqual(len(posts), 4)
        self.assertTrue(all(r == AV.params(r["system"][0]["text"], r["messages"][0]["content"])
                            for r in api.requests))
        self.assertGreater(s.cost, 0)
        # t1_r1 quotes PlaceAlpha and names PlaceBeta; the quote is marked, so
        # the fake (which only reads bare words) sees PlaceBeta alone.
        self.assertEqual(self.q("select restaurant_raw from mentions where comment_id = 't1_r1'"),
                         [("PlaceBeta",)])
        self.assertEqual(self.q("select count(*) from mentions where thread_id = 't3_c'"), [(1,)])
        # nothing left; a second pass sends nothing
        with F.FakeAnthropic() as api2:
            self.run_direct(api2)
        self.assertEqual(api2.requests, [])

    def test_item_errors_retry_once_then_park(self):
        def answer(p):
            u = F.user_text(p)
            if "keens" in u:
                return 200, F.message('{"mentions": [', stop="max_tokens")
            if "+1" in u:
                return 200, dict(F.message(None, stop="refusal"), stop_details={"category": "bio"})
            if "PlaceEps" in u:
                return 200, F.message("garbage")
            return F.default_answer(p)
        with F.FakeAnthropic(answer) as api:
            s1 = self.run_direct(api, kinds=("comment",))
            self.assertEqual((s1.failed, s1.parked), (3, 0))
            s2 = self.run_direct(api, kinds=("comment",))
        self.assertEqual((s2.failed, s2.parked, s2.done), (3, 3, 0))
        errs = dict(self.q("select item_id, split_part(extract_error, ':', 1) from extraction_state "
                           "where extract_error is not null"))
        self.assertEqual(errs, {"t1_r2": "max_tokens", "t1_plus": "refusal", "t1_orphan": "invalid_json"})
        # billed failures still count toward spend
        self.assertGreater(float(self.q("select cost_usd from extraction_state where item_id='t1_r2'")[0][0]), 0)

    def test_400_stops_the_pass_and_marks_nothing(self):
        with F.FakeAnthropic(lambda p: F.error(400, "invalid_request_error", "bad param")) as api:
            with self.assertRaises(AV.FatalAPIError) as cm:
                self.run_direct(api, workers=1)
        self.assertIn("bad param", str(cm.exception))
        self.assertEqual(len(api.requests), 1)
        self.assertEqual(self.q("select count(*) from extraction_state"), [(0,)])

    def test_400_midway_keeps_what_was_stored(self):
        def answer(p):
            return F.error(401, "authentication_error") if "PlaceEps" in F.user_text(p) else F.default_answer(p)
        with F.FakeAnthropic(answer) as api:
            with self.assertRaises(AV.FatalAPIError):
                self.run_direct(api, workers=1, kinds=("comment",))
        done = self.done_ids()
        self.assertTrue(done)
        self.assertNotIn("t1_orphan", done)
        self.assertEqual(self.q("select count(*) from extraction_state where extract_error is not null"), [(0,)])

    def test_outage_stops_without_marking(self):
        with F.FakeAnthropic(lambda p: F.error(529, "overloaded_error")) as api:
            with mock.patch.object(AV, "ATTEMPTS", 2), mock.patch("time.sleep"):
                with self.assertRaises(AV.TransientAPIError):
                    self.run_direct(api, workers=1)
        self.assertEqual(self.q("select count(*) from extraction_state"), [(0,)])

    def test_cap_holds_worst_case_before_sending(self):
        it = X.render_items(self.conn, "comment", ["t1_top"])[0]
        w = it.worst(batch=False)
        with F.FakeAnthropic() as api:
            s = self.run_direct(api, budget=w * 0.9, workers=1, kinds=("comment",))
        self.assertEqual((len(api.requests), s.done), (0, 0))      # not even one worst case fits
        self.assertGreater(s.refused, 0)

        # Each answer costs 0.6 of a worst case: the first fits under 1.5, the
        # second's worst case would not (0.6 + 1.0 > 1.5), so it is never sent.
        out = int(0.6 * w / AV.PRICES["out"])
        with F.FakeAnthropic(lambda p: (200, F.message('{"mentions": []}', usage={"output_tokens": out,
                                                                                 "input_tokens": 0}))) as api:
            s = self.run_direct(api, budget=w * 1.5, workers=1, kinds=("comment",))
        self.assertEqual((len(api.requests), s.done), (1, 1))
        self.assertLessEqual(s.cost, w * 1.5)


# ---------------------------------------------------------------- batches
class Batches(DbCase):
    def run_batch(self, api, budget=10.0, **kw):
        stats = X.Stats()
        cl = AV.client("k", api.base_url)
        kw.setdefault("poll_seconds", 0)
        X.run_batch(self.conn, cl, X.Budget(budget), log=QUIET, sleep=lambda s: None, stats=stats, **kw)
        return stats

    def test_backfill_in_sub_batches(self):
        with F.FakeAnthropic(polls_until_ended=1) as api:
            s = self.run_batch(api, batch_size=5, max_inflight=2)
        self.assertEqual(self.done_ids(), HOME_LIVE | {"t3_a", "t3_b", "t3_c", "t3_old"})
        self.assertEqual(len(api.batch_requests), len(HOME_LIVE) + 4)
        self.assertTrue(all(r["params"] == AV.params(r["params"]["system"][0]["text"],
                                                     r["params"]["messages"][0]["content"])
                            for r in api.batch_requests))
        self.assertEqual({r["custom_id"] for r in api.batch_requests}, self.done_ids())
        b = self.q("select count(*), count(*) filter (where status = 'collected'), sum(cost_usd) from extract_batches")
        self.assertEqual(b[0][:2], (4, 4))
        self.assertAlmostEqual(float(b[0][2]), s.cost, places=6)
        # batch price is half the direct price
        self.assertAlmostEqual(s.cost, AV.cost(F.USAGE, True) * s.done, places=6)

    def test_sub_batches_are_sized_to_the_cap(self):
        it = X.render_items(self.conn, "comment", ["t1_top"])[0]
        w = it.worst(batch=True)
        with F.FakeAnthropic() as api:
            s = self.run_batch(api, budget=w * 3.5, batch_size=100)
        sizes = [n for (n,) in self.q("select requests from extract_batches order by created_at")]
        self.assertTrue(all(n <= 3 for n in sizes), sizes)
        self.assertEqual(s.refused, 0)            # holds come back as small actual costs
        self.assertEqual(len(self.done_ids()), len(HOME_LIVE) + 4)

    def test_reattaches_instead_of_resubmitting(self):
        real = X._collect
        calls = []

        def interrupted(*a, **k):
            calls.append(1)
            if len(calls) == 1:
                raise KeyboardInterrupt
            return real(*a, **k)
        with F.FakeAnthropic(polls_until_ended=0) as api:
            with mock.patch.object(X, "_collect", interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    self.run_batch(api, kinds=("comment",))
            self.assertEqual(self.q("select status from extract_batches"), [("submitted",)])
            self.assertEqual(self.done_ids(), set())
            sent = len(api.batch_requests)
            # in flight: not due, so a run that only looks for work finds none
            self.assertEqual(X.candidate_ids(self.conn, "comment"), [])
            with mock.patch.object(X, "_collect", interrupted):
                self.run_batch(api, kinds=("comment",))
        self.assertEqual(len(api.batch_requests), sent)        # nothing resubmitted
        self.assertEqual(self.done_ids(), HOME_LIVE)
        self.assertEqual(self.q("select status from extract_batches"), [("collected",)])

    def test_errored_and_expired_retry_once(self):
        seen = {}

        def results(cid, params):
            seen[cid] = seen.get(cid, 0) + 1
            if cid == "t1_r2" and seen[cid] == 1:
                return {"type": "expired"}
            if cid == "t1_plus":
                return {"type": "errored", "error": {"type": "error",
                                                     "error": {"type": "api_error", "message": "boom"}}}
            st, msg = F.default_answer(params)
            return {"type": "succeeded", "message": msg}
        with F.FakeAnthropic(batch_results=results) as api:
            s = self.run_batch(api, kinds=("comment",))
        self.assertEqual(seen["t1_r2"], 2)
        self.assertEqual(seen["t1_plus"], 2)
        self.assertIn("t1_r2", self.done_ids())
        self.assertEqual(self.q("select extract_error from extraction_state where item_id = 't1_plus'"),
                         [("batch_errored: api_error: boom",)])
        self.assertEqual(s.parked, 1)

    def test_invalid_request_in_a_batch_is_fatal_and_unmarked(self):
        def results(cid, params):
            if cid == "t1_r2":
                return {"type": "errored", "error": {"type": "error", "error": {
                    "type": "invalid_request_error", "message": "schema too complex"}}}
            return {"type": "succeeded", "message": F.default_answer(params)[1]}
        with F.FakeAnthropic(batch_results=results) as api:
            with self.assertRaises(AV.FatalAPIError) as cm:
                self.run_batch(api, kinds=("comment",))
        self.assertIn("schema too complex", str(cm.exception))
        self.assertEqual(self.done_ids(), HOME_LIVE - {"t1_r2"})
        self.assertEqual(self.q("select batch_id, extract_error, attempts from extraction_state "
                                "where item_id = 't1_r2'"), [(None, None, 0)])
        self.assertIn("t1_r2", X.candidate_ids(self.conn, "comment"))

    def test_submit_400_is_fatal_and_undone(self):
        with F.FakeAnthropic() as api:
            api.submit_status = F.error(400, "invalid_request_error", "too big")
            with self.assertRaises(AV.FatalAPIError):
                self.run_batch(api)
        self.assertEqual(self.q("select count(*) from extract_batches"), [(0,)])
        self.assertEqual(self.q("select count(*) from extraction_state where batch_id is not null"), [(0,)])

    def test_pending_row_stops_the_run_until_resolved(self):
        with self.conn.cursor() as cur:
            cur.execute("insert into extract_batches (id, version, requests, hold_usd) "
                        "values ('pending-1', 'v6', 1, 0.01)")
            cur.execute("insert into extraction_state (item_id, version, kind, batch_id) "
                        "values ('t1_r2', 'v6', 'comment', 'pending-1')")
        self.conn.commit()
        with F.FakeAnthropic() as api:
            with self.assertRaises(SystemExit):
                self.run_batch(api)
            self.assertEqual(api.batch_requests, [])
            X.resolve_pending(self.conn, "pending-1", "none")
            self.run_batch(api, kinds=("comment",))
        self.assertIn("t1_r2", self.done_ids())


# ---------------------------------------------------------------- dry run, cli, poller
class DryRunAndCli(DbCase):
    def test_dry_run_reads_only(self):
        out = io.StringIO()
        with F.FakeAnthropic() as api:
            totals = X.dry_run(self.conn, log=lambda *a: print(*a, file=out))
        self.assertEqual(api.requests, [])
        self.assertEqual(totals["comment"]["n"], len(HOME_LIVE))
        self.assertEqual(totals["post"]["n"], 4)
        self.assertGreater(totals["comment"]["worst"], totals["comment"]["fresh"])
        self.assertGreater(totals["comment"]["fresh"], totals["comment"]["cached"])
        self.assertEqual(self.q("select count(*) from extraction_state"), [(0,)])
        self.assertIn("per 1,000", out.getvalue())
        # the connection is writable again afterwards
        self.assertFalse(self.conn.readonly)

    def test_main_needs_a_cap_and_the_key(self):
        with mock.patch.object(db, "DATABASE_URL", URL), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EXTRACT_ANTHROPIC_API_KEY", None)
            with self.assertRaises(SystemExit) as cm:
                X.main(["--batch"])
            self.assertIn("--max-usd", str(cm.exception))
            with self.assertRaises(SystemExit) as cm:
                X.main(["--max-usd", "1"])
            self.assertIn("EXTRACT_ANTHROPIC_API_KEY", str(cm.exception))
            with redirect_stdout(io.StringIO()) as out:
                X.main(["--dry-run", "--scope", "comments", "--max-chars", "5"])
                X.main(["--status"])
        self.assertIn("comments: 2,", out.getvalue())
        self.assertIn("board reads: legacy", out.getvalue())

    def test_main_runs_and_retries_errors(self):
        def answer(p):
            if "keens" in F.user_text(p):
                return 200, F.message("{", stop="max_tokens")
            return F.default_answer(p)
        with F.FakeAnthropic(answer) as api:
            real = AV.client
            env = {"EXTRACT_ANTHROPIC_API_KEY": "k"}
            with mock.patch.object(db, "DATABASE_URL", URL), mock.patch.dict(os.environ, env), \
                    mock.patch.object(AV, "client", lambda key: real(key, api.base_url)), \
                    redirect_stdout(io.StringIO()) as out:
                self.assertEqual(X.main(["--max-usd", "1", "--scope", "comments", "--workers", "2"]), 0)
                X.main(["--max-usd", "1", "--scope", "comments"])
                self.assertNotIn("t1_r2", self.done_ids())
                api.answer = F.default_answer
                X.main(["--max-usd", "1", "--scope", "comments", "--retry-errors"])
        self.assertIn("t1_r2", self.done_ids())
        self.assertIn("cleared 1 error(s)", out.getvalue())

    def test_extract_py_forwards_v6(self):
        import extract
        with mock.patch.object(db, "DATABASE_URL", URL), mock.patch("sys.argv", ["extract.py", "--v6", "--status"]), \
                redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit) as cm:
                extract.main()
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("board reads: legacy", out.getvalue())


class Poller(DbCase):
    def test_extract_v6_once(self):
        import poller
        with F.FakeAnthropic() as api:
            real = AV.client
            with mock.patch.object(AV, "client", lambda key: real(key, api.base_url)), \
                    mock.patch.dict(os.environ, {"EXTRACT_ANTHROPIC_API_KEY": "k"}), \
                    redirect_stdout(io.StringIO()) as out:
                n = poller.extract_v6_once(self.conn, 3, 1000, 2, 1.0)
        # the 3-day window leaves out last year's thread and comment
        self.assertEqual(self.done_ids(), (HOME_LIVE - {"t1_old"}) | {"t3_a", "t3_b", "t3_c"})
        self.assertEqual(n, len(self.done_ids()))
        self.assertIn("extract v6:", out.getvalue())

    def test_extract_v6_once_fails_loud_on_4xx(self):
        import poller
        with F.FakeAnthropic(lambda p: F.error(403, "permission_error", "key revoked")) as api:
            real = AV.client
            with mock.patch.object(AV, "client", lambda key: real(key, api.base_url)), \
                    mock.patch.dict(os.environ, {"EXTRACT_ANTHROPIC_API_KEY": "k"}), \
                    redirect_stdout(io.StringIO()) as out:
                n = poller.extract_v6_once(self.conn, 3, 1000, 1, 1.0)
        self.assertEqual(n, 0)
        self.assertIn("EXTRACTION STOPPED", out.getvalue())
        self.assertIn("key revoked", out.getvalue())
        self.assertEqual(self.q("select count(*) from extraction_state"), [(0,)])


if __name__ == "__main__":
    unittest.main()
