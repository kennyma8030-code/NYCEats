"""Two cities behind one API: `?subreddit=` picks the board, a place is
(subreddit, entity_key), and nothing read for one city is another's.

Both cities have a place keyed "alpha". New York likes its one; Los Angeles
does not like its own.
"""

from datetime import timedelta
from unittest import mock

import apptest
from apptest import NOW, AppCase
import subreddits
from app import images, queries
from app.routers import admin, public

HOME = subreddits.HOME
LA = "FoodLosAngeles"


def seed(conn):
    """v6 rows, read live.

    r/FoodNYC          alpha   12 people stated +1
                       beta    3 people stated +1
    r/FoodLosAngeles   alpha   10 people stated -1, 1 stated +1, and one more
                               +1 typed "alfa", which only LA merges into alpha
                       gamma   11 people stated +1 (a name New York never typed)
    """
    plan = {
        HOME: [("alpha", 1)] * 12 + [("beta", 1)] * 3,
        LA: [("alpha", -1)] * 10 + [("alpha", 1), ("alfa", 1)] + [("gamma", 1)] * 11,
    }
    with conn.cursor() as cur:
        for sub, rows in plan.items():
            cur.execute("""insert into threads (id, subreddit, title, created_utc)
                           values (%s, %s, 'Where to eat?', %s)""",
                        (f"t3_{sub}", sub, NOW - timedelta(days=3)))
            for n, (key, level) in enumerate(rows):
                cid = f"t1_{sub[4:7].lower()}{n}"
                cur.execute("""insert into comments (id, subreddit, thread_id, parent_id, author,
                                                     body, permalink, created_utc, score,
                                                     score_settled)
                               values (%s, %s, %s, %s, %s, %s, %s, %s, 1, true)""",
                            (cid, sub, f"t3_{sub}", f"t3_{sub}", f"{sub[4:7]}{n}",
                             f"{key} in r/{sub}", f"/r/{sub}/comments/x/{n}/",
                             NOW - timedelta(days=1, minutes=n)))
                cur.execute("""insert into extraction_state (item_id, version, kind, prompt_hash,
                                                             extracted_at)
                               values (%s, 'v6', 'comment', 'p6', now())""", (cid,))
                cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key,
                                                     model_version, prompt_hash, schema_version,
                                                     kind, opinion, overall_level, descriptors)
                               values (%s, %s, %s, 'm', 'p6', 6, 'restaurant', 'stated', %s,
                                       '["patio"]')""", (cid, key, key, level))
        cur.execute("""insert into restaurants (name, name_key, cuisine, boroughs)
                       values ('ALPHA NYC', 'alpha', 'Pizza', '{Queens}')""")
        cur.execute("""insert into city_restaurants (subreddit, name, name_key, areas, source)
                       values (%s, 'Alpha LA', 'alpha', '{Pasadena}', 'test')""", (LA,))
        cur.execute("""insert into alias_overrides (subreddit, entity_key, resolved_key, note)
                       values (%s, 'alfa', 'alpha', 'test')""", (LA,))
        cur.execute("update extraction_settings set read_version = 'v6'")
    conn.commit()


class Cities(AppCase):
    @classmethod
    def setUpClass(cls):
        with mock.patch.object(apptest, "seed", seed):
            super().setUpClass()

    def setUp(self):
        queries.forget_rating_ready()
        public._facets_cache.clear()

    def get(self, path, sub=None, **params):
        if sub:
            params["subreddit"] = sub
        r = self.client.get(path, params=params)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_the_cities_with_a_board(self):
        self.assertEqual(self.get("/api/cities"), [
            {"subreddit": HOME, "name": "New York City", "short": "NYC", "home": True, "places": 2},
            {"subreddit": LA, "name": "Los Angeles", "short": "LA", "home": False, "places": 2},
        ])

    def test_no_subreddit_is_new_york_and_an_unknown_one_is_refused(self):
        self.assertEqual(self.get("/api/leaderboard"), self.get("/api/leaderboard", HOME))
        # Matched like the poller's settings: any case, with or without r/.
        self.assertEqual(self.get("/api/leaderboard", "r/foodlosangeles"),
                         self.get("/api/leaderboard", LA))
        for path in ("/api/leaderboard", "/api/ledger", "/api/boards", "/api/feed", "/api/stats",
                     "/api/facets", "/api/names", "/api/search?q=a", "/api/restaurants/alpha",
                     "/api/restaurants/alpha/mentions", "/api/restaurants/alpha/voices"):
            r = self.client.get(path, params={"subreddit": "FoodBoston"})
            self.assertEqual(r.status_code, 422, path)
            self.assertIn("FoodBoston", r.json()["detail"])

    def test_one_name_is_two_places(self):
        home, la = self.get("/api/restaurants/alpha"), self.get("/api/restaurants/alpha", LA)
        self.assertEqual((home["summary"]["official_name"], home["summary"]["cuisine"],
                          home["summary"]["boroughs"], home["summary"]["raw_mentions"]),
                         ("ALPHA NYC", "Pizza", ["Queens"], 12))
        self.assertEqual((la["summary"]["official_name"], la["summary"]["cuisine"],
                          la["summary"]["boroughs"], la["summary"]["raw_mentions"]),
                         ("Alpha LA", None, ["Pasadena"], 12))
        self.assertEqual((home["rating"]["pos"], home["rating"]["neg"]), (12, 0))
        self.assertEqual((la["rating"]["pos"], la["rating"]["neg"]), (2, 10))
        # The merge is Los Angeles's: New York never typed "alfa", and has no such spelling.
        self.assertEqual([s["entity_key"] for s in home["spellings"]], ["alpha"])
        self.assertEqual([(s["entity_key"], s["method"], s["mentions"]) for s in la["spellings"]],
                         [("alpha", "exact", 11), ("alfa", "manual", 1)])
        self.assertEqual(home["top_descriptors"], [{"name": "patio", "n": 12}])
        # A place only one city has is a 404 in the other.
        self.assertEqual(self.get("/api/restaurants/gamma", LA)["summary"]["raw_mentions"], 11)
        self.assertEqual(self.client.get("/api/restaurants/gamma").status_code, 404)
        self.assertEqual(self.client.get("/api/restaurants/beta", params={"subreddit": LA}).status_code, 404)

    def test_evidence_is_the_citys_own(self):
        for sub, prefix, voices in ((HOME, "t1_nyc", dict(pos=12, neg=0)), (LA, "t1_los", dict(pos=2, neg=10))):
            page = self.get("/api/restaurants/alpha/mentions", sub, limit=200)
            self.assertEqual(page["total"], 12, sub)
            self.assertTrue(all(m["comment_id"].startswith(prefix) for m in page["items"]), sub)
            for voice, n in voices.items():
                page = self.get("/api/restaurants/alpha/voices", sub, voice=voice)
                self.assertEqual(page["total"], n, (sub, voice))
                self.assertTrue(all(m["comment_id"].startswith(prefix) for m in page["items"]))

    def test_boards_and_lists_are_per_city(self):
        def keys(path, sub=None, **params):
            return [i["entity_key"] for i in self.get(path, sub, **params)["items"]]
        self.assertEqual(keys("/api/leaderboard", sort="mentions"), ["alpha", "beta"])
        self.assertEqual(keys("/api/leaderboard", LA, sort="mentions"), ["alpha", "gamma"])
        self.assertEqual(keys("/api/ledger", category="top", window=7), ["alpha", "beta"])
        self.assertEqual(sorted(keys("/api/ledger", LA, category="top", window=7)), ["alpha", "gamma"])
        self.assertEqual(self.get("/api/ledger/entity", LA, key="alpha")["name"], "Alpha LA")
        # Each city's lines are cut from its own places: New York's only
        # rankable place is alpha, Los Angeles's best liked is gamma.
        home, la = self.get("/api/boards", board="top"), self.get("/api/boards", LA, board="top")
        self.assertEqual(([i["entity_key"] for i in home["items"]], home["lines"]["busy_line"]),
                         (["alpha"], 12))
        self.assertEqual(([i["entity_key"] for i in la["items"]], la["lines"]["busy_line"]),
                         (["gamma"], 11))
        self.assertEqual(home["items"][0]["rating"]["badge"], "consensus")
        # The same name, badged against its own city: busy in New York, not in Los Angeles.
        self.assertFalse(self.get("/api/restaurants/alpha", LA)["rating"]["busy"])
        self.assertEqual([r[0] for r in self.get("/api/names", min_mentions=1)], ["alpha", "beta"])
        la_names = {r[0]: r for r in self.get("/api/names", LA, min_mentions=1)}
        self.assertEqual(set(la_names), {"alpha", "gamma"})
        self.assertEqual((la_names["alpha"][1], la_names["alpha"][3], la_names["alpha"][5]),
                         ("Alpha LA", "Pasadena", ["alfa"]))
        self.assertEqual(self.get("/api/search", q="gam"), [])
        self.assertEqual([h["entity_key"] for h in self.get("/api/search", LA, q="gam")], ["gamma"])
        self.assertEqual(keys("/api/leaderboard", descriptor="patio", sort="mentions"), ["alpha", "beta"])
        self.assertEqual(keys("/api/leaderboard", LA, topic="where to eat", sort="mentions"),
                         ["alpha", "gamma"])

    def test_facets_stats_and_feed_are_per_city(self):
        home, la = self.get("/api/facets"), self.get("/api/facets", LA)
        self.assertEqual((home["cuisines"], home["boroughs"]),
                         ([{"name": "Pizza", "n": 1}], [{"name": "Queens", "n": 1}]))
        self.assertEqual((la["cuisines"], la["boroughs"]), ([], [{"name": "Pasadena", "n": 1}]))
        self.assertEqual((home["descriptors"], la["descriptors"]),
                         ([{"name": "patio", "n": 15}], [{"name": "patio", "n": 23}]))
        self.assertEqual({s["name"]: s["n"] for s in la["statuses"]},
                         {"exact": 1, "unlisted": 1, "unverified": 1})
        home, la = self.get("/api/stats"), self.get("/api/stats", LA)
        self.assertEqual((home["mentions"], home["entities"], home["comments"], home["extracted"],
                          home["threads"]), (15, 2, 15, 15, 1))
        self.assertEqual((la["mentions"], la["entities"], la["comments"], la["extracted"],
                          la["threads"]), (23, 2, 23, 23, 1))
        feed = self.get("/api/feed", LA, limit=200)["items"]
        self.assertEqual(len(feed), 24)                                   # 23 comments and the post
        self.assertTrue(all(i["id"].startswith(("t1_los", "t3_Food")) for i in feed))
        self.assertEqual({p["key"] for i in feed for p in i["places"]}, {"alpha", "gamma"})
        named = {p["name"] for i in feed for p in i["places"] if p["key"] == "alpha"}
        self.assertEqual(named, {"Alpha LA"})                             # not ALPHA NYC

    def test_a_picture_is_cached_for_one_citys_place(self):
        found = {"status": "found", "source": "wikimedia", "source_ref": "Q1", "url": "https://x/y.jpg",
                 "attribution": "someone", "license": "CC BY-SA 4.0",
                 "source_url": "https://www.wikidata.org/wiki/Q1"}
        asked = []

        def fake(entity_key, display_name, sub):
            asked.append((entity_key, display_name, sub))
            return dict(found, source_ref="Q-" + sub), True

        try:
            with mock.patch.object(images, "resolve", fake):
                self.assertEqual(self.get("/api/restaurants/alpha/image")["source_ref"], "Q-" + HOME)
                # New York's cached picture does not answer for Los Angeles's alpha.
                self.assertEqual(self.get("/api/restaurants/alpha/image", LA)["source_ref"], "Q-" + LA)
                self.assertEqual(self.get("/api/restaurants/alpha/image")["source_ref"], "Q-" + HOME)
            self.assertEqual(asked, [("alpha", "ALPHA NYC", HOME), ("alpha", "Alpha LA", LA)])
            self.assertEqual(sorted(self.q("select subreddit, source_ref from restaurant_images")),
                             [(LA, "Q-" + LA), (HOME, "Q-" + HOME)])
        finally:
            self.q("delete from restaurant_images")

    def test_a_photo_is_only_ever_of_the_citys_own_place(self):
        # Every subreddit collected has its own Wikidata city, and no two share one.
        self.assertEqual(set(images.CITY_QIDS), set(subreddits.SUBREDDITS))
        for a in subreddits.SUBREDDITS:
            for b in subreddits.SUBREDDITS:
                if a != b:
                    self.assertFalse(images.CITY_QIDS[a] & images.CITY_QIDS[b], (a, b))
        with mock.patch.object(images, "_wikidata_match") as match:
            self.assertEqual(images.resolve("alpha", "Alpha", "FoodBoston"), (images.MISS, True))
            match.assert_not_called()                                      # no city to check against
            match.return_value = None
            images.resolve("alpha", "Alpha", LA)
            match.assert_called_with("alpha", images.CITY_QIDS[LA])

    def test_identity_decisions_are_per_city(self):
        with mock.patch.object(admin, "ADMIN_TOKEN", "s3cret"):
            auth = {"X-Admin-Token": "s3cret"}

            def aliases(sub=None):
                r = self.client.get("/api/admin/aliases", headers=auth,
                                    params={"subreddit": sub} if sub else None)
                return [(a["subreddit"], a["entity_key"], a["resolved_key"]) for a in r.json()["items"]]
            self.assertEqual(aliases(), [])
            self.assertEqual(aliases(LA), [(LA, "alfa", "alpha")])
            try:
                r = self.client.post("/api/admin/aliases", headers=auth,
                                     json={"entity_key": "alfa", "resolved_key": "beta"})
                self.assertEqual((r.status_code, r.json()["subreddit"]), (201, HOME))
                self.assertEqual(aliases(), [(HOME, "alfa", "beta")])
                self.assertEqual(aliases(LA), [(LA, "alfa", "alpha")])      # untouched
                queue = self.client.get("/api/admin/unresolved", headers=auth,
                                        params={"subreddit": LA}).json()["items"]
                self.assertEqual([u["entity_key"] for u in queue], ["gamma"])
                self.assertEqual(self.client.delete("/api/admin/aliases/alfa", headers=auth).status_code, 204)
                self.assertEqual(self.client.delete("/api/admin/aliases/alfa", headers=auth).status_code, 404)
            finally:
                self.q("delete from alias_overrides where subreddit = %s", HOME)
            self.assertEqual(aliases(LA), [(LA, "alfa", "alpha")])
