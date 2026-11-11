"""The rating (scoring.sql, section 8): latest stated opinions make % positive,
each person's latest word makes the volume, a bare endorse never changes the
rating, and every count clicks through to exactly the comments it counted.

The pure checks run anywhere. The database ones need TEST_DATABASE_URL
(tests/pgtest.py) and seed one place whose every count is worked out by hand
below, so a change to the voice rules shows up as a wrong number.
"""

import unittest
from datetime import timedelta
from typing import get_args
from unittest import mock

from fastapi import HTTPException
from psycopg2.errors import UndefinedColumn, UndefinedTable

import apptest
from apptest import NOW, AppCase

import refresh
import subreddits
from app import queries
from app.models import (CATEGORY_VOICE_FILTERS, OVERALL_BOARDS, RATING_CATEGORIES,
                        RatingBoard, VoiceFilter)
from app.routers.ledger import build_rating, rating_only

RATING_VIEWS = ("rating_mentions", "place_voices", "place_recommenders",
                "place_category_voices", "entity_rating", "entity_category_rating")


class Wiring(unittest.TestCase):
    def tearDown(self):
        queries.forget_rating_ready()

    def test_every_board_and_voice_is_whitelisted(self):
        self.assertEqual(set(get_args(RatingBoard)), set(OVERALL_BOARDS) | set(RATING_CATEGORIES))
        self.assertEqual(set(queries.RATING_BOARDS), set(OVERALL_BOARDS))
        self.assertEqual(set(get_args(VoiceFilter)), set(queries.VOICE_SOURCES))
        self.assertEqual(set(CATEGORY_VOICE_FILTERS), set(queries.CATEGORY_VOICE_SOURCES))

    def test_rating_views_refresh_after_their_inputs(self):
        order = [name for name, _ in refresh.VIEWS]
        at = {name: order.index(name) for name in RATING_VIEWS}
        self.assertLess(order.index("mention_weights"), at["rating_mentions"])
        self.assertLess(at["rating_mentions"],
                        min(at["place_voices"], at["place_recommenders"],
                            at["place_category_voices"]))
        self.assertLess(max(at["place_voices"], at["place_recommenders"]), at["entity_rating"])
        self.assertLess(at["place_category_voices"], at["entity_category_rating"])
        with open(refresh.os.path.join(refresh.HERE, "scoring.sql"), encoding="utf-8") as f:
            created = refresh.created_views(f.read())
        self.assertTrue(set(RATING_VIEWS) | {"rating_params"} <= set(created))
        self.assertEqual(set(queries.RATING_VIEWS), set(RATING_VIEWS) | {"rating_params"})

    def test_build_rating(self):
        self.assertIsNone(build_rating(None))
        cat = dict(category="wait", pos=1, neg=0, neutral=0, pct_pos=1.0, lb=0.4, rankable=False)
        only_cat = build_rating({"overall": None, "categories": [cat], "window_days": 365})
        self.assertEqual((only_cat.pos, only_cat.recommenders, only_cat.badge, only_cat.busy),
                         (0, 0, None, False))
        self.assertEqual(only_cat.categories["wait"].lb, 0.4)

    def test_missing_views_degrade(self):
        """Not built: no rating and no query. Gone under a query: rolled back,
        no rating, and the next call looks again."""
        conn = mock.Mock()
        never = mock.Mock(side_effect=AssertionError("queried"))
        with mock.patch.object(queries, "rating_ready", return_value=False):
            self.assertEqual(queries.ratings_for(conn, "FoodNYC", ["k"], never, never), {})

        gone = mock.Mock(side_effect=UndefinedTable())
        queries._rating_ready.update(at=queries.time.monotonic(), ready=True)
        self.assertEqual(queries.ratings_for(conn, "FoodNYC", ["k"], gone, gone), {})
        conn.rollback.assert_called()
        self.assertIsNone(queries._rating_ready["at"])

        queries._rating_ready.update(at=queries.time.monotonic(), ready=True)
        with mock.patch("app.routers.ledger.fetch_value"):
            with self.assertRaises(HTTPException) as cm:
                rating_only(conn, mock.Mock(side_effect=UndefinedTable()))
        self.assertEqual(cm.exception.status_code, 503)
        self.assertIsNone(queries._rating_ready["at"])

        # An older build's views, missing a column: the same.
        queries._rating_ready.update(at=queries.time.monotonic(), ready=True)
        stale = mock.Mock(side_effect=UndefinedColumn())
        self.assertEqual(queries.ratings_for(conn, "FoodNYC", ["k"], stale, stale), {})
        queries._rating_ready.update(at=queries.time.monotonic(), ready=True)
        with self.assertRaises(UndefinedColumn):
            queries.ratings_for(conn, "FoodNYC", ["k"], stale, stale, strict=True)
        with self.assertRaises(HTTPException) as cm:
            rating_only(conn, lambda: queries.ratings_for(conn, "FoodNYC", ["k"], stale, stale, strict=True))
        self.assertEqual(cm.exception.status_code, 503)


