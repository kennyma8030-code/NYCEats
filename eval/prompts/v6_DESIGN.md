# Extraction v6: design note

v6 turns one r/FoodNYC comment, or a chunk of a thread, into structured
opinions: one entry per place per comment. It records the evidence and
leaves the scoring for later, which is still to be decided.

| file | what |
|---|---|
| `v6_schema.json` | strict JSON Schema, comment mode. Thread mode adds `id` (`v6_common.SCHEMA_THREAD`) |
| `v6_common.py` | shared prompt text, both schemas, `response_format` / Anthropic `output_config.format` helpers |
| `v6_comment.py`, `v6_thread.py` | the two system prompts, for `eval/run.py --prompt file:...` |
| `../v6_adapter.py` | maps v6 output to the shape the v1/v2 gold and v4 labels use. `score.load_run` and `v4/labels.py` call it automatically |
| `../v6_selftest.py` | offline checks: schema strictness, no eval text in the prompts, and 14 real gold comments scored through the adapter |
| `../../migrations/v6_mentions.sql` | storage draft. **Not applied.** |

To benchmark (the orchestrator does this; it needs `OPENROUTER_API_KEY`):

```bash
python eval/run.py --model M --mode comment --prompt file:eval/prompts/v6_comment.py [--schema]
python eval/run.py --model M --mode thread  --prompt file:eval/prompts/v6_thread.py  [--schema]
python eval/run.py --model M --mode comment --items eval/v4/items_single.jsonl --tag v4 --prompt file:eval/prompts/v6_comment.py
python eval/score.py eval/runs/<run>.jsonl          # v1 headline; v6 output is adapted on load
```

`--schema` sends the strict schema as `response_format` and only works on
providers that support `json_schema`. Without it, the run uses
`json_object`, as production does today. A schema run writes to its own
file (`..._schema.jsonl`). Keep reasoning on: commit 512c016 measured that
turning it off loses negations that point at the parent comment.

---

## The output

```json
{"mentions": [{
  "name": "Golden Lotus", "named_in": "context", "location": null,
  "experience": "firsthand", "opinion": "stated",
  "overall": "negative",
  "aspects": {"taste": "negative", "value": "negative", "service": null, "atmosphere": null, "wait": "negative"},
  "avoid": false,
  "dishes": [{"dish": "noodles", "level": "negative", "avoid": false}],
  "price": null, "timeframe": "current", "trend": null, "status": null,
  "tags": [],
  "notes": [{"about": "price", "text": "$24 a bowl", "level": "negative", "dish": "noodles"},
            {"about": "best time to go", "text": "go early, line by noon", "level": null, "dish": null}]
}]}
```

That is the prompt's own invented example, for a reply under "Golden Lotus
has the best hand-pulled noodles in Queens": *"lol no. noodles were gummy
and $24 a bowl is a joke. go early if you do go, line by noon"*.

Every property is required. "Nothing said" is `null` or `[]`, never a
missing key. That is what strict mode needs, and it means a downstream
reader never has to tell a missing key from an empty one.

## Fields

The examples are real r/FoodNYC comments. None of them is in any eval set
(v1, v2, top-ups or v4). Comment ids are given so a reader can check them.

