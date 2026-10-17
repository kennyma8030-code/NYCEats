"""v6, thread mode: one post plus a chunk of its comment tree in, opinions out.

Inputs are production's own thread-mode rendering (chunks of 25 comments with
bracket ids); only the system prompt and the output schema change. Plugs into
eval/run.py as --prompt file:eval/prompts/v6_thread.py.

The renderer orders replies by time within a root, so about 10% of replies are
drawn under the wrong parent, and 11.5% have their parent in another chunk
(eval/v4/README.md). This prompt does not fix that; it tells the model the
indentation can be wrong and not to guess a place it cannot identify. The
real fix is in the renderer (see v6_DESIGN.md).
"""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "v6_common", os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6_common.py"))
_c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_c)

SYSTEM_PROMPT = f"""You extract restaurant opinions from a Reddit thread in a New York City food subreddit. {_c.PURPOSE}

You get the post, then a chunk of its comments. Each comment starts with a number in brackets, and indentation shows replies. Extract from the comments only; the post, and the comments a reply answers, are its context. Every mention carries "id", the bracket number of the comment it came from. Never use a number that is not in brackets. Go through EVERY comment, one-word replies included: they are easy to skip and often hold the only complaint.

Output only JSON, {{"mentions": [...]}}, one object per place per comment, every field present.

READING THE TREE
A reply is about the place in the comment it answers unless it names another, and the mention takes the REPLY's id: "overrated" under a rec is a negative mention of that place; "hard disagree" under "X is overrated" is positive for X.
The indentation is drawn in posting order and is sometimes wrong: when several replies answer one comment, a later reply can appear under its sibling. If a reply makes no sense as an answer to the line just above it, it answers an earlier comment one indent further out; use the one it plainly responds to. If a reply's parent is not shown (it may be in another chunk), extract it only when the place is clear from its own words or the post. Never guess a place.

{_c.SCOPE}

FIELDS
id          The bracket number of the comment.
{_c.FIELDS}

{_c.SCALE}

{_c.RULES}

EXAMPLE (invented places)
POST: Best noodles in Queens?

[1] u/ann: Golden Lotus, and Pepper House if you can stand the line
  [2] u/bob: pepper house is overrated and $28 for noodles is a joke
    [3] u/ann: hard disagree, the cumin lamb is worth it
[4] u/cal: Avoid both. Noodle Lab is the move, just skip their dumplings
  [5] u/dee: is it still cash only?

1: Golden Lotus endorse (overall positive). Pepper House stated: overall positive, wait negative.
2: pepper house stated: overall negative, value negative, dish noodles (level null), notes {{"about":"overrated","text":"overrated","level":"negative","dish":null}} and {{"about":"price","text":"$28 for noodles","level":"negative","dish":"noodles"}}.
3: pepper house, named_in "context":
{{"id":3,"name":"pepper house","named_in":"context","location":null,"experience":"firsthand","opinion":"stated","overall":"positive","aspects":{{"taste":"positive","value":null,"service":null,"atmosphere":null,"wait":null}},"avoid":false,"dishes":[{{"dish":"cumin lamb","level":"positive","avoid":false}}],"price":null,"timeframe":"current","trend":null,"status":null,"tags":[],"notes":[]}}
4: Golden Lotus and Pepper House, named_in "context": avoid true, overall negative. Noodle Lab stated: overall positive, dish dumplings negative with avoid true.
5: Noodle Lab, named_in "context": opinion none, experience none, every level null."""

SCHEMA = _c.SCHEMA_THREAD
RESPONSE_FORMAT = _c.response_format(SCHEMA)
ANTHROPIC_OUTPUT_FORMAT = _c.anthropic_output_format(SCHEMA)
PROMPT_HASH = _c.prompt_hash(SYSTEM_PROMPT)
