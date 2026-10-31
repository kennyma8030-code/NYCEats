"""The daily extraction run and the settle re-read, against a throwaway Postgres.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55493/livetest python -m pytest tests

Thread selection by state (age, subreddit, floor), late comments on a
thread done before, long comments alone, the redo's retry of a failed
chunk of several one comment at a time, keys for names in other scripts,
and the settle pass: 40 hours, posts, deletions and edits. The API is
tests/fake_anthropic.py and Arctic Shift is mocked; the first classes need
no database.
"""

import datetime as dt
import os
import re
import unicodedata
import unittest
from unittest import mock

from fakes import ROOT

import anthropic_v6 as AV
import db
import extract
import extract_v6 as X
import fake_anthropic as F
import pgtest
import poller
import prompt_v6
import test_extract_budget_guards as G
import test_extract_v6_db as base
import test_extract_v6_thread_db as TT
import thread_chunks as T

QUIET = base.QUIET
TH = prompt_v6.PROMPT_HASH_THREAD
H = dt.timedelta(hours=1)


_RUNS = iter(range(1, 10**6))


def fake(answer=TT.answer, **kw):
    """A fake API whose batch ids do not repeat an earlier fake's in the same
    test (each starts counting from 1), as a new day's run would see."""
    api = F.FakeAnthropic(answer, **kw)
    api._n = next(_RUNS) * 1000
    return api


def text(request):
    """The user message of a direct request or of a batch's request."""
    return F.user_text(request.get("params", request))


