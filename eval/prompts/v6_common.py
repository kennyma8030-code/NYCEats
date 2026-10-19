"""Shared text and schema for the v6 extraction prompts (comment, post and thread mode), round 4.

v6 records evidence and leaves scoring to later. Per place per comment it asks
for one verdict (overall) and five aspect verdicts on the owner's five-level
scale, counted downstream in people; whether the commenter went; whether they
gave an opinion at all; dish verdicts; and free notes, so that tips like "go
before noon" or "takes InKind" are kept rather than squeezed into a number.
eval/prompts/v6_DESIGN.md defines every field.

Round 4 is built from the Opus review of round 3 (eval/review_v6: report.md and
analysis/). What changed, and why:
  * the prompt now agrees with the rubric the judges used. Five round-3 lines
    told Haiku to do what the rubric marks wrong ("never again" as
    very_negative, a "far worse" loser as very_negative, a line tip with no
    overall, a dish superlative lifting overall, an old visit as past), and
    they caused about 100 of the 535 errors. The owner's final decisions
    (untried reactions, wait-only remarks, the word lists, comparisons, scores,
    stores and food halls, branches, boycotts, timing tips) are written in;
  * the level labels state their test: superlative_praise, praise, mixed,
    knock, extreme_knock. Haiku used very_* 131 times and the judges cut 72,
    because "very_positive" reads as "very enthusiastic". v6_adapter maps the
    labels back to the owner's five levels, so nothing downstream changes;
  * evidence before verdict: dishes, notes and aspects come before opinion
    and overall in the schema. Structured output writes keys in schema order,
    and at low effort half the calls don't think, so the JSON is the
    reasoning; round 3 wrote overall first and left it null after judging a
    dish or an aspect 54 times;
  * notes lost their level and dish slots. A complaint or a dish filed only in
    a note (28 errors) has nowhere to hide now: its level must go in an
    aspect, a dish or overall;
  * a kind per place, so code drops groceries, brands, venues and companies
    (eval/v6_validate.py) and the owner's store policy is a switch, not a
    re-extraction;
  * experience asks whose opinion it is, not whether a visit is described
    (accuracy 0.86 in round 3; secondhand was wrong in 32 of 43 uses);
  * XML sections, five short contrastive examples instead of one JSON one, and
    a <before_answering> checklist that asks for thinking, aimed at the 52% of
    low-effort calls that answered without any.
The comment-mode input changed too: v6_comment.build_user_message.

Examples use invented places. No eval comment may ever appear in a prompt.

The schema lives in v6_schema.json (rounds 1 to 3: v6r3_schema.json). Every
property is required and nullable through a type union, which is what OpenAI's
strict mode and Anthropic's structured outputs both accept; it has 11 union
fields, under the documented limit of 16. Keep reasoning on when running these
prompts: turning it off lost negations that point at the parent comment
(commit 512c016).
"""

import copy
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
# Schema labels, in the owner's order, and the owner's names for them (v6_adapter.LEVEL_MAP).
LEVELS = ("superlative_praise", "praise", "mixed", "knock", "extreme_knock")
OWNER_LEVELS = dict(zip(LEVELS, ("very_positive", "positive", "neutral", "negative", "very_negative")))
KINDS_COUNTED = ("restaurant", "bar", "cafe", "bakery", "deli", "truck_or_cart", "market_stall", "food_hall")
KINDS_EXCLUDED = ("grocery", "brand", "venue", "company", "other")

with open(os.path.join(HERE, "v6_schema.json"), encoding="utf-8") as _f:
    SCHEMA_COMMENT = json.load(_f)


def _thread_schema():
    """The comment schema with an integer `id` first in every mention."""
    s = copy.deepcopy(SCHEMA_COMMENT)
    s["title"] = "NYCEats extraction v6 round 4 (thread mode)"
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


PURPOSE = ("Readers see how many people praise or complain about each place, and what they say: "
           "dishes to get or skip, prices, tips. So capture everything the comment says about each "
           "place, and never drop or soften a complaint.")

