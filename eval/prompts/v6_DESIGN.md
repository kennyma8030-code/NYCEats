# Extraction v6: design note

v6 turns one r/FoodNYC comment, or a chunk of a thread, into structured
opinions: one entry per place per comment. It records the evidence and
leaves the scoring for later, which is still to be decided.

| file | what |
|---|---|
| `v6_schema.json` | strict JSON Schema, comment mode. Thread mode adds `id` (`v6_common.SCHEMA_THREAD`) |
| `v6_common.py` | shared prompt text, both schemas, `response_format` / Anthropic `output_config.format` helpers |
| `v6_comment.py`, `v6_thread.py` | the live system prompts (round 2), for `eval/run.py --prompt file:...`. `v6_thread.py` also has its own chunk renderer, `render_chunk`. `v6_comment.py` also has post mode: `SYSTEM_PROMPT_POST` and `build_post_message` |
| `v6r1_common.py`, `v6r1_comment.py`, `v6r1_thread.py` | round 1, frozen exactly as benchmarked (hashes a15cfb978cce / 44e1a49c7781). Benchmark steps a–k run on these |
| `../CONVENTIONS.md` | the owner's conventions, one rule per case, and where the v1/v2 gold disagrees |
| `../labels/proposed_convention_patches.py` | candidate gold patches for those conventions. **Not applied** |
| `../v6_adapter.py` | maps v6 output to the shape the v1/v2 gold and v4 labels use. `score.load_run` and `v4/labels.py` call it automatically |
| `../build_thread_rows.py` | read-only: fetches the raw rows behind every thread chunk and writes `<items>.thread_rows.jsonl`, verified byte for byte against production's renderer |
| `../items.thread_rows.jsonl`, `../v2/items.thread_rows.jsonl`, `../v4/items_{single,thread}.thread_rows.jsonl` | those rows (1,032 chunks, all verified), committed so a benchmark needs no database |
| `../v6_selftest.py` | offline checks: schema strictness, no eval text in the prompts, 20 real gold comments and 5 rendered thread comments scored through the adapter, and the renderer checked on every real chunk |
| `../../migrations/v6_mentions.sql` | storage draft. **Not applied.** |

To benchmark (the orchestrator does this; it needs `OPENROUTER_API_KEY`):

```bash
python eval/run.py --model M --mode comment --prompt file:eval/prompts/v6_comment.py [--schema]
python eval/run.py --model M --mode thread  --prompt file:eval/prompts/v6_thread.py  [--schema]
python eval/run.py --model M --mode comment --items eval/v4/items_single.jsonl --tag v4 --prompt file:eval/prompts/v6_comment.py
python eval/score.py eval/runs/<run>.jsonl          # v1 headline; v6 output is adapted on load
```

In thread mode `run.py` re-renders every chunk with `render_chunk` from the
committed `.thread_rows.jsonl` file next to the items file (only when the
prompt module defines `render_chunk`; the stored rendering is untouched for
every other prompt). The renderer renumbers comments, so each run record
keeps the `id_map` it used.

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
| `opinion` | `none`: only facts or a question, no judgment at all. `endorse`: offered as a pick with nothing else said. `stated`: anything else that judges, however briefly. | `none`: *"Vanessa moved to UES"* (t1_nxnnpa6). `endorse`: *"Second this!"* under "I like Sushi by Bou for inexpensive omakase" (t1_nvl78cn). `stated`: *"Lucali is just really overrated for this."* (t1_ojnugks). |
| `overall` | The verdict on the place as a whole: is it worth going? It is its own judgment, not an average of the aspects. `null` when the comment gives no verdict. Always `positive` for an endorsement. | *"Prince street used to be IT. God tier. Went downhill SO much… It's not even in tier 2 anymore."* (t1_nnskhna): `negative`. *"Usually theyve been sold out by 5pm so you might wanna go earlier"* (t1_nf0fbw4): `null`, with wait `negative`. |
| `aspects.taste` | The food and drink. | *"The Khao Yum was pretty good, everything else meh."* (t1_nl6cnst): `negative` (the rest is "meh"), with the dish entry `positive`. |
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
| very_positive | a superlative about this place against a broad class | *"it is the best halal I've ever had"* (t1_n5qfnmv) |
| positive | real praise, a clear yes, including "great", "amazing", "my favorite", "a must" | *"Quality Bistro is pretty solid"* (t1_mohzmwn); *"the quality is always very good"* (t1_pfb25mg); *"L'industrie IS in fact fire"* (t1_njj4kjv) |
| neutral | a balanced verdict, good and bad weighed evenly | *"The service was great and everyone was welcoming, but the food wasn't at all memorable"* (t1_pgdrvqi): overall `neutral`, with service `positive` and taste `negative` |
| negative | any knock, however mild or polite, lukewarm words included | *"Rubirosa is mid"* (t1_njj4kjv); *"Lucali is just really overrated"* (t1_ojnugks); *"Hamburger America was fine. Not bad, not exceptionally good."* (t1_mpf6fit) |
| very_negative | strong | *"used to be good then turned into slop"* (t1_ntcepjk) |
| null | not mentioned | |

