# NYCEats — algorithm spec

Supersedes the working notes where they conflict. Everything under **Decided**
is settled and measured; **Open** is still unresolved.

---

## Pipeline

```
Arctic Shift  ->  comments + threads  ->  mentions  ->  derived scores
   (raw)          (append-only)          (LLM)         (recomputable cache)
```

Only `mentions` and the raw tables are truth. Every score is a cache that can be
dropped and rebuilt.

---

## Decided — ingestion

**Source: Arctic Shift.** Reddit's `.json` API is WAF-blocked and OAuth
registration requires manual approval since late 2025. Arctic Shift retrieves via
the official API, captures ~20s after posting, and re-captures at 36h.

- Collect the seven largest city food subreddits (`subreddits.py`) into the
  same tables, told apart by `subreddit`. Only r/FoodNYC is extracted and
  scored; every reader of the corpus filters on `subreddit` first.
- Poll `/comments/search?subreddit=X&limit=100&sort=desc` per city, paging
  back until the page is 8 hours (`POLL_LAG_HOURS`) behind the newest
  comment the previous poll of that city saw (kept in memory, seeded from
  the table at boot -- not the table's max, which thread pulls and the
  backfill move ahead of the poll). The lag is because Arctic Shift
  publishes out of order: comments turn up as much as 8.8 h (p99) after
  newer ones, and stopping at the previous newest lost ~1%. Interval sized
  so the busiest hour of the past week fills half a page, clamped to
  10–60 min. Which cities are polled: `POLL_SUBREDDITS`, default all seven.
- Every boot resumes a per-subreddit backfill cursor in the background.
  Only r/FoodNYC by default: another city's history is swept only when
  `BACKFILL_SUBREDDITS` lists it and `BACKFILL_YEARS_OTHER` is not 0, and
  stops once the database passes `BACKFILL_MAX_DB_MB` (3,500). A city that
  fails three times in a row goes to the back of the queue rather than
  stalling the rest.
- Paging forward (backfill, thread pulls, re-sweep) asks for
  `after = newest - 1` and drops ids already seen: `after` is exclusive, and
  `after = newest` lost the rest of a page's last second.
- Settling scores, a re-sweep of each city's last 48 h (every 6 h),
  extraction, the scoring refresh and embedding run on one 30-minute timer
  of their own, not per city poll.
- Unknown thread -> fetch the post, then every comment in it, before inserting.
  A post the archive does not have yet (posts can trail their comments by
  ~20 h) is asked for again on later polls for 48 h; when it appears its
  whole thread is pulled.
- Dedup on the `t1_`/`t3_` fullname. All inserts idempotent.
- History available back to 2014-08-24 (~747k comments, ~47k posts).

**Score settles once, at 36h.** Arctic Shift's second pass is the only update;
re-fetching later returns the same number. Track with `score_settled`.

**`_meta.was_deleted_later`** flags comments gone from Reddit. Required for the
permalink click-through rule — never link evidence that 404s.

---

## Decided — extraction context

A comment alone is not enough context. Pass:

1. **Post title** (~61 chars avg)
2. **Post selftext** (~1,087 chars avg, present on 82% of posts) — carries the
   real ask: budget, neighborhood, what they've already tried
3. **Immediate parent comment** (~82 chars avg)

**Not the full ancestor chain.** Measured on a 215-comment thread: 70% of
comments are top-level, and only 15 of 215 sit deeper than one reply. Walking to
root costs tokens and usually lands on something unrelated.

`selftext` dominates the prompt. If cost matters, truncate it or extract
per-thread instead of per-comment.

This is the old extractor's input (`prompt.py`). v6 replaces it once switched
on (next section): the benchmark's review traced most missed mentions to the
place being named above the parent or past the post cut, so v6 passes up to
five ancestors.

---

## Decided — v6 extraction

Built in `extract_v6.py`, `prompt_v6.py`, `anthropic_v6.py` and
`extract_v6_schema.sql`, from the benchmark on branch `extraction-v6`
(`eval/prompts/v6_DESIGN.md`, `eval/review_v6r4/`). Off until the owner
switches it on; the handoff is `docs/handoffs/extraction-v6.md`.