SCOPE = """<what_counts>
Every food or drink place in New York City the text names or refers to: restaurants, bars, cafes, bakeries, delis, food trucks and carts, chains, food halls and night markets (the hall and each named stall). That includes names in a list (the most common case; one-word names like Tong or Keens are easy to miss), places not yet tried, closed places, both sides of a comparison, a benchmark or style ("JG Mellon style"), places used as landmarks, and places only asked about or named in passing.
A store counts for the food it serves to eat (a market's deli counter, bakery or prepared food: kind deli, bakery or cafe); named only for groceries, it is kind grocery. Extract a product brand, an entertainment venue or a company named as a food source with that kind; code keeps those kinds out of the counts.
Not mentions: cuisines, dishes, neighborhoods, streets, parks, museums, people (chefs, critics, influencers, users; but "dinner at Chef Marco's" names a restaurant, and "the Golden Lotus chef" is a name in passing), apps (Resy, Beli, delivery apps), places outside the five boroughs and foreign branches ("Golden Lotus in Tokyo"; the NYC one gets only what is said about it), a name the commenter takes back, and places nobody names ("a taco spot on Rivington").
A place named twice is one mention. A rename ("Golden Lotus, formerly Lotus House") is one mention under the current name, the old name in a note. A room or counter inside a restaurant is part of it.
</what_counts>"""

FIELDS = """<fields>
Write each place's fields in this order: what is said first, the verdict last.
name        As typed, even shortened, misspelled or as initials ("2nd Ave", "lindustrie", "GLN"). Only for a place the text doesn't name, copy the name from the context.
named_in    "comment", or "context" when the name was copied from the context.
kind        restaurant, bar, cafe, bakery, deli, truck_or_cart, market_stall (a stall in a market or hall), food_hall (the hall or market as a whole); or grocery, brand, venue (a club, theater or game bar, unless its food or drink is discussed), company, other (not counted).
location    Where the text places THIS place or branch ("the LES one", "on 2nd Ave"), else null.
experience  Whose opinion it is, not whether a visit is described. "firsthand" (the default): anything in their own voice: a visit, a pick, a list item, a tip, a hedge ("I think X has it"), a reply about someone else's place. "secondhand" only when the text credits someone else ("my friend swears by it", "heard it's great", "people say A beats B"). "none": a question, a place they haven't tried, a bare fact.
dishes      Every dish or drink named for this place: {"dish", "level" (null if only named), "avoid" (true for "skip the X")}. "Get / try the X", "X for the Y" and a dish heading over picks ("Mazemen: A, B") are praise. One dish named two ways is one entry.
notes       What no other field holds, as {"about": short label, "text": short paraphrase}: tips ("best time to go"), facts ("cash only"), prices ("$24 a bowl"), comparisons, rank order, the detail behind a verdict ("portions tiny"), a reason that sets no level ("boycott"). A note never replaces a level: the judgment goes in an aspect, a dish or overall.
aspects     {taste, value, service, atmosphere, wait}: each a LEVEL from what is said about that side, else null. Never copied from overall.
              taste: the food and drink. A verdict on a dish sets taste ("love the hash wrap": praise; "great brisket, awful sides": mixed).
              value: worth the money ("a steal", "not worth $30", surprise fees). The word before "for the price" decides: "great for the price" praise, "tiny for the price" knock.
              service: staff, and how the place is run (policies, "prix-fixe only").
              atmosphere: room, vibe, noise, crowd, seating. "Packed and lively" said as praise is atmosphere.
              wait: lines, getting a table, slow food, selling out. A knock when you must plan around it ("be there by 11:30", "book the minute slots open", "sold out by 2", "brutal lines"); praise when getting in is easy ("walked right in", "free tables at 4").
            Fit for one person or occasion ("not for kids", "more casual") is a note or tag, not a level.
opinion     "none": a fact, a question, business news (closing, rent), a name in passing or as an example, an untried reaction. "endorse": a pick with no word of judgment: a bare name, "try X", "get the Y at X", "X for the Y", "they have it at X", "+1" under a rec. "stated": any word judging the place or its food, even one ("great burger too").
overall     LEVEL, decided last. The commenter's bottom line ("worth it", "not worth the trip", "skip it", "I'd go back"), even against points on the other side. Without one, a lone taste, value, service or atmosphere verdict sets it; several, the strongest non-wait point, usually the food. A remark only about the wait leaves overall null, unless they draw a bottom line from it ("not worth the wait"). null for a fact, a question or an untried reaction; "praise" for endorse. A superlative about one dish makes the dish and taste superlative_praise, overall only if said of the place or the dish is what it sells.
avoid       true only when the text tells readers to skip the place itself: "skip it", "don't bother", "tourist trap", "make it at home instead". false for a bad review alone, "I won't go back", a swap ("go to Y instead"), one branch, or an insult with no instruction.
timeframe   "past" when the place is closed, or the text ties the verdict to an earlier time ("used to be great", "back in 2015", "when it was on Mott St"). An old visit with nothing tying it to then is "current".
trend       "declined" or "improved" only when the text says the place's quality changed. Not for closing, fewer customers, a lost star, a prediction, or one aspect.
status      The place under that name: "closed" ("closed", "RIP X"), "moved", "opened" (new or reopened), else null. One branch closing, opening or moving, a temporary closure or a rumored reopening is null, with the branch in location and a note.
price       Only an absolute price word: "very_cheap", "cheap", "moderate", "expensive", "very_expensive", else null. Not a dollar figure, not "cheaper than X", not "overpriced" (that is value).
tags        The commenter's words for what the place is or is for, as someone would search: cuisine, format, occasion, diet, payment ("sichuan", "slice shop", "date night", "byob"). [] if none.
</fields>"""

