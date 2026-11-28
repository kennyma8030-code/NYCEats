"""Search: reading a query, and what comes back for it.

The first half needs nothing but a hand-built vocabulary and the local
stand-in for Anthropic's API (tests/fake_anthropic.py). The second half
needs TEST_DATABASE_URL (tests/pgtest.py), and its last class needs pgvector
on that server as well.
"""

import json
import os
import threading
import time
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

    def test_fast_without_a_model_to_ask_asks_for_no_second_pass(self):
        # No key: mode=full could read no more than this, so the browser is
        # not sent back for it.
        with mock.patch.dict(os.environ, {parse.KEY_VAR: ""}):
            p = search.understand(subreddits.HOME, "not italian", "fast", vocab(), "x")
        self.assertEqual((p.source, p.needs_model, p.search_text, p.include),
                         ("fallback", False, "not italian", []))

    def test_fast_answers_from_a_reading_already_kept(self):
        with says(answer("romantic", exclude=[("cuisine", "Italian")])) as api:
            self.ask(api, "romantic but not italian")
            p = self.ask(api, "Romantic but not Italian", mode="fast")
            self.assertEqual(len(api.requests), 1)
        self.assertEqual((p.source, p.needs_model, kinds(p.exclude)),
                         ("cache", False, [("cuisine", "Italian")]))

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


class Building(unittest.TestCase):
    """The vocabulary's first build, with the scans faked: one computation
    per city, shared by everyone waiting, and no city waiting on another."""

    def setUp(self):
        search.forget()
        self.addCleanup(search.forget)
        self.go = threading.Event()
        self.calls = []

    def load(self, sub):
        self.calls.append(sub)
        if sub == "slow":
            self.go.wait(5)
        if sub == "broken":
            self.go.wait(5)
            raise psycopg2.OperationalError("no db")
        return Vocabulary(sub=sub, version=1, terms={}, names={}, labels={}, boroughs=[])

    def together(self, sub, n=4):
        """n requests for one city at once, released together: what each got."""
        got = []

        def ask():
            try:
                got.append(search.vocabulary(sub))
            except Exception as e:
                got.append(e)
        threads = [threading.Thread(target=ask) for _ in range(n)]
        for t in threads:
            t.start()
        deadline = time.monotonic() + 5
        while self.calls.count(sub) < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.05)                    # the others have joined the wait
        return threads, got

    def test_requests_for_one_city_share_one_build(self):
        with mock.patch.object(search, "_load", side_effect=self.load):
            threads, got = self.together("slow")
            self.go.set()
            for t in threads:
                t.join(5)
        self.assertEqual(self.calls, ["slow"])
        self.assertEqual(len(got), 4)
        self.assertTrue(all(v is got[0] for v in got))

    def test_a_failed_build_reaches_every_waiter_and_is_not_rerun_for_them(self):
        with mock.patch.object(search, "_load", side_effect=self.load):
            threads, got = self.together("broken")
            self.go.set()
            for t in threads:
                t.join(5)
            self.assertEqual(self.calls, ["broken"])
            self.assertEqual([type(e) for e in got], [psycopg2.OperationalError] * 4)
            # Not remembered either: the next request builds again.
            self.assertRaises(psycopg2.OperationalError, search.vocabulary, "broken")
        self.assertEqual(self.calls, ["broken", "broken"])

    def test_one_citys_build_does_not_hold_up_another(self):
        with mock.patch.object(search, "_load", side_effect=self.load):
            threads, _ = self.together("slow", n=1)
            started = time.monotonic()
            self.assertEqual(search.vocabulary("quick").sub, "quick")
            self.assertLess(time.monotonic() - started, 1)
            self.go.set()
            threads[0].join(5)

    def test_a_waiter_gives_up_after_a_bounded_wait(self):
        with mock.patch.object(search, "_load", side_effect=self.load), \
                mock.patch.object(search._VOCAB, "wait", 0.05):
            threads, _ = self.together("slow", n=1)
            self.assertRaises(psycopg2.errors.QueryCanceled, search.vocabulary, "slow")
            self.go.set()
            threads[0].join(5)

    def test_a_stale_copy_is_served_while_one_thread_replaces_it(self):
        with mock.patch.object(search, "_load", side_effect=self.load) as load, \
                mock.patch.object(search, "connection"), \
                mock.patch.object(queries, "facets_version", return_value=2):
            old = search.vocabulary("quick")
            old.checked -= search.VOCAB_CHECK + 1
            self.assertIs(search.vocabulary("quick"), old)       # no wait
            deadline = time.monotonic() + 5
            while search._VOCAB.peek("quick") is old and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIsNot(search._VOCAB.peek("quick"), old)
            self.assertEqual(load.call_count, 2)


