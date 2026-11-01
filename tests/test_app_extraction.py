"""/api/extractions/{id}: every extraction of one comment or post, v6 first."""

from psycopg2.extras import Json

from apptest import AppCase

THREAD = "d92ec8610d8c"
COMMENT = "979dcd6b9267"


class Extraction(AppCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with cls.conn.cursor() as cur:
            # t1_c1 already has a legacy Cellos row from the seed. Add a v6
            # row to it, a post mention, and a v6 state row for an item with
            # no mentions.
            cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key, model_version,
                               prompt_hash, schema_version, overall_level, taste_level, value_level,
                               dish_opinions, price_level, timeframe)
                           values ('t1_c1', 'Cello''s', 'cellos', 'v6', %s, 6, 2, 2, -1, %s, 1, 'current')""",
                        (COMMENT, Json([{"dish": "slice", "level": 2, "avoid": False}])))
            cur.execute("""insert into mentions (thread_id, restaurant_raw, entity_key, model_version,
                               prompt_hash, schema_version, overall_level)
                           values ('t3_a', 'Cellos', 'cellos', 'v6', %s, 6, 1)""", (THREAD,))
            cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash, extracted_at)
                           values ('t1_c4', 'v6', 'comment', %s, now())""", (COMMENT,))
        cls.conn.commit()

    def get(self, item_id):
        r = self.client.get(f"/api/extractions/{item_id}")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_v6_group_comes_before_legacy(self):
        body = self.get("t1_c1")
        self.assertEqual([g["label"] for g in body["groups"]][0], "v6 comment mode")
        self.assertEqual(body["groups"][1]["prompt_hash"], "p")
        v6 = body["groups"][0]["mentions"][0]
        self.assertEqual((v6["overall_level"], v6["taste_level"], v6["value_level"]), (2, 2, -1))
        self.assertIsNone(v6["service_level"])
        self.assertEqual(v6["dish_opinions"][0]["dish"], "slice")
        self.assertEqual(v6["resolved_key"], "cellos")
        self.assertEqual(body["groups"][1]["mentions"][0]["aspects"]["food"], -0.9)

    def test_a_post_is_found_by_thread_id(self):
        body = self.get("t3_a")
        self.assertEqual(body["groups"][0]["label"], "v6 thread mode")
        self.assertEqual(len(body["groups"][0]["mentions"]), 1)

    def test_extracted_nothing_differs_from_never_extracted(self):
        read = self.get("t1_c4")
        self.assertEqual(read["groups"][0]["mentions"][0]["entity_key"], "abc")  # legacy only
        self.assertIsNotNone(read["state"]["extracted_at"])
        never = self.get("t1_c7")
        self.assertEqual(never["groups"], [])
        self.assertIsNone(never["state"])

    def test_bad_ids_are_refused(self):
        for bad in ("c1", "t2_c1", "t1_C1", "t1_c1'--", "t1_"):
            self.assertEqual(self.client.get(f"/api/extractions/{bad}").status_code, 422, bad)