| field | definition | real example |
|---|---|---|
| `name` | The name exactly as typed; never corrected or expanded. Copied from the context when the comment doesn't name the place. | *"Joes shouldn't be on the list and Rubi Rosa is too high"* (t1_njir37a): `"Rubi Rosa"`, not "Rubirosa". |
| `named_in` | `comment`, or `context` when the name came from the parent, an ancestor, the title or the body. Shows which mentions rest on reply attribution, the riskiest kind. | *"Used to be amazing pre covid. Now its kinda meh."* under "Gramercy Tavern" (t1_n9428u8): `context`. |
| `location` | Where the comment places this place. | *"The williamsburg one is the best one!"* (t1_p2newsp): `"williamsburg"`. |
| `experience` | `firsthand`: they went, or gave their own pick or verdict. `secondhand`: they repeat others. `none`: questions, "on my list", bare facts. | `firsthand`: *"I arrived a few mins after 4pm on a Thursday… the food wasn't at all memorable"* (t1_pgdrvqi). `secondhand`: *"I've heard great things about Takeda, but haven't been yet"* (t1_njjt6lg). `none`: *"Are they still cash only?"* (t1_pck88y8). |
| `opinion` | `none`: only neutral facts or a question. `endorse`: named as a pick with nothing said about it. `stated`: anything that judges. | `none`: *"Vanessa moved to UES"* (t1_nxnnpa6). `endorse`: *"Second this!"* under "I like Sushi by Bou for inexpensive omakase" (t1_nvl78cn). `stated`: *"Lucali is just really overrated for this."* (t1_ojnugks). |
| `overall` | The verdict on the place as a whole: is it worth going? It is its own judgment, not an average of the aspects. `null` when the comment gives no verdict. Always `positive` for an endorsement. | *"Prince street used to be IT. God tier. Went downhill SO much… It's not even in tier 2 anymore."* (t1_nnskhna): `negative`. *"Usually theyve been sold out by 5pm so you might wanna go earlier"* (t1_nf0fbw4): `null`, with wait `negative`. |
| `aspects.taste` | The food and drink. | *"The Khao Yum was pretty good, everything else meh."* (t1_nl6cnst): `neutral`, with the dish entry `positive`. |
| `aspects.value` | Worth the money, including portions for the price. | *"Makina is good but their portions are tiny for the price."* (t1_p1wjq1c): `negative`. |
| `aspects.service` | Staff, and how the place is run. | *"Waiter was rude… and then forgot to put in our order."* (t1_n9aoblb): `negative`. |
| `aspects.atmosphere` | Room, vibe, noise, crowd. | *"The Smith is SO LOUD."* (t1_o4x3tiq): `negative`. |
| `aspects.wait` | Lines, getting a table or reservation, slow food, selling out. | *"Been trying to go but it's impossible to get a res!"* under Le Veau d'Or (t1_odm85nw): `negative`. |
| `avoid` | The comment tells others to avoid the place. A bad review, or "I won't go back", is not enough. | *"The Smith is SO LOUD. Avoid it."* (t1_o4x3tiq): `true`. *"Used to love that place, now never going back."* (t1_n9aoblb): `false`. |
| `dishes` | Every dish or drink named for this place, with a level (`null` if only named) and `avoid` for "skip / don't get". | *"Superiority Burger is fantastic (just skip the burger)"* (t1_ogrbqmn): burger `avoid: true`. *"Spicy cumin lamb is the play."* (t1_omixdn4): `positive`. |
| `price` | How pricey, only when said in words: `very_cheap` … `very_expensive`. | *"Breads is pricey but the quality is always very good"* (t1_pfb25mg): `expensive`. *"Sushi kai… $85 i think"* (t1_nezwid0): `null`, with the figure kept in a note. |
| `timeframe` | `past` when the levels describe how it was, not how it is. | *"I loved alta, too, but it closed permanently."* (t1_o5w3ls8): `past`, overall `positive`, status `closed`. |
| `trend` | `declined` / `improved` when the comment says it changed. | t1_nnskhna above: `declined`. *"The speed has improved a lot since I last went"* (t1_n9yt7wi): `improved`. |
| `status` | `closed`, `moved`, `opened` (new or reopened). | t1_nxnnpa6: `moved`, location `"UES"`. |
| `tags` | The commenter's words for what the place is or is for: cuisine, format, occasion, diet, payment. | *"For chill group vibes, Shinzo Omakase… BYOB option available"* (t1_nacayj3): `["omakase", "byob", "group"]`. |
| `notes` | Everything else said about the place that no other field holds: `{about, text, level, dish}`. This includes the complaints no aspect covers (portion size, overrated, got sick, stopped making a dish), each with a plain `about` and its level. | *"I got so sad they stopped serving oxtail that I stopped going"* (t1_mwqt6af): `{"about": "stopped serving oxtail", "level": "negative"}`. *"very overrated. It has a very good publicist"* (t1_nsuni5l): overall `negative` plus `{"about": "overrated", "level": "negative"}`. *"The Modern is in InKind too"* (t1_o1rc19q): `{"about": "accepts InKind"}`. *"go on a weekday afternoon if you can. the line is significantly more manageable"* (t1_ouyftfe): `{"about": "best time to go"}`. Carmine's *"portions are HUGE, so even though prices might look high, divide everything by like two"* (t1_pcq6e7y): value `positive`, plus `{"about": "portion size", "level": "positive"}`. |
| `id` | Thread mode only: the bracket number of the comment. | |

## Levels

The owner's scale has five levels plus "not said": `very_positive`,
`positive`, `neutral`, `negative`, `very_negative`, and `null`. They are
words rather than numbers so the model can't drift to 0.4, and so a
bucket in a people-count means exactly one thing. Storage maps them to
-2…2 (see the migration).

