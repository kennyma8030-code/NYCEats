# Extraction schema v5

This is the single written copy of the v5 contract: what a v5 prompt asks the
model to output, what the v5 gold stores, and how the harness reads both.
`lib/schema_v5.py` implements it, `score_v5.py` scores against it, and
`bench.py` runs it. If they disagree with this file, this file is the bug
report.

## Model output

```jsonc
{"mentions": [{
  "id": 5,                          // thread mode only: the bracket number of the comment
  "restaurant_raw": "F&F",          // verbatim; a nameless reply copies the name it refers to
  "neighborhood_hint": null,        // string or null
  "reference_only": false,          // a question, a fact, a comparison anchor: no judgment
  "aspects": {"food": "awful", "value": null, "service": "bad", "atmosphere": null, "wait": null},
  "is_negated": false,              // tells people to avoid the place
  "price": null,                    // cheap | moderate | pricey | very_pricey | null
  "experience": "ate_there",        // ate_there | secondhand | unclear
  "dishes_liked": [], "dishes_disliked": ["slice"], "dishes_mentioned": [],
  "descriptors": []                 // the commenter's own words
}]}
```

Every key is required on every mention, and no other key is allowed.

### Aspect labels

| label | level | production float | typical wording |
|---|---:|---:|---|
| rave | +3 | 1.0 | "best in the city" |
| good | +2 | 0.6 | "great", "my favorite" |
| decent | +1 | 0.3 | "solid", "pretty good" |
| mixed | 0 | 0.0 | explicitly mixed on that aspect |
| meh | -1 | -0.3 | "mid", "fine", "it's ok", "overrated" |
| bad | -2 | -0.6 | "bad", "overpriced" (value), "rude" |
| awful | -3 | -1.0 | "worst I've had", "got sick", "never again" |

Null means the aspect wasn't addressed. "It's ok" is **meh**, never decent.

### Price

Price is a fact, not a judgment: `cheap`, `moderate`, `pricey`, `very_pricey`
or null. "Overpriced" is price pricey **and** value bad.

### Semantics

1. **Bare endorsement.** A name given as an answer to the post's question,
   with nothing said about it, is `reference_only: false` with every aspect
   null. No food score is invented. The non-sentiment fields can still be
   filled.
