"""FROZEN: round 1 of v6, as benchmarked on Haiku 5.5 (eval/bench_v6, steps a-j). Do not edit:
the run files are keyed by this prompt's hash (comment a15cfb978cce, thread 44e1a49c7781).
The live prompt is the v6_* file of the same name.

v6, comment mode: one Reddit comment in, its restaurant opinions out.

Inputs are production's own comment-mode rendering (title, first 400 chars of
the post, the parent comment, the comment); only the system prompt and the
output schema change. Plugs into eval/run.py as --prompt file:eval/prompts/v6_comment.py.
"""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "v6r1_common", os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6r1_common.py"))
_c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_c)

SYSTEM_PROMPT = f"""You extract restaurant opinions from ONE Reddit comment in a New York City food subreddit. {_c.PURPOSE}

You get the post title, usually the post body, sometimes the parent comment (together, the context), then the COMMENT. Extract from the COMMENT only. A place named only in the context counts when the comment says something about it: a reply that judges a place without naming it ("v mid", "the line is brutal", "hard disagree") is a mention of the place it replies about. Most negative opinions are in these replies.

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

SCHEMA = _c.SCHEMA_COMMENT
RESPONSE_FORMAT = _c.response_format(SCHEMA)
ANTHROPIC_OUTPUT_FORMAT = _c.anthropic_output_format(SCHEMA)
PROMPT_HASH = _c.prompt_hash(SYSTEM_PROMPT)
