"""Thread mode's chunker: how one thread's due items are cut into requests, and how each is drawn.

Pure functions over rows already read, no database and no network, so
extract_v6.py (production) and eval/thread_v6 (the offline head-to-head)
import the same code and cannot drift apart.

The rules, as decided with the owner:

  * A group is a top-level comment and every reply under it, in depth-first
    order, siblings by posting time. A reply whose parent is not in the
    database starts a group of its own.
  * Whole groups are packed into a chunk until a soft budget is reached
    (soft_comments items or soft_tokens of comment text, whichever comes
    first). One group may stay whole past the budget up to max_comments; only
    a group bigger than that is split, depth-first, and only between branches
    (where one reply branch ends and its next sibling begins), going down into
    a branch that alone is too big. A comment whose branches were split always
    shares a chunk with the start of its first reply branch: the packer
    carries it forward, and that branch's first piece is cut small enough to
    leave room for it (only a chain of split comments as long as the hard max
    cannot all travel together). A one-comment chunk in a thread that has
    others joins its neighbour when the hard max allows.
  * Only due items are counted and numbered. A comment already extracted
    under v6, or [deleted]/[removed]/blank, is never an item; it is drawn
    only as context, when a due reply hangs under it.
  * Every chunk starts with the post. In a thread's first chunk the post is
    item [0] when it is still due (its body then cut at post mode's 4,000
    characters); everywhere else it is context (cut at 800).
  * A chunk whose comments hang under comments outside it quotes each such
    comment's whole ancestor chain, from the top-level comment down to the
    direct parent, at full text (cut at 1,500), above its comments. Quoted
    lines carry no number, so the model cannot attribute a mention to them,
    and they are never billed as items. Depth is not capped: measured reply
    chains go 20 deep.

Drawing is prompts_v6/v6_thread.render_chunk, the benchmark's renderer with
the two production additions (the post as [0], the quoted chains).

Token counts here are estimates for packing only, at TEXT_CHARS_PER_TOKEN
characters a token for English comment text.
"""

import prompt_v6

SOFT_COMMENTS = 15
SOFT_TOKENS = 3000
MAX_COMMENTS = 25
TEXT_CHARS_PER_TOKEN = 4.0
GONE = ("", "[deleted]", "[removed]")

R = prompt_v6.thread       # the vendored renderer module


def is_gone(body):
    return (body or "").strip() in GONE


def text_tokens(body, limit=None):
    """Estimated tokens of a comment as the renderer draws it (flattened, cut)."""
    return len(R._cut(R._flat(body), limit or R.MAX_COMMENT_CHARS)) / TEXT_CHARS_PER_TOKEN


class Chunk:
    """One request's items: the post (when it is item [0]) and due comment ids, in thread order."""
    __slots__ = ("thread_id", "post_item", "members")

    def __init__(self, thread_id, post_item, members):
        self.thread_id, self.post_item, self.members = thread_id, bool(post_item), list(members)

    @property
    def items(self):
        """Item ids, post first: what extraction_state rows this chunk settles."""
        return ([self.thread_id] if self.post_item else []) + self.members

    def __len__(self):
        return len(self.members) + self.post_item

    def __repr__(self):
        return f"Chunk({self.thread_id}, post={self.post_item}, {self.members})"


class Tree:
    """A thread's comments as a tree: rows by id, children in posting order, roots in posting order."""

    def __init__(self, comments):
        self.rows = {c["comment_id"]: c for c in comments}
        order = sorted(self.rows.values(), key=lambda c: (str(c.get("created_utc") or ""), c["comment_id"]))
        raw_kids = {cid: [] for cid in self.rows}
        self.roots = []
        for c in order:
            p = c.get("parent_comment_id")
            if p and p in self.rows and p != c["comment_id"]:
                raw_kids[p].append(c["comment_id"])
            else:
                self.roots.append(c["comment_id"])
        # The walk fixes each comment's depth-first position, depth and tree
        # parent. A corrupt cycle in parent ids is unreachable from any root;
        # its first comment becomes a root of its own, so none is ever lost
        # and nothing below loops.
        self.pos, self.depth, self.up = {}, {}, {}
        self.kids = {cid: [] for cid in self.rows}
        for r in list(self.roots):
            self._walk(r, raw_kids)
        for c in order:
            if c["comment_id"] not in self.pos:
                self.roots.append(c["comment_id"])
                self._walk(c["comment_id"], raw_kids)

    def _walk(self, root, raw_kids):
        stack = [(root, 0, None)]
        while stack:
            cid, d, up = stack.pop()
            if cid in self.pos:
                continue
            self.pos[cid] = len(self.pos)
            self.depth[cid] = d
            self.up[cid] = up
            if up is not None:
                self.kids[up].append(cid)
            stack.extend((k, d + 1, cid) for k in reversed(raw_kids[cid]))

    def parent(self, cid):
        """The parent in the tree, or None for a top-level comment (or one whose parent is missing)."""
        return self.up.get(cid)

    def drawn_parent(self, cid):
        """The parent the renderer is told about: the tree parent, else the
        missing one's id (drawn as "a comment not shown"), else None."""
        if self.up.get(cid):
            return self.up[cid]
        p = self.rows[cid].get("parent_comment_id")
        return p if p and p not in self.rows else None


