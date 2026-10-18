# Haiku 5.5 benchmark of v6: diagnosis

Read-only analysis of the a–f runs (Message Batches, Claude Haiku 5.5). Step
g (current prompt, thread mode, v2 chunks) was still running, so the v2
thread comparisons below use the 18 chunks g had finished. No paid calls
were made. Every re-score works on filtered copies in a scratch directory;
the ledger and run files were not touched. Unless a line says otherwise,
counts are gold mentions. Comments shared by v1 and v2 count once per set.

## Summary

The two biggest losses are **truncation, not prompt quality**. Both come
from `max_tokens`, set at 6k for comment mode and 16k for thread mode. On
medium effort, thinking uses up the budget before the JSON is finished.

| finding | cause | fix |
|---|---|---|
| Thread mode: 109 of 361 v6 chunks truncated | thinking (mean 13.5k on truncated chunks) consumes the 16k budget | raise `max_tokens` (re-run the 109: ~$0.60), or use effort low for thread mode |
| Comment recall 0.886 vs 0.941 (v1), 0.825 vs 0.936 (v2) | 6 truncated long-list calls carry 132 of the 154 gold mentions current found and v6 missed | raise `max_tokens` to 16k (~$0.01 to redo the 6). Without them, recall **ties**: 0.937 vs 0.937 (v1), 0.930 vs 0.930 (v2) |
| Low beat medium on recall | 1 truncated medium call (4 of its 6 mention misses come from one other comment), plus medium dropping landmark references | the same `max_tokens` fix, plus one prompt line |
| Remaining negative gap in comment mode (8 unique misses) | 3 line/wait tips filed as reference or endorse, 2 by the comparison rule, 1 adapter artifact, 1 name rewrite, 1 neutral | prompt (3), owner (2), scorer (1 + 1) |
| Experience accuracy 0.89 vs 0.64 | real, but it is definition alignment: the current prompt says not-firsthand for 47% of mentions, including most bare recs | none needed; one prompt line fixes v6's remaining errors |
| Dish-negative recall 0.61–0.69 | real: same dish names, negative levels | none |

## 1. Thread mode: truncation

| | v6 medium | current medium | v6 low |
|---|---:|---:|---:|
| chunks | 361 | 24 (v1) | 8 |
| stopped at `max_tokens` | **109** (all invalid JSON, so whole chunk lost) | 0 | 0 |
| thinking, mean / p50 / p90 | 8,605 / 8,439 / 14,352 | 1,675 / 1,512 / 3,131 | 2,873 / 2,128 / 9,139 |
| output (thinking + JSON), p50 / p90 | 12,440 / 16,000 | 2,295 / 5,356 | 3,330 / 14,510 |
| visible JSON, p50 / p90 | 3,048 / 4,656 | 1,123 / 2,782 | 953 / 5,371 |

**Thinking is what overflows, not the JSON.** On the 109 truncated chunks,
thinking averaged 13,471 tokens (minimum 8,259; some used all 16,000), and
visible JSON only about 2,529. The JSON is bigger than the current
prompt's, but that alone wouldn't overflow:
- v6 finds more places, 17.8 mentions per chunk against 10.6;
- each mention is about 396 characters against 250. Aspects (90% of them
  null) take 23% of those characters and notes 15%;
- so visible JSON is about 2.7× the current prompt's at p50 (3,048 vs
  1,123 tokens). At p90, 4.7k tokens still fits easily.

Thinking per mention is about 480 tokens for v6 medium against about 160
for the current prompt: v6 deliberates about 17 fields and 12 rules for
every mention. Truncation grows with chunk size and input length:

| | truncated |
|---|---:|
| 25-comment chunks | 87 / 210 |
| 20–24 comments | 10 / 33 |
| 10–19 comments | 11 / 88 |
| under 10 comments | 1 / 30 |
| input 5.4k–6.4k tokens | 1 / 90 |
| input 7.3k–9.1k tokens | 53 / 91 |