| level | means | real examples |
|---|---|---|
| very_positive | superlative or emphatic | *"it is the best halal I've ever had"* (t1_n5qfnmv); *"L'industrie IS in fact fire"* (t1_njj4kjv) |
| positive | real praise | *"Quality Bistro is pretty solid"* (t1_mohzmwn); *"the quality is always very good"* (t1_pfb25mg) |
| neutral | a verdict that is middling or mixed | *"Hamburger America was fine. Not bad, not exceptionally good."* (t1_mpf6fit); *"Emmet's… Its decent."* (t1_n00ed52) |
| negative | any knock, however mild or polite | *"Rubirosa is mid"* (t1_njj4kjv); *"Lucali is just really overrated"* (t1_ojnugks) |
| very_negative | strong | *"used to be good then turned into slop"* (t1_ntcepjk) |
| null | not mentioned | |

**The boundaries that matter.** v5 lost negatives at these edges.

- **Neutral vs. positive.** Positive needs actual praise: "good", "pretty
  solid", "tasty", "worth it". "Not bad", "fine", "ok" and "decent" are
  neutral. v5 read them as mild praise. *"Hamburger America was fine. Not
  bad, not exceptionally good."* is neutral, not a weak positive.
- **Neutral vs. negative.** A word that disappoints or warns is negative:
  "mid", "overrated", "nothing special", "underwhelming", "not worth the
  hype". Acceptable without enthusiasm is neutral. A neutral word next to a
  knock is negative: *"It's not bad, but both times I've been I'm surprised
  at the hype"* (t1_mnwprq9) is negative, with an "overrated" note.