class _Atom:
    """A run of due comments that is never cut: a whole subtree, or one comment whose subtree was split."""
    __slots__ = ("ids", "tokens", "sticky")

    def __init__(self, ids, tokens, sticky=False):
        self.ids, self.tokens, self.sticky = ids, tokens, sticky


def chunk_thread(thread_id, comments, due, post_due=False, post_tokens=0.0, soft_comments=SOFT_COMMENTS,
                 soft_tokens=SOFT_TOKENS, max_comments=MAX_COMMENTS):
    """The thread's chunks, in thread order. Every due comment is in exactly one.

    comments: every comment row of the thread (dicts with comment_id,
      parent_comment_id, author, body, created_utc), due or not, so the tree
      and its context are whole.
    due: ids of the comments to extract. post_due: the post is to be
      extracted too, as item [0] of the first chunk; post_tokens is its text's
      estimated size, which counts against the first chunk's soft budget.
    """
    tree = Tree(comments)
    due = set(due) & set(tree.rows)
    size, toks = {}, {}

    def measure(cid):
        # Iterative post-order, so a 20-deep chain needs no recursion limit.
        stack, seen = [cid], []
        while stack:
            x = stack.pop()
            seen.append(x)
            stack.extend(tree.kids[x])
        for x in reversed(seen):
            mine = x in due
            size[x] = mine + sum(size[k] for k in tree.kids[x])
            toks[x] = (text_tokens(tree.rows[x].get("body")) if mine else 0.0) + sum(toks[k] for k in tree.kids[x])

    def subtree_ids(cid):
        out, stack = [], [cid]
        while stack:
            x = stack.pop()
            if x in due:
                out.append(x)
            stack.extend(reversed(tree.kids[x]))
        return out

    def atoms(cid, reserve=0):
        """cid's subtree as atoms. `reserve` is how many split comments above
        it travel with its first atom (each must share a chunk with its first
        reply branch), so that atom must leave room for them under the hard
        max; a subtree too big for that is split further. A chain of split
        comments as long as the hard max cannot all travel together, and
        there the reserve starts again from nothing."""
        if size[cid] == 0:
            return []
        if size[cid] <= max_comments - reserve:
            return [_Atom(subtree_ids(cid), toks[cid])]
        mine = cid in due
        out = [_Atom([cid], text_tokens(tree.rows[cid].get("body")), sticky=True)] if mine else []
        carried = reserve + mine
        first = next((k for k in tree.kids[cid] if size[k]), None)
        for k in tree.kids[cid]:
            out += atoms(k, (carried if carried < max_comments else 0) if k == first else 0)
        return out

    seq = []
    if post_due:
        seq.append(_Atom([], post_tokens, sticky=True))
    for r in tree.roots:
        measure(r)
        seq += atoms(r)

    def comments(atoms_):
        # The post is an item for the soft budget but not a comment for the hard max.
        return sum(len(a.ids) for a in atoms_)

    def items(atoms_):
        return sum(len(a.ids) or 1 for a in atoms_)

    groups, cur = [], []
    for a in seq:
        if cur:
            over_hard = comments(cur) + len(a.ids) > max_comments
            over_soft = (items(cur) + (len(a.ids) or 1) > soft_comments
                         or sum(x.tokens for x in cur) + a.tokens > soft_tokens)
            if over_hard or (over_soft and not all(x.sticky for x in cur)):
                # Split comments at the end of the chunk (a's ancestors, waiting
                # for their first replies) go on with a; atoms() left them room.
                k = len(cur)
                while k and cur[k - 1].sticky:
                    k -= 1
                if k and comments(cur[k:]) + len(a.ids) <= max_comments:
                    groups.append(cur[:k])
                    cur = cur[k:]
                else:
                    groups.append(cur)
                    cur = []
        cur.append(a)
    if cur:
        groups.append(cur)
    # A chunk of one comment, in a thread that has others, is one request for
    # one comment: it joins the chunk before it, or else the one after, when
    # the hard max allows. The soft budget gives way by that one comment.
    n = 0
    while n < len(groups):
        g = groups[n]
        if len(groups) > 1 and comments(g) == 1 and items(g) == 1:
            if n > 0 and comments(groups[n - 1]) + 1 <= max_comments:
                groups[n - 1] = groups[n - 1] + g
                del groups[n]
                continue
            if n + 1 < len(groups) and comments(groups[n + 1]) + 1 <= max_comments:
                groups[n + 1] = g + groups[n + 1]
                del groups[n]
                continue
        n += 1

    out = []
    for n, g in enumerate(groups):
        members = [i for a in g for i in a.ids]
        post = post_due and n == 0
        if members or post:
            out.append(Chunk(thread_id, post, members))
    return out


