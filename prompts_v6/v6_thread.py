"""v6 round 4, thread mode: one post plus a chunk of its comment tree in, opinions out.

The fields, levels, rules, examples and checklist are v6_common's (round 4); only the
input section and the thread example are thread mode's own.

Plugs into eval/run.py as --prompt file:eval/prompts/v6_thread.py. Unlike
the comment prompt, this one brings its own renderer, render_chunk, because
production's renderer is where most of thread mode's errors start
(eval/v4/README.md):

  * replies are ordered by time within a root, so when two replies answer one
    comment the later one is drawn under its sibling. That is 9.75% of
    replies, and the model files their opinions against the wrong place;
  * 11.5% of replies have their parent in another chunk, and 17,202 replies
    answer a parent that is never rendered at all, because it is 15
    characters or shorter. Those are mostly bare names like "Keens", the very
    comment a nameless "overrated" reply is about;
  * comments are cut at 700 characters, which drops 4.9% of comment text,
    mostly the tail of long lists of places.

render_chunk keeps production's chunk membership (the same 25 comments, so
results stay comparable), and changes how the chunk is drawn:

  * depth-first order within the chunk, so each reply follows its parent;
  * every reply names its parent explicitly, "(reply to [3])", and the
    prompt tells the model to trust that over position. Attribution becomes
    a lookup instead of a reconstruction, which is also meant to cut the
    reasoning thread mode spends (about 6.7k tokens a chunk on Haiku 5.5);
  * a parent outside the chunk is quoted in one line, with its author;
  * comments are cut at 1,500 characters and the post body at 800.

eval/build_thread_rows.py fetches the raw rows this needs (read-only), and
eval/run.py re-renders every thread chunk with render_chunk when the prompt
module defines it.

Production (prompts_v6/v6_thread.py) is this file plus two additions, each
marked "production addition" below and listed in tests/v6_thread_additions.py:
  * the post can be an item, "[0] POST: ...", extracted under post mode's
    rules (<post_item> in the prompt, which therefore has its own hash);
  * a chunk whose comments hang under comments outside it quotes their whole
    ancestor chains above its comments, as context lines with no number.
"""
import collections
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "v6_common", os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6_common.py"))
_c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_c)

SELFTEXT_LIMIT = 800       # once per chunk, so cheap; the ask is often past 400
MAX_COMMENT_CHARS = 1500   # 0.4% of comments are longer; 700 cut 1.7%
STUB_CHARS = 140           # enough to carry the name a reply is about
MAX_INDENT = 6             # indentation is a reading aid now; the marker carries the parent
# production addition: the post as item [0] gets post mode's body cut, and a
# quoted ancestor the full comment cut, because both are read for what they say.
POST_ITEM_CHARS = 4000
CONTEXT_CHARS = MAX_COMMENT_CHARS
CONTEXT_HEADER = "Earlier comments in this thread, quoted as context (not in this chunk; never extract from them):"


def _flat(text):
    return " ".join((text or "").split())


def _cut(text, limit):
    return text if len(text) <= limit else text[:limit].rstrip() + " ..."


def depth_first(rows):
    """Rows in production order -> [(row, depth within the chunk)], parents first.

    Siblings keep production's order, which is posting time. A row whose parent
    is not in the chunk starts a new subtree where it first appeared.
    """
    present = {r["comment_id"] for r in rows}
    kids, roots = collections.defaultdict(list), []
    for r in rows:
        p = r.get("parent_comment_id")
        (kids[p] if p in present and p != r["comment_id"] else roots).append(r)
    out = []

    def walk(r, d):
        out.append((r, d))
        for k in kids[r["comment_id"]]:
            walk(k, d + 1)

    for r in roots:
        walk(r, 0)
    return out


