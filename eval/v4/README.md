# Extraction eval v4

v4 compares candidate extraction models against **Claude's own extraction**.
Claude labels every item with the same prompt the candidates get, in two
passes:

- **same_input** sees exactly what the model sees.
- **full_context** sees the whole conversation and serves as the gold pass.

Production's extraction is not a baseline here. Its stored output was used
for one thing only: the round 1 heuristics that picked likely-hard comments.
No label is ever checked against it, and items, packets and batches never
contain it.

Round 1 has **504 comments**. 250 are single comments in comment mode (200
new, plus 50 overlapping v1 gold). The other 254 sit in 14 thread chunks in
thread mode. About 30% of the new comments were drawn at random from real
traffic and 70% by failure-targeted heuristics. Every item carries its
stratum, every matching heuristic tag, its inclusion probability and its
weight. Labeling has not started.

## The workflow

1. **Label.** Give Opus labelers the prompt and the batch files, one pass
   at a time. Then check and export the labels.
2. **Run the models** on the exact production inputs with `eval/run.py`.
3. **Compare to Claude's labels** with `compare_v4.py`.
4. **Draw round 2 from the models' failures** with `next_round.py`, then
   repeat.

Commands are under [Scoring](#scoring) and [Round 2 and
beyond](#round-2-and-beyond).

## On a new device

Everything needed is on this branch: the round 1 items, packets, labeling
batches and keys are committed. Labeling, running models and comparing need
no database. You need:

- **This branch** and a Python with `psycopg2` (the repo's
  `requirements.txt`).
- **`OPENROUTER_API_KEY`**, only to run candidate models (`eval/run.py`).
- **A read-only `DATABASE_URL`** (or `EVAL_DB_URL`), only to draw round 2
  and later. Point it at production and run with
  `PGOPTIONS='-c default_transaction_read_only=on'`; every v4 connection
  also opens a read-only session.
- **The cutoff.** It is fixed in `corpus.CUTOFF`: comments created before
  2026-10-09 UTC. Round 2 samples the same population.

Round 1's corpus snapshot (`~/.cache/nyceats-eval-v4/snapshot_20261009.pickle`,
about 300 MB) is an optional fast path; don't copy it. Without it,
`next_round.py` reads the corpus from the live database with the same
cutoff, which takes a few minutes and several GB of memory. It then warns
that the population may have drifted since round 1's snapshot
(`2026-10-13T20:11:58Z`): deletions, late-arriving comments, and extraction
progress moving the production-derived heuristic tags. Pooled weights
across rounds are then approximate, and `compare_v4.py` warns. A live read
is never saved, so it can never stand in for round 1's snapshot; each run
without the snapshot reads the database again.

| file | what |
|---|---|
| `corpus.py` | Loads the corpus read-only (from the optional cache, else the live DB) and holds every heuristic |
| `render.py` | Renders model inputs from the DB with production's SQL and builders |
| `design.py` | Draws, inclusion probabilities, the holdout split, item assembly, and `design.json` |
| `build_round1.py` | The round 1 spec and build: writes `items*.jsonl` and `design.json` |
| `verify_inputs.py` | Byte-diffs v4's inputs against production's own functions and writes `verify_inputs.json` |
| `packets.py` | Writes `packets.jsonl`: a `same_input` and a `full_context` packet per item |
| `batches.py` | Writes the blind labeling batches `batches/<pass>/bNNN.txt`, plus `keys/<pass>.json` |
| `labels.py` | Checks label files and exports them to run and gold format |
| `compare_v4.py` | Scores model runs against Claude's labels per mode, stratum, tag, split and weight; reports Claude's own ceilings |
| `next_round.py` | Measures candidate models' failure rates against Claude's labels and draws round 2, 3, ... |
| `items.jsonl` | Round 1: 250 `comment` items and 14 `thread` items. `items_single.jsonl` and `items_thread.jsonl` hold the same items split for `run.py` |
| `export_production.py` | Optional, not part of the workflow: exports production's stored output for a round into gitignored `production/`, only once both label passes are complete (see the appendix) |
| `selftest.py` | Regression checks: misattachment counting, label export failures, duplicate placement in batches |

