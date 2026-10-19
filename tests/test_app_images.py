"""The image endpoint: refresh is gated, no pooled connection is held while
the providers are called, and resolutions are capped per process. The
providers are always faked."""

import threading
from unittest import mock

from apptest import AppCase, in_use
from app import images
from app.routers import admin, restaurants


FOUND = {"status": "found", "source": "wikimedia", "source_ref": "Q1", "url": "https://x/y.jpg",
         "attribution": "someone", "license": "CC BY-SA 4.0", "source_url": "https://www.wikidata.org/wiki/Q1"}


class Images(AppCase):
    def setUp(self):
        self.q("delete from restaurant_images")

    def test_resolution_holds_no_pooled_connection(self):
        seen = []

        def fake(entity_key, display_name):
            seen.append(in_use())
            return dict(FOUND), True

        with mock.patch.object(images, "resolve", fake):
            r = self.client.get("/api/restaurants/katzs/image")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "found")
        self.assertEqual(seen, [0])
        self.assertEqual(self.q("select status from restaurant_images where entity_key = 'katzs'"),
                         [("found",)])

    def test_refresh_needs_the_admin_token(self):
        self.q("""insert into restaurant_images (entity_key, status, fetched_at)
                  values ('katzs', 'none', now())""")
        calls = []

        def fake(entity_key, display_name):
            calls.append(entity_key)
            return dict(FOUND), True

        with mock.patch.object(images, "resolve", fake):
            with mock.patch.object(admin, "ADMIN_TOKEN", None):
                self.assertEqual(self.client.get("/api/restaurants/katzs/image?refresh=true").status_code, 503)
            with mock.patch.object(admin, "ADMIN_TOKEN", "s3cret"):
                self.assertEqual(self.client.get("/api/restaurants/katzs/image?refresh=true").status_code, 401)
                self.assertEqual(self.client.get("/api/restaurants/katzs/image?refresh=true",
                                                 headers={"X-Admin-Token": "nope"}).status_code, 401)
                self.assertEqual(calls, [])
                # Without refresh the cached answer stands and nothing is resolved.
                self.assertEqual(self.client.get("/api/restaurants/katzs/image").json()["status"], "none")
                r = self.client.get("/api/restaurants/katzs/image?refresh=true",
                                    headers={"X-Admin-Token": "s3cret"})
        self.assertEqual(r.json()["status"], "found")
        self.assertEqual(calls, ["katzs"])

    def test_resolutions_are_capped_per_process(self):
        gate, started = threading.Event(), threading.Event()

        def slow(entity_key, display_name):
            started.set()
            gate.wait(5)
            return dict(FOUND), True

        sem = threading.BoundedSemaphore(1)
        results = {}
        with mock.patch.object(images, "resolve", slow), \
                mock.patch.object(restaurants, "_resolving", sem), \
                mock.patch.object(restaurants, "RESOLVE_WAIT", 0.1):
            first = threading.Thread(target=lambda: results.update(
                katzs=self.client.get("/api/restaurants/katzs/image").json()))
            first.start()
            self.assertTrue(started.wait(5))
            # The second place finds the one slot taken: told "error", which
            # is not cached, rather than queueing behind a minute of HTTP.
            second = self.client.get("/api/restaurants/abc/image").json()
            gate.set()
            first.join()
        self.assertEqual(second["status"], "error")
        self.assertEqual(results["katzs"]["status"], "found")
        self.assertEqual(self.q("select entity_key from restaurant_images"), [("katzs",)])