class TextWords(unittest.TestCase):
    def test_the_words_looked_for_as_typed(self):
        self.assertEqual(search.text_words("Best jalapeño  tacos, tacos!"), ["jalapeño", "tacos"])
        self.assertEqual(search.text_words("the best"), [])

    def test_only_what_has_a_letter_or_a_digit_is_a_word(self):
        # Punctuation standing alone, or a single letter, is in no comment's
        # dishes: asked for, it matched nothing.
        self.assertEqual(search.text_words("mac & cheese"), ["mac", "cheese"])
        self.assertEqual(search.text_words("mac 'n' cheese"), ["mac", "cheese"])
        self.assertEqual(search.text_words("pizza - cheap"), ["pizza", "cheap"])
        self.assertEqual(search.text_words("“pizza”, (cheap)... $$ 24/7?"), ["pizza", "cheap", "24"])
        self.assertEqual(search.text_words("katz's pan-fried soup_dumplings"),
                         ["katz's", "pan-fried", "soup", "dumplings"])
        self.assertEqual(search.text_words("& - !!"), [])

    def test_the_words_of_a_question_are_not_looked_for(self):
        self.assertEqual(search.text_words("Where should I take my parents for dinner?"),
                         ["take", "parents", "dinner"])
        self.assertEqual(search.text_words("what's cheap near me"), ["cheap"])
        # A word that turns the phrase round stays, so the match stays strict.
        self.assertEqual(search.text_words("not crowded"), ["not", "crowded"])

    def test_a_long_query_is_a_bounded_scan(self):
        words = search.text_words(" ".join(f"word{i}" for i in range(40)))
        self.assertEqual(len(words), search.TEXT_WORDS_MAX)


class FakeConn:
    """Stands in for a pooled connection; the queries are faked beside it."""
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def hit(key, people, comments, ids, total, need):
    return {"entity_key": key, "people": people, "comments": comments, "mention_ids": ids,
            "total": total, "need": need}