`items.jsonl` is also blind: it contains no stored mention and no
`extracted_with`. Item ids are assigned in hashed order, so an id says
nothing about how its item was drawn. The rule from v1 still holds: **no
eval comment may ever be used as a prompt example.**

---

## What production actually sends

The renderers reproduce production's input byte for byte. `verify_inputs.py`
called production's functions directly on a read-only connection and got
identical strings in every check:

| check | identical |
|---|---|
| next 200 comments in production's queue (`extract.next_batch` → `prompt.build_user_message`) vs `render.comment_inputs` | 200 / 200 |
| all 250 v4 single items vs a fresh render | 250 / 250 |
| v4 thread chunks whose thread is wholly unextracted (`extract_threads.thread_rows` → `chunks` → fetch_chunk's numbering → `build_message`) | 7 / 7 (the other 7 are partly extracted, so production's pending filter would render a subset) |
| the five biggest wholly-pending threads in production's own queue | 5 / 5 |
| the 50 v1 overlap items vs the input v1 stored | 50 / 50 unchanged |

**Comment mode** (`extract.py`, which the poller runs) sends four things:

- the post title;
- the selftext, cut at 400 characters (`rstrip` + `" ..."`, original
  whitespace kept);
- the **immediate parent only, untruncated**;
- the comment, untruncated.

The parent is left out when it is `[deleted]` or `[removed]`, or missing
from the DB. No grandparent is ever sent, so a reply two levels below the
place it judges cannot be resolved (`deep_chain_context_gap`). Parent
lengths have a median of 106 characters, a p99 of 1,158 and a maximum of
9,664. There are 1,834 comments whose parent runs over 1,500 characters.

**Thread mode** (`extract_threads.py`) renders a thread as an indented tree.
Comments are ordered by `coalesce(root_comment_id, id), created_utc` and cut
into chunks of 25. The selftext is whitespace-collapsed and cut at 400, each
comment is cut at 700, and indentation is capped at depth 6. v4 renders
every eligible comment, as a full re-extraction after `--reset` would. A
plain run would only see the comments still pending. Things that surprised
me:

1. **Indentation points at the wrong parent for 9.75% of replies.** Within a
   root, replies are sorted by time, not depth-first. The model reads
   "a comment indented under another is replying to it", so a late reply to
   an early sibling lands under whichever comment came just before it. In
   t002 (Keens), `[10]` replies to `[8]` but sits under `[9]`, and `[15]`
   replies to `[13]` but sits under `[14]`. Over the corpus, 33,560 of
   344,189 replies are misattached. 31,880 of them are this time-ordering at
   depth ≤ 6. The other 1,680 are past the depth-6 indentation cap, where a
   reply is drawn flush with its parent and so can only be read as replying
   to the line right above it. That is wrong when two replies share a capped
   parent. This is a renderer bug, not a prompt problem, and it is its own
   stratum (`chunk_misattached`). The first build reported 37,584 (10.9%):
   it also counted 4,024 consecutive deep-chain replies past the cap as
   misattached, although they read correctly (`visual_parent` never accepted
   a parent drawn at the cap). The corrected stratum kept every drawn chunk;
   only thread weights moved.
2. **11.5% of replies have no parent in their chunk.** In 22,390 the parent
   is in another chunk. In the rest it is deleted, 15 characters or
   shorter, or missing.
3. **Stored output mixes prompts.** 6,547 comments stamped with the
   comment-mode hash `1d5bac550078` still carry 9,988 mentions from the
   thread prompt `ca5439be83b3`. The comment-mode re-run added mentions
   without removing the old ones. No (comment, entity) pair is duplicated,
   so the stored output is the union of both runs. The production export
   keeps the union, because that is what the board shows. These comments
   are tagged `mixed_prompt_mentions`.
4. **70% of the corpus has never been extracted.** That is 476,973 of
   681,125 eligible comments. Extraction covers 2026 almost completely, a
   quarter of 2025, and essentially nothing before. The DB history starts in
   **2021-09**, not 2014 as SPEC.md says.
5. 114 groups of comments share a root and a `created_utc` second, so
   production's order between them is not deterministic. None fall in a v4
   chunk.

---

## How round 1 was built