def render_chunk(title, selftext, rows, outside=None, above=None, post_item=None):
    """Render one chunk. Returns (message, {bracket number: comment_id}).

    rows: dicts with comment_id, parent_comment_id, author, body, in
      production's chunk order.
    outside: {parent_comment_id: {"author", "body"} or None} for parents not
      in the chunk. None, or a missing key, means the parent is not in the
      database; "[deleted]" / "[removed]" bodies are said to be deleted.
    above (production addition): context lines quoted between the post and
      the comments, [(depth, author, body, parent)] in thread order, body
      None for a deleted comment, parent what it answers ("[3]", "u/zed",
      "a deleted comment") or None for a top-level one. Unnumbered, so no
      mention can name them.
    post_item (production addition): the thread id when the post is an item
      to extract. It is numbered [0], its body is cut at POST_ITEM_CHARS, and
      the map gets {0: post_item}.
    """
    outside = outside or {}
    ordered = depth_first(rows)
    num = {r["comment_id"]: n for n, (r, _) in enumerate(ordered, start=1)}
    parts = [f"{'[0] ' if post_item else ''}POST: {_flat(title)}"]
    body = _flat(selftext)
    if body:
        parts.append(_cut(body, POST_ITEM_CHARS if post_item else SELFTEXT_LIMIT))
    parts.append("")
    if above:
        parts.append(CONTEXT_HEADER)
        for depth, author, text, parent in above:
            to = f" (reply to {parent})" if parent else ""
            line = (f"u/{author or '?'}{to}: \"{_cut(_flat(text), CONTEXT_CHARS)}\"" if text is not None
                    else f"(a deleted comment{', reply to ' + parent if parent else ''})")
            parts.append(f"{'  ' * min(depth, MAX_INDENT)}{line}")
        parts.append("")
    for r, depth in ordered:
        p = r.get("parent_comment_id")
        if not p:
            head = ""
        elif p in num:
            head = f" (reply to [{num[p]}])"
        else:
            o = outside.get(p)
            text = _flat((o or {}).get("body"))
            if not o:
                head = " (reply to a comment not shown)"
            elif text in ("", "[deleted]", "[removed]"):
                head = " (reply to a deleted comment)"
            else:
                head = (f" (reply to u/{o.get('author') or '?'}, not in this chunk: "
                        f"\"{_cut(text, STUB_CHARS)}\")")
        parts.append(f"{'  ' * min(depth, MAX_INDENT)}[{num[r['comment_id']]}] "
                     f"u/{r.get('author') or '?'}{head}: {_cut(_flat(r.get('body')), MAX_COMMENT_CHARS)}")
    ids = {n: cid for cid, n in num.items()}
    if post_item:
        ids[0] = post_item
    return "\n".join(parts), ids


SYSTEM_PROMPT = f"""You extract restaurant opinions from a Reddit thread in a New York City food subreddit. {_c.PURPOSE}

<input>
You get the post, then a chunk of its comments, each starting with a number in brackets. Extract from the comments only; the post, and the comment a reply answers, are its context. Every mention carries "id", the bracket number of the comment it came from; never use a number that is not in brackets. Go through EVERY comment, one-word replies included: they are easy to skip and often hold the only complaint.
Each reply follows the comment it answers and says which one: "(reply to [3])". Trust that marker over position or indentation. A reply to a comment outside this chunk quotes it: (reply to u/zed, not in this chunk: "..."). The quote is context only; never extract from it, but a reply that judges the quoted place is a mention of that place.
A reply is about the place in the comment it answers unless it names another, and the mention takes the REPLY's id, with named_in "context": "overrated" under a rec is a knock on that place; "hard disagree" under "X is overrated" is praise for X. Each comment's levels come only from what that comment says, plus a claim it agrees with ("+1", "exactly"); a commenter's earlier comment is counted on its own, with its own id. If the place still cannot be told (a reply to a deleted comment), skip it rather than guess. Most comments name no place and need no deliberation.
</input>

<post_item>
When the post itself is numbered, "[0] POST: ...", it is an item too: extract its title and body, written by the poster, and its mentions carry "id" 0. Extract the places the post names and what the poster says about them, their own visits and verdicts included. A place the post only asks about ("is X worth it?") is a mention with opinion "none". named_in is always "comment" for item 0. A post with no number is context only.
</post_item>

One object per place per comment.

{_c.SCOPE}

{_c.FIELDS.replace("<fields>", "<fields>" + chr(10) + "id          The bracket number of the comment.", 1)}

{_c.SCALE}

{_c.RULES}

{_c.EXAMPLES}

<thread_example>
POST: Best noodles in Queens?

[1] u/ann: Golden Lotus, and Pepper House if you can stand the line
  [2] u/bob (reply to [1]): pepper house is overrated and $28 for noodles is a joke
    [3] u/ann (reply to [2]): hard disagree, the cumin lamb is worth it
  [4] u/eve (reply to [1]): golden lotus was mid last time
[5] u/cal (reply to u/zed, not in this chunk: "Noodle Lab for knife-cut, skip the dumplings"): meh, wouldn't cross town for it
[6] u/dee: is Noodle Lab still cash only?

1: Golden Lotus endorse, overall praise, dish noodles praise and taste praise (a bare answer takes the dish the question asks about). Pepper House stated: dish noodles praise, taste praise, wait knock, overall praise (a pick; the wait never lowers overall).
2: pepper house: overall knock ("overrated"), value knock, dish noodles (level null), note "$28 for noodles".
3: pepper house (named_in "context"): stated, overall praise, taste praise, dish cumin lamb praise.
4: golden lotus (named_in "context"): overall and taste knock ("mid").
5: Noodle Lab (named_in "context", from the quote): overall knock ("meh" is lukewarm, and they wouldn't make the trip).
6: Noodle Lab: opinion none, experience none, every level null.
</thread_example>

{_c.CHECK}"""

SCHEMA = _c.SCHEMA_THREAD
RESPONSE_FORMAT = _c.response_format(SCHEMA)
ANTHROPIC_OUTPUT_FORMAT = _c.anthropic_output_format(SCHEMA)
PROMPT_HASH = _c.prompt_hash(SYSTEM_PROMPT)