# ---------------------------------------------------------------- no database
def old_normalize(raw):
    """normalize_entity exactly as it was before other scripts were kept
    (extract.py at 54ed680): every key stored so far was made by this."""
    s = (raw or "").lower().replace("'", "").replace("’", "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = " ".join(w for w in re.sub(r"[^a-z0-9]+", " ", s).split() if w != "and")
    if s.startswith("the "):
        s = s[4:]
    for suffix in (" restaurant", " nyc"):
        if s.endswith(suffix):
            s = s[:-len(suffix)]
    return s.strip()


LATIN = ["L'Industrie", "L’industrie Pizzeria", "Ba Xuyên", "Joe & Pat's", "The Four Horsemen", "Café Mogador",
         "Đông Restaurant", "Straße Bar", "Smørrebrød NYC", "Łódź Deli", "Ñ", "Mamá Pizza", "Xi'an Famous Foods",
         "Keens", "PlaceAlpha", "S & P Lunch", "7th Street Burger", "Ｆｕｌｌｗｉｄｔｈ", "Lucali", "Cafe ½",
         "Kopitiam 鼎泰豐", "Joe's Shanghai 鹿鸣春", "Nom Wah Tea Parlor (Chinatown)", "Uncle Boons",
         "!!!", "", "   ", "and", "the", "Bánh Mì Saigon"]
OTHER = {"鱼你在一起": "鱼你在一起", "불짬뽕": "불짬뽕", "Генатсвале": "генатсвале", "मैनहट्टा": "मैनहट्टा",
         "鹿鸣春 & 金": "鹿鸣春 金", "Гена и Ко": "гена и ко"}


class Keys(unittest.TestCase):
    def test_every_key_the_old_rules_made_is_unchanged(self):
        with open(os.path.join(ROOT, "chains.txt"), encoding="utf-8") as f:
            names = [line.strip() for line in f if line.strip()] + LATIN
        for name in names:
            old = old_normalize(name)
            if old:
                self.assertEqual(extract.normalize_entity(name), old, name)
            self.assertEqual(extract.latin_key(name), old, name)

    def test_names_in_other_scripts_keep_their_letters(self):
        for name, key in OTHER.items():
            self.assertEqual(old_normalize(name), "")
            self.assertEqual(extract.normalize_entity(name), key, name)
        for name in ("!!!", "", "  ", "&"):
            self.assertEqual(extract.normalize_entity(name), "")
        # Composed, not decomposed: Hangul stays syllables, Devanagari keeps its vowel signs.
        self.assertEqual(len(extract.normalize_entity("불짬뽕")), 3)
        self.assertIn("ै", extract.normalize_entity("मैनहट्टा"))
        row = X.mention_row(X.Item("comment", "t1_x", None, None, TH), F.mention("불짬뽕"))
        self.assertEqual(row["entity_key"], "불짬뽕")


class LoneChunks(unittest.TestCase):
    def rows(self, bodies):
        return [{"comment_id": f"t1_{i}", "parent_comment_id": None, "author": f"u{i}", "body": b,
                 "created_utc": f"2026-10-01T00:00:{i:02d}"} for i, b in enumerate(bodies)]

    def test_a_comment_over_3000_characters_is_a_chunk_of_its_own(self):
        long = " ".join(f"PlaceL{i:03d} rocks." for i in range(200))       # 3,399 characters
        rows = self.rows(["PlaceA", long, "PlaceB", "x" * 3000])
        due = {r["comment_id"] for r in rows}
        chunks = T.chunk_thread("t3_t", rows, due, post_due=True)
        self.assertEqual([(c.post_item, c.members) for c in chunks],
                         [(True, ["t1_0", "t1_2", "t1_3"]), (False, ["t1_1"])])    # 3,000 exactly packs
        # Off, everything packs as before.
        self.assertEqual(len(T.chunk_thread("t3_t", rows, due, post_due=True, lone_chars=None)), 1)
        # Only long ones: the post goes in a chunk of its own, each long comment in another.
        chunks = T.chunk_thread("t3_t", rows, {"t1_1"}, post_due=True)
        self.assertEqual([(c.post_item, c.members) for c in chunks], [(True, []), (False, ["t1_1"])])

    def test_the_thread_prompt_hash_is_unchanged(self):
        self.assertEqual(prompt_v6.PROMPT_HASH_THREAD, "d92ec8610d8c")


class Parsing(unittest.TestCase):
    def test_floors_ages_and_subreddits(self):
        subs = X.parse_subreddits("foodnyc,r/chicagofood")
        self.assertEqual(subs, ["FoodNYC", "chicagofood"])
        self.assertEqual(X.parse_subreddits(None), ["FoodNYC"])
        f = X.parse_floors("FoodNYC=2025-06-01, chicagofood=all", subs)
        self.assertEqual(f, {"FoodNYC": dt.datetime(2025, 6, 1, tzinfo=dt.timezone.utc), "chicagofood": None})
        self.assertIsNone(X.parse_floors("all", subs))
        self.assertEqual(X.parse_floors("2025-06-01"), dt.datetime(2025, 6, 1, tzinfo=dt.timezone.utc))
        for bad, s in (("FoodLosAngeles=2025-06-01", subs), ("FoodNYC=2025-06-01", None), ("FoodNYC", subs),
                       ("FoodNYC=soon", subs), ("all=2025-01-01", subs),
                       # A subreddit added to the run without a pair would get its whole history.
                       ("FoodNYC=2025-06-01", subs)):
            with self.assertRaises(SystemExit):
                X.parse_floors(bad, s)
        with self.assertRaises(SystemExit) as e:
            X.parse_floors("FoodNYC=2025-06-01", ["FoodNYC", "FoodLosAngeles"])
        self.assertIn("FoodLosAngeles", str(e.exception))
        self.assertEqual(X.parse_age("48h"), 48 * H)
        self.assertEqual(X.parse_age("2d"), 48 * H)
        self.assertEqual(X.parse_age("36.5"), 36.5 * H)
        self.assertIsNone(X.parse_age(None))
        for bad in ("-1h", "soon", "infh"):
            with self.assertRaises(SystemExit):
                X.parse_age(bad)

    def test_thread_flags_are_refused_in_comment_mode(self):
        for flags in (["--subreddit", "FoodNYC"], ["--min-post-age", "48h"]):
            with self.assertRaises(SystemExit):
                X.main(["--dry-run"] + flags)


# ---------------------------------------------------------------- selection
def opts(**kw):
    return X.ThreadOpts(**kw)


class Selection(TT.ThreadCase):
    def age(self, tid, hours):
        """Move a thread and its comments to `hours` ago, keeping their spacing."""
        self.q("""with t as (select created_utc from threads where id = %s)
                  update comments set created_utc = comments.created_utc - (t.created_utc - (now() - %s))
                  from t where comments.thread_id = %s returning 1""", (tid, hours * H, tid))
        self.q("update threads set created_utc = now() - %s where id = %s returning 1", (hours * H, tid))

    def items(self, tid):
        return {tid} | {r[0] for r in self.q("select id from comments where thread_id = %s", (tid,))}

    def test_threads_younger_than_the_minimum_age_are_not_touched(self):
        for tid in ("t3_a", "t3_b"):
            self.age(tid, 72)
        self.age("t3_c", 47)                        # a day and 23 hours: not yet
        with fake() as api:
            self.batch(api, opts=opts(min_age=48 * H))
        st = self.state()
        self.assertFalse(set(st) & self.items("t3_c"))           # neither the post nor any comment
        self.assertTrue(all("PlacePost" not in text(r) for r in api.batch_requests))
        self.assertIn("t3_a", st)
        self.assertIn("t3_old", st)                              # 400 days old: no upper bound
        self.assertTrue(all(v[2] and v[1] == TH for v in st.values()))
        # A day later it is old enough, and goes out whole: the post as [0] and every comment.
        self.age("t3_c", 49)
        with fake() as api:
            self.batch(api, opts=opts(min_age=48 * H))
        users = [text(r) for r in api.batch_requests]
        self.assertTrue(users and all(u.startswith("[0] POST: PlacePost") for u in users))
        self.assertTrue(self.items("t3_c") <= set(self.state()))

    def test_subreddits_and_a_floor_each(self):
        self.age("t3_a", 24 * 40)                 # 40 days old
        with fake() as api:
            self.direct(api)                      # by default r/FoodNYC only, whole history
        self.assertNotIn("t1_chi", self.state())
        self.q("delete from extraction_state returning 1")
        self.q("delete from mentions returning 1")
        self.q("delete from extract_chunks returning 1")
        floors = X.parse_floors("FoodNYC=30d,chicagofood=all", ["FoodNYC", "chicagofood"])
        with fake() as api:
            self.direct(api, opts=opts(subs=["FoodNYC", "chicagofood"]), since=floors)
        st = self.state()
        self.assertIn("t1_chi", st)                              # chicagofood: no floor
        self.assertFalse(st.keys() & (self.items("t3_a") | self.items("t3_old")))   # older than r/FoodNYC's floor
        self.assertIn("t3_c", st)
        self.assertEqual(self.q("select comment_id, thread_id from mentions where entity_key = 'placechicago' "
                                "order by 1"), [("t1_chi", None), (None, "t3_chi")])

    def test_a_late_comment_goes_out_alone_under_its_ancestors_and_the_post(self):
        with fake() as api:
            self.direct(api)
        post_before = self.q("select extracted_at, prompt_hash from extraction_state where item_id = 't3_c'")
        self.q("""insert into comments (id, subreddit, thread_id, parent_id, parent_comment_id, author, body,
                    permalink, created_utc, first_seen_at)
                  values ('t1_late', 'FoodNYC', 't3_c', 't1_d8', 't1_d8', 'zoe', 'PlaceLate is better',
                          '/r/x/t1_late', now(), now()) returning 1""")
        db.fill_tree(self.conn, ["t3_c"])
        self.assertEqual(X.thread_candidates(self.conn, newest_first=True), ["t3_c"])
        with fake() as api:
            self.batch(api, opts=opts(min_age=0 * H))
        self.assertEqual(len(api.batch_requests), 1)
        user = text(api.batch_requests[0])
        self.assertTrue(user.startswith("POST: PlacePost worth it?"))            # the post, as context
        self.assertEqual(list(TT.numbered(user)), [1])                             # only the late comment
        self.assertIn("[1] u/zoe (reply to u/u8, quoted above): PlaceLate is better", user)
        ctx = user.split(prompt_v6.thread.CONTEXT_HEADER, 1)[1].split("[1]")[0]
        for i in range(1, 9):                                                      # the whole chain, top first
            self.assertIn(f"level {i} talk about PlaceDeep{i}", ctx)
        self.assertLess(ctx.index("PlaceDeep1"), ctx.index("PlaceDeep8"))
        self.assertEqual(self.q("select extracted_at, prompt_hash from extraction_state where item_id = 't3_c'"),
                         post_before)
        self.assertEqual(self.q("select entity_key from mentions where comment_id = 't1_late'"), [("placelate",)])

    def test_a_batch_left_by_yesterdays_run_is_collected_not_sent_again(self):
        with fake(polls_until_ended=10**6) as api:
            b = X.Budget(10.0)
            jobs, _ = X.build_thread_jobs(self.conn, ["t3_a"], opts(), log=QUIET)
            bid = X._submit(self.conn, AV.client("k", api.base_url), b, jobs, QUIET)
            self.assertNotIn("t3_a", X.thread_candidates(self.conn))             # its items carry the batch
            api.polls_until_ended = 0
            sent = len(api.batch_requests)
            self.batch(api)                                                      # the next day's run
        self.assertEqual(self.q("select status from extract_batches where id = %s", (bid,)), [("collected",)])
        self.assertEqual(len([r for r in api.batch_requests[sent:] if "Best dumplings" in text(r)]), 0)
        self.assertTrue(all(v[2] for v in self.state().values()))

    def test_a_long_comment_is_sent_alone_in_thread_mode(self):
        long = " ".join(f"PlaceT{i:02d} is a tier pick." for i in range(150))
        self.q("""insert into comments (id, subreddit, thread_id, parent_id, author, body, permalink, created_utc,
                    first_seen_at)
                  select 't1_tier', subreddit, id, id, 'tierlist', %s, '/r/x/t1_tier', created_utc, created_utc
                  from threads where id = 't3_a' returning 1""", (long,))
        with fake() as api:
            self.direct(api, ids=["t3_a"])
        mine = [text(r) for r in api.requests if "] u/tierlist" in text(r)]
        self.assertEqual(len(mine), 1)
        self.assertEqual(list(TT.numbered(mine[0])), [1])
        self.assertTrue(all(v[1] == TH for v in self.state().values()))
        self.assertEqual(len(self.q("select 1 from mentions where comment_id = 't1_tier'")), 150)


# ---------------------------------------------------------------- redo
LIST2 = [" ".join(f"PlaceR{n}x{i:03d} ok." for i in range(150)) for n in (1, 2)]     # ~2,250 characters each


class RedoSplit(TT.ThreadCase):
    """Two comments read with the old cut, together in one redo chunk that
    runs out of tokens: each is tried again on its own, in the same run."""

    def load(self):
        super().load()
        with self.conn.cursor() as cur:
            for n, body in enumerate(LIST2, start=1):
                cur.execute("""insert into comments (id, subreddit, thread_id, parent_id, author, body, permalink,
                                 created_utc, first_seen_at)
                               select %s, subreddit, id, id, %s, %s, '/r/x/' || %s,
                                      created_utc + %s * interval '1 minute', created_utc
                               from threads where id = 't3_a'""", (f"t1_l{n}", f"lister{n}", body, f"t1_l{n}", 30 + n))
            cur.execute("update comments set body = 'level 7 talk about PlaceDeep7' where id = 't1_d7'")
        self.conn.commit()

    def old_run(self):
        with mock.patch.object(prompt_v6.thread, "MEMBER_CHARS", 1500), F.FakeAnthropic(TT.answer) as api:
            self.direct(api)
        self.q("update extraction_state set output = output - 'member_chars' returning 1")

    @staticmethod
    def cut_pairs(p):
        if TT.is_thread(p) and len(TT.numbered(text(p))) > 1:
            return 200, F.message('{"mentions": [', stop="max_tokens")
        return TT.answer(p)

    def places(self, cid):
        return {k for (k,) in self.q("select entity_key from mentions where comment_id = %s", (cid,))}

    def check(self, api, requests):
        self.assertEqual(len(requests), 3)                     # the pair, then each alone
        self.assertEqual([len(TT.numbered(text(r))) for r in requests], [2, 1, 1])
        for n in (1, 2):
            self.assertIn(f"placer{n}x149", self.places(f"t1_l{n}"))
            self.assertEqual(len(self.places(f"t1_l{n}")), 150)
        self.assertEqual(X.redo_candidates(self.conn, dt.datetime.now(dt.timezone.utc)), {})

    def test_direct(self):
        self.old_run()
        before = dt.datetime.now(dt.timezone.utc)
        self.assertEqual(X.redo_candidates(self.conn, before), {"t3_a": ["t1_l1", "t1_l2"]})
        with fake(self.cut_pairs) as api:
            X.run_redo(self.conn, AV.client("k", api.base_url), X.Budget(10.0, G.ceiling(50.0)), opts(), before,
                       log=QUIET, stats=X.Stats())
        self.check(api, api.requests)

    def test_batch(self):
        self.old_run()
        before = dt.datetime.now(dt.timezone.utc)
        with fake(self.cut_pairs) as api:
            X.run_redo(self.conn, AV.client("k", api.base_url), X.Budget(10.0, G.ceiling(50.0)), opts(), before,
                       batch=True, poll_seconds=0, log=QUIET, sleep=lambda s: None, stats=X.Stats())
        self.check(api, api.batch_requests)

    def test_comments_given_up_after_two_failed_chunks_of_several_are_tried_alone(self):
        """The production case: two 2-comment redo chunks failed, which used to
        be the end of it."""
        self.old_run()
        before = dt.datetime.now(dt.timezone.utc)
        for _ in range(2):
            self.q("""insert into extract_chunks (id, version, thread_id, prompt_hash, effort, members, status,
                        error, cost_usd, finished_at)
                      values (%s, 'v6', 't3_a', %s, 'medium', array['t1_l1', 't1_l2'], 'failed', 'max_tokens', 0.01,
                              now()) returning 1""", (X.new_chunk_id(redo=True), TH))
        self.assertEqual(X.redo_candidates(self.conn, before), {"t3_a": ["t1_l1", "t1_l2"]})
        jobs = X.build_redo_jobs(self.conn, X.redo_candidates(self.conn, before), opts())
        self.assertEqual(sorted(j.chunk.members for j in jobs), [["t1_l1"], ["t1_l2"]])
        # Alone, two failures are the end, as before.
        cut = lambda p: (200, F.message('{"mentions": [', stop="max_tokens"))     # noqa: E731
        with fake(cut) as api:
            X.run_redo(self.conn, AV.client("k", api.base_url), X.Budget(10.0, G.ceiling(50.0)), opts(), before,
                       log=QUIET, stats=X.Stats())
        self.assertEqual(len(api.requests), 4)                 # each alone, twice
        self.assertEqual(X.redo_candidates(self.conn, before), {})


# ---------------------------------------------------------------- non-Latin names on record
class RestoreUnkeyed(TT.ThreadCase):
    def test_mentions_dropped_for_a_name_in_another_script_are_stored_once(self):
        out = {"mentions": [dict(F.mention("불짬뽕"), id=1), dict(F.mention("PlaceAlpha"), id=1)],
               "chunk_id": "ch-x"}
        self.q("""insert into extraction_state (item_id, version, kind, prompt_hash, model, attempts, extracted_at,
                    output, cost_usd)
                  values ('t1_top', 'v6', 'comment', %s, %s, 1, now(), %s, 0.001) returning 1""",
               (TH, prompt_v6.MODEL, X.Json(out)))
        self.q("""insert into mentions (comment_id, restaurant_raw, entity_key, model_version, prompt_hash,
                    schema_version)
                  values ('t1_top', 'PlaceAlpha', 'placealpha', 'm', %s, 6) returning 1""", (TH,))
        state = self.q("select * from extraction_state")
        self.assertEqual(X.restore_unkeyed(self.conn, log=QUIET), (1, 0))
        self.assertEqual(self.q("select count(*) from mentions"), [(1,)])
        self.assertEqual(X.restore_unkeyed(self.conn, yes=True, log=QUIET), (1, 1))
        self.assertEqual(X.restore_unkeyed(self.conn, yes=True, log=QUIET), (1, 0))
        self.assertEqual(sorted(self.q("select entity_key, prompt_hash, schema_version from mentions")),
                         [("placealpha", TH, 6), ("불짬뽕", TH, 6)])
        self.assertEqual(self.q("select * from extraction_state"), state)          # nothing else changes
        self.q("update extraction_settings set read_version = 'v6' returning 1")
        self.assertIn(("불짬뽕",), self.q("select entity_key from live_mentions"))


# ---------------------------------------------------------------- settle
def arctic(item_id, **kw):
    """An Arctic Shift record for a stored comment or post, as the ids endpoints return it."""
    return dict({"id": item_id[3:], "score": 7, "controversiality": 0, "upvote_ratio": 0.9, "num_comments": 12},
                **kw)


class Settle(TT.ThreadCase):
    def setUp(self):
        super().setUp()
        # Every fixture item 41 hours old and not yet settled.
        self.q("update threads set created_utc = now() - interval '41 hours', score_settled = false returning 1")
        self.q("update comments set created_utc = now() - interval '41 hours', score_settled = false returning 1")

    def settle(self, comments=(), posts=(), missing=()):
        """poller.settle_once with Arctic Shift answering these records; any
        id not among them and not in `missing` comes back as it is stored."""
        stored = {r[0]: r[1:] for r in self.q("select id, body, author from comments")}
        stored_p = {r[0]: r[1:] for r in self.q("select id, selftext, author from threads")}
        mine = {c["id"]: c for c in comments}
        mine_p = {p["id"]: p for p in posts}

        def by_id(table, given, kind):
            def fetch(bare):
                out = []
                for b in bare:
                    full = ("t1_" if kind == "comment" else "t3_") + b
                    if full in missing:
                        continue
                    if b in given:
                        out.append(given[b])
                    else:
                        text, author = table[full]
                        out.append(arctic(full, author=author, **({"body": text} if kind == "comment"
                                                                   else {"selftext": text})))
                return out
            return fetch
        with mock.patch.object(poller.arctic, "comments_by_id", by_id(stored, mine, "comment")), \
                mock.patch.object(poller.arctic, "posts_by_id", by_id(stored_p, mine_p, "post")), \
                mock.patch.object(poller.time, "sleep", lambda s: None), \
                mock.patch("builtins.print"):
            poller.settle_once(self.conn)

    def test_the_threshold_is_40_hours(self):
        self.assertEqual(db.SETTLE_HOURS, 40.0)
        self.q("update comments set created_utc = now() - interval '39 hours' where id = 't1_top' returning 1")
        self.q("update threads set created_utc = now() - interval '39 hours' where id = 't3_c' returning 1")
        self.assertNotIn("t1_top", db.unsettled_comment_ids(self.conn, limit=1000))
        self.assertIn("t1_r1", db.unsettled_comment_ids(self.conn, limit=1000))
        self.assertEqual(sorted(db.unsettled_thread_ids(self.conn)), ["t3_a", "t3_b", "t3_chi", "t3_old"])
        # At insert: past 40 hours an item arrives settled, under it not.
        t = int(dt.datetime.now(dt.timezone.utc).timestamp())      # now, not at import: the suite can be slow
        db.insert_threads(self.conn, [dict(arctic("t3_n1", subreddit="FoodNYC", title="x", created_utc=t - 39 * 3600)),
                                      dict(arctic("t3_n2", subreddit="FoodNYC", title="y", created_utc=t - 41 * 3600))])
        db.insert_comments(self.conn, [
            {"id": f"n{i}", "subreddit": "FoodNYC", "link_id": "t3_n1", "parent_id": "t3_n1", "body": "b",
             "created_utc": t - h * 3600} for i, h in ((1, 39), (2, 41))])
        self.assertEqual(self.q("select id, score_settled from threads where id like 't3_n%%' order by 1"),
                         [("t3_n1", False), ("t3_n2", True)])
        self.assertEqual(self.q("select id, score_settled from comments where id like 't1_n%%' order by 1"),
                         [("t1_n1", False), ("t1_n2", True)])

    def test_scores_deletions_and_what_is_not_a_deletion(self):
        self.settle(comments=[arctic("t1_top", body="[deleted]", author="[deleted]", score=40),
                              arctic("t1_r1", body="[removed]", author="[deleted]"),
                              # A deleted account: the comment and its permalink are still up.
                              arctic("t1_plus", body="+1", author="[deleted]", score=2)],
                    posts=[arctic("t3_b", selftext="[removed]", removed_by_category="moderator"),
                           arctic("t3_a", selftext=base.THREADS[0][3], author="[deleted]",
                                  score=300, upvote_ratio=0.97, num_comments=88)],
                    missing={"t1_r2", "t3_c"})
        c = {r[0]: r[1:] for r in self.q("select id, body, score, was_deleted_later, score_settled, original_body "
                                         "from comments")}
        self.assertEqual(c["t1_top"], ("PlaceAlpha is great", 40, True, True, None))   # the text we had is kept
        self.assertEqual(c["t1_r1"][2], True)
        self.assertEqual(c["t1_plus"], ("+1", 2, False, True, None))
        self.assertEqual(c["t1_r2"][2:4], (True, True))                               # gone from the archive
        self.assertEqual(c["t1_ondel"][1:4], (7, False, True))
        self.assertTrue(all(v[3] for v in c.values()))
        t = {r[0]: r[1:] for r in self.q("select id, score, upvote_ratio, num_comments, was_deleted_later, "
                                         "score_settled, selftext from threads")}
        self.assertEqual(t["t3_a"][:5], (300, 0.97, 88, False, True))
        self.assertEqual(t["t3_b"][3:6], (True, True, "[removed]"))
        self.assertEqual(t["t3_c"][3:5], (True, True))
        self.assertEqual(db.unsettled_comment_ids(self.conn), [])
        self.assertEqual(db.unsettled_thread_ids(self.conn), [])

    def test_an_edit_takes_the_new_text_and_the_next_run_replaces_its_mentions(self):
        with fake() as api:
            self.direct(api)
        self.assertEqual(self.q("select entity_key from mentions where comment_id = 't1_top'"), [("placealpha",)])
        cost = self.q("select cost_usd from extraction_state where item_id = 't1_top'")[0][0]
        self.settle(comments=[arctic("t1_top", body="Edit: PlaceAlpha closed, go to PlaceOmega", author="alice"),
                              # Whitespace alone is not an edit.
                              arctic("t1_r1", body="> PlaceAlpha is great\n\n  agree, PlaceBeta too ", author="op")],
                    posts=[arctic("t3_c", selftext="Update: PlacePost was great", author="poster")])
        c = self.q("select body, original_body, was_deleted_later from comments where id = 't1_top'")[0]
        self.assertEqual(c, ("Edit: PlaceAlpha closed, go to PlaceOmega", "PlaceAlpha is great", False))
        self.assertEqual(self.q("select original_body from comments where id = 't1_r1'"), [(None,)])
        self.assertEqual(self.q("select selftext, original_selftext from threads where id = 't3_c'"),
                         [("Update: PlacePost was great", None)])
        # Due again, with a fresh count of attempts; the mentions stay live until replaced.
        self.assertEqual(self.q("select extracted_at, attempts, prompt_hash from extraction_state "
                                "where item_id in ('t1_top', 't3_c') order by item_id"),
                         [(None, 0, TH), (None, 0, TH)])
        self.assertEqual(self.q("select entity_key from mentions where comment_id = 't1_top'"), [("placealpha",)])
        self.assertEqual(X.thread_candidates(self.conn), ["t3_a", "t3_c"])
        with fake() as api:
            self.batch(api)
        users = [text(r) for r in api.batch_requests]
        self.assertEqual(len(users), 2)
        self.assertTrue(any(list(TT.numbered(u)) == [1] and "PlaceOmega" in u for u in users))
        self.assertTrue(any(u.startswith("[0] POST: PlacePost worth it?\nUpdate: PlacePost was great") for u in users))
        self.assertEqual(sorted(k for (k,) in self.q("select entity_key from mentions where comment_id = 't1_top'")),
                         ["placealpha", "placeomega"])
        self.assertEqual(self.q("select count(*) from mentions where comment_id = 't1_top'"), [(2,)])
        self.assertGreater(self.q("select cost_usd from extraction_state where item_id = 't1_top'")[0][0], cost)
        # A second edit keeps the first text.
        self.q("update comments set score_settled = false where id = 't1_top' returning 1")
        self.settle(comments=[arctic("t1_top", body="PlaceZeta now", author="alice")])
        self.assertEqual(self.q("select body, original_body from comments where id = 't1_top'"),
                         [("PlaceZeta now", "PlaceAlpha is great")])
        with fake() as api:
            self.batch(api)
        self.assertEqual(self.q("select entity_key from mentions where comment_id = 't1_top'"), [("placezeta",)])

    def live_ids(self):
        return [r[0] for r in self.q("select id from comments where body not in ('[deleted]', '[removed]') "
                                     "and btrim(body) <> '' order by id")]

    def test_too_many_edits_at_once_are_left_for_a_later_pass(self):
        ids = self.live_ids()
        logs = []
        fetched = {i: arctic(i, body="&gt; changed " + i, author="x") for i in ids}
        self.assertGreater(len(ids), 5)
        gone, edited, later = db.settle_items(self.conn, "comment", fetched, log=logs.append)
        self.assertEqual((gone, edited, later), (0, 0, set(ids)))
        self.assertTrue(any("too many to be edits" in line for line in logs))
        self.assertEqual(self.q("select count(*) from comments where original_body is not null"), [(0,)])
        # Not settled: a later pass reads them again, and this one does not.
        self.assertEqual(self.q("select count(*) from comments where id = any(%s) and score_settled", (ids,)),
                         [(0,)])
        self.assertTrue(set(ids) <= set(db.unsettled_comment_ids(self.conn, limit=1000)))
        self.assertFalse(set(ids) & set(db.unsettled_comment_ids(self.conn, limit=1000, skip=ids)))

    def test_posts_have_more_room_for_edits_than_comments(self):
        # Three of six posts edited ("EDIT: thanks all"): half, within the posts' 50%.
        self.q("""insert into threads (id, subreddit, title, selftext, created_utc, score_settled)
                  values ('t3_e', 'FoodNYC', 'e', 'body', now() - interval '41 hours', false) returning 1""")
        edits = ["t3_a", "t3_c", "t3_chi"]                 # half of them (t3_b was removed when stored)
        some = {p: arctic(p, selftext=f"EDIT: thanks all ({p})") for p in edits}
        rest = {p: arctic(p, selftext=s) for p, s in self.q("select id, selftext from threads where not id = any(%s)",
                                                             (edits,))}
        with mock.patch.object(db, "MIN_EDITS_CHECKED", 1):
            self.assertEqual(db.settle_items(self.conn, "post", dict(some, **rest), log=QUIET)[1:], (3, set()))
            # The same share of comments is over theirs.
            ids = self.live_ids()[:6]
            fetched = {i: arctic(i, body=f"edit {i}" if n < 3 else b, author="a")
                       for n, (i, b) in enumerate(self.q("select id, body from comments where id = any(%s) "
                                                         "order by id", (ids,)))}
            self.assertEqual(db.settle_items(self.conn, "comment", fetched, log=QUIET)[1:], (0, set(ids[:3])))

    def test_a_record_without_text_is_not_an_edit(self):
        fetched = {"t1_top": {"id": "top", "score": 9}, "t1_r1": dict(arctic("t1_r1"), body=None),
                   "t3_c": {"id": "c", "score": 4}}
        self.assertEqual(db.settle_items(self.conn, "comment", {k: v for k, v in fetched.items() if k[:2] == "t1"},
                                         log=QUIET), (0, 0, set()))
        self.assertEqual(db.settle_items(self.conn, "post", {"t3_c": fetched["t3_c"]}, log=QUIET), (0, 0, set()))
        self.assertEqual(self.q("select id, body, score, score_settled from comments where id in ('t1_top', 't1_r1') "
                                "order by id"),
                         [("t1_r1", "> PlaceAlpha is great\n\nagree, PlaceBeta too", 7, True),
                          ("t1_top", "PlaceAlpha is great", 9, True)])
        self.assertEqual(self.q("select selftext, score from threads where id = 't3_c'"), [(None, 4)])

    def test_an_item_in_a_batch_waits(self):
        self.q("""insert into extraction_state (item_id, version, kind, prompt_hash, model, batch_id)
                  values ('t1_top', 'v6', 'comment', %s, %s, 'msgbatch_x'),
                         ('t3_a', 'v6', 'post', %s, %s, 'msgbatch_x') returning 1""",
               (TH, prompt_v6.MODEL, TH, prompt_v6.MODEL))
        self.assertNotIn("t1_top", db.unsettled_comment_ids(self.conn, limit=1000))
        self.assertNotIn("t3_a", db.unsettled_thread_ids(self.conn))
        self.settle(comments=[arctic("t1_top", body="edited", author="alice")])
        self.assertEqual(self.q("select body, score_settled from comments where id = 't1_top'"),
                         [("PlaceAlpha is great", False)])

    def test_an_edit_is_put_off_while_a_v6_run_could_read_the_old_text(self):
        """The race: the pick saw no batch, then a run rendered the old text
        and marked the item in a batch before the update. Checked again in
        the update's transaction, under the v6 lock, the edit waits."""
        fetched = {"t1_top": arctic("t1_top", body="PlaceOmega now", author="alice")}
        self.assertIn("t1_top", db.unsettled_comment_ids(self.conn, limit=1000))
        # 1. A run holds the v6 lock (it may be rendering this very comment).
        other = pgtest.connect()
        try:
            self.assertTrue(X.try_lock(other))
            self.assertEqual(db.settle_items(self.conn, "comment", fetched, log=QUIET), (0, 0, {"t1_top"}))
            self.assertEqual(self.q("select body, score_settled, edited_at from comments where id = 't1_top'"),
                             [("PlaceAlpha is great", False, None)])
            X.unlock(other)
        finally:
            other.close()
        # 2. No run now, but one left the item in a batch after the pick.
        self.q("""insert into extraction_state (item_id, version, kind, prompt_hash, model, batch_id)
                  values ('t1_top', 'v6', 'comment', %s, %s, 'msgbatch_y') returning 1""", (TH, prompt_v6.MODEL))
        self.assertEqual(db.settle_items(self.conn, "comment", fetched, log=QUIET), (0, 0, {"t1_top"}))
        self.assertEqual(self.q("select body, score_settled from comments where id = 't1_top'"),
                         [("PlaceAlpha is great", False)])
        # 3. Collected: the next pass takes it.
        self.q("update extraction_state set batch_id = null, extracted_at = now() returning 1")
        self.assertEqual(db.settle_items(self.conn, "comment", fetched, log=QUIET), (0, 1, set()))
        self.assertEqual(self.q("select body, score_settled, edited_at is not null from comments "
                                "where id = 't1_top'"), [("PlaceOmega now", True, True)])
        # And settle_once does not read a put-off item twice in one pass.
        reads = []
        self.q("update comments set score_settled = false, body = 'PlaceAlpha is great', original_body = null "
               "where id = 't1_top' returning 1")
        other = pgtest.connect()
        try:
            X.try_lock(other)
            with mock.patch.object(poller.arctic, "comments_by_id",
                                   lambda bare: reads.append(list(bare)) or [fetched["t1_top"]] if "top" in bare
                                   else []), \
                    mock.patch.object(poller.arctic, "posts_by_id", lambda bare: []), \
                    mock.patch.object(poller.time, "sleep", lambda s: None), mock.patch("builtins.print"):
                poller.settle_once(self.conn)
        finally:
            other.close()
        self.assertEqual(sum("top" in r for r in reads), 1)
        self.assertEqual(self.q("select score_settled from comments where id = 't1_top'"), [(False,)])


class Evidence(TT.ThreadCase):
    """What a mention clicks through to once its comment was edited, and the
    app's reads before the poller has added the new columns."""

    def body_of(self, mention_id):
        from app import queries
        return self.q(f"""select {queries.evidence_body_sql('m', 'c')} from mentions m
                          join comments c on c.id = m.comment_id where m.id = %s""", (mention_id,))[0][0]

    def test_a_mention_older_than_the_edit_shows_the_text_it_was_read_from(self):
        (old,) = self.q("""insert into mentions (comment_id, restaurant_raw, entity_key, model_version, prompt_hash,
                             created_at)
                           values ('t1_top', 'PlaceAlpha', 'placealpha', 'm', 'legacy', now() - interval '1 hour')
                           returning id""")[0]
        self.q("update comments set created_utc = now() - interval '41 hours' returning 1")
        db.settle_items(self.conn, "comment", {"t1_top": arctic("t1_top", body="PlaceOmega now")}, log=QUIET)
        (new,) = self.q("""insert into mentions (comment_id, restaurant_raw, entity_key, model_version, prompt_hash,
                             created_at)
                           values ('t1_top', 'PlaceOmega', 'placeomega', 'm', 'legacy', now() + interval '1 second')
                           returning id""")[0]
        self.assertEqual(self.body_of(old), "PlaceAlpha is great")
        self.assertEqual(self.body_of(new), "PlaceOmega now")
        self.assertEqual(self.q("select count(*) from mentions"), [(2,)])            # nothing deleted

    def test_reads_work_before_the_schema_has_the_new_columns(self):
        from app import db as appdb
        from app import queries
        (mid,) = self.q("""insert into mentions (comment_id, restaurant_raw, entity_key, model_version, prompt_hash)
                           values ('t1_top', 'PlaceAlpha', 'placealpha', 'm', 'legacy') returning id""")[0]
        with self.conn.cursor() as cur:
            cur.execute("alter table comments drop column original_body, drop column edited_at")
            cur.execute("alter table threads drop column was_deleted_later")
        self.conn.commit()
        self.assertEqual(self.body_of(mid), "PlaceAlpha is great")
        import refresh
        refresh.apply_sql(self.conn, verbose=False)
        items = queries.feed_items(self.conn, None, False, None, None, 100, appdb.fetch_all)
        posts = [i for i in items if i["kind"] == "post"]
        self.assertTrue(posts and all(i["permalink"] for i in posts))
        self.conn.rollback()

    def test_the_feed_hides_a_deleted_posts_link(self):
        from app import db as appdb
        from app import queries
        import refresh
        self.q("update threads set was_deleted_later = true where id = 't3_c' returning 1")
        refresh.apply_sql(self.conn, verbose=False)
        items = {i["id"]: i for i in queries.feed_items(self.conn, None, False, None, None, 100, appdb.fetch_all)}
        self.assertIsNone(items["t3_c"]["permalink"])
        self.assertTrue(items["t3_a"]["permalink"])
        self.conn.rollback()


class ThreadsMigration(base.DbCase):
    def strip(self):
        with self.conn.cursor() as cur:
            cur.execute("drop index threads_unsettled_idx")
            cur.execute("alter table threads drop column score_settled, drop column was_deleted_later, "
                        "drop column original_selftext")
            cur.execute("alter table comments drop column original_body, drop column edited_at")
            # t3_a was polled live (first seen as it was posted); t3_old came from the backfill.
            cur.execute("update threads set first_seen_at = created_utc + interval '400 days' where id = 't3_old'")
        self.conn.commit()

    def test_existing_posts_settled_but_the_live_ones_and_new_ones_not(self):
        self.strip()
        for _ in range(2):
            db.init(self.conn, os.path.join(ROOT, "schema.sql"))
        self.assertEqual(self.q("select id, score_settled, was_deleted_later, original_selftext from threads "
                                "where id in ('t3_a', 't3_old') order by id"),
                         [("t3_a", False, False, None), ("t3_old", True, False, None)])
        self.q("""insert into threads (id, subreddit, title, created_utc) values ('t3_new', 'FoodNYC', 't', now())
                  returning 1""")
        self.assertEqual(self.q("select score_settled from threads where id = 't3_new'"), [(False,)])
        self.assertEqual(self.q("select count(*) from comments where original_body is not null "
                                "or edited_at is not null"), [(0,)])

    def test_the_one_off_update_uses_settle_hours(self):
        # t3_b first seen 20 hours after it was posted: unsettled under 40
        # hours, settled under the 12 db.init passes on here.
        self.q("update threads set first_seen_at = created_utc + interval '20 hours' where id = 't3_b' returning 1")
        self.strip()
        with mock.patch.object(db, "SETTLE_HOURS", 12.0):
            db.init(self.conn, os.path.join(ROOT, "schema.sql"))
        self.assertEqual(self.q("select id, score_settled from threads where id in ('t3_a', 't3_b') order by id"),
                         [("t3_a", False), ("t3_b", True)])
        # Applied by hand (no setting), it is 40.
        self.strip()
        with open(os.path.join(ROOT, "schema.sql"), encoding="utf-8") as f:
            sql = f.read()
        with self.conn.cursor() as cur:
            cur.execute(sql)
        self.conn.commit()
        self.assertEqual(self.q("select id, score_settled from threads where id in ('t3_a', 't3_b') order by id"),
                         [("t3_a", False), ("t3_b", False)])


if __name__ == "__main__":
    unittest.main()
