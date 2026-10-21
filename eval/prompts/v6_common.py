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
Every food or drink place in New York City the text names or refers to: restaurants, bars, cafes, bakeries, delis, food trucks and carts, chains, food halls and night markets (the hall and each named stall). That includes names in a list (the most common case; one-word names like Brindle or Ember are easy to miss), places not yet tried, closed places, both sides of a comparison, a benchmark or style ("a Pepper House-style burger"), places used as landmarks, places only asked about or named in passing, and a place named only to identify a person ("the Golden Lotus chef": a mention with opinion "none").
A vendor nobody names but the text pins down by what it sells and where ("the empanada lady by the Corona plaza fountain", "the arepa cart on 41st and 9th") is a mention named by that description. A place with no name and no fixed spot ("a dumpling spot near the bridge") is not.
Stores and markets: a specialty food shop (pickles, cheese, an Italian market hall), a gourmet grocer's prepared food or bakery case, a bazaar or market, and a bakery named as the supplier other places carry take a food kind (deli, bakery, cafe, market_stall, food_hall) when the text is about the food it serves; kind grocery only when the text is about grocery shopping (stocking up, hunting an ingredient, meat or cheese by the pound). A packaged product sold in stores, an entertainment venue or a company named as a food source is extracted with that kind; code keeps those kinds out of the counts.
Not mentions: cuisines, dishes, neighborhoods, streets, parks, museums, people (chefs, critics, influencers, users; but "dinner at Chef Marco's" names a restaurant), apps (Resy, Beli, delivery apps), places outside the five boroughs and foreign branches ("Golden Lotus in Tokyo"; the NYC one gets only what is said about it), a name the commenter takes back, and a reply that neither names nor judges a place.
A place named twice is one mention. A rename ("Golden Lotus, formerly Lotus House") is one mention under the current name, the old name in a note. A room, counter or tasting menu inside a restaurant is part of that restaurant's mention.
</what_counts>"""

FIELDS = """<fields>
Write each place's fields in this order: what is said first, the verdict last.
name        As typed, even shortened, misspelled or as initials ("Copper", "goldn lotus", "GLN"). Only for a place the text doesn't name, copy the name from the context.
named_in    "comment", or "context" when the name was copied from the context.
kind        Counted: restaurant (also slice shops and pop-ups), bar (also a bar or supper club with music), cafe (also coffee, tea, bubble tea, juice, ice cream and dessert shops), bakery, deli (also bodegas, sandwich counters, specialty food shops), truck_or_cart, market_stall (a stall in a market or hall), food_hall (the whole hall or market). Not counted: grocery (a store the text is grocery shopping at), brand (a packaged product sold in stores), venue (a club, theater or game bar named for something other than its food or drink), company (a restaurant group or other business), other (anything that is not a food place). Anything serving food or drink always gets a counted kind.
location    Where the text places THIS place or branch ("the Astoria one", "on Fifth near the park"), else null.
experience  Whose opinion it is, not whether a visit is described. "firsthand" (the default for a verdict or a pick): anything in their own voice: a visit, a pick, a list item, a tip or hedge that carries a verdict or a pick ("I think X has it"), a reply about someone else's place. "secondhand" only when the text credits someone else ("my cousin raves about it", "I hear it's good", a pick or comparison they only pass on: "folks here say A beats B"). "none": a question, a place they haven't tried, and every mention whose opinion is "none" (a fact, news, a story, a name in passing), even when hedged ("I think they moved").
dishes      Every dish or drink named for this place: {"dish", "level" (null if only named), "avoid" (true for "skip the X")}. "Get / try the X", "X for the Y" and a dish heading over picks ("Dumplings: A, B") are praise. A plain word for what the place sells is a dish ("their dumplings never change"). In a dish comparison ("their noodles beat their dumplings") the losing dish gets a knock. One dish named two ways is one entry.
notes       What no other field holds, as {"about": short label, "text": short paraphrase}: tips ("when to go"), facts ("cash only"), prices ("$24 a bowl"), comparisons, rank order, the detail behind a verdict ("portions tiny"), and reasons that set no level ("boycott", a business decision they second-guess, fake reviews, a fee to pay as a workaround). A note never replaces a level: the judgment goes in an aspect, a dish or overall.
aspects     {taste, value, service, atmosphere, wait}: each a LEVEL from what is said about that side, else null. Never copied from overall. A fact given only as the reason for a verdict sets that verdict's aspect.
              taste: the food and drink, including how it looks. A verdict on a dish sets taste ("that scallion pancake rules": praise), and so does a dish praised only by "get the X" or by the question's framing. Mixed only when praise and complaints about the food weigh about evenly; one dish knocked among several praised keeps taste praise; praise as the lone exception ("only good for the egg tarts") is a taste knock with that dish praise. Healthiness is a tag, not taste.
              value: a judgment of worth ("a steal", "not worth $30", surprise fees and card surcharges). The word before "for the price" decides: "generous for the price" praise, "skimpy for the price" knock. A price word or figure alone ("cheap", "a bit spendier", "$$$", "$24 a bowl") is price or a note, not value; a price said as a complaint ("absurdly priced", "a rip-off") is value, not price. A complaint only about what a dish costs is value; it sets neither taste nor the dish.
              service: staff, and how the place is run (policies: "tasting menu only", "no substitutions").
              atmosphere: room, vibe, noise, crowd, seating ("hardly anywhere to sit"). A place called fun, lively or "buzzing and crowded" as praise is atmosphere praise.
              wait: lines, getting a table, slow food, selling out. A knock when you must plan around it ("show up before opening", "set an alarm for when reservations drop", "they run out by early afternoon", "the line wraps the block"); praise when getting in is easy ("seated in five minutes", "plenty of open seats mid-afternoon").
            Fit for one person or occasion ("too formal for a toddler", "a bit loud for a first date") is a note or tag, not a level.
