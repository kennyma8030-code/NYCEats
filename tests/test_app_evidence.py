"""The comments behind a score: legacy rows of the wrong shape, and the
permalink rule, on every endpoint that returns mentions."""

from apptest import AppCase
import subreddits


class Evidence(AppCase):
    def test_mentions_of_the_wrong_shape_do_not_500(self):
        r = self.client.get("/api/restaurants/cellos/mentions?limit=50")
        self.assertEqual(r.status_code, 200, r.text)
        by_comment = {m["comment_id"]: m for m in r.json()["items"]}
        self.assertEqual(set(by_comment), {"t1_c1", "t1_c2", "t1_c3"})
        legacy = by_comment["t1_c1"]
        self.assertIsNone(legacy["descriptors"])
        self.assertIsNone(legacy["dishes"])
        self.assertEqual(legacy["aspects"]["food"], -0.9)
        self.assertIsNone(legacy["aspects"]["value"])        # "cheap" is not a score
        self.assertEqual(by_comment["t1_c2"]["descriptors"], ["slice"])

    def test_deleted_comments_never_link(self):
        items = self.client.get("/api/restaurants/cellos/mentions").json()["items"]
        links = {m["comment_id"]: m["permalink"] for m in items}
        self.assertIsNone(links["t1_c2"])
        self.assertEqual(links["t1_c1"], f"/r/{subreddits.HOME}/comments/a/1/")

    def test_standout_negatives_survive_legacy_rows_and_hide_deleted_links(self):
        r = self.client.get("/api/restaurants/cellos/standout-negatives")
        self.assertEqual(r.status_code, 200, r.text)
        by_comment = {m["comment_id"]: m for m in r.json()}
        self.assertEqual(set(by_comment), {"t1_c1", "t1_c2"})
        self.assertIsNone(by_comment["t1_c1"]["descriptors"])
        self.assertIsNone(by_comment["t1_c2"]["permalink"])

    def test_the_model_tolerates_what_the_sql_would_null(self):
        from app.models import Mention
        m = Mention(mention_id=1, comment_id="t1_x", restaurant_raw="x", typed_key="x",
                    descriptors="solid counter slice joint", dishes={"a": 1},
                    aspects={"food": "good", "wait": True, "value": 0.2})
        self.assertIsNone(m.descriptors)
        self.assertIsNone(m.dishes)
        self.assertEqual(m.aspects, {"food": None, "wait": None, "value": 0.2})