**Exactly what was benchmarked.** Comment mode, round-4 prompt (hash
`979dcd6b9267`; post mode `436d834d7edd`). The prompt, schema and v6-to-legacy
mapping are the branch's files copied byte for byte into `prompts_v6/`, and
`tests/test_prompt_v6.py` pins their hashes and diffs them against the branch.
Model `claude-haiku-5-5`, adaptive thinking, effort `medium`, strict
`json_schema` output (nullable unions as `anyOf`), `cache_control` on the
system prompt, `max_tokens` 16,000, no sampling parameters. The benchmark's
code validators are not used at medium. Key: `EXTRACT_ANTHROPIC_API_KEY`,
nothing else.

**Input.** `<post_title>`, `<post_body>` (cut at 1,200; `author="you"` when
the commenter wrote the post), `<thread_above>` (up to five ancestors, oldest
first: the parent cut at 1,500, the rest at 300, labelled OP / you, earlier /
another user, deleted and missing ones marked), `<comment_to_extract>` with
`>` quotes marked. Rows are read from the database the way the benchmark's
builder read them, and `tests/test_extract_v6_db.py` checks the bytes match.

**What is extracted.** r/FoodNYC only. Every comment that is not
`[deleted]`/`[removed]`/blank, however short ("keens" and "+1" are evidence;
the old `length > 15` cut is gone). Every post, in post mode (title plus body
cut at 4,000), whose mentions name the thread instead of a comment.

**Storage.** v6 rows go into `mentions` beside the old ones, which are never
touched: `schema_version = 6`, the v6 fields as columns (levels as -2..2,
kind, opinion, experience, avoid, dish opinions, notes, tags, timeframe,
trend, status, price), each mention's raw JSON, and the legacy columns filled
through the benchmark's adapter so scoring reads v6 rows unchanged.
`extraction_state` is the v6 cursor (not `comments.extracted_at`, so both
extractors can run at once) and keeps the model's whole answer per item.
Chains are kept with `is_chain` instead of deleted; excluded kinds (grocery,
brand, venue, company, other) are kept with their kind.

**One switch for readers.** scoring, resolve and the API read `live_mentions`,
a view over `mentions` chosen by the one row in `extraction_settings`:
`legacy` (default: exactly today's rows) or `v6` (v6 rows minus excluded
kinds, chains.txt names and post mentions, which scoring cannot place yet).
`extract_v6.py --read v6` flips it and refreshes. Separately,
`EXTRACT_VERSION=v6` makes the poller extract new rows with v6.

**Failures.** max_tokens, refusal and invalid JSON are the item's: retried
once, then parked with a coded `extract_error`. A 4xx other than 429 stops
the pass and marks nothing. 429/5xx back off, then stop the pass if they
persist. Spend is capped by reserving each request's worst case (16k tokens
out, all input as cache writes) before it is sent, and again before any
retry after a timeout that may have been billed. A batch submission whose
outcome is unknown is never resubmitted; it stays pending until matched to
the API's batch list. One v6 run at a time, by advisory lock.

---

## Decided — storage

Two raw tables (`schema.sql`): `threads`, `comments`.

- `comments.thread_id` is a real FK; the poller guarantees the post exists first.
- `comments.parent_comment_id` is **not** a FK — 56% of replies arrive before
  their parent. `fill_tree` resolves `root_comment_id` and `depth` after insert
  with a recursive CTE, and self-heals when late parents land.
- Facts get copied in (`restaurant_raw`), conclusions get referenced
  (`entity_id`) so re-resolution never destroys evidence.

---

## Decided — scoring

Unchanged from the working notes:

- **Volume** — decayed mention count, half-life ~180d.
- **Momentum** — 7d decayed count ÷ volume. Cancels "famous", leaves "changing".
- **Lazy decay** — store `(value, last_updated)`, shrink on next touch. Do the
  shrink-and-add in one `on conflict do update` so concurrent mentions can't
  clobber each other.
- **Weighting at mention time** — per-author cap, `N/sqrt(N)` thread divisor,
  momentum floor ~5 weighted mentions, separate "new" label for no-baseline
  entities.