- **"meh" and "mid".** These are the closest call. v6 puts "meh" in neutral,
  following the v5 finding that grouped it with "fine". It puts "mid" in
  negative, because on this subreddit "mid" is a dismissal (the original
  prompt's "it's v mid" reply was its model negative). This is open question 1.
- **Price as a drawback.** *"The quality was fine, but it was a little
  pricey"* (t1_o72jfgb): taste neutral, price `expensive`, and, because of
  the "but", value negative. *"Pricey but so worth
  it"* (t1_n9xmub1) is price `expensive` and value positive.
- **Facts that are complaints.** `opinion: none` covers only neutral facts:
  cash only, BYOB, moved, closed, an address, a question, a hypothetical
  (*"if it's mid you're dead to me"*, t1_ns74zo4). These are judgments, not
  facts: reservations (*"impossible to get a res"*), lines, selling out
  (*"sold out by 5pm"*), portions for the price (value), stopped making
  something (a negative note). They are what v5's reference bucket
  swallowed.
- **`null` vs. `neutral`.** `null` is silence; `neutral` is a verdict.
  "Missing renders as absent, never neutral" (SPEC.md) holds all the way
  through.

## Judgment calls

1. **Endorsements get overall `positive`, with aspects `null`.** Naming a
   place as an answer is a yes. Tying it to `overall` keeps the field
   robust: if the model confuses "try X" (endorse) with "X is good"
   (stated), `overall` is still positive. `opinion` keeps the two apart,
   so scoring can count bare endorsements separately (open question 2).
2. **Generic praise goes to `overall`, not `taste`.** "X is amazing" sets
   overall only. Taste is set when the food is talked about ("best slice in
   the city" sets both). That keeps the Taste distribution about food. The
   adapter falls back to overall when scoring against the old gold, which
   put generic praise in food.
3. **`overall` is null when there is no verdict**, e.g. a timing tip. A
   comment that only complains about one thing still has a negative
   overall when that complaint reads as a verdict (rude service). The test
   is "is it worth going?".
4. **Losing a comparison gives no level.** "I prefer A over B" doesn't say
   B is bad, so B gets a note and no level. The v1 gold scored it -1 (open
   question 8).
5. **Closed places keep their remembered verdict**, with `timeframe: past`
   and `status: closed`. The old prompt threw the verdict away. Scoring can
   ignore past rows; it cannot recover deleted ones.
6. **`price` only from words.** A dollar figure goes into a note. Its
   meaning depends on the dish ($24 is cheap omakase and dear ramen), and
   v5 got this right. "Overpriced" is value, not a price level. Against the
   v1 gold this costs expensiveness presence (2 of 14 test comments).
7. **`avoid` means telling others.** "I won't go back" and bad reviews are
   not avoid instructions, the same rule as `is_negated`.
8. **No complaint list (owner's decision).** Complaints are counted
   through the aspects. A complaint no aspect holds (portion size,
   overrated, got sick, stopped making a dish) is a note with a plain
   `about` and a level, so it is kept but not forced into a category.
   Small portions for the price are value.
9. **`named_in`** costs a few output tokens per mention. It marks the
   nameless-reply mentions, which is where thread-mode attribution errors
   live.
10. **One mention per place per comment**, even when two branches are judged
    differently ("skip the Carmine St Joe's and go to the 14th st one",
    t1_nj027zy). The difference goes in `location` and notes.
11. **Out of scope:** supermarkets, apps and services (InKind is a note, not
    a place), and places outside NYC. *"Food poisoning central!"* about a
    place in Saugus (t1_of92lql) is not a mention. Chains are in scope;
    filtering them is a downstream decision.
12. **Thread mode can't fix the renderer, so it hedges.** The prompt says
    indentation can be wrong when siblings interleave, tells the model to
    pick the comment a reply plainly answers, and tells it not to guess when
    the parent isn't shown.

## Scoring v6 against the existing gold

`eval/v6_adapter.py` translates each mention once, inside `score.load_run`
(so `score.py`, `compare_v4.py` and `next_round.py` all see it) and inside
`v4/labels.py` (so labels written with the v6 prompt export as gold).
Production-shaped mentions pass through unchanged. Re-scoring a stored
DeepSeek run gives the same 0.872 negative-mention recall as before.

| v6 | gold / production shape |
|---|---|
| `name`, `location` | `restaurant_raw`, `neighborhood_hint` |
| levels | ±1, ±0.67, 0 (buckets to ±3, ±2, 0) |
| `taste`, else 0.33 for `endorse`, else `overall` | `food` |
| `status: closed` | every aspect null, `"closed"` in descriptors |
| `price` | `expensiveness` ±1, ±0.67, 0 |
| value negative | `value_complaint` |
| `avoid`, `experience == firsthand` | `is_negated`, `is_firsthand` |
| `dishes` | `dishes` (names) and `dish_sentiment` |
| `tags` | `descriptors` (search-terms recall) |

**Offline test** (`python eval/v6_selftest.py`). I hand-wrote v6 outputs
for 14 real v1 gold comments under the v6 rules: a bare list of 8, a
question, a closed place, a GrubHub tip, a walk-in tip, "never able to get
a reservation", a hearsay self-skip, "second this" in a worst-restaurant
thread, highway-robbery yogurt, a nameless "inedible", "service is
horrible, def not worth it", "skip lenwich", a $34 sandwich, and a
Super Burrito rant with a Chipotle comparison. Scored through the adapter:
recall 1.0, precision 1.0, negative-mention recall 1.0, value-complaint
recall 1.0, dish-negative recall 1.0, sign accuracy 1.0, is_negated and
is_firsthand accuracy 1.0, and food exact-level accuracy 0.93. The one
designed miss is expensiveness presence on the two comments that give only
a dollar figure. The test also lints the schema for strict mode, validates
every output and the prompts' own examples against it, checks the v4 label
path in both modes, and confirms that no eval comment shares a 7-word run
with either prompt.

Expect lower **exact-level** agreement than a 7-level prompt: five levels
cannot express the gold's -1/-2 split, so a gold "mid" (-1) reads as -2.
Sign, recall and the negative metrics are the comparable numbers. Where v6
calls "fine" neutral, v1 gold says -1, and that will show as a sign miss.
It is the owner's rule, not a model error.

## Cost

Estimated as characters ÷ 4, the same way for every prompt (there is no
tokenizer offline):

| prompt | system prompt |
|---|---|
| production `prompt.py` | ~1,820 tokens |
| production `prompt_thread.py` | ~2,170 |
| rubric_v1 comment / thread | ~1,910 / ~2,330 |
| **v6 comment / thread** | **~1,840 / ~2,180** |
| v5 (lost) | about 3× production |

The system prompt is about the same size as today's and is identical on
every call, so prefix caching (DeepSeek and OpenAI cache automatically;
Anthropic with `cache_control`) bills most of it at the cache rate. Where
v6 does cost more is **output**. A bare endorsement is 312 characters
(about 80 tokens), against 222 (about 55) today. A rich mention with
dishes and notes runs 480–700 characters (120–180 tokens). Output is priced at 2× input on
DeepSeek, so expect roughly 1.4–1.8× today's output bill per mention
before reasoning tokens. The benchmark run will give the real figure.

## Production gaps (not changed here)

1. **`length(c.body) > 15` drops real mentions** (`extract.py:169`,
   `:336`, and `extract_threads.py` in both queries). A read-only count:
   67,164 comments (8.9%) are 15 characters or fewer. **20,756 of them are
   nothing but a known place name** ("keens" ×149, "monkey bar" ×98,
   "balthazar" ×93, "minetta tavern" ×88), 19,295 of those top-level
   answers. That is the majority case, the bare rec, and it never reaches
   extraction. The rest include "second this" ×125, "this" ×387, "so good"
   ×98. Proposed fix: drop the filter, or lower it to `length(trim(body)) >= 2`,
   and let the model return `[]` for "thanks". It costs about 9% more calls in
   comment mode and almost nothing in thread mode. Whether "+1" counts as a
   person is open question 3.
2. **`db.insert_mentions` writes a fixed column list** (`db.py:142`). v6
   needs a writer that fills the new columns, `raw`, and the legacy columns
   (via the adapter mapping) so `scoring.sql` and `app/queries.py` keep
   working until they are rewritten.
3. **`response_format` is `json_object` with no schema** (`extract.py:102`).
   Use `json_schema` strict where the provider supports it. Otherwise
   validate against `v6_schema.json` locally and retry once on failure,
   as the parse retry does today.
4. **Chains are dropped at write time** (`extract.py:240`,
   `extract_threads.py:142`). That throws evidence away. Keep every row and
   filter chains at query time (`restaurants.is_chain`, or a `chains` table
   loaded from `chains.txt`), as `excluded_entities` already does
   (open question 5).
5. **`descriptors` is the only open field** (`prompt.py:37`). v6 adds
   `tags` (stored in `descriptors`), `notes`, and `raw` for everything else.
6. **Storage** is `migrations/v6_mentions.sql`: typed columns for every v6
   field (levels as smallint -2…2 with checks, `dish_opinions`, `notes`
   and `raw` as jsonb), plus `schema_version`. It
   does not change the unique key. It is tested on a throwaway local
   cluster: it applies, re-runs cleanly, and rejects out-of-range levels,
   and unknown enum values.
7. **The thread renderer** (`extract_threads.thread_rows`,
   `prompt_thread.build_message`). Replies are time-ordered within a root,
   so 9.75% sit under the wrong parent, and 11.5% have their parent in
   another chunk. The prompt can only hedge. The fix belongs in the renderer:
   - order depth-first within each root;
   - print an explicit parent, `[7 ↩3]` or `(reply to [3])`, and tell the
     prompt that marker is authoritative;
   - for a parent outside the chunk, print a one-line stub of it, e.g.
     `(replying to: "Keens is the move for…")`.

   That changes the thread-mode input, so v4's thread items would need
   re-rendering, which is why it isn't done here.

## Open questions for the owner

1. **What does neutral mean?** v6 makes neutral "a middling or mixed
   verdict": fine, ok, not bad, decent, meh, hit or miss. The v1 gold
   scored "fine" as a mild knock. Should "meh" be neutral or negative?
   Should a mixed verdict ("great food, awful service") have a neutral
   overall, or should overall follow the dominant side?
2. **Do bare endorsements count as "praised"?** The majority of mentions
   are a name given as an answer. v6 records them as `opinion: endorse`,
   overall positive. They could fill the praised bucket, get their own
   bucket ("recommended"), or count only toward volume.
3. **Do short replies count as people?** "+1", "this", "second this" and
   "agreed" are filtered out today (and so are 20,756 bare-name answers; see
   gap 1). If they count, a popular rec with ten "+1"s has eleven people
   behind it. Per-author caps and the thread divisor already exist to stop
   that from dominating.
4. **Should the original post be extracted?** Posts often carry a verdict
   ("went to X last night, it was mid, where should I go instead?"). Only
   comments are extracted now. Thread mode could send the post as `[0]`.
5. **Keep chains?** v6 emits them. Should they be stored and filtered at
   query time (recommended: nothing is lost), or still dropped at write?
6. **Should Taste count generic praise?** "X is amazing" currently sets
   only overall. If the owner reads Taste as "people who liked it", the
   prompt should copy generic verdicts into taste.
7. **Single-complaint verdicts.** Should "the service was rude" (and
   nothing else) count toward the overall negative distribution, or only
   toward Service?
8. **The comparison loser.** In "Leo over L'industrie", is that a mild
   negative for L'industrie (the v1 gold) or nothing (v6)?
9. **Past and closed opinions.** v6 keeps them with `timeframe: past`.
   Should they appear in the distributions, in history only, or nowhere?
10. **Secondhand opinions.** "Heard it's great" has `experience:
    secondhand`. Count it as a person, down-weight it, or show it apart?
11. **"Not worth it" as an answer to "which should I pick?"** Is that an
    avoid instruction (the v1 gold) or a negative review? v6 leaves it to
    context.
12. **Dollar figures.** v6 keeps them as notes. Should a later step turn
    them into a price level per category (a $30 sandwich vs. a $30
    omakase)?
