"""The multi-city poller's SQL against a real, disposable Postgres.

Skipped without TEST_DATABASE_URL (see tests/pgtest.py). Arctic Shift is
faked; nothing here touches the network or any database but the throwaway.
"""

import io
import os
import sys
import types
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock

import psycopg2.extensions as ext

from fakes import ROOT
import pgtest

import db
import refresh
import subreddits

HOME = subreddits.HOME
NOW = datetime.now(timezone.utc)
NOW_S = int(NOW.timestamp())


def arctic_comment(i, sub, link, t, parent=None, **kw):
    c = {"id": f"{sub[:3].lower()}{i:05d}", "subreddit": sub, "link_id": link,
         "parent_id": parent or link, "author": f"u{i}",
         "body": f"comment {i} about a place, long enough to extract",
         "permalink": f"/r/{sub}/comments/x/{i}/", "created_utc": t,
         "retrieved_on": t + 30, "score": 3, "controversiality": 0}
    c.update(kw)
    return c


def arctic_post(pid, sub, t):
    return {"id": pid, "subreddit": sub, "title": f"{sub} thread", "selftext": "",
            "author": "op", "created_utc": t, "score": 5, "upvote_ratio": 1.0,
            "num_comments": 0, "retrieved_on": t}


class Seeded(pgtest.PgCase):
    """Two cities: three r/FoodNYC comments with mentions, many Chicago ones."""

    def seed_home(self):
        db.insert_threads(self.conn, [arctic_post("nyc1", HOME, NOW_S - 3600)])
        rows = [arctic_comment(i, HOME, "t3_nyc1", NOW_S - 600 * i) for i in range(1, 4)]
        db.insert_comments(self.conn, rows)
        with self.conn.cursor() as cur:
            for c in rows:
                cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key,
                                                     model_version, prompt_hash)
                               values (%s, 'Lucali', 'lucali', 'm', 'p')""", ("t1_" + c["id"],))
        self.conn.commit()

    def seed_chicago(self, n=200, mention=True):
        db.insert_threads(self.conn, [arctic_post("chi1", "chicagofood", NOW_S - 3600)])
        rows = [arctic_comment(i, "chicagofood", "t3_chi1", NOW_S - 60 * i) for i in range(1, n + 1)]
        db.insert_comments(self.conn, rows)
        if mention:
            # Cannot happen today (extraction reads HOME only); the scoring
            # filters must hold even if it does.
            with self.conn.cursor() as cur:
                cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key,
                                                     model_version, prompt_hash)
                               values (%s, 'Lucali', 'lucali', 'm', 'p')""", ("t1_" + rows[0]["id"],))
            self.conn.commit()


class InsertComments(Seeded):
    def test_columns_line_up(self):
        db.insert_threads(self.conn, [arctic_post("chi1", "chicagofood", NOW_S - 90_000)])
        old = NOW_S - 86_400 * 3
        db.insert_comments(self.conn, [
            arctic_comment(1, "chicagofood", "t3_chi1", old, score=7, controversiality=1),
            arctic_comment(2, "chicagofood", "t3_chi1", NOW_S, parent="t1_chi00001"),
        ])
        rows = self.q("""select id, subreddit, thread_id, parent_id, parent_comment_id, author,
                                body, permalink, extract(epoch from created_utc)::bigint,
                                extract(epoch from retrieved_on)::bigint, score,
                                controversiality, score_settled
                         from comments order by id""")
        self.assertEqual(rows[0], (
            "t1_chi00001", "chicagofood", "t3_chi1", "t3_chi1", None, "u1",
            "comment 1 about a place, long enough to extract", "/r/chicagofood/comments/x/1/",
            old, old + 30, 7, 1, True))
        self.assertEqual(rows[1][3:5], ("t1_chi00001", "t1_chi00001"))
        self.assertFalse(rows[1][12])          # under 36h: still to settle