**The boundaries that matter.** v5 lost negatives at these edges.

- **Lukewarm is negative.** "Fine", "ok", "not bad", "meh" and "mid" are
  knocks on this subreddit, so they are `negative`, never positive and
  never neutral. v5 read "not bad" as mild praise, and a first draft of v6
  called these words neutral. Both lose negatives. The gold, and the
  benchmark's "meh" bucket, score them as a mild knock (−1): "meh" is −1 in
  8 of 11 v1/v2 gold mentions, and "not bad" in both. A neutral reading also
  reproduces the benchmark's "scored mixed" misses. *"Hamburger America was
  fine. Not bad, not exceptionally good."* is negative.
- **Positive needs real praise.** "Good", "pretty solid", "tasty", "worth
  it". "Decent" is not listed either way; in the gold it is mostly a weak
  yes, and the model reads it in context.
- **Very positive is rare (round 2).** Only a superlative about this place
  against a broad class: "best in the city", "best X I've ever had", "my
  favorite in NYC", "god tier", "life-changing". "Great", "amazing", "so
  good", "love it", "my favorite", "my go-to" and "a must" are positive, and
  so is every item under a "My favorites:" heading. This follows the gold,
  where "my favorite" and a favorites header are +2 and only a broad
  superlative is +3. Round 1 called 107 of the gold's 314 +2 food mentions
  very_positive.
- **Neutral is a balance.** Use it only when good and bad are weighed evenly:
  *"The service was great… but the food wasn't at all memorable"*
  (t1_pgdrvqi) is overall neutral, service positive, taste negative. A
  lukewarm word next to a knock is just negative: *"It's not bad, but both
  times I've been I'm surprised at the hype"* (t1_mnwprq9) is negative, with
  an "overrated" note.
- **Price as a drawback.** *"The quality was fine, but it was a little
  pricey"* (t1_o72jfgb): taste neutral, price `expensive`, and, because of
  the "but", value negative. *"Pricey but so worth
  it"* (t1_n9xmub1) is price `expensive` and value positive.
- **Facts that are complaints.** `opinion: none` covers only neutral facts:
  cash only, BYOB, moved, closed, an address, a question, a hypothetical
  (*"if it's mid you're dead to me"*, t1_ns74zo4). These are judgments, not
  facts: reservations (*"impossible to get a res"*), lines, selling out
  (*"sold out by 5pm"*), portions for the price (value), something no
  longer made in house (taste), stopped making a dish (overall, plus a
  note). They are what v5's reference bucket swallowed. Every complaint
  has to lower some level; a note alone never carries one, because nothing
  counts a note as a negative.
- **`null` vs. `neutral`.** `null` is silence; `neutral` is a verdict.
  "Missing renders as absent, never neutral" (SPEC.md) holds all the way
  through.

## Judgment calls

1. **Endorsements get overall `positive`, with aspects `null`.** Naming a
   place as an answer is a yes. Tying it to `overall` keeps the field
   robust: if the model confuses "try X" (endorse) with "X is good"
   (stated), `overall` is still positive. **Owner decision:** a bare
   endorsement counts as "praised". `opinion` still keeps the two apart.