class Degrading(unittest.TestCase):
    """What a search does when matching by meaning cannot run, with the
    database faked: which statements are sent, what is remembered and what
    the answer says. The statements themselves run in the classes below."""

    def setUp(self):
        search.forget()
        self.addCleanup(search.forget)
        self.q = mock.Mock()
        self.q.search_board.return_value = ([{"entity_key": "katzs", "people": 4}], 1)
        self.q.board_evidence.return_value = []
        self.q.search_evidence.return_value = []
        self.q.search_places.return_value = []
        self.q.top_neighborhoods.return_value = []
        self.q.text_matches.return_value = [hit("cellos", 2, 70, [5, 6], 1, 2)]
        for name, value in (("queries", self.q), ("connection", FakeConn),
                            ("transaction", lambda conn: FakeConn()),
                            ("_embed", mock.Mock(return_value="[0]"))):
            p = mock.patch.object(search, name, value)
            p.start()
            self.addCleanup(p.stop)

    def find(self, text="cash only", **parsed):
        return search.retrieve(subreddits.HOME, search.Parsed(search_text=text, **parsed), 20)

    def test_a_vector_query_that_timed_out_is_not_followed_by_a_heavier_scan(self):
        self.q.semantic_matches.side_effect = psycopg2.errors.QueryCanceled("statement timeout")
        with self.assertLogs("uvicorn.error", "WARNING"):
            out = self.find()
        self.q.text_matches.assert_not_called()
        self.assertEqual((out["semantic"], out["ranked_by"], out["matched"]),
                         ("unavailable", "people", None))
        self.assertEqual([i["entity_key"] for i in out["items"]], ["katzs"])
        self.assertEqual(out["notes"], ["Matching by meaning is not available right now, so this "
                                        "is the most talked-about places."])
        self.assertNotIn("why", out)
        self.assertNotIn("slow", out)
        # Kept its minute: asking again at once would run the statement that
        # just timed out.
        self.find()
        self.assertEqual(self.q.semantic_matches.call_count, 1)

    def test_a_text_match_that_timed_out_is_the_board_and_not_an_error(self):
        self.q.semantic_matches.side_effect = psycopg2.OperationalError("connection reset")
        self.q.text_matches.side_effect = psycopg2.errors.QueryCanceled("statement timeout")
        with self.assertLogs("uvicorn.error", "WARNING"):
            out = self.find()
        self.assertEqual((out["semantic"], out["ranked_by"]), ("unavailable", "people"))
        self.assertEqual([i["entity_key"] for i in out["items"]], ["katzs"])
        self.assertIn("took too long", out["notes"][0])
        self.assertIn("most talked-about", out["notes"][0])

    def test_a_lost_connection_still_matches_the_words_and_is_tried_again(self):
        self.q.semantic_matches.side_effect = psycopg2.OperationalError("connection reset")
        with self.assertLogs("uvicorn.error", "WARNING"):
            out = self.find()
            self.find()
        self.assertEqual(out["semantic"], "text")
        self.assertEqual(self.q.semantic_matches.call_count, 2)

    def test_a_broken_vector_query_is_an_error_in_the_log_and_is_not_rerun(self):
        for error in (psycopg2.errors.UndefinedColumn("column e.embeding does not exist"),
                      psycopg2.errors.UndefinedTable('relation "mention_weights" does not exist')):
            search.forget()
            self.q.semantic_matches.reset_mock()
            self.q.semantic_matches.side_effect = error
            with self.assertLogs("uvicorn.error", "ERROR") as logged:
                out = self.find()
            self.assertIsNotNone(logged.records[0].exc_info)
            # The search is still answered, by its words.
            self.assertEqual(out["semantic"], "text")
            # Another search, a moment later, does not run it again.
            with self.assertNoLogs("uvicorn.error", "WARNING"):
                self.find("date night")
            self.assertEqual(self.q.semantic_matches.call_count, 1)
            self.assertEqual(search._embed.call_count, 1)
            search._embed.reset_mock()
            # Until the wait is over.
            later = time.monotonic() + search.VECTORS_RETRY + 1
            with mock.patch.object(search.time, "monotonic", return_value=later), \
                    self.assertLogs("uvicorn.error", "ERROR"):
                self.find("brunch")
            self.assertEqual(self.q.semantic_matches.call_count, 2)
            search._embed.reset_mock()

    def test_a_database_without_vectors_is_quiet_and_is_not_asked_again(self):
        self.q.semantic_matches.side_effect = psycopg2.errors.UndefinedTable(
            'relation "comment_embeddings" does not exist')
        with self.assertNoLogs("uvicorn.error", "ERROR"):
            self.find()
            self.find("date night")
        self.assertEqual(self.q.semantic_matches.call_count, 1)

    def test_a_busy_pool_is_not_swallowed(self):
        from app.db import PoolTimeout
        self.q.semantic_matches.side_effect = PoolTimeout("busy")
        with self.assertRaises(PoolTimeout):
            self.find()

    def test_the_note_says_which_words_were_matched(self):
        self.q.semantic_matches.side_effect = psycopg2.OperationalError("connection reset")
        with self.assertLogs("uvicorn.error", "WARNING"):
            out = self.find("cash only")
            self.assertEqual(out["matched"], {"words": ["cash", "only"], "need": 2})
            self.assertEqual(out["notes"], [
                "Matching by meaning is not available right now, so these are the places whose "
                "comments use the words “cash” and “only”."])
            # Loose unless a word turns the phrase round.
            self.assertIs(self.q.text_matches.call_args.args[3], True)

            self.q.text_matches.return_value = [hit("cellos", 2, 2, [5, 6], 1, 1)]
            out = self.find("where should we take my parents for dinner")
            self.assertEqual(out["matched"], {"words": ["take", "parents", "dinner"], "need": 1})
            self.assertTrue(out["notes"][0].endswith(
                "and no comment uses all of the words “take”, “parents” and “dinner”, so these "
                "are the places whose comments use any of them."), out["notes"])

            self.q.text_matches.return_value = [hit("cellos", 2, 2, [5, 6], 1, 2)]
            out = self.find("cheap parents dinner")
            self.assertIn("use at least 2 of them.", out["notes"][0])

            out = self.find("tacos")
            self.assertIn("use the word “tacos”.", out["notes"][0])

            self.find("not crowded")
            self.assertIs(self.q.text_matches.call_args.args[3], False)

            self.q.text_matches.return_value = []
            out = self.find("zzz qqq")
            self.assertEqual((out["semantic"], out["items"], out["notes"][-1]),
                             ("text", [], "No comments use those words."))

    def test_a_text_match_names_a_bounded_number_of_its_comments(self):
        self.q.semantic_matches.side_effect = psycopg2.OperationalError("connection reset")
        with self.assertLogs("uvicorn.error", "WARNING"):
            out = self.find()
        self.assertEqual(self.q.text_matches.call_args.args[-2], search.TEXT_IDS)
        cellos = out["items"][0]
        # The count is all seventy; two are named and the rest are paged.
        self.assertEqual((cellos["people"], cellos["comment_count"], cellos["mention_ids"]),
                         (2, 70, [5, 6]))

    def test_a_meaning_match_and_the_board_say_how_many_comments(self):
        self.q.semantic_matches.return_value = [
            {"entity_key": "katzs", "mention_id": m, "comment_id": f"c{m}", "person": f"u{m}",
             "similarity": 0.9} for m in (1, 2, 3)]
        out = self.find()
        self.assertEqual((out["semantic"], out["items"][0]["comment_count"]), ("ok", 3))
        out = self.find("")
        self.assertEqual((out["semantic"], out["items"][0]["comment_count"],
                          out["items"][0]["mention_ids"]), ("none", None, None))

    def test_the_rest_of_a_text_match_is_read_a_page_at_a_time(self):
        self.q.text_match_ids.return_value = [{"mention_id": 9}, {"mention_id": 7}, {"mention_id": 8}]
        self.q.search_evidence.return_value = [{"mention_id": 7}, {"mention_id": 9}]
        rows = search.matched_comments(subreddits.HOME, "cellos", ["Cash", "&", "only", "the"], 9, 50, 50)
        # In the match's order, without the comment gone since.
        self.assertEqual(rows, [{"mention_id": 9}, {"mention_id": 7}])
        args = self.q.text_match_ids.call_args.args
        # Only what a search could have asked: its words, and no more of
        # them than there are.
        self.assertEqual(args[1:7], (subreddits.HOME, "cellos", ["cash", "only"], 2, 50, 50))
        self.q.text_match_ids.reset_mock()
        self.assertEqual(search.matched_comments(subreddits.HOME, "cellos", ["&", "the"], 1, 0, 50), [])
        self.q.text_match_ids.assert_not_called()

    def test_a_waiter_outlasts_the_slowest_retrieval(self):
        slowest = (embedding.QUERY_ATTEMPTS * (embedding.QUERY_TIMEOUT + 1)
                   + 2 * search.POOL_TIMEOUT + search.STATEMENT_TIMEOUT_MS / 1000)
        self.assertGreater(search.RETRIEVED_WAIT, slowest)


