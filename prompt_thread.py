"""Thread-mode prompt: one call per post instead of one per comment.

Cheaper and better-informed than comment mode. The post body is sent once per
thread rather than once per comment -- a 300-comment thread currently re-sends
the same selftext 300 times -- and the model sees the whole conversation, so a
reply like "Naw, low mid spot OP" resolves from position instead of needing its
parent plumbed in separately.

The cost is attribution: the model must say WHICH comment each mention came
from. Short sequential ids make a wrong one obvious -- anything outside the
range we sent is rejected rather than silently mis-filed against the wrong
restaurant's evidence.
"""

import hashlib

SELFTEXT_LIMIT = 400
MAX_COMMENT_CHARS = 700     # a few comments are essays; they dominate a batch
MAX_DEPTH_INDENT = 6        # deeper chains stop indenting, they do not stop nesting


SYSTEM_PROMPT = """You extract restaurant mentions from a Reddit thread in a New York City food subreddit.

You are given the post, then its comments as an indented tree. Each comment starts with a number in brackets. Indentation means a reply: a comment indented under another is replying to it.

Output ONLY a JSON object. No prose, no code fences:

{"mentions": [ {"id": 3, ...}, {"id": 7, ...} ]}

Every mention carries the bracket number of the comment it came from. Most comments produce nothing; that is normal. A comment naming three places produces three entries with the same id.

NEVER invent an id. Only use numbers that appear in brackets.

FIELDS (every key required on every mention, no extra keys)

id                 integer. The bracket number of the comment this came from.
restaurant_raw     string. The name VERBATIM, exactly as that commenter typed
                   it. Never fix spelling, never fix capitalization, never
                   expand an abbreviation, never add a borough or a "Pizzeria"
                   they did not type. "lindustrie" stays "lindustrie".
neighborhood_hint  string or null. Only when the comment places THIS restaurant
                   somewhere: "the LES one", "Astoria".
dishes             array of strings. Dishes actually named. [] if none.
descriptors        array of strings. OPEN VOCABULARY -- the commenter's own
                   words for what the place IS or FEELS like: "red sauce",
                   "hole in the wall", "slice shop", "cash only", "closed".
                   There is no fixed list. Do not invent words they did not
                   use. [] if none.
aspects            object with exactly these keys: food, value, service,
                   atmosphere, wait. Each is a number from -1 to 1, or null.
expensiveness      number from -1 to 1, or null.
is_firsthand       boolean. Did that person actually go?
is_negated         boolean. Is the comment telling people to avoid the place?

USING THE TREE

A reply is about its parent unless it names something else. "Overrated" indented under a comment praising a place is about that place -- and the mention belongs to the REPLY's id, because it is the replier's opinion.

The post is context, not a source. Never emit a mention for a place named only in the post, unless a comment says something about it.

ASPECTS -- the part that is easiest to get wrong

null is the default. Most comments touch ONE aspect at most; the other four stay null. NEVER infer one aspect from another: great food says NOTHING about service, price, atmosphere, or the wait. And 0 does not mean "unmentioned" -- 0 means explicitly mixed. Unmentioned is null.

  food        the cooking. Generic praise or hate ("my favorite", "mid") here.
  value       worth the money. "Overpriced" is negative value. "Cheap" alone is
              not value, it is expensiveness.
  service     the staff.
  atmosphere  the room, the vibe, noise, the crowd.
  wait        the line, reservations, how long the food took.

Scale: 1 superlative ("best in the city"), 0.6 clear praise, 0.3 named as an answer with no adjective, -0.3 mild knock, -0.6 clear complaint, -1 "never again".

EXPENSIVENESS is a fact with no valence: -1 very cheap, +1 very pricey. Being expensive is not bad. "Pricey but worth every penny" is expensiveness 0.7 with value 0.6. "Overpriced" is expensiveness 0.6 with value -0.7.

IS_FIRSTHAND is false when they are repeating what they heard or read ("heard great things", "my friend swears by it", "it's on my list").

IS_NEGATED is true only when the comment tells people to AVOID the place: skip it, don't bother, not worth it. A negative review is not automatically an avoid instruction, and losing a comparison is not one.

RULES

1. A bare list of names is the MAJORITY case, and every name in it is a mention.
   Being named as an answer to the thread's question is an endorsement: food
   0.3, every other aspect null. Cuisine headings, neighborhoods, boroughs,
   streets and dish names are not restaurants.
2. Single-word names are common and are the ones most often missed: Tong,
   Luger, Keens, Juniors, Angel, Scarr's, Emily, Rubirosa. Catch them.
3. Chains count. Emit McDonald's, Starbucks, Chipotle like any other name.
4. The same place named twice in ONE comment is ONE mention.
5. Sentiment is what the commenter thinks NOW, not what they used to think.
6. A closed place is still a mention: every aspect null, "closed" in descriptors.
7. An avoid instruction heading a list applies to EVERY name in that list.
   "I'd skip everyone you mentioned. Lucali, Di Fara, L&B" is three mentions,
   all with is_negated true. This is the single easiest thing to get wrong.

EXAMPLE

POST: Best pizza in Brooklyn?

[1] u/ann: L'industrie, and Lucali if you can stand the wait
  [2] u/bob: lucali is overrated
    [3] u/ann: hard disagree
[4] u/cal: Skip both. Di Fara and F&F.

{"mentions":[
{"id":1,"restaurant_raw":"L'industrie","neighborhood_hint":null,"dishes":[],"descriptors":[],"aspects":{"food":0.6,"value":null,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"is_firsthand":true,"is_negated":false},
{"id":1,"restaurant_raw":"Lucali","neighborhood_hint":null,"dishes":[],"descriptors":[],"aspects":{"food":0.5,"value":null,"service":null,"atmosphere":null,"wait":-0.5},"expensiveness":null,"is_firsthand":true,"is_negated":false},
{"id":2,"restaurant_raw":"lucali","neighborhood_hint":null,"dishes":[],"descriptors":["overrated"],"aspects":{"food":-0.5,"value":null,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"is_firsthand":true,"is_negated":false},
{"id":4,"restaurant_raw":"Di Fara","neighborhood_hint":null,"dishes":[],"descriptors":[],"aspects":{"food":0.3,"value":null,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"is_firsthand":true,"is_negated":false},
{"id":4,"restaurant_raw":"F&F","neighborhood_hint":null,"dishes":[],"descriptors":[],"aspects":{"food":0.3,"value":null,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"is_firsthand":true,"is_negated":false}]}

Comment 3 names nothing, so it produces nothing. Comment 4 says "Skip both" about places already named above, but only the NEW names it contributes are emitted under id 4.
"""

PROMPT_HASH = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]


def build_message(title, selftext, nodes):
    """Render a thread as an indented tree.

    nodes: (short_id, depth, author, body) in reading order.

    Indentation carries the reply structure, so parent ids never appear in the
    text. The model reads position rather than resolving references across the
    prompt, which is both more reliable and fewer tokens.
    """
    parts = [f"POST: {title}"]
    if selftext:
        body = " ".join(selftext.split())
        if len(body) > SELFTEXT_LIMIT:
            body = body[:SELFTEXT_LIMIT] + " ..."
        parts.append(body)
    parts.append("")
    for sid, depth, author, text in nodes:
        flat = " ".join((text or "").split())
        if len(flat) > MAX_COMMENT_CHARS:
            flat = flat[:MAX_COMMENT_CHARS] + " ..."
        parts.append(f"{'  ' * min(depth, MAX_DEPTH_INDENT)}[{sid}] "
                     f"u/{author or '?'}: {flat}")
    return "\n".join(parts)
