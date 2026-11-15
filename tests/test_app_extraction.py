"""/api/extractions/{id}: what v6 thread mode took from one comment or post,
read for the page's city with that city's own thread prompt."""

from unittest import mock

from psycopg2.errors import UndefinedTable
from psycopg2.extras import Json

from apptest import NOW, AppCase
from app import queries
from app.routers import extraction
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
            # t1_c4 was last read in comment mode and t1_c5 in thread mode,
            # both finding nothing; t1_c6's thread-mode read failed.
            cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash, extracted_at)
                           values ('t1_c4', 'v6', 'comment', %s, now())""", (COMMENT,))
            cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash, extracted_at)
                           values ('t1_c5', 'v6', 'comment', %s, now())""", (THREAD,))
            cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash, extract_error,
                                                         model, attempts, cost_usd)
                           values ('t1_c6', 'v6', 'comment', %s, 'schema: secret detail', 'some-model', 3, 0.5)""",
                        (THREAD,))
            # t1_c2's row names no prompt (the column is nullable). t1_c3
            # was read under an older prompt, found nothing, and is now in a
            # batch under this one: the batch set the row's prompt and left
            # the old read's time.
            cur.execute("""insert into extraction_state (item_id, version, kind, extracted_at)
                           values ('t1_c2', 'v6', 'comment', now())""")
            cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash, batch_id, extracted_at)
                           values ('t1_c3', 'v6', 'comment', %s, 'msgbatch_1', now() - interval '21 days')""",
                        (THREAD,))
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

    def setUp(self):
        queries.forget_v6_ready()

    def test_extracted_nothing_differs_from_never_extracted(self):
        read = self.get("t1_c5")
        self.assertEqual(read["groups"], [])
        self.assertIsNotNone(read["state"]["extracted_at"])
        self.assertEqual((read["state"]["this_prompt"], read["state"]["failed"]), (True, False))
        never = self.get("t1_c7")
        self.assertEqual(never["groups"], [])
        self.assertIsNone(never["state"])

    def test_a_read_under_another_prompt_is_not_passed_off_as_this_one(self):
        # t1_c4's cursor row is its comment-mode read: it says nothing about
        # what thread mode found, and the response says so.
        other = self.get("t1_c4")
        self.assertEqual(other["groups"], [])
        self.assertFalse(other["state"]["this_prompt"])
        # t1_c1 has thread-mode rows and no cursor row at all.
        self.assertIsNone(self.get("t1_c1")["state"])

    def test_a_row_with_no_prompt_is_not_this_prompts_and_does_not_break_the_route(self):
        # `null = hash` is null, which the response's bool refused: a 500.
        state = self.get("t1_c2")["state"]
        self.assertIs(state["this_prompt"], False)

    def test_an_item_only_queued_under_this_prompt_is_not_said_to_have_been_read(self):
        state = self.get("t1_c3")["state"]
        self.assertEqual(state, {"extracted_at": None, "failed": False, "this_prompt": True, "pending": True})
        self.assertFalse(self.get("t1_c5")["state"]["pending"])

    def test_the_pipelines_bookkeeping_is_not_in_a_public_response(self):
        failed = self.get("t1_c6")
        self.assertEqual(failed["state"],
                         {"extracted_at": None, "failed": True, "this_prompt": True, "pending": False})
        body = self.get("t1_c1")
        self.assertEqual(sorted(body["groups"][0]), ["created_at", "label", "mentions", "prompt_hash"])
        for word in ("secret detail", "some-model", "cost_usd", "attempts", "extract_error", "model_version"):
            self.assertNotIn(word, str(failed) + str(body), word)

    def test_a_database_without_v6_storage_answers_as_never_extracted(self):
        # Checked in the catalog first; and dropped since the check, the
        # failed statement is rolled back and the check forgotten.
        absent = lambda conn, sql, params=None, default=None: False       # noqa: E731
        never = mock.Mock(side_effect=AssertionError("queried a schema that is not there"))
        conn = mock.Mock()
        self.assertIsNone(queries.item_extraction(conn, "FoodNYC", "t1_c1", THREAD, never, never, absent))
        queries._v6_ready.update(at=queries.time.monotonic(), ready=True)
        gone = mock.Mock(side_effect=UndefinedTable("extraction_state"))
        self.assertIsNone(queries.item_extraction(conn, "FoodNYC", "t1_c1", THREAD, gone, never, absent))
        conn.rollback.assert_called_once()
        self.assertIsNone(queries._v6_ready["at"])
        with mock.patch.object(queries, "item_extraction", return_value=None):
            body = self.get("t1_c1")
        self.assertEqual((body["groups"], body["state"]), ([], None))

    def test_a_prompt_that_cannot_be_built_fails_this_route_only(self):
        # The hashes used to be computed when the module was imported, where
        # the same error stopped the app from starting.
        extraction.thread_hash.cache_clear()
        try:
            with mock.patch.object(prompt_v6, "thread_prompt", side_effect=ValueError("the prompt still says NYC")):
                r = self.client.get("/api/extractions/t1_c1")
            self.assertEqual(r.status_code, 503)
            # The reason is the log's; the public answer is a fixed line.
            self.assertEqual(r.json()["detail"], "the extraction prompt for this city could not be built")
            # A bug is not a bad prompt: it is not turned into a 503 to retry.
            with mock.patch.object(prompt_v6, "thread_prompt", side_effect=TypeError("a bug")):
                with self.assertRaises(TypeError):
                    self.client.get("/api/extractions/t1_c1")
            self.assertEqual(self.client.get("/api/cities").status_code, 200)
        finally:
            extraction.thread_hash.cache_clear()
        self.assertEqual(self.get("t1_c1")["groups"][0]["label"], "v6 thread mode")      # not cached as failed

    def test_each_kind_of_item_is_read_by_its_own_column(self):
        # A comment id never matches a post's rows or the other way round,
        # and neither statement ORs the two columns (no index serves that).
        sqls = []
        real = queries.item_extraction

        def fetch_all(conn, sql, params=None):
            sqls.append(sql)
            return []
        for item in ("t1_c1", "t3_a"):
            real(self.conn, "FoodNYC", item, THREAD, fetch_all, lambda *a, **k: None,
                 lambda *a, **k: True)
        self.conn.rollback()
        self.assertIn("m.comment_id = %(id)s", sqls[0])
        self.assertNotIn("thread_id", sqls[0])
        self.assertIn("m.thread_id = %(id)s and m.comment_id is null", sqls[1])
        self.assertNotRegex(sqls[0] + sqls[1], r"comment_id = %\(id\)s or")

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
