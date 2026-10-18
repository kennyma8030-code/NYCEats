"""Shared text and schema for the v6 extraction prompts (comment and thread mode).

v6 records evidence and leaves scoring to later. Per place per comment it asks
for one verdict (overall) and five aspect verdicts on the owner's five-level
scale, counted downstream in people; whether the commenter went; whether they
gave an opinion at all; dish verdicts; and free notes, so that tips like "go
before noon" or "takes InKind" are kept rather than squeezed into a number.
eval/prompts/v6_DESIGN.md defines every field and lists what the owner still
has to decide.

The Haiku 5.5 benchmark of the lost v5 prompt shaped the rules. The full
issue-to-rule table is in v6_DESIGN.md; in short:
  * a "reference" bucket swallowed mild complaints, so negative recall fell
    from 0.87 to 0.71. opinion "none" is facts and questions with no
    judgment (RULES 1), and every complaint must lower a level (RULES 2);
  * lukewarm words were read as praise or as "mixed", where the gold calls
    them a mild knock. They are negative (RULES 3), and neutral is kept for
    a verdict that weighs good against bad;
  * missed negatives came back "scored positive", the named-as-an-answer
    default applied to places that had a remark. "endorse" is only a bare
    pick (RULES 4), and a trait shared with another place carries over to
    it (RULES 5);
  * value complaints fell from 0.98 to 0.80. Any money complaint is value
    negative (RULES 6). A bare dollar figure still never becomes a price
    level.

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
Every restaurant, cafe, bakery, bar, deli, food truck, cart, stall or chain in New York City that the comment names or clearly refers to: names in a list (the most common case; single-word names like Tong, Keens or Emily are the easiest to miss), places not yet tried, closed places, comparisons, examples, food places used as landmarks ("near X"), and places a comment only asks about or names in passing (opinion "none"). Not places: cuisines, dishes, neighborhoods, streets, museums, stores, parks, venues, supermarkets and grocery stores, apps and services (Resy, InKind, Beli), people, and places outside NYC. A place named twice is one mention."""

FIELDS = """name        The name exactly as the comment types it, even shortened or misspelled ("2nd Ave", "lindustrie"); never fix it from the context. Only for a place the comment doesn't name, copy the name from the context.
named_in    "comment", or "context" when the name was copied from the context.
location    Where the comment places THIS place ("the LES one", "on 2nd Ave"), else null.
experience  "firsthand" is the default: a visit, or any pick, list item or verdict in their own voice. "secondhand" only when they credit someone else ("heard great things", "my friend swears by it", "people say"). "none" only for questions, places not yet tried, and bare facts.
opinion     "none": only neutral facts, a question, or a name in passing ("cash only", "they moved to Bushwick", "is it still good?", "near X"). "endorse": a bare name or "try X" with no word of praise (a plain list item, "second this" under a rec). "stated": anything that judges the place; one praise word ("great burger too") makes it stated.
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
  very_positive  a superlative about THIS place against a broad class: "best in the city", "best X I've ever had", "my favorite in NYC", "one of the best meals of my life", "god tier", "life-changing"
  positive       real praise, a clear yes: "good", "great", "amazing", "so good", "love it", "my favorite", "my go-to", "a must", "delicious", "pretty solid", "worth it", "get the X"
  neutral        a balanced verdict, good and bad weighed evenly: "hit or miss", "great food, awful service". Never for lukewarm words.
  negative       any knock, however mild or polite, lukewarm words included: "fine", "ok", "not bad", "meh", "mid", "nothing special", "overrated", "underwhelming", "bland", "overpriced", "rude", "hard to book", "the line is insane"
  very_negative  strong: "worst I've had", "inedible", "disgusting", "got sick", "never again", "regretted going", "avoid at all costs"
null means not mentioned. neutral is a verdict, never a stand-in for "not mentioned"."""

RULES = """RULES
1. opinion "none" is ONLY for facts and questions with no judgment at all. A complaint put as a fact is stated, with a negative level: "impossible to book", "they sell out by noon", "the line started at 4:15", "be there by 11:30" and "busy even in the rain" are wait negative, while "easy walk-ins", "free tables at 4" and "no line on weekdays" are wait positive; "tiny portions for the price" is value negative; "the sauce comes from a jar now" is taste negative.
2. Every complaint lowers a level: the aspect it is about, or overall when none fits. A note adds the detail of a complaint no aspect names (overrated, got sick, portion size, stopped making a dish), with a plain "about" and its level, but never holds a complaint alone.
3. Lukewarm is negative. On this subreddit "fine", "ok", "not bad" and "meh" are knocks, not praise and not neutral.
4. Never default to positive. "endorse" is only for a bare name with no word of praise. A place with any remark that judges it is "stated" and leveled by what is said; one only asked about or named in passing is "none". A complaint replying to a rave is still a complaint.
5. A comparison judges both sides; note it on each. The loser is negative by default ("I prefer A over B": B negative), very_negative if the comment says it is far worse, and positive if the comment says both are good ("both great, I just prefer A"). Shared traits carry over: "as hard to book as X" is wait negative for X too.
6. Money complaints are value negative: "overpriced", "not worth the money", "for the price", "$28 for that is a joke". The dollar figure also goes in a note.
7. A complaint about one dish is a negative dish entry, even when the place is praised.
8. A heading or lead-in covers every name under it: "My favorites:" makes each item stated, positive (very_positive only with its own superlative); "I'd skip all of these: A, B, C" makes all three avoid true, overall negative.
9. "This", "+1" and "second this" take the verdict they agree with: under a rec or praise, endorse; under a knock, stated with the same overall.
10. Levels are what the commenter thinks NOW. "Used to be great, now mid": overall negative, trend declined. A closed place remembered fondly: overall positive, status closed, timeframe past.
11. Thread framing and sarcasm decide polarity: "second this" under "worst meal you've had?" is negative.
12. Never soften a complaint because the thread likes the place or the commenter is polite."""

EXAMPLE_JSON = """{"mentions":[{"name":"Golden Lotus","named_in":"context","location":null,"experience":"firsthand","opinion":"stated","overall":"negative","aspects":{"taste":"negative","value":"negative","service":null,"atmosphere":null,"wait":"negative"},"avoid":false,"dishes":[{"dish":"noodles","level":"negative","avoid":false}],"price":null,"timeframe":"current","trend":null,"status":null,"tags":[],"notes":[{"about":"price","text":"$24 a bowl","level":"negative","dish":"noodles"},{"about":"best time to go","text":"go early, line by noon","level":null,"dish":null}]}]}"""