def seed(conn):
    """One thread, place "alpha" and place "beta", all v6 rows read live.

    alpha, person by person (rating = latest stated; volume = latest word):
      a1..a10   stated +1 (a1 at +2), taste +1        pos x10 (1 superlative); pos
      a2 again  later, stated, no overall, wait -1    not a voice at all; wait neg
      flip      stated -1, then later +1              pos; pos
      [deleted] two comments, stated +1               two people: pos x2; pos x2
      pe        stated +1, then later a bare endorse  pos; endorse, recommends
      dt        stated -1, then later a bare endorse  neg; endorse, does NOT recommend
      n1        stated -1, taste -1, comment deleted  neg; neg
      n2        avoid, opinion none, no level         neg (level -1); neg
      sk        avoid on an endorse at level +1       neg (level -1); neg -- never recommends
      z         stated 0                              neutral; neutral
      e1..e3    endorse (e1 with taste +1)            none; endorse x3, no taste
      dup       one comment naming it twice: "alpha x" stated +1 (resolves to
                alpha) and then "alpha" endorse        pos; pos -- the stated one wins the tie
      pd        stated -1, past, trend declined        neg ("better before, now mid"); neg
      pa        stated +1 and taste +1, past, no trend nothing
      sp        avoid, past, no trend                  neg -- an avoid is a neg whatever its time; neg
      AutoModerator endorse, c1 stated +1 'closed', old1 stated -1 400 days ago: nothing
    rating: pos 15, neg 6, neutral 1, superlative 1
    volume: recommenders 14 latest pos + e1..e3 + pe = 18, endorse 4; 25 people
    beta: three stated +1, not rankable.
    """
    # (author, minutes ago, key, opinion, overall, avoid, taste, wait, status,
    #  timeframe, trend, comment)
    rows = []
    for i in range(1, 11):
        rows.append((f"a{i}", 100 + i, "alpha", "stated", 2 if i == 1 else 1, False, 1, None,
                     None, None, None, None))
    rows += [
        ("a2", 10, "alpha", "stated", None, False, None, -1, None, None, None, None),
        ("flip", 500, "alpha", "stated", -1, False, None, None, None, None, None, None),
        ("flip", 50, "alpha", "stated", 1, False, None, None, None, None, None, None),
        ("[deleted]", 60, "alpha", "stated", 1, False, None, None, None, None, None, None),
        ("[deleted]", 61, "alpha", "stated", 1, False, None, None, None, None, None, None),
        ("pe", 300, "alpha", "stated", 1, False, None, None, None, None, None, None),
        ("pe", 20, "alpha", "endorse", 1, False, None, None, None, None, None, None),
        ("dt", 310, "alpha", "stated", -1, False, None, None, None, None, None, None),
        ("dt", 21, "alpha", "endorse", 1, False, None, None, None, None, None, None),
        ("n1", 70, "alpha", "stated", -1, False, -1, None, None, None, None, None),
        ("n2", 71, "alpha", "none", None, True, None, None, None, None, None, None),
        ("sk", 73, "alpha", "endorse", 1, True, None, None, None, None, None, None),
        ("z", 72, "alpha", "stated", 0, False, None, None, None, None, None, None),
        ("e1", 80, "alpha", "endorse", 1, False, 1, None, None, None, None, None),
        ("e2", 81, "alpha", "endorse", 1, False, None, None, None, None, None, None),
        ("e3", 82, "alpha", "endorse", None, False, None, None, None, None, None, None),
        ("dup", 40, "alpha x", "stated", 1, False, None, None, None, None, None, "t1_dup"),
        ("dup", 40, "alpha", "endorse", 1, False, None, None, None, None, None, "t1_dup"),
        ("pd", 44, "alpha", "stated", -1, False, None, None, None, "past", "declined", None),
        ("pa", 45, "alpha", "stated", 1, False, 1, None, None, "past", None, None),
        ("sp", 46, "alpha", "stated", None, True, None, None, None, "past", None, None),
        ("AutoModerator", 90, "alpha", "endorse", 1, False, None, None, None, None, None, None),
        ("c1", 91, "alpha", "stated", 1, False, None, None, "closed", None, None, None),
        ("old1", 400 * 24 * 60, "alpha", "stated", -1, False, None, None, None, None, None, None),
        ("b1", 30, "beta", "stated", 1, False, None, None, None, None, None, None),
        ("b2", 31, "beta", "stated", 1, False, None, None, None, None, None, None),
        ("b3", 32, "beta", "stated", 1, False, None, None, None, None, None, None),
    ]
    with conn.cursor() as cur:
        cur.execute("""insert into threads (id, subreddit, title, created_utc)
                       values ('t3_r', %s, 'Where to eat?', %s)""",
                    (subreddits.HOME, NOW - timedelta(days=500)))
        made = set()
        for n, (author, ago, key, opinion, overall, avoid, taste, wait, status, timeframe,
                trend, cid) in enumerate(rows):
            cid = cid or f"t1_r{n}"
            if cid not in made:
                made.add(cid)
                cur.execute("""insert into comments (id, thread_id, parent_id, author, body,
                                                     permalink, created_utc, score, score_settled,
                                                     was_deleted_later)
                               values (%s, 't3_r', 't3_r', %s, 'x', %s, %s, 1, true, %s)""",
                            (cid, author, f"/r/{subreddits.HOME}/comments/r/{n}/",
                             NOW - timedelta(minutes=ago), author == "n1"))
                cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash,
                                                             extracted_at)
                               values (%s, 'v6', 'comment', 'p6', now())""", (cid,))
            cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key,
                                                 model_version, prompt_hash, schema_version, kind,
                                                 opinion, overall_level, avoid, taste_level,
                                                 wait_level, status, timeframe, trend)
                           values (%s, %s, %s, 'm', 'p6', 6, 'restaurant', %s, %s, %s, %s, %s,
                                   %s, %s, %s)""",
                        (cid, key, key, opinion, overall, avoid, taste, wait, status, timeframe,
                         trend))
        cur.execute("""insert into alias_overrides (entity_key, resolved_key, note)
                       values ('alpha x', 'alpha', 'test')""")
        cur.execute("update extraction_settings set read_version = 'v6'")
    conn.commit()


