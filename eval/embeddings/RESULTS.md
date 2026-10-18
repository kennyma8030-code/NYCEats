# Embedding model benchmark: results

**Recommendation: `qwen/qwen3-embedding-8b`, stored truncated to 1024 dims,
dense-only to start.** It is in the top tier on every fully judged metric. It
leads on nDCG@10 and on grade-2 precision, and it makes the fewest
negated-match errors. It is also the cheapest model tested: $0.01/M tokens,
half the price of `text-embedding-3-small`. Truncating to 1024 costs nothing
measurable, and 1024 is the size pgvector can actually index (see Storage). The
plan's default, `voyage-4-large`, came second to last of the five.

The reasoning, the noise, and the caveats are below. Tables are in
`RESULTS_TABLES_comments.md` (all systems, all metrics), `DEPTH50.md` (recall
corrected for pool depth), `RESULTS_TABLES_threads.md`, `CORPUS.md` and
`SPEND.md`.

## Setup in one paragraph

**Corpus.** Every eligible comment in production, 96,872 of them: at least one
`mentions` row, and a body that isn't `[deleted]` or `[removed]`. Each is
embedded as thread title + comment body, nothing else.
- **Order of work.** A stratified 25,000-comment core was embedded first so a
  budget stop would still leave a comparison. Spend allowed the whole eligible
  population, so the results below run against all 96,872, which is exactly
  what search would index.
- **Queries.** 110 search-box queries in 8 categories, 22 of them holdout. They
  were frozen and committed (3c971c9) before any retrieval ran.
- **Systems.** 14:
  - each of the five models at its native dims;
  - three free 1024-dim truncations;
  - local BM25;
  - each model fused with BM25 by RRF, k=60 fixed in advance.
- **Judging.** Pooled TREC-style from every system's top 20, giving 10,001
  (query, comment) pairs. Opus subagents graded them 0/1/2 blind and shuffled,
  against written guidelines (`GUIDELINES.md`). A separate 1,000-pair re-judge
  measured consistency.

## Main table (comments, 110 queries)

Mean ×100, 95% bootstrap CI over queries. nDCG@10, P@20 and grade-2 P@10 are
fully judged for every system. Recall is covered in its own section, because
the raw numbers are misleading.

| system | nDCG@10 | P@20 | P@10, grade 2 only | MRR | negated hits in top 10 | relevant restaurants in top 10 |
|---|---|---|---|---|---|---|
| **qwen3-8b** | **79.6** [75.6, 82.9] | 87.6 [84.6, 90.2] | **67.1** [62.0, 72.3] | 94.6 | **0.17** | 86.9 |
| qwen3-8b@1024 | 79.1 [75.2, 82.7] | 86.8 [83.7, 89.6] | 67.3 [61.8, 72.4] | 93.0 | 0.18 | 86.0 |
| oai-3-large | 76.4 [72.8, 79.8] | **88.4** [85.7, 90.9] | 61.5 [56.8, 66.3] | 94.5 | 0.29 | 91.5 |
| oai-3-large@1024 | 76.3 [72.8, 79.8] | 88.0 [85.2, 90.5] | 61.5 [56.6, 66.4] | 95.3 | 0.29 | 91.0 |
| gemini-2 | 72.8 [68.7, 76.9] | 88.0 [85.1, 90.9] | 57.7 [52.7, 62.8] | 93.1 | 0.35 | 89.8 |
| gemini-2@1024 | 72.1 [68.2, 76.1] | 87.3 [84.4, 89.9] | 56.0 [50.4, 61.2] | 93.7 | 0.37 | 89.7 |
| oai-3-small | 69.6 [65.8, 73.2] | 82.2 [78.8, 85.1] | 54.6 [49.9, 59.1] | 91.2 | 0.55 | 85.3 |
| voyage-4-large | 66.4 [61.8, 70.7] | 78.1 [73.8, 82.0] | 51.7 [47.1, 56.2] | 88.7 | 0.65 | 80.8 |
| bm25 | 66.4 [61.8, 70.9] | 76.0 [71.3, 80.3] | 51.2 [45.9, 56.2] | 89.9 | 0.73 | 79.9 |
| qwen3-8b+bm25 | 80.1 [77.1, 83.1] | 86.0 [83.3, 88.6] | 67.2 [62.5, 71.5] | 96.8 | 0.31 | 93.6 |
| oai-3-large+bm25 | 74.7 [71.1, 78.0] | 85.6 [82.7, 88.3] | 59.4 [55.3, 63.5] | 94.3 | 0.47 | 90.9 |
| gemini-2+bm25 | 74.9 [71.3, 78.3] | 85.4 [82.4, 88.2] | 60.9 [56.3, 65.6] | 93.1 | 0.45 | 90.4 |
| oai-3-small+bm25 | 71.1 [67.3, 74.8] | 81.8 [78.5, 85.1] | 56.0 [51.3, 60.7] | 89.8 | 0.63 | 87.8 |
| voyage-4-large+bm25 | 70.6 [66.7, 74.4] | 80.6 [77.5, 83.6] | 56.0 [51.3, 60.5] | 91.9 | 0.63 | 88.2 |

