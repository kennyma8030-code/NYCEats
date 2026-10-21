"""thread_chunks: grouping, packing, splitting, quoted ancestors, and what is an item. No database.

These are the rules decided with the owner (thread_chunks.py's docstring);
the property tests check, on random trees, that every due item lands in
exactly one chunk and that no chunk passes the hard max.
"""

import random
import re
import unittest

import fakes  # noqa: F401  (puts the repo root on sys.path)

import prompt_v6
import thread_chunks as T

TID = "t3_x"


class Rows:
    """A thread built comment by comment, in posting order."""

    def __init__(self):
        self.rows, self.n = [], 0

    def add(self, cid, parent=None, body=None, author=None):
        self.n += 1
        self.rows.append({"comment_id": cid, "parent_comment_id": parent, "author": author or "u" + cid,
                          "body": body if body is not None else f"words from {cid}",
                          "created_utc": f"2026-01-01T{self.n // 3600:02d}:{self.n // 60 % 60:02d}:{self.n % 60:02d}"})
        return cid

    def ids(self):
        return [r["comment_id"] for r in self.rows]


def chunks(rows, due=None, **kw):
    due = set(rows.ids()) if due is None else due
    return T.chunk_thread(TID, rows.rows, due, **kw)


def group(rows, root, size, fan=3):
    """A reply group of `size` comments under top-level `root`, `fan` replies per comment, depth-first."""
    rows.add(root)
    made, frontier = 1, [root]
    while made < size:
        nxt = []
        for p in frontier:
            for _ in range(fan):
                if made >= size:
                    break
                nxt.append(rows.add(f"{root}_{made}", p))
                made += 1
        frontier = nxt


class Grouping(unittest.TestCase):
    def test_small_groups_pack_whole_up_to_the_soft_budget(self):
        r = Rows()
        for g in "abcdef":
            group(r, g, 4)
        out = chunks(r, soft_comments=10)
        self.assertEqual([len(c) for c in out], [8, 8, 8])
        for c in out:
            roots = {m.split("_")[0] for m in c.members}
            for g in roots:   # every group is whole in the chunk that has it
                self.assertEqual(sum(m.split("_")[0] == g for m in c.members), 4)

    def test_token_budget_closes_a_chunk_before_the_count_does(self):
        r = Rows()
        for g in "abcd":
            r.add(g, body="x" * 1500)      # 375 estimated tokens each
        out = chunks(r, soft_comments=15, soft_tokens=800)
        self.assertEqual([len(c) for c in out], [2, 2])

    def test_a_group_past_the_soft_budget_stays_whole_up_to_the_max(self):
        r = Rows()
        group(r, "a", 3)
        group(r, "b", 22)
        group(r, "c", 2)
        out = chunks(r, soft_comments=15, max_comments=25)
        self.assertEqual([len(c) for c in out], [3, 22, 2])
        self.assertEqual(out[1].members[0], "b")

    def test_only_a_group_over_the_max_is_split_and_only_between_branches(self):
        r = Rows()
        r.add("a")
        for k in range(4):                      # four branches of 9 under the top-level comment
            b = r.add(f"a{k}", "a")
            for j in range(8):
                r.add(f"a{k}_{j}", b)
        out = chunks(r, soft_comments=15, max_comments=25)
        self.assertEqual(sum(len(c) for c in out), 37)
        self.assertTrue(all(len(c) <= 25 for c in out))
        branch = lambda m: m.split("_")[0] if m != "a" else "a"  # noqa: E731
        for c in out:
            for k in range(4):
                n = sum(branch(m) == f"a{k}" for m in c.members)
                self.assertIn(n, (0, 9), f"branch a{k} cut inside: {c.members}")
        self.assertEqual(out[0].members[0], "a")      # the split comment heads its first replies

    def test_a_branch_that_alone_is_too_big_is_split_inside_it(self):
        r = Rows()
        r.add("a")
        b = r.add("b", "a")
        for k in range(3):
            c = r.add(f"b{k}", b)
            for j in range(11):
                r.add(f"b{k}_{j}", c)
        out = chunks(r, soft_comments=15, max_comments=25)
        self.assertTrue(all(len(c) <= 25 for c in out))
        self.assertEqual(sum(len(c) for c in out), 38)
        self.assertEqual(out[0].members[:2], ["a", "b"])
        for c in out:
            for k in range(3):
                n = sum(m.startswith(f"b{k}") for m in c.members)
                self.assertIn(n, (0, 12))

    def test_split_comment_is_carried_to_the_chunk_with_its_replies(self):
        r = Rows()
        for g in "pq":
            group(r, g, 6)
        r.add("big")
        for k in range(3):
            b = r.add(f"big{k}", "big")
            for j in range(9):
                r.add(f"big{k}_{j}", b)
        out = chunks(r, soft_comments=15, max_comments=25)
        holder = next(c for c in out if "big" in c.members)
        self.assertEqual(holder.members[0], "big")
        self.assertIn("big0", holder.members)

    def test_orphan_reply_starts_its_own_group(self):
        r = Rows()
        r.add("a")
        r.add("orph", "t1_missing")
        out = chunks(r)
        self.assertEqual(out[0].members, ["a", "orph"])
        user, ids, ctx = T.render(out[0], "T", "", r.rows)
        self.assertIn("(reply to a comment not shown)", user)
        self.assertEqual(ctx, [])

    def test_cycle_in_parent_ids_loses_nothing(self):
        r = Rows()
        r.add("a", "b")
        r.add("b", "a")
        r.add("c")
        out = chunks(r)
        self.assertEqual(sorted(m for c in out for m in c.members), ["a", "b", "c"])
        user, ids, _ = T.render(out[0], "T", "", r.rows)
        self.assertEqual(sorted(ids.values()), ["a", "b", "c"])