class Cursors(pgtest.PgCase):
    def init(self):
        db.init(self.conn, os.path.join(ROOT, "schema.sql"))

    def cursors(self):
        return self.q("select subreddit, kind, cursor_utc from backfill_cursors order by 1, 2")

    def test_seeded_from_backfill_progress_once(self):
        self.q("insert into backfill_progress (kind, cursor_utc) "
               "values ('posts', 111), ('comments', 222) returning kind")
        self.init()
        self.assertEqual(self.cursors(), [(HOME, "comments", 222), (HOME, "posts", 111)])
        db.set_cursor(self.conn, HOME, "comments", 999)
        self.init()                                     # every boot re-runs schema.sql
        self.assertEqual(self.cursors(), [(HOME, "comments", 999), (HOME, "posts", 111)])

    def test_clear_home_also_clears_the_old_cursor(self):
        self.q("insert into backfill_progress (kind, cursor_utc) values ('comments', 222) returning kind")
        self.init()
        db.set_cursor(self.conn, "chicagofood", "comments", 5)
        db.clear_cursors(self.conn, [HOME])
        self.init()
        self.assertEqual(self.cursors(), [("chicagofood", "comments", 5)])
        self.assertEqual(self.q("select count(*) from backfill_progress"), [(0,)])

    def test_clear_other_city_leaves_home(self):
        self.q("insert into backfill_progress (kind, cursor_utc) values ('comments', 222) returning kind")
        self.init()
        db.set_cursor(self.conn, "chicagofood", "comments", 5)
        db.clear_cursors(self.conn, ["chicagofood"])
        self.assertEqual(self.cursors(), [(HOME, "comments", 222)])
        self.assertEqual(db.get_cursor(self.conn, "chicagofood", "comments", 42), 42)


class UnextractedIndex(pgtest.PgCase):
    def indexdef(self):
        return self.q("""select indexdef, (select oid from pg_class
                                          where relname = 'comments_unextracted_idx')
                         from pg_indexes where indexname = 'comments_unextracted_idx'""")[0]

    def test_home_only_and_rebuilt_once_from_the_old_definition(self):
        self.assertIn(f"subreddit = '{HOME}'", self.indexdef()[0])
        # Production's index, as built before this branch.
        self.q("drop index comments_unextracted_idx; "
               "create index comments_unextracted_idx on comments(thread_id) "
               "where extracted_at is null and extract_error is null; select 1")
        db.init(self.conn, os.path.join(ROOT, "schema.sql"))
        new_def, oid = self.indexdef()
        self.assertIn(f"subreddit = '{HOME}'", new_def)
        db.init(self.conn, os.path.join(ROOT, "schema.sql"))
        self.assertEqual(self.indexdef(), (new_def, oid), "rebuilt on a boot that needed nothing")

    def test_extract_query_can_use_it(self):
        with self.conn.cursor() as cur:
            cur.execute("set enable_seqscan = off")
            cur.execute(f"""explain select c.id from comments c
                            where c.subreddit = '{HOME}' and c.extracted_at is null
                              and c.extract_error is null order by c.thread_id""")
            plan = "\n".join(r[0] for r in cur.fetchall())
        self.conn.rollback()
        self.assertIn("comments_unextracted_idx", plan)


class Scoring(Seeded):
    """scoring.sql reads one city: mention_weights, entity_volume, momentum."""

    def snapshot(self):
        refresh.refresh_views(self.conn, verbose=False)
        return (self.q("select comment_id from mention_weights order by 1"),
                self.q("select entity_key, volume_share from entity_volume order by 1"),
                self.q("select window_days, recent_comments, baseline_comments "
                       "from momentum_windows order by 1"))

    def setUp(self):
        super().setUp()
        refresh.apply_sql(self.conn, verbose=False)
        self.seed_home()

    def test_other_cities_change_nothing(self):
        before = self.snapshot()
        self.assertEqual(len(before[0]), 3)
        self.assertEqual(before[2][0][1], 3)
        self.seed_chicago()
        after = self.snapshot()
        self.assertEqual(after[0], before[0])
        self.assertEqual(after[2], before[2])
        # volume_share decays with now(), which moved between the two reads;
        # numerator and denominator decay alike, so only rounding differs.
        # 200 Chicago comments in the denominator would cut it by ~98%.
        [(key, share_before)], [(key2, share_after)] = before[1], after[1]
        self.assertEqual(key, key2)
        self.assertAlmostEqual(share_after, share_before, places=9)

    def test_feed_and_stats_are_home_only(self):
        from app import db as appdb
        from app import queries
        self.seed_chicago(mention=False)
        refresh.refresh_views(self.conn, verbose=False)
        stats = queries.stats(self.conn, appdb.fetch_one)
        self.assertEqual((stats["comments"], stats["threads"]), (3, 1))
        items = queries.feed_items(self.conn, None, False, None, None, 100, appdb.fetch_all)
        self.assertEqual({i["id"] for i in items},
                         {"t3_nyc1"} | {f"t1_foo{i:05d}" for i in range(1, 4)})
        hits = queries.feed_items(self.conn, "comment", False, None, None, 100, appdb.fetch_all)
        self.assertTrue(hits)
        self.assertTrue(all(i["id"].startswith(("t1_foo", "t3_nyc")) for i in hits))


class ExtractHomeOnly(Seeded):
    def test_candidates(self):
        import extract
        import extract_threads
        self.seed_home()
        self.seed_chicago(mention=False)
        rows = extract.next_batch(self.conn, limit=1000)
        self.assertEqual({r[0] for r in rows}, {f"t1_foo{i:05d}" for i in range(1, 4)})
        self.assertEqual([t for t, _ in extract_threads.pending_threads(self.conn)], ["t3_nyc1"])
        _, rows = extract_threads.thread_rows(self.conn, "t3_chi1")
        self.assertEqual(rows, [])


