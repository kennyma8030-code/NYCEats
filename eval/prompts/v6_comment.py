"""v6 round 4, comment mode: one Reddit comment in, its restaurant opinions out.

Plugs into eval/run.py as --prompt file:eval/prompts/v6_comment.py. Round 4
renders its own input, build_user_message, from raw rows (eval/build_comment_rows.py
writes them next to each items file as <items>.comment_rows.jsonl; run.py
re-renders every comment call with them because COMMENT_ROWS is set).

Production's rendering (prompt.build_user_message) is four plain sections: the
title, the first 400 characters of the post, the immediate parent, the comment.
The round-3 review traced 40 failing items and 28 of 39 missed mentions to it
(eval/review_v6/analysis/input.md):
  * the place was named above the parent (13 of 20 in the grandparent, 6 three
    to five levels up) or past the 400-character cut. Now up to five ancestors,
    the parent at up to 1,500 characters and the others at 300, and the post
    body at 1,200;
  * 11 of those 20 referents were in the commenter's own earlier comment, and
    52 of the 542 items were by the post's author, which the model could not
    know. Ancestors are labelled "OP", "you, earlier" or "another user", and the
    post carries author="you" when the commenter wrote it;
  * context bled into the comment (8 of 25 false-positive mentions). Labelled
    XML sections and one rule (<input>) keep the comment apart from its context;
  * a deleted parent was silently dropped, so a reply to it looked top-level,
    and "> quote" lines from someone else read as the commenter's words. Both
    are marked now.
On the 600 benchmark comments the message grows from about 210 to about 340 tokens,
uncached; the system prompt grows more (about 5.7k tokens against 3.1k), but it is
cached.

Post mode (SYSTEM_PROMPT_POST, build_post_message) extracts the original post itself.
"""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "v6_common", os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6_common.py"))
_c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_c)

COMMENT_ROWS = True          # run.py: re-render comment calls from <items>.comment_rows.jsonl
POST_BODY_CHARS = 1200       # 34% of posts are past 400; the ask and its places often are too
PARENT_CHARS = 1500
ANCESTOR_CHARS = 300         # enough to carry the name a reply is about
MAX_ANCESTORS = 5
GONE = ("[deleted]", "[removed]")

SYSTEM_PROMPT = f"""You extract restaurant opinions from ONE Reddit comment in a New York City food subreddit. {_c.PURPOSE}

<input>
The message has labelled parts: <post_title> and <post_body> (author="you" when the commenter wrote the post), <thread_above> (the comments this one sits under, oldest first: "OP" is the post's author, "you, earlier" the commenter's own earlier comments), and <comment_to_extract>. Extract from <comment_to_extract> only; everything else is context. A <quote> inside the comment is someone else's words being answered.
A place named only in the context is a mention only when the comment refers to it: by name, as "it", "they" or "this place", or by replying to what was said about it ("v mid", "the line is brutal", "hard disagree"); then named_in is "context". Places the context names that the comment doesn't refer to are not its mentions, and a claim in the context is the commenter's only when they wrote it or agree with it. A comment that answers the post's general question, or talks about restaurants in general, doesn't mention the places the post names. When a nameless reply could mean two places, use the one its words fit; if neither fits, skip it.
</input>

One object per place; {{"mentions": []}} when the comment refers to no place.

{_c.SCOPE}

{_c.FIELDS}

{_c.SCALE}

{_c.RULES}

{_c.EXAMPLES}

{_c.CHECK}"""


# ---------------------------------------------------------------- input
def _flat(text):
    return " ".join((text or "").split())


def _cut(text, limit):
    return text if len(text) <= limit else text[:limit].rstrip() + " ..."


def _same(a, b):
    return bool(a) and a not in GONE and a == b


def _quotes(body):
    """Mark Reddit quote blocks ('> ...' lines) as someone else's words."""
    out, block = [], []
    for line in (body or "").strip().splitlines():
        if line.lstrip().startswith(">"):
            block.append(line.lstrip()[1:].strip())
            continue
        if block:
            out.append("<quote>" + " ".join(x for x in block if x) + "</quote>")
            block = []
        out.append(line)
    if block:
        out.append("<quote>" + " ".join(x for x in block if x) + "</quote>")
    return "\n".join(out).strip()


def build_user_message(rec):
    """The round-4 comment-mode input from one comment_rows record (eval/build_comment_rows.py)."""
    me, op = rec.get("author"), rec.get("thread_author")
    by = ' author="you"' if _same(me, op) else ""
    parts = [f'<post_title{by}>{_flat(rec.get("title"))}</post_title>']
    body = (rec.get("selftext") or "").strip()
    if body and body not in GONE:
        parts.append(f'<post_body{by}>{_cut(body, POST_BODY_CHARS)}</post_body>')
    anc = rec.get("ancestors") or []
    if anc:
        shown = anc[-MAX_ANCESTORS:]
        lines = []
        if rec.get("ancestors_total", len(anc)) > len(shown):
            lines.append(f"({rec['ancestors_total'] - len(shown)} earlier comments not shown)")
        for n, a in enumerate(shown, 1):
            if a.get("state") == "missing":
                lines.append(f"[{n}] (a comment that is not available)")
                continue
            who = "you, earlier" if _same(a.get("author"), me) else "OP" if _same(a.get("author"), op) \
                else "another user"
            if a.get("state") == "deleted":
                lines.append(f"[{n}] (a deleted comment)")
                continue
            limit = PARENT_CHARS if n == len(shown) else ANCESTOR_CHARS
            lines.append(f"[{n}] {who}: {_cut(_flat(a.get('body')), limit)}")
        parts.append("<thread_above>\n" + "\n".join(lines) + "\n</thread_above>")
    parts.append("<comment_to_extract>\n" + _quotes(rec.get("body")) + "\n</comment_to_extract>")
    return "\n".join(parts)


# ---------------------------------------------------------------- post mode
# The original post (title + body) is the text to extract from, written by the poster.
POST_LIMIT = 4000

SYSTEM_PROMPT_POST = f"""You extract restaurant opinions from the ORIGINAL POST of a Reddit thread in a New York City food subreddit: its title and body, written by the poster. {_c.PURPOSE}

<input>
The message is <post_title> and <post_body>. Extract the places the post names and what the poster says about them, their own visits and verdicts included. A place the post only asks about ("is X worth it?") is a mention with opinion "none". named_in is always "comment" here.
</input>

One object per place; {{"mentions": []}} when the post names no place.

{_c.SCOPE}

{_c.FIELDS}

{_c.SCALE}

{_c.RULES}

{_c.EXAMPLES}

{_c.CHECK}"""


def build_post_message(title, selftext):
    """The user message for post mode: the post's title and body, the body cut at POST_LIMIT."""
    body = (selftext or "").strip()
    parts = [f"<post_title>{_flat(title)}</post_title>"]
    if body and body not in GONE:
        parts.append(f"<post_body>{_cut(body, POST_LIMIT)}</post_body>")
    return "\n".join(parts)


SCHEMA = _c.SCHEMA_COMMENT
RESPONSE_FORMAT = _c.response_format(SCHEMA)
ANTHROPIC_OUTPUT_FORMAT = _c.anthropic_output_format(SCHEMA)
PROMPT_HASH = _c.prompt_hash(SYSTEM_PROMPT)
PROMPT_HASH_POST = _c.prompt_hash(SYSTEM_PROMPT_POST)