def split_half(chunk):
    """The two halves a failed chunk is retried as, in thread order; the post stays in the first."""
    items = chunk.items
    k = (len(items) + 1) // 2
    first, second = items[:k], items[k:]
    post = chunk.post_item

    def make(part, with_post):
        return Chunk(chunk.thread_id, with_post, [i for i in part if i != chunk.thread_id])
    return [c for c in (make(first, post), make(second, False)) if len(c)]


def context_of(members, tree):
    """Ids quoted above a chunk's comments, in thread order: for each member
    whose parent is not a member, the whole chain from that parent up to its
    top-level comment, stopping at a member (it is drawn anyway) or at an
    ancestor the database does not have."""
    inside = set(members)
    out = set()
    for m in members:
        p, seen = tree.parent(m), set()
        while p and p not in inside and p not in seen and p in tree.rows:
            seen.add(p)
            out.add(p)
            p = tree.parent(p)
    return sorted(out, key=lambda c: tree.pos.get(c, 0))


def render(chunk, title, selftext, comments, tree=None):
    """(user message, {bracket number: item id}, quoted context ids) for one chunk.

    The members are drawn by v6_thread.render_chunk, which numbers them in its
    own depth-first order; the map it returns is the one the answer's ids are
    read against.
    """
    tree = tree or Tree(comments)
    members = sorted(chunk.members, key=lambda c: tree.pos.get(c, 0))
    ctx = context_of(members, tree)
    rows = [{"comment_id": c, "parent_comment_id": tree.drawn_parent(c), "author": tree.rows[c].get("author"),
             "body": tree.rows[c].get("body")} for c in members]
    outside = {}
    for r in rows:
        p = r["parent_comment_id"]
        if p and p not in chunk.members:
            o = tree.rows.get(p)
            outside[p] = {"author": o.get("author"), "body": o.get("body")} if o else None
    # A quoted comment says what it answers, as numbered comments do: a
    # number when its parent is in the chunk (a done or deleted comment
    # between two numbered ones), else the quoted parent's author.
    num = {r["comment_id"]: n for n, (r, _) in enumerate(R.depth_first(rows), start=1)}

    def answers(c):
        p = tree.parent(c)
        if p is None:
            return None
        if p in num:
            return f"[{num[p]}]"
        return "a deleted comment" if is_gone(tree.rows[p].get("body")) else f"u/{tree.rows[p].get('author') or '?'}"
    above = [(tree.depth.get(c, 0), tree.rows[c].get("author"),
              None if is_gone(tree.rows[c].get("body")) else tree.rows[c].get("body"), answers(c)) for c in ctx]
    user, ids = R.render_chunk(title, selftext, rows, outside, above=above,
                               post_item=chunk.thread_id if chunk.post_item else None)
    return user, ids, ctx


def stats(chunks):
    """Counts for a dry run: chunks, items, and the distribution of items per chunk."""
    sizes = sorted(len(c) for c in chunks)
    if not sizes:
        return {"chunks": 0, "items": 0}
    q = lambda p: sizes[min(len(sizes) - 1, int(p * len(sizes)))]  # noqa: E731
    return {"chunks": len(sizes), "items": sum(sizes), "posts": sum(c.post_item for c in chunks),
            "min": sizes[0], "p50": q(0.5), "p90": q(0.9), "max": sizes[-1]}
