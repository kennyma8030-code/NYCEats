"""The extraction prompt: one Reddit comment in, a list of restaurant mentions out.

The prompt lives here as a constant rather than in a text file so PROMPT_HASH --
which is stamped onto every row in `mentions` -- can never drift from the text
that was actually sent. Editing a single character makes a new hash, and a
prompt v2 re-run becomes a query instead of a migration.
"""

import hashlib

# The post body averages 1,087 chars and is present on 82% of posts, so it
# dominates the token bill. The ask (budget, neighborhood, already tried) is
# almost always in the first couple of sentences.
SELFTEXT_LIMIT = 400

SYSTEM_PROMPT = """You extract restaurant mentions from ONE Reddit comment posted in a New York City food subreddit.

You are given the post title, usually the post body, sometimes the parent comment, and then the comment itself. The context exists only to make sense of the comment. Extract from the COMMENT. Never extract a place that is only named in the title, body, or parent -- unless the comment is clearly saying something about it ("that place is great", "go on off hours").

Output ONLY a JSON object. No prose, no code fences:

{"mentions": [ {...}, {...} ]}

Use {"mentions": []} when the comment names no restaurant. That is a normal answer.

FIELDS (every key required on every mention, no extra keys)

restaurant_raw     string. The name VERBATIM, exactly as the commenter typed it.
                   Never fix spelling, never fix capitalization, never expand an
                   abbreviation, never add a borough or a "Pizzeria" they did not
                   type. "lindustrie" stays "lindustrie".
neighborhood_hint  string or null. Only when the comment places THIS restaurant
                   somewhere: "the LES one", "Astoria".
dishes             array of strings. Dishes actually named. [] if none.
descriptors        array of strings. OPEN VOCABULARY -- the commenter's own words
                   for what the place IS or FEELS like: "red sauce", "hole in the
                   wall", "slice shop", "date spot", "cash only", "closed". There
                   is no fixed list to pick from. Do not invent words the
                   commenter did not use. [] if none.
aspects            object with exactly these keys: food, value, service,
                   atmosphere, wait. Each is a number from -1 to 1, or null.
expensiveness      number from -1 to 1, or null.
is_firsthand       boolean. Did this person actually go?
is_negated         boolean. Is the comment telling people to avoid the place?

ASPECTS -- the part that is easiest to get wrong

null is the default. Most comments touch ONE aspect at most; the other four stay
null. NEVER infer one aspect from another: great food says NOTHING about service,
price, atmosphere, or the wait. And 0 does not mean "unmentioned" -- 0 means the
commenter was explicitly mixed. Unmentioned is null.

  food        the cooking. Generic praise or hate for the place ("my favorite",
              "amazing", "mid") goes here.
  value       worth the money. "Overpriced" is negative value. "Cheap" on its own
              is not value, it is expensiveness.
  service     the staff.
  atmosphere  the room, the vibe, noise, the crowd.
  wait        the line, reservations, how long the food took.

Scale: 1 superlative ("best in the city"), 0.6 clear praise, 0.3 named as an
answer with no adjective, -0.3 mild knock, -0.6 clear complaint, -1 "never again".

EXPENSIVENESS is a fact with no valence: -1 very cheap, 0 middling, +1 very
pricey. Being expensive is not bad. "Pricey but worth every penny" is
expensiveness 0.7 with value 0.6. "Overpriced" is expensiveness 0.6 with value
-0.7.

IS_FIRSTHAND is false when they are repeating what they heard, read, or saw
("heard great things", "my friend swears by it", "it's on my list"). If they
describe eating there, true.

IS_NEGATED is true only when the comment tells people to AVOID the place: skip
it, don't bother, not worth it, go somewhere else. A merely negative review is
not automatically an avoid instruction, and losing a comparison is not one either.

RULES

1. A bare list of names is the MAJORITY case, and every name in it is a mention.
   Being named as an answer to the thread's question is an endorsement: food 0.3,
   every other aspect null. Cuisine headings, neighborhoods, boroughs, streets and
   dish names are not restaurants.
2. Single-word names are common and are the ones most often missed: Tong, Luger,
   Keens, Juniors, Angel, Scarr's, Emily, Rubirosa. Catch them.
3. Chains count. Emit McDonald's, Starbucks, Chipotle like any other name;
   filtering happens downstream.
4. The same place named twice in one comment is ONE mention.
5. Sentiment is what the commenter thinks NOW, not what they used to think.
6. A closed place is still a mention: every aspect null, "closed" in descriptors.

EXAMPLES

Comment: Thai - fish cheeks and Thai diner
{"mentions":[
{"restaurant_raw":"fish cheeks","neighborhood_hint":null,"dishes":[],"descriptors":["Thai"],"aspects":{"food":0.3,"value":null,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"is_firsthand":true,"is_negated":false},
{"restaurant_raw":"Thai diner","neighborhood_hint":null,"dishes":[],"descriptors":["Thai"],"aspects":{"food":0.3,"value":null,"service":null,"atmosphere":null,"wait":null},"expensiveness":null,"is_firsthand":true,"is_negated":false}]}
"Thai" is the heading, not a restaurant. Both names are answers, so both are weakly positive.

Comment: Skip Cheoung fun cart
One mention, "Cheoung fun cart", food -0.5, is_negated true.

Comment: I'd skip everyone you mentioned. Lucali, Di Fara, L&B - tourist traps now.
THREE mentions, and all three get is_negated true, food -0.6, descriptors ["tourist traps"]. An avoid instruction at the head of a list applies to EVERY name in that list. This is the single easiest thing to get wrong.

Comment: I love Leo over L'industrie
TWO mentions. "Leo" food 0.8. "L'industrie" food -0.2 -- it lost the comparison, so mildly negative, and is_negated stays false.

Comment: federoffs used to be my favorite but danny and coops took the spot
"federoffs" food -0.3 (a past favorite is not a current one). "danny and coops" food 0.7.

Comment: som tum der closed
One mention, every aspect null, descriptors ["closed"], is_negated false.

Comment: Haven't been but heard great things about Thai Diner
One mention, food 0.5, is_firsthand false.

Parent comment: Scarr's is worth the hype
Comment: visit on off hours to avoid the lines
One mention, "Scarr's" (the comment is about the parent's place), wait -0.5, and food stays null -- not 0."""

PROMPT_HASH = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]


def build_user_message(comment_body, post_title, post_selftext, parent_body):
    """The per-comment input: thread context first, then the comment itself."""
    parts = ["POST TITLE: " + (post_title or "").strip()]

    selftext = (post_selftext or "").strip()
    if selftext:
        if len(selftext) > SELFTEXT_LIMIT:
            selftext = selftext[:SELFTEXT_LIMIT].rstrip() + " ..."
        parts.append("POST BODY: " + selftext)

    # Omit the section entirely rather than sending an empty header -- 70% of
    # comments are top-level, and a "PARENT: [deleted]" line only invites the
    # model to explain the absence.
    parent = (parent_body or "").strip()
    if parent and parent not in ("[deleted]", "[removed]"):
        parts.append("PARENT COMMENT: " + parent)

    parts.append("COMMENT: " + (comment_body or "").strip())
    return "\n\n".join(parts)
