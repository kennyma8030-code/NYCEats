"""The place card's AI summary: GET /api/restaurants/{key} carries
`place_summary`, null for the many places without one and when the table is
absent, and never the table's bookkeeping columns.

The database tests need TEST_DATABASE_URL (tests/pgtest.py).
"""

import unittest
from unittest import mock

from psycopg2.errors import UndefinedTable

from apptest import AppCase
from app import queries


class Wiring(unittest.TestCase):
    def test_missing_table_is_none_and_rolled_back(self):
        conn = mock.Mock()
        gone = mock.Mock(side_effect=UndefinedTable())
        self.assertIsNone(queries.place_summary(conn, "k", gone))
        conn.rollback.assert_called_once()


class Summary(AppCase):
    def detail(self, key="cellos"):
        r = self.client.get(f"/api/restaurants/{key}")
        self.assertEqual(r.status_code, 200)
        return r.json()

    def put(self, key, summary):
        self.q("""insert into place_summaries (resolved_key, summary, model, mention_count,
                      input_comments, written_at, seen_comment_ids, cost_usd, error, attempts)
                  values (%s, %s, 'm1', 7, 5, '2026-10-03', array['t1_c1'], 0.01, 'secret', 2)
                  on conflict (resolved_key) do update set summary = excluded.summary""",
               key, summary)

    def test_a_place_with_a_summary(self):
        self.put("cellos", "Regulars love the slice.")
        s = self.detail()["place_summary"]
        self.assertEqual((s["text"], s["comment_count"], s["model"]),
                         ("Regulars love the slice.", 7, "m1"))
        self.assertTrue(s["written_at"].startswith("2026-10-03"))
        # Bookkeeping stays server side.
        self.assertEqual(set(s), {"text", "comment_count", "written_at", "model"})

    def test_a_place_without_a_row(self):
        self.assertIsNone(self.detail("katzs")["place_summary"])

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
