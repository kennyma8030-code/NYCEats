"""The v6 extraction audit's findings, one or more tests each, on a disposable Postgres.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55447/extracttest python -m pytest tests

Same fixture as test_extract_v6_db.py (its DbCase), same fake Anthropic
server; skipped without a URL.
"""

import datetime as dt
import io
import os
import time
from contextlib import redirect_stdout
from unittest import mock

import psycopg2
import psycopg2.extensions

from fakes import ROOT

import anthropic_v6 as AV
import db
import extract_v6 as X
import fake_anthropic as F
import pgtest
import prompt_v6
from test_extract_v6_db import HOME_LIVE, OUTPUT, QUIET, URL, DbCase

POSTS = {"t3_a", "t3_b", "t3_c", "t3_old"}


class Counting(psycopg2.extensions.connection):
    """A connection that counts what goes over the wire: statements, and
    transactions (psycopg2 sends a BEGIN before the first statement of each,
    and the COMMIT is one more round trip)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.statements = 0
        self.commits = 0
        conn = self

        class Cur(psycopg2.extensions.cursor):
            def execute(self, sql, args=None):
                conn.statements += 1
                return super().execute(sql, args)

        self.cursor_factory = Cur

    def commit(self):
        self.commits += 1
        return super().commit()

    def round_trips(self):
        return self.statements + 2 * self.commits

    def zero(self):
        self.statements = self.commits = 0


def batch(conn, api, budget=10.0, **kw):
    stats = X.Stats()
    X.run_batch(conn, AV.client("k", api.base_url), X.Budget(budget), log=QUIET, sleep=lambda s: None,
                poll_seconds=0, stats=stats, **kw)
    return stats


# ---------------------------------------------------------------- 1. round trips
class RoundTrips(DbCase):
    """The backfill runs from a laptop, ~325 ms from production per round
    trip, so the number of statements per item is what sets its speed."""

    def setUp(self):
        super().setUp()
        self.conn.close()
        self.conn = psycopg2.connect(URL, connection_factory=Counting)

    def test_submit_is_two_statements_whatever_the_batch_size(self):
        items = X.render_items(self.conn, "comment", sorted(HOME_LIVE))
        with F.FakeAnthropic() as api:
            self.conn.zero()
            X._submit(self.conn, AV.client("k", api.base_url), X.Budget(10), items, QUIET)
        # the ledger row with every state row; then the real id on both
        self.assertEqual((self.conn.statements, self.conn.commits), (2, 2))
        self.assertEqual(self.q("select count(*) from extraction_state where batch_id like 'msgbatch_%%'"),
                         [(len(items),)])

    def test_collect_writes_a_chunk_in_a_few_statements(self):
        items = X.render_items(self.conn, "comment", sorted(HOME_LIVE))

        def results(cid, params):
            if cid == "t1_r2":
                return {"type": "expired"}
            return {"type": "succeeded", "message": F.default_answer(params)[1]}
        with F.FakeAnthropic(batch_results=results) as api, mock.patch.object(X, "WRITE_CHUNK", 5):
            cl = AV.client("k", api.base_url)
            bid = X._submit(self.conn, cl, X.Budget(10), items, QUIET)
            stats = X.Stats()
            self.conn.zero()
            retry = X._collect(self.conn, cl, X.Budget(10), bid, stats, QUIET)
        chunks = -(-len(items) // 5)
        # members; per chunk at most: previous attempts, mention rows, done
        # rows, failed rows; the ledger update. However many mentions.
        self.assertLessEqual(self.conn.statements, 1 + 4 * chunks + 1)
        self.assertEqual(self.conn.commits, 1 + chunks + 1)
        self.assertEqual(retry, [("comment", "t1_r2")])
        self.assertEqual(stats.done, len(items) - 1)
        self.assertEqual(self.q("select count(*) from extraction_state where extracted_at is not null"),
                         [(len(items) - 1,)])
        # one row per (comment, key), and every mention made it
        self.assertEqual(self.q("select count(*) from mentions"), [(stats.mentions,)])
        self.assertGreater(stats.mentions, 10)

    def test_batched_writes_match_the_per_item_writer(self):
        # Two items in one write(): both stored, attempts and cost carried over.
        a = X.Item("comment", "t1_top", None, None, prompt_v6.PROMPT_HASH)
        b = X.Item("comment", "t1_r2", None, None, prompt_v6.PROMPT_HASH)
        X.record_failure(self.conn, a, "max_tokens", {"output_tokens": 1}, 0.25)
        n, parked = X.write(self.conn, [X.Done(a, OUTPUT, {"input_tokens": 1}, 0.5),
                                        X.Failed(b, "refusal: x", None, 0.125)])
        self.assertEqual((n, parked), (5, set()))
        self.assertEqual(self.q("select item_id, attempts, cost_usd::float, extract_error, extracted_at is not null "
                                "from extraction_state order by item_id"),
                         [("t1_r2", 1, 0.125, None, False), ("t1_top", 2, 0.75, None, True)])
        n, parked = X.write(self.conn, [X.Failed(b, "refusal: again")])
        self.assertEqual(parked, {"t1_r2"})

    def test_a_refused_row_in_a_chunk_parks_only_its_item(self):
        bad = X.Item("comment", "t1_top", None, None, prompt_v6.PROMPT_HASH)
        good = X.Item("comment", "t1_r2", None, None, prompt_v6.PROMPT_HASH)
        entries = [X.Done(bad, {"mentions": [F.mention("PlaceBad", named_in="elsewhere")]}, {}, 0.0),
                   X.Done(good, {"mentions": [F.mention("PlaceGood")]}, {}, 0.0)]
        stats = X.Stats()
        X._write_counted(self.conn, entries, stats, QUIET)
        self.assertEqual((stats.done, stats.failed, stats.parked), (1, 1, 0))
        self.assertEqual(self.q("select entity_key from mentions"), [("placegood",)])
        self.assertEqual(self.q("select split_part(extract_error, ':', 1), attempts from extraction_state "
                                "where item_id = 't1_top'"), [(None, 1)])


# ---------------------------------------------------------------- 2. boot locks
class BootTakesNoLock(DbCase):
    def apply(self, path):
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            sql = f.read()
        t = time.monotonic()
        with self.conn.cursor() as cur:
            cur.execute(sql)
        self.conn.commit()
        return time.monotonic() - t

    def test_boot_behind_an_open_write_to_extraction_state(self):
        # A run's write to extraction_state, still open: a ROW EXCLUSIVE lock,
        # which CREATE INDEX IF NOT EXISTS (SHARE) would queue behind.
        other = pgtest.connect()
        write = "insert into extraction_state (item_id, version, kind) values ('t1_top', 'v6', 'comment')"
        try:
            with other.cursor() as cur:
                cur.execute(write)
                cur.execute("select count(*) from live_mentions")          # and board reads in flight
                cur.execute("select count(*) from comments")
            self.assertLess(self.apply("extract_v6_schema.sql"), 2.0)
            # The whole boot schema, behind the write alone (the older part of
            # schema.sql ALTERs comments, which any open read would hold up).
            other.rollback()
            with other.cursor() as cur:
                cur.execute(write)
            t = time.monotonic()
            db.init(self.conn, os.path.join(ROOT, "schema.sql"))
            self.assertLess(time.monotonic() - t, 4.0)
        finally:
            other.rollback()
            other.close()

    def test_the_first_seen_index_is_skipped_on_a_lock_timeout(self):
        # It is an optimisation: behind a long write to comments, the boot
        # goes on without it, and a later boot builds it.
        with self.conn.cursor() as cur:
            cur.execute("drop index comments_first_seen_idx")
        self.conn.commit()
        other = pgtest.connect()
        try:
            with other.cursor() as cur:
                cur.execute("update comments set score = 1 where id = 't1_top'")
            self.apply("extract_v6_schema.sql")
            self.assertEqual(self.q("select to_regclass('comments_first_seen_idx') is null"), [(True,)])
        finally:
            other.rollback()
            other.close()
        self.apply("extract_v6_schema.sql")
        self.assertEqual(self.q("select to_regclass('comments_first_seen_idx') is null"), [(False,)])

    def test_first_view_is_upgraded_once(self):
        old = """create or replace view live_mentions as select m.* from mentions m
                 where case (select read_version from extraction_settings)
                         when 'v6' then m.schema_version = 6 and m.comment_id is not null
                         else m.schema_version is null end"""
        with self.conn.cursor() as cur:
            cur.execute(old)
        self.conn.commit()
        self.apply("extract_v6_schema.sql")
        self.assertIn("extraction_state", self.q("select pg_get_viewdef('live_mentions'::regclass)")[0][0])
        # and from then on it is left alone, even with a reader holding the view
        other = pgtest.connect()
        try:
            with other.cursor() as cur:
                cur.execute("select count(*) from live_mentions")
            self.assertLess(self.apply("extract_v6_schema.sql"), 2.0)
        finally:
            other.rollback()
            other.close()


# ---------------------------------------------------------------- 3. pending rows
class PendingSettles(DbCase):
    def ambiguous(self, api):
        api.accept_then_fail = F.error(503, "api_error")
        with self.assertRaises(AV.AmbiguousSubmit):
            batch(self.conn, api, kinds=("comment",))
        pid = self.q("select id from extract_batches")[0][0]
        api.forgotten.update(api.batches)
        api.batches.clear()                    # the API made nothing after all
        return pid

    def age(self, pid, minutes):
        with self.conn.cursor() as cur:
            cur.execute("update extract_batches set created_at = now() - make_interval(mins => %s) where id = %s",
                        (minutes, pid))
        self.conn.commit()

    def test_no_match_after_half_an_hour_is_none(self):
        with F.FakeAnthropic() as api:
            pid = self.ambiguous(api)
            self.age(pid, 31)
            batch(self.conn, api, kinds=("comment",))
        self.assertEqual(self.done_ids(), HOME_LIVE)
        self.assertEqual(self.q("select count(*) from extract_batches where id = %s", (pid,)), [(0,)])

    def test_too_soon_or_not_covered_still_stops(self):
        with F.FakeAnthropic() as api:
            pid = self.ambiguous(api)
            self.age(pid, 20)
            with self.assertRaises(SystemExit):
                batch(self.conn, api, kinds=("comment",))
            self.age(pid, 31)
            with mock.patch.object(AV, "recent_batches", lambda cl, until=None: ([], False)), \
                    self.assertRaises(SystemExit):
                batch(self.conn, api, kinds=("comment",))
            self.assertEqual(api.batch_requests[len(HOME_LIVE):], [])      # nothing sent again
        self.assertEqual(self.q("select status from extract_batches where id = %s", (pid,)), [("pending",)])

    def test_a_slow_upload_landing_after_the_window_is_not_none(self):
        # The API did make the batch, but its upload took so long that it was
        # created after MATCH_AFTER: not adopted blindly, and never called none.
        with F.FakeAnthropic() as api:
            api.accept_then_fail = F.error(503, "api_error")
            with self.assertRaises(AV.AmbiguousSubmit):
                batch(self.conn, api, kinds=("comment",))
            pid = self.q("select id from extract_batches")[0][0]
            self.age(pid, 60)
            with self.assertRaises(SystemExit):
                batch(self.conn, api, kinds=("comment",))
            self.assertEqual(len(api.batch_requests), len(HOME_LIVE))       # nothing sent again
        self.assertEqual(self.q("select status from extract_batches where id = %s", (pid,)), [("pending",)])
        self.assertEqual(X.candidate_ids(self.conn, "comment"), [])

    def test_an_outage_while_polling_is_ridden_out(self):
        with F.FakeAnthropic(polls_until_ended=1) as api:
            real = AV.retrieve
            calls = []

            def flaky(cl, bid, sleep=None, log=print):
                calls.append(1)
                if len(calls) <= 2:
                    api.get_failures = [F.error(529, "overloaded_error"), F.error(502, "api_error")]
                return real(cl, bid, sleep=sleep, log=log)
            with mock.patch.object(AV, "retrieve", flaky):
                api.truncate_results = 1
                batch(self.conn, api, kinds=("comment",))
        self.assertEqual(self.done_ids(), HOME_LIVE)


# ---------------------------------------------------------------- 4. late arrivals
class LateArrivals(DbCase):
    def poll(self, env=None):
        import poller
        real = AV.client
        with F.FakeAnthropic() as api, mock.patch.object(AV, "client", lambda key: real(key, api.base_url)), \
                mock.patch.dict(os.environ, {"EXTRACT_ANTHROPIC_API_KEY": "k", **(env or {})}), \
                redirect_stdout(io.StringIO()) as out:
            poller.extract_v6_once(self.conn, 3, 1000, 2, 1.0)
        return out.getvalue()

    def test_the_poller_window_is_on_first_seen(self):
        # A comment written five days ago reached the database just now (a
        # re-read thread): new to v6, and recent enough for the poller.
        with self.conn.cursor() as cur:
            cur.execute("update comments set created_utc = now() - interval '5 days', first_seen_at = now() "
                        "where id = 't1_old'")
            # and a recent comment first seen long ago is not in the window
            cur.execute("update comments set first_seen_at = now() - interval '10 days' where id = 't1_top'")
        self.conn.commit()
        self.poll()
        done = self.done_ids()
        self.assertIn("t1_old", done)
        self.assertNotIn("t1_top", done)

    def test_bulk_inserts_of_old_items_are_left_for_a_batch(self):
        # Last year's post and comment arrive now, as a backfill (or the
        # poller's own boot gap-fill) would insert them: the direct path,
        # at twice the batch price, leaves them and says so.
        with self.conn.cursor() as cur:
            cur.execute("update comments set first_seen_at = now() where id = 't1_old'")
            cur.execute("update threads set first_seen_at = now() where id = 't3_old'")
        self.conn.commit()
        out = self.poll()
        done = self.done_ids()
        self.assertNotIn("t1_old", done)
        self.assertNotIn("t3_old", done)
        self.assertIn("t1_top", done)
        self.assertIn("left 2 item(s)", out)
        self.assertIn("t1_old", X.candidate_ids(self.conn, "comment"))     # the batch catch-up takes them
        # The bound is $POLL_EXTRACT_V6_MAX_AGE_DAYS.
        self.poll({"POLL_EXTRACT_V6_MAX_AGE_DAYS": "500"})
        self.assertIn("t1_old", self.done_ids())

    def test_catch_up_without_since_takes_late_arrivals(self):
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
        self.assertNotIn("t1_old", X.candidate_ids(self.conn, "comment", since=since))
        self.assertIn("t1_old", X.candidate_ids(self.conn, "comment"))
        self.assertNotIn("t1_old", X.candidate_ids(self.conn, "comment", seen_since=since))
        with self.conn.cursor() as cur:
            cur.execute("update comments set first_seen_at = now() where id = 't1_old'")
        self.conn.commit()
        self.assertIn("t1_old", X.candidate_ids(self.conn, "comment", seen_since=since))


# ---------------------------------------------------------------- 5. reset a prompt hash
OLD = "0ldv6hash000"


class ResetHash(DbCase):
    def setUp(self):
        super().setUp()
        db.insert_mentions(self.conn, "t1_top", [{"restaurant_raw": "PlaceAlpha", "entity_key": "placealpha"}],
                           "deepseek", "oldhash")
        for iid in ("t1_top", "t1_r1"):
            X.store(self.conn, X.Item("comment", iid, None, None, OLD), OUTPUT, {}, 0.0)
        X.store(self.conn, X.Item("comment", "t1_r2", None, None, prompt_v6.PROMPT_HASH),
                {"mentions": [F.mention("PlaceNew")]}, {}, 0.0)
        X.store(self.conn, X.Item("post", "t3_c", None, None, OLD), {"mentions": [F.mention("PlacePost")]}, {}, 0.0)

    def counts(self):
        return self.q("""select prompt_hash, count(*) from mentions group by 1 order by 1""")

    def test_counts_without_yes_then_deletes_in_chunks(self):
        before = self.counts()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(X.reset_hash(self.conn, OLD, log=QUIET), (3, 11))
        self.assertEqual(self.counts(), before)
        X.reset_hash(self.conn, OLD, ("comment",), yes=True, chunk=1, log=QUIET)
        self.assertEqual(self.counts(), [(OLD, 1), (prompt_v6.PROMPT_HASH, 1), ("oldhash", 1)])  # the post's
        self.assertIn("t1_top", X.candidate_ids(self.conn, "comment"))
        self.assertNotIn("t1_r2", X.candidate_ids(self.conn, "comment"))
        X.reset_hash(self.conn, OLD, yes=True, log=QUIET)
        self.assertEqual(self.counts(), [(prompt_v6.PROMPT_HASH, 1), ("oldhash", 1)])
        self.assertEqual(self.q("select item_id from extraction_state"), [("t1_r2",)])

    def test_refuses_while_a_batch_holds_items_of_that_hash(self):
        with self.conn.cursor() as cur:
            cur.execute("update extraction_state set extracted_at = null, batch_id = 'msgbatch_x' "
                        "where item_id = 't1_r1'")
        self.conn.commit()
        with self.assertRaises(SystemExit) as cm:
            X.reset_hash(self.conn, OLD, yes=True, log=QUIET)
        self.assertIn("in a batch", str(cm.exception))
        self.assertEqual(self.q("select count(*) from mentions where prompt_hash = %s", (OLD,)), [(11,)])

    def test_cli(self):
        with mock.patch.object(db, "DATABASE_URL", URL), redirect_stdout(io.StringIO()) as out:
            X.main(["--reset-hash", OLD, "--scope", "posts"])
            X.main(["--reset-hash", OLD, "--scope", "posts", "--yes"])
        self.assertIn("re-run with --yes", out.getvalue())
        self.assertEqual(self.q("select count(*) from mentions where thread_id is not null"), [(0,)])
        self.assertEqual(self.q("select count(*) from mentions where prompt_hash = %s", (OLD,)), [(10,)])

    def test_cli_refreshes_the_board_when_it_reads_v6(self):
        with mock.patch.object(db, "DATABASE_URL", URL), redirect_stdout(io.StringIO()), \
                mock.patch("refresh.refresh_views") as refresh_views:
            X.main(["--reset-hash", OLD, "--scope", "posts", "--yes"])      # legacy board: no refresh
            self.assertEqual(refresh_views.call_count, 0)
            X.set_read_version(self.conn, "v6", refresh_views=False)
            X.main(["--reset-hash", OLD, "--yes"])
            self.assertEqual(refresh_views.call_count, 1)
            X.main(["--reset-hash", OLD, "--yes"])                         # nothing left: nothing to refresh
            self.assertEqual(refresh_views.call_count, 1)

    def test_a_stale_hash_is_never_live(self):
        with redirect_stdout(io.StringIO()):
            X.set_read_version(self.conn, "v6", refresh_views=False)
        live = lambda: sorted(self.q("select comment_id, prompt_hash from live_mentions"))  # noqa: E731
        self.assertEqual({c for c, _ in live()}, {"t1_top", "t1_r1", "t1_r2"})
        # t1_top queued again under a newer prompt: its old rows drop out of
        # the board at once, before any reset deletes them.
        with self.conn.cursor() as cur:
            cur.execute("update extraction_state set prompt_hash = %s, extracted_at = null where item_id = 't1_top'",
                        (prompt_v6.PROMPT_HASH,))
        self.conn.commit()
        self.assertEqual({c for c, _ in live()}, {"t1_r1", "t1_r2"})
        # The legacy branch is unchanged: every old row, whatever extraction_state says.
        with redirect_stdout(io.StringIO()):
            X.set_read_version(self.conn, "legacy", refresh_views=False)
        self.assertEqual(live(), [("t1_top", "oldhash")])


# ---------------------------------------------------------------- 6. flip safety
class FlipSafety(DbCase):
    def main(self, *argv):
        with mock.patch.object(db, "DATABASE_URL", URL), redirect_stdout(io.StringIO()) as out:
            try:
                X.main(["--read", "v6", *argv])
            except SystemExit as e:
                return str(e), out.getvalue()
        return None, out.getvalue()

    def setUp(self):
        super().setUp()
        with self.conn.cursor() as cur:
            # what the old extractor read: everything over 15 characters
            cur.execute("update comments set extracted_at = now() - interval '1 day' where length(body) > 15")
        self.conn.commit()
        self.legacy = {r[0] for r in self.q("select id from comments where extracted_at is not null "
                                            "and subreddit = 'FoodNYC' and body not in ('[deleted]', '[removed]')")}

    def test_refuses_until_v6_covers_the_old_comments(self):
        err, out = self.main()
        self.assertIn(f"{len(self.legacy):,} r/FoodNYC comment(s)", err)
        self.assertIn("v6 coverage", out)
        self.assertEqual(X.read_version(self.conn), "legacy")
        with F.FakeAnthropic() as api:
            batch(self.conn, api, kinds=("comment",))
        with mock.patch.object(X, "set_read_version") as flip:
            err, out = self.main()
        self.assertIsNone(err)
        flip.assert_called_once()

    def test_parked_items_over_the_threshold_refuse(self):
        def answer(p):
            return (200, F.message("{", stop="max_tokens")) if "PlaceDeep" in F.user_text(p) else F.default_answer(p)
        with F.FakeAnthropic(answer) as api:
            for _ in range(2):
                X.run_direct(self.conn, AV.client("k", api.base_url), X.Budget(10), kinds=("comment",), log=QUIET)
        counts, reasons = X.flip_check(self.conn)
        self.assertEqual(counts["missing"], 0)            # parked ones are counted apart
        self.assertEqual(counts["parked"], 8)
        err, _ = self.main()
        self.assertIn("8 v6 item(s) are parked", err)
        with mock.patch.object(X, "set_read_version") as flip:
            err, _ = self.main("--force")
        self.assertIsNone(err)
        flip.assert_called_once()
        with mock.patch.object(X, "FLIP_MAX_PARKED_SHARE", 0.5), mock.patch.object(X, "set_read_version"):
            self.assertIsNone(self.main()[0])

    def test_the_old_pollers_last_passes_are_forgiven(self):
        # v6 covers everything, then the old poller (still running until it
        # is switched) extracts one more comment ten minutes before the flip.
        with F.FakeAnthropic() as api:
            batch(self.conn, api, kinds=("comment",))
        with self.conn.cursor() as cur:
            cur.execute("""insert into comments (id, subreddit, thread_id, parent_id, author, body, permalink,
                                                 created_utc, extracted_at)
                           values ('t1_late', 'FoodNYC', 't3_a', 't3_a', 'zed', 'PlaceLate is a fine spot',
                                   '/r/x/t1_late', now(), now() - interval '10 minutes')""")
        self.conn.commit()
        counts, reasons = X.flip_check(self.conn)
        self.assertEqual((counts["missing"], counts["recent"], reasons), (0, 1, []))
        with mock.patch.object(X, "set_read_version") as flip:
            err, out = self.main()
        self.assertIsNone(err)
        self.assertIn("1 more from the last 2h (allowed)", out)
        flip.assert_called_once()
        # Still meaningful: with no grace, or once it is older than the grace, it refuses.
        err, _ = self.main("--flip-grace-hours", "0")
        self.assertIn("1 r/FoodNYC comment(s)", err)
        with self.conn.cursor() as cur:
            cur.execute("update comments set extracted_at = now() - interval '3 hours' where id = 't1_late'")
        self.conn.commit()
        self.assertIn("1 r/FoodNYC comment(s)", self.main()[0])

    def test_legacy_needs_no_check(self):
        with mock.patch.object(X, "set_read_version") as flip:
            with mock.patch.object(db, "DATABASE_URL", URL), redirect_stdout(io.StringIO()):
                X.main(["--read", "legacy"])
        flip.assert_called_once()


if __name__ == "__main__":
    import unittest
    unittest.main()
