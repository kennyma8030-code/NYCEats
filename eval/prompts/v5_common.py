"""Shared text for the v5 prompts (comment and thread mode).

v5 implements schema contract v5. What changed from production's revised
prompt (0d75b20b5f83 / 5b02ac883c80):
  * aspects are seven level WORDS instead of floats. Models land on named
    levels far more consistently, and eval/schema_v5.py (eval-v5-harness) maps
    them back to the floats scoring already reads;
  * reference_only replaces the "food 0.3" sentinel. A bare endorsement keeps
    every aspect null, so no food score is invented for a name nobody judged;
  * questions, stated facts and yardstick comparisons are mentions too, marked
    reference_only, because the board counts how many people talk about a place;
  * three dish lists, so "skip the dumplings" is no longer lost;
  * experience has an "unclear" state, so a bare list stops counting as a visit;
  * price replaces expensiveness, as a word.

Every example uses invented places and comments. None come from the eval set,
and none may ever be added from it. eval/prompts/check_v5.py validates every
example against the contract, because models copy examples over rules.
"""

import json

LEVELS = ["rave", "good", "decent", "mixed", "meh", "bad", "awful"]
ASPECTS = ["food", "value", "service", "atmosphere", "wait"]
PRICES = ["cheap", "moderate", "pricey", "very_pricey"]
EXPERIENCES = ["ate_there", "secondhand", "unclear"]


def mention(name, *, id=None, ref=False, hood=None, neg=False, price=None,
            exp="unclear", liked=(), disliked=(), mentioned=(), desc=(), **asp):
    """One example mention, keys in contract order, compact JSON."""
    m = {} if id is None else {"id": id}
    m.update({
        "restaurant_raw": name,
        "neighborhood_hint": hood,
        "reference_only": ref,
        "aspects": {a: asp.get(a) for a in ASPECTS},
        "is_negated": neg,
        "price": price,
        "experience": exp,
        "dishes_liked": list(liked),
        "dishes_disliked": list(disliked),
        "dishes_mentioned": list(mentioned),
        "descriptors": list(desc),
    })
    return json.dumps(m, ensure_ascii=False, separators=(",", ":"))


def comment_input(title, comment, body=None, parent=None):
    """An example input laid out exactly as production's build_user_message
    renders one (check_v5.py compares the two), so the examples look like
    the real inputs the model is scored on."""
    parts = ["POST TITLE: " + title]
    if body:
        parts.append("POST BODY: " + body)
    if parent:
        parts.append("PARENT COMMENT: " + parent)
    parts.append("COMMENT: " + comment)
    return "\n\n".join(parts)


def output(*mentions):
    if not mentions:
        return '{"mentions":[]}'
    return '{"mentions":[\n' + ",\n".join(mentions) + "]}"


KINDS = """KIND OF MENTION -- decide this FIRST for every mention

A. OPINION. The comment judges the place: the food or a dish, whether it is worth
   the money, the staff, the room, the wait -- or uses a judging word about it
   ("tourist trap", "overrated", "hidden gem", "my favorite", "mid") -- or tells
   people to avoid it.
   -> reference_only false. Score the aspects it judges; the rest stay null.

B. ENDORSEMENT. The place is named as an answer to a request for places to go
   ("best pizza?", "where should I eat in Astoria", "recs for a date spot"),
   with nothing said about it.
   -> reference_only false and EVERY aspect null. Being named is the
   endorsement. Never invent a food level for it.
   EXCEPTION: when the request itself carries a judgment ("most overrated
   spot?", "worst service you've had?", "biggest letdown?"), a bare name
   answering it takes that judgment, scored by the LEVELS table entry for the
   request's own words: "most overrated" -> food "meh" and descriptor
   "overrated"; "worst service" -> service "awful"; "biggest letdown" -> food
   "bad". That makes it kind A.

C. REFERENCE. Everything else that names or points at a place:
   - a question about it: "is Okiku still open?", "has anyone tried Okiku?"
   - a stated fact: "they moved to Court St", "it's cash only btw", "closed"
   - a yardstick: "if you like Okiku you'll love Harbor Fish" (Okiku is the
     yardstick)
   - a passing reference: "I was near Okiku and saw a line"
   - a bare name when nobody asked for places to go ("where did you eat this
     week?", or a post that asks for no recommendation)
   -> reference_only true, every aspect null, is_negated false, dishes_liked
   and dishes_disliked empty. STILL fill neighborhood_hint, price, experience,
   dishes_mentioned and descriptors when the comment STATES them.

Who asked: a top-level comment answers the post. A reply answers the comment it
replies to; if that comment asks nothing, it answers the post."""

