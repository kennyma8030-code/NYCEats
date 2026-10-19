"""The admin refresh: a database-wide lock, and a connection of its own."""

from unittest import mock

from apptest import AppCase, in_use
import pgtest
import refresh
from app import db as appdb
from app import locks
from app.routers import admin


class AdminRefresh(AppCase):
    def setUp(self):
        self._tok = mock.patch.object(admin, "ADMIN_TOKEN", "s3cret")
        self._tok.start()

    def tearDown(self):
        self._tok.stop()
        super().tearDown()

    def post(self):
        return self.client.post("/api/admin/refresh", headers={"X-Admin-Token": "s3cret"}).json()

    def test_a_refresh_elsewhere_holds_this_one_off(self):
        # The other uvicorn worker is running an admin refresh, so holds the lock.
        other = pgtest.connect()
        try:
            self.assertTrue(locks.try_lock(other))
            with mock.patch.object(refresh, "refresh_views") as rv:
                r = self.post()
            self.assertFalse(r["started"])
            rv.assert_not_called()
        finally:
            locks.unlock(other)
            other.close()

    def test_refresh_runs_off_the_pool_and_releases_the_lock(self):
        seen = {}

        def fake(conn, verbose=True):
            seen["pooled"] = isinstance(conn, appdb._Conn)
            seen["in_use"] = in_use()
            probe = pgtest.connect()
            try:
                seen["held"] = not locks.try_lock(probe)
            finally:
                probe.close()

        with mock.patch.object(refresh, "refresh_views", fake):
            r = self.post()
        self.assertTrue(r["started"])
        self.assertEqual(seen, {"pooled": False, "in_use": 0, "held": True})
        probe = pgtest.connect()
        try:
            self.assertTrue(locks.try_lock(probe))      # released when it finished
            locks.unlock(probe)
        finally:
            probe.close()