### What is real and what is noise

These are paired bootstrap differences, row minus column on the same queries.
The full matrices are in `RESULTS_TABLES_comments.md`.

- **Top tier: Qwen3-8B, OpenAI 3-large and Gemini 2.** They are tied on P@20
  (all within ±0.8, CIs straddle 0) and tied on corrected recall@50 (below).
- **Qwen vs OpenAI-large on nDCG@10:** +3.1 [−1.0, +7.1]. That is within noise.
  On the 22 holdout queries the two are level (79.0 vs 78.9). Qwen's ranking
  edge is real only on **grade-2 precision**: +5.5 [+0.6, +10.5] in the top 10.
  It puts more comments that clearly answer the query at the top, rather than
  more comments that are merely on topic.
- **Qwen vs Gemini on nDCG@10:** +6.8 [+2.7, +11.0]. This one is real.
- **Qwen vs 3-small:** +10.0 [+6.1, +14.1] on nDCG@10 and +5.4 [+2.2, +8.9] on
  P@20. Real. OpenAI-large vs 3-small is also real: +6.8 [+4.4, +9.6].
- **Voyage-4-large** is reliably below the top tier: −13.2 nDCG@10 vs Qwen and
  −10.0 vs OpenAI-large. It is not separable from 3-small (−3.2 [−7.5, +1.0]).
  Its `input_type` query/document handling was verified to reach Voyage (see
  below), so this is not a configuration miss.
- **1024-dim truncation is free on comments.** Qwen 4096 vs 1024: −0.4
  [−1.6, +0.7]. OpenAI-large 3072 vs 1024: −0.1 [−1.1, +0.9]. Gemini 3072 vs
  1024: −0.6 [−1.3, +0.1].
- **On threads it is not quite free.** Threads are longer texts, and there the
  same truncation costs 1–2 nDCG@5 points, significantly, for all three models
  (see Threads).

### Recall, corrected for pool depth

As scored, recall@50 seems to put OpenAI-large (47.7) well ahead of Qwen
(40.1). That gap is a pooling artifact. The pool is each system's top 20, so a
comment at rank 21–50 is judged only if another system had it in its top 20,
and unjudged comments count as misses.
- **Coverage differs by system.** Only 62% of Qwen's top 50 is judged, against
  75% of OpenAI-large's. Qwen's deeper results are simply different from
  everyone else's.
- **The fix.** 150 of each system's unjudged top-50 comments were judged blind,
  884 pairs in all, and each system's unjudged comments were credited at its
  sampled relevance rate (`DEPTH50.md`):

| system | relevance rate of its unjudged top-50 comments | recall@50 corrected | est. precision@50 |
|---|---|---|---|
| qwen3-8b | 79% [71, 84] | **31.7** [30.6, 32.5] | 84% |
| oai-3-large | 80% [73, 86] | **32.1** [31.4, 32.6] | 85% |
| gemini-2 | 81% [74, 86] | **32.1** [31.3, 32.8] | 85% |
| oai-3-small | 71% [64, 78] | 29.8 [28.9, 30.6] | 79% |
| voyage-4-large | 70% [62, 77] | 29.0 [27.9, 30.0] | 77% |
| bm25 | 58% [50, 66] | 27.1 [26.1, 28.1] | 72% |

- **The top three tie on recall.** 3-small and Voyage are about 2–3 points
  lower, with non-overlapping ranges.
- **Why the numbers look low.** There are about 133 relevant comments per
  query, so even a perfect top 50 would reach only about 38 recall@50. Read the
  precision column for scale.
- **The intervals here** cover only the sampling of unjudged comments, not the
  sampling of queries.

Raw recall@20 is no help either. With that many relevant comments its ceiling
is about 28 for everyone, and all five models sit between 22.8 and 26.0.

### The plan's tie-break rule

