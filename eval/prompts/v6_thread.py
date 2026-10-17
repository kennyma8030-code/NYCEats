"""v6, thread mode: one post plus a chunk of its comment tree in, opinions out.

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


def render_chunk(title, selftext, rows, outside=None):
    """Render one chunk. Returns (message, {bracket number: comment_id}).

    rows: dicts with comment_id, parent_comment_id, author, body, in
      production's chunk order.
    outside: {parent_comment_id: {"author", "body"} or None} for parents not
      in the chunk. None, or a missing key, means the parent is not in the
      database; "[deleted]" / "[removed]" bodies are said to be deleted.
    """
    outside = outside or {}
    ordered = depth_first(rows)
    num = {r["comment_id"]: n for n, (r, _) in enumerate(ordered, start=1)}
    parts = [f"POST: {_flat(title)}"]
    body = _flat(selftext)
    if body:
        parts.append(_cut(body, SELFTEXT_LIMIT))
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
    return "\n".join(parts), {n: cid for cid, n in num.items()}


SYSTEM_PROMPT = f"""You extract restaurant opinions from a Reddit thread in a New York City food subreddit. {_c.PURPOSE}

You get the post, then a chunk of its comments. Each comment starts with a number in brackets. Extract from the comments only; the post, and the comment a reply answers, are its context. Every mention carries "id", the bracket number of the comment it came from. Never use a number that is not in brackets. Go through EVERY comment, one-word replies included: they are easy to skip and often hold the only complaint.

Output only JSON, {{"mentions": [...]}}, one object per place per comment, every field present.

READING THE COMMENTS
Each reply follows the comment it answers and says which one: "(reply to [3])". Trust that marker over position or indentation.
A reply to a comment outside this chunk quotes it: (reply to u/zed, not in this chunk: "..."). The quote is context only; never extract from it, but a reply that judges the quoted place is a mention of that place.
A reply is about the place in the comment it answers unless it names another, and the mention takes the REPLY's id: "overrated" under a rec is a negative mention of that place; "hard disagree" under "X is overrated" is positive for X. If the place still cannot be told (a reply to a deleted comment), skip it rather than guess.
Read the comments once, in order. A comment's own words and the comment it answers are all you need; most comments name no place and need no deliberation.

{_c.SCOPE}

FIELDS
id          The bracket number of the comment.
{_c.FIELDS}

{_c.SCALE}

{_c.RULES}

EXAMPLE (invented places)
POST: Best noodles in Queens?

[1] u/ann: Golden Lotus, and Pepper House if you can stand the line
  [2] u/bob (reply to [1]): pepper house is overrated and $28 for noodles is a joke
    [3] u/ann (reply to [2]): hard disagree, the cumin lamb is worth it
  [4] u/eve (reply to [1]): golden lotus was mid last time
[5] u/cal (reply to u/zed, not in this chunk: "Noodle Lab for hand-pulled, skip the dumplings"): it's fine. not worth the trip
[6] u/dee: is Noodle Lab still cash only?

1: Golden Lotus endorse (overall positive). Pepper House stated: overall positive, wait negative.
2: pepper house: overall negative, value negative, dish noodles (level null), notes {{"about":"overrated","text":"overrated","level":"negative","dish":null}} and {{"about":"price","text":"$28 for noodles","level":"negative","dish":"noodles"}}.
3: pepper house, named_in "context":
{{"id":3,"name":"pepper house","named_in":"context","location":null,"experience":"firsthand","opinion":"stated","overall":"positive","aspects":{{"taste":"positive","value":null,"service":null,"atmosphere":null,"wait":null}},"avoid":false,"dishes":[{{"dish":"cumin lamb","level":"positive","avoid":false}}],"price":null,"timeframe":"current","trend":null,"status":null,"tags":[],"notes":[]}}
4: golden lotus, named_in "context": overall and taste negative ("mid").
5: Noodle Lab, named_in "context" (from the quote): overall negative ("fine" is lukewarm, and "not worth the trip").
6: Noodle Lab: opinion none, experience none, every level null."""

SCHEMA = _c.SCHEMA_THREAD
RESPONSE_FORMAT = _c.response_format(SCHEMA)
ANTHROPIC_OUTPUT_FORMAT = _c.anthropic_output_format(SCHEMA)
PROMPT_HASH = _c.prompt_hash(SYSTEM_PROMPT)
