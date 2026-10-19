"""The app's connection pool against a throwaway Postgres: bursts wait, a
pool that stays busy answers 503, statements time out, dead connections are
replaced, and database errors reach the log rather than the client."""

import threading
import time
import unittest
from unittest import mock

import psycopg2
import psycopg2.errors
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apptest import AppCase, in_use
from app import db as appdb
from app import main


class Pool(AppCase):
    def test_a_burst_waits_for_a_connection_instead_of_failing(self):
        # Eight requests on a pool of two: psycopg2's pool alone raises
        # PoolError for six of them. Through the semaphore all eight finish.
        errors, peak, live = [], [0], [0]
        lock = threading.Lock()

        def work():
            try:
                with appdb.connection() as conn:
                    with lock:
                        live[0] += 1
                        peak[0] = max(peak[0], live[0])
                    appdb.fetch_value(conn, "select pg_sleep(0.1)")
                    with lock:
                        live[0] -= 1
            except Exception as e:          # noqa: BLE001
                errors.append(e)

        with mock.patch.object(appdb, "POOL_MAX", 2), mock.patch.object(appdb, "POOL_TIMEOUT", 10):
            threads = [threading.Thread(target=work) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(errors, [])
        self.assertEqual(peak[0], 2)
        self.assertEqual(in_use(), 0)

    def test_a_pool_that_stays_busy_answers_503(self):
        with mock.patch.object(appdb, "POOL_MAX", 1), mock.patch.object(appdb, "POOL_TIMEOUT", 0.2):
            with appdb.connection():
                began = time.monotonic()
                with self.assertRaises(appdb.PoolTimeout):
                    with appdb.connection():
                        pass
                self.assertGreaterEqual(time.monotonic() - began, 0.15)
                r = self.client.get("/api/stats")
            self.assertEqual(r.status_code, 503)
            self.assertEqual(r.headers.get("retry-after"), "1")
            # The slot came back: the next request is served.
            self.assertEqual(self.client.get("/api/stats").status_code, 200)

    def test_statement_timeout_is_set_and_pgoptions_kept(self):
        # The local read-only run relies on PGOPTIONS; the timeout must not
        # replace it.
        with mock.patch.dict("os.environ", {"PGOPTIONS": "-c default_transaction_read_only=on"}):
            with appdb.connection() as conn:
                self.assertEqual(appdb.fetch_value(conn, "show statement_timeout"), "10s")
                self.assertEqual(appdb.fetch_value(conn, "show default_transaction_read_only"), "on")
        appdb.close_pool()
        with mock.patch.object(appdb, "STATEMENT_TIMEOUT_MS", 100):
            with appdb.connection() as conn:
                with self.assertRaises(psycopg2.errors.QueryCanceled):
                    appdb.fetch_value(conn, "select pg_sleep(2)")
            # The cancelled connection went back usable.
            with appdb.connection() as conn:
                self.assertEqual(appdb.fetch_value(conn, "select 1"), 1)

    def test_a_dead_pooled_connection_is_replaced_on_checkout(self):
        # What a database restart leaves behind: an idle pooled connection
        # whose server is gone. It must not fail the next request.
        with appdb.connection() as conn:
            pid = appdb.fetch_value(conn, "select pg_backend_pid()")
        self.q("select pg_terminate_backend(%s)", pid)
        time.sleep(0.2)
        with mock.patch.object(appdb, "PING_AFTER", 0):
            with appdb.connection() as conn:
                self.assertNotEqual(appdb.fetch_value(conn, "select pg_backend_pid()"), pid)
            self.assertEqual(self.client.get("/api/stats").status_code, 200)


class Errors(unittest.TestCase):
    """The handlers themselves; no database needed."""

    def client_raising(self, exc):
        app = FastAPI()
        app.add_exception_handler(psycopg2.Error, main.database_error)

        @app.get("/boom")
        def boom():
            raise exc

        return TestClient(app, raise_server_exceptions=False)

    def test_database_text_is_logged_not_returned(self):
        secret = 'relation "secret_internal_table" violates something'
        exc = psycopg2.errors.InternalError_(secret)
        with self.assertLogs("uvicorn.error", level="ERROR") as logs:
            r = self.client_raising(exc).get("/boom")
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("secret_internal_table", r.text)
        self.assertIsNone(r.json()["hint"])
        self.assertIn("secret_internal_table", "\n".join(logs.output))

    def test_missing_views_still_get_their_hint(self):
        with self.assertLogs("uvicorn.error", level="ERROR"):
            r = self.client_raising(psycopg2.errors.UndefinedTable(
                'relation "entity_leaderboard" does not exist')).get("/boom")
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("entity_leaderboard", r.json()["detail"])
        self.assertIn("refresh.py", r.json()["hint"])

    def test_statement_timeout_is_503(self):
        with self.assertLogs("uvicorn.error", level="ERROR"):
            r = self.client_raising(psycopg2.errors.QueryCanceled("canceling statement")).get("/boom")
        self.assertEqual(r.status_code, 503)
