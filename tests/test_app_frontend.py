"""The page at /: the built React app when frontend/dist exists, and a plain
503 saying it is not built when it does not, with the API reachable either
way. No database: these build a bare app around main.serve_frontend."""

import os
import tempfile
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fakes import ROOT  # noqa: F401  (puts the repo root on sys.path)
from app import main


def app_serving(directory):
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    return app, main.serve_frontend(app, directory)


class Frontend(unittest.TestCase):
    def test_a_build_is_served_at_the_root(self):
        with tempfile.TemporaryDirectory() as dist:
            with open(os.path.join(dist, "index.html"), "w") as f:
                f.write("<div id=root></div>")
            app, served = app_serving(dist)
            client = TestClient(app)
            self.assertTrue(served)
            self.assertEqual(client.get("/").text, "<div id=root></div>")
            self.assertEqual(client.get("/api/ping").json(), {"ok": True})

    def test_a_missing_build_says_so_and_leaves_the_api_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertLogs("uvicorn.error", level="WARNING") as logged:
                app, served = app_serving(os.path.join(tmp, "dist"))
            client = TestClient(app)
            self.assertFalse(served)
            # A warning, not an error: it is also what local dev looks like.
            self.assertEqual([r.levelname for r in logged.records], ["WARNING"])
            self.assertIn("not built", logged.output[0])
            for path in ("/", "/index.html", "/assets/index.js", "/favicon.ico"):
                r = client.get(path)
                self.assertEqual(r.status_code, 503, path)
                self.assertIn("frontend/dist does not exist", r.text)
            self.assertEqual(client.head("/").status_code, 503)
            # The catch-all is behind everything else: the API, the docs and
            # the schema still answer, and an unknown API path is still a 404.
            self.assertEqual(client.get("/api/ping").json(), {"ok": True})
            self.assertEqual(client.get("/docs").status_code, 200)
            self.assertEqual(client.get("/openapi.json").status_code, 200)
            self.assertEqual(client.get("/api/nope").status_code, 404)
            self.assertEqual(client.post("/").status_code, 405)

    def test_the_old_page_is_not_a_fallback(self):
        # static/ used to be served when no build existed, which is how
        # production kept showing the old page. Nothing may stand in for a
        # build, even if such a directory turns up beside the app again.
        with tempfile.TemporaryDirectory() as root:
            os.mkdir(os.path.join(root, "static"))
            with open(os.path.join(root, "static", "index.html"), "w") as f:
                f.write("the old page")
            app, served = app_serving(main.frontend_dir(root))
            client = TestClient(app)
            self.assertFalse(served)
            for path in ("/", "/index.html", "/static/index.html"):
                r = client.get(path)
                self.assertEqual(r.status_code, 503, path)
                self.assertNotIn("the old page", r.text)

    def test_the_build_is_found_from_the_app_not_the_working_directory(self):
        # uvicorn started from outside the repo must not report a build that
        # exists as missing.
        with tempfile.TemporaryDirectory() as elsewhere:
            here = os.getcwd()
            os.chdir(elsewhere)
            try:
                self.assertEqual(main.frontend_dir(),
                                 os.path.join(ROOT, "frontend", "dist"))
                self.assertTrue(os.path.isabs(main.frontend_dir()))
            finally:
                os.chdir(here)

    def test_the_real_app_keeps_its_own_routes_ahead_of_the_page(self):
        # Whichever way the page is served, it is the last route, so nothing
        # the API or the docs registered can be shadowed by it.
        last = main.app.router.routes[-1]
        self.assertIn(getattr(last, "name", None), ("frontend", "frontend_missing"))


if __name__ == "__main__":
    unittest.main()