class Rating(AppCase):
    @classmethod
    def setUpClass(cls):
        with mock.patch.object(apptest, "seed", seed):
            super().setUpClass()

    def setUp(self):
        queries.forget_rating_ready()

    def test_counts(self):
        r = self.client.get("/api/restaurants/alpha").json()["rating"]
        self.assertEqual((r["pos"], r["neg"], r["neutral"], r["superlative"],
                          r["endorse"], r["recommenders"]), (15, 6, 1, 1, 4, 18))
        self.assertAlmostEqual(r["pct_pos"], 15 / 21)
        self.assertAlmostEqual(r["neg_share"], 6 / 21)
        self.assertTrue(r["rankable"] and r["busy"])
        self.assertEqual(r["badge"], "consensus")      # the only rankable place
        self.assertLess(r["lb"], r["pct_pos"])
        taste, wait = r["categories"]["taste"], r["categories"]["wait"]
        self.assertEqual((taste["pos"], taste["neg"], taste["rankable"]), (10, 1, True))
        self.assertEqual((wait["pos"], wait["neg"], wait["rankable"]), (0, 1, False))
        beta = self.client.get("/api/restaurants/beta").json()["rating"]
        self.assertEqual((beta["pos"], beta["rankable"], beta["busy"], beta["badge"]),
                         (3, False, False, None))

    def test_boards(self):
        top = self.client.get("/api/boards?board=top").json()
        self.assertEqual([i["entity_key"] for i in top["items"]], ["alpha"])
        self.assertEqual((top["total"], top["lines"]["busy_line"]), (1, 18))
        past_end = self.client.get("/api/boards?board=top&offset=5").json()
        self.assertEqual((past_end["items"], past_end["total"]), ([], 1))
        self.assertEqual(self.client.get("/api/boards?board=gems").json()["items"], [])
        taste = self.client.get("/api/boards?board=taste").json()
        self.assertEqual([i["entity_key"] for i in taste["items"]], ["alpha"])

    def test_every_count_clicks_through(self):
        def total(qs):
            return self.client.get(f"/api/restaurants/alpha/voices?{qs}").json()["total"]
        self.assertEqual({v: total(f"voice={v}") for v in
                          ("pos", "neg", "neutral", "opinions", "superlative",
                           "endorse", "recommenders", "all")},
                         dict(pos=15, neg=6, neutral=1, opinions=21, superlative=1,
                              endorse=4, recommenders=18, all=25))
        self.assertEqual(total("voice=pos&category=taste"), 10)
        self.assertEqual(total("voice=opinions&category=taste"), 11)
        self.assertEqual(self.client.get(
            "/api/restaurants/alpha/voices?voice=endorse&category=taste").status_code, 422)
        neg = self.client.get("/api/restaurants/alpha/voices?voice=neg").json()["items"]
        # Every neg carries a negative level, avoids included.
        self.assertTrue(all(m["level"] is not None and m["level"] < 0 for m in neg))
        self.assertEqual({m["author"] for m in neg}, {"n1", "n2", "sk", "pd", "dt", "sp"})
        # n1's comment was deleted from Reddit: still counted, never linked.
        self.assertIsNone(next(m for m in neg if m["author"] == "n1")["permalink"])
        recs = self.client.get("/api/restaurants/alpha/voices?voice=recommenders&limit=200").json()
        by = {m["author"]: m["voice"] for m in recs["items"]}
        self.assertEqual((by["pe"], by["dup"]), ("endorse", "pos"))
        self.assertNotIn("sk", by)
        self.assertNotIn("dt", by)

    def test_ledger_rows_carry_the_rating(self):
        items = self.client.get("/api/ledger?category=top&window=7").json()["items"]
        alpha = next(i for i in items if i["entity_key"] == "alpha")
        self.assertEqual(alpha["rating"]["recommenders"], 18)

    def test_without_the_views_the_rating_is_null(self):
        with mock.patch.object(queries, "rating_ready", return_value=False):
            items = self.client.get("/api/ledger?category=top&window=7").json()["items"]
            self.assertTrue(items and all(i["rating"] is None for i in items))
            one = self.client.get("/api/ledger/entity?key=alpha").json()
            self.assertIsNone(one["rating"])
            self.assertIsNone(self.client.get("/api/restaurants/alpha").json()["rating"])
            self.assertEqual(self.client.get("/api/boards").status_code, 503)
            self.assertEqual(self.client.get("/api/restaurants/alpha/voices").status_code, 503)