The **snapshot** was read 2026-10-13 and cut at `created_utc < 2026-10-09`.
The poller only extracts the last 3 days, so stored output for these
comments is settled. It holds 762,745 comments, 681,125 of them eligible
(body not `[deleted]`/`[removed]` and longer than 15 characters, which is
`next_batch`'s filter), in 51,123 production chunks. All 1,006 eligible
comments from v1/v2 (single items, thread items and top-ups) and v1's 17
whole threads are excluded, except for the overlap.

The **seed** is `nyceats-eval-v4-r1`. Every draw orders candidates by
`md5(seed|purpose|key)`, so rebuilding over the same snapshot gives the same
set.

### Comment mode (unit: one comment)

- **Random:** 60 comments drawn uniformly from all 679,827 eligible
  comments.
- **Targeted:** 140 comments. Each comment's stratum is the first heuristic
  it matches in the order below, or `none`. Each stratum then draws its
  quota at random from the comments not already picked.
- **Overlap:** 50 v1 single-comment gold items in hashed order. They use
  v1's labels, which v1 corrected against production. They carry no weight
  and are left out of every re-weighted number. They exist only to measure
  Claude-vs-v1 agreement.

The inclusion probability is
`pi = n_r/N + (1 - n_r/N) * n_s/(N_s - r_s)`, and weight = 1/pi.

### Thread mode (unit: one production chunk)

- **Random:** comments are taken in random order, and each brings in its
  whole chunk, until 65 comments are covered. This makes the draw
  proportional to size, so it is proportional to traffic: k = 4 draws gave
  4 chunks and 85 comments. `pi_r = 1 - (1 - size/668,167)^k`.
- **Targeted:** each chunk stratum takes chunks at random until its comment
  budget is met (35/30/35/35). `pi = pi_r + (1 - pi_r) * n_s/(M_s - r_s)`.
- At most one chunk is taken per thread, and no chunk contains a v1/v2
  comment or a single item's comment. That way no comment has two
  references.
- Every comment in a chunk carries the chunk's weight.

There are two approximations here: the one-chunk-per-thread rule, and
stopping on a comment budget rather than a fixed count. Both are small next
to the sampling error of 14 chunks.

### Holdout

Within each mode, items are sorted by (stratum, draw, hash), and every fifth
item is marked `holdout`, starting from a hashed offset. That gives
**50 / 250 single items and 3 / 14 chunks (41 comments)**, spread over the
strata. Holdout is for final scoring only, never for prompt tuning.

### Counts

| mode | items | comments | random | targeted | overlap | holdout |
|---|---:|---:|---:|---:|---:|---:|
| comment | 250 | 250 | 60 | 140 | 50 | 50 |
| thread | 14 chunks | 254 | 85 (4 chunks) | 169 (10 chunks) | – | 41 (3 chunks) |
| **total** | | **504** | 145 | 309 | 50 | 91 |

Comment-mode strata, in priority order. `N_s` is the population, `r_s` the
random picks that fell in the stratum, and `n_s` the targeted draws:

| stratum | N_s | r_s | n_s | items | holdout | weight |
|---|---:|---:|---:|---:|---:|---:|
| dish_complaint | 4,021 | 0 | 14 | 14 | 3 | 280 |
| price_complaint | 8,981 | 0 | 14 | 14 | 2 | 607 |
| neg_wording_nonneg_score | 1,997 | 0 | 14 | 14 | 3 | 141 |
| deep_chain_context_gap | 30,612 | 5 | 12 | 17 | 3 | 2,082 |
| reply_ancestor_named | 65,433 | 6 | 18 | 24 | 5 | 2,752 |
| short_opinion_reply | 18,802 | 0 | 14 | 14 | 3 | 1,201 |
| avoid_or_strong_negative | 11,763 | 0 | 12 | 12 | 3 | 902 |
| question_or_unvisited | 11,401 | 2 | 12 | 14 | 3 | 877 |
| stuck_default_with_opinion | 5,166 | 1 | 12 | 13 | 2 | 415 |
| zero_mentions_suspicious | 10,241 | 0 | 10 | 10 | 2 | 939 |
| long_list | 10,125 | 2 | 8 | 10 | 2 | 1,138 |
| none | 501,323 | 44 | 0 | 44 | 9 | 11,331 |
| overlap_v1 | – | – | – | 50 | 10 | none |

Thread-mode strata:

| stratum | chunks M_s | comments in stratum | drawn (random + targeted) | comments | holdout chunks |
|---|---:|---:|---:|---:|---:|
| chunk_misattached | 6,791 | 165,799 | 1 + 2 | 75 | 1 |
| chunk_parent_outside | 2,198 | 49,993 | 0 + 2 | 43 | 0 |
| chunk_title_names_place | 3,033 | 55,247 | 0 + 3 | 36 | 1 |
| chunk_failure_dense | 2,540 | 41,450 | 0 + 3 | 40 | 1 |
| none | 35,934 | 355,678 | 3 + 0 | 60 | 0 |

`design.json` has every number above, plus tag counts in the sample and in
the population.

---

## Heuristics

Every heuristic is read-only. Some read only the comment text; others also
read production's stored mentions, which are used only to choose candidates
and never written into an item. The **gazetteer** is production's entity
keys with at least 8 stored mentions, after removing four kinds of key:

- keys in `excluded_entities` or `chains.txt`;
- keys made only of generic words ("best pizza", "coffee shop", "little
  italy");
- keys ending in a location word ("7th street", "bryant park");
- single-word keys that appear in the corpus more than 4 times as often as
  they were extracted ("best", "via").

That leaves 2,350 keys. Names are matched on `normalize_entity` n-grams of
1 to 4 words. The gazetteer is what lets "a parent names a place" work on
the 70% of comments that were never extracted.

Comment-level tags. A single item and every comment in a thread item
carries every tag it matches. "Stratum" is the count after first-match
assignment.

| tag | definition | population | stratum | single items | thread comments |
|---|---|---:|---:|---:|---:|
| dish_complaint | body matches DISH_COMPLAINT: "skip/avoid/don't get the ...", or "the <dish> was bland/dry/soggy/..." | 4,046 | 4,021 | 14 | 2 |
| price_complaint | body matches PRICE_COMPLAINT: overpriced, rip-off, not worth it / the money, too expensive, for that price, "$N for a ..." | 9,230 | 8,981 | 16 | 2 |
| neg_wording_nonneg_score | extracted with at least 1 stored mention, body matches NEG_WORDS, and no stored mention has an aspect < 0 or `is_negated` | 2,408 | 1,997 | 17 | 2 |
| deep_chain_context_gap | depth ≥ 2, length ≤ 400, no stored mention or gazetteer name in the comment or its parent, but the grandparent or great-grandparent has one (comment mode never sends it) | 31,152 | 30,612 | 25 | 7 |
| reply_ancestor_named | depth ≥ 1, length ≤ 400, no stored mention (or never extracted) and no gazetteer name in the comment, while the parent or grandparent has a stored mention or a gazetteer name | 89,557 | 65,433 | 52 | 28 |
| short_opinion_reply | depth ≥ 1, length ≤ 150, body matches SHORT_OPINION | 29,842 | 18,802 | 24 | 16 |
| avoid_or_strong_negative | body matches AVOID_OR_STRONG_NEG | 19,845 | 11,763 | 25 | 13 |
| question_or_unvisited | body matches QUESTION_OR_UNVISITED | 14,655 | 11,401 | 17 | 2 |
| stuck_default_with_opinion | extracted, at least 1 stored mention at the "named, nothing said" default (food 0.3 ± 0.01, other aspects null), and body matches NEG_WORDS or POS_WORDS | 6,848 | 5,166 | 21 | 6 |
| zero_mentions_suspicious | extracted with no stored mention, and the body has a gazetteer name or meets v1's rule (PLACE_WORDS plus CAP_MID or POSSESSIVE, or a top-level reply under a rec-seeking title) | 13,924 | 10,241 | 23 | 5 |
| long_list | ≥ 4 BULLET lines, ≥ 8 line breaks, or ≥ 6 stored mentions | 14,044 | 10,125 | 23 | 6 |
| never_extracted | `extracted_at` is null (pending, or parked with `extract_error`). Too common to target; the random draw covers it | 476,973 | – | 125 | 125 |
| extract_error | `extract_error` is set | 386 | – | 0 | 0 |
| extracted_no_mentions | extracted, no stored mention | 107,985 | – | 64 | 74 |
| original_thread_prompt | `extracted_with` ends in the original thread prompt `ca5439be83b3`. Tag only: it is 86% of extracted comments, so random sampling already covers it | 177,078 | – | 114 | 87 |
| mixed_prompt_mentions | stored mentions carry a prompt hash other than the comment's `extracted_with` | 6,547 | – | 2 | 28 |
| parent_missing | a reply whose parent is not in the DB | 199 | – | 0 | 0 |
| parent_not_sent | parent is `[deleted]`/`[removed]`, so comment mode omits it | 1,979 | – | 0 | 0 |
| long_parent | the parent comment mode sends is over 1,500 characters | 1,834 | – | 0 | 0 |

Chunk-level tags, computed on production's chunking of the full thread. The
visual parent of a line is the nearest earlier line indented one step less.
Indentation is capped at 6 as production caps it, so a reply deeper than 6
is drawn flush with its parent and its visual parent is the line right above
it (`corpus.visual_parent`; `selftest.py` checks that a consecutive deep
chain counts as no misattachment).

| tag | definition | population chunks | stratum | thread items tagged |
|---|---|---:|---:|---:|
| chunk_misattached | ≥ 2 replies whose real parent is in the chunk but is not the line the indentation points to (past the cap: not the line right above) | 6,954 | 6,791 | 3 |
| chunk_parent_outside | ≥ 3 replies whose parent is not in the chunk (another chunk, or not sent) | 4,546 | 2,198 | 4 |
| chunk_title_names_place | the title has a gazetteer name, and the chunk has ≥ 3 replies with no gazetteer name of their own | 4,763 | 3,033 | 4 |
| chunk_failure_dense | ≥ 3 comments, and ≥ 40% of the chunk, carry a comment-level failure signal (any comment stratum except long_list and question_or_unvisited) | 6,261 | 2,540 | 4 |
| chunk_later | not the thread's first chunk (tag only) | 15,222 | – | 3 |
| chunk_never_extracted | every comment in the chunk is unextracted (tag only) | 35,962 | – | 7 |

The patterns are `re.IGNORECASE` (except CAP_MID and POSSESSIVE) and are
copied from `corpus.py`:

```
SHORT_OPINION = (^\W*(this|same|\+1|yes+|no+|nah|facts|agreed?|seconded|word)\b)|\b(mid|meh|overrated|overhyped|underwhelming|mediocre|not worth|skip|pass on|hard pass|avoid|tourist trap|trash|garbage|bland|disappointing|disagree|hard disagree|second this|underrated|so good|it'?s fine|it'?s ok(ay)?|just ok(ay)?|decent|solid|fell off|gone downhill|went downhill|nothing special)\b
NEG_WORDS = \b(mid|meh|overrated|overhyped|underwhelming|mediocre|disappoint\w*|bland|terrible|awful|horrible|gross|disgusting|inedible|worst|trash|garbage|sucks?|sucked|rude|dirty|food poisoning|got sick|never again|never going back|not worth|overpriced|rip ?-?off|tourist trap|avoid|skip|stay away|don'?t bother|wouldn'?t (go|recommend|return)|nothing special|fell off|(gone|went) downhill|not what it used to be|soggy|stale|greasy|overcooked|undercooked|lukewarm|flavorless|tasteless)\b
POS_WORDS = \b(amazing|incredible|delicious|great|awesome|best|love|loved|favou?rite|fav|excellent|fantastic|outstanding|phenomenal|underrated|insane|unreal|bomb|slaps|fire|perfect|worth it|worth the)\b
PRICE_COMPLAINT = \b(over-? ?priced|rip-? ?off|highway robbery|robbery|price gouging|money grab|not worth (it|the (money|price|cost|hype))|(too|so|very|way|crazy|insanely|ridiculously|absurdly|really) (expensive|pricey|overpriced)|for (that|the|this) price|at (that|this) price|prices? (are|is|have gone|went) (up|insane|crazy|ridiculous|absurd|way up)|\$\d+(\.\d\d)? for (a|an|one|two|three|\d) \w+)
DISH_COMPLAINT = (\b(skip|avoid|don'?t (get|order|bother with)|pass on|stay away from|steer clear of) (the|their|any of the)\b)|(\b(the|their|my) [\w'’ -]{2,30}? (was|is|were|are|tasted|felt) (kind of |kinda |a bit |pretty |so |very |really |super |too )?(bland|dry|soggy|overcooked|undercooked|under-?seasoned|salty|too salty|greasy|stale|rubbery|mushy|tough|chewy|lukewarm|mid|meh|forgettable|disappointing|overrated|not good|terrible|awful|inedible|gross|burnt|flavorless|tasteless)\b)
QUESTION_OR_UNVISITED = \b(haven'?t (been|tried|gone|had|made it)|have not (been|tried)|never (been|tried)|on my (list|radar)|want(ed)? to try|wanna try|planning (to|on) (go|try)|heard (good|great|amazing|mixed|bad|nothing but) things|(has|have) any ?one (been|tried|gone)|any ?one (been|tried)|have you (been|tried)|is it (good|worth)|worth (it|going|the hype|the wait)\s*\?|how (is|was|are|were) [^?]{1,40}\?)
AVOID_OR_STRONG_NEG = \b(avoid|skip|tourist trap|don'?t go|dont bother|don'?t bother|not worth|overrated|stay away|overhyped|got sick|food poisoning|rude|worst|never again|never going back|never go back|regret\w*|disgusting|inedible)\b
BULLET = ^\s*(?:[-*•+]|\d{1,2}[.)])\s+\S        (multiline)
PLACE_WORDS = \b(try|tried|go to|went to|spot|place|recommend|check out|love|loved|favorite|fav|go-to|get the|order the|pizzeria|deli|bakery|ramen|tacos?)\b
CAP_MID = [a-z,;:(] +[A-Z][A-Za-z'’&\-]{2,}
POSSESSIVE = \b[A-Za-z]{2,}(?:'|’)s\b
```

These heuristics find *situations*, not confirmed failures. Spot checks
were mostly on target. Two weaker spots: `dish_complaint` also catches
place-level knocks ("the dessert places on your list are mid"), and
`deep_chain_context_gap` catches some chains that have wandered off topic.

---

## Packets, batches and labels

`packets.py` builds two packets per item:

- **same_input** is the exact model input: the comment-mode message, or the
  chunk.
- **full_context** gives the full title and body, untruncated. For a single
  comment it adds the whole ancestor chain, the comment marked
  `>>> COMMENT TO LABEL`, and its replies. For a chunk it adds the whole
  thread in true reply order (depth-first). Chunk comments keep their
  `[n]` numbers; everything else is marked `(context)`. Threads over 150
  comments show only the chunk's comments, their ancestors and their
  direct replies. In t002/t004-style chunks this view shows the real
  parents that the same-input rendering misattaches.

`batches.py` cuts each pass into **30 batches** in hashed order: 14 batches
of about 20 single comments, and 16 batches that each hold one chunk. Each
pass has 291 packets. The **self-consistency subset** is 10% of items per
mode (25 singles and 2 chunks, the same items in both passes). Each copy
appears a second time under a different opaque packet id and always in a
different batch. Batch files contain only instructions and packet text. A
scan for strata, weights, item ids, prompt hashes and the word "production"
finds only comment text. `keys/<pass>.json` maps packet ids back to items;
it is for tooling, not labelers.

**Label format** is one file per batch, `labels/<pass>/bNNN.jsonl`, with one
line per packet:

```json
{"packet_id": "0000abcd", "output": {"mentions": [{"id": 4, "restaurant_raw": "Example Place", "neighborhood_hint": null,
  "dishes": ["noodles"], "descriptors": [], "aspects": {"food": null, "value": null, "service": -0.6,
  "atmosphere": null, "wait": null}, "expensiveness": null, "is_firsthand": false, "is_negated": false}]}}
```

`output` is production's extraction schema (`prompt.py` /
`prompt_thread.py`). That way Claude's labels, production's rows and model
runs all go through `score.py` the same way. `id` appears only in thread
packets, and it is the bracket number. The optional fields
`value_complaint`, `dish_sentiment`, `ambiguous` and `out_of_scope` are used
when present. **If the user's labeling prompt returns a different schema,
map it into this shape before `labels.py export`.** That is the one mapping
step.

To label, give each Opus labeler the user's prompt plus one batch file (or
the lines of `batches/<pass>/packets.jsonl` for that batch) and nothing
else. Never give it `items.jsonl`, `keys/`, any `production/` export or
v1/v2 files.
Run the two passes with separate labelers.

