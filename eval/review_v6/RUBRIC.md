# Judging Haiku's v6 extraction: rubric

You are judging how well a small model (Claude Haiku 5.5) turned r/FoodNYC
comments into structured restaurant opinions. You read each comment
yourself, write your own answer **before** looking at Haiku's, then compare
the two field by field and decide what is right. Your reading is the
reference, so read carefully; and when you disagree with Haiku, re-read the
comment and be willing to find that Haiku was right.

These rules are the owner's. Where they decide a case, follow them even if
you'd read it differently. Where they don't, say so in `rule_questions`.

## What you get per item

1. **What the model saw**: the post title, the start of the post body (cut
   at 400 characters), the immediate parent comment if any, and the
   comment. Haiku saw exactly this and nothing more.
2. **Wider thread context**: the full post, every ancestor, and the replies.
   Haiku did not see this. Use it to understand the comment, but **judge
   Haiku against what it could know**: if the place or the verdict can
   only be told from the wider context, record what's right but set
   `right` to `"neither"` with reason "needs wider context", not
   `"judge"`.
3. A divider, `--- Haiku output below: write your own_read first ---`, and
   then Haiku's output. **Do not read below the divider until you have
   written `own_read` for the item.**

## Procedure for each item

1. **Blind read.** From the comment (and the context), write `own_read`:
   every place mentioned, and for each place `overall`, the five
   `aspects`, `experience`, `opinion`, `avoid`, `dishes` (each with
   `level` and `avoid`), `timeframe`, `trend` and `status`. The field
   definitions are below. No place is `own_read: []`.
2. **Read Haiku's output.**
3. **Compare.** Wherever your `own_read` and Haiku differ on a scored field,
   or on whether a place is a mention at all, re-read the comment and write
   one `compare` entry: Haiku's value, yours, the `final` value, who was
   right (`haiku`, `judge` for your first read, or `neither`), and a one-line
   reason. Matching fields need no entry; the aggregator counts them as
   agreed. Your first read is graded too, so overturn it whenever Haiku was
   right.