class Items(unittest.TestCase):
    def test_done_and_deleted_comments_are_never_items_and_quoted_only_above_a_due_reply(self):
        r = Rows()
        r.add("a", body="Golden Lotus rocks")
        r.add("a1", "a", body="agreed")
        r.add("d", body="[deleted]")
        r.add("d1", "d", body="what did they say")
        r.add("e", body="[removed]")                 # nothing due under it: not drawn at all
        r.add("done", body="already extracted")      # done, nothing due under it
        due = {"a1", "d1"}
        out = chunks(r, due=due)
        self.assertEqual([c.members for c in out], [["a1", "d1"]])
        user, ids, ctx = T.render(out[0], "T", "", r.rows)
        self.assertEqual(ctx, ["a", "d"])
        self.assertIn(prompt_v6.thread.CONTEXT_HEADER, user)
        self.assertIn('u/ua: "Golden Lotus rocks"', user)
        self.assertIn("(a deleted comment)", user)
        self.assertIn("(reply to a deleted comment)", user)
        self.assertNotIn("removed", user)
        self.assertNotIn("already extracted", user)
        self.assertEqual(sorted(ids.values()), ["a1", "d1"])

    def test_full_ancestor_chain_is_quoted_twenty_deep_at_full_text(self):
        r = Rows()
        prev = None
        for d in range(21):
            prev = r.add(f"c{d}", prev, body=f"level {d} " + "y" * 1600)
        due = {"c20"}
        out = chunks(r, due=due)
        user, ids, ctx = T.render(out[0], "T", "", r.rows)
        self.assertEqual(ctx, [f"c{d}" for d in range(20)])
        block = user.split(prompt_v6.thread.CONTEXT_HEADER)[1].split("\n\n")[0]
        lines = [x for x in block.split("\n") if x.strip()]
        self.assertEqual(len(lines), 20)
        self.assertTrue(lines[0].startswith('u/uc0: "level 0 '))
        self.assertTrue(all(len(x.strip()) > 1500 for x in lines))     # 1,500 characters, not a stub
        self.assertTrue(all(x.strip().endswith(' ..."') for x in lines))
        self.assertEqual(ids, {1: "c20"})

    def test_chain_stops_at_a_member_of_the_chunk(self):
        r = Rows()
        r.add("a")
        r.add("b", "a")
        r.add("c", "b")
        r.add("d", "c", body="[deleted]")
        r.add("e", "d")
        out = chunks(r, due={"a", "c", "e"})
        user, ids, ctx = T.render(out[0], "T", "", r.rows)
        self.assertEqual(ctx, ["b", "d"])
        self.assertEqual(sorted(ids.values()), ["a", "c", "e"])
        # A quoted comment between two numbered ones says which it answers.
        self.assertIn('  u/ub (reply to [1]): "words from b"', user)
        self.assertIn("      (a deleted comment, reply to [2])", user)
        self.assertIn('[2] u/uc (reply to u/ub, not in this chunk: "words from b"): words from c', user)
        self.assertIn("[3] u/ue (reply to a deleted comment): words from e", user)

    def test_whole_groups_need_no_context(self):
        r = Rows()
        group(r, "a", 5)
        user, _, ctx = T.render(chunks(r)[0], "Title", "Body", r.rows)
        self.assertEqual(ctx, [])
        self.assertNotIn(prompt_v6.thread.CONTEXT_HEADER, user)

    def test_post_is_item_zero_of_the_first_chunk_only(self):
        r = Rows()
        for g in "abcdefghij":
            group(r, g, 3)
        out = chunks(r, post_due=True, post_tokens=10)
        self.assertTrue(out[0].post_item)
        self.assertFalse(any(c.post_item for c in out[1:]))
        # The post counts against the soft budget: 1 + 4 groups of 3, where a
        # chunk of comments alone takes 5 groups.
        self.assertEqual([len(c) for c in out], [13, 15, 3])
        u0, ids0, _ = T.render(out[0], "Best noodles?", "body " * 300, r.rows)
        self.assertTrue(u0.startswith("[0] POST: Best noodles?\n"))
        self.assertEqual(ids0[0], TID)
        self.assertGreater(len(u0.split("\n")[1]), 800)  # post mode's 4,000 cut, not the 800 of context
        u1, ids1, _ = T.render(out[1], "Best noodles?", "body " * 300, r.rows)
        self.assertTrue(u1.startswith("POST: Best noodles?\n"))
        self.assertNotIn(0, ids1)
        self.assertLessEqual(len(u1.split("\n")[1]), 805)

    def test_post_alone_when_no_comment_is_due(self):
        r = Rows()
        r.add("a")
        out = chunks(r, due=set(), post_due=True)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].items, [TID])

    def test_post_not_due_is_context(self):
        r = Rows()
        r.add("a")
        out = chunks(r, post_due=False)
        self.assertFalse(out[0].post_item)
        self.assertTrue(T.render(out[0], "T", "b", r.rows)[0].startswith("POST: T"))

    def test_split_half_keeps_the_post_in_the_first_half(self):
        c = T.Chunk(TID, True, ["a", "b", "c", "d", "e"])
        h = T.split_half(c)
        self.assertEqual([x.items for x in h], [[TID, "a", "b"], ["c", "d", "e"]])
        self.assertTrue(h[0].post_item and not h[1].post_item)
        self.assertEqual([x.items for x in T.split_half(T.Chunk(TID, False, ["a"]))], [["a"]])
        self.assertEqual([x.items for x in T.split_half(T.Chunk(TID, True, []))], [[TID]])

    def test_render_numbers_match_the_map(self):
        r = Rows()
        group(r, "a", 7)
        user, ids, _ = T.render(chunks(r, post_due=True)[0], "T", "", r.rows)
        for n, cid in ids.items():
            if n:
                self.assertRegex(user, rf"\[{n}\] u/u{re.escape(cid)}[ :]")


