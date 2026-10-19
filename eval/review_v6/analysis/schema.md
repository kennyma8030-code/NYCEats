# Output schema and prompt structure for v7: let the structure catch mistakes

This looks at what the round-3 Opus review found wrong in Haiku 5.5's output (low
effort, strict JSON via `output_config.format`) and asks which changes to the
**shape** of the output would stop those mistakes, before any rule is reworded.
All counts come from the 542 real (unplanted) items in
`eval/review_v6/judgments/*.jsonl`, scored against the judges' `final` values,
and from the round-3 run file
`eval/runs/claude-haiku-5-5__6b046d8ed65d__comment__bench6-low-r3_schema.jsonl`.
No API calls were made.

## 1. Summary

The biggest finding is that the cheapest fixes aren't schema changes at all.
Four rules in `v6_common.py` contradict the rubric the judges used, and the
schema asks for `overall` before the evidence that should decide it. Fixing
those costs zero tokens. The structural change worth making after them is a
per-place list of **quoted claims, each tied to one aspect and one level**. The
model writes these first. Code then builds `aspects`, `opinion`, `experience`
and the notes from them. That removes four of the error patterns by
construction, and it costs about the same number of tokens as v6 (an estimated
-20 to +10 tokens per mention).

Ranked by expected benefit per output token (details in section 4):

| # | change | targets (errors in 542 items) | tokens per mention | verdict |
|---|---|---|---:|---|
| 1 | Make the prompt agree with the rubric (very_negative list, old visits, untried impressions, overall on a single aspect) | ~55 overall/aspect/timeframe errors | 0 | do first; owner must decide two of these |
| 2 | Move `overall` after the evidence (aspects, dishes, notes or claims) | ~26 "stated, overall null" + some flips | 0 | do |
| 3 | Rename levels so the label states the test: `superlative / praise / mixed / knock / extreme` | 55 of 103 very_* overturned; 17 dish over-scales | 0 | do |
| 4 | Merge `timeframe`, `trend`, `status` into one `change` enum; derive timeframe | 36 errors across the three | about -10 | do |
| 5 | `said`: quoted claims `{quote, about, dish, level}`, where an `info` claim can't carry a level; code derives aspects, opinion and notes | complaints only in notes (14 confirmed), aspect null→negative (26), opinion (57), notes wrong (23) | -20 to +10 | do; the main redesign |
| 6 | `ref`: the comment's own words for a place named only in the context (replaces `named_in`) | 15 of 25 spurious mentions are context-named (8% spurious rate vs 2.3% for names typed in the comment) | +2 average | do |
| 7 | Experience as evidence: `heard_from` (quote or null) + `not_been`; code derives experience | 80 experience errors (accuracy 0.86) | +5 | do; low product stakes, since the owner counts secondhand like firsthand |
| 8 | `kind` enum per place (restaurant ... grocery, brand, venue, company) | 11 to 13 grocery, brand and company false positives; turns the open Zabar's, food hall and jazz club questions into a switch in code | +5 | do |
| 9 | Top-level `places` inventory before details | ~15 of 22 misses that weren't caused by missing context (names in passing, comparison references) | +6 per place | try; smallest expected gain |
| 10 | Numeric -2..2 levels | none expected | 0 | don't |

Validators (section 6) cost nothing in tokens and work with the v6 schema
today. Two of them have measured precision of 0.80 or better on this review:
an opinion with `experience: none`, and a `very_*` level with no superlative or
extreme wording anywhere in the comment.

**Token economics.** Round 3 averaged 505 output tokens per comment: 256 of
reasoning and 249 of JSON. Only 48% of calls reasoned at all at low effort. The
JSON fits ≈ 37 + 169 tokens per mention, at 1.26 mentions per comment. At
$0.50/MTok, 10 more tokens per mention cost about $6 per million comments
($3 in batch). Dollars don't rank these options. What matters is whether each
added field helps or hurts a small model at low effort.

The data points one way. Calls that skipped reasoning made **1.22 errors per
mention** on single-place comments; calls that reasoned made 0.82. Simpler
comments are the ones that skip reasoning, so the true gap is probably larger.
In half the calls, the JSON is the only thinking the model does, so putting
evidence before verdicts gives those calls a short written reasoning step.

## 2. What actually goes wrong (542 real items, 615 Haiku mentions)