4. **Missed.** Put every place Haiku should have extracted and didn't in
   `missed`, as a full v6 mention object (all fields, as in Haiku's output).
5. **Notes, tags, location.** Grade these after reading Haiku's output: `ok`,
   `wrong` (says something the comment doesn't), or `missing` (leaves out
   something important a reader would want: a tip, a price, a dish verdict,
   a fact).

   **Price** isn't in your blind read. When Haiku's price is wrong, add a
   `compare` entry for it with `own: null`, the `final` value and
   `right: "judge"`. No entry means it was right. Timeframe, trend and
   status are in your blind read and are compared like any other field.
6. **rule_questions.** Any case this rubric doesn't decide. One sentence each.
7. **overall_item_ok**: true only if every `final` value equals Haiku's and
   nothing is missed.

Some items contain deliberately altered outputs, to check that judging is
careful. Judge every item on its merits.

## What counts as a mention

A mention is a restaurant, cafe, bakery, bar, deli, food truck, cart, stall
or chain in New York City that the comment names or clearly refers to. That
includes:
- names in a list. This is the most common case, and single-word names
  (Tong, Keens, Emily) are the easiest to miss;
- places the commenter hasn't tried;
- closed places;
- places in comparisons or given as examples;
- food or drink places used as landmarks ("near X");
- places a comment only asks about or names in passing (`opinion: none`).

A reply that judges a place without naming it ("v mid", "hard disagree",
"the line is brutal") is a mention of the place it replies about, with the
name copied from the context.

**Not places:** cuisines, dishes, neighborhoods, streets, museums, stores,
parks, venues, supermarkets and grocery stores, apps and services (Resy,
InKind, Beli), people, and places outside NYC.

Chains are mentions like any other place. A place named twice in one
comment is one mention.

## Levels

`very_positive`, `positive`, `neutral`, `negative`, `very_negative`, or
`null` for not mentioned. `neutral` is a verdict, never "not mentioned".

| level | when | examples |
|---|---|---|
| very_positive | only a superlative about this place against a broad class | "best in the city", "best X I've ever had", "my favorite in NYC", "one of the best meals of my life", "god tier", "life-changing" |
| positive | real praise, a clear yes | "good", "great", "amazing", "so good", "love it", "my favorite", "my go-to", "a must", "delicious", "pretty solid", "worth it", "get the X" |
| neutral | a balanced verdict, good and bad weighed evenly | "hit or miss", "great food, awful service" (overall) |
| negative | any knock, however mild or polite, lukewarm words included | "fine", "ok", "not bad", "meh", "mid", "nothing special", "overrated", "underwhelming", "bland", "overpriced", "rude", "disappointing", "never again", "regretted going", "hard to book", "the line is insane" |
| very_negative | only an extreme | "worst I've had", "inedible", "disgusting", "got sick", "avoid at all costs" |

**Calibrations** (the owner's, and stricter than Haiku's prompt):
- very_negative is for extremes only. "Never again", "regretted going",
  "disappointing" and "overpriced" are **negative**.
- very_positive needs a broad superlative about the place. "My favorite",
  "a must" and "amazing" are positive.

## Fields

- **name**: the name exactly as the comment types it, even shortened or
  misspelled ("2nd Ave", "lindustrie"). For an unnamed reference, copy the
  name from the context. When grading, treat obvious spellings of the same
  place as the same mention.
- **overall**: the verdict on the place as a whole. It follows the
  commenter's **bottom line** if they give one ("worth it", "never going
  back", "skip it"). Otherwise it follows their **strongest point**, usually
  the food. It is null when there is no verdict, e.g. only a tip or a fact.
  A bare endorsement is positive.
- **aspects**: `taste` (the food and drink), `value` (worth the money,
  including portions for the price), `service` (staff, and how the place is
  run), `atmosphere` (room, vibe, noise, crowd), `wait` (lines, getting a
  table or reservation, slow food, selling out). Set each only from what is
  said. Never infer one aspect from another, or from overall.
- **experience**: `firsthand` is the default: a visit, or any pick, list
  item or verdict in the commenter's own voice. `secondhand` only when they
  credit someone else ("heard great things", "my friend swears by it",
  "people say"). `none` only for questions, places not yet tried, and bare
  facts. **Owner:** secondhand opinions count like firsthand ones.
- **opinion**:
  - `none`: only facts, a question, or a name in passing. **Owner:** these
    count as mentions.
  - `endorse`: a bare name or "try X" with no word of praise. A plain list
    item. "Second this" under a recommendation. **Owner:** an endorsement
    counts as praise, overall positive, aspects null.
  - `stated`: anything that judges the place. One praise word ("great
    burger too") makes it stated.
- **avoid**: true only when the comment tells *others* to avoid the place:
  "skip it", "don't bother", "tourist trap", an avoid list. A bad review
  alone, or "I won't go back", is false.
- **dishes**: every dish or drink named for this place, each with a `level`
  (null if only named) and `avoid` (true for "skip / don't get the X").
  "Get the X" is positive. A complaint about one dish is a negative dish
  entry, even when the place is praised.
- **price**: only when said in words: very_cheap, cheap, moderate,
  expensive, very_expensive. A dollar figure alone is not a price level,
  and "overpriced" is value, not price.
- **timeframe**: `current`, or `past` when the levels describe how the
  place was, not how it is.
- **trend**: `declined` or `improved` when the comment says it changed.
- **status**: `closed`, `moved`, `opened`, or null.
- **tags**: the commenter's own words for what the place is or is for
  (cuisine, format, occasion, diet, payment).
- **notes**: everything else worth keeping: tips, facts, prices,
  comparisons, the specifics behind a verdict. No note that only repeats a
  level.
- **location**: where the comment places this place ("the LES one").

## Rules

1. `opinion: none` is **only** for facts and questions with no judgment. A
   complaint put as a fact is stated, with a negative level.
   - Wait negative: "impossible to book", "they sell out by noon", "the
     line started at 4:15", "be there by 11:30", "busy even in the rain".
   - Wait positive: "easy walk-ins", "free tables at 4", "no line on
     weekdays".
   - Value negative: "tiny portions for the price".
   - Taste negative: "the sauce comes from a jar now".
2. Every complaint lowers a level: the aspect it is about, or `overall` if
   none fits. A note can add detail, but never holds a complaint alone.
3. Lukewarm is negative.
4. Never default to positive. A place with any remark that judges it is
   stated, leveled by what is said. A complaint replying to a rave is still
   a complaint.
5. **Comparisons (owner):** a comparison judges both sides. The loser is
   negative by default ("I prefer A over B": B negative). It is
   very_negative only if the comment calls it extreme, and positive if the
   comment says both are good ("both great, I just prefer A"). The note
   records the comparison. Shared traits carry over: "as hard to book as X"
   makes X wait negative.
6. Money complaints are value negative: "overpriced", "not worth the money",
   "$28 for that is a joke".
7. A heading covers every name under it.
   - "My favorites:" makes each item stated and positive (very_positive only
     with its own superlative).
   - "I'd skip all of these: A, B, C" makes all three `avoid` true, overall
     negative.
8. **Agreement replies (owner):** "This", "+1" and "second this" take the
   verdict they agree with. Under a recommendation or praise, endorse;
   under a knock, stated with the same overall.
9. Levels are what the commenter thinks **now**. "Used to be great, now mid"
   is overall negative, with `trend: declined`.
10. **Closed places (owner):** a closed place keeps its mention and its
    remembered verdict, with `status: closed` and `timeframe: past`.
    Rankings will leave closed places out; that isn't your concern.
11. Thread framing and sarcasm decide polarity: "second this" under "worst
    meal you've had?" is negative.
12. Never soften a complaint because the thread likes the place or the
    commenter is polite.

## Worked examples (invented places)

- *Parent: "Golden Lotus has the best hand-pulled noodles in Queens." Reply:
  "lol no. noodles were gummy and $24 a bowl is a joke. go early if you do
  go, line by noon".*
  - Golden Lotus (named in context): firsthand, stated, overall negative.
  - taste negative, value negative, wait negative.
  - dish noodles negative.
  - notes: the price ($24 a bowl) and the best time to go.
- *"Sichuan: Golden Lotus and Pepper House"* under "where for spicy food?":
  two endorsements, overall positive, aspects null, tags `sichuan`.
- *"Pepper House is overrated and $28 for noodles is a joke"*: stated,
  overall negative, value negative, dish noodles (level null). Notes:
  "overrated", "$28 noodles".
- *"hard disagree, the cumin lamb is worth it"*, replying to the above:
  Pepper House, stated, overall positive, taste positive, dish cumin lamb
  positive.
- *"Avoid both. Noodle Lab is the move, just skip their dumplings"*:
  - the two places named above: avoid true, overall negative;
  - Noodle Lab: stated, overall positive, dish dumplings negative with
    avoid true.
- *"is Noodle Lab still cash only?"*: opinion none, experience none, every
  level null.
- *"I prefer Pepper House over Golden Lotus"*: Pepper House positive, Golden
  Lotus negative, both noting the comparison.
- *"Golden Lotus closed last year, I miss it"*: status closed, timeframe
  past, overall positive.

## Judgment format

One JSON line per item in `eval/review_v6/judgments/rNNN.jsonl`, in packet
order:

```json
{"item_id": "Q0001", "comment_id": "t1_x",
 "own_read": [{"name": "Golden Lotus", "overall": "negative",
               "aspects": {"taste": "negative", "value": "negative", "service": null, "atmosphere": null, "wait": "negative"},
               "experience": "firsthand", "opinion": "stated", "avoid": false,
               "dishes": [{"dish": "noodles", "level": "negative", "avoid": false}]}],
 "compare": [{"name": "Golden Lotus", "field": "aspects.wait", "haiku": null, "own": "negative",
              "final": "negative", "right": "judge", "reason": "'line by noon' is a wait complaint"}],
 "missed": [],
 "notes_grade": [{"name": "Golden Lotus", "notes": "ok", "tags": "ok", "location": "ok", "note": ""}],
 "rule_questions": [],
 "overall_item_ok": false}
```

**Field names for `compare`:**
- `overall`, `aspects.taste`, `aspects.value`, `aspects.service`,
  `aspects.atmosphere`, `aspects.wait`, `experience`, `opinion`, `avoid`;
- `price`, `timeframe`, `trend`, `status` (only when Haiku's is wrong; see
  step 5);
- `dish:<dish name>`: the value is `{"level": ..., "avoid": ...}`, or null
  when the dish is absent on that side;
- `_mention`: whether the place is a mention at all. The value is
  `"present"` or `null`.

A place only in your `own_read` (Haiku missed it) needs a `_mention`
compare entry. Its full object goes in `missed` only if the final value is
`"present"`. A place only in Haiku's output (you didn't list it) also needs
a `_mention` entry.
