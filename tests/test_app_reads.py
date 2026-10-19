"""The read endpoints: LIKE escaping, health, the facets cache."""

from unittest import mock

from apptest import AppCase, build_views
import refresh
from app.routers import public


class Reads(AppCase):
    def test_like_wildcards_in_search_are_literal(self):
        self.assertEqual(self.client.get("/api/search?q=%25").json(), [])
        self.assertEqual(self.client.get("/api/search?q=a_c").json(), [])
        self.assertEqual([h["entity_key"] for h in self.client.get("/api/search?q=ab").json()], ["abc"])

    def test_like_wildcards_in_board_filters_are_literal(self):
        everything = self.client.get("/api/leaderboard?hide_chains=false").json()["total"]
        self.assertGreater(everything, 1)
        self.assertEqual(self.client.get("/api/leaderboard?search=%25").json()["total"], 0)
        self.assertEqual(self.client.get("/api/leaderboard?search=a_c").json()["total"], 0)
        self.assertEqual(self.client.get("/api/leaderboard?topic=%25").json()["total"], 0)
        self.assertEqual([r["entity_key"] for r in
                          self.client.get("/api/leaderboard?search=abc").json()["items"]], ["abc"])

    def test_health_reports_every_refreshed_view(self):
        views = self.client.get("/healthz").json()["views_populated"]
        self.assertEqual(set(views), {name for name, _ in refresh.VIEWS})
        self.assertTrue(views["mention_resolution"])


class FacetsCache(AppCase):
    def setUp(self):
        public._facets_cache.update(version=None, at=0.0, value=None)

    def descriptors(self):
        return {d["name"]: d["n"] for d in self.client.get("/api/facets").json()["descriptors"]}

    def test_descriptors_are_kept_until_a_refresh_brings_new_mentions(self):
        self.assertEqual(self.descriptors(), {"cash only": 3})
        with mock.patch.object(public.queries, "facets", wraps=public.queries.facets) as scan:
            self.descriptors()
            self.descriptors()
        self.assertEqual(scan.call_count, 0)

        with self.conn.cursor() as cur:
            for i in (6, 7, 8):
                cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key, descriptors,
                                                     dishes, aspects, model_version, prompt_hash)
                               values (%s, 'Lucali', 'lucali', '["hole in the wall"]', '[]',
                                       '{"food": 0.5}', 'm', 'p2')""", (f"t1_c{i}",))
        self.conn.commit()
        try:
            self.assertNotIn("hole in the wall", self.descriptors())    # not refreshed yet
            build_views(self.conn)
            self.assertEqual(self.descriptors(), {"cash only": 3, "hole in the wall": 3})
        finally:
            self.q("delete from mentions where prompt_hash = 'p2'")
            build_views(self.conn)