---

## Scoring

```bash
# 1. labels: check, then export each pass (exit 1, nothing written, on any problem)
python eval/v4/labels.py check  --pass full_context
python eval/v4/labels.py export --pass full_context          # -> labels/full_context.run.jsonl + .gold.jsonl
python eval/v4/labels.py export --pass same_input

# 2. candidate models on the exact production inputs, mode-matched (OPENROUTER_API_KEY)
python eval/run.py --model x/y --mode comment --items eval/v4/items_single.jsonl --tag v4 --prompt file:<prompt>
python eval/run.py --model x/y --mode thread  --items eval/v4/items_thread.jsonl --tag v4 --prompt file:<prompt>

# 3. compare every eval/runs/*__v4*.jsonl to Claude's labels
python eval/v4/compare_v4.py --ref full_context    # gold reference
python eval/v4/compare_v4.py --ref same_input      # same-input reference
python eval/v4/selftest.py                         # tooling regression checks (no data needed)
```

`labels.py export` fails with a nonzero exit and writes nothing in any of
these cases:

- a line is bad JSON;
- a line names a packet outside its batch;
- a packet is labeled twice;
- a mention fails the schema, including a thread `id` that is not a
  bracket number;
- a packet is unlabeled (`--allow-missing` exports a partial pass).