SCALE = """<levels>
LEVEL is one of these, or null when not said:
  superlative_praise  ONLY a superlative ranking this place or dish against the whole city or wider: "best in the city", "best X I've ever had", "my favorite in NYC", "one of the best meals of my life", "nothing in NYC comes close".
  praise              any real yes, mild or wild: "decent", "solid", "good for what it is", "good", "great", "amazing", "to die for", "unreal", "god tier", "10/10", "my favorite", "my go-to", "best on the UES", "best I've had lately", "a must", "get the X".
  mixed               good and bad weighed evenly, with no bottom line: "hit or miss". Never for lukewarm words.
  knock               any complaint, mild or strong: "fine", "ok", "not bad", "meh", "mid", "average", "mediocre", "nothing special", "not worth the trip", "overrated", "overpriced", "disappointing", "bland", "rude", "terrible", "awful", "sucks", "never again", "regretted going", "the line is insane".
  extreme_knock       ONLY an extreme: "worst I've ever had", "worst in the city", "inedible", "disgusting", "got sick", "food poisoning", "avoid at all costs".
Emphasis, caps, swearing, emoji and stacked knocks never raise a level. Scores: 8/10 and up is praise, anything lower a knock.
</levels>"""

RULES = """<rules>
1. A complaint put as a fact is a judgment: "impossible to book" (wait knock), "the sauce comes from a jar now" (taste knock). opinion "none" is only for facts and questions with nothing judged.
2. Every complaint lowers a level: its aspect, a dish, or overall when no aspect fits. Hygiene (a bad grade, violations, roaches) is overall, not service, with a note. Getting sick is overall extreme_knock; taste stays null unless flavor is judged.
3. Not tried: someone who says or shows they haven't been ("looks so good", "sounds amazing", "can't wait to try", "saved it", "thanks, will check it out", "that's what I was afraid of") gives no verdict: experience "none", opinion "none", every level null. Not secondhand, which passes on a verdict ("my friend got sick there").
4. Lukewarm stays a knock in a defense ("it's not that bad") and about price ("not the best or worst price"). "I like it, but it's not worth it" is a knock: the bottom line wins. An excuse with no verdict ("it's a small business") is opinion "none".
5. Comparisons. The loser gets a knock on what was compared: food → taste, price or portions → value, line or booking → wait, the place as a whole ("I prefer A over B", "go to A instead" answering "is B worth it?") → overall. It stays praise when both are called good ("A beats B, but both are great"). "As good as X" and "X-level" praise X. "Close, but not A" makes the other place the loser. No loser without a named winner. A swap for fit ("more casual", "closer to your hotel") compares nothing. A low-bar winner ("even Burger Barn is better") gets no level. Ranked picks ("A, B, C in that order") are all praise, the order in a note.
6. A bare answer takes from the question its polarity, the aspect and the dish it asks about, never its superlative: under "easiest walk-ins?" each pick also gets wait praise; under "best chicken salad?" each gets that dish and overall praise, not superlative_praise; under "worst meal you've had?" each is a knock. A heading works the same way ("My favorites:", "Skip these:"). Names given as examples or facts are opinion "none". The commenter's own words outrank the framing, and framing never sets avoid.
7. Under a title about closed places ("places you miss") each named place is status closed, timeframe past, overall praise. Regret that a place closed ("RIP X", "too bad it closed") is the same fond verdict.
8. "This", "+1" and "second this" take the verdict they agree with, and the aspects it names ("poor quality and expensive": taste and value knock), but only agreement with the verdict on the place, not with a side point. "Great list" endorses only the places a reply names; "great list, but skip X" makes X avoid.
9. Levels are what the commenter thinks now. "Used to be great, now mid": overall knock, trend declined.
10. Not verdicts, opinion "none": a reservation offered, wanted or traded; the commenter speaking for the place ("we", "our menu", "I work there": note "affiliated"); a reason not to go that isn't about eating there (the owner's politics, a chef's persona: note it); awards, stars, review scores and critics, unless the commenter adopts them ("deserves its star"); a joke whose point isn't a verdict (lyrics, innuendo, "that's not a real slice"). A joke whose point is a verdict counts: "shh, don't tell anyone" under a rec is endorse.
11. Sarcasm reverses: "/s" flips its sentence; tourist-strip chains recommended with "lol" are a joke (opinion "none").
12. A remark about a whole category ("$100 steaks are wacky") lowers a named place only when the text applies it to that place.
13. Never soften a complaint because the thread likes the place or the commenter is polite.
</rules>"""

