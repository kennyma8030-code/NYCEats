"""The rating (scoring.sql, section 8): stated opinions make % positive, bare
recommendations only the volume, one voice per person, and every count
clicks through to exactly the comments it counted.

The pure checks run anywhere. The database ones need TEST_DATABASE_URL
(tests/pgtest.py) and seed one place whose every count is worked out by hand
below, so a change to the voice rules shows up as a wrong number.
"""

import unittest
from datetime import timedelta
from unittest import mock

import apptest
from apptest import NOW, AppCase

import refresh
import subreddits
from app import queries
from app.models import RATING_CATEGORIES, RatingBoard, VoiceFilter
from app.routers.ledger import build_rating
from typing import get_args

RATING_VIEWS = ("place_voices", "place_category_voices", "entity_rating", "entity_category_rating")


class Wiring(unittest.TestCase):
    def test_every_board_and_voice_is_whitelisted(self):
        self.assertEqual(set(get_args(RatingBoard)),
                         set(queries.RATING_BOARDS) | set(RATING_CATEGORIES))
        self.assertEqual(set(get_args(VoiceFilter)), set(queries.VOICE_FILTERS))

    def test_rating_views_refresh_after_their_inputs(self):
        order = [name for name, _ in refresh.VIEWS]
        at = {name: order.index(name) for name in RATING_VIEWS}
        self.assertLess(order.index("mention_weights"), at["place_voices"])
        self.assertLess(at["place_voices"], at["entity_rating"])
        self.assertLess(at["place_category_voices"], at["entity_category_rating"])
        with open(refresh.os.path.join(refresh.HERE, "scoring.sql"), encoding="utf-8") as f:
            created = refresh.created_views(f.read())
        self.assertTrue(set(RATING_VIEWS) <= set(created))

    def test_build_rating(self):
        self.assertIsNone(build_rating({"rating_pos": None, "rating_window_days": 365}, []))
        cat = dict(category="wait", pos=1, neg=0, neutral=0, pct_pos=1.0, lb=0.4, rankable=False)
        only_cat = build_rating({"rating_pos": None, "rating_window_days": 365}, [cat])
        self.assertEqual((only_cat.pos, only_cat.recommenders, only_cat.badge), (0, 0, None))
        self.assertEqual(only_cat.categories["wait"].lb, 0.4)


