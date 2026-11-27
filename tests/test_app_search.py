"""Search: reading a query, and what comes back for it.

The first half needs nothing but a hand-built vocabulary and the local
stand-in for Anthropic's API (tests/fake_anthropic.py). The second half
needs TEST_DATABASE_URL (tests/pgtest.py), and its last class needs pgvector
on that server as well.
"""

import json
import os
import unittest
from unittest import mock

import psycopg2

from fakes import ROOT  # noqa: F401  (puts the repo root on sys.path)
import apptest
import fake_anthropic as fake
import pgtest
from apptest import AppCase

import embedding
import subreddits
from app import parse, queries, search
from app.search import Filter, Term, Vocabulary


def vocab():
    """A small city: two cuisines, two areas, a few words and three names."""
    cuisines = {"italian": Term("cuisine", "Italian", 2, frozenset({"lilia", "via carota"})),
                "pizza": Term("cuisine", "Pizza", 1, frozenset({"lucali"})),
                "steakhouse": Term("cuisine", "Steakhouse", 1, frozenset({"peter luger"}))}
    areas = {"brooklyn": Term("area", "Brooklyn", 3, frozenset({"lilia", "lucali", "peter luger"})),
             "west village": Term("area", "west village", 1, frozenset({"via carota"}))}
    tags = {t: Term("tag", t, 9) for t in ("romantic", "date night", "cash only", "west")}
    dishes = {t: Term("dish", t, 9) for t in ("bagels", "salt and pepper shrimp", "ramen")}
    names = {"lilia": "lilia", "via carota": "via carota", "lucali": "lucali",
             "peter luger": "peter luger", "peter lugers": "peter luger", "katzs": "katzs"}
    labels = {"lilia": "Lilia", "via carota": "Via Carota", "lucali": "Lucali",
              "peter luger": "Peter Luger Steak House", "katzs": "Katz's Delicatessen"}
    return Vocabulary(sub=subreddits.HOME, version=1,
                      terms={"cuisine": cuisines, "area": areas, "tag": tags, "dish": dishes},
                      names=names, labels=labels, boroughs=["Brooklyn", "Manhattan"])


def answer(search_text="", include=(), exclude=(), no_data=(), hard=False):
    return {"search_text": search_text,
            "include": [{"type": t, "value": v} for t, v in include],
            "exclude": [{"type": t, "value": v} for t, v in exclude],
            "no_data": list(no_data), "hard": hard}


def says(obj):
    """A fake API that answers every request with `obj` as the JSON text."""
    return fake.FakeAnthropic(answer=lambda params: (200, fake.message(json.dumps(obj))))


def kinds(filters):
    return [(f.kind, f.label) for f in filters]


class Words(unittest.TestCase):
    def test_fold_meets_the_stored_form(self):
        self.assertEqual(search.fold("Katz’s  Café!"), "katzs cafe")
        self.assertEqual(search.name_key("The Cheese & Wine Restaurant"), "cheese wine")
        self.assertEqual(search.name_key("Joe and Pat's NYC"), "joe pats")

    def test_normalize_keeps_punctuation(self):
        self.assertEqual(search.normalize("  Not   Italian?? "), "not italian??")


class Segment(unittest.TestCase):
    def seg(self, q):
        return search.segment(q, vocab())

    def test_filters_and_filler_need_no_model(self):
        p, left = self.seg("best pizza in Brooklyn")
        self.assertEqual(left, [])
        self.assertEqual(kinds(p.include), [("cuisine", "Pizza"), ("area", "Brooklyn")])
        self.assertEqual(p.search_text, "")

    def test_known_words_that_are_not_filters_become_the_text(self):
        p, left = self.seg("romantic italian for date night")
        self.assertEqual(left, [])
        self.assertEqual(kinds(p.include), [("cuisine", "Italian")])
        self.assertEqual(p.search_text, "romantic for date night")

    def test_longest_phrase_wins(self):
        # "west" alone is a known word too; the area must still be found.
        p, left = self.seg("west village")
        self.assertEqual(kinds(p.include), [("area", "west village")])
        self.assertEqual((p.search_text, left), ("", []))

    def test_filler_inside_a_known_phrase_is_part_of_it(self):
        p, left = self.seg("salt and pepper shrimp")
        self.assertEqual((p.search_text, left), ("salt and pepper shrimp", []))

    def test_plurals(self):
        self.assertEqual(self.seg("bagel")[0].search_text, "bagel")
        self.assertEqual(kinds(self.seg("steakhouses")[0].include), [("cuisine", "Steakhouse")])

    def test_a_word_that_changes_meaning_is_left_over(self):
        # No cue-word list: "not" is simply not vocabulary, so the model is asked.
        for q in ("not italian", "anything but pizza", "pizza without the wait"):
            self.assertTrue(self.seg(q)[1], q)

    def test_a_name_is_a_restaurant_filter(self):
        p, left = self.seg("Peter Luger's")
        self.assertEqual(left, [])
        self.assertEqual(kinds(p.include), [("restaurant", "Peter Luger Steak House")])
        self.assertEqual(p.include[0].keys, frozenset({"peter luger"}))

    def test_a_name_with_a_known_word_stays_a_description(self):
        v = vocab()
        v.names["pizza loves emily"] = "pizza loves emily"
        p, left = search.segment("pizza loves emily", v)
        self.assertEqual(left, ["loves", "emily"])
        self.assertEqual(kinds(p.include), [("cuisine", "Pizza")])

    def test_only_filler_is_the_whole_board(self):
        p, left = self.seg("best restaurants in nyc")
        self.assertEqual((p.search_text, p.include, left), ("", [], []))


