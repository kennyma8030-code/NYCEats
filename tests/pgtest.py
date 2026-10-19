"""Shared setup for the tests that need a real, disposable Postgres.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55439/nyceatstest \\
        python -m pytest tests

EMBED_TEST_DATABASE_URL is accepted too, for the embedding tests that used it
first. These tests DROP AND RECREATE the public schema of that database, so
the URL must point at a throwaway server on this machine: guard() refuses
anything that is not localhost, the stale local copy on :5433, a database
without "test" in its name, or DATABASE_URL itself. Without a URL every
database test is skipped, and the run says so in its header and summary
(tests/conftest.py).
"""

import os
import unittest
from urllib.parse import urlparse

import psycopg2

from fakes import ROOT

URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("EMBED_TEST_DATABASE_URL")
SKIP_REASON = ("database tests skipped: set TEST_DATABASE_URL to a throwaway local "
               "Postgres (with pgvector for the embedding tests)")


def guard(url):
    u = urlparse(url)
    if u.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit(f"refusing to drop schemas on {u.hostname}: tests need a local throwaway db")
    if (u.port or 5432) == 5433:
        raise SystemExit("refusing :5433, the stale local copy")
    if "test" not in (u.path or "").lstrip("/"):
        raise SystemExit("refusing a database whose name lacks 'test'")
    if url == os.environ.get("DATABASE_URL"):
        raise SystemExit("the test database URL equals DATABASE_URL")


def connect():
    return psycopg2.connect(URL)


def reset(conn):
    """An empty public schema with schema.sql applied, as a fresh boot sees it."""
    import db
    with conn.cursor() as cur:
        cur.execute("drop schema if exists public cascade; create schema public")
    conn.commit()
    db.init(conn, os.path.join(ROOT, "schema.sql"))


def has_pgvector(conn):
    with conn.cursor() as cur:
        cur.execute("select exists (select 1 from pg_available_extensions where name = 'vector')")
        ok = cur.fetchone()[0]
    conn.commit()
    return ok


class PgCase(unittest.TestCase):
    """A fresh schema per test, on the throwaway database."""

    @classmethod
    def setUpClass(cls):
        if not URL:
            raise unittest.SkipTest(SKIP_REASON)
        guard(URL)

    def setUp(self):
        self.conn = connect()
        reset(self.conn)

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def q(self, sql, *args):
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            rows = cur.fetchall()
        self.conn.commit()
        return rows