The rule is to prefer `text-embedding-3-small` if it is within a point or two
of the best on recall. **It does not apply.**
- **Recall:** corrected recall@50 is 29.8 vs 32.1, 2.3 points behind, and that
  is on a scale whose ceiling is about 38.
- **Precision:** est. precision@50 is 79% vs 85%.
- **Ranking:** 3-small is 10 nDCG@10 points behind Qwen.
- **Cost:** the rule exists to buy savings, and 3-small costs twice what Qwen
  does.

## Per-category results (nDCG@10)

Category sizes are 9 to 18 queries, so treat any single cell as ±8 points.

| category (n) | best | Qwen3-8B | OAI-large | Gemini | OAI-small | Voyage | BM25 |
|---|---|---|---|---|---|---|---|
| attribute (15) | qwen+bm25 88.1 | 83.2 | 82.7 | 76.6 | 76.4 | 70.4 | 74.1 |
| avoid_negative (9) | oai-large@1024 76.9 | 67.4 | **76.7** | 56.3 | 65.6 | 73.0 | 69.2 |
| cuisine_neighborhood (14) | gemini 84.9 | 77.3 | 76.4 | **84.9** | 71.7 | 72.2 | 79.1 |
| dish (18) | qwen 88.9 | **88.9** | 75.0 | 69.8 | 71.8 | 64.9 | 70.7 |
| hard_case (15) | qwen@1024 73.0 | **72.9** | 66.2 | 68.2 | 56.5 | 62.7 | 45.1 |
| occasion_vibe (15) | qwen+bm25 84.6 | 80.2 | 80.7 | **84.3** | 72.8 | 72.1 | 69.6 |
| paraphrase_slang (12) | qwen@1024 75.6 | **74.8** | 73.8 | 57.0 | 69.8 | 42.2 | 54.2 |
| price (12) | qwen 85.1 | **85.1** | 80.6 | 77.6 | 70.4 | 73.8 | 68.1 |

- **Qwen** is strongest on dish, price, hard cases (exclusions and negation)
  and slang.
- **OpenAI-large** is best on avoid-intent queries ("overrated spots",
  "tourist traps").
- **Gemini** is best on cuisine plus neighborhood, where BM25 is also strong.
  Place names are keywords.
- **Hard cases** separate models the most. BM25 collapses to 45.1 there, and
  that is where dense retrieval earns its keep.

## Negation check

This counts comments in the top 10 that were judged 0 *and* flagged as on
topic but negated or opposite, such as "don't bring a date here" for *date
night*. Mean per query, with the number of queries (out of 110) that had at
least one:

| system | mean | queries with ≥1 |
|---|---|---|
| qwen3-8b | **0.17** [0.10, 0.25] | 17 |
| oai-3-large | 0.29 [0.15, 0.46] | 20 |
| gemini-2 | 0.35 [0.22, 0.52] | 25 |
| oai-3-small | 0.55 [0.37, 0.76] | 36 |
| voyage-4-large | 0.65 | 47 |
| bm25 | 0.73 | 45 |

- **Qwen makes the fewest of these errors.** Its CI overlaps OpenAI-large's but
  clears 3-small's.
- **Adding BM25 nearly doubles them for Qwen** (0.17 to 0.31). Keyword matching
  pulls in "date" from "don't bring a date here".
- **No model is immune.** The plan's downstream filters still matter: drop
  `is_negated` mentions and rank restaurants by distinct people.

## Restaurant-level view

Each system's top 50 comments were grouped by restaurant, skipping
`is_negated` mentions and `excluded_entities`. Restaurants were ranked by
distinct people. The table shows the share of the top 10 restaurants backed by
at least one comment judged ≥1.
- **Dense models:** OpenAI-large 91.5, Gemini 89.8, Qwen 86.9, 3-small 85.3,
  Voyage 80.8, BM25 79.9.
- **Hybrids** score highest (Qwen+BM25 93.6).

This view inherits the pool-depth bias above, and the judged-coverage column
shows it. Only 93% of Qwen's top-10 restaurants have any judged comment,
against 98% for OpenAI-large and 99% for the hybrids. An unjudged restaurant
counts as irrelevant, so the order among the top three dense models here is
within the bias. **No `reference_only` filter was applied:** the plan mentions
one, but no such column exists in production yet.

## Should search be hybrid (embedding + BM25)?

The plan intends RRF fusion with full-text search. Fusing BM25 into Qwen is
neutral on nDCG@10 (+0.5, noise) and slightly negative on P@20 (−1.6). It
nearly doubles negated hits. It helps weaker models more: Voyage gains 4.2
nDCG@10 and Gemini 2.1. OpenAI-large *loses* 1.7.

