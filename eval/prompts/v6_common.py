"""Shared text and schema for the v6 extraction prompts (comment and thread mode).

v6 records evidence and leaves scoring to later. Per place per comment it asks
for one verdict (overall) and five aspect verdicts on the owner's five-level
scale, counted downstream in people; whether the commenter went; whether they
gave an opinion at all; dish verdicts; and free notes, so that tips like "go
before noon" or "takes InKind" are kept rather than squeezed into a number.
eval/prompts/v6_DESIGN.md defines every field and lists what the owner still
has to decide.

What the benchmark of the lost v5 taught, and where each lesson lives here:
  * a "reference" bucket swallowed mild complaints, so negatives fell from
    0.87 to 0.71. opinion "none" is defined as neutral facts and questions
    only, and RULES 1 names the complaints that look like facts;
  * "not bad", "fine" and "ok" were read as praise. They are listed under
    neutral, and the positive level asks for real praise;
  * a bare dollar figure was never turned into a price level. That rule is
    kept, and the figure goes in a note instead.

Examples use invented places. No eval comment may ever appear in a prompt.

The schema lives in v6_schema.json so the prompt, the eval and production can
share one file. Every property is required and nullable through a type union,
which is what OpenAI's strict mode and Anthropic's structured outputs both
accept. Keep reasoning on when running these prompts: turning it off lost
negations that point at the parent comment (commit 512c016).
"""

import copy
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LEVELS = ("very_positive", "positive", "neutral", "negative", "very_negative")

with open(os.path.join(HERE, "v6_schema.json"), encoding="utf-8") as _f:
    SCHEMA_COMMENT = json.load(_f)


def _thread_schema():
    """The comment schema with an integer `id` first in every mention."""
    s = copy.deepcopy(SCHEMA_COMMENT)
    s["title"] = "NYCEats extraction v6 (thread mode)"
    m = s["$defs"]["mention"]
    m["properties"] = {"id": {"type": "integer"}, **m["properties"]}
    m["required"] = ["id"] + m["required"]
    return s


SCHEMA_THREAD = _thread_schema()


def response_format(schema):
    """OpenAI / OpenRouter `response_format` for strict structured output."""
    return {"type": "json_schema",
            "json_schema": {"name": "v6_mentions", "strict": True, "schema": schema}}


def anthropic_output_format(schema):
    """Anthropic Messages API `output_config.format`."""
    return {"type": "json_schema", "schema": schema}


def prompt_hash(text):
    """Same definition as prompt.PROMPT_HASH and eval/run.py."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


PURPOSE = ("Readers see how many people praise or complain about each place, and "
           "what they say: dishes to get or skip, prices, tips. So capture "
           "everything the comment says about each place, and never drop or "
           "soften a complaint.")

SCOPE = """WHAT COUNTS
Every restaurant, cafe, bakery, bar, deli, food truck, cart, stall or chain in New York City that the comment names or clearly refers to: names in a list (the most common case; single-word names like Tong, Keens or Emily are the easiest to miss), questions about a place, places not yet tried, closed places, and places used as comparisons. Not places: cuisines, dishes, neighborhoods, streets, supermarkets and grocery stores, apps and services (Resy, InKind, Beli), people, and places outside NYC. A place named twice is one mention."""

FIELDS = """name        The name exactly as typed. Never fix spelling or case, never add words. For a place the comment refers to without naming it, copy the name from the context.
named_in    "comment", or "context" when the name was copied from the context.
location    Where the comment places THIS place ("the LES one", "on 2nd Ave"), else null.
experience  "firsthand": describes going or eating there, or gives their own pick or verdict. "secondhand": repeats others ("heard great things", "my friend swears by it", "people say it's gone downhill"). "none": anything else (questions, "on my list", a bare fact).
opinion     "none": only neutral facts or a question ("cash only", "they moved to Bushwick", "is it still good?"). "endorse": named as a pick with nothing said about it (a list item, "try X", "second this" under a rec). "stated": anything that judges the place.
overall     LEVEL. The verdict on the place as a whole: is it worth going? "Best slice in the city" is overall and taste very_positive; "go early to beat the line" has no overall (null). Always "positive" for "endorse".
aspects     {taste, value, service, atmosphere, wait}, each a LEVEL or null. Only what is said; never infer one aspect from another or from overall.
              taste: the food and drink. value: worth the money, including portions for the price. service: staff, and how the place is run. atmosphere: room, vibe, noise, crowd. wait: lines, getting a table or reservation, slow food, selling out.
