"""FROZEN: round 3 of v6, as benchmarked on Haiku 5.5 (eval/bench_v6, step m) and reviewed by
Opus (eval/review_v6). Do not edit: the run files are keyed by this prompt's hash (comment
6b046d8ed65d, thread 1b87239a557f, post 1b0a9d4098e3). Its schema is v6r3_schema.json, the
schema of rounds 1 to 3. The live prompt is the v6_* file of the same name.

v6, comment mode: one Reddit comment in, its restaurant opinions out.

Inputs are production's own comment-mode rendering (title, first 400 chars of
the post, the parent comment, the comment); only the system prompt and the
output schema change. Plugs into eval/run.py as --prompt file:eval/prompts/v6_comment.py.
"""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "v6r3_common", os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6r3_common.py"))
_c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_c)

SYSTEM_PROMPT = f"""You extract restaurant opinions from ONE Reddit comment in a New York City food subreddit. {_c.PURPOSE}

You get the post title, usually the post body, sometimes the parent comment (together, the context), then the COMMENT. Extract from the COMMENT only. A place named only in the context counts when the comment says anything about it, a question included: a reply that judges a place without naming it ("v mid", "the line is brutal", "hard disagree") is a mention of the place it replies about. Most negative opinions are in these replies.

Output only JSON, {{"mentions": [...]}}, one object per place, every field present. {{"mentions": []}} when the comment refers to no place.

{_c.SCOPE}

FIELDS
{_c.FIELDS}

{_c.SCALE}

{_c.RULES}

EXAMPLE (invented place)
Parent comment: Golden Lotus has the best hand-pulled noodles in Queens
Comment: lol no. noodles were gummy and $24 a bowl is a joke. go early if you do go, line by noon
{_c.EXAMPLE_JSON}"""

# Post mode: the original post (title + body) is the text to extract from, written
# by the poster. Same fields, same rules; only the framing changes.
POST_LIMIT = 4000

SYSTEM_PROMPT_POST = f"""You extract restaurant opinions from the ORIGINAL POST of a Reddit thread in a New York City food subreddit: its title and body, written by the poster. {_c.PURPOSE}

Extract from the post itself: the places it names, and what the poster says about them, their own visits and verdicts included. A place the post only asks about ("is X worth it?") is a mention with opinion "none". named_in is always "comment" here.

Output only JSON, {{"mentions": [...]}}, one object per place, every field present. {{"mentions": []}} when the post names no place.

{_c.SCOPE}

FIELDS
{_c.FIELDS}

{_c.SCALE}

{_c.RULES}

EXAMPLE (invented place; the same fields apply to a post)
Parent comment: Golden Lotus has the best hand-pulled noodles in Queens
Comment: lol no. noodles were gummy and $24 a bowl is a joke. go early if you do go, line by noon
{_c.EXAMPLE_JSON}"""


def build_post_message(title, selftext):
    """The user message for post mode: the post's title and body, the body cut at POST_LIMIT."""
    body = (selftext or "").strip()
    if len(body) > POST_LIMIT:
        body = body[:POST_LIMIT].rstrip() + " ..."
    parts = ["POST TITLE: " + (title or "").strip()]
    if body:
        parts.append("POST BODY: " + body)
    return "\n\n".join(parts)


SCHEMA = _c.SCHEMA_COMMENT
RESPONSE_FORMAT = _c.response_format(SCHEMA)
ANTHROPIC_OUTPUT_FORMAT = _c.anthropic_output_format(SCHEMA)
PROMPT_HASH = _c.prompt_hash(SYSTEM_PROMPT)
PROMPT_HASH_POST = _c.prompt_hash(SYSTEM_PROMPT_POST)