class Statements(unittest.TestCase):
    """The text match's SQL, as far as it can be read without a database:
    every word is a parameter, and the place a page is for is one too."""

    def sent(self, call, *args):
        seen = {}

        def fetch_all(conn, sql, params):
            seen.update(sql=sql, params=params)
            return []
        call(None, subreddits.HOME, *args, fetch_all)
        # Every placeholder has its parameter, and nothing typed is in the text.
        seen["sql"] % {k: "?" for k in seen["params"]}
        return seen["sql"], seen["params"]

    def test_text_matches(self):
        sql, params = self.sent(queries.text_matches, ["50%", "o'brien"], True, (("a",),), ("b",),
                                False, 20, 50)
        self.assertEqual((params["w0"], params["w1"]), ("%50\\%%", "%o'brien%"))
        self.assertNotIn("o'brien", sql)
        self.assertEqual((params["floor"], params["ids"], params["limit"]), (1, 50, 20))
        self.assertIn("rn <= %(ids)s", sql)
        _, params = self.sent(queries.text_matches, ["a", "b", "c"], False, (), (), False, 20, 50)
        self.assertEqual(params["floor"], 3)

    def test_text_match_ids(self):
        sql, params = self.sent(queries.text_match_ids, "cellos", ["cash", "only"], 2, 50, 25)
        self.assertEqual((params["key"], params["floor"], params["offset"], params["limit"]),
                         ("cellos", 2, 50, 25))
        self.assertIn("w.entity_key = %(key)s", sql)


