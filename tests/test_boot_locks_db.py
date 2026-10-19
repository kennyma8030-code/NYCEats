"""What a boot locks, against a real, disposable Postgres.

Skipped without TEST_DATABASE_URL (see tests/pgtest.py). The production
facts behind these: an older worker sits "idle in transaction" holding
ACCESS SHARE on comments and threads, and every board read goes through the
scoring views. A boot must not queue behind the first or drop the second
out from under a reader.
"""

import io
import os
import threading
import time
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock

import psycopg2
import psycopg2.errors

from fakes import ROOT
import pgtest

import db
import refresh

SCHEMA = os.path.join(ROOT, "schema.sql")
NOW = datetime.now(timezone.utc)


def quiet(fn, *args, **kw):
    with redirect_stdout(io.StringIO()):
        return fn(*args, **kw)


class Boot(pgtest.PgCase):
    def test_current_database_boots_under_an_exclusive_lock(self):
        # EXCLUSIVE conflicts with everything but ACCESS SHARE: if a second
        # boot needed anything stronger than a plain read on these tables,
        # it would time out here.
        other = pgtest.connect()
        try:
            with other.cursor() as cur:
                cur.execute("lock table comments, threads, mentions in exclusive mode")
            with mock.patch.object(db, "LOCK_TIMEOUT", "300ms"):
                quiet(db.init, self.conn, SCHEMA, waits=())
        finally:
            other.rollback()
            other.close()

    def make_old(self):
        """The production shape: comments before the subreddit column."""
        with self.conn.cursor() as cur:
            cur.execute("drop index comments_sub_created_idx, threads_sub_created_idx")
            cur.execute("alter table comments drop column subreddit")   # takes the partial index too
            cur.execute("""create index comments_unextracted_idx on comments(thread_id)
                           where extracted_at is null and extract_error is null""")
        self.conn.commit()

    def has_subreddit(self):
        return bool(self.q("""select 1 from pg_attribute where attrelid = 'comments'::regclass
                              and attname = 'subreddit' and not attisdropped"""))

    def test_migration_gives_up_quickly_behind_an_idle_transaction(self):
        self.make_old()
        holder = pgtest.connect()
        with holder.cursor() as cur:
            cur.execute("select 1 from comments limit 1")          # idle in transaction
        try:
            began = time.time()
            with mock.patch.object(db, "LOCK_TIMEOUT", "200ms"), \
                    self.assertRaises(psycopg2.errors.LockNotAvailable):
                quiet(db.init, self.conn, SCHEMA, waits=(0.1,))
            self.assertLess(time.time() - began, 3)
            # All or nothing: no column, and nobody is left queued behind us.
            self.assertFalse(self.has_subreddit())
            reader = pgtest.connect()
            with reader.cursor() as cur:
                cur.execute("set statement_timeout = '1s'")
                cur.execute("select count(*) from comments")
            reader.close()
        finally:
            holder.rollback()
            holder.close()

    def test_migration_retries_until_the_holder_lets_go(self):
        self.make_old()
        holder = pgtest.connect()
        with holder.cursor() as cur:
            cur.execute("select 1 from comments limit 1")
        threading.Timer(0.5, holder.commit).start()
        try:
            with mock.patch.object(db, "LOCK_TIMEOUT", "200ms"):
                out = io.StringIO()
                with redirect_stdout(out):
                    db.init(self.conn, SCHEMA, waits=(0.3, 0.3, 0.3, 0.3))
            self.assertTrue(self.has_subreddit())
            self.assertIn("retrying", out.getvalue())
            self.assertIn("idle in transaction", out.getvalue())
            self.assertEqual(self.q("select position('subreddit' in indexdef) > 0 from pg_indexes "
                                    "where indexname = 'comments_unextracted_idx'"), [(True,)])
        finally:
            holder.close()

    def test_timeout_does_not_leak_into_the_session(self):
        quiet(db.init, self.conn, SCHEMA)
        self.assertEqual(self.q("show lock_timeout"), [("0",)])


