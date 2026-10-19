"""Shared setup for the web app's database tests.

AppCase seeds one throwaway database per test class (tests/pgtest.py) and
points the app's pool at it. Nothing here touches the network.
"""

import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi.testclient import TestClient
from psycopg2.extras import Json

from fakes import ROOT  # noqa: F401  (puts the repo root on sys.path)
import pgtest

import db as pipeline_db
import refresh
import subreddits
from app import db as appdb
from app import main

NOW = datetime.now(timezone.utc)


def seed(conn):
    """A handful of r/FoodNYC comments: a place with two legacy rows of the
    wrong shape, one with a deleted comment, and names for the LIKE tests."""
    with conn.cursor() as cur:
        cur.execute("""insert into threads (id, subreddit, title, created_utc)
                       values ('t3_a', %s, 'Best slice?', %s)""", (subreddits.HOME, NOW - timedelta(days=2)))
        for i in range(1, 9):
            cur.execute("""insert into comments (id, thread_id, parent_id, author, body, permalink,
                                                 created_utc, score, score_settled, was_deleted_later)
                           values (%s, 't3_a', 't3_a', %s, %s, %s, %s, 5, true, %s)""",
                        (f"t1_c{i}", f"u{i}", f"comment {i}", f"/r/{subreddits.HOME}/comments/a/{i}/",
                         NOW - timedelta(days=1, minutes=i), i == 2))
        rows = [
            # Legacy shape: descriptors stored as a bare JSON string (production
            # mentions 78858 and 78859), aspects a string where a number goes.
            ("t1_c1", "Cellos", "cellos", Json("solid counter slice joint"), Json("slice"),
             Json({"food": -0.9, "value": "cheap"}), True),
            ("t1_c2", "Cellos", "cellos", Json(["slice"]), Json([]), Json({"food": -0.8}), True),
            ("t1_c3", "Cellos", "cellos", Json(["cash only"]), Json(["slice"]), Json({"food": 0.4}), False),
            ("t1_c4", "abc", "abc", Json(["cash only"]), Json([]), Json({"food": 0.5}), False),
            ("t1_c5", "Katz's", "katzs", Json(["cash only"]), Json(["pastrami"]), Json({"food": 0.9}), True),
            ("t1_c6", "Katz's", "katzs", Json([]), Json([]), Json({"food": 0.8}), True),
        ]
        for comment, raw, key, desc, dishes, aspects, firsthand in rows:
            cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key, descriptors,
                                                 dishes, aspects, is_firsthand, model_version, prompt_hash)
                           values (%s, %s, %s, %s, %s, %s, %s, 'm', 'p')""",
                        (comment, raw, key, desc, dishes, aspects, firsthand))
    conn.commit()


def build_views(conn):
    with redirect_stdout(io.StringIO()):
        refresh.apply_sql(conn, verbose=False)
        refresh.refresh_views(conn, verbose=False)


def in_use():
    """Connections checked out of the app's pool right now."""
    return len(appdb._pool._used) if appdb._pool else 0


class AppCase(unittest.TestCase):
    """One seeded database per class; the app's pool pointed at it."""

    @classmethod
    def setUpClass(cls):
        if not pgtest.URL:
            raise unittest.SkipTest(pgtest.SKIP_REASON)
        pgtest.guard(pgtest.URL)
        cls.conn = pgtest.connect()
        pgtest.reset(cls.conn)
        seed(cls.conn)
        build_views(cls.conn)
        cls._url = mock.patch.object(pipeline_db, "DATABASE_URL", pgtest.URL)
        cls._url.start()
        appdb.close_pool()
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        appdb.close_pool()
        cls._url.stop()
        cls.conn.close()

    def tearDown(self):
        appdb.close_pool()
        self.conn.rollback()

    def q(self, sql, *args):
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            rows = cur.fetchall() if cur.description else None
        self.conn.commit()
        return rows
