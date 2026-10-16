"""v5, comment mode: one Reddit comment in, its restaurant mentions out.

Inputs are production's own comment-mode rendering (POST TITLE, the first 400
chars of the POST BODY, the PARENT COMMENT, the COMMENT), so only the system
prompt changes. That is why this file defines no build_user_message. The shared
wording lives in v5_common.py.
"""

import hashlib
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "v5_common", os.path.join(os.path.dirname(os.path.abspath(__file__)), "v5_common.py"))
_c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_c)
M, OUT = _c.mention, _c.output

EXAMPLES = "\n\n".join([
    "EXAMPLES (invented places)",

    """POST TITLE: Best Thai in Queens?
COMMENT: Thai - Siam Garden and Lemongrass Hut
""" + OUT(M("Siam Garden", desc=["Thai"]),
          M("Lemongrass Hut", desc=["Thai"])) + """
Why: "Thai" is a heading, not a restaurant. Both names answer a request for places, so both are endorsements: reference_only false, every aspect null.""",

    """POST TITLE: Most overrated restaurant in Manhattan?
COMMENT: Copper Kettle. Also Marlowe's, the service is slow
""" + OUT(M("Copper Kettle", food="meh", desc=["overrated"]),
          M("Marlowe's", food="meh", service="bad", exp="ate_there", desc=["overrated"])) + """
Why: the post asks for overrated places, so each bare name takes that judgment: food "meh", descriptor "overrated". "the service is slow" adds service "bad".""",

    """POST TITLE: Late night food in the East Village
COMMENT: Is Okiku still cash only?
""" + OUT(M("Okiku", ref=True)) + """
Why: a question about a place is a reference. "cash only" is asked, not stated, so there is no descriptor.""",

    """POST TITLE: Golden Lotus closing?
COMMENT: No, they just moved to the Flushing location. It's BYOB now too
""" + OUT(M("Golden Lotus", ref=True, hood="Flushing", desc=["BYOB"])) + """
Why: the comment is about the place the post names, so the name is copied from the post. It states facts and judges nothing, so it is a reference that still carries the location and "BYOB".""",

    """POST TITLE: Where should I eat near Times Square?
COMMENT: Bridge Diner is a tourist trap. Pricey too. Go to Sal's Slices instead, get the grandma slice
""" + OUT(M("Bridge Diner", food="bad", neg=True, price="pricey", exp="ate_there", desc=["tourist trap"]),
          M("Sal's Slices", food="good", exp="ate_there", liked=["grandma slice"])) + """
Why: "tourist trap" judges the place, so food is "bad". "Go to Sal's Slices instead" tells people to avoid Bridge Diner. "Pricey" is price; nothing says whether it is worth it, so value stays null. "get the grandma slice" recommends a dish, and food follows it.""",

    """POST TITLE: Brunch in Park Slope
PARENT COMMENT: Marlowe's is my go-to brunch spot
COMMENT: honestly mid, and the wait is insane
""" + OUT(M("Marlowe's", food="meh", wait="bad", exp="ate_there")) + """
Why: the comment never types a name, but it judges the place its parent names, so it is a mention of "Marlowe's". "mid" is "meh", never "decent".""",

    """POST TITLE: Gino's, Pepper Pie or Nonna Rosa?
COMMENT: I'd skip everyone you mentioned. Gino's, Pepper Pie, Nonna Rosa - tourist traps now
""" + OUT(M("Gino's", food="bad", neg=True, exp="ate_there", desc=["tourist traps"]),
          M("Pepper Pie", food="bad", neg=True, exp="ate_there", desc=["tourist traps"]),
          M("Nonna Rosa", food="bad", neg=True, exp="ate_there", desc=["tourist traps"])) + """
Why: an avoid instruction at the head of a list applies to EVERY name in it. This is the easiest thing to get wrong.""",

    """POST TITLE: Sichuan in Flushing?
COMMENT: Pepper House is hit or miss. Get the cumin lamb, skip the dumplings. I also had the cucumber salad. Cheap for the area
""" + OUT(M("Pepper House", food="mixed", price="cheap", exp="ate_there",
            liked=["cumin lamb"], disliked=["dumplings"], mentioned=["cucumber salad"])) + """
Why: "hit or miss" is the verdict on the food overall, so food is "mixed". Each dish goes in exactly one list: recommended, judged negatively, or only named.""",

    """POST TITLE: Omakase under $100?
COMMENT: Haven't been but my friend swears by Okiku. Supposedly it's like Hoshi
""" + OUT(M("Okiku", food="good", exp="secondhand"),
          M("Hoshi", ref=True)) + """
Why: the opinion on Okiku is the friend's, so experience is "secondhand"; the opinion is still recorded. Hoshi is only a yardstick, so it is a reference.""",

    """POST TITLE: What closed spot do you miss most?
COMMENT: Silver Pond. Closed last year, their soup dumplings were the best
""" + OUT(M("Silver Pond", ref=True, exp="ate_there", mentioned=["soup dumplings"], desc=["closed"])) + """
Why: a closed place is a reference with "closed" in descriptors and every aspect null, even when it is remembered fondly. Its remembered dish goes in dishes_mentioned.""",

    """POST TITLE: Ramen recs?
COMMENT: Kumo over Hikari any day
""" + OUT(M("Kumo", food="good", exp="ate_there"),
          M("Hikari", food="meh", exp="ate_there")) + """
Why: Hikari lost the comparison, so it is food "meh" and is_negated stays false.""",

    """POST TITLE: Best slice near Court St?
PARENT COMMENT: Tony's Corner on Court St
COMMENT: went last month, worst slice I've had and the guy at the counter was rude. regretted going
""" + OUT(M("Tony's Corner", food="awful", service="bad", exp="ate_there", disliked=["slice"])) + """
Why: named from the parent. "worst I've had" and "regretted going" are "awful". It is a bad review, not an instruction to others, so is_negated is false.""",

    """POST TITLE: Best bagels?
COMMENT: Honestly any bodega bagel with scallion cream cheese hits
""" + OUT() + """
Why: no place is named or pointed at.""",
])

SYSTEM_PROMPT = f"""You extract restaurant mentions from ONE Reddit comment posted in a New York City food subreddit.

The input has these parts, in this order: POST TITLE, usually POST BODY (cut at 400 characters), sometimes PARENT COMMENT (the comment this one replies to), and then COMMENT. The other parts exist only to make sense of the COMMENT. Extract from the COMMENT. Never extract a place that is only named in the title, body or parent -- unless the COMMENT says something about it or asks about it. A comment that gives an opinion without repeating the name IS a mention of the place it replies about.

Output ONLY a JSON object. No prose, no code fences:

{{"mentions": [ {{...}}, {{...}} ]}}

Use {{"mentions": []}} only when the comment names and points at no place at all. That is a normal answer.

{_c.KINDS}

{_c.FIELDS}

{_c.LEVEL_TABLE}

{_c.OTHER_FIELDS}

{_c.RULES}

{EXAMPLES}"""

PROMPT_HASH = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]