Nearly all of it is in step f (v2 comments' chunks): 109 of 355. Step c
(v1 threads) lost only 2 of 24.

**Underlying quality, truncated chunks excluded, on identical comment sets:**

| set | prompt | comments | drop | recall | precision | negative recall | sign | experience |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| v1 threads (c vs d) | v6 | 332 | **0.039** | **0.960** | 0.892 | 0.792 | 0.993 | 0.877 |
| | current | 332 | 0.091 | 0.902 | 0.957 | **0.875** | 0.986 | 0.919 |
| v2 chunks g finished, v6 not truncated | v6 | 110 | **0.051** | **0.948** | 0.991 | 0.789 | 1.000 | 0.912 |
| | current | 110 | 0.121 | 0.870 | 0.990 | **0.842** | 0.978 | 0.897 |
| v2, v6 thread vs v6 comment (f vs a) | thread | 351 | 0.043 | 0.931 | 0.975 | 0.842 | 0.977 | 0.886 |
| | comment | 351 | 0.056 | 0.887 | 0.957 | 0.860 | 0.961 | 0.880 |
| v1 low-slice chunks, medium not truncated | low | 93 | 0.000 | 1.000 | 0.947 | 1.000 | 1.000 | 0.970 |
| | medium | 93 | 0.138 | 0.889 | 0.914 | 0.667 | 1.000 | 0.933 |

With all chunks counted, v6 thread on v1 reads recall 0.790 and drop 0.173.
On v2 thread vs comment it reads recall 0.538. Those are truncation, not
quality. On complete chunks the new renderer and prompt find more places
and drop fewer comments than the current prompt, at slightly lower
precision and negative recall. Low effort on the 8 low-slice chunks looked
better than medium even with truncation excluded, but n = 93 and the
negatives are a handful.

**Thread negatives that current caught and v6 missed** (v1, complete
chunks), 3:
- *"Its overpriced produce in liquid form"* (Pressed, named only in the
  title; the parent is a 14-character stub). Not extracted.
- *"Those lines are brutal"* (Mama's Too, named in the title). Not extracted.
- *"Went a few sundays ago, the line started around 4:15"* (Red Hook
  Tavern). Filed as `opinion: none`.

**Thread precision.** Of the 20 v6 mentions the gold doesn't have:
- 14 are `named_in: context` with `opinion: none`: questions or asides in
  replies, named from the title or parent ("Where is this at.. upper east
  side?", "Where is it located?"). v6's rules count them; the gold leaves
  them out or marks them ambiguous. That is a scope difference, not noise.
- 6 are `context, stated` ("Amaze! Amaze! Amaze!" under Eleven Madison
  Park).

**Fix options for thread mode:**
1. **`max_tokens` 32k** (Haiku 5.5 allows 128k output). Re-run only the 109
   truncated chunks at medium:
   - each truncated attempt cost $0.0041 for 16k of output;
   - at 32k, expect about 18–24k of output, about $0.0055 a chunk, so
     **≈ $0.60 for the 109**;
   - the ledger holds the worst case first: 109 × $0.0087 ≈ **$0.95**. That
     fits the ~$1.5 left once g's $1.58 hold settles.
   - Mechanics: run.py treats a truncated record as done because `raw` is
     set, so the re-run must go to a new tag (e.g. `bench6-med32k`) with
     `--call-keys` listing the 109 chunks. `compare` would then take each
     chunk's complete record.
2. **Effort low for thread mode.** Measured $0.00126 a chunk, about
   **$0.45 for all 361**, with no truncation on the 8 low chunks (worst
   chunk 14.5k of output). Low looked at least as good on the slice. Running
   low on all 361 is also the larger sample for deciding thread mode's
   default effort.
3. **Prompt or chunking** (cuts thinking, untested):
   - smaller chunks. 12–15 comments would roughly halve thinking per call;
     the quoted out-of-chunk parents make this cheap;
   - a thread-only line: "Decide each mention in a sentence; most fields
     are null, so don't deliberate over them."

   Recommendation: 1 for comparability with c/d/f. Add 2 as the
   effort-default test if the budget allows; both fit (≈ $0.60 + $0.45).

## 2. Comment mode: why v6 found fewer places

The 154 gold mentions the current prompt found and v6 medium missed
(v1 44, v2 110; v6 found 8 + 14 the current prompt missed):

| count | category | type |
|---:|---|---|
| **132** | in one of **6 v6 calls that stopped at `max_tokens` 6,000** (thinking 3.7–5.9k). All are long lists: "East Village for Japanese 1. Hi Collar… Sobaya… Raku… Little Myanmar…", a Cantonese banquet list, a Russ & Daughters / El Malecon list. One (t1_nobth7a) spent 5,935 of 6,000 tokens thinking and wrote 153 characters | `max_tokens` |
| 12 | reference-only names in the comment, not emitted. Landmarks: *"near Kossar's Bialys and the Doughnut Plant… walking distance to Katz's and Russ and Daughter"*. Comparisons: *"even Chipotle"*, *"similar to Yoshino and Sho"* | prompt (model skipped, against the rule) |
| 4 | list or suggestion items: Wonder's *"pop salad and el diez"*; *"Maybe swap it for Thai dinner or golden dinner?"* | prompt / model |
| 3 | v6 returned nothing: *"Thank you!! Marked, looks so nice"* (S&P, named in the parent, ×2 sets); *"This! … following Wheated…"* | model |
| 3 | named, but the key didn't match. *"2nd Ave pickles have sucked"*: v6 wrote "2nd avenue deli", copied from the parent instead of as typed, and the scorer's fuzzy match doesn't treat avenue = ave (×2 sets). Minetta Tavern: v6 named Red Hook Tavern instead, a real wrong-place error | scorer (1) + prompt (as-typed) + model (1) |

**With the 6 truncated calls excluded:**

| set | prompt | comments | drop | recall | precision | negative recall | value complaint | dish negative | sign | experience |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v1 | v6 | 766 | **0.044** | 0.937 | 0.914 | 0.861 | 0.944 | 0.613 | 0.994 | **0.891** |
| v1 | current | 766 | 0.054 | 0.937 | 0.933 | **0.878** | 1.000 | n/a | 0.993 | 0.650 |
| v2 | v6 | 475 | **0.055** | 0.930 | 0.965 | 0.883 | 0.920 | 0.710 | 0.964 | **0.880** |
| v2 | current | 475 | 0.062 | 0.930 | 0.963 | **0.909** | 0.960 | n/a | 0.982 | 0.677 |

Reweighted v1: recall 0.941 vs 0.943, negative recall 0.859 vs 0.852.

**Negatives the current prompt caught and v6 didn't**, truncation excluded,
8 unique:

| count | cause | example | type |
|---:|---|---|---|
| 3 | wait tips filed as `opinion: none` or `endorse` | *"Went a few sundays ago, the line started around 4:15"*; *"Be there at 11:30"*; *"even on a sticky and rainy saturday it was busy"* (all Red Hook Tavern) | prompt: the v5 pattern, weaker but still present |
| 2 | v6's comparison rule (the loser of a comparison gets no level) | *"I actually prefer Tatiana to Kabawa"*; *"Prefer Saperavi over Chama Mama"*. The gold scores both −1 | owner decision (open question 8) |
| 1 | **adapter/scorer artifact** | *"I think Lucali is the most overrated restaurant on the planet. They make a good pizza…"*: v6 says overall **negative**, taste positive. The adapter maps food = taste (positive), and `score.model_negative` reads only aspects and `is_negated`, so the negative overall is invisible | scorer |
| 1 | name rewritten | "2nd Ave" → "2nd avenue deli" (see above) | scorer + prompt |
| 1 | read as balanced, not a knock | Ham Ji Bach: neutral overall with positive taste and value; gold −1 | model |

## 3. Why low beat medium in comment mode

On the shared 300-comment subset:
- one medium call is truncated (the East Village list); low never
  truncates. Excluding it, the gap shrinks from 5.5 to 1.9 points on v1
  (0.943 vs 0.924) and from 5.9 to 2.4 on v2;
- the remainder is 6 mentions low found and medium missed, against 1 the
  other way. **4 of the 6 are one comment's landmark references**
  (*"near Kossar's Bialys and the Doughnut Plant… Katz's… Russ and
  Daughter"*): low listed them all as references, medium decided they
  weren't being "talked about". The others: Wheated in *"This! … following
  Wheated"*, and Kabawa named in the title under *"Ask the staff for
  recommendations"*;
- so: medium thinks more and over-applies scope, dropping names it judges
  incidental. Medium is better on experience (0.865 vs 0.764) and on par
  for negatives.

Thinking on the subset: medium mean 513 (max 4,640), low 301 (max 2,483).

## 4. Experience and dish negatives: real, not artifacts

**Experience** (matched mentions, gold firsthand known, truncation excluded):

| | gold yes → yes | gold yes → no | gold no → no | gold no → yes | accuracy |
|---|---:|---:|---:|---:|---:|
| v6 | 753 | 97 | 46 | 9 | 0.883 |
| current | 530 | **320** | 51 | 3 | 0.643 |

The current prompt emits an explicit `is_firsthand: false` on 617 of 1,309
mentions. These are real `false` values, not nulls being counted as false.
It reads "did this person actually go?" literally for bare recommendations,
where the gold, and v6's definition, count a personal pick as firsthand.
So the win is genuine against the gold's convention: it comes from the
definition, not better reading. v6's own 97 misses are mostly
`experience: none` on stated opinions (133 `none/stated` mentions in all).

**Dish negatives:** 44 of 62 gold dish negatives on matched mentions are
hit, each with the same dish named and a negative level: *"chicken"* −1.0
vs gold −3 at Gramercy Tavern; *"bagel"* at Leon's; *"steak"* at Keens;
*"cornbread"* at Jacobs Pickles. The adapter only renames fields
(`dishes` → `dish_sentiment`, level → number), and the match needs a
lenient dish-name match plus a negative level or avoid. The misses are
dishes v6 didn't list (Luigi's *"pizza"* in a nameless "inedible" reply)
or listed without a level.

## Proposed changes (not made)

**`max_tokens` and run settings**
1. Comment mode: `max_tokens` 6k → 16k. Long lists need 4–6k of thinking
   plus several thousand tokens of JSON. Re-running the 6 truncated calls
   costs about $0.01.
2. Thread mode: 16k → 32k at medium (re-run the 109: ≈ $0.60, $0.95
   held), or make **low** the thread-mode default (≈ $0.45 for all 361).
3. run.py: let `--retry-truncated` (or a new tag plus `--call-keys`)
   re-send records with `stop_reason: max_tokens`, since today it counts
   them as done.

**Prompt (v6_common / v6_thread)**
1. RULES 1: add the tip forms. *"the line started at 4:15", "be there by
   11:30", "it was packed even in the rain" are wait negative, not
   facts.*
2. WHAT COUNTS: *"Every named place is a mention, including landmarks
   ('near X'), comparisons and examples; with nothing judged, opinion
   none."*
3. `name`: *"If the comment types the name, even shortened ('2nd Ave'),
   use the comment's form, not the context's."*
4. `experience`: *"A verdict in their own voice is firsthand unless they
   say they haven't been."*
5. Thread only: either smaller chunks or a line that keeps per-mention
   deliberation short.

**Scorer (score.py / v6_adapter)**
1. Count a v6 mention as negative when its `overall` is negative or very
   negative, not only when an aspect or `avoid` is (Lucali).
2. In the fuzzy key match, treat avenue/ave, street/st and the like as
   equal ("2nd avenue deli" vs "2nd ave deli").
3. Report thread-mode precision with and without `named_in: context,
   opinion: none` mentions. The owner decides whether a question in a
   reply counts as a person talking about the place (this is open
   question 3's sibling).

**Owner decisions surfaced**
- The comparison loser (open question 8) costs 2 negatives against the gold.
- Lukewarm-as-negative did not hurt here: sign accuracy is 0.994 on v1.

## Follow-up: compare scoping fix and the scorer-fixed view

- **A compare bug, now fixed.** Steps c and f share one run file, and so do
  d and g. The original compare scored each run file whole, so
  `v6_comment_vs_thread_v1` also counted the v1 single comments that fall
  inside f's v2 chunks: n = 503 instead of the 374 comments of c's own 24
  chunks. compare now cuts each run to its own step's calls before scoring.
  The other 128 metrics in compare.json are unchanged.
- **Scorer-fixed view on the as-run data.** Counting a negative v6
  `overall` as a negative mention matters more than the single Lucali case
  in section 2 suggested. v6's comment-mode negative recall rises from 0.861
  to 0.896 on v1 (current prompt: 0.878) and from 0.833 to 0.852 on v2
  (current: 0.909). Many mentions carry a negative `overall` with no
  negative aspect, because a verdict like "overrated" lives only in
  `overall`. Recall changes only by the "2nd Ave" street-word fix (0.886 →
  0.887). In thread mode, leaving out context-named mentions with no opinion
  raises v6 precision on v1 from 0.892 to about 0.96.

## Re-run cost (batch prices, about $1.5 left after g)

| job | calls | expected | ledger hold |
|---|---:|---:|---:|
| v6 thread medium, the 109 truncated chunks, `max_tokens` 32k | 109 | ≈ $0.60 | ≈ $0.95 |
| v6 comment medium, the 6 truncated calls, `max_tokens` 16k | 6 | ≈ $0.01 | ≈ $0.05 |
| optional: v6 thread **low** on all 361 chunks (effort-default test) | 361 | ≈ $0.45 | ≈ $1.7 at `max_tokens` 16k if sent as one batch; run.py sizes sub-batches to what remains |

The first two together fit comfortably. Adding the third may need it to
run after the first settles, which the sub-batch sizing already does.

## Round 2: what was applied

- **Prompt** (live `v6_*`; round 1 is frozen as `v6r1_*`, so steps a–k keep
  their hashes):
  - very_positive only for broad superlatives ("my favorite", "a must" and
    favorites headers are positive, as in the gold);
  - line and timing tips are wait negative;
  - every named place counts, landmarks, comparisons and examples included
    (opinion none);
  - names kept as typed;
  - a verdict in the commenter's own voice is firsthand;
  - comparison losers negative by default (owner);
  - a reply that only asks about a place is a mention with opinion none
    (owner);
  - new post mode for the original post (owner).
- **Scorer:** the three fixes are now the default. The context-reference
  fix also applies in comment mode. `--legacy-scorer` / `fixes=False`
  reproduces the old numbers, and compare writes a `legacy_scorer` view.
  New metrics: five-level accuracy per aspect, a food confusion table,
  overall-verdict agreement, and opinion-type accuracy where the gold can
  tell.
- **Conventions:** `eval/CONVENTIONS.md`, with gold disagreement counts and
  107 candidate patches (not applied).
- **Re-test:** step l, v6 round 2, low effort, a hashed 600 of a's comments
  (it contains the 300-comment low subset). Expected about $0.11 at round
  1's measured low rate; about $0.30 if no request hits the cache.

## Round 2 results: the regressions explained

Step l is v6 round 2, low effort, on a hashed 600 of a's comments: v1
n = 455, v2 n = 287. It cost $0.1039, or $0.000173 per call, with no
truncation. The wins are in compare.json. Below, l is round-2 low, k is
round-1 low and a is round-1 medium, all on l's comments. "Medium" numbers
are round-1 prompt numbers.

### 1. Experience accuracy did not improve: an effort problem, not a rule problem

Errors on gold-firsthand mentions:

| set | run | gold firsthand → none | gold firsthand → secondhand | accuracy |
|---|---|---:|---:|---:|
| v1 | l (r2 low) | 57 | 23 | 0.734 |
| v1 | k (r1 low) | 62 | 13 | 0.751 |
| v1 | a (r1 medium) | 26 | 3 | 0.888 |
| v2 | l (r2 low) | 65 | 25 | 0.774 |
| v2 | k (r1 low) | 68 | 12 | 0.799 |
| v2 | a (r1 medium) | 42 | 4 | 0.867 |

The own-voice line barely moved "none": low effort still files picks and
list items as none. *"You could go wait in line at Via Carota… same with
l'artusi"*: all three places none. In the East Village list, Sobaya, Pig
and Khao and Saigon Social are none. It also doubled "secondhand" on
own-voice praise: *"Great burger too"*, *"Their round pies are excellent
too"*, *"Cote is quite good"*, *"Their loaded grilled cheese is something
else"*. Medium reads the same definition correctly.

**Fix:** make firsthand the stated default.
> "experience: firsthand is the default for any pick, list item or verdict
> in the commenter's own voice. secondhand only when they credit someone
> else (heard, a friend, reviews, 'people say'). none only for questions,
> places they haven't been or plan to try, and bare facts."

### 2. Opinion type fell on v1 (0.849 → 0.723): mostly stated read as endorse

Confusions in l on v1 (gold → model): stated→endorse 40 (14 in k, 7 in
a), stated→none 7, none→stated 13, none→endorse 1.

- **stated → endorse (40)** is the round-2 regression. Praised items came
  back as bare endorsements: *"Great burger too"* (gold +2), every item
  under *"Personal favs:"* (gold +2), *"they'd give a table for 4 for walk
  ins"* (gold wait +1). Round 2 moved favorites headers and "my
  favorite"-type praise from very_positive to positive, which is the same
  overall an endorsement gets. At low effort the model then picks
  "endorse" for them. This is the prompt, not the scorer: the gold is right
  that praise is "stated".
- **stated → none (7)** are positive timing tips the gold scores wait +1:
  *"if you go around 4/4:40ish there always one or two free tables"*,
  *"Weekdays 12-2 is the best time to go"*. The new line-tip rule covers
  only lines (negative), so the model filed easy-access tips as facts.
- **none → stated (13 on v1, 36 on v2)** is mostly convention, not error:

  | cause | v1 | v2 |
  |---|---:|---:|
  | closed places the gold nulls by rule; v6 keeps the remembered verdict (*"Omg!! Our favorite spot forever"*, Lin's Garden) | 5 | 18 |
  | comparison places the new loser rule now levels; the gold leaves them null (so the gold does disagree with the owner's rule on these, which CONVENTIONS.md's narrow regex undercounted) | 5 | 4 |
  | other | 4 | 14 |

**Scorer fix, applied:** opinion-type accuracy now skips closed gold
mentions. v1 opinion-none accuracy goes from 0.696 to 0.795. The
comparison cases need gold patches, which are listed and not applied.

**Prompt fixes:**
> "endorse is only a bare name or 'try X' with no word of praise; any praise
> word, a favorites heading or a remark ('great burger too', 'they seat
> walk-ins') makes it stated."
>
> Rule 8: "'My favorites:' makes each item stated, positive."
>
> Rule 1: "easy walk-ins, free tables at 4pm, 'no line on weekdays' are wait
> positive."

### 3. Precision on v1 fell (0.947 → 0.916)

Unmatched mentions on v1, l against k:

| unmatched mention | l | k |
|---|---:|---:|
| context-named, no opinion (already not counted against precision) | 22 | 16 |
| context-named, stated | 17 | 10 |
| named in the comment, no opinion | 4 | 0 |
| named in the comment, endorse | 4 | 3 |
| context-named, endorse | 3 | 2 |
| named in the comment, stated | 5 | 5 |

- **Convention, not error:** the no-opinion mentions are what the owner's
  rule now asks for, and the gold lacks them. **Scorer fix, applied:**
  every no-opinion mention (named in the comment or from context) is
  neither a true positive nor a false positive when the gold lacks it. It
  is reported as `reference_mentions_unmatched` (26 for l on v1, 16 for k).
  v1 precision is now 0.925 against round 1's 0.947.
- **Real false positives**, from the "landmarks count" rule reaching past
  food: *The Intrepid*, *The Cloisters*, *Transit Museum*, *Bloomingdale's*.
  **Prompt fix:** "a landmark counts only when it is a food or drink place;
  museums, stores, parks and venues never count."
- **Context-stated, +7:** nameless replies the model attached to a place
  from context: *"Damn if it aint delicious though"* → Fedoroffs;
  *"100%, those breakfasts are insane"* → Cheesecake Factory. Some are
  real reply-mentions the gold lacks or marks ambiguous (gold-patch
  candidates). Others are a stretch: *"You need to get a grip…"* → Ceres
  Pizza. That's mixed and small.

### 4. Value complaints and dish negatives: noise

- **Value complaints, v1:** 8 of 9. The one miss is a missed mention, not
  a missed complaint: *"$25 for a chicken sandwich was a disappointment,
  solid house slice though"* (Mama's Too, named only in the title).
- **Dish negatives, v1:** 7 of 14 (k and a: 8 of 14). The misses:
  - Dame's fish and chips scored neutral (gold −1);
  - 02 Hot Stone's sauce and kimchi not listed;
  - Jacob's "needs snacking/crunching pickles" listed as positive pickles;
  - the Parisi/Parm cutlet sandwich not listed;
  - the Mama's Too mention above.

  One dish's difference on n = 14 is noise. v2 is unchanged at 30 of 37.

### A fix round

Applying the prompt fixes above (experience default; endorse vs stated;
rules 1 and 8; food-only landmarks) and re-running low effort on **the
same 600 comments** would expect about **$0.10**, at round 2's measured
$0.000173 per call plus one cache write for the new hash. That pairs it
with l. On all 1,006 comments it would expect about $0.17. Either fits
the ~$0.25 available. The 600 has the larger margin and gives a direct
comparison with l. Each sub-batch's worst-case hold is about $0.0045 a
request at max_tokens 16k, so with ~$0.29 left it runs as about 10
sub-batches; max_tokens 8k would halve that (round 2's longest output was
7,060 tokens).