class NoIdleTransaction(Seeded):
    """Nothing the poller does may leave its connection in a transaction."""

    def assertIdle(self, conn, what):
        self.assertEqual(conn.info.transaction_status, ext.TRANSACTION_STATUS_IDLE, what)

    def test_read_helpers(self):
        self.seed_home()
        for name, call in [
            ("newest_stored_utc", lambda: db.newest_stored_utc(self.conn, HOME)),
            ("busiest_hour", lambda: db.busiest_hour(self.conn, HOME)),
            ("unsettled_comment_ids", lambda: db.unsettled_comment_ids(self.conn)),
            ("get_cursor", lambda: db.get_cursor(self.conn, HOME, "comments", 0)),
            ("missing_thread_ids", lambda: db.missing_thread_ids(self.conn, {"t3_nyc1", "t3_no"})),
        ]:
            call()
            self.assertIdle(self.conn, name)

    def fake_arctic(self):
        page = [arctic_comment(i, "chicagofood", "t3_chi1", NOW_S - 30 * i) for i in range(1, 6)]
        return mock.patch.multiple(
            "arctic", newest_comments=mock.Mock(return_value=page),
            posts_by_id=mock.Mock(return_value=[arctic_post("chi1", "chicagofood", NOW_S - 3600)]),
            all_thread_comments=mock.Mock(return_value=page),
            comments_by_id=mock.Mock(return_value=[]))

    def test_poll_and_chores(self):
        import poller
        self.seed_home()
        args = types.SimpleNamespace(extract=False, embed=False)
        due = dict.fromkeys(["chicagofood", HOME], 0.0)
        with self.fake_arctic(), mock.patch.object(poller.time, "sleep"), \
                redirect_stdout(io.StringIO()):
            conn = poller.poll_due(self.conn, list(due), due, {})
            self.assertIdle(conn, "after poll_due")
            conn = poller.run_chores(conn, args)
            self.assertIdle(conn, "after run_chores")
        self.assertEqual(self.q("select count(*) from comments where subreddit = 'chicagofood'"),
                         [(5,)])

    def test_main_loop_sleeps_idle(self):
        import poller
        conn = self.conn

        class Stop(Exception):
            pass
        states = []

        def sleep(_s):
            # Only the loop's own sleep; the steps' politeness pauses go by.
            if sys._getframe(1).f_code.co_name != "main":
                return
            other = pgtest.connect()
            try:
                with other.cursor() as cur:
                    cur.execute("select state from pg_stat_activity where pid = %s",
                                (conn.info.backend_pid,))
                    states.append(cur.fetchone()[0])
            finally:
                other.close()
            raise Stop

        init = db.init
        env = {k: v for k, v in os.environ.items() if not k.startswith("POLL_")}
        with self.fake_arctic(), mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("sys.argv", ["poller.py", "--no-rss", "--no-backfill"]), \
                mock.patch.object(poller.db, "connect", return_value=conn), \
                mock.patch.object(poller.db, "init",
                                  lambda c: init(c, os.path.join(ROOT, "schema.sql"))), \
                mock.patch.object(poller.restaurants, "ensure_loaded", return_value=0), \
                mock.patch.object(poller.time, "sleep", sleep), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(Stop):
                poller.main()
        self.assertEqual(states, ["idle"])


class DroppedConnection(Seeded):
    def test_poller_reconnects_and_carries_on(self):
        import poller
        dead = pgtest.connect()
        with self.conn.cursor() as cur:
            cur.execute("select pg_terminate_backend(%s)", (dead.info.backend_pid,))
        self.conn.commit()
        page = [arctic_comment(i, HOME, "t3_nyc9", NOW_S - i) for i in range(1, 4)]
        due = dict.fromkeys(["chicagofood", HOME], 0.0)
        with mock.patch.multiple(
                "arctic", newest_comments=mock.Mock(return_value=page),
                posts_by_id=mock.Mock(return_value=[arctic_post("nyc9", HOME, NOW_S - 60)]),
                all_thread_comments=mock.Mock(return_value=page)), \
                mock.patch.object(poller.db, "connect", side_effect=pgtest.connect), \
                mock.patch.object(poller.time, "sleep"), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            conn = poller.poll_due(dead, list(due), due, {})
        self.assertIsNot(conn, dead)
        self.assertFalse(conn.closed)
        self.assertEqual(self.q("select count(*) from comments where thread_id = 't3_nyc9'"), [(3,)])
        conn.close()
