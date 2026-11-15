"""/api/extractions/{id}: what v6 thread mode took from one comment or post,
read for the page's city with that city's own thread prompt."""

from psycopg2.extras import Json

from apptest import NOW, AppCase
import prompt_v6

THREAD = "d92ec8610d8c"
COMMENT = "979dcd6b9267"
LA = "FoodLosAngeles"
LA_THREAD = prompt_v6.thread_prompt(LA)[1]


class Extraction(AppCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with cls.conn.cursor() as cur:
            # t1_c1 already has a legacy Cellos row from the seed. Add a v6
            # thread-mode row and a comment-mode row to it, a post mention,
            # and a v6 state row for an item with no mentions.
            cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key, model_version,
                               prompt_hash, schema_version, overall_level, taste_level, value_level,
                               dish_opinions, price_level, timeframe)
                           values ('t1_c1', 'Cello''s', 'cellos', 'v6', %s, 6, 2, 2, -1, %s, 1, 'current')""",
                        (THREAD, Json([{"dish": "slice", "level": 2, "avoid": False}])))
            cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key, model_version,
                               prompt_hash, schema_version, overall_level)
                           values ('t1_c1', 'Joe''s', 'joes', 'v6', %s, 6, -2)""", (COMMENT,))
            cur.execute("""insert into mentions (thread_id, restaurant_raw, entity_key, model_version,
                               prompt_hash, schema_version, overall_level)
                           values ('t3_a', 'Cellos', 'cellos', 'v6', %s, 6, 1)""", (THREAD,))
            cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash, extracted_at)
                           values ('t1_c4', 'v6', 'comment', %s, now())""", (COMMENT,))
            # A Los Angeles comment, read by Los Angeles's thread prompt.
            cur.execute("""insert into threads (id, subreddit, title, created_utc)
                           values ('t3_la', %s, 'Best tacos?', %s)""", (LA, NOW))
            cur.execute("""insert into comments (id, subreddit, thread_id, parent_id, author, body,
                                                 permalink, created_utc, score, score_settled)
                           values ('t1_la1', %s, 't3_la', 't3_la', 'x', 'tacos', '/r/x/1/', %s, 1, true)""",
                        (LA, NOW))
            cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key, model_version,
                               prompt_hash, schema_version, overall_level)
                           values ('t1_la1', 'Cellos', 'cellos', 'v6', %s, 6, 1)""", (LA_THREAD,))
            cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash, extracted_at)
                           values ('t1_la1', 'v6', 'comment', %s, now())""", (LA_THREAD,))
        cls.conn.commit()

    def get(self, item_id, sub=None):
        r = self.client.get(f"/api/extractions/{item_id}", params={"subreddit": sub} if sub else None)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_only_thread_mode_is_shown(self):
        body = self.get("t1_c1")
        self.assertEqual([g["label"] for g in body["groups"]], ["v6 thread mode"])
        self.assertEqual([m["entity_key"] for m in body["groups"][0]["mentions"]], ["cellos"])
        v6 = body["groups"][0]["mentions"][0]
        self.assertEqual((v6["overall_level"], v6["taste_level"], v6["value_level"]), (2, 2, -1))
        self.assertIsNone(v6["service_level"])
        self.assertEqual(v6["dish_opinions"][0]["dish"], "slice")
        self.assertEqual(v6["resolved_key"], "cellos")

    def test_a_post_is_found_by_thread_id(self):
        body = self.get("t3_a")
        self.assertEqual(body["groups"][0]["label"], "v6 thread mode")
        self.assertEqual([m["entity_key"] for m in body["groups"][0]["mentions"]], ["cellos"])

    def test_extracted_nothing_differs_from_never_extracted(self):
        read = self.get("t1_c4")
        self.assertEqual(read["groups"], [])  # its only row is legacy
        self.assertIsNotNone(read["state"]["extracted_at"])
        never = self.get("t1_c7")
        self.assertEqual(never["groups"], [])
        self.assertIsNone(never["state"])

    def test_a_citys_item_is_read_with_its_own_thread_prompt(self):
        self.assertNotEqual(LA_THREAD, THREAD)
        body = self.get("t1_la1", LA)
        self.assertEqual([g["prompt_hash"] for g in body["groups"]], [LA_THREAD])
        self.assertEqual(body["groups"][0]["label"], "v6 thread mode")
        m = body["groups"][0]["mentions"][0]
        # "cellos" is a place in New York's alias table, not in Los Angeles's:
        # the views were built before this comment was added.
        self.assertEqual((m["entity_key"], m["resolved_key"]), ("cellos", None))
        self.assertIsNotNone(body["state"]["extracted_at"])

    def test_an_item_is_not_shown_under_another_city(self):
        for item, sub in (("t1_la1", None), ("t1_c1", LA), ("t3_a", LA), ("t1_c4", LA)):
            body = self.get(item, sub)
            self.assertEqual((body["groups"], body["state"]), ([], None), (item, sub))
        self.assertEqual(self.client.get("/api/extractions/t1_c1?subreddit=nowhere").status_code, 422)

    def test_bad_ids_are_refused(self):
        for bad in ("c1", "t2_c1", "t1_C1", "t1_c1'--", "t1_"):
            self.assertEqual(self.client.get(f"/api/extractions/{bad}").status_code, 422, bad)