FIELDS = """FIELDS (every key on every mention, no extra keys)

restaurant_raw     string. The name VERBATIM, exactly as typed: same spelling,
                   same capitalization, no added words. Never fix spelling,
                   never expand an abbreviation, never add a borough or a
                   "Pizzeria" nobody typed. "lindustrie" stays "lindustrie".
                   When the comment talks about a place without naming it,
                   copy the name exactly as the comment or post it refers to
                   typed it.
neighborhood_hint  string or null. Only when the comment says where THIS place
                   is: "the LES one", "Astoria".
reference_only     true or false. See KIND OF MENTION.
aspects            object with exactly these keys: food, value, service,
                   atmosphere, wait. Each is one LEVEL word, or null.
is_negated         true or false. True ONLY when the comment tells people to
                   avoid the place.
price              "cheap", "moderate", "pricey", "very_pricey", or null.
experience         "ate_there", "secondhand", or "unclear".
dishes_liked       array of strings. [] if none.
dishes_disliked    array of strings. [] if none.
dishes_mentioned   array of strings. [] if none.
descriptors        array of strings: the commenter's own words. [] if none."""

LEVEL_TABLE = """LEVELS -- the only allowed values in aspects, or null

  "rave"    superlative: "best in the city", "best I've ever had", "perfect",
            "the GOAT", "life-changing"
  "good"    clear praise: "so good", "great", "excellent", "love it",
            "my favorite", "my go-to", "swears by it", "hidden gem"
  "decent"  mild praise: "solid", "pretty good", "decent", "not bad"
  "mixed"   explicitly mixed: "hit or miss", "inconsistent", "some good,
            some bad"
  "meh"     mild knock: "mid", "fine", "it's ok", "overrated", "nothing
            special", "not worth the hype", "used to be good"
  "bad"     clear complaint: "bad", "bland", "rude", "slow", "disappointing",
            "letdown", "tourist trap", "skip it"; and for value:
            "overpriced", "not worth the price", "not worth $40"
  "awful"   strong bad experience: "worst", "worst I've had", "got sick",
            "never again", "regretted going", "inedible"

"fine", "it's ok" and "mid" are "meh", NEVER "decent": on Reddit they are a
knock. Use the whole negative half. Do not soften a complaint because the thread
likes the place or because the commenter is polite about it.

null is the default and means NOT MENTIONED. "mixed" never means unmentioned.

ASPECTS
  food        the cooking, including dishes. Generic praise or hate for the
              place with no aspect named ("amazing", "mid", "my favorite",
              "skip it") goes here.
  value       worth the money: "overpriced", "worth every penny", "great deal",
              "not worth the price", "not worth $40". "Cheap" or "pricey"
              alone is price, not value.
  service     the staff.
  atmosphere  the room, the vibe, noise, the crowd.
  wait        the line, getting a table or a reservation, how long food took.

Most comments judge ONE aspect; the other four stay null. NEVER infer one aspect
from another: great food says NOTHING about service, value, the room or the wait.
When the comment gives no verdict on the food overall, food takes the level of
the dishes it judges, whatever it says about value, service, atmosphere or the
wait: liked dishes -> their level; disliked dishes -> their level, at most
"meh"; liked and disliked together -> "mixed". A verdict on the food overall
wins: "great, but skip the dumplings" is food "good"."""