def first_reply(tree, cid, due):
    """The first due comment of cid's first reply branch that holds one, or None."""
    for k in tree.kids[cid]:
        stack = [k]
        while stack:
            x = stack.pop()
            if x in due:
                return x
            stack.extend(reversed(tree.kids[x]))
    return None


def bushy(rng, n, fan=(1, 6), deep=0.5):
    """A random thread whose reply groups often run past 25 comments."""
    r = Rows()
    open_ = []
    for i in range(n):
        if not open_ or rng.random() < 0.08:
            parent = None
        else:
            parent = rng.choice(open_[-12:]) if rng.random() < deep else rng.choice(open_)
        cid = r.add(f"c{i}", parent, body="x " * rng.randint(1, 200))
        open_.append(cid)
    return r


class SplitParents(unittest.TestCase):
    def test_carried_parent_is_not_flushed_alone_when_its_first_branch_is_full(self):
        # The case the review found: a split comment carried to a new chunk,
        # whose first branch is exactly the hard max, used to go out alone.
        r = Rows()
        r.add("a")
        b = r.add("b", "a")                       # first branch: 25 comments
        for j in range(24):
            r.add(f"b{j}", b)
        c = r.add("c", "a")                       # second branch: 10
        for j in range(9):
            r.add(f"c{j}", c)
        out = chunks(r, soft_comments=15, max_comments=25)
        holder = next(ch for ch in out if "a" in ch.members)
        self.assertIn("b", holder.members)        # with its first reply
        self.assertTrue(all(len(ch) > 1 for ch in out), [len(ch) for ch in out])
        self.assertTrue(all(len(ch.members) <= 25 for ch in out))

    def test_split_parents_keep_their_first_reply_and_no_chunk_is_one_item(self):
        rng = random.Random(11)
        for trial in range(400):
            r = bushy(rng, rng.randint(30, 220))
            soft, hard = rng.choice([(12, 25), (15, 25), (5, 10), (25, 25)])
            due = set(r.ids())
            post = rng.random() < 0.5
            out = T.chunk_thread(TID, r.rows, due, post, 5.0, soft, 3000, hard)
            tree = T.Tree(r.rows)
            if max(tree.depth.values()) >= hard - 1:
                continue                          # a chain as long as the max must be cut somewhere
            where = {m: n for n, c in enumerate(out) for m in c.members}
            for m, n in where.items():
                sub = [x for x in T.Tree(r.rows).kids[m]]
                if not sub:
                    continue
                desc, stack = set(), list(sub)
                while stack:
                    x = stack.pop()
                    desc.add(x)
                    stack.extend(tree.kids[x])
                if all(where[d] == n for d in desc):
                    continue                      # not split
                fr = first_reply(tree, m, due)
                self.assertEqual(where[fr], n, (trial, m, fr))
            for n, c in enumerate(out):
                if len(c.members) == 1 and not c.post_item and len(out) > 1:
                    # Only when neither neighbour has room for it.
                    full = lambda k: not (0 <= k < len(out)) or len(out[k].members) >= hard  # noqa: E731
                    self.assertTrue(full(n - 1) and full(n + 1), (trial, n, [len(x) for x in out]))
            self.assertEqual(sorted(where), sorted(due), trial)
            self.assertTrue(all(len(c.members) <= hard for c in out), trial)