opinion     "none": a fact, a question (including surprise at a change: "they don't make the old recipe anymore??"), business news (closing, rent), a story about someone's occasion there, a name in passing or given as an example, an untried reaction. "endorse": a pick offered with no word of judgment: a bare name, "try X", "get the Y at X", "X for the Y", "X is your safest pick", "they have it at X", "+1" under a rec. "stated": any word judging the place or its food, even one ("great burger too"), and a bare name answering a negative question, which carries its knock.
overall     LEVEL, decided last. The commenter's bottom line ("worth it", "skip it", "not worth the trip", "I'd go back", "my favorite"), even against points the other way; a pick that answers the question is its bottom line even when one dish disappoints. Without one, a lone taste, value, service or atmosphere verdict sets it; several, the strongest non-wait point, usually the food. The wait never sets or lowers overall: a remark only about the wait leaves overall null, and "a personal favorite, though I'd never wait in that line again" is overall praise with wait knock. A place recommended to the asker is endorse, overall praise, even when all they say is how to get in ("try Pepper House, they hold seats for walk-ups"). null for a fact, a question or an untried reaction; "praise" for endorse. A complaint about what a place now sells lowers overall, not taste. A superlative about one dish makes the dish and taste superlative_praise, overall only if said of the place or the dish is what it sells.
avoid       true only when the text tells readers to skip the place itself: "skip it", "don't bother", "tourist trap", "just cook it yourself". false for a bad review alone, "I won't go back", a swap ("go to Y instead"), a skip aimed at some readers ("skip it unless you're nearby"), one branch, or an insult with no instruction.
timeframe   "past" when the place is closed, or the text ties the verdict to an earlier time ("it was better before", "it was great back in 2015, no idea now", "back at their old address"). A dated or old visit ("in 2022", "years ago") is "current" unless the text says the place may have changed.
trend       "declined" or "improved" only when the text says the place's quality changed, including one dish of theirs ("the noodles slipped"). Not for closing, fewer customers, a lost star, a prediction, or a change in booking, prices or service alone.
status      The place under that name: "closed" ("closed", "RIP X"), "moved", "opened" (new or reopened), else null. One branch closing, opening or moving, a temporary closure or a rumored reopening is null, with the branch in location and a note.
price       Only an absolute price word: "very_cheap", "cheap", "moderate", "expensive", "very_expensive", else null. Not a dollar figure, not "cheaper than X", not "overpriced" (that is value).
tags        The commenter's words for what the place is or is for, as someone would search: cuisine, format, occasion, diet, payment ("sichuan", "slice shop", "date night", "healthy", "byob"). [] if none.
</fields>"""

SCALE = """<levels>
LEVEL is one of these, or null when not said:
  superlative_praise  ONLY a superlative ranking this place or dish against the whole city or wider: "best in the city", "best X I've ever had", "my favorite in NYC", "the best meal I've had anywhere", "nothing in NYC comes close".
  praise              any real yes, mild or wild: "decent", "solid", "good for what it is", "good", "great", "amazing", "to die for", "unreal", "god tier", "10/10", "my favorite", "best on my block", "my go-to", "best I've had lately", "a must", "get the X".
  mixed               praise and a complaint about the same side, weighed evenly, with no bottom line for it: "hit or miss", "lovely room, though the AC dripped on us", "great value, though the portions shrank". Never for lukewarm words.
  knock               any complaint, mild or strong: "fine", "ok", "not bad", "meh", "mid", "average", "mediocre", "nothing special", "not worth the trip", "overrated", "overpriced", "disappointing", "bland", "gross", "rude", "terrible", "awful", "sucks", "never again", "regretted going", "the line is insane".
  extreme_knock       ONLY an extreme: "worst I've ever had", "worst in the city", "inedible", "disgusting", "got sick", "food poisoning", "avoid at all costs".
