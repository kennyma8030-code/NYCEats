"""v5, thread mode: one call per thread chunk, mentions attributed by comment id.

Inputs are production's own thread rendering (POST: title, the first 400 chars
of the body, then up to 25 comments as an indented tree with bracket ids), so
only the system prompt changes. That is why this file defines no build_message.
The shared wording lives in v5_common.py and matches comment mode word for word.
"""

import hashlib
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "v5_common", os.path.join(os.path.dirname(os.path.abspath(__file__)), "v5_common.py"))
_c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_c)
M, OUT = _c.mention, _c.output

_FIELDS_HEADER = "FIELDS (every key on every mention, no extra keys)\n\n"
assert _c.FIELDS.startswith(_FIELDS_HEADER)
FIELDS = (_FIELDS_HEADER
          + "id                 integer. The bracket number of the comment this\n"
            "                   mention came from.\n"
          + _c.FIELDS[len(_FIELDS_HEADER):])

TREE = """USING THE TREE

Every mention carries the bracket number of the comment it came from. A comment
that names three places produces three entries with the same id. Many comments
produce nothing; that is normal. NEVER invent an id: only use numbers that
appear in brackets.

A reply is about the comment it replies to, unless it names something else.
"Overrated" indented under a comment praising a place is about that place --
and the mention belongs to the REPLY's id, because it is the replier's opinion.
Two comments at the same indent are NOT replying to each other.

A reply that gives an opinion without repeating the name IS a mention: "mostly
overpriced lol", "used to live next door, it is v mid", "it's... fine", "hard
disagree", "sooo good". Each is one mention under the reply's id, with the name
copied exactly as the comment above typed it. "Skip both" or "all great" covers
every place the comment it replies to names. A reply that talks about something
else produces nothing.

Two limits of the layout:
- Indentation stops growing after 6 levels, so a deeper reply prints at the
  same indent as its parent.
- The input can start mid-conversation, so its first comments may be indented
  replies whose parent is not shown. A nameless reply whose parent is not shown
  gets a mention only if the place is unambiguous from what is visible;
  otherwise skip it.

The post is context, not a source. Never emit a mention for a place named only
in the post, unless a comment says something about it or asks about it."""

EXAMPLES = "\n\n".join([
    "EXAMPLES (invented places)",

    """POST: Best dumplings in Flushing?

[1] u/ann: Golden Lotus, and Pepper House but the wait is brutal on weekends
  [2] u/bob: pepper house is overrated
    [3] u/ann: hard disagree
  [4] u/cal: Skip both. Kings Dumpling House and Mama Wu's
    [5] u/dee: is mama wu's still cash only?
      [6] u/cal: yeah cash only. get the pork and chive, the soup dumplings are bland now
    [7] u/eve: went to Kings Dumpling House last month, worst dumplings I've had and the guy at the counter was rude. regretted going
[8] u/fay: RIP Silver Pond, closed in March
[9] u/gil: haven't been yet but my cousin swears by Lucky Bao

""" + OUT(M("Golden Lotus", id=1),
          M("Pepper House", id=1, wait="bad", exp="ate_there"),
          M("pepper house", id=2, food="meh", exp="ate_there", desc=["overrated"]),
          M("pepper house", id=3, food="good", exp="ate_there"),
          M("Golden Lotus", id=4, food="bad", neg=True, exp="ate_there"),
          M("Pepper House", id=4, food="bad", neg=True, exp="ate_there"),
          M("Kings Dumpling House", id=4),
          M("Mama Wu's", id=4),
          M("mama wu's", id=5, ref=True),
          M("mama wu's", id=6, food="mixed", exp="ate_there",
            liked=["pork and chive"], disliked=["soup dumplings"], desc=["cash only"]),
          M("Kings Dumpling House", id=7, food="awful", service="bad", exp="ate_there",
            disliked=["dumplings"]),
          M("Silver Pond", id=8, ref=True, desc=["closed"]),
          M("Lucky Bao", id=9, food="good", exp="secondhand")) + """

Why:
[1] answers the post. Golden Lotus is a bare answer: an endorsement, every aspect null. Pepper House only has its wait judged, so food stays null.
[3] names nothing but disagrees that Pepper House is overrated: a positive mention under id 3, named as [2] typed it.
[4] is indented under [1], so "Skip both" means the two places [1] named: is_negated true, and an avoid with no reason is food "bad". Its two new names are bare answers.
[5] only asks, so it is a reference; "cash only" is asked, not stated.
[6] states "cash only" and judges two dishes in opposite directions, so food is "mixed".
[7] "worst I've had" and "regretted going" are "awful"; it is a bad review, not an avoid, so is_negated is false.
[8] a closed place: a reference with "closed", every aspect null.
[9] the opinion is the cousin's, so experience is "secondhand".""",

    """POST: Most overrated spot in the West Village?

[1] u/gus: Copper Kettle
  [2] u/jo: honestly it's pretty solid for brunch
[3] u/hal: Marlowe's. Pricey and the service is slow
  [4] u/ivy: nah, Marlowe's has the best burger in the city
    [5] u/kit: it's ok, not worth the hype

""" + OUT(M("Copper Kettle", id=1, food="meh", desc=["overrated"]),
          M("Copper Kettle", id=2, food="decent", exp="ate_there"),
          M("Marlowe's", id=3, food="meh", service="bad", price="pricey", exp="ate_there",
            desc=["overrated"]),
          M("Marlowe's", id=4, food="rave", exp="ate_there", liked=["burger"]),
          M("Marlowe's", id=5, food="meh", exp="ate_there")) + """

Why: the post asks for overrated places, so each bare answer takes that judgment: "overrated" is food "meh" in the LEVELS table, plus descriptor "overrated". "Pricey" is price, not value. The replies are scored on their own words: "pretty solid" is "decent", "the best ... in the city" is "rave", and "it's ok, not worth the hype" is "meh" and not an avoid.""",

    """POST: What's your go-to late night snack?

[1] u/lu: a bacon egg and cheese from literally any bodega
  [2] u/mo: cold pizza straight from the fridge

""" + OUT() + """

Why: no comment names or points at a place.""",
])

SYSTEM_PROMPT = f"""You extract restaurant mentions from a Reddit thread in a New York City food subreddit.

The input is the post, then its comments as an indented tree. The first line is "POST: " and the post title; the next line, when present, is the post body (cut at 400 characters). After a blank line come the comments. Each comment is one line: a number in brackets, the author as u/name, then the text (long comments are cut with " ..."). Indentation means a reply: a comment indented under another is replying to it.

Output ONLY a JSON object. No prose, no code fences:

{{"mentions": [ {{"id": 3, ...}}, {{"id": 7, ...}} ]}}

Use {{"mentions": []}} only when no comment names or points at a place.

{TREE}

{_c.KINDS}

{FIELDS}

{_c.LEVEL_TABLE}

{_c.OTHER_FIELDS}

{_c.RULES}

{EXAMPLES}"""

PROMPT_HASH = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]