class Resolve(unittest.TestCase):
    def res(self, a, q="q"):
        return search.resolve(parse.clean(a), vocab(), q, "model")

    def test_exclusion_resolves_to_places(self):
        p = self.res(answer(exclude=[("cuisine", "Italian")], include=[("area", "Brooklyn")]))
        self.assertEqual(kinds(p.exclude), [("cuisine", "Italian")])
        self.assertEqual(p.exclude[0].keys, frozenset({"lilia", "via carota"}))
        self.assertEqual(kinds(p.include), [("area", "Brooklyn")])

    def test_a_wanted_thing_nobody_knows_joins_the_text(self):
        p = self.res(answer("late night", include=[("cuisine", "Omakase")]))
        self.assertEqual((p.search_text, p.include), ("late night Omakase", []))

    def test_an_unwanted_thing_nobody_knows_is_reported(self):
        p = self.res(answer("steak", exclude=[("restaurant", "Nowhere Grill")]))
        self.assertEqual((p.exclude, p.ignored), ([], ["Nowhere Grill"]))

    def test_the_wrong_type_still_resolves(self):
        p = self.res(answer(include=[("cuisine", "West Village")],
                            exclude=[("area", "Lucali")]))
        self.assertEqual(kinds(p.include), [("area", "west village")])
        self.assertEqual(kinds(p.exclude), [("restaurant", "Lucali")])

    def test_a_typo_resolves_and_a_guess_does_not(self):
        self.assertEqual(kinds(self.res(answer(include=[("restaurant", "Peter Lugar")])).include),
                         [("restaurant", "Peter Luger Steak House")])
        self.assertEqual(kinds(self.res(answer(include=[("cuisine", "Itallian")])).include),
                         [("cuisine", "Italian")])
        self.assertEqual(self.res(answer(exclude=[("restaurant", "Peter Piper")])).exclude, [])

    def test_an_empty_reading_falls_back_to_the_words(self):
        self.assertEqual(self.res(answer(), q="hmm what").search_text, "hmm what")

    def test_clean_drops_what_the_schema_does_not_allow(self):
        c = parse.clean({"search_text": "  a\n b ", "include": [{"type": "dish", "value": "x"},
                                                              {"type": "area", "value": " "}, "junk"],
                         "exclude": None, "no_data": ["hours", "weather"], "hard": "yes",
                         "extra": 1})
        self.assertEqual(c, {"search_text": "a b", "include": [], "exclude": [],
                             "no_data": ["hours"], "hard": False})
        with self.assertRaises(parse.ParseFailed):
            parse.clean([])