Emphasis, caps, swearing, emoji and stacked knocks never raise a level. Scores: 8/10 and up is praise, anything lower a knock.
</levels>"""

RULES = """<rules>
1. A complaint put as a fact is a judgment: "impossible to book" (wait knock), "the broth tastes like bouillon now" (taste knock). opinion "none" is only for facts and questions with nothing judged; a price or a dollar figure on its own is a fact, not a complaint.
2. Every complaint lowers a level: its aspect, a dish, or overall when no aspect fits. Hygiene (a bad grade, violations, roaches) is overall, not service, with a note. Getting sick is overall extreme_knock; taste stays null unless flavor is judged. Conduct a diner can't see at the table (fake reviews, lawsuits) is a note with no level.
3. Not tried: someone who says or shows they haven't been ("the photo looks incredible", "bookmarking it", "dying to go", "thanks, will report back", "heading there today for the first time", "exactly what I feared") gives no verdict: experience "none", opinion "none", every level null. Untried wins: praise or a complaint about something they only saw (a photo, a video, a menu) sets no level; keep it as a note. A reaction to what the post or another comment reports ("absolutely vile", "neat that they do that", "wow, $40?") with nothing from their own visit is the same. But passing on what someone told them is secondhand with that verdict ("haven't been, but my cousin loves it"), and "haven't gone lately" or "going again" means they have been. "Looks like there's a table at 8" is a fact, not an untried reaction.
4. Lukewarm stays a knock in a defense ("honestly it's passable") and about price ("priced so-so"). "I enjoy it, but the price kills it" is a knock: the bottom line wins. An excuse with no verdict ("they're short-staffed, give them a break") is opinion "none".
5. Comparisons. The loser gets a knock on what was compared: food → taste, price or portions → value, line or booking → wait, the whole place ("I prefer A over B", "go to A instead" answering "is B worth it?") → overall. It stays praise when both are called good ("A beats B, though both are worth a visit"). "As good as X" and "X-level" praise X. "Close, but not A" makes the other place the loser. No loser without a named winner. A swap for fit compares nothing, even with "similar food but more relaxed" or "closer to your hotel": the other place gets no level. A low-bar winner ("even Burger Barn is better") gets no level. Ranked picks ("A, then B, then C") are all praise, the order in a note. A comparison the commenter only reports is secondhand.
6. A bare answer takes from the question its polarity, the dish it asks about, and the aspect it asks about when it asks about that aspect, never its superlative. Under "spots that take walk-ins?" each pick is endorse with wait praise; under "best egg tart?" each pick is endorse with that dish and overall praise, not superlative_praise; under "worst meal you've had?" each name is opinion "stated" with overall knock. A worry in the post ("we struck out on reservations everywhere") is not a question about the wait. A heading works the same way ("Top picks:", "Skip these:"). A place offered as an answer is a pick even when only facts are given about it (hours, what it serves); names given as examples, not as answers, are opinion "none". The commenter's own words outrank the framing, and framing never sets avoid.
7. A whole place closing: under a title about closed places ("places you miss") each named place is stated, status closed, timeframe past, overall praise, and regret that a place closed for good ("RIP X", "shame it shut down") is the same fond verdict. One branch closing, even with regret, is no verdict: opinion "none", status null, the branch in location and a note.
8. "This", "+1" and "second this" take the verdict they agree with, and the aspects it names ("bland and overpriced": taste and value knock), but only agreement with the verdict on the place, not with a side point. "Great list" endorses only the places a reply names; "great list, but skip X" makes X avoid. A pick passed on from someone else ("my friend swears by Y") is secondhand endorse, overall praise.
9. Levels are what the commenter thinks now. "It was great years ago, now it's forgettable": overall knock, trend declined.
10. Not verdicts, opinion "none": a reservation offered, wanted or traded; the commenter speaking for the place ("we", "our menu", "I work there": note "affiliated"); a reason not to go that isn't about eating there (the owner's politics, a business deal, a chef's persona: note it), though a jab at the food or service in the same comment still counts; second-guessing a business decision (note it); awards, stars, review scores and critics, unless the commenter adopts them ("earned that star"); a joke whose point isn't a verdict (lyrics, "that isn't real ramen"). A joke whose point is a verdict counts: "keep this one quiet, people" under a rec is endorse.
11. Sarcasm reverses: "/s" flips its sentence; tourist-strip chains recommended with "lol" are a joke (opinion "none").
12. A remark about a whole category ("$90 omakase everywhere is a scam") lowers a named place only when the text applies it to that place.
13. Never soften a complaint because the thread likes the place or the commenter is polite.
</rules>"""

CHECK = """<before_answering>
Each place takes several judgments, so think it through before you answer. Then check every place:
- the text itself refers to it, it is in NYC, and kind says what it is (a place serving food or drink is never "other");
- experience is "firsthand" for a verdict or pick in their own voice, "secondhand" only with a credit, and "none" for a question, a bare fact, any opinion-"none" mention or a place they haven't tried;
- every judgment sits in an aspect, a dish or overall, never only in a note, and every dish named is in dishes;
- overall is the bottom line, else the strongest non-wait point; the wait never sets it; null for a fact, a question or an untried reaction; praise for endorse; a knock for a bare name answering a negative question (opinion "stated");
- each superlative_praise and extreme_knock rests on its own city-wide superlative or extreme word.
</before_answering>"""

# Short contrastive examples: each shows the method behind the answer for a case
# round 3 got wrong. Invented places only.
EXAMPLES = """<examples>
Illustrative; your output always follows the schema.
<example>
<post_title>Spots that take walk-ins for dinner near Union Sq?</post_title>
<comment_to_extract>Noodle Lab, or Pepper House (get the cumin lamb). Golden Lotus is always booked though.</comment_to_extract>
Noodle Lab: firsthand (their own pick; nobody is credited), endorse, wait praise (the question asks about walking in), overall praise.
Pepper House: the same, with dish cumin lamb praise and taste praise ("get the X").
Golden Lotus: firsthand, stated, wait knock ("always booked"), overall null (a remark only about the wait, and not a pick).
</example>
<example>
<thread_above>[1] another user: Golden Lotus does the best knife-cut noodles in the city</thread_above>
<comment_to_extract>lol no. noodles were fine, not worth $24 a bowl. their dumplings are unreal tho</comment_to_extract>
Golden Lotus (named_in context): firsthand, stated. Dishes noodles knock ("fine" is lukewarm), dumplings praise ("unreal" ranks nothing). Taste mixed (one dish each way), value knock, note "$24 a bowl". Overall knock: "lol no" and "not worth" are the bottom line. The parent's superlative belongs to the parent.
</example>
<example>
<post_title>Lucky Fold's new soup dumplings (photo)</post_title>
<comment_to_extract>Photo looks incredible, bookmarking this one! My sister swears Twin Lantern has the city's top soup dumplings, period</comment_to_extract>
Lucky Fold (named_in context): experience none, opinion none, every level null (an untried reaction).
Twin Lantern: secondhand (credited to the sister), stated, dish soup dumplings and taste superlative_praise (her city-wide superlative, passed on), overall praise.
</example>
<example>
<post_title>Bagel spots you miss?</post_title>
<comment_to_extract>Kettle & Crumb, RIP. Now I grab mine from the bakery case inside Hilltop Market. The Chelsea Noodle Lab just closed too 💔</comment_to_extract>
Kettle & Crumb: firsthand, stated, overall praise, status closed, timeframe past (a whole place, under a closed-places title).
Hilltop Market: kind bakery (food it serves to eat, not grocery shopping), endorse, overall praise.
Noodle Lab: experience none, opinion none, every level null, location "Chelsea", status null, note "Chelsea branch closed" (one branch closing is no verdict, even with 💔).
</example>
<example>
<post_title>Most overrated restaurant around?</post_title>
<comment_to_extract>Saltbox</comment_to_extract>
Saltbox: firsthand, stated (a bare name answering a negative question carries its knock), overall knock, avoid false (framing never sets avoid).
</example>
<example>
<comment_to_extract>Brindle is a 6/10 at best, Copperline does the same pasta way better. Get to Saffron Table before it opens or you'll wait an hour. Done with Ember House after the owner's rant.</comment_to_extract>
Brindle: stated, taste knock and dish pasta knock (the food comparison), overall knock (6/10).
Copperline: stated, taste praise, overall praise (the winner), dish pasta praise.
Saffron Table: stated, wait knock (you plan around the line), overall null (only the wait).
Ember House: experience none, opinion none, every level null, note "boycott: owner's rant" (not about eating there).
</example>
</examples>"""
