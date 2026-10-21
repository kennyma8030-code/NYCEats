"""Shared text for the rubric_v1 prompts (comment and thread mode).

Differences from production's revised prompt (0d75b20b5f83 / 5b02ac883c80):
  * a 7-level scale with exactly seven allowed values, each level defined, so
    a score carries more than "liked it" / "loved it";
  * every named place counts, including questions, "haven't been yet" and
    closed places -- the board counts how many people are talking;
  * dish_sentiment: per-dish verdicts, because "skip the X" is one of the
    strongest signals a reader acts on;
  * value_complaint: overpriced / not worth it, flagged explicitly;
  * descriptors carry the words someone would search: cuisine, dish, occasion.

Examples use invented places and comments; none come from the eval set.
"""

FIELDS = """FIELDS (every key required on every mention, no extra keys)

restaurant_raw     string. The name VERBATIM, exactly as typed. Never fix spelling
                   or capitalization, never expand an abbreviation, never add a
                   borough or a "Pizzeria" nobody typed. When the comment talks
                   about a place without naming it ("it's v mid", "their service
                   is terrible", "hard disagree"), copy the name from the comment
                   it replies to (or the post) that does.
neighborhood_hint  string or null. Only when the comment places THIS restaurant
                   somewhere: "the LES one", "Astoria".
dishes             array of strings. Dishes or drinks actually named. [] if none.
dish_sentiment     array of {"dish": string, "level": LEVEL or null, "avoid": boolean},
                   one entry per dish the comment JUDGES or RECOMMENDS. "get the
                   spicy cumin noodles" is level 0.67; "skip the dumplings" is
                   avoid true, level -0.67; "the burger is overrated" is -0.33.
                   A dish only named, with nothing said about it, gets level null.
                   [] if no dish is named.
descriptors        array of strings. The commenter's OWN words for what the place
                   is or is for -- the words someone would search to find it:
                   cuisine ("Sichuan", "omakase"), format ("slice shop", "food
                   truck", "BYOB"), occasion ("date night", "birthday", "group
                   dinner"), price feel ("cheap eats"), and "closed" when closed.
                   Lowercase is fine. Never invent words they did not use. [] if none.
aspects            object with exactly these keys: food, value, service,
                   atmosphere, wait. Each is a LEVEL or null.
expensiveness      LEVEL or null. Price level, not a judgement: -1 very cheap ...
                   1 very pricey.
value_complaint    boolean. True when the comment says the place, or something on
                   its menu, is overpriced, a rip-off, or not worth the money.
is_firsthand       boolean. Did this person actually go?
is_negated         boolean. Is the comment telling OTHER people to avoid the place?"""

SCALE = """LEVELS -- use exactly these seven numbers, or null

   1     superlative: "best in the city", "life-changing", "the GOAT"
   0.67  clear praise: "so good", "excellent", "my go-to", "get the X"
   0.33  mild positive, or simply named as an answer with nothing said
   0     explicitly mixed: "hit or miss", "some good some bad", "fine but"
  -0.33  mild knock: "mid", "fine", "overrated", "not worth the hype"
  -0.67  clear complaint: "bad", "overpriced", "rude", "bland", "not good"
  -1     strong bad experience: "worst I've had", "got sick", "never again",
         "regretted going", "inedible"

null is the default and means NOT MENTIONED. 0 is not "unmentioned"; 0 means the
commenter was explicitly mixed. Most comments touch one aspect; the rest stay
null. NEVER infer one aspect from another: great food says nothing about the
service, the price, the room, or the wait.

  food        the cooking. Generic praise or hate for the place ("my favorite",
              "amazing", "mid") goes here.
  value       worth the money. "Overpriced" is value -0.67 and value_complaint
              true. "Cheap" alone is expensiveness, not value.
  service     the staff.
  atmosphere  the room, the vibe, noise, the crowd.
  wait        the line, getting a table or reservation, how long food took.
              "Easy to walk in" is wait 0.33; "impossible reservation" -0.67.

Negatives are what readers act on. Use the whole negative half of the scale and
do not soften a complaint because the thread likes the place or because the
commenter is polite. A complaint about one dish is a dish_sentiment entry even
when the commenter likes the place overall."""

RULES = """WHAT COUNTS AS A MENTION

Every restaurant, cafe, bakery, bar, food hall stall, food truck, or chain the
comment NAMES or clearly refers to -- including:
  * a bare name in a list (the most common case);
  * a question about a place ("is Golden Lotus still good?");
  * a place the commenter has not been to ("on my list", "heard it's great"):
    is_firsthand false, aspects null unless they repeat an opinion;
  * a closed place: every aspect null, descriptors include "closed", even when
    they remember it fondly;
  * a place used as a comparison ("like Ray's but better").
NOT mentions: cuisines, dishes on their own, neighborhoods, streets, grocery
stores and supermarkets, apps and delivery services, and places outside New York
City.

RULES

1. A name given as an answer with nothing said about it: food 0.33, everything
   else null. That default is ONLY for a name with nothing said. If the comment
   says anything -- the line, the price, a dish, the room -- score what it says
   and leave food null unless the food is judged.
2. A list under a heading inherits the heading: "My favorites:" makes every
   name food 0.67; "Avoid:" makes every name is_negated true and food -0.67.
3. Single-word names are the ones most often missed: Tong, Luger, Keens,
   Angel, Emily. Catch them.
4. The same place named twice in one comment is ONE mention.
5. Sentiment is what the commenter thinks NOW. "Used to be my favorite" is -0.33.
6. Losing a comparison ("I prefer X over Y") is mildly negative for Y (-0.33),
   not an instruction to avoid it."""

EXAMPLES_COMMENT = """EXAMPLES (invented places)

Comment: Sichuan - Golden Lotus and Pepper House
Two mentions, both food 0.33, descriptors ["Sichuan"]. "Sichuan" is a heading, not a place.

Comment: Pepper House is great but skip the dumplings, and $28 for noodles is a joke
One mention: food 0.67, value -0.67, value_complaint true, dishes ["dumplings", "noodles"],
dish_sentiment [{"dish":"dumplings","level":-0.67,"avoid":true},{"dish":"noodles","level":null,"avoid":false}].

Parent comment: Marlowe's is my go-to brunch spot
Comment: honestly mid, and the wait is insane
One mention, "Marlowe's" (named from the parent): food -0.33, wait -0.67.

Comment: Has anyone been to Okiku since it reopened?
One mention, "Okiku": every aspect null, is_firsthand false.

Comment: Avoid: Sal's Slices, Bridge Diner. Both tourist traps now.
Two mentions, each is_negated true, food -0.67, descriptors ["tourist traps"].

Comment: got food poisoning from Harbor Fish last month, never again
One mention: food -1, is_negated false (a bad experience, not an instruction).

OUTPUT, for "Pepper House is great but skip the dumplings":
{"mentions":[{"restaurant_raw":"Pepper House","neighborhood_hint":null,"dishes":["dumplings"],"dish_sentiment":[{"dish":"dumplings","level":-0.67,"avoid":true}],"descriptors":[],"aspects":{"food":0.67,"value":null,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"value_complaint":false,"is_firsthand":true,"is_negated":false}]}"""