class KeptParses(unittest.TestCase):
    """mode=fast must cost no connection for a query it has just learned has
    no kept parse, and must never fail for want of the cache."""

    def setUp(self):
        search.forget()
        self.addCleanup(search.forget)
        self.get = mock.Mock(return_value=None)
        for name, value in (("connection", FakeConn),
                            ("queries", mock.Mock(search_parse_get=self.get))):
            p = mock.patch.object(search, name, value)
            p.start()
            self.addCleanup(p.stop)

    def fast(self, q, v):
        with mock.patch.dict(os.environ, {parse.KEY_VAR: "sk-test"}):
            return search.understand(subreddits.HOME, q, "fast", v, "1.2.3.4")

    def test_a_miss_is_remembered_and_the_prompt_is_built_once(self):
        v = vocab()
        with mock.patch.object(parse, "system_prompt", wraps=parse.system_prompt) as built:
            for _ in range(3):
                p = self.fast("not italian", v)
            self.fast("not pizza", v)
            self.assertEqual(built.call_count, 1)
        self.assertEqual((p.source, p.needs_model), ("unparsed", True))
        self.assertEqual(self.get.call_count, 2)        # once a query, not once a request
        # Not for good: the other worker may keep one.
        later = time.monotonic() + search.MISS_TTL + 1
        with mock.patch.object(search.time, "monotonic", return_value=later):
            self.fast("not italian", v)
        self.assertEqual(self.get.call_count, 3)

    def test_the_full_pass_always_looks(self):
        v = vocab()
        self.fast("not italian", v)
        key = (subreddits.HOME, "not italian", parse.MODEL, v.prompt()[1])
        self.assertIsNone(search._kept(key))
        self.assertEqual(self.get.call_count, 2)

    def test_a_parse_kept_meanwhile_ends_the_miss(self):
        v = vocab()
        self.fast("not italian", v)
        key = (subreddits.HOME, "not italian", parse.MODEL, v.prompt()[1])
        search._remember(key, answer(exclude=[("cuisine", "Italian")]))
        p = self.fast("not italian", v)
        self.assertEqual((p.source, p.needs_model), ("cache", False))

    def test_a_busy_pool_is_a_miss_and_not_a_failure(self):
        from app.db import PoolTimeout
        v = vocab()
        with mock.patch.object(search, "connection", side_effect=PoolTimeout("busy")) as taken:
            p = self.fast("not italian", v)
            self.fast("not italian", v)
            self.assertEqual(taken.call_count, 1)
        self.assertEqual((p.source, p.needs_model), ("unparsed", True))


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
        # Nobody wrote both words, and the answer says they were not read.
        self.assertEqual((fast["semantic"], fast["items"]), ("text", []))
        self.assertIn(search.AS_TYPED, fast["notes"])
        self.assertNotIn(search.AS_TYPED, full["notes"])
        self.assertEqual((full["source"], again["source"]), ("model", "cache"))
        self.assertEqual(full["parse"]["exclude"], [{"type": "cuisine", "value": "Pizza"}])
        self.assertEqual(self.keys(full), ["abc"])
        # Kept for good, as the model said it; and every search is logged
        # once: the provisional fast answer is not a search of its own.
        self.assertEqual(self.q("select query, model, parse->'exclude' from search_parses"),
                         [("not pizza", parse.MODEL, [{"type": "cuisine", "value": "Pizza"}])])
        self.assertEqual(self.q("select query, mode, source, results from search_log "
                                "where query = 'not pizza' order by id"),
                         [("not pizza", "full", "model", 1), ("not pizza", "full", "cache", 1)])
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

    def no_vectors(self, error=None):
        """Search as on a server whose vector query fails with `error`."""
        error = error or psycopg2.errors.UndefinedTable("comment_embeddings")
        return mock.patch.multiple(
            "app.search", _embed=mock.Mock(return_value=embedding.to_pgvector([0.0] * embedding.DIMS)),
            queries=mock.Mock(wraps=queries, semantic_matches=mock.Mock(side_effect=error)))

    def test_text_without_vectors_is_matched_as_words_and_says_so(self):
        # This server has no embeddings table (or the class below covers
        # it): the words still filter the list, with a note, not a 500.
        with self.no_vectors():
            body = self.get("cash only")
        self.assertEqual((body["parse"]["search_text"], body["semantic"], body["ranked_by"]),
                         ("cash only", "text", "matching_people"))
        # One person each wrote "cash only" of these three; nobody of a fourth.
        self.assertEqual(self.keys(body), ["abc", "cellos", "katzs"])
        self.assertEqual([i["people"] for i in body["items"]], [1, 1, 1])
        self.assertEqual(body["total"], 3)
        self.assertEqual([c["comment_id"] for c in body["items"][2]["comments"]], ["t1_c5"])
        self.assertIn("not available right now", " ".join(body["notes"]))
        # Read from the vocabulary, so nothing says the words went unread.
        self.assertNotIn(search.AS_TYPED, body["notes"])

    def test_a_slow_or_failed_vector_query_degrades_instead_of_failing(self):
        with self.no_vectors(psycopg2.OperationalError("server closed the connection")):
            body = self.get("cash only")
        self.assertEqual((body["semantic"], self.keys(body)), ("text", ["abc", "cellos", "katzs"]))
        self.assertEqual(body["matched"], {"words": ["cash", "only"], "need": 2})
        # One that timed out is not followed by the heavier text scan: the
        # board, and a note.
        search.forget()
        with self.no_vectors(psycopg2.errors.QueryCanceled("statement timeout")), \
                mock.patch.object(queries, "text_matches", wraps=queries.text_matches) as scan:
            body = self.get("cash only")
            scan.assert_not_called()
        self.assertEqual((body["semantic"], self.keys(body)), ("unavailable", ["katzs", "cellos", "abc"]))
        self.assertIn("not available right now", " ".join(body["notes"]))

    def test_a_question_matches_the_words_some_comment_uses(self):
        # Nobody wrote "cash", "only" and "parents" of one place, so the
        # comments that use the most of them together count, and the note
        # says so. Asked for strictly, this was an empty list.
        with self.no_vectors():
            body = self.get("where should I take my parents, cash only?")
        self.assertEqual(body["matched"], {"words": ["take", "parents", "cash", "only"], "need": 2})
        self.assertEqual(self.keys(body), ["abc", "cellos", "katzs"])
        self.assertEqual([i["people"] for i in body["items"]], [1, 1, 1])
        self.assertIn("at least 2 of them", " ".join(body["notes"]))
        # A word that turns the phrase round keeps the match strict.
        with self.no_vectors(), mock.patch.dict(os.environ, {parse.KEY_VAR: ""}):
            body = self.get("not zzz slice")
        self.assertEqual((body["semantic"], body["items"]), ("text", []))

    def test_punctuation_is_not_a_word_to_match(self):
        with self.no_vectors():
            self.assertEqual(self.keys(self.get("cash & only")), ["abc", "cellos", "katzs"])

    def test_a_long_text_match_is_named_in_part_and_read_in_pages(self):
        with self.no_vectors(), mock.patch.object(search, "TEXT_IDS", 2):
            body = self.get("slice")
        katzs = body["items"][0]
        self.assertEqual((katzs["entity_key"], katzs["people"], katzs["comment_count"],
                          len(katzs["mention_ids"])), ("katzs", 4, 4, 2))
        self.assertEqual(body["matched"], {"words": ["slice"], "need": 1})
        with self.no_vectors():
            whole = self.get("slice", limit=19)["items"][0]["mention_ids"]
        self.assertEqual(whole[:2], katzs["mention_ids"])
        page = {"key": "katzs", "words": ["slice"], "need": 1}
        r = self.client.get("/api/search/matched", params={**page, "offset": 2, "limit": 1})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([c["mention_id"] for c in r.json()], whole[2:3])
        r = self.client.get("/api/search/matched", params={**page, "offset": 3})
        self.assertEqual([c["mention_id"] for c in r.json()], whole[3:])
        self.assertEqual(self.client.get("/api/search/matched", params={**page, "offset": 4}).json(), [])
        # Another city's place has none of these; and a request is bounded.
        other = self.client.get("/api/search/matched",
                                params={**page, "offset": 0, "subreddit": "austinfood"})
        self.assertEqual((other.status_code, other.json()), (200, []))
        for bad in ({"limit": 51}, {"need": 0}, {"words": ["x" * 201]},
                    {"words": [f"w{i}" for i in range(search.TEXT_WORDS_MAX + 1)]}):
            r = self.client.get("/api/search/matched", params={**page, "offset": 0, **bad})
            self.assertEqual(r.status_code, 422, bad)

    def test_filters_hold_under_the_text_match(self):
        with self.no_vectors():
            self.assertEqual(self.keys(self.get("cash only pizza")), ["cellos", "katzs"])
            # abc's only comment in the thread that is not a knock is c4.
            self.assertEqual(self.keys(self.get("cash only in manhattan")), ["abc"])

    def test_text_with_no_word_to_match_is_the_board_and_says_so(self):
        with self.no_vectors():
            out = search.retrieve(subreddits.HOME, search.Parsed(search_text="the best"), 20)
        self.assertEqual((out["semantic"], out["ranked_by"]), ("unavailable", "people"))
        self.assertEqual([i["entity_key"] for i in out["items"]], ["katzs", "cellos", "abc"])
        self.assertIn("most talked-about", " ".join(out["notes"]))

    def test_another_city_is_never_matched_against_new_yorks_vectors(self):
        with mock.patch.object(search, "_embed") as embed:
            r = self.client.get("/api/search/query", params={"q": "tacos", "subreddit": "austinfood"})
            self.assertEqual(r.status_code, 200, r.text)
            embed.assert_not_called()
        body = r.json()
        # The typed word filters the list, as the topic match did: nobody
        # in this empty city wrote it, so nothing is listed, not everything.
        self.assertEqual((body["semantic"], body["items"]), ("text", []))
        self.assertIn("not available for this city yet", " ".join(body["notes"]))

    def test_another_citys_words_filter_its_own_list(self):
        self.q("""insert into threads (id, subreddit, title, created_utc)
                  values ('t3_x', 'austinfood', 'Lunch?', now())""")
        self.q("""insert into comments (id, thread_id, parent_id, subreddit, author, body, permalink,
                                        created_utc, score, score_settled)
                  values ('t1_x1', 't3_x', 't3_x', 'austinfood', 'ua', 'go', '/r/austinfood/x/1/', now(), 3, true),
                         ('t1_x2', 't3_x', 't3_x', 'austinfood', 'ub', 'go', '/r/austinfood/x/2/', now(), 2, true)""")
        self.q("""insert into mentions (comment_id, restaurant_raw, entity_key, dishes, model_version, prompt_hash)
                  values ('t1_x1', 'Veracruz', 'veracruz', '["migas tacos"]', 'm', 'p'),
                         ('t1_x2', 'Franklin', 'franklin', '["brisket"]', 'm', 'p')""")
        apptest.build_views(self.conn)
        search.forget()
        r = self.client.get("/api/search/query", params={"q": "tacos", "subreddit": "austinfood"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual((body["semantic"], self.keys(body)), ("text", ["veracruz"]))
        self.assertEqual([c["comment_id"] for c in body["items"][0]["comments"]], ["t1_x1"])

    def test_unread_words_are_said_to_be_matched_as_typed(self):
        # No key: "not pizza" cannot be read, and the list is not passed off
        # as an answer to it.
        with self.no_vectors(), mock.patch.dict(os.environ, {parse.KEY_VAR: ""}):
            body = self.get("not slice", mode="fast")
        self.assertEqual((body["source"], body["needs_model"]), ("fallback", False))
        self.assertEqual(body["notes"][0], search.AS_TYPED)
        # One request was the whole search, so it is the one logged.
        self.assertEqual(self.q("select mode, source from search_log where query = 'not slice'"),
                         [("fast", "fallback")])

    def test_the_second_pass_reuses_the_first_ones_retrieval(self):
        with fake.FakeAnthropic(answer=lambda p: fake.error(529, "overloaded_error")) as api, \
                mock.patch.dict(os.environ, {parse.KEY_VAR: "sk-test"}), \
                mock.patch.object(parse, "BASE_URL", api.base_url), \
                self.no_vectors(), \
                mock.patch.object(search, "_retrieve", wraps=search._retrieve) as retrieved:
            fast = self.get("zzz slice", mode="fast")
            full = self.get("zzz slice")
            self.assertEqual(retrieved.call_count, 1)
        self.assertEqual((fast["source"], full["source"]), ("unparsed", "fallback"))
        self.assertEqual(fast["items"], full["items"])
        self.assertEqual(self.q("select mode, source from search_log where query = 'zzz slice'"),
                         [("full", "fallback")])

    def test_a_provider_hiccup_is_not_kept_for_the_next_search(self):
        with mock.patch.object(search, "_embed", side_effect=embedding.EmbedError("down")), \
                mock.patch.object(search, "_retrieve", wraps=search._retrieve) as retrieved:
            self.get("cash only")
            self.get("cash only")
            self.assertEqual(retrieved.call_count, 2)

    def test_the_whole_count_can_be_opened(self):
        # Every mention is in the thread "Best slice?", so each place's
        # count for "slice" is all of its people who did not knock it.
        with self.no_vectors():
            body = self.get("slice")
        self.assertEqual([(i["entity_key"], i["people"]) for i in body["items"]],
                         [("katzs", 4), ("cellos", 3), ("abc", 1)])
        katzs, cellos, _ = body["items"]
        # Three comments come with the answer; the ids name all four.
        self.assertEqual((len(katzs["comments"]), len(katzs["mention_ids"])), (3, 4))
        self.assertEqual([c["mention_id"] for c in katzs["comments"]], katzs["mention_ids"][:3])
        r = self.client.get("/api/search/comments", params={"ids": katzs["mention_ids"]})
        self.assertEqual(r.status_code, 200, r.text)
        rest = r.json()
        self.assertEqual([c["mention_id"] for c in rest], katzs["mention_ids"])
        self.assertEqual({c["author"] for c in rest}, {"u5", "u6", "u7", "u8"})
        # Never a link to a deleted comment, here either.
        r = self.client.get("/api/search/comments", params={"ids": cellos["mention_ids"]})
        links = {c["comment_id"]: c["permalink"] for c in r.json()}
        self.assertIsNone(links["t1_c2"])
        self.assertTrue(links["t1_c1"].endswith("/a/1/"))
        # Ids are only ever this city's mentions; and a request is bounded.
        other = self.client.get("/api/search/comments",
                                params={"ids": katzs["mention_ids"], "subreddit": "austinfood"})
        self.assertEqual((other.status_code, other.json()), (200, []))
        self.assertEqual(self.client.get("/api/search/comments",
                                         params={"ids": list(range(51))}).status_code, 422)
        self.assertEqual(self.client.get("/api/search/comments").status_code, 422)

    def test_a_meaning_ranked_count_names_every_comment_it_counts(self):
        # The vector query is faked (the class below runs the real one where
        # there is pgvector): four of katzs' comments are near, by four people.
        ids = dict(self.q("""select comment_id, min(id) from mentions
                             where entity_key = 'katzs' group by 1"""))
        near = [{"entity_key": "katzs", "mention_id": ids[c], "comment_id": c, "person": who,
                 "similarity": sim}
                for c, who, sim in (("t1_c5", "u5", 0.7), ("t1_c6", "u6", 0.9),
                                    ("t1_c7", "u7", 0.8), ("t1_c8", "u8", 0.6))]
        with mock.patch.multiple(
                "app.search", _embed=mock.Mock(return_value="[0]"),
                queries=mock.Mock(wraps=queries, semantic_matches=mock.Mock(return_value=near))):
            body = self.get("cash only")
        self.assertEqual((body["semantic"], body["ranked_by"], body["total"]), ("ok", "matching_people", 1))
        katzs = body["items"][0]
        self.assertEqual(katzs["people"], 4)
        self.assertEqual(katzs["mention_ids"], [ids[c] for c in ("t1_c6", "t1_c7", "t1_c5", "t1_c8")])
        self.assertEqual([c["comment_id"] for c in katzs["comments"]], ["t1_c6", "t1_c7", "t1_c5"])

    def test_the_boards_own_count_names_no_comments_of_its_own(self):
        body = self.get("pizza")
        self.assertEqual({i["mention_ids"] for i in body["items"]}, {None})

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
        self.assertEqual(cellos["mention_ids"], [c["mention_id"] for c in cellos["comments"]])
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