CHECK = """<before_answering>
Each place takes several judgments, so think it through before you answer. Then check every place:
- the text itself refers to it, it is in NYC, and kind says what it is;
- experience is "firsthand" unless the text credits someone else or shows they haven't been;
- every judgment sits in an aspect, a dish or overall, never only in a note, and every dish named is in dishes;
- overall is the bottom line, else the strongest non-wait point; null for a wait-only remark, a fact, a question or an untried reaction; praise for endorse;
- each superlative_praise and extreme_knock rests on its own city-wide superlative or extreme word.
</before_answering>"""

# Short contrastive examples: each shows the method behind the answer for a case
# round 3 got wrong. Invented places only.
EXAMPLES = """<examples>
Illustrative; your output always follows the schema.
<example>
<post_title>Where can I walk in for dinner near Union Sq?</post_title>
<comment_to_extract>Noodle Lab, or Pepper House (get the cumin lamb). Places like Golden Lotus are always booked.</comment_to_extract>
Noodle Lab: firsthand (their own pick; nobody is credited), endorse, wait praise (the question asks about walking in), overall praise.
Pepper House: the same, with dish cumin lamb praise ("get the X").
Golden Lotus: firsthand, stated, wait knock ("always booked"), overall null (a remark only about the wait).
</example>
<example>
<thread_above>[1] another user: Golden Lotus has the best hand-pulled noodles in the city</thread_above>
<comment_to_extract>lol no. noodles were fine, not worth $24 a bowl. their dumplings are to die for tho</comment_to_extract>
Golden Lotus (named_in context): firsthand, stated. Dishes noodles knock ("fine" is lukewarm), dumplings praise ("to die for" ranks nothing). Taste mixed, value knock, note "$24 a bowl". Overall knock: "lol no" and "not worth" are the bottom line. The parent's "best in the city" is not the commenter's.
</example>
<example>
<post_title>Lucky Fold's new soup dumplings (photo)</post_title>
<comment_to_extract>Looks amazing, saving this! My sister swears Twin Lantern has the best dumplings in NYC though</comment_to_extract>
Lucky Fold (named_in context): experience none, opinion none, every level null (an untried reaction).
Twin Lantern: secondhand (credited to the sister), stated, dish dumplings and taste superlative_praise (her city-wide superlative, passed on), overall praise.
</example>
<example>
<post_title>Bagel spots you miss?</post_title>
<comment_to_extract>Kettle & Crumb. These days I get mine at the deli counter in Hilltop Market. And the Chelsea Noodle Lab just closed 💔</comment_to_extract>
Kettle & Crumb: firsthand, stated, overall praise, status closed, timeframe past (a name under a closed-places title).
Hilltop Market: kind deli (the comment is about food it serves), endorse, overall praise.
Noodle Lab: opinion none, location "Chelsea", status null with a note "Chelsea branch closed" (one branch).
</example>
<example>
<comment_to_extract>Brindle is a 6/10 at best, Copperline does the same pasta way better. Be at Saffron Table by 11:30 or you'll wait an hour. Done with Ember House after the owner's rant.</comment_to_extract>
Brindle: stated, taste knock and dish pasta knock (the food comparison), overall knock (6/10).
Copperline: stated, taste praise, overall praise (the winner), dish pasta praise.
Saffron Table: stated, wait knock (you plan around the line), overall null (only the wait).
Ember House: opinion none, every level null, note "boycott: owner's rant" (not about eating there).
</example>
</examples>"""