2. **Judgment-carrying question.** If the post's question carries a
   negative or aspect-specific judgment ("most overrated", "worst service"),
   a bare name takes that judgment: "overrated" gives food meh plus the
   descriptor "overrated". A plain "best X?" or "where should I eat" is still
   a bare endorsement. A question that asks for neither ("where did you eat
   this week") makes a bare name reference_only.
3. **Reference only.** This covers questions about a place, stated facts
   ("they moved", "closed", "cash only btw"), comparison anchors ("like Katz's
   but cheaper", for Katz's) and passing references.
   - **Must be empty:** every aspect null, `is_negated` false, no liked or
     disliked dishes.
   - **Still filled when stated:** neighborhood_hint, price, experience,
     dishes_mentioned and descriptors.
4. **Stated, not asked.** "Is it still cash only?" gives no descriptor.
   "It's cash only btw" gives "cash only".
5. **Evaluative descriptors are opinions.** "Tourist trap", "overrated" and
   "hidden gem" make a mention not reference_only, and its aspects get
   scored. Factual descriptors ("cash only", "BYOB", "slice shop", "closed")
   are neutral.
6. **Dishes.** Each dish goes in exactly one list.
   - **dishes_liked:** a recommendation ("get the vodka slice", "the pastrami
     is a must"), or a named dish covered by praise of the meal ("got the
     pastrami and soup, both great").
   - **dishes_disliked:** a dish judged negatively.
   - **dishes_mentioned:** a dish named with no judgment.
7. **Closed place.** reference_only true, "closed" in descriptors, aspects
   null, even when the comment remembers it fondly.
8. **Avoid instructions.** An avoid heading a list applies to every name in
   it. A negative review is not an avoid, and losing a comparison isn't one
   either.

## Normalizer (`schema_v5.normalize_v5`)

`score_v5.Run` picks one schema per run file, by majority of its mentions
(`schema_v5.run_schema`). Every mention in a v5 run goes through the
normalizer, including one that drifted back to old-style numbers, and every
mention in an old run goes through the adapter.

The normalizer turns a raw v5 mention into the contract. It counts every
repair, and `score_v5` reports the count per 100 mentions with the most
common kinds. A prompt that needs many repairs is a finding in itself.

| input | becomes | counted as |
|---|---|---|
| not an object / no `restaurant_raw` | dropped | `not_object`, `no_name` |
| a key outside the contract | ignored | `extra_key` |
| aspects missing or not an object | all null | `aspects_missing` / `aspects_invalid` |
| an aspect key missing / an extra one | null / ignored | `aspect_missing_key` / `aspect_extra_key` |
| `"Good"`, `" good "` | `good` | `aspect_label_case` |
| a whole number (`2`, `"-1"`, `"+1"`, `2.0`) | that 7-point level's label, clamped to ±3 (so 1 is decent) | `aspect_numeric_level` |
| a fractional number (`0.6`, `-0.33`) | its label on the old -1..1 scale | `aspect_numeric_float` |
| an unknown label (`"ok"`) | null | `aspect_bad_label` |
| `"true"` / `"false"` / `1` / `0` for a boolean | that boolean | `<field>_string` / `<field>_number` |
| a missing boolean | false | `<field>_missing` |
| `"very pricey"` | `very_pricey` | – |
| a numeric price | whole numbers as levels, fractions as the old scale, then the price map | `price_numeric` |
| `experience: true/false` | ate_there / secondhand | `experience_bool` |
| missing experience | unclear | `experience_missing` |
| a string where a list belongs | a one-item list | `<field>_string` |
| a dish in two lists | disliked > liked > mentioned | `dish_in_two_lists` |

**Rule 9, consistency.** Evidence of an opinion overrides the
`reference_only` flag, so each of these clears it:
- **Set aspects** (`reference_with_aspects`). The contract says this
  outright.
- **`is_negated`** (`reference_with_negated`).
- **A liked or disliked dish** (`reference_with_dish_verdict`).

The contract only states that a reference_only mention has neither of the
last two. Clearing the flag, rather than dropping the opinion, is this
harness's reading: each is something the commenter said, and dropping it
would lose the negative evidence the eval exists to catch.

## Adapter (`schema_v5.adapt_old`)

The adapter puts old-schema output into the contract: production's prompts,
the current prompt and rubric_v1. That way every baseline scores on the same
scorer, with no new calls.

- **Aspects:** floats → levels with `score.bucket`'s cut points (±0.167,
  ±0.5, ±0.833) → labels.
- **Bare endorsement:** food at level 1 (0.3, or rubric_v1's 0.33) with
  every other aspect null and no avoid becomes aspects null and
  reference_only false. A genuine "X is solid" also lands at food 0.3 in the
  old schema, and the two can't be told apart.
- **reference_only is derived:** every aspect null and no avoid. The old
  prompts gave every bare name food 0.3, so an all-null old mention is one
  the model recorded no judgment for. Old prompts never had the concept,
  though, so reference_only numbers for adapted runs are a derived reading.
  The reports say so.
- **Price from expensiveness, by level:** -1 or below is cheap, 0 is
  moderate, +1 or +2 is pricey, +3 is very_pricey.
- **Dishes:**
  - `dishes` goes to dishes_mentioned.
  - rubric_v1's `dish_sentiment` entries go to liked (level > 0) or disliked
    (level < 0, or avoid).
  - Runs without `dish_sentiment` report dish metrics as n/a.
- **Experience:** `is_firsthand` true/false/null → ate_there / secondhand /
  unclear.
- **value_complaint:** rubric_v1's own field is used for value-complaint
  recall where it exists.

To write v5 output into today's `mentions` columns, use
`schema_v5.to_production_floats`. It maps each label to its float and turns a
bare endorsement into food 0.3 exactly, which is what scoring_v2's bare-name
test reads.

## Gold v5 (`eval/v1/gold_v5.jsonl`, `eval/v2/gold_v5.jsonl`)

**Items.** Each item has the same keys as v1 gold (`item_id`, `comment_id`,
`thread_id`, `has_mention`, `mentions`, `note`, …), with `label_version: 3`.

**Mentions** carry two kinds of keys:
- **Unchanged metadata:** canonical_name, canonical_key, accept_keys,
  entity_type, out_of_scope, ambiguous, confidence, named_in,
  resolvable_comment_mode, resolvable_thread_mode, uncertain_fields,
  rationale, value_complaint.
- **The v5 fields, named as in the model output:** restaurant_raw,
  neighborhood_hint, reference_only, is_negated, price, experience,
  dishes_liked, dishes_disliked, dishes_mentioned and descriptors, plus
  aspects as label strings.

Two more keys:
- **`aspect_alternatives`:** maps a field to other acceptable values (null
  allowed). The scorer reads it for each aspect, for `price`, and for
  `experience`.
- **`judgment_question`:** true when semantic rule 2 applied.

**Removed:** dish_sentiment, dishes, is_firsthand, expensiveness, and numeric
aspects. A field named in `uncertain_fields` (is_negated, experience,
reference_only) isn't scored. `search_terms` is optional: where present, it
feeds search-terms recall. A closed place is recognized by "closed" in the
gold descriptors.

## What the scorer reports

The headline keeps score.py's priority order:
- comment drop rate
- mention recall
- negative-mention recall
- value-complaint recall
- dish-negative recall (gold dishes_disliked found in the model's
  dishes_disliked)
- sign accuracy and levels used

**v5 metrics:**
- reference_only P/R
- bare-endorsement P/R
- per-aspect presence F1, exact and within-one-level agreement (honoring
  alternatives)
- price presence and agreement
- dishes_liked and dishes_disliked P/R, plus any-dish recall across all three
  lists
- experience accuracy and its confusion matrix
- is_negated P/R
- judgment-question accuracy
- closed handling (matched, marked reference_only, with "closed" in
  descriptors)

**Run health:**
- parse-failure and error rates
- normalizer repairs per 100 mentions
- bad thread ids
- cost per call and per 1k comments
- latency p50/p90
- cache reads and writes

**Across `--repeat`:** every metric is mean ± sd, plus the rate at which a
required gold mention's found/missed status flips between reps.