def seed(conn):
    """One thread, place "alpha" and place "beta", all v6 rows read live.

    alpha, voice by voice:
      a1..a10   stated +1 (a1 at +2), taste +1           10 pos, 1 superlative
      flip      stated -1, then later +1                  latest wins: pos
      [deleted] two comments, stated +1                   two people: 2 pos
      n1        stated -1, taste -1                       neg
      n2        avoid, no level                           neg
      z         stated 0                                  neutral
      e1..e3    endorse (e1 with taste +1)                3 endorse, no taste
      a2 again  later, stated, no overall, wait -1        not a voice; wait neg
      AutoModerator endorse, c1 stated +1 'closed',
      old1 stated -1 400 days ago                         none of them count
    so pos 13, neg 2, neutral 1, endorse 3, recommenders 16, rankable.
    beta: three stated +1, not rankable.
    """
    rows = []   # (author, minutes ago, key, opinion, overall, avoid, taste, wait, status)
    for i in range(1, 11):
        rows.append((f"a{i}", 100 + i, "alpha", "stated", 2 if i == 1 else 1, False, 1, None, None))
    rows += [
        ("flip", 500, "alpha", "stated", -1, False, None, None, None),
        ("flip", 50, "alpha", "stated", 1, False, None, None, None),
        ("[deleted]", 60, "alpha", "stated", 1, False, None, None, None),
        ("[deleted]", 61, "alpha", "stated", 1, False, None, None, None),
        ("n1", 70, "alpha", "stated", -1, False, -1, None, None),
        ("n2", 71, "alpha", None, None, True, None, None, None),
        ("z", 72, "alpha", "stated", 0, False, None, None, None),
        ("e1", 80, "alpha", "endorse", 1, False, 1, None, None),
        ("e2", 81, "alpha", "endorse", 1, False, None, None, None),
        ("e3", 82, "alpha", "endorse", None, False, None, None, None),
        ("a2", 10, "alpha", "stated", None, False, None, -1, None),
        ("AutoModerator", 90, "alpha", "endorse", 1, False, None, None, None),
        ("c1", 91, "alpha", "stated", 1, False, None, None, "closed"),
        ("old1", 400 * 24 * 60, "alpha", "stated", -1, False, None, None, None),
        ("b1", 30, "beta", "stated", 1, False, None, None, None),
        ("b2", 31, "beta", "stated", 1, False, None, None, None),
        ("b3", 32, "beta", "stated", 1, False, None, None, None),
    ]
    with conn.cursor() as cur:
        cur.execute("""insert into threads (id, subreddit, title, created_utc)
                       values ('t3_r', %s, 'Where to eat?', %s)""",
                    (subreddits.HOME, NOW - timedelta(days=500)))
        for n, (author, ago, key, opinion, overall, avoid, taste, wait, status) in enumerate(rows):
            cid = f"t1_r{n}"
            cur.execute("""insert into comments (id, thread_id, parent_id, author, body, permalink,
                                                 created_utc, score, score_settled, was_deleted_later)
                           values (%s, 't3_r', 't3_r', %s, 'x', %s, %s, 1, true, %s)""",
                        (cid, author, f"/r/{subreddits.HOME}/comments/r/{n}/",
                         NOW - timedelta(minutes=ago), author == "n1"))
            cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key, model_version,
                                                 prompt_hash, schema_version, kind, opinion,
                                                 overall_level, avoid, taste_level, wait_level, status)
                           values (%s, %s, %s, 'm', 'p6', 6, 'restaurant', %s, %s, %s, %s, %s, %s)""",
                        (cid, key, key, opinion or "none", overall, avoid, taste, wait, status))
            cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash, extracted_at)
                           values (%s, 'v6', 'comment', 'p6', now())""", (cid,))
        cur.execute("update extraction_settings set read_version = 'v6'")
    conn.commit()


class Rating(AppCase):
    @classmethod
    def setUpClass(cls):
        with mock.patch.object(apptest, "seed", seed):
            super().setUpClass()

    def test_counts(self):
        r = self.client.get("/api/restaurants/alpha").json()["rating"]
        self.assertEqual((r["pos"], r["neg"], r["neutral"], r["endorse"], r["superlative"],
                          r["recommenders"]), (13, 2, 1, 3, 1, 16))
        self.assertAlmostEqual(r["pct_pos"], 13 / 15)
        self.assertAlmostEqual(r["neg_share"], 2 / 16)
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
        self.assertEqual(top["lines"]["busy_line"], 16)
        self.assertEqual(self.client.get("/api/boards?board=gems").json()["items"], [])
        taste = self.client.get("/api/boards?board=taste").json()
        self.assertEqual([i["entity_key"] for i in taste["items"]], ["alpha"])

    def test_every_count_clicks_through(self):
        def total(qs):
            return self.client.get(f"/api/restaurants/alpha/voices?{qs}").json()["total"]
        self.assertEqual([total(f"voice={v}") for v in
                          ("pos", "neg", "neutral", "endorse", "recommenders", "superlative")],
                         [13, 2, 1, 3, 16, 1])
        self.assertEqual(total("voice=pos&category=taste"), 10)
        self.assertEqual(self.client.get(
            "/api/restaurants/alpha/voices?voice=endorse&category=taste").status_code, 422)
        neg = self.client.get("/api/restaurants/alpha/voices?voice=neg").json()["items"]
        # n1's comment was deleted from Reddit: still counted, never linked.
        gone = [m for m in neg if m["author"] == "n1"]
        self.assertEqual(len(gone), 1)
        self.assertIsNone(gone[0]["permalink"])

    def test_ledger_rows_carry_the_rating(self):
        items = self.client.get("/api/ledger?category=top&window=7").json()["items"]
        alpha = next(i for i in items if i["entity_key"] == "alpha")
        self.assertEqual(alpha["rating"]["recommenders"], 16)