2. **Generic praise goes to `overall`, not `taste`.** "X is amazing" sets
   overall only. Taste is set when the food is talked about ("best slice in
   the city" sets both). That keeps the Taste distribution about food. The
   adapter falls back to overall when scoring against the old gold, which
   put generic praise in food.
3. **`overall` is null when there is no verdict**, e.g. a timing tip. A
   comment that only complains about one thing still has a negative
   overall when that complaint reads as a verdict (rude service). The test
   is "is it worth going?".
4. **The loser of a comparison gets a level (owner decision), and a shared
   trait carries over.** "I prefer A over B" makes B negative by default.
   B is very_negative when the comment says it is far worse, and positive
   when the comment says both are good ("both great, I just prefer A").
   Each side carries a note with the comparison. The gold already scores
   losers negative (CONVENTIONS.md). "As hard to book as X" makes X wait
   negative; that was the Sushi Sho miss.
5. **Closed places keep their mention and their remembered verdict**, with
   `timeframe: past` and `status: closed`. **Owner decision:** scoring
   excludes closed places from rankings but keeps their pages. Past-only
   opinions count, dated by the comment. "Used to be great, now mid" counts
   the current verdict.
6. **`price` only from words.** A dollar figure goes into a note. Its
   meaning depends on the dish ($24 is cheap omakase and dear ramen), and
   v5 got this right. "Overpriced" is value, not a price level. Against the
   gold this costs expensiveness presence (3 of the 20 test comments).
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
12. **Thread mode brings its own renderer** (next section) instead of
    asking the model to repair production's. The prompt trusts the explicit
    reply marker and skips a reply whose place it still can't identify,
    rather than guessing.
13. **Never default to positive.** Only a bare pick is `endorse`. A place
    named with any remark is `stated` and leveled by what was said. This
    keeps the named-as-an-answer default from turning a knock positive.

## The Haiku 5.5 benchmark of v5: issue → cause → fix

These issues come from the benchmark page: Haiku 5.5 with the v5 prompt
against Haiku 5.5 with the current prompt, on the v1, v2 and v4 sets. The
"self-test" column names the real gold comments in `v6_selftest.py` that
show each fix offline. Whether a model actually follows the rules can only
be measured by the paid benchmark.

| # | issue | cause | v6 fix (prompt text) | self-test |
|---|---|---|---|---|
| 1 | Negative recall 0.87 → 0.71 (comment mode). Reference-only precision 0.573. Misses: Sushi Sho "extremely hard to get a reservation", Monkey Bar "never able to get a reservation", Edward's "aren't making it in store". | A reference bucket accepted facts that carry a complaint. Nothing forced a complaint into a level. A place used as a yardstick ("tie with Sho") had no way to inherit the trait. | RULES 1: *opinion "none" is ONLY for facts and questions with no judgment at all. A complaint put as a fact is stated, with a negative level: "impossible to book" and "they sell out by noon" are wait negative; … "the sauce comes from a jar now" is taste negative.* RULES 2: *Every complaint lowers a level: the aspect it is about, or overall when none fits. A note … never holds a complaint alone.* RULES 5: *Shared traits carry over: "as hard to book as X" is wait negative for X too.* | c0038 Monkey Bar, c0185 Edward's, v0065 Sho: all negatives hit |
| 2 | "Not bad" read as a mild positive where the gold says meh (−1). | Lukewarm words read as praise (v5) or as neutral (v6's first draft). | SCALE, negative: *any knock, however mild or polite, lukewarm words included: "fine", "ok", "not bad", "meh", "mid", …*; neutral: *Never for lukewarm words.* RULES 3: *Lukewarm is negative.* | c0155 "They're not bad. But Tal is a million times better": negative hit |
| 3 | Missed negatives came back "scored positive" (v2 comment: 10, against 3 with the current prompt; thread: 13) or "scored mixed". 8–16 per set were not extracted at all. | The named-as-an-answer default applied to places that had a remark; praise elsewhere in the comment ("the dosa was amazing") outweighed the knock; the mixed level absorbed lukewarm knocks. The current prompt (0.87) limits its default to "a name with nothing said about it" and says "use the whole negative half of the scale"; v5 lacked both. Unextracted: thread rendering (issue 4) and skipped short replies. | RULES 4: *Never default to positive. "endorse" is only for a name offered as a pick with nothing else said. A place named in a comparison, as an example, in a question or with any remark is "stated" and leveled by what is said. A complaint replying to a rave is still a complaint.* `opinion` field: *"stated": anything else that judges the place, however briefly.* Neutral only for a balance. RULES 7: *A complaint about one dish is a negative dish entry, even when the place is praised.* RULES 12 (never soften) is kept. Thread intro: *Go through EVERY comment, one-word replies included.* | v0119 Semma (scored positive by the original model), v0364 moms, v0373 L'industrie: negatives hit, no sign error |
| 4 | Thread mode: negative recall 0.684 (Claude's ceiling 0.922), mention recall 0.932 (0.978), dish-negative recall 0.40 (comment mode ~0.52), precision 0.904 (0.941). | The renderer. 9.75% of replies are drawn under the wrong parent. 11.5% have their parent in another chunk. 17,202 replies answer a parent of 15 characters or fewer, never rendered (usually a bare name like "Carbone"). Comments are cut at 700 characters (4.9% of text lost) and the post body at 400. | `v6_thread.render_chunk`: depth-first order, an explicit *(reply to [n])* that the prompt says to trust over position, a quoted one-line stub for a parent outside the chunk, comments cut at 1,500 and the post at 800. Prompt section READING THE COMMENTS. RULES 7 for dish knocks. | All 10,447 in-chunk markers in the 1,032 real chunks point at the true parent. t003/0: the misordered "I LOVE their pickled mango" now answers Pickle Guys. t001/0 [25] "Its overpriced produce in liquid form" now shows its 14-character parent and scores value negative |
| 5 | Thread mode slow: ~25 s and ~6.7k reasoning tokens per chunk. | The model rebuilds the tree from indentation and second-guesses it, because the old prompt warned that indentation can be wrong. | The explicit markers make attribution a lookup. Prompt: *Read the comments once, in order. A comment's own words and the comment it answers are all you need; most comments name no place and need no deliberation.* Reasoning stays on. | Cannot be measured offline |
| 6 | Value-complaint recall 0.80 with v5 against 0.98 with the current prompt (v1 comment). | Money remarks were kept as price facts or references. | RULES 6: *Money complaints are value negative: "overpriced", "not worth the money", "for the price", "$28 for that is a joke". The dollar figure also goes in a note.* `price` field: *"overpriced" is value, not price.* | c0045, c0049, c0064, c0084, c0205, t001/0[25] hit. c0155 is a deliberate miss: "80% normal bagel size" says nothing about price, so under the owner's rule it is a portion note, not value |
| 7 | v5 prompt ~3× the current one. | | v6 comment ~2,050 tokens (1.12× `prompt.py`), thread ~2,450 (1.13× `prompt_thread.py`). | |

## Thread mode rendering

`render_chunk` keeps production's chunk membership (the same comments in
the same chunk, so every run stays comparable with earlier ones), and
changes only how a chunk is drawn. Here is v1 t003, chunk 0 (lines cut).
Production:

```
[1] u/guatemamaLF: I used to go to my neighborhood deli … Jacob's Pickles and The Pickle Guys …
  [2] u/aalliias: A bucket of pickles sounds heavenly
  [3] u/Relative_Prize9052: I like pickle guys fruit, oddly enough. Other stuff seems average …
  [4] u/bfume: Jacob's needs snacking/crunching pickles. …
    [5] u/helcat: The Pickle Guys is the first time I've ever had pickled pineapple. …
    [6] u/bmsa131: I LOVE their pickled mango. 🥭
```

Here [5] and [6] answer [3] (Pickle Guys) but are drawn under [4] (Jacob's),
so a model files the mango praise against Jacob's. v6:

```
[1] u/guatemamaLF: I used to go to my neighborhood deli … Jacob's Pickles and The Pickle Guys …
  [2] u/aalliias (reply to [1]): A bucket of pickles sounds heavenly
  [3] u/Relative_Prize9052 (reply to [1]): I like pickle guys fruit, oddly enough. …
    [4] u/helcat (reply to [3]): The Pickle Guys is the first time I've ever had pickled pineapple. …
    [5] u/bmsa131 (reply to [3]): I LOVE their pickled mango. 🥭
  [6] u/bfume (reply to [1]): Jacob's needs snacking/crunching pickles. …
```

A parent outside the chunk, including the short ones production never
draws, is quoted:

```
[20] u/villagevigaro (reply to u/ENYVan, not in this chunk: "Carbone"): THIS! Super whatever food at an insane price point
```

Across the 1,032 eval chunks the renderer writes 10,447 in-chunk reply
markers, 904 stubs for parents in another chunk, 507 for parents too short
to be drawn, and 45 "reply to a deleted comment". Input grows 15%: 4,327
characters a chunk against 3,777, about 171 tokens per comment against 150
counting the system prompt. The cached system prompt is most of that.

**Chunk size stays 25**, for three reasons. The stubs remove the main
reason to shrink chunks: a reply no longer needs its parent inside the
chunk. Smaller chunks pay the system prompt more often. And keeping
production's boundaries keeps the benchmark comparable. If the benchmark
shows reasoning per chunk still near 6.7k tokens, try 15 next.

**What production would need** (in `extract_threads.py`, not changed here):
1. Select `parent_comment_id` in `thread_rows`.
2. Fetch each chunk's outside parents in one query, with no length filter,
   so short and deleted parents get a stub.
3. Order the pending rows depth-first within each root before cutting
   chunks, and prefer cutting at a root boundary.
4. Render with `render_chunk`, and map the model's ids back through the
   id map it returns instead of the short-id enumeration in `fetch_chunk`.
5. Raise `MAX_COMMENT_CHARS` to 1,500 and `SELFTEXT_LIMIT` to 800.

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
under the v6 rules for:
- 16 real v1 gold comments: a bare list of 8, a question, a closed place, a
  GrubHub tip, a walk-in tip, "never able to get a reservation", a hearsay
  self-skip, "second this" in a worst-restaurant thread, highway-robbery
  yogurt, a nameless "inedible", "service is horrible, def not worth it",
  "skip lenwich", a $34 sandwich, a Super Burrito rant with a Chipotle
  comparison, Edward's "aren't making it in store", and "they're not bad";
- 4 v2 gold comments: Sushi Sho, and three where the original model scored
  a knock positive;
- 5 comments from two real v1 thread chunks rendered by `render_chunk`
  (misordered replies, and a reply to a short parent in another chunk),
  mapped back through its id map.

Scored through the adapter: recall 1.0, precision 1.0, negative-mention
recall 1.0, dish-negative recall 1.0, sign accuracy 1.0, is_negated and
is_firsthand accuracy 1.0. Value-complaint recall is 0.86. Its one miss,
c0155, is by design: a portion complaint with no price is a note. The other
designed miss is expensiveness on the three comments that give only a
dollar figure.

The test also:
- lints the schema for strict mode;
- validates every output and the prompts' own examples against it;
- renders an invented chunk and compares the exact text;
- renders all 1,032 real chunks and checks that membership is unchanged and
  every reply marker names the true parent;
- checks the v4 label path in both modes;
- confirms no eval comment shares a 7-word run with either prompt.

Expect lower **exact-level** agreement than a 7-level prompt: five levels
cannot express the gold's −1/−2 split, so a gold "mid" (−1) reads as −2.
Sign, recall and the negative metrics are the comparable numbers.

## What only the paid benchmark can settle

- Whether Haiku 5.5 (or any model) follows the tightened rules. The
  offline test shows the rules and adapter produce the right scores when
  followed, not that they will be followed.
- **Prompt against mode in thread mode.** The v5 page compares Haiku + v5
  with Haiku + the current prompt in comment mode, but thread mode has no
  Haiku + current-prompt baseline. Without one, a thread-mode change can't
  be split between the prompt and the mode. Run Haiku with the current
  prompt in thread mode on the stored rendering, then Haiku + v6 thread. A
  third run (v6 rules on the stored rendering) would isolate the renderer,
  but it needs a v6 prompt variant without the marker text, so I haven't
  built it.
- Reasoning tokens and latency per chunk with the new rendering (`run.py`
  records `reasoning_tokens` and `latency_s`).
- Whether lukewarm → negative over-counts negatives against the v4 Claude
  labels. Those labels follow whatever prompt the labelers get.
- Output-token growth per mention.

## Owner decisions (round 2)

- **Comparison losers** get a level (judgment call 4).
- **Question replies and asides.** A reply that only asks about a place, or
  names it in passing, counts as a mention with `opinion: none` and no
  levels, and nothing more. The scorer no longer counts these as false
  positives when the gold lacks them, in either mode (CONVENTIONS.md).
- **Bare endorsements** count as "praised" (judgment call 1).
- **Secondhand opinions count the same as firsthand.** The prompt is
  unchanged: `experience` records the difference, and scoring treats
  secondhand and firsthand alike.
- **Closed and past** (judgment call 5). Closed places keep their mentions,
  and rankings exclude them. Past-only opinions count, dated by the comment.
- **The original post is extracted** (post mode, below).
- **Prompt fixes from the benchmark**, in v6_common.py:
  - very_positive only for broad superlatives;
  - line and timing tips are wait negative;
  - every named place counts, landmarks, comparisons and examples included;
  - names are kept as the comment types them ("2nd Ave");
  - a verdict in the commenter's own voice is firsthand.

## Post mode

`v6_comment.py` has a second system prompt, `SYSTEM_PROMPT_POST` (hash
6826c6c98013), and `build_post_message(title, selftext)`. The post's title
and body are the text to extract from, the poster is the author, and every
field and rule is the same. A place the post only asks about ("is X worth
it?") is a mention with `opinion: none`. The body is cut at 4,000
characters. Posts average about 1,100 characters, and a post is extracted
once.

**What production needs** (not built):
1. A pass over `threads` with non-empty `selftext` that aren't extracted
   yet. The migration draft adds `extracted_at`, `extracted_with` and
   `extract_error` to `threads`, the same cursor comments use.
2. Mentions stored with the post: the draft adds `mentions.thread_id`
   (a foreign key to `threads`), makes `comment_id` nullable, and checks that
   exactly one of the two is set. A post-only unique index mirrors the
   comment one. Downstream joins that go through `comments` (author, score,
   permalink, `was_deleted_later`) need a post branch through `threads`.
   The post's permalink comes from its id.
3. Thread mode can keep sending the post as context. Extracting it there as
   `[0]` would mix two rules in one prompt, so posts stay a separate pass.

**Eval items for posts don't exist yet.** To add some:
- draw posts the same way as v4's round 1, read-only from the live
  database: random plus targeted (titles that name a place; bodies with
  verdict words);
- write items of a new `kind: "post"` whose input is `build_post_message`;
- label them with Claude in the v4 two-pass setup;
- teach `run.py` a `--mode post` that sends `SYSTEM_PROMPT_POST`, and key
  the gold by thread id.

About 100 posts would give a first read.

## Cost

Estimated as characters ÷ 4, the same way for every prompt (there is no
tokenizer offline):

| prompt | system prompt |
|---|---|
| production `prompt.py` | ~1,820 tokens |
| production `prompt_thread.py` | ~2,170 |
| rubric_v1 comment / thread | ~1,910 / ~2,330 |
| v6 round 1 comment / thread (frozen) | ~2,050 / ~2,450 (1.12× / 1.13× production) |
| **v6 round 2 comment / thread** | **~2,220 / ~2,620** (1.22× / 1.21× production) |
| v6 round 2 post mode | ~2,200 |
| v5 (lost) | about 3× production |

In thread mode the rendered chunk also grows 15% (see Thread mode
rendering). The system prompt is close to today's size and is identical on
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
   `prompt_thread.build_message`). It is fixed for the eval in
   `v6_thread.render_chunk`. Production needs the five changes listed under
   Thread mode rendering.

## Open questions for the owner

1. **What does neutral mean?** v6 now makes neutral only "a balanced
   verdict" and counts lukewarm words (fine, ok, not bad, meh, mid) as
   negative. That follows the benchmark and the gold, where they are a mild
   knock, but it puts "it's fine" in the owner's negative bucket. Is that
   the reading the owner wants? Should a mixed verdict ("great food, awful
   service") have a neutral overall, or should overall follow the dominant
   side?
2. ~~Do bare endorsements count as "praised"?~~ **Decided: yes.**
3. **Do short replies count as people?** "+1", "this", "second this" and
   "agreed" are filtered out today (and so are 20,756 bare-name answers; see
   gap 1). If they count, a popular rec with ten "+1"s has eleven people
   behind it. Per-author caps and the thread divisor already exist to stop
   that from dominating.
4. ~~Should the original post be extracted?~~ **Decided: yes** (post mode).
5. **Keep chains?** v6 emits them. Should they be stored and filtered at
   query time (recommended: nothing is lost), or still dropped at write?
6. **Should Taste count generic praise?** "X is amazing" currently sets
   only overall. If the owner reads Taste as "people who liked it", the
   prompt should copy generic verdicts into taste.
7. **Single-complaint verdicts.** Should "the service was rude" (and
   nothing else) count toward the overall negative distribution, or only
   toward Service?
8. ~~The comparison loser.~~ **Decided:** negative by default (CONVENTIONS.md).
9. ~~Past and closed opinions.~~ **Decided:** closed places keep their mentions and are left
   out of rankings; past-only opinions count, dated by the comment.
10. ~~Secondhand opinions.~~ **Decided:** counted the same as firsthand.
11. **"Not worth it" as an answer to "which should I pick?"** Is that an
    avoid instruction (the v1 gold) or a negative review? v6 leaves it to
    context.
12. **Dollar figures.** v6 keeps them as notes. Should a later step turn
    them into a price level per category (a $30 sandwich vs. a $30
    omakase)?