- **Price is two fields** — `expensiveness` (fact) and `value` (opinion).
- **Aspects** — per `(entity, aspect)` decayed `W` and `S`, mean `S/W`, shrunk
  toward city mean. Missing renders as absent, never neutral. A 0 is "mixed".

### Upvotes (new)

**Score does not multiply volume.** Volume measures attention; a mention is a
mention.

Score weights the **aspect sentiment** mean only:

```
w = 1 + log(1 + max(score, 0))
```

Log-compressed, or one +347 comment outweighs 300 others. Floor negatives at 0.

Caveats: 49% of comments sit at score 1, so it adds signal for a minority. And
score partly measures *posted early*, not *is right* — the same correlation the
thread divisor already fights.

**`controversiality`** is Reddit's own mixed-vote flag. Free input to the
deferred polarization work, though it describes the comment's reception rather
than the restaurant's.

---

## Decided — semantic search embeddings

Vectors for semantic search are a **cache**, like every score: three tables
(`comment_embeddings`, `thread_embeddings`, `embedding_errors`) that can be
dropped and rebuilt with `embed.py`. They are never columns on `comments`.
The model was picked by the benchmark on branch `worktree-agent-abf6969e5737447f0`
(`eval/embeddings/RESULTS.md`).

**What is embedded.** Only r/FoodNYC (`subreddits.HOME`). The other cities
are collected but not searched, and embedding their backfilled history would
be paid for and never read, so both candidate queries filter on `subreddit`.
- **Comments.** Every comment with at least one `mentions` row (under any
  prompt hash) whose body is not `[deleted]`/`[removed]`, about 97k. The text
  is thread title, a blank line, then the comment body. No parent and no
  selftext: selftext is shared by the whole thread and would pull its comments
  together. One vector per comment. Search groups by restaurant through
  `mentions` when it reads, never at embed time.
- **Threads.** All of r/FoodNYC's, about 44k. The text is the title, a blank line,
  then the selftext cut to 1,500 characters (blank if removed).
- **Nothing is filtered at embed time** for `excluded_entities`, unresolved
  names, `is_negated` or `reference_only`. Those move with identity decisions
  and prompt versions, so filtering them belongs to the query.

**The model.** `qwen/qwen3-embedding-8b` through OpenRouter, pinned to
DeepInfra with no fallback. DeepInfra and Nebius disagree (cos 0.9976).
The model returns 4,096 dims; the first 1,024 are kept and L2-renormalised, stored as
`halfvec(1024)`. That scored within noise of full size on comments, and HNSW
cannot index a halfvec over 4,000 dims. OpenRouter's `dimensions: 1024` was
checked to give the same vector, so it is sent to shrink responses.
Documents are embedded raw. Queries get the model card's instruction
(`embedding.format_query`), because OpenRouter ignores `input_type` for Qwen.
All of it lives in `embedding.py`. `model` in the tables is
`embedding.MODEL_KEY` (`qwen/qwen3-embedding-8b@1024:deepinfra`), and vectors
are only comparable within one value.

**Keys.** `EMBED_OPENROUTER_API_KEY` if set, else `OPENROUTER_API_KEY`. Give
embeddings their own key with its own limit, so they can never exhaust the
key extraction runs on.

**Running the backlog.** It costs about $0.09 (8.6M tokens at $0.01/M).
`embed.py` is a pipeline script like `refresh.py` and `backfill.py`: it
reads `DATABASE_URL` and writes to production, so it is run on purpose, one
run at a time, never as an experiment. Only `--dry-run` and
`--build-index --dry-run` are read-only.

Production has pgvector 0.8.6 available but not installed (checked
2026-10-19). The next poller boot installs it through the guarded block in
`schema.sql`, which needs a superuser role because pgvector is not a
trusted extension (`select rolsuper from pg_roles where rolname =
current_user`). Without one the block logs a notice, the boot carries on,
and embedding stays off until a superuser applies `embed_schema.sql`.

```
psql "$DATABASE_URL" -f embed_schema.sql     # once: pgvector + the tables
python embed.py --dry-run                    # rows, tokens, projected cost; no call, no write
python embed.py --max-usd 0.50               # comments, then threads; resumable
python embed.py --build-index                # HNSW, only after the backlog has loaded
```

