# Gold rules

How the v1 and v2 gold was labeled, and what each field means. The owner's
rules come first because they decide every edge case below. The v5 version of
the same gold is described in `schema_v5.md`. Back to the index: `../README.md`.

## Who this is for

The owner uses r/FoodNYC like this: search a cuisine, dish or experience,
read about a year of comments, and pick a place by (a) **how many people are
talking about it** and (b) **negatives**, which weigh heavily, especially
repeated ones ("avoid the X", "overpriced"). The rules below serve that use.
Every named place counts toward volume, and negatives, value complaints and
dish-level knocks are the signals that matter most.

## What a mention is

A **mention** is a specific food or drink business that the comment names or
unambiguously refers to.

- **In scope:** restaurants, cafes, bakeries, dessert shops, delis, bars,
  food halls, individual stalls and vendors, food trucks, and chains. Each
  gets an `entity_type`. Production drops chains downstream (`chains.txt`;
  `score.py --drop-chains` mirrors that), but extraction must still emit
  them.
- **Out of scope, but recorded with `out_of_scope: true`** (neither required
  nor penalised): primarily retail grocery stores, supermarkets and markets
  (Whole Foods, Trader Joe's, Zabar's as a grocery, Costco), and places
  outside NYC. Any key in `data/excluded_entities.json` (production's 279
  exclusions) is also treated as out of scope when matching.