class Understand(unittest.TestCase):
    """The model path, against the fake API and with no database: the parse
    cache's table reads as absent."""

    def setUp(self):
        search.forget()
        down = mock.patch.object(search, "connection", side_effect=psycopg2.OperationalError("no db"))
        down.start()
        self.addCleanup(down.stop)
        self.addCleanup(search.forget)

    def ask(self, api, q, mode="full", caller="1.2.3.4"):
        with mock.patch.dict(os.environ, {parse.KEY_VAR: "sk-test"}), \
                mock.patch.object(parse, "BASE_URL", api.base_url):
            return search.understand(subreddits.HOME, q, mode, vocab(), caller)

    def test_fast_never_calls_and_never_half_filters(self):
        with says(answer()) as api:
            p = self.ask(api, "not italian", mode="fast")
            self.assertEqual(api.requests, [])
        self.assertEqual((p.source, p.needs_model, p.search_text, p.include, p.exclude),
                         ("unparsed", True, "not italian", [], []))

    def test_a_query_the_vocabulary_explains_never_calls(self):
        with says(answer()) as api:
            p = self.ask(api, "romantic italian in brooklyn")
            self.assertEqual(api.requests, [])
        self.assertEqual((p.source, p.needs_model), ("vocabulary", False))

    def test_the_model_reads_what_is_left_and_the_answer_is_kept(self):
        with says(answer("romantic", exclude=[("cuisine", "Italian")])) as api:
            p = self.ask(api, "Romantic but NOT italian")
            again = self.ask(api, "romantic  but not Italian")
            self.assertEqual(len(api.requests), 1)
            sent = api.requests[0]
        self.assertEqual((p.source, again.source), ("model", "cache"))
        self.assertEqual((p.search_text, kinds(p.exclude)), ("romantic", [("cuisine", "Italian")]))
        self.assertEqual(again.as_json(), p.as_json())
        # The request: the query as data in its tag, the labels in the
        # instructions, a strict schema, and nothing that slows it down.
        self.assertEqual(sent["messages"], [{"role": "user",
                                             "content": "<query>romantic but not italian</query>"}])
        self.assertIn("Cuisine labels: Italian, Pizza, Steakhouse", sent["system"][0]["text"])
        self.assertIn("Boroughs: Brooklyn, Manhattan", sent["system"][0]["text"])
        self.assertNotIn("romantic", sent["system"][0]["text"].split("Cuisine labels:")[1])
        self.assertEqual(sent["output_config"]["format"]["schema"], parse.SCHEMA)
        self.assertEqual(sent["model"], parse.MODEL)
        self.assertNotIn("thinking", sent)

    def test_without_a_key_the_whole_query_is_the_text(self):
        with mock.patch.dict(os.environ, {parse.KEY_VAR: ""}):
            p = search.understand(subreddits.HOME, "not italian", "full", vocab(), "x")
        self.assertEqual((p.source, p.needs_model, p.search_text), ("fallback", False, "not italian"))

    def test_a_failed_call_falls_back_and_is_not_kept(self):
        with fake.FakeAnthropic(answer=lambda p: fake.error(529, "overloaded_error")) as api:
            p = self.ask(api, "not italian")
            self.assertEqual(len(api.requests), 1)       # one attempt, no retry
            self.ask(api, "not italian")
            self.assertEqual(len(api.requests), 2)
        self.assertEqual(p.source, "fallback")

    def test_a_refusal_or_a_cut_answer_falls_back(self):
        for stop in ("refusal", "max_tokens"):
            search.forget()
            with fake.FakeAnthropic(answer=lambda p: (200, fake.message("{", stop=stop))) as api:
                self.assertEqual(self.ask(api, "not italian").source, "fallback", stop)

    def test_model_calls_are_capped_per_caller(self):
        with says(answer("x")) as api, mock.patch.object(search, "MODEL_CALLS", search.Window(2, 60)):
            sources = [self.ask(api, f"zzz{i} italian").source for i in range(3)]
            other = self.ask(api, "zzz9 italian", caller="5.6.7.8").source
        self.assertEqual((sources, other), (["model", "model", "fallback"], "model"))

    def test_the_prompt_hash_moves_with_the_labels(self):
        a = parse.prompt_hash(parse.system_prompt(subreddits.HOME, ["Thai", "Italian"], ["Queens"]))
        b = parse.prompt_hash(parse.system_prompt(subreddits.HOME, ["Italian", "Thai"], ["Queens"]))
        c = parse.prompt_hash(parse.system_prompt(subreddits.HOME, ["Italian"], ["Queens"]))
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


class Limits(unittest.TestCase):
    def test_window(self):
        w = search.Window(2, 60)
        self.assertEqual([w.allow("a"), w.allow("a"), w.allow("a"), w.allow("b")],
                         [True, True, False, True])
        with mock.patch.object(search.time, "monotonic", return_value=search.time.monotonic() + 61):
            self.assertTrue(w.allow("a"))


# --- with a database ---------------------------------------------------------

_base_seed = apptest.seed