A row is due when it has no vector for the current `MODEL_KEY`, or its stored
`input_hash` (sha256 of the exact text) no longer matches. Kill and restart
freely. A refused input is isolated by splitting its batch, then recorded in
`embedding_errors` and skipped until its text changes, or until
`--retry-errors`. A 400 can also be about the request rather than the input
(an unsupported parameter, a routing error), and then every batch is refused.
So the first time a run gets down to one refused input, it sends a one-line
canary with the same request shape. If that is refused too, the run stops.
A run also stops after 50 rejected rows, and never splits deeper than 8
levels. An auth, credit, outage or malformed-response failure stops the run
too, and leaves the rows to do. The spend cap reserves each request before sending it.
Attempts that may have been billed without returning vectors (timeouts, 5xx,
a 200 without vectors) are charged against it.

The poller keeps up with new comments when `POLL_EMBED=1`. Its 30-minute
chores pass runs settle, extract, refresh, then embed, over the last
`POLL_EMBED_DAYS` (3).
Embedding goes last so it can never delay the board. It is capped by
`POLL_EMBED_LIMIT` (2,000 rows) and `POLL_EMBED_MAX_USD` ($0.05) per pass,
and stops starting new batches after 5 minutes; the city polls wait behind
it, which costs freshness, not comments, since each poll pages back. `POLL_EMBED_SCOPE` is
`comments` by default, so new threads need `both` or a periodic
`embed.py --scope threads`. The step is fail-soft: with no key or an invalid
scope it switches off at boot, and an error or outage in it is logged and
skipped.

**The index** is built after the backlog, never before: a graph maintained
through 140k inserts is far slower than one built once. There is one partial
index per table and model (`... where model = '<MODEL_KEY>'`). The build is
`CONCURRENTLY` and serial: Railway's small `/dev/shm` kills parallel builds
the same way it killed the parallel refresh.

**A model or provider swap** is new rows, not a migration:
1. Change `MODEL`/`DIMS`/`PROVIDER` in `embedding.py`. That gives a new
   `MODEL_KEY`.
2. Run `embed.py`. Every row is due under the new key; the old rows are
   untouched and search keeps working.
3. Run `embed.py --build-index` for the new partial index.
4. Point search at the new key, then
   `delete from comment_embeddings where model = '<old key>'` (and the same for
   threads and `embedding_errors`), and drop the old index.

A dims change past 1,024 also needs a new column type, since the columns are
`halfvec(1024)`.

**What search must do when it reads:**
- Say `where model = '<MODEL_KEY>'` as a literal, or the partial index is not
  used.
- `set hnsw.iterative_scan = relaxed_order` (pgvector 0.8+; production has
  0.8.6). Otherwise a time window or the filters below empty out the 40
  candidates HNSW returns, and results silently starve.
- Filter at read time: mentions of `excluded_entities` (on the resolved key),
  `is_negated` mentions, and `reference_only` once that column exists.
- Suppress permalinks where `was_deleted_later` is set, like everywhere else.
- Embed the query with `embedding.embed_query`. It uses the same model,
  provider, instruction, cut and keep-alive session.

---

## Open

- **Entity resolution.** Still the hardest part and most likely to sink it.
  pgvector is available in Postgres, so embedding + gazetteer blocking can live
  in the same database.
- Unresolved names: pending-cluster, drop, or manual queue.
- Chains, closed restaurants.
- Exact half-lives, pseudo-count, momentum floor. All still placeholders.
- Whether aspects beyond `food` and `value` produce signal at low volume.
- Frontend framework.

---

## Deferred — now buildable

The original notes deferred these for lack of history. **The history exists** —
12 years of it — so these are buildable as soon as backfill runs, not in two
years:

- **Polarization** — 5-bucket decayed histogram per aspect.
- **Longevity** — undecayed `first_seen`, `total_mentions`, monthly coverage
  bitmap. Note ~145 months of history, so one 64-bit int is not enough.
- **Sentiment momentum**, separate from volume momentum.

---

## Non-negotiable

Every score clicks through to the comments that produced it, with live Reddit
permalinks. Suppress links where `was_deleted_later` is set.

## Rejected

A single composite score. Rank by whichever axis the user picks; everything else
is a filter or a badge.