OTHER_FIELDS = """PRICE is how expensive, with no judgment. Fill it only when the comment says
it in words ("cheap", "affordable", "pricey", "expensive", "$$$$"). A dollar
figure with no word about it is null. Being expensive is not bad: "pricey but
worth every penny" is price "pricey" with value "good". "Overpriced" is price
"pricey" with value "bad".

EXPERIENCE
  "ate_there"   they say or clearly imply they ate there: they describe a meal,
                "my go-to", "I used to live next door", or give a verdict in
                their own voice ("it's mid", "so good", "skip it").
  "secondhand"  they say they have not been, or the opinion is someone else's:
                "haven't been", "heard great things", "my friend swears by it",
                "it's on my list".
  "unclear"     neither: a bare name in a list, a question, a fact.

IS_NEGATED is true only when the comment tells people to AVOID the place: "skip
it", "don't bother", "avoid", "go somewhere else", and a bare "not worth it" or
"not worth going" given as advice. Saying what it is not worth is NOT an avoid:
"not worth the price" and "not worth $40" are value "bad"; "not worth the hype"
is food "meh". A bad review is not an avoid: "worst slice I've had, regretted
going" is is_negated false.
Losing a comparison is not an avoid. An avoid instruction that heads a list
applies to EVERY name in that list. An avoid with no reason given is also food
"bad".

DISHES are dishes and drinks the comment names for this place. Each dish goes in
exactly ONE list:
  dishes_liked      praised or recommended: "get the vodka slice", "the
                    pastrami is a must", "got the pastrami and the soup, both
                    great" (both are liked).
  dishes_disliked   judged negatively: "skip the dumplings", "the soup was
                    bland".
  dishes_mentioned  named with no judgment: "I got the vodka slice". Every dish
                    on a REFERENCE mention goes here.

DESCRIPTORS are OPEN VOCABULARY: the commenter's own words for what the place IS
or FEELS like: "red sauce", "hole in the wall", "slice shop", "date spot",
"cash only", "BYOB", "tourist trap", "closed". There is no fixed list. Never
invent words they did not use; the one exception is the judgment from a
judging request ("overrated"). Record what is STATED, not what is ASKED: "is it
still cash only?" gives no descriptor; "it's cash only btw" gives "cash only".
Factual descriptors ("cash only", "BYOB", "slice shop", "closed") are not an
opinion. Judging descriptors ("tourist trap", "overrated", "hidden gem") are an
opinion: kind A, with the aspect scored."""

RULES = """RULES -- the most common misses first

1. A reply that gives an opinion without repeating the name IS a mention of the
   place it replies about: "it's v mid", "hard disagree", "their service is
   terrible". Copy the name from the comment it replies to. This is the most
   common miss, and these replies carry most of the negative opinions.
2. A bare list of names is the most common comment. Every name in it is a
   mention.
3. Single-word names are the ones most often missed: Tong, Luger, Keens,
   Juniors, Angel, Scarr's, Emily, Rubirosa. Catch them.
4. Chains count. Emit McDonald's, Starbucks, Chipotle like any other name;
   filtering happens later.
5. Cuisine headings, neighborhoods, boroughs, streets and dishes are not
   restaurants.
6. The same place named twice in one comment is ONE mention.
7. Sentiment is what the commenter thinks NOW. "Used to be my favorite" is food
   "meh".
8. A closed place is still a mention: reference_only true, "closed" in
   descriptors, every aspect null -- even when the comment remembers how good
   it was. Dishes they remember go in dishes_mentioned.
9. "X over Y" or "X is better than Y": Y lost, so Y is food "meh" unless the
   comment also praises Y. Never is_negated. A place used only as a yardstick
   ("if you like Okiku you'll love Harbor Fish") is a REFERENCE."""