Nothing is silently dropped or overwritten.

`compare_v4.py` scores every comment with `score.py`'s `score_comment`, so
the metrics mean exactly what `eval/README.md` says. A label gold mention
is keyed like a model mention: `normalize_entity` plus alias overrides.
Levels come from `score.bucket`. There are no accept-keys or alternatives,
so matching relies on score.py's fuzzy rule. A comment-mode run is scored
on single items, and a thread-mode run on chunks.

For each mode, the report shows these scopes:

- unweighted;
- **weighted** to traffic (Hajek, 1/pi; overlap excluded);
- tuning / holdout, both unweighted and weighted;
- each draw;
- each stratum;
- each heuristic tag.

The **ceilings** come in three rows:

- **claude self-consistency**: the duplicate copies scored against the
  primary copies.
- **claude same_input vs full_context**: what the mode's missing context
  costs even Claude.
- **Claude vs v1 hand gold**: on the 50 overlap items.

Outputs go to `results/comparison_<ref>.json` and `.md`. Pass `--dirs` to
pool rounds. The combined `pi` is the sum of the item's `pi` under each
round's design. It is exact when every round drew from the same snapshot,
and approximate when a later round read the live database. In that case
`compare_v4.py` prints a one-line warning, and the output JSON records each
round's `snapshot_at` with `mixed_snapshots: true`.