def seed(conn):
    """apptest's comments, plus what search reads: official cuisines and
    boroughs, a cuisine known only from tags, a neighbourhood, and a knock."""
    _base_seed(conn)
    with conn.cursor() as cur:
        cur.execute("""insert into restaurants (name, name_key, cuisine, boroughs) values
                         ('CELLOS', 'cellos', 'Pizza', '{Brooklyn}'),
                         ('ABC KITCHEN', 'abc', 'Italian', '{Manhattan}')""")
        # katzs has no official record: commenters call it pizza, twice.
        for c in ("t1_c7", "t1_c8"):
            cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key, descriptors,
                                                 neighborhood_hint, model_version, prompt_hash)
                           values (%s, 'Katz''s', 'katzs', '["Pizza"]', 'Lower East Side', 'm', 'p')""",
                        (c,))
        # A ninth comment, by u1 again, warning people off abc.
        cur.execute("""insert into comments (id, thread_id, parent_id, author, body, permalink,
                                             created_utc, score, score_settled)
                       values ('t1_c9', 't3_a', 't3_a', 'u1', 'skip abc', %s, now(), 99, true)""",
                    (f"/r/{subreddits.HOME}/comments/a/9/",))
        cur.execute("""insert into mentions (comment_id, restaurant_raw, entity_key, is_negated,
                                             model_version, prompt_hash)
                       values ('t1_c9', 'abc', 'abc', true, 'm', 'p')""")
    conn.commit()


class SearchCase(AppCase):
    @classmethod
    def setUpClass(cls):
        with mock.patch.object(apptest, "seed", seed):
            super().setUpClass()

    def setUp(self):
        search.forget()
        for name, value in (("TERM_MIN", 1), ("AREA_MIN", 1)):
            p = mock.patch.object(search, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(search.forget)

    def get(self, q, **params):
        r = self.client.get("/api/search/query", params={"q": q, **params})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def keys(self, body):
        return [i["entity_key"] for i in body["items"]]


class Endpoint(SearchCase):
    def test_vocabulary(self):
        r = self.client.get("/api/search/vocabulary")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers["cache-control"], "public, max-age=300")
        v = r.json()
        # Pizza: cellos by the city's label, katzs by the commenters' tags.
        self.assertEqual(dict(map(tuple, v["cuisines"])), {"Pizza": 2, "Italian": 1})
        self.assertEqual(dict(map(tuple, v["areas"])),
                         {"Brooklyn": 1, "Manhattan": 1, "lower east side": 1})
        self.assertIn(["cash only", 3], v["tags"])
        self.assertIn("slice", [t for t, _ in v["dishes"] + v["tags"]])
        # A tag that is a cuisine is the cuisine, not a second row.
        self.assertNotIn("pizza", [t for t, _ in v["tags"]])

    def test_a_filter_alone_ranks_by_people_and_shows_its_comments(self):
        body = self.get("best pizza")
        self.assertEqual((body["source"], body["semantic"], body["ranked_by"], body["needs_model"]),
                         ("vocabulary", "none", "people", False))
        self.assertEqual(body["parse"]["include"], [{"type": "cuisine", "value": "Pizza"}])
        self.assertEqual(self.keys(body), ["katzs", "cellos"])
        self.assertEqual([i["people"] for i in body["items"]], [4, 3])
        self.assertEqual(body["total"], 2)
        cellos = body["items"][1]
        self.assertEqual((cellos["name"], cellos["cuisine"], cellos["borough"]),
                         ("Cellos", "Pizza", "Brooklyn"))
        self.assertEqual(body["items"][0]["neighborhood"], "Lower East Side")
        self.assertEqual(len(cellos["comments"]), 3)
        # Click-through, and never a link to a deleted comment.
        links = {c["comment_id"]: c["permalink"] for c in cellos["comments"]}
        self.assertIsNone(links["t1_c2"])
        self.assertTrue(links["t1_c1"].endswith("/a/1/"))

    def test_kinds_combine_and_a_knock_is_never_evidence(self):
        body = self.get("italian in manhattan")
        self.assertEqual(self.keys(body), ["abc"])
        self.assertEqual([c["comment_id"] for c in body["items"][0]["comments"]], ["t1_c4"])
        self.assertEqual(self.get("pizza in manhattan")["items"], [])

    def test_a_name_is_that_place(self):
        body = self.get("Katz's")
        self.assertEqual(body["parse"]["include"], [{"type": "restaurant", "value": "Katzs"}])
        self.assertEqual(self.keys(body), ["katzs"])

    def test_fast_then_full_with_the_model(self):
        with says(answer(exclude=[("cuisine", "Pizza")])) as api, \
                mock.patch.dict(os.environ, {parse.KEY_VAR: "sk-test"}), \
                mock.patch.object(parse, "BASE_URL", api.base_url), \
                mock.patch.object(search, "_embed", side_effect=embedding.EmbedError("no key")):
            fast = self.get("not pizza", mode="fast")
            full = self.get("not pizza")
            again = self.get("NOT  pizza")
            self.assertEqual(len(api.requests), 1)
        self.assertEqual((fast["source"], fast["needs_model"], fast["parse"]["exclude"]),
                         ("unparsed", True, []))
        self.assertEqual(fast["semantic"], "unavailable")
        self.assertEqual((full["source"], again["source"]), ("model", "cache"))
        self.assertEqual(full["parse"]["exclude"], [{"type": "cuisine", "value": "Pizza"}])
        self.assertEqual(self.keys(full), ["abc"])
        # Kept for good, as the model said it; and every search is logged.
        self.assertEqual(self.q("select query, model, parse->'exclude' from search_parses"),
                         [("not pizza", parse.MODEL, [{"type": "cuisine", "value": "Pizza"}])])
        self.assertEqual(self.q("select query, mode, source, results from search_log "
                                "where query = 'not pizza' order by id"),
                         [("not pizza", "fast", "unparsed", 3), ("not pizza", "full", "model", 1),
                          ("not pizza", "full", "cache", 1)])
        # A new process finds it in the table.
        search.forget()
        with mock.patch.dict(os.environ, {parse.KEY_VAR: ""}):
            self.assertEqual(self.get("not pizza")["source"], "cache")

    def test_notes_say_what_the_site_cannot_know(self):
        with says(answer("open late", no_data=["hours"], hard=True,
                         exclude=[("restaurant", "Nowhere Grill")])) as api, \
                mock.patch.dict(os.environ, {parse.KEY_VAR: "sk-test"}), \
                mock.patch.object(parse, "BASE_URL", api.base_url), \
                mock.patch.object(search, "_embed", side_effect=embedding.EmbedError("no key")):
            body = self.get("open late tonight but not nowhere grill")
        notes = " ".join(body["notes"])
        self.assertIn("no data on opening hours", notes)
        self.assertIn("Nowhere Grill", notes)
        self.assertIn("more of a question", notes)
        self.assertIn("not available right now", notes)
        self.assertEqual(body["parse"]["ignored"], ["Nowhere Grill"])

    def test_text_without_vectors_says_so_and_falls_back(self):
        # This server has no embeddings table (or the test below covers it):
        # the answer is the board, and a note, not a 500.
        with mock.patch.object(search, "_embed", return_value=embedding.to_pgvector([0.0] * embedding.DIMS)), \
                mock.patch.object(queries, "semantic_matches",
                                  side_effect=psycopg2.errors.UndefinedTable("comment_embeddings")):
            body = self.get("cash only")
        self.assertEqual((body["parse"]["search_text"], body["semantic"], body["ranked_by"]),
                         ("cash only", "unavailable", "people"))
        self.assertEqual(self.keys(body), ["katzs", "cellos", "abc"])

    def test_another_city_is_never_matched_against_new_yorks_vectors(self):
        with mock.patch.object(search, "_embed") as embed:
            r = self.client.get("/api/search/query", params={"q": "tacos", "subreddit": "austinfood"})
            self.assertEqual(r.status_code, 200, r.text)
            embed.assert_not_called()
        self.assertEqual(r.json()["semantic"], "unavailable")

    def test_rate_limit_and_bad_input(self):
        with mock.patch.object(search, "REQUESTS", search.Window(2, 60)):
            codes = [self.client.get("/api/search/query", params={"q": "pizza"},
                                     headers={"x-forwarded-for": "9.9.9.9, 7.7.7.7"}).status_code
                     for _ in range(3)]
            # The first X-Forwarded-For entry is the client's to forge; only
            # the last one, the edge's, tells callers apart.
            forged = self.client.get("/api/search/query", params={"q": "pizza"},
                                     headers={"x-forwarded-for": "1.1.1.1, 7.7.7.7"}).status_code
            other = self.client.get("/api/search/query", params={"q": "pizza"},
                                    headers={"x-forwarded-for": "9.9.9.9, 8.8.8.8"}).status_code
        self.assertEqual((codes, forged, other), ([200, 200, 429], 429, 200))
        self.assertEqual(self.client.get("/api/search/query", params={"q": "   "}).status_code, 422)
        self.assertEqual(self.client.get("/api/search/query", params={"q": "x" * 201}).status_code, 422)

    def test_a_search_survives_a_database_that_cannot_be_written(self):
        with mock.patch.object(queries, "search_log_put",
                               side_effect=psycopg2.errors.ReadOnlySqlTransaction("read only")):
            self.assertEqual(self.keys(self.get("pizza")), ["katzs", "cellos"])


def unit(i):
    """A unit vector along axis i."""
    v = [0.0] * embedding.DIMS
    v[i] = 1.0
    return v


def toward(i, j, cos):
    """A unit vector at cosine `cos` to axis i, leaning to axis j."""
    v = [0.0] * embedding.DIMS
    v[i], v[j] = cos, (1 - cos * cos) ** 0.5
    return v


class Semantic(SearchCase):
    """The retrieval itself, on real vectors. Needs pgvector."""

    @classmethod
    def setUpClass(cls):
        if not pgtest.URL:
            raise unittest.SkipTest(pgtest.SKIP_REASON)
        conn = pgtest.connect()
        try:
            if not pgtest.has_pgvector(conn):
                raise unittest.SkipTest("semantic search tests skipped: the test server has no pgvector")
        finally:
            conn.close()
        super().setUpClass()
        # The query is axis 0. cellos: three comments by three people, near.
        # katzs: four comments, one near and three far. abc: its praise (c4)
        # is nearest of all, and so is its knock (c9), which must not count.
        vectors = {"t1_c1": toward(0, 1, 0.90), "t1_c2": toward(0, 1, 0.85),
                   "t1_c3": toward(0, 1, 0.80), "t1_c4": toward(0, 1, 0.99),
                   "t1_c5": toward(0, 1, 0.95), "t1_c6": unit(2), "t1_c7": unit(2),
                   "t1_c8": unit(2), "t1_c9": toward(0, 1, 0.98)}
        with cls.conn.cursor() as cur:
            for cid, vec in vectors.items():
                cur.execute("""insert into comment_embeddings (comment_id, model, input_hash, embedding)
                               values (%s, %s, 'h', %s::halfvec)""",
                            (cid, embedding.MODEL_KEY, embedding.to_pgvector(vec)))
        cls.conn.commit()

    def find(self, q, **params):
        with mock.patch.object(search, "_embed", return_value=embedding.to_pgvector(unit(0))), \
                mock.patch.object(search, "MIN_SIMILARITY", 0.5):
            return self.get(q, **params)

    def test_ranks_by_distinct_people_with_a_matching_comment(self):
        body = self.find("cash only")
        self.assertEqual((body["semantic"], body["ranked_by"]), ("ok", "matching_people"))
        # cellos 3 people; then abc and katzs with one each, abc's comment nearer.
        self.assertEqual(self.keys(body), ["cellos", "abc", "katzs"])
        self.assertEqual([i["people"] for i in body["items"]], [3, 1, 1])
        self.assertEqual(body["total"], 3)
        cellos, abc, katzs = body["items"]
        # Evidence is the matching comments, nearest first; the deleted one
        # shows without a link.
        self.assertEqual([c["comment_id"] for c in cellos["comments"]], ["t1_c1", "t1_c2", "t1_c3"])
        self.assertIsNone(cellos["comments"][1]["permalink"])
        self.assertAlmostEqual(cellos["best_similarity"], 0.90, places=2)
        # The knock is nearer than the praise and is neither counted nor shown.
        self.assertEqual([c["comment_id"] for c in abc["comments"]], ["t1_c4"])
        # Far comments are under the cutoff: one of katzs' four people matches.
        self.assertEqual(([c["comment_id"] for c in katzs["comments"]], katzs["total_people"]),
                         (["t1_c5"], 4))

    def test_filters_apply_to_the_nearest(self):
        self.assertEqual(self.keys(self.find("cash only pizza")), ["cellos", "katzs"])
        self.assertEqual(self.keys(self.find("cash only in manhattan")), ["abc"])

    def test_nothing_near_enough_is_an_empty_answer(self):
        with mock.patch.object(search, "_embed", return_value=embedding.to_pgvector(unit(5))), \
                mock.patch.object(search, "MIN_SIMILARITY", 0.5):
            body = self.get("cash only")
        self.assertEqual((body["semantic"], body["items"]), ("ok", []))
        self.assertIn("closely enough", " ".join(body["notes"]))


if __name__ == "__main__":
    unittest.main()