class Properties(unittest.TestCase):
    def test_random_trees(self):
        rng = random.Random(7)
        for trial in range(300):
            r = Rows()
            n = rng.randint(1, 160)
            for i in range(n):
                parent = None if i == 0 or rng.random() < 0.15 else r.ids()[rng.randrange(len(r.ids()))]
                if rng.random() < 0.03:
                    parent = "t1_gone"
                body = rng.choice(["[deleted]", "x " * rng.randint(1, 900), "ok", ""])
                r.add(f"c{i}", parent, body=body)
            due = {c for c in r.ids() if rng.random() < 0.85 and not T.is_gone(
                next(x["body"] for x in r.rows if x["comment_id"] == c))}
            soft, hard = rng.choice([(12, 25), (15, 25), (5, 10)])
            post = rng.random() < 0.5
            out = T.chunk_thread(TID, r.rows, due, post, 5.0, soft, 3000, hard)
            got = [m for c in out for m in c.members]
            self.assertEqual(sorted(got), sorted(due), trial)
            self.assertEqual(len(got), len(set(got)), trial)
            self.assertTrue(all(len(c.members) <= hard for c in out), trial)
            self.assertEqual(sum(c.post_item for c in out), int(post), trial)
            tree = T.Tree(r.rows)
            for c in out:
                user, ids, ctx = T.render(c, "T", "", r.rows, tree)
                self.assertEqual(sorted(ids.values()), sorted(c.items), trial)
                self.assertFalse(set(ctx) & set(c.members), trial)
                # Every member's parent is a member, quoted, missing, or absent.
                for m in c.members:
                    p = tree.parent(m)
                    self.assertTrue(p is None or p in c.members or p in ctx, (trial, m))


if __name__ == "__main__":
    unittest.main()