- **Doesn't count:** cuisines ("Haitian food"), dishes, neighborhoods,
  streets, generic categories ("any banh mi shop", "kati roll places"),
  products and brands (Arizona iced tea, a panettone), apps and services
  (Beli, Resy, InKind, GrubHub), unnamed places ("a guy on the corner", "the
  restaurant next door"), and people.
- **Nameless replies count.** A reply that judges the place it replies about,
  without naming it ("v mid", "this is the answer", "great burger too",
  "second this"), is a mention of that place under the reply. It is identified
  from the full thread.
- **Places named only in the title, the body or an ancestor** are mentions of
  the comment only when the comment says something about them. Answering
  "what should I order at Portale?" with dishes counts.
- **Reference-only names are REQUIRED mentions**, because they count toward
  "how many people are talking". Examples: "I haven't visited X yet", "the
  chef moved to Y", "what drinks do you recommend at DCP?", "like X but
  cheaper", X given as an example. Aspects stay null unless an opinion is
  actually expressed, and `is_firsthand` is false where appropriate.
- **Closed places are REQUIRED mentions**: all aspects null, `closed: true`,
  and `descriptors` include "closed". The remembered sentiment is not
  accepted as an alternative.
- **`ambiguous: true`** is only for genuinely two-reading cases, e.g. a
  nameless reply that could be about the parent's place or just the cuisine.
  Those mentions are neither required nor penalised.
- **The same place twice in one comment** is one mention.

## Aspect scale (7 points)

Aspects are `food`, `value`, `service`, `atmosphere` and `wait`. Each is an
integer from -3 to 3, or **null when the aspect is not addressed. Null is not
0.** The aspect definitions follow the production prompt:

- `food` is the cooking, and also generic praise or hate ("my favorite",
  "mid").
- `value` is worth the money. "Cheap" alone is not value.
- `service` is the staff.
- `atmosphere` is the room, the vibe, the noise.
- `wait` is the line, reservations and walk-in ease, and how long the food
  took.

| level | meaning | typical wording |
|---:|---|---|
| **+3** | superlative against a broad class | "best in the city", "one of the best restaurants in New York", "better than anything I had in Korea", "life-changing" |
| **+2** | clear praise | "great", "really good", "awesome", "insane", "my favorite", "personal favs:" list header, "great burger too" |
| **+1** | named as an answer with no adjective, or mild positive | bare list items, "try X", "X is solid", "looks so nice" (not firsthand), "this" / "+1" under a bare rec |
| **0** | explicitly mixed on THIS aspect, net neutral | "food was hit or miss", "good apps, bad mains" |
| **-1** | mild knock | "mid", "fine", "overrated", "not as good as it used to be", "I'd rather skip it" (hearsay) |
| **-2** | clear complaint | "bad", "awful", "sucks", "overpriced", "highway robbery" (value), "rude" |
| **-3** | avoid-level or extreme | "worst I've had", "got sick", "never again", "regretted going", "inedible", "disgusting", "avoid at all costs" |

The rules for applying the scale:

1. **Don't infer one aspect from another.** Great food says nothing about
   service, price, the room or the wait.
2. **Named as an answer means food +1.** A name given with nothing said about
   it, in answer to the thread's question, is food +1 and nothing else. If the
   comment says something about another aspect (the line, the price, walk-in
   odds), score that aspect and leave food null, with food +1 listed as an
   accepted alternative.
3. **Reservation and walk-in ease is `wait`.** "They'll seat walk-ins for 4",
   "always one or two free tables at 4pm", and "looks like they have an
   opening" are wait +1. "Never able to get a reservation" is wait -1. A
   logistics tip that doesn't judge the wait ("order on GrubHub and skip the
   line") is null.
4. **List headers apply to every item.** "Personal favs:" makes each name +2.
   An avoid header makes each item `is_negated` (see below).
5. **A superlative has to be broad for +3.** "One of the best meals we've had
   lately" is +2, with +3 accepted. "My favorite" is +2; "my favorite in the
   city" is +3.
6. **-3 needs harm, refusal, a superlative negative or extreme words.**
   "Awful" alone is -2.
7. **Don't soften.** Score what the commenter says even if the thread loves
   the place or the commenter is polite. Sentiment is what they think now.
8. **Sarcasm and thread framing decide polarity.** "Second this" in a thread
   asking for the worst restaurant to send an enemy to is negative.
9. **Use 0 sparingly.** Only when the comment weighs both sides of the same
   aspect. Mixed across aspects means separate scores.

### Other fields

- `is_negated` is true only when the comment tells OTHERS to avoid the place:
  skip it, don't bother, tourist trap, an avoid list. A bad review is not
  negation, and neither is losing a comparison. A **self-skip** ("I'd rather
  skip it", "I wouldn't go back") puts the negative in the aspect and sets
  `is_negated` false, with true accepted (the field is listed in
  `uncertain_fields`).
- `is_firsthand` is true when they went, and false for hearsay, "on my list",
  "haven't been" or reservation attempts. It is null when it can't be
  determined. Bare recommendations default to true.
- `expensiveness` is the price level on the same 7 points, with no valence:
  -3 very cheap, -1 cheap-ish / reasonable, +1 pricey, +3 very expensive
  ("$400 omakase"). Null if price isn't said. "Overpriced" is value -2 AND
  expensiveness +1/+2.
- `value_complaint` is true when the comment says overpriced, not worth the
  money, rip-off, highway robbery, or "for that price" as a complaint. It is
  reported as its own recall.
- `dish_sentiment` is `[{dish, level, avoid}]`, one entry per dish actually
  named for that place. `level` is the 7-point sentiment for that dish, or
  null if the dish is only named. `avoid` is true for "avoid / skip / don't
  get the X". "Get the Z" is +1; "the Y is overrated" is -1. Dish-level
  negatives are one of the owner's strongest signals. `dishes` is the list
  of dish names.
- `search_terms` are the cuisine, dish and experience words in the comment
  that someone might search to find this place ("omakase", "date night",
  "cheap eats", "slice", "byob", "hand-pulled noodles", "walk-ins"). They are
  in the commenter's own words, lowercase, and only words tied to this
  place.
- `descriptors` holds labeler-supplied descriptors that matter for scoring,
  currently "closed" for closed places.
- `out_of_scope` is set for retail grocery and non-NYC places (see above).
- `neighborhood_hint` is set only when the comment places THIS restaurant
  somewhere.
- `restaurant_raw` is the name as typed in the comment. For a nameless reply,
  it is the name as typed where the thread names it, and `named_in` says
  where: `comment`, `parent`, `ancestor`, `title` or `selftext`.
- `canonical_key` is `extract.normalize_entity(canonical_name)` with
  `alias_overrides` applied. `accept_keys` holds the other normalized forms a
  correct model might emit (typed form, common short form, misspelling).
- `resolvable_comment_mode` asks whether the place AND its polarity could be
  determined from what comment mode sends: the title, the first 400 chars of
  the body, the immediate parent, and the comment.
- `resolvable_thread_mode` asks the same of the rendered thread chunk the
  model would actually see: 25 comments, each cut at 700 chars. An ancestor
  in a different chunk is invisible.
- `confidence` is high, medium or low.
- `ambiguous` marks a mention with two defensible readings. It is not
  required for recall and not counted against precision.
- `aspect_alternatives` gives other accepted values for an aspect or for
  `expensiveness` (null included). `uncertain_fields` lists boolean fields
  that are not scored.
- `rationale` is one line.

A gold line per comment also has `has_mention`, true when there is at least
one required mention (not ambiguous, not out of scope), and a `note`. Gold
lines for thread comments use the thread's item_id (`t001`) plus the
comment_id.

## Mapping to the model's -1..1 scale

- **Gold to model scale:** `v / 3`, which gives -1, -0.67, -0.33, 0, 0.33,
  0.67, 1.
- **Model float to level** (for agreement metrics): `level = sign(v) *
  floor(|v| * 3 + 0.5)`, with v clipped to [-1, 1]. The cut points are
  ±0.167, ±0.5 and ±0.833.

  | model value | 0.1 | 0.3 | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 | 1.0 |
  |---|---|---|---|---|---|---|---|---|
  | level | 0 | 1 | 2 | 2 | 2 | 2 | 3 | 3 |

  (0.85 rounds to 3; the same holds for negatives.)

  The old prompt's anchors therefore map one-to-one: 1 → +3, 0.6 → +2,
  0.3 → +1, -0.3 → -1, -0.6 → -2, -1 → -3.
- **MAE** is measured in levels: `|v*3 − gold|`, against the nearest accepted
  value.

## Labeling procedure

1. Label **blind.** Labeling packets show the title, the full body, the full
   ancestor chain, the comment and its replies. They do not show risk groups,
   stored mentions or any model output. Don't run `tools/export_stored.py` or
   `score.py` on production output until every item you will label is done.
2. Read the whole thread context, not only what the model sees, to decide
   meaning. Then judge resolvability separately for each mode.
3. Record **all** mentions in the comment, not just the risky one.
4. Every comment in a sampled whole thread gets a label line, including the
   ones with no mention.
5. Write labels into `v1/labels/batchNN.py` (using `v1/labels/common.py`'s `M()`)
   and run `python eval/v1/labels/build_gold.py` to regenerate gold.jsonl from
   every batch. Never edit gold.jsonl by hand. Corrections made after
   adjudication go in `v1/labels/adjudication.py` as patches (the blind label
   stays visible) and are logged in `v1/gold_changes.md`.
6. Do not run `tools/export_stored.py`, `tools/adjudicate.py` or `score.py` on
   production output until every item you will label is done.