**Recommendation:** ship Qwen dense-only, and keep full-text search for
restaurant-name lookups. The query set deliberately has no bare name searches,
and those are where keyword matching earns its place. If hybrid is wanted
later, re-test it on name queries rather than assume it.

## Query vs document handling (what OpenRouter passes through)

Checked by real calls (`probe_inputs.py`, `probe_inputs2.py`). A setting
counted as passed through if the vector changed beyond each provider's repeat
noise. Repeat noise was cosine 1.000000 for all five.

| model | what works | what is silently ignored |
|---|---|---|
| Voyage 4-large | `input_type: query/document` changes the vector (cos 0.845 vs none) and equals typing Voyage's documented prompts by hand (cos 1.0). `dimensions` maps to Voyage's output dimension. | `output_dimension` |
| Gemini Embedding 2 | Prefixes in the text. OpenRouter's `input_type: query` adds exactly Google's `task: search result \| query: ` prefix (cos 1.0, +7 tokens). `dimensions` works. | `task_type` (Google says this model doesn't support it), `output_dimensionality`. OpenRouter's `input_type: document` adds an undocumented 2-token prefix, *not* Google's `title: … \| text: …`, so documents were formatted by hand per Google's docs. |
| Qwen3-8B | The model card's query instruction typed into the text (`Instruct: …\nQuery:`) changes the vector (cos 0.79). `dimensions=1024` equals truncation (cos 1.0). | `input_type` (cos 1.0 vs none on a pinned provider) |
| OpenAI 3-large / 3-small | Symmetric models, no query/document mode. `dimensions=1024` equals truncate + renormalise (cos 0.99999998). | `input_type` |

Two operational findings:
- **Qwen is served by two providers that disagree.** DeepInfra and Nebius
  return different vectors for the same text (cos 0.9976), so this run pinned
  DeepInfra with `allow_fallbacks: false`. Production must pin one provider, or
  query vectors drift slightly from the stored ones on a failover. Even on one
  provider, the same text in a different batch varied up to cos 0.9988.
  That's harmless for ranking, but it means vectors are not bit-reproducible.
- **Gemini rejects batches over 100 inputs.**

The Qwen query instruction was written once from the model card's convention
before any results: "Given a search query for New York City restaurants,
retrieve Reddit comments that recommend or describe places matching it". It
was not tuned.

## Cost, latency, storage

| model | price $/M tokens | this run, 97k comments + 7.6k threads | est. for all ~747k comments | query latency median / p90 | dims stored | bytes/vector (float32 / halfvec) |
|---|---|---|---|---|---|---|
| qwen3-8b | 0.01 | $0.058 | ~$0.40 | 410 / 436 ms | 4096 → **1024** | 4 KB / 2 KB at 1024 |
| oai-3-small | 0.02 | $0.113 | ~$0.80 | 410 / 511 ms | 1536 | 6 KB / 3 KB |
| voyage-4-large | 0.12 | $0.669 | ~$4.80 | 400 / 410 ms | 1024 | 4 KB / 2 KB |
| oai-3-large | 0.13 | $0.733 | ~$5.20 | 510 / 512 ms | 3072 (1024) | 12 KB (4 KB) / 6 KB (2 KB) |
| gemini-2 | 0.20 | $1.222 | ~$8.20 | 627 / 1026 ms | 3072 (1024) | 12 KB (4 KB) / 6 KB (2 KB) |

- **Prices** match OpenRouter's catalog. Every call's reported `usage.cost`
  equalled tokens × catalog price. Reported tokens came to 0.77× our pessimistic
  estimate (cl100k × 1.3), so provider tokenizers land close to cl100k.
- **Latency** is single-query embedding, 25 calls per model, from a laptop
  through OpenRouter, interleaved across models. Railway's absolute numbers
  will differ, but the ordering should hold.
- **Storage and indexing.** pgvector's HNSW index takes `vector` up to 2,000
  dims and `halfvec` up to 4,000. Native Qwen (4,096) cannot be indexed at
  all, and OpenAI-large or Gemini at 3,072 only as `halfvec`. At 1,024 dims any
  of them indexes as a plain `vector`. The eligible corpus at 1,024 float32 is
  about 400 MB.
- **Re-embedding cost.** A full re-embed with Qwen costs well under a dollar,
  so re-indexing after prompt or model changes is cheap.

## Threads (secondary)

The 7,658 threads behind the eligible comments were embedded as title +
selftext, with selftext cut at 1,500 characters. They were run against the
same 110 queries, with full tables in `RESULTS_TABLES_threads.md`.
- **Shallower pool.** As the secondary priority, threads were pooled from each
  system's top **5**, not 20: 2,252 pairs.
- **Separate guidelines section.** A thread section was added to
  `GUIDELINES.md` before any thread results were looked at.
- **Which metrics count.** Only @5 metrics are fully judged. The @10 numbers in
  the tables count every unjudged thread as a miss. For dense-only Qwen that is
  30% of its top 10, so ignore them.

| system | nDCG@5 | P@5 | MRR |
|---|---|---|---|
| qwen3-8b+bm25 | **85.1** [82.2, 87.9] | **94.4** [92.2, 96.4] | 99.1 |
| gemini-2 | 83.9 [79.9, 87.4] | 91.1 [87.8, 94.0] | 96.7 |
| oai-3-large | 81.9 [78.3, 85.3] | 90.7 [87.6, 93.8] | 96.4 |
| qwen3-8b | 81.2 [78.1, 84.3] | 89.8 [86.5, 92.7] | **99.1** |
| voyage-4-large | 81.0 [76.4, 85.2] | 89.1 [84.9, 92.5] | 93.5 |
| oai-3-small | 78.8 [74.6, 82.5] | 87.3 [83.3, 91.1] | 94.6 |
| bm25 | 71.5 [67.5, 75.6] | 84.0 [80.0, 87.8] | 93.3 |

- **The five dense models are statistically indistinguishable on threads.**
  Every pairwise nDCG@5 gap is within noise, except that Gemini and
  OpenAI-large beat 3-small, by +5.1 and +3.1. Qwen's first result is relevant
  for every query but one (MRR 99.1).
- **BM25 is far behind.** Thread titles are short questions, and the selftext
  is the asker's context, not the answer.
- **Truncating to 1024 dims costs a little on threads.** The loss is
  significant: Qwen −1.5 [+0.1, +2.9] nDCG@5, OpenAI-large −1.9 [+0.5, +3.2],
  Gemini −1.1 [+0.0, +2.2]. Threads run up to 1,500 characters, against about
  150 for comments, and longer texts use more of the vector. If threads are
  indexed, consider `halfvec(2048)` for them. Comments, the main index, show
  no loss at 1024.
- **Nothing here changes the comment-based recommendation.**
- **Judge agreement on threads** (225-pair re-judge): 89.8% exact (κ 0.83) and
  96.9% on relevant vs not (κ 0.89).

## Judge consistency

A seeded 10% of comment pairs (1,000) were re-shuffled into different batches
and graded again by different subagents against the same guidelines
(`agreement_comments.json`):
- **Exact 0/1/2 agreement:** 88.6%, Cohen's κ 0.81.
- **Relevant (≥1) vs not:** 96.5% agreement, κ 0.88.
- **No pair moved between 0 and 2.**
- **Where they disagree.** Almost all disagreements are on the 1/2 boundary
  (50 pairs went 1→2, 29 went 2→1), so P@10 counting grade-2 only is the
  softest metric. The ≥1 metrics rest on very stable labels.

## Spend

**$2.79 total** (`SPEND.md`, `data/ledger.jsonl`), against the $4.50 cap and
$5 budget. All of it was embeddings:
- **Gemini:** $1.22. **OpenAI-large:** $0.73. **Voyage:** $0.67.
  **3-small:** $0.11. **Qwen:** $0.06.
- **Probes and latency tests:** under a cent.

Nothing came near the cap. The dry run projected $3.64 with the 1.3× safety
factor.

## Caveats

- **Judges are Claude, not people.** Agreement is high, but a systematic Claude
  bias (for example, toward verbose recommendations) would shift every system
  similarly and could favour some. The guidelines were frozen before results.
- **Time span.** Eligible comments are almost all from 2025–2026: 2,619 from
  2022–2024 and none from 2021. Extraction hasn't been run on older history, so
  the corpus can't stratify across 2021–2026 as the brief asked. `CORPUS.md`
  has the strata as they are.
- **The queries are mine.** They were written before any results and frozen,
  but they are one author's idea of user searches. There are no bare
  restaurant-name queries.
- **Category cells are small** (9–18 queries).
- **Restaurant view and as-scored recall@50** inherit pool-depth bias. The
  depth-50 correction covers recall for the five dense models and BM25 only,
  not the hybrids or the restaurant view.
- **Thread pooling** is depth 5, not 20; see the thread section.
