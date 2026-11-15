"""The page at /: the built React app when frontend/dist exists, and a plain
503 saying it is not built when it does not, with the API reachable either
way. No database: these build a bare app around main.serve_frontend."""

import os
import tempfile
import unittest

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
            with self.assertLogs("uvicorn.error", level="ERROR") as logged:
                app, served = app_serving(os.path.join(tmp, "dist"))
            client = TestClient(app)
            self.assertFalse(served)
            self.assertIn("not built", logged.output[0])
            r = client.get("/")
            self.assertEqual(r.status_code, 503)
            self.assertIn("frontend/dist does not exist", r.text)
            self.assertEqual(client.get("/api/ping").json(), {"ok": True})

    def test_the_old_page_is_not_a_fallback(self):
        # static/ was served when no build existed, which is how production
        # kept showing the old page. Nothing may quietly stand in for a build.
        self.assertEqual(main.FRONTEND_DIR, "frontend/dist")
        self.assertFalse(os.path.exists(os.path.join(ROOT, "static")))


if __name__ == "__main__":
    unittest.main()
