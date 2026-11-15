"""The place card's AI summary: GET /api/restaurants/{key} carries
`place_summary`, null for the many places without one and when the table is
absent, and never the table's bookkeeping columns.

The database tests need TEST_DATABASE_URL (tests/pgtest.py).
"""

import unittest
from unittest import mock

from psycopg2.errors import UndefinedTable

from apptest import AppCase
import subreddits
from app import queries

HOME = subreddits.HOME
LA = "FoodLosAngeles"


class Wiring(unittest.TestCase):
    # Cleared before too: any earlier card load in the run leaves the answer cached.
    def setUp(self):
        queries.forget_summary_ready()

    def tearDown(self):
        queries.forget_summary_ready()

    def test_missing_table_is_none_and_rolled_back(self):
        conn = mock.Mock()
        never = mock.Mock(side_effect=AssertionError("queried"))
        absent = mock.Mock(return_value=False)
        self.assertIsNone(queries.place_summary(conn, HOME, "k", never, absent))
        # The answer is cached: a second card load does not look again.
        self.assertIsNone(queries.place_summary(conn, HOME, "k", never, absent))
        absent.assert_called_once()
        # Dropped after the check: rolled back, and the next call looks again.
        gone = mock.Mock(side_effect=UndefinedTable())
        queries._summary_ready.update(at=queries.time.monotonic(), ready=True)
        self.assertIsNone(queries.place_summary(conn, HOME, "k", gone, absent))
        conn.rollback.assert_called_once()
        self.assertIsNone(queries._summary_ready["at"])


class Summary(AppCase):
    def setUp(self):
        queries.forget_summary_ready()

    def detail(self, key="cellos"):
        r = self.client.get(f"/api/restaurants/{key}")
        self.assertEqual(r.status_code, 200)
        return r.json()

    def put(self, key, summary, sub=HOME):
        self.q("""insert into place_summaries (subreddit, resolved_key, summary, model,
                      mention_count, input_comments, written_at, seen_comment_ids, cost_usd,
                      error, attempts)
                  values (%s, %s, %s, 'm1', 7, 5, '2026-10-03', array['t1_c1'], 0.01, 'secret', 2)
                  on conflict (subreddit, resolved_key) do update
                      set summary = excluded.summary""",
               sub, key, summary)

    def test_a_place_with_a_summary(self):
        self.put("cellos", "Regulars love the slice.")
        s = self.detail()["place_summary"]
        # input_comments (5), not mention_count (7).
        self.assertEqual((s["text"], s["comment_count"]), ("Regulars love the slice.", 5))
        self.assertTrue(s["written_at"].startswith("2026-10-03"))
        # Bookkeeping stays server side.
        self.assertEqual(set(s), {"text", "comment_count", "written_at"})

    def test_a_place_without_a_row(self):
        self.assertIsNone(self.detail("katzs")["place_summary"])

    def test_another_citys_summary_of_the_same_name_is_not_shown(self):
        # A summary is keyed by subreddit and name: Los Angeles's place of
        # the same name is a different place, so New York's card neither
        # loses its own summary to it nor borrows it when it has none. The
        # rows are put here because the class shares one database.
        self.put("cellos", "Regulars love the slice.")
        self.put("cellos", "An LA place of the same name.", sub=LA)
        self.assertEqual(self.detail()["place_summary"]["text"], "Regulars love the slice.")
        self.put("katzs", None)
        self.put("katzs", "An LA deli of the same name.", sub=LA)
        self.assertIsNone(self.detail("katzs")["place_summary"])

    def test_a_table_keyed_by_name_alone_is_none(self):
        # A table from before the per-city key has no subreddit to read by;
        # the card treats it as absent instead of failing on every load.
        self.q("alter table place_summaries rename column subreddit to subreddit_off")
        try:
            self.assertIsNone(self.detail()["place_summary"])
            self.assertTrue(self.detail()["aspects"] is not None)
        finally:
            self.q("alter table place_summaries rename column subreddit_off to subreddit")

    def test_a_null_summary_is_none(self):
        self.put("katzs", None)
        self.assertIsNone(self.detail("katzs")["place_summary"])

    def test_without_the_table(self):
        self.q("alter table place_summaries rename to place_summaries_off")
        try:
            self.assertIsNone(self.detail()["place_summary"])
            # The connection was left usable: the rest of the card still loads.
            self.assertTrue(self.detail()["aspects"] is not None)
        finally:
            self.q("alter table place_summaries_off rename to place_summaries")


if __name__ == "__main__":
    unittest.main()