## Round 2 and beyond

```bash
# 4. draw the next round from where the candidate models fail against Claude's labels
python eval/v4/next_round.py eval/runs/*__v4.jsonl --dry-run          # failure rates + proposed allocation
EVAL_DB_URL=... python eval/v4/next_round.py eval/runs/*__v4.jsonl    # draws eval/v4/round2/ (read-only DB)
python eval/v4/packets.py --dir eval/v4/round2 && python eval/v4/batches.py --dir eval/v4/round2
# label round2/batches/*, labels.py export --pass ... --dir eval/v4/round2,
# run the models on round2/items_single.jsonl and items_thread.jsonl, then compare_v4.py (pools all rounds)
```

`next_round.py` takes one or more candidate model run files. A path that
doesn't exist, such as an unexpanded glob, stops it with a message. It
scores each file against Claude's labels (`--ref`, default `full_context`)
on every labeled round: a comment-mode run on single items, a thread-mode
run on chunks.

Files are grouped by model (`run.py`'s recorded model). Every model counts
equally: its failure rates are averaged with the other models', so a model
with many run files doesn't dominate.

If no run covers a mode, that mode's strata fall back to a uniform
allocation. It prints a warning and records it as `allocation_basis` in
`failure_rates.json`. `--modes comment` (or `--modes thread`) draws only the
modes you have runs for.

Production's stored output can be added with `--production`, as one more
model, but it isn't needed. It types each comment's failures:

- dropped comment
- dropped mention
- wrong place
- spurious mention
- wrong sign
- scored milder than written
- missed negative
- missed negation
- missed price complaint
- missed dish complaint
- stuck at the +1 default

It reports the rate of each type per heuristic, per stratum and weighted to
traffic, then allocates the new round:

- 30% of each mode's 250-comment budget stays random.
- The other 70% is split across strata in proportion to
  `sum over failure types seen of (c[s,f] + 0.5) / (n[s] + 1)`.
- Each stratum keeps a floor of 3 comments, or 25 thread comments.

The strata are still round 1's heuristics. They read production's stored
output only to locate likely-hard comments, and the models' failures decide
how many to take from each.

The draw uses round 1's snapshot if it is in the cache. Otherwise it reads
the corpus from the live database (read-only, comments before the Oct 9
cutoff) and warns that the population may have drifted (see [On a new
device](#on-a-new-device)). It excludes every comment and thread from
earlier rounds. It builds the round in a hidden temp directory and renames
it to `round<N>/` only when `items.jsonl`, `design.json` and
`failure_rates.json` are all written, so a failed draw leaves nothing
behind. `compare_v4.py` and `next_round.py` skip, with a warning, any
`round<N>/` that lacks `items.jsonl` or `design.json`. Rerun it for round 3
and on.

## Reproducing round 1

Round 1 is committed, so nothing needs rebuilding. To rebuild or re-check it:

```bash
EVAL_DB_URL=$DATABASE_URL PGOPTIONS='-c default_transaction_read_only=on' \
    python eval/v4/build_round1.py        # uses the cached snapshot, else reads ~100 MB live
EVAL_DB_URL=... python eval/v4/verify_inputs.py
python eval/v4/packets.py && python eval/v4/batches.py
```

A byte-identical rebuild needs round 1's snapshot: `snapshot_20261009.pickle`
in `~/.cache/nyceats-eval-v4/` (or `$V4_CACHE_DIR`), read at
`2026-10-13T20:11:58.568679+00:00`. Without it the build reads the live
database, which has moved on since, and saves nothing. The tags derived from
round 1's snapshot are cached next to it as `corpus_<cutoff>_<key>.pickle`. The key hashes `corpus.py`,
`extract.py`, `chains.txt`, `extract_threads.py`, `prompt_thread.py`,
`excluded_entities.json`, the v1/v2 item files and the snapshot file's size
and mtime. The cache holds comment text and production output, so keep it
out of the repo.

Every connection is opened with `default_transaction_read_only=on` and a
read-only session.

## Appendix: production's stored output (optional)

Not part of the workflow. To also score production's stored extraction,
export it after a round's labeling is finished:

```bash
EVAL_DB_URL=... python eval/v4/export_production.py [--dir eval/v4/round2]
python eval/v4/compare_v4.py                 # adds a "production (stored)" row
python eval/v4/compare_v4.py --self-test     # production vs itself: must be perfect
python eval/v4/next_round.py --production ...  # also counts production's failures
```

It refuses until both label passes are complete, and it runs
`eval/export_stored.py` unchanged into gitignored `production/`. If the
round 1 snapshot is cached, it checks every exported comment against it and
stops if production re-extracted any since (`--allow-drift` keeps the
export). Production covers only the comments it ever extracted, 254 of
round 1's 504.

## Caveats and open questions

- **Thread mode has only 14 chunks.** Re-weighted thread numbers rest on 4
  random chunks, so treat them as indicative. Round 2 should add chunks.
- **The full re-extraction assumption.** v4 renders a thread with every
  eligible comment pending. If the backlog is re-run *without* `--reset`,
  production sends only unextracted comments, which changes the chunks for
  partly extracted threads (7 of 14 v4 chunks).
- **"No extraction at all" was read two ways.** `never_extracted` (70% of
  the corpus) is a tag that the random draw covers.
  `zero_mentions_suspicious` targets extracted comments that came back
  empty while naming a place.
- **Gold without alternatives.** Claude's labels carry one value per
  aspect, unlike v1's accepted alternatives. Exact-level agreement will
  read lower than v1's for the same quality, so sign and recall metrics are
  the robust ones.
- **The production export is the union of prompts** for the 6,547 mixed
  comments, as the board shows it. Comments production never extracted are
  not counted against it, because it never processed them.
- **The renderer misattachment** looks worth fixing in `extract_threads.py`
  independently of the model choice: order depth-first within each root.
  That would change the thread-mode input, so v4's thread items would need
  re-rendering for the fixed version.