class ApplySql(pgtest.PgCase):
    def oid(self, name):
        return self.q("select to_regclass(%s)::oid", name)[0][0]

    def test_unchanged_files_are_skipped(self):
        self.assertEqual(quiet(refresh.apply_sql, self.conn), list(refresh.SQL_FILES))
        board = self.oid("entity_leaderboard_v2")
        self.assertEqual(quiet(refresh.apply_sql, self.conn), [])
        self.assertEqual(self.oid("entity_leaderboard_v2"), board)

    def test_a_view_rebuilt_elsewhere_is_noticed(self):
        quiet(refresh.apply_sql, self.conn)
        # resolve.sql's view lost its marker (rebuilt by an older worker):
        # only that file runs.
        self.q("comment on materialized view mention_resolution is null; select 1")
        self.assertEqual(quiet(refresh.apply_sql, self.conn), ["resolve.sql"])
        # scoring_v2's views dropped by a CASCADE: it and every file after it.
        self.q("drop materialized view mention_v2 cascade; select 1")
        self.assertEqual(quiet(refresh.apply_sql, self.conn), ["scoring_v2.sql", "resolve.sql"])
        self.assertIsNotNone(self.oid("entity_leaderboard_v2"))

    def test_a_changed_file_reruns_it_and_everything_after(self):
        quiet(refresh.apply_sql, self.conn)
        real = open

        def edited(path, *a, **k):
            f = real(path, *a, **k)
            if os.path.basename(str(path)) == "scoring.sql":
                text = f.read() + "\n-- edited\n"
                f.close()
                return io.StringIO(text)
            return f
        with mock.patch("builtins.open", edited):
            self.assertEqual(quiet(refresh.apply_sql, self.conn), list(refresh.SQL_FILES))

    def test_markers_cover_every_view(self):
        quiet(refresh.apply_sql, self.conn)
        for name in refresh.SQL_FILES:
            with open(os.path.join(ROOT, name), encoding="utf-8") as f:
                views = refresh.created_views(f.read())
            self.assertTrue(views, name)
            rows = self.q("select relname, obj_description(oid, 'pg_class') from pg_class "
                          "where relname = any(%s)", views)
            self.assertEqual(len(rows), len(views), name)
            self.assertTrue(all(d and d.startswith(f"nyceats {name} sha256:") for _, d in rows))

    def test_the_board_never_disappears_mid_apply(self):
        quiet(refresh.apply_sql, self.conn)
        errors, reads, stop = [], [0], threading.Event()

        def reader():
            c = pgtest.connect()
            c.autocommit = True
            while not stop.is_set():
                try:
                    with c.cursor() as cur:
                        cur.execute("select count(*) from entity_leaderboard_v2")
                    reads[0] += 1
                except psycopg2.Error as e:
                    errors.append(str(e).strip())
            c.close()
        t = threading.Thread(target=reader)
        t.start()
        try:
            for _ in range(3):
                quiet(refresh.apply_sql, self.conn, force=True)
        finally:
            stop.set()
            t.join(10)
        self.assertGreater(reads[0], 0)
        self.assertEqual(errors, [])

    def test_waits_for_a_reader_then_retries(self):
        quiet(refresh.apply_sql, self.conn)
        holder = pgtest.connect()
        with holder.cursor() as cur:
            cur.execute("select count(*) from entity_leaderboard_v2")   # idle in transaction
        try:
            with mock.patch.object(db, "LOCK_TIMEOUT", "200ms"), \
                    self.assertRaises(psycopg2.errors.LockNotAvailable):
                quiet(refresh.apply_sql, self.conn, force=True, waits=(0.1,))
            threading.Timer(0.4, holder.commit).start()
            with mock.patch.object(db, "LOCK_TIMEOUT", "200ms"):
                self.assertEqual(quiet(refresh.apply_sql, self.conn, force=True,
                                       waits=(0.3, 0.3, 0.3)), list(refresh.SQL_FILES))
        finally:
            holder.close()


# The view as it was at fa26141, kept here as the oracle for the rewrite.
OLD_LONGEVITY = """
create view entity_longevity_old as
with active_months as (
  select coalesce(a.resolved_key, m.entity_key) as entity_key,
         extract(year from c.created_utc)::int * 12
           + extract(month from c.created_utc)::int as month_idx
  from live_mentions m
  join comments c on c.id = m.comment_id
  left join entity_alias a on a.entity_key = m.entity_key
  group by 1, 2
),
gaps as (
  select entity_key,
         month_idx - lag(month_idx) over (partition by entity_key
                                          order by month_idx) as step
  from active_months
),
totals as (
  select coalesce(a.resolved_key, m.entity_key) as entity_key,
         min(c.created_utc) as first_seen,
         max(c.created_utc) as last_seen,
         count(*)           as total_mentions
  from live_mentions m
  join comments c on c.id = m.comment_id
  left join entity_alias a on a.entity_key = m.entity_key
  group by 1
)
select t.entity_key,
       t.first_seen,
       t.last_seen,
       t.total_mentions,
       (select count(*) from active_months a where a.entity_key = t.entity_key)
         as months_active,
       coalesce((select max(g.step) - 1 from gaps g
                  where g.entity_key = t.entity_key and g.step is not null), 0)
         as longest_gap_months
from totals t;
"""


class Longevity(pgtest.PgCase):
    def test_same_rows_as_the_correlated_version(self):
        with self.conn.cursor() as cur:
            cur.execute("""insert into threads (id, subreddit, title, created_utc)
                           values ('t3_a', 'FoodNYC', 't', now())""")
            # Months chosen for gaps of 0, 1, 5 and 13, a one-month place, a
            # place mentioned twice in one month, and two spellings merged
            # by an override.
            plan = {"lucali": [0, 1, 2, 8, 9], "katz": [0, 14], "katzs": [3],
                    "once": [4], "twice": [6, 6], "joes": [0, 2, 3, 30]}
            n = 0
            for key, months in plan.items():
                for m in months:
                    n += 1
                    cur.execute("""insert into comments (id, subreddit, thread_id, parent_id, body,
                                                         permalink, created_utc, author)
                                   values (%s, 'FoodNYC', 't3_a', 't3_a', 'b', 'p', %s, %s)""",
                                (f"t1_{n}", NOW - timedelta(days=31 * m + 1), f"u{n}"))
                    cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key,
                                                         model_version, prompt_hash)
                                   values (%s, %s, %s, 'm', 'p')""", (f"t1_{n}", key, key))
            cur.execute("insert into alias_overrides (entity_key, resolved_key) values ('katzs', 'katz')")
        self.conn.commit()
        quiet(refresh.apply_sql, self.conn)
        self.q(OLD_LONGEVITY + "; select 1")
        cols = "entity_key, first_seen, last_seen, total_mentions, months_active, longest_gap_months"
        new = self.q(f"select {cols} from entity_longevity order by 1")
        old = self.q(f"select {cols} from entity_longevity_old order by 1")
        self.assertEqual(new, old)
        self.assertEqual(len(new), 5)
        self.assertEqual(self.q("select count(*) from entity_longevity where longest_gap_months > 0"),
                         [(3,)])
        types = "select atttypid::regtype::text from pg_attribute where attrelid = %s::regclass " \
                "and attnum > 0 order by attnum"
        self.assertEqual(self.q(types, "entity_longevity"), self.q(types, "entity_longevity_old"))