avoid       true only when the comment tells OTHERS to avoid the place: "skip it", "don't bother", "tourist trap", an avoid list. A bad review alone, or "I won't go back", is false.
dishes      Every dish or drink named for this place: {"dish", "level": LEVEL, or null if only named, "avoid": true for "skip / don't get the X"}. "Get the X" is "positive".
price       How pricey, only when said in words: "very_cheap", "cheap", "moderate", "expensive", "very_expensive", else null. A dollar figure alone is not a price level (note it instead), and "overpriced" is value, not price.
timeframe   "current", or "past" when the levels describe how it was, not how it is (a closed place, a visit years ago with nothing about now).
trend       "declined" or "improved" when the comment says it changed, else null.
status      "closed", "moved", "opened" (new or reopened), else null.
tags        The commenter's own words for what the place is or is for, as someone would search: cuisine, format, occasion, diet, payment ("sichuan", "slice shop", "omakase", "date night", "halal", "byob", "cash only"). [] if none.
notes       Everything else said about the place that no field above holds, so nothing is lost: {"about": short label, "text": short paraphrase, "level": LEVEL or null, "dish": dish or null}. Tips ("best time to go"), facts ("accepts InKind"), prices ("$24 a bowl"), comparisons, the specifics behind a verdict ("pasta portions tiny"). No note that only repeats a level."""

SCALE = """LEVELS: "very_positive", "positive", "neutral", "negative", "very_negative", or null.
  very_positive  superlative or emphatic: "best in the city", "my favorite", "one of the best meals of my life", "god tier", "a must"
  positive       real praise: "good", "great", "delicious", "pretty solid", "worth it", "get the X"
  neutral        a verdict that is middling or mixed: "fine", "ok", "not bad", "decent", "meh", "hit or miss", "good, not great"
  negative       any knock or complaint, however mild or polite: "mid", "overrated", "nothing special", "underwhelming", "bland", "overpriced", "rude", "hard to get a reservation", "the line is insane"
  very_negative  strong: "worst I've had", "inedible", "disgusting", "got sick", "never again", "regretted going", "avoid at all costs"
null means not mentioned. neutral is a verdict, never a stand-in for "not mentioned"."""

RULES = """RULES
1. opinion "none" is ONLY for neutral facts and questions. A complaint put as a fact is an opinion: "impossible to get a reservation" and "they sell out by noon" are wait negative; "tiny portions for the price" is value negative.
2. A complaint no aspect holds (portion size, overrated, got sick, stopped making a dish) goes in notes with a plain "about" and its level: "they stopped making the babka" is about "stopped making the babka", level negative.
3. Positive needs real praise. "Not bad", "fine", "ok" and "decent" are neutral.
4. A heading or lead-in covers every name under it: "My favorites:" makes each very_positive; "I'd skip all of these: A, B, C" makes all three avoid true, overall negative.
5. "This", "+1" and "second this" take the verdict they agree with: under a rec or praise, endorse; under a knock, stated with the same overall.
6. Levels are what the commenter thinks NOW. "Used to be great, now mid": overall negative, trend declined. A closed place remembered fondly: overall positive, status closed, timeframe past.
7. Losing a comparison is not a complaint: in "I prefer A over B", B gets no level, only a note.
8. Thread framing and sarcasm decide polarity: "second this" under "worst meal you've had?" is negative.
9. Never soften a complaint because the thread likes the place or the commenter is polite."""

EXAMPLE_JSON = """{"mentions":[{"name":"Golden Lotus","named_in":"context","location":null,"experience":"firsthand","opinion":"stated","overall":"negative","aspects":{"taste":"negative","value":"negative","service":null,"atmosphere":null,"wait":"negative"},"avoid":false,"dishes":[{"dish":"noodles","level":"negative","avoid":false}],"price":null,"timeframe":"current","trend":null,"status":null,"tags":[],"notes":[{"about":"price","text":"$24 a bowl","level":"negative","dish":"noodles"},{"about":"best time to go","text":"go early, line by noon","level":null,"dish":null}]}]}"""