| pattern | count | example |
|---|---:|---|
| experience: own pick marked `none` | 44 | Q0101 Utopia, a pick in own voice; 20 of the 44 had `opinion: endorse` |
| experience: own pick marked `secondhand` | 23 | Q0213, a plain steakhouse list, all four marked secondhand |
| overall null despite a verdict | 54 | Q0408 "Noodle village for soup dumplings": dish positive, overall null; Q0177 Joe and the Juice: value negative, overall null |
| overall over-scaled to very_* | 25 | Q0050 "my favorite" → very_positive; Q0065 "sucks" → very_negative |
| overall positive for an untried impression | 14 | Q0004, Q0025 "looks tasty" (the rubric doesn't decide this case) |
| overall polarity flip | 7 | Q0370 list under "terrible restaurants with great reviews", then "I've always had great experiences here" |
| mention missed | 39 | 17 need wider context Haiku never saw; the rest are names in passing or reference points (Q0167 Peter Luger, Minetta, JG Mellon), comparison sides (Q0476 Chipotle) and context places asked about (Q0116 Di Palo's) |
| mention spurious | 25 | 11 grocery, brand or company (Zabar's ×2, H Mart ×2, Western Beef, Pomegranate, Grillo's, Unapologetic Foods ...), 2 outside NYC, 3 places only in the post (Q0357 Oases, Sweet Greens; Q0560), ~5 wrong referent, ~6 needing wider context |
| dish omitted | 26 | Q0086 "reg slice" kept only in a note; Q0258 Kwik's sauces only in a note |
| dish "X for the Y" or "get the X" left at null level | 12 | Q0295 ramen lists, Q0012 "you need to try their elote slice" |
| dish over-scaled | 17 | Q0001 "personal favorite, truly unique" → very_positive |
| complaint only in a note | 14 confirmed of 23 flagged | Q0258 Royal Grill "inconsistent" as a neutral note, taste neutral, overall positive |
| opinion none↔stated↔endorse | 57 | Q0210 "That's cool" → none; Q0185 a question → stated |
| timeframe past for an old visit | 11 | Q0153 Gramercy Tavern, an old visit with nothing changed (the prompt tells Haiku to say past here) |

Two patterns come straight from the prompt text, not from the model:

1. **very_negative.** `SCALE` lists "never again" and "regretted going" as
   very_negative. The rubric's calibration says those are negative. Of the 32
   overall very_negative values Haiku gave, 17 were overturned.
2. **Old visits.** `FIELDS.timeframe` says "a visit years ago with nothing
   about now" is past. The judges ruled it current in 11 cases.

Two more are owner decisions the judges split on. One is whether a lone aspect
judgment sets overall: the prompt's example "go early to beat the line has no
overall (null)" goes against the rubric's "overall follows the strongest
point", and rule questions Q0020, Q0132, Q0178, Q0223 and Q0392 all ask about
it. The other is whether "looks so good" about an untried place is stated or
none (Q0004, Q0025, Q0200, Q0438). No schema can fix a field while the rubric
and the prompt disagree on its definition. Settle these first, re-run round 3
(the whole run cost $0.15), and score the re-run against the existing finals
(section 8) as the baseline for the schema work.

## 3. Proposed v7 schema

Generation order is the order of `properties`: constrained decoding emits keys
in schema order. Check this on a sample, but every v6 output so far follows it.
Evidence comes first, then the verdict, then low-value fields at the end, so the
fields that matter are written while the model is still paying attention.

```json
{
  "type": "object",
  "properties": {
    "places": {"type": "array", "items": {"type": "string"}},
    "mentions": {"type": "array", "items": {"$ref": "#/$defs/mention"}}
  },
  "required": ["places", "mentions"],
  "additionalProperties": false,
  "$defs": {
    "level":   {"type": "string", "enum": ["superlative", "praise", "mixed", "knock", "extreme"]},
    "level_n": {"type": ["string", "null"], "enum": ["superlative", "praise", "mixed", "knock", "extreme", null]},
    "said": {
      "anyOf": [
        {"type": "object",
         "properties": {
           "quote": {"type": "string"},
           "about": {"type": "string", "enum": ["overall", "taste", "value", "service", "atmosphere", "wait"]},
           "dish":  {"type": ["string", "null"]},
           "level": {"$ref": "#/$defs/level"}},
         "required": ["quote", "about", "dish", "level"], "additionalProperties": false},
        {"type": "object",
         "properties": {
           "quote": {"type": "string"},
           "about": {"type": "string", "const": "info"},
           "dish":  {"type": ["string", "null"]}},
         "required": ["quote", "about", "dish"], "additionalProperties": false}
      ]
    },
    "dish": {
      "type": "object",
      "properties": {"dish": {"type": "string"}, "level": {"$ref": "#/$defs/level_n"}, "avoid": {"type": "boolean"}},
      "required": ["dish", "level", "avoid"], "additionalProperties": false
    },
    "mention": {
      "type": "object",
      "properties": {
        "name":       {"type": "string"},
        "ref":        {"type": ["string", "null"]},
        "kind":       {"type": "string", "enum": ["restaurant", "bar", "cafe", "bakery", "deli", "truck_or_cart",
                                                  "stall_or_food_hall", "gourmet_shop", "grocery", "brand",
                                                  "venue", "company", "other"]},
        "heard_from": {"type": ["string", "null"]},
        "not_been":   {"type": "boolean"},
        "pick":       {"type": "boolean"},
        "said":       {"type": "array", "items": {"$ref": "#/$defs/said"}},
        "dishes":     {"type": "array", "items": {"$ref": "#/$defs/dish"}},
        "overall":    {"$ref": "#/$defs/level_n"},
        "avoid":      {"type": "boolean"},
        "change":     {"type": ["string", "null"], "enum": ["declined", "improved", "closed", "moved", "opened", null]},
        "tags":       {"type": "array", "items": {"type": "string"}},
        "location":   {"type": ["string", "null"]},
        "price":      {"type": ["string", "null"], "enum": ["very_cheap", "cheap", "moderate", "expensive", "very_expensive", null]}
      },
      "required": ["name", "ref", "kind", "heard_from", "not_been", "pick", "said", "dishes",
                   "overall", "avoid", "change", "tags", "location", "price"],
      "additionalProperties": false
    }
  }
}
```

Thread mode keeps the integer `id` as the first mention property, as in v6.

**What code derives** (all rebuildable, as `CLAUDE.md` asks):

| v6 field | v7 source |
|---|---|
| `named_in` | `"context"` when `ref` is set, else `"comment"` |
| `aspects.X` | from the `said` claims with `about = X`: null if there are none; the strongest level if all are on one side (superlative over praise, extreme over knock); `neutral` if there are claims on both sides or any `mixed` |
| `opinion` | `stated` if any claim has a level or `overall` is set and `pick` is false; `endorse` if `pick` is true and no claim has a level; else `none` |
| `overall` | the model's value; `positive` for an endorsement (owner rule, enforced in code); for stated with null overall, the owner's policy (section 2) |
| `experience` | `secondhand` if `heard_from` is set; `none` if `not_been` or opinion is none; else `firsthand` |
| `timeframe` | `past` if `change = closed`, else `current` |
| `trend`, `status` | split from `change` |
| `notes` | every `said` quote, labeled with its `about`; `info` claims are the tips and facts |
| levels | `superlative→very_positive`, `praise→positive`, `mixed→neutral`, `knock→negative`, `extreme→very_negative` |
| dropped mention | `kind` in the excluded set (grocery, brand, venue, company, other, and per the owner's decision gourmet_shop and stall_or_food_hall), kept in a side table so a change of policy needs no re-extraction |

`mentions` and the five-level counts the product shows stay exactly as they
are. Only the intermediate form changes.

## 4. Each change: effect, cost, risk

### 4.1 Align prompt and rubric (0 tokens)

Change the `SCALE` very_negative line to "worst I've had", "inedible",
"disgusting", "got sick", "avoid at all costs". Add: '"never again",
"regretted going", "terrible", "sucks" and "disappointing" are knock, not
extreme.' Remove "a visit years ago with nothing about now" from timeframe; in
v7, timeframe is derived anyway. Then state the owner's decision on lone-aspect
overall and on untried impressions.

Expected effect: most of the 17 overturned overall very_negative values, the 11
past→current errors, and about 20 to 30 overall null/positive disagreements,
depending on which way the owner rules. Risk: none, beyond the decisions
themselves.

### 4.2 Overall after the evidence (0 tokens)

In v6, `overall` comes before `aspects`, `dishes` and `notes`, so the model
commits to a verdict before writing down what it read. Of the 54 "overall null
despite a verdict" errors, 26 came with `opinion: stated`, and in most of those
Haiku had set an aspect or dish level later in the same object (Q0408: five
places with positive dishes and null overall; Q0177: value negative, overall
null). With `overall` written last, the model has its own evidence in view.
Risk: very low. This is the same idea as "reason, then answer".

### 4.3 Level names that state the test (0 tokens)

Haiku used very_* 103 times and the judges overturned 55. `very_positive` reads
as "very enthusiastic", so "amazing", "to die for" and "bomb af" land there.
The owner's test is categorical: a broad superlative, or an extreme harm. Use
labels that *are* the test:

- `superlative`: "best in the city", "my favorite in NYC", "best I've ever had"
- `praise`: any real yes, however enthusiastic: "amazing", "to die for", "my favorite"
- `mixed`: good and bad weighed evenly
- `knock`: any complaint, however mild: "fine", "meh", "overpriced", "sucks", "terrible", "never again"
- `extreme`: "worst", "inedible", "disgusting", "got sick", "avoid at all costs"

`mixed` also stops `neutral` from inviting "fine/ok" (the rubric rule is that
lukewarm is negative), and `knock` says outright that mild counts. Code maps
the labels back, so the product's five levels don't change.

Options rejected:

- **Numeric -2..2.** It invites interpolation by intensity, the exact failure
  here, and a sign is easier to flip than a word.
- **raves / likes / mixed / dislikes / pans.** "Raves" is again a word about
  intensity.

Under-scaling is rare (6 cases), so a label that slightly discourages
superlatives costs little. Risk: a new label has no prior, and Haiku may fall
back to "praise" for real superlatives. Watch the under-scale count.

### 4.4 `said`: quoted claims mapped to an aspect (−20 to +10 tokens)

This replaces `aspects`, `notes` and `opinion` with one list written first:

```json
"said": [
  {"quote": "noodles were gummy", "about": "taste", "dish": "noodles", "level": "knock"},
  {"quote": "$24 a bowl is a joke", "about": "value", "dish": "noodles", "level": "knock"},
  {"quote": "go early if you do go, line by noon", "about": "wait", "dish": null, "level": "knock"}
]
```

What it prevents:

- **Complaints kept only in notes.** The `anyOf` makes an `info` claim
  level-less, so a complaint *can't* be filed as info with a level. To carry
  the level, it has to name an aspect or `overall`. Strict decoding enforces
  this; it's one of the few cross-field rules it can enforce.
- **Opinion confusion (57 errors).** Opinion is no longer a judgment the model
  makes; it falls out of whether any leveled claim exists and whether `pick` is
  set. "Stated with every level null" (6 cases, 5 wrong) becomes impossible.
- **Aspects set without evidence, and the reverse.** Every aspect level now has
  a quote. The 26 aspect null→negative misses are cases where the model read a
  complaint and never wrote it anywhere. Asking for "every judging phrase" is
  closer to how the model reads than filling a five-slot form.
- **Paraphrase errors in notes** (23 wrong). The text is now verbatim and
  links back to the comment, which the click-through rule wants anyway.
- **Over-scaling becomes checkable.** A `superlative` or `extreme` claim whose
  quote has no superlative or extreme word can be flagged per claim (section
  6), much more sharply than the comment-wide check measured below.

Cost: v6 spends about 88 tokens per mention on `aspects` (mostly five nulls),
`notes` and `dishes`. Converting the round-3 outputs to v7 shape gives about
223 JSON tokens per comment against 248 now, but that assumed 1.3 claims per
mention. At a realistic two claims of 8 to 10 words, the change is about -20
to +10 tokens per mention.

Risks:

1. **Quotes may get long or be paraphrased.** Say "the shortest span, at most
   10 words", and make the validator match fuzzily.
2. **The aggregation rule is a design decision.** "Great food, awful service"
   leaves taste praise and service knock, and overall stays the model's call.
   The neutral-on-conflict rule for one aspect needs the owner's nod.
3. **A bigger change for a small model.** A/B it against v6 plus 4.1 to 4.3 on
   the same 542 items before adopting it.
4. **Bare endorsements have no claims.** `pick: true` covers them. List items
   with a dish ("X for the Y") should produce a claim with `about: taste` and
   `level: praise`, which also fixes the 12 dish levels left at null.

### 4.5 `ref` instead of `named_in` (+2 tokens on average)

`ref` holds the COMMENT's words that point at a place whose name isn't in the
comment ("v mid", "the line is brutal", "hard disagree"); it is null when the
name is typed in the comment.

- `named_in` is already honest for names typed in the comment: 430 of 433
  were found in the comment text, and only 10 of them were spurious, all of
  them grocery stores or brands.
- Context-named mentions are where the trouble is: 15 of 182 (8%) were
  spurious.

The post-only places (Q0357 Oases and Sweet Greens, from the post body)
have no words in the comment, so the model has to either invent a `ref`, which
code catches because it isn't a substring of the COMMENT, or drop the place.
The wrong-referent cases (Q0544 Los Tacos, Q0550 Fedoroffs) become visible:
the `ref` shows which words were taken to mean which place.

Expected: catches the 3 post-attributed places and most of the ~5
wrong-referent ones. Nothing helps the 6 wider-context cases. Cost: about 2
tokens on the 70% of mentions with null `ref`, and about 8 when set. A
per-mention quote for names typed in the comment adds nothing, since the name
already grounds the mention. Risk: the model may refuse to extract real
unnamed replies. Watch context-mention recall; the prompt example has to show
`"ref": "lol no"`.

### 4.6 Experience as evidence (+5 tokens)

`heard_from` holds the words that credit someone else ("my friend swears by
it"), else null. `not_been` is true only if the comment says or shows they
haven't been.

- **Secondhand needs a quote.** Of the 43 `secondhand` outputs, 29 were wrong.
  The model can't write a credit quote that isn't there.
- **`none` without `not_been` becomes firsthand.** Code also applies "opinion
  ⇒ not none". Of the 59 mentions with `experience: none` and an opinion, 47
  were errors.

Expected: experience accuracy from 0.86 to about 0.95. The product stakes are
low, because the owner counts secondhand like firsthand. The fix is still
worth it, because these errors also shake the opinion field: 20 picks were
`none/endorse`. Risk: `not_been` may stay false for "looks good, will try";
section 6 has a check for want-to-try words.

### 4.7 `kind` enum (+5 tokens)

`kind` lists food-place types plus `gourmet_shop`, `grocery`, `brand`,
`venue`, `company` and `other`. Asking for the type makes the model classify a
place before treating it as one. Code drops the excluded kinds.

Expected:

- **False positives.** Removes most of the 11 grocery, brand and company
  cases; Haiku is not careless here, it simply never had to say what kind of
  place it was.
- **Open owner questions.** About 12 rule questions (Zabar's ×5, Smorgasburg
  and food halls, jazz and comedy clubs, Spin, Unapologetic Foods) become a
  set membership in code, and changing the policy needs no re-extraction.

Risk: Haiku labels a real deli as `gourmet_shop` and recall falls; check the
`kind` confusion on the 542 items. Places outside NYC (2 cases) stay a prompt
rule. A separate field isn't worth it.

### 4.8 `change` instead of `timeframe` / `trend` / `status` (about −10 tokens)

These three fields are null 94 to 97% of the time and account for 36 errors.
One enum covers declined, improved, closed, moved, opened or null. Timeframe
follows from `closed`, which removes the 11 past-for-an-old-visit errors along
with the field. The two lost combinations are both rare in this data:

- declined *and* closed;
- remembered from long ago *and* still open, which is current under the
  judges' rule.

Risk: small.

### 4.9 `places` inventory first (+6 tokens per place)

`places` lists every food-place name in the COMMENT, in order, plus any
context place the comment replies about, before any detail. It targets the
~22 misses that weren't caused by missing context: reference points
("JG Mellon style", "inspired by Peter Luger and Minetta"), comparison sides
(Chipotle), passing names (Ritz Diner) and the context place the comment asks
about (Di Palo's).

Truncation isn't the issue it was in round 1: all 600 round-3 calls ended
`end_turn`.

Validator: a place in `places` with no mention is flagged. Expected gain: a
few points of recall, from 0.94 to about 0.95. Risk: the model lists
non-places and then dutifully extracts them; `kind` mitigates this. Rank:
last among the "do" items.

### 4.10 What not to do

- **Don't drop `tags`, `location` or `price`.** They are about 11% of JSON
  tokens. `location` (24% non-null) helps identity resolution for chains and
  branches, and `tags` feed search. Move them to the end, where they cost
  attention only after the scored fields are written.
- **Don't add a per-mention free `reasoning` string.** The `said` quotes are
  that reasoning, in a checkable form.
- **Don't use `minLength`, `maxLength`, `minimum` or `maxItems`.** Structured
  outputs reject them; the Python SDK strips them and validates on the client,
  which turns a long quote into a parse failure.

## 5. What strict structured outputs can and cannot do

**Can.**

- Enums and `const`.
- Nullability.
- Key order, and so generation order.
- `anyOf` variants that couple fields within one object, as in `said` (an
  `info` claim has no level). The same trick could tie `pick` to `overall`,
  but derivation in code is simpler.
- Required presence of a quote string.

**Cannot.**

- **That a quote is really in the comment.** No substring constraint exists.
- **Consistency across fields or objects.** `overall` against claims, `avoid`
  against `overall`, `dishes` covering every claim's dish, `places` covering
  `mentions`, no duplicate places.
- **Numeric or length bounds,** and non-empty arrays tied to another field
  (such as "a stated mention has at least one claim").
- **Calibration.** The grammar permits `superlative` wherever the enum
  allows it.

Every `anyOf` and nullable union also adds grammar complexity. v6 already
carries about 14 nullable unions per mention, and v7 has about the same. Check
that the schema compiles before a batch run; the first request pays the compile
cost, and later ones use a 24-hour cache.

## 6. Post-processing validators

Each check below is cheap and runs on stored JSON. The measured ones were run
on v6 round-3 output against the judges' finals. "Precision" means the share
of flagged mentions where the flagged field was really wrong. "Auto-fix" means
safe to apply in production, and "flag" means show it in a review queue.

| # | check | flagged | precision | action |
|---|---|---:|---:|---|
| V1 | experience `none` but opinion is not `none` | 59 | **0.80** | auto-fix to firsthand |
| V2 | very_* level with no superlative or extreme wording in the comment (rough regex) | 57 of 103 very_* | fixes 40, breaks 17 | auto-downgrade in v6; per claim in v7 the quote makes it sharper |
| V3 | stated, overall null, some aspect or dish level set | 38 | 0.63 | fill overall from the strongest level, once the owner decides lone-aspect overall |
| V4 | a note with a negative level but no negative aspect, overall or dish | 23 | 0.61 | flag; impossible by construction in v7 |
| V5 | `secondhand` with no credit words in the comment (friend, heard, people say ...) | 36 | 0.72 (26 of 36 not secondhand) | flag only; in v7 a null `heard_from` decides it |
| V6 | stated with every level null and no dish level | 6 | 0.83 | set opinion none |
| V7 | `avoid: true` with overall positive | 1 | 1/1 | flag |
| V8 | `endorse` with overall not positive | 1 | 1/1 | auto-fix (owner rule) |
| V9 | a note's dish missing from `dishes` | 8 | 0.38 | add the dish with level null |
| V10 | overall on one side, aspects only on the other | 6 | **0.00** | don't use: "great but overpriced" stays positive |
| V11 | (v7) `ref` or any `said.quote` not found, fuzzily, in the COMMENT; found in the post or parent instead | — | — | drop the mention or claim: the place came from the post |
| V12 | (v7) `kind` in the excluded set | — | — | move to the side table |
| V13 | (v7) a `places` entry with no mention, or a mention not in `places` | — | — | flag |
| V14 | (v7) `not_been` false but the comment has want-to-try words ("want to try", "never been", "bookmarked", "looks") | — | — | flag |
| V15 | (thread mode) a quote found in a different comment of the thread than the mention's `id` | — | — | reassign or drop |

V10 is a useful negative result: when Haiku's overall disagreed with the sign
of its aspects, Haiku was right every time.

## 7. Prompt wording for v7

These replace `FIELDS` and `SCALE`. `SCOPE` and `RULES` stay, with the
wording changes listed at the end.

```text
Write each place's fields in this order. Write what the comment says first; the verdict comes last.

places      Before anything else: every food place the COMMENT names, in order, including names in a list, in passing, in a comparison or as a reference point ("JG Mellon style"), plus the place from the context that the comment replies about. Then one mention per place.
name        The name exactly as the comment types it. For a place the comment doesn't name, copy the name from the context.
ref         null when the name is in the comment. Otherwise the comment's own words that point at the place ("v mid", "the line is brutal", "hard disagree"), copied exactly. If no words in the COMMENT refer to it, it is not a mention: places only in the post or parent don't count.
kind        restaurant, bar, cafe, bakery, deli, truck_or_cart, stall_or_food_hall, gourmet_shop (a specialty food store), grocery (supermarket), brand (a packaged product), venue (club, theater, stadium), company (a restaurant group or business), other.
heard_from  The words that credit someone else ("my friend swears by it", "heard it's great"), copied exactly, else null. A pick or verdict in their own voice has none.
not_been    true only when the comment says or shows they haven't been: a question, "want to try", "never been", "bookmarked". Otherwise false.
pick        true when the place is named as a recommendation or an answer with no word of judgment: a plain list item, "try X", "second this" under a rec.
said        Every phrase that judges the place or tells something about it, each as {"quote", "about", "dish", "level"}:
              quote  the shortest exact span from the COMMENT, at most 10 words.
              about  overall, taste (food and drink), value (worth the money, portions for the price), service (staff, how it's run), atmosphere (room, vibe, noise, crowd), wait (lines, booking, slow food, selling out); or info for a tip or fact with no judgment ("cash only", "$24 a bowl", "go before noon"). An info item has no level, so a complaint is never info.
              dish   the dish or drink the phrase is about, else null.
              level  see LEVELS.
            "X for the Y" or "get the Y" in a list is {"about": "taste", "dish": "Y", "level": "praise"}.
dishes      Every dish or drink named for this place, in said or anywhere else: {"dish", "level" (null if only named), "avoid" (true for "skip the X")}.
overall     Last, after said: the bottom line ("worth it", "skip it", "never going back"), else the strongest point in said. null only when said has no level and pick is false. A pick is praise.
avoid       true only when the comment tells others to avoid the place.
change      declined or improved when it says the place changed; closed, moved or opened (new or reopened); else null.
tags, location, price    as before.

LEVELS
  superlative  only a superlative about this place against a broad class: "best in the city", "best X I've ever had", "my favorite in NYC", "one of the best meals of my life"
  praise       any real yes, however enthusiastic: "good", "amazing", "to die for", "bomb", "my favorite", "my go-to", "a must", "get the X"
  mixed        good and bad weighed evenly: "hit or miss". Never for lukewarm words.
  knock        any complaint, however mild, polite or strong: "fine", "ok", "meh", "mid", "overrated", "overpriced", "rude", "sucks", "terrible", "disappointing", "never again", "regretted going", "the line is insane"
  extreme      only these: "worst I've had", "inedible", "disgusting", "got sick", "avoid at all costs"
```

Changes to RULES:

- Rule 2 becomes: "Every complaint is a said item with an aspect or overall
  and a knock or extreme level, never info."
- Rule 4 drops the opinion vocabulary: "A remark that judges the place is a
  said item; pick is only for a bare name."
- Rule 10's "timeframe past" becomes "change closed".
- Add the owner's decisions from 4.1.

The worked example becomes:

```json
{"places":["Golden Lotus"],"mentions":[{"name":"Golden Lotus","ref":"lol no","kind":"restaurant","heard_from":null,"not_been":false,"pick":false,"said":[{"quote":"lol no","about":"overall","dish":null,"level":"knock"},{"quote":"noodles were gummy","about":"taste","dish":"noodles","level":"knock"},{"quote":"$24 a bowl is a joke","about":"value","dish":"noodles","level":"knock"},{"quote":"go early if you do go, line by noon","about":"wait","dish":null,"level":"knock"}],"dishes":[{"dish":"noodles","level":"knock","avoid":false}],"overall":"knock","avoid":false,"change":null,"tags":[],"location":null,"price":null}]}
```

Add a second invented example showing:

- a `pick` with empty `said`;
- an `info` item;
- a name in passing with `said: []` and `pick: false`;
- a grocery with `kind: grocery`.

## 8. How to test it cheaply

1. The 542 judged items already have a final value for every scored field.
   A new run can be scored by code against those finals; extend
   `judgments.py`, or write a small scorer that maps v7 to v6 with the
   derivations in section 3. That needs no new judging, except for mentions
   the new run finds that no judge listed: send only those to a judge.
2. Run the arms in order, each about $0.15 for 600 comments in batch:
   1. v6 with the prompt fixes from 4.1;
   2. plus 4.2 and 4.3;
   3. full v7.

   Report field accuracy, negatives caught, mention recall and precision,
   reasoning tokens and visible JSON tokens per mention.
3. Run each arm twice. Round 3's error rates are small counts (for example 25
   spurious mentions), and run-to-run noise at low effort may be comparable to
   some of the expected gains.
4. Owner decisions in section 2 have to land before arm 1. Otherwise the
   finals and the prompt measure different things.
