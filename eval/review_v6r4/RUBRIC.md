# Judging Haiku's v6 round-4 extraction: rubric

You are judging how well a small model (Claude Haiku 5.5) turned r/FoodNYC
comments into structured restaurant opinions. You read each comment
yourself, write your own answer **before** looking at Haiku's, then compare
the two field by field and decide what is right. Your reading is the
reference, so read carefully; and when you disagree with Haiku, re-read the
comment and be willing to find that Haiku was right.

These rules are the owner's final decisions. The model's prompt
(`eval/prompts/v6_common.py`, round 4) states the same rules, so where they
decide a case, follow them even if you'd read it differently. Where they
don't, say so in `rule_questions`.

The prompt names levels by their test; you use the owner's names. They map
one to one:

| owner's level (you write) | prompt's label |
|---|---|
| very_positive | superlative_praise |
| positive | praise |
| neutral | mixed |
| negative | knock |
| very_negative | extreme_knock |

Haiku's output in each item is already converted to the owner's names.

## What you get per item

1. **What the model saw**: the round-4 input. The post title, the post body
   (cut at 1,200 characters), up to five comments above this one (the
   parent at up to 1,500 characters, the others at 300), labelled `OP`,
   `you, earlier` (the commenter's own earlier comment) or `another user`,
   and the comment. `author="you"` on the post means the commenter wrote the
   post. A `<quote>` in the comment is someone else's words. Haiku saw
   exactly this and nothing more.
2. **Wider thread context**: the full post, every ancestor, and the replies.
   Haiku did not see this. Use it to understand the comment, but **judge
   Haiku against what it could know**: if the place or the verdict can only
   be told from the wider context, record what's right but set `right` to
   `"neither"` with reason "needs wider context".
3. A divider, `--- Haiku output below: write your own_read first ---`, and
   then Haiku's output. **Do not read below the divider until you have
   written `own_read` for the item.** Places Haiku classified as a grocery,
   brand, venue, company or other are already removed, as the counts remove
   them: if one of them is a real food place here, it is a miss.

## Procedure for each item

1. **Blind read.** From the comment (and the context), write `own_read`:
   every place mentioned, and for each place `overall`, the five `aspects`,
   `experience`, `opinion`, `avoid`, `dishes` (each with `level` and
   `avoid`), `timeframe`, `trend` and `status`. The field definitions are
   below. No place is `own_read: []`.
2. **Read Haiku's output.**
3. **Compare.** Wherever your `own_read` and Haiku differ on any of those
   fields, or on whether a place is a mention at all, re-read the comment
   and write one `compare` entry: Haiku's value, yours, the `final` value,
   who was right (`haiku`, `judge` for your first read, or `neither`), and a
   one-line reason. Matching fields need no entry; the aggregator counts
   them as agreed. Your first read is graded too, so overturn it whenever
   Haiku was right. The checker rejects a judgment where your `own_read` and
   Haiku differ on a field with no `compare` entry.
4. **Missed.** Put every place Haiku should have extracted and didn't in
   `missed`, as a full mention object (the fields of your `own_read`).
5. **Notes, tags, location, kind.** Grade these after reading Haiku's
   output: `ok`, `wrong` (says something the comment doesn't, or the wrong
   kind), or `missing` (leaves out something important a reader would want:
   a tip, a price, a dish verdict, a fact).

   **Price** isn't in your blind read. When Haiku's price is wrong, add a
   `compare` entry for it with `own: null`, the `final` value and
   `right: "judge"`. No entry means it was right.
6. **rule_questions.** Any case this rubric doesn't decide. One sentence each.
7. **overall_item_ok**: true only if every `final` value equals Haiku's and
   nothing is missed.

Some items contain deliberately altered outputs, to check that judging is
careful. Judge every item on its merits. The same comment may appear in two
packets with different outputs; judge each where you find it.

## What counts as a mention

Every food or drink place in New York City that the comment names or refers
to: restaurants, bars, cafes, bakeries, delis, food trucks and carts, chains,
food halls and night markets (the hall **and** each named stall). That
includes names in a list (single-word names like Tong, Keens or Emily are the
easiest to miss), places not yet tried, closed places, both sides of a
comparison, a benchmark or style ("JG Mellon style"), places used as
landmarks, and places only asked about or named in passing (`opinion: none`).

- **Stores:** a store counts for the food it serves to eat (a gourmet
  market's deli counter, bakery, cafe or prepared food: Zabar's for a bagel
  is a mention). Named only for groceries or packaged goods, it is not.
- **Entertainment venues** (music and comedy clubs, game bars, theaters) are
  not places unless the comment talks about their food or drink; a bar or
  supper club whose music is part of the draw is a bar.
- **Not places:** cuisines, dishes, neighborhoods, streets, parks, museums,
  people (chefs, critics, influencers, users; but "dinner at Chef Marco's"
  names a restaurant), product brands, restaurant groups and companies, apps
  (Resy, Beli, delivery apps), places outside the five boroughs and foreign
  branches ("Golden Lotus in Tokyo"), a name the commenter takes back, and
  places nobody names ("a taco spot on Rivington").
- A place named only to identify a person ("the Golden Lotus chef") is a
  name in passing: a mention with opinion none.
- A place named twice is one mention. A rename ("Golden Lotus, formerly
  Lotus House") is one mention under the current name. A room, counter or
  tasting menu inside a restaurant is part of that restaurant.

**Context places.** A place named only in the context is a mention only when
the comment refers to it: by name, as "it", "they" or "this place", or by
replying to what was said about it ("v mid", "hard disagree"). Places the
context names that the comment doesn't refer to are not its mentions; a
comment that answers the post's general question, or talks about restaurants
in general, doesn't mention the places the post names. A claim in the
context is the commenter's only when they wrote it (the post with
`author="you"`, or a `you, earlier` comment) or agree with it. A reply that
neither names nor judges a place is not a mention of it. When a nameless
reply could mean two places, pick the one its words fit; if neither fits,
there is no mention.

## Levels

| level | when | examples |
|---|---|---|
| very_positive | **only** a superlative ranking this place or dish against the whole city or wider | "best in the city", "best X I've ever had", "my favorite in NYC", "one of the best meals of my life", "nothing in NYC comes close" |
| positive | any real yes, mild or wild | "decent", "solid", "good for what it is", "good", "great", "amazing", "to die for", "unreal", "god tier", "10/10", "my favorite", "my go-to", "best on the UES", "best I've had lately", "a must", "get the X" |
| neutral | good and bad weighed evenly, with no bottom line | "hit or miss"; never for lukewarm words |
| negative | any complaint, mild or strong | "fine", "ok", "not bad", "meh", "mid", "average", "mediocre", "nothing special", "not worth the trip", "overrated", "overpriced", "disappointing", "bland", "rude", "terrible", "awful", "sucks", "never again", "regretted going", "the line is insane" |
| very_negative | **only** an extreme | "worst I've ever had", "worst in the city", "inedible", "disgusting", "got sick", "food poisoning", "avoid at all costs" |

- Local, recent and classless hyperbole is positive: "best on the UES",
  "best I've had lately", "to die for", "unreal", "god tier", "10/10".
- Emphasis, caps, swearing, emoji and stacked knocks never raise a level.
- **Scores:** 8/10 and up is positive; anything lower is negative
  (very_negative only with an extreme word).
- `null` means not said. `neutral` is a verdict, never "not said".

## Fields

- **name**: as typed, even shortened, misspelled or as initials. When
  grading, treat obvious spellings of the same place as the same mention.
- **kind** (graded with notes): restaurant, bar, cafe, bakery, deli,
  truck_or_cart, market_stall, food_hall; grocery, brand, venue, company and
  other are removed from the counts.
- **overall**: the commenter's **bottom line** ("worth it", "not worth the
  trip", "skip it", "I'd go back"), even against points on the other side.
  Without one, a lone taste, value, service or atmosphere verdict sets it
  (a dish verdict is taste); with several, the **strongest non-wait point**,
  usually the food. **A remark only about the wait leaves overall null**,
  unless the commenter draws a bottom line from it ("not worth the wait").
  Null for a fact, a question or an untried reaction. Positive for an
  endorsement. A superlative about one dish makes the dish and taste
  very_positive; overall only if it is said of the place, or the dish is
  what the place sells.
- **aspects**, each a level from what is said about that side, never copied
  from overall:
  - `taste`: the food and drink. A verdict on a dish sets taste ("great
    brisket, awful sides": neutral).
  - `value`: worth the money ("a steal", "not worth $30", surprise fees and
    card surcharges). The word before "for the price" decides: "great for
    the price" positive, "tiny for the price" negative. A price word alone
    is price, not value.
  - `service`: staff, and how the place is run (policies, format: "prix-fixe
    only", "no substitutions").
  - `atmosphere`: room, vibe, noise, crowd, seating ("barely any seating").
    "Packed and lively" said as praise is atmosphere.
  - `wait`: lines, getting a table or reservation, slow food, selling out.
    **Negative when you must plan around it** ("be there by 11:30", "book
    the minute slots open", "sold out by 2", "those lines are brutal");
    **positive when getting in is easy** ("walked right in", "free tables at
    4").
  - Fit for one person or occasion ("not for kids", "more casual") is a note
    or tag, not a level.
- **experience**: whose opinion it is, not whether a visit is described.
  `firsthand` is the default: anything in the commenter's own voice, a visit,
  a pick, a list item, a tip, a hedge, a reply about someone else's place.
  `secondhand` only when the comment credits someone else ("my friend swears
  by it", "heard it's great", "people say A beats B"). `none`: a question, a
  place they haven't tried, a bare fact. Secondhand counts like firsthand.
- **opinion**: `none` (a fact, a question, business news, a name in passing
  or as an example, an untried reaction); `endorse` (a pick with no word of
  judgment: a bare name, "try X", "get the Y at X", "X for the Y", "+1"
  under a rec; overall positive); `stated` (any word judging the place or its
  food, even one).
- **avoid**: true only when the comment tells readers to skip the place
  itself ("skip it", "don't bother", "tourist trap", "make it at home
  instead", "great list, but skip X"). False for a bad review alone, "I won't
  go back", a swap ("go to Y instead"), a skip for one branch, or an insult
  with no instruction ("should be burned down" is a level, not avoid).
- **dishes**: every dish or drink named for this place, with `level` (null
  if only named) and `avoid` ("skip the X"). "Get / try the X", "X for the
  Y" and a dish heading over picks ("Mazemen: A, B") are positive.
- **timeframe**: `past` when the place is closed, or the comment ties the
  verdict to an earlier time ("used to be great", "back in 2015"). **An old
  visit with nothing tying it to then is `current`.**
- **trend**: `declined` or `improved` only when the comment says the place's
  quality changed. Not for closing, fewer customers, a lost star, a
  prediction, or a change in one aspect.
- **status**: the place under that name: `closed`, `moved`, `opened` (new or
  reopened), else null. **One branch closing, opening or moving, a temporary
  closure or a rumored reopening is null**, with the branch in location and
  a note.
- **price**: only an absolute price word (very_cheap … very_expensive). Not a
  dollar figure, not "cheaper than X", not "overpriced".
- **tags, notes, location**: as before. Notes hold tips, facts, prices,
  comparisons, rank order, the detail behind a verdict, and reasons that set
  no level. A note never replaces a level.

## Rules

1. A complaint put as a fact is a judgment ("impossible to book": wait
   negative; "the sauce comes from a jar now": taste negative). `opinion:
   none` is only for facts and questions with nothing judged.
2. Every complaint lowers a level: its aspect, a dish, or overall when no
   aspect fits. **Hygiene** (a bad grade, violations, roaches) is overall,
   not service, with a note. **Getting sick** is overall very_negative; taste
   stays null unless the flavor is judged.
3. **Not tried (owner):** someone who says or shows they haven't been ("looks
   so good", "sounds amazing", "can't wait to try", "saved it", "thanks, will
   check it out", "that's what I was afraid of") gives no verdict: a mention
   with experience none, opinion none, every level null. That is not
   secondhand, which passes on a verdict about the place ("my friend got sick
   there").
4. **Lukewarm** stays negative in a defense ("it's not that bad") and about
   price ("not the best or worst price"). "I like it, but it's not worth it"
   is negative: the bottom line wins. An excuse with no verdict ("it's a small
   business") is opinion none.
5. **Comparisons (owner).** The loser is negative on what was compared:
   food → taste, price or portions → value, line or booking → wait, the place
   as a whole ("I prefer A over B", "go to A instead" answering "is B worth
   it?") → overall. It stays positive when both are called good. "As good as
   X" and "X-level" praise X. "Close, but not the same as A" makes the other
   place the loser. No loser without a winner the comment names. A swap for
   fit ("more casual", "closer to your hotel") lowers nothing. A low-bar
   winner ("even Burger Barn is better") gets no level. Ranked picks ("A, B,
   C in that order") are all positive. A comparison the commenter only
   reports is secondhand.
6. **Bare answers (owner).** A bare answer takes from the question its
   polarity, the aspect it asks about and the dish it asks about, **never its
   superlative**: under "easiest walk-ins?" each pick also gets wait positive;
   under "best chicken salad?" each pick gets that dish positive and overall
   positive; under "worst meal you've had?" each pick is negative. A heading
   works the same way. Names given as examples or facts are opinion none.
   The commenter's own words outrank the framing, and framing never sets
   avoid.
7. **Closed places.** Under a title about closed places ("places you miss")
   each named place is status closed, timeframe past, overall positive.
   Regret that a place closed ("RIP X", "too bad it closed") is the same fond
   verdict.
8. **Agreement replies.** "This", "+1", "second this" take the verdict they
   agree with, and the aspects the agreed text names ("poor quality and
   expensive": taste and value negative), but only agreement with the verdict
   on the place, not with an analogy or side point. "Great list" endorses only
   the places the reply names; "great list, but skip X" makes X avoid.
9. Levels are what the commenter thinks now. "Used to be great, now mid":
   overall negative, trend declined.
10. **Not verdicts (opinion none):** a reservation offered, wanted or traded;
    the commenter speaking for the place ("we", "our menu", "I work there");
    **a boycott or a reason not to go that isn't about eating there** (the
    owner's politics, a business deal, a chef's persona: a note only, no
    level); awards, stars, review scores and critics unless the commenter
    adopts them; a joke whose point isn't a verdict (lyrics, innuendo,
    arguing a label). A joke whose point is a verdict counts ("shh, don't
    tell anyone" under a rec is an endorsement).
11. Sarcasm reverses: "/s" flips its sentence; tourist-strip chains
    recommended with "lol" are a joke (opinion none).
12. A remark about a whole category ("$100 steaks are wacky") lowers a named
    place only when the comment applies it to that place.
13. Never soften a complaint because the thread likes the place or the
    commenter is polite.

## Worked examples (invented places)

- *Under "Where can I walk in near Union Sq?": "Noodle Lab, or Pepper House
  (get the cumin lamb). Places like Golden Lotus are always booked."*
  Noodle Lab and Pepper House: firsthand, endorse, wait positive, overall
  positive; Pepper House dish cumin lamb positive. Golden Lotus: stated, wait
  negative, **overall null** (only the wait).
- *Parent: "Golden Lotus has the best hand-pulled noodles in the city."
  Reply: "lol no. noodles were fine, not worth $24 a bowl. their dumplings
  are to die for tho".* Golden Lotus (named in context): stated; dishes
  noodles negative, dumplings positive; taste neutral; value negative;
  overall negative (the bottom line).
- *Under a photo post of Lucky Fold: "Looks amazing, saving this! My sister
  swears Twin Lantern has the best dumplings in NYC though".* Lucky Fold:
  experience none, opinion none, no levels. Twin Lantern: secondhand, stated,
  dish dumplings and taste very_positive, overall positive.
- *Under "Bagel spots you miss?": "Kettle & Crumb. These days I get mine at
  the deli counter in Hilltop Market. And the Chelsea Noodle Lab just
  closed".* Kettle & Crumb: closed, past, overall positive. Hilltop Market: a
  mention (food it serves), endorse, positive. Noodle Lab: opinion none,
  status null, location Chelsea, a note.
- *"Brindle is a 6/10 at best, Copperline does the same pasta way better. Be
  at Saffron Table by 11:30 or you'll wait an hour. Done with Ember House
  after the owner's rant."* Brindle: taste and pasta negative, overall
  negative. Copperline: taste, pasta and overall positive. Saffron Table:
  wait negative, overall null. Ember House: opinion none, no levels, a note.
- *"is Noodle Lab still cash only?"*: opinion none, experience none, every
  level null.

## Judgment format

One JSON line per item in `eval/review_v6r4/judgments/pNNN.jsonl`, in packet
order:

```json
{"item_id": "R0001", "comment_id": "t1_x",
 "own_read": [{"name": "Golden Lotus", "overall": "negative",
               "aspects": {"taste": "neutral", "value": "negative", "service": null, "atmosphere": null, "wait": null},
               "experience": "firsthand", "opinion": "stated", "avoid": false,
               "dishes": [{"dish": "noodles", "level": "negative", "avoid": false},
                          {"dish": "dumplings", "level": "positive", "avoid": false}],
               "timeframe": "current", "trend": null, "status": null}],
 "compare": [{"name": "Golden Lotus", "field": "aspects.value", "haiku": null, "own": "negative",
              "final": "negative", "right": "judge", "reason": "'not worth $24 a bowl' is a value complaint"}],
 "missed": [],
 "notes_grade": [{"name": "Golden Lotus", "notes": "ok", "tags": "ok", "location": "ok", "kind": "ok", "note": ""}],
 "rule_questions": [],
 "overall_item_ok": false}
```

**Field names for `compare`:**
- `overall`, `aspects.taste`, `aspects.value`, `aspects.service`,
  `aspects.atmosphere`, `aspects.wait`, `experience`, `opinion`, `avoid`,
  `timeframe`, `trend`, `status`;
- `price` (only when Haiku's is wrong; see step 5);
- `dish:<dish name>`: the value is `{"level": ..., "avoid": ...}`, or null
  when the dish is absent on that side;
- `_mention`: whether the place is a mention at all. The value is
  `"present"` or `null`.

A place only in your `own_read` (Haiku missed it) needs a `_mention` compare
entry, and its full object goes in `missed` if the final value is
`"present"`. A place only in Haiku's output (you didn't list it) also needs a
`_mention` entry.
