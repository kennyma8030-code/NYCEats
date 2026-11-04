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
- Settling scores, a re-sweep of each city's last 48 h (every 6 h, never
  before the city's oldest stored comment), extraction, the scoring refresh
  (after any extraction, and at least every 6 h) and embedding run on one
  30-minute timer of their own, not per city poll.
- Unknown thread -> fetch the post, then every comment in it, before inserting.
  A post the archive does not have yet (posts can trail their comments by
  ~20 h) is asked for again on later polls for 48 h; when it appears its
  whole thread is pulled.
- Dedup on the `t1_`/`t3_` fullname. All inserts idempotent.
- History available back to 2014-08-24 (~747k comments, ~47k posts).

**Score settles once, at 40h** (`db.SETTLE_HOURS`). Arctic Shift's second
pass, at 36h, is the only update; re-fetching later returns the same number.
Asking a few hours after it leaves room for that pass to land late. Comments
and posts alike (posts' score, `upvote_ratio` and `num_comments`), each
tracked with `score_settled`. An item already past 40h when it arrives came
with its final numbers and is stored settled, flagged deleted already if
its record says so (below).

**`was_deleted_later`** flags comments and posts gone from Reddit. Required
for the permalink click-through rule — never link evidence that 404s. Arctic
Shift keeps a deleted item and returns it with its text replaced by
`[deleted]`/`[removed]` in place of its body or selftext, so that is a
deletion; the text we stored is kept. An author of `[deleted]` alone is not
one (a deleted account leaves its comments up), nor is a post's
`removed_by_category` (a post a moderator removed keeps its thread page).
An item the re-read does not return stays unsettled and is asked for again,
once a pass, for 48h (`db.SETTLE_MISSING_HOURS`); then it is settled and
flagged, the protective rule: never link evidence that may 404.

**Edits are ignored, on purpose.** The settle re-read takes scores and
deletions only; a comment's body and a post's selftext stay as first stored,
and nothing is extracted again for an edit. A mention stays tied to the text
it was read from, which is what its click-through shows.

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
retry after a timeout that may have been billed. That cap is per process;
`--ceiling-usd` / `EXTRACT_CEILING_USD` caps all v6 spend ever: before every
submission, spend recorded in the database plus every batch still in flight
there plus the request's worst case must fit, so a restarted process cannot
spend past it, and reaching it exits 0. A batch or call that costs more than
was held for it, or recorded spend over the ceiling, trips a wire that stops
the run (exit 5; a direct call only trips under a ceiling, so the poller
logs it and goes on). A model without a full, non-zero price list never
starts. Unattended runs go through `extract_runner.py` in a Railway service
of their own, deployed with `railway up` from a copy whose `railway.json` is
`railway.extract.json`. It requires both caps: `EXTRACT_RUN_USD` caps one
attempt (cut to what the ceiling leaves), `EXTRACT_CEILING_USD` is the total
across restarts. `--reset-hash` deletes recorded cost and so loosens it. A batch submission whose
outcome is unknown is never resubmitted; it stays pending until matched to
the API's batch list. One v6 run at a time, by advisory lock.

**Thread mode (built, not yet chosen).** `extract_v6.py --mode thread` sends
a post and up to ~25 of its comments as one request, to fit the backfill in
the owner's budget; it is benchmarked offline first
(`docs/handoffs/extraction-v6-thread.md`). Same cursor, same mention rows,
its own prompt hash (`d92ec8610d8c`: round 4's thread prompt plus a
`<post_item>` section, and replies to quoted comments pointing to the quote).
Whole reply groups (a top-level comment and its
replies) are packed to a soft budget of 15 items or 3,000 tokens; only a
group over 25 comments is split, between branches. A chunk whose comments
hang under comments outside it quotes their whole ancestor chain. A chunk's
own comments are cut at 6,000 characters, quoted ones at 1,500 (rendering
only: the hash is unchanged); `--redo-cut-before T` re-extracts the comments
read with the old 1,500 cut before T and replaces their mentions; a redo
chunk of several that fails has each of its comments retried in a chunk of
its own. A comment over 3,000 characters is always a chunk of its own: dense
lists in busy chunks came back empty or short. The post is
item `[0]` of a thread's first chunk while it is due, else context. Comments
already done, and deleted ones, are context only. A chunk whose answer is no
use (cut off, refused, not JSON, not storable) is split in half once; a half
that fails sends its items one at a time in comment and post mode. A chunk a
batch lost for other reasons (expired, an API error) is resent as it was.
Effort medium by default, `max_tokens` 32,000.

**Live extraction: one batch run a day.** `extract_runner.py`, a Railway
cron job (`0 9 * * *` UTC), runs thread mode through Message Batches over
every thread with anything not yet extracted, chosen by state rather than a
time window: posted at least 48 hours ago (`EXTRACT_MIN_POST_AGE_HOURS`;
a younger thread is not touched at all, so it is read once, whole, with its
first two days of comments), on or after its subreddit's floor
(`EXTRACT_SINCE`, required, one floor per subreddit taken or `all` said
outright: r/FoodNYC from mid-2025, the older backlog left on purpose), in
`EXTRACT_SUBREDDITS` (r/FoodNYC by default), newest first. No upper bound
on age: what a missed day, a cap or a failure leaves is the next run's, and
a late comment on a thread done before goes out with only itself numbered,
under the post and its quoted ancestors. A run caps itself at
`EXTRACT_RUN_USD` under the `EXTRACT_CEILING_USD` total, re-attaches any
batch an earlier run left in flight before sending anything, and after a
spend tripwire does nothing (exit 0, loudly) until a person names the batch
as seen. The redo of cut comments takes the run's subreddits too; comment
and post mode stay r/FoodNYC only. The prompt is written for New York ("a
New York City food subreddit", places outside the five boroughs are not
mentions, "best in NYC"), so another city needs a prompt of its own before
it is extracted; its mentions would be stored but not scored (scoring reads
`scoring_params.subreddit`).

**Names in other scripts.** `normalize_entity` keeps the letters of other
scripts when the Latin rules leave only a fragment: no key at all (불짬뽕,
which used to store no mention), or, for a name with letters of another
script, a key with no letter ("산수갚산 2" was "2") or only generic words
(`extract.GENERIC_WORDS`: "불짬뽕 NYC" was "nyc"). Latin letters with no
decomposition are kept there, folded the usual way (ß is ss, ø is o). A key
with a word of its own is kept, so bilingual names ("Xi'an Famous Foods
西安名吃", "游子老鸭粉丝馆 Yozi") still match the city's list, and no purely
Latin name changes key. Stored rows are not re-keyed.
`extract_v6.py --restore-unkeyed --yes` stores, from the answers on record,
the mentions dropped for an empty key.

Known limit: a key in another script is never `prompted` (scoring.sql's
"did the thread name the place?" flattens title and selftext to a-z0-9).
Accepted, and rare. Teaching it other scripts would mean a SQL copy of the
key rules, which would drift from extract.py, and CJK text has no spaces
between words to match a key against.

---

## Decided — storage

Two raw tables (`schema.sql`): `threads`, `comments`.

- Rows are appended, never deleted, and their text never changes. What
  changes in place is what the settle re-read learns: scores and
  `was_deleted_later`. The posts' columns for it (`threads.score_settled`,
  default true, and `threads.was_deleted_later`) are added by
  `migrations/live_extract.sql`, applied by hand (`psql -f`) before the web
  app or the poller is deployed: the feed names `was_deleted_later`
  outright. That file is only the ALTER; schema.sql has the same, and on the
  new poller's first boot also marks, once, the posts collected live up to
  the deploy to settle (first seen less than 40h after they were posted).
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

### Rating and recommenders (new, v6)

Built in `scoring.sql` section 8 (`rating_params`, `rating_mentions`,
`place_voices`, `place_recommenders`, `place_category_voices`,
`entity_rating`, `entity_category_rating`), served by `/api/boards`,
`/api/restaurants/{key}/voices` and a `rating` object on ledger rows and the
detail page. Reads v6's columns, so it needs `live_mentions` in v6 mode.

**Why.** 44.5% of v6's positive mentions are bare recommendations, a name
dropped with no judgment (`opinion = 'endorse'`). Counted as praise they put
the median place at 90% positive and 361 places at 100%; over stated opinions
only the board is about 74.5% positive. So the rating and the volume come from
different signals: stated opinions make the rating, and a bare endorse is
volume only. It can never change the rating, not even by being someone's
latest word.

**Window and exclusions** (`rating_mentions`, shared by everything below).
The last 365 days (`window_days`), r/FoodNYC, everything `live_mentions`
already leaves out, `excluded_entities`, mentions the model marked
`status = 'closed'` ("RIP Florent" nostalgia was ranking shut places) and
mentions marked `timeframe = 'past'` ("it used to be great"; a mention with
no timeframe stays). AutoModerator is dropped; `[deleted]` counts once per
comment.

**What a mention says**, tested in this order:

| voice | rule |
|---|---|
| neg | `avoid` ("skip it"), whatever else it says, so a warning is never a recommendation |
| endorse | `opinion = 'endorse'`, whatever level it carries |
| pos | `opinion = 'stated'`, overall level 1 or 2 |
| neg | `opinion = 'stated'`, overall level -1 or -2 |
| neutral | `opinion = 'stated'`, overall level 0 |

A mention with none of these (a fact, a question, a remark on the wait alone)
is not a voice and never hides an earlier one.

**One voice per person per place, picked twice**, because the two axes ask
different things:

- **Rating** (`place_voices`): each person's latest *stated* voice (pos, neg,
  neutral). A later bare endorse does not replace it.
- **Volume** (`place_recommenders`): each person's latest voice of any kind.
  A **recommender** is a person whose latest voice is an endorse or a stated
  pos. Two mentions of one place in the same comment (two spellings that
  resolve together) tie on time; the stated one wins.

**Per place** (`entity_rating`): pos, neg, neutral and `superlative` (latest
stated level 2) from the rating pass; `pct_pos = pos / (pos + neg)`; `lb` =
its Wilson lower bound at z = 1.28; `neg_share = neg / (pos + neg + neutral)`,
the complaint share of stated opinions. `endorse` (latest voice a bare
endorse) and `recommenders` from the volume pass. recommenders is not
pos + endorse: someone who praised a place and later only named it is one pos
and one recommender. **Rankable** at 10 or more stated non-neutral people
(`min_rated`).

**Categories** (`entity_category_rating`): taste, value, service, atmosphere,
wait. Each person's latest *stated* level for that category, by sign (a level
on a bare endorse is left out, as overall). pos, neg, pct_pos and lb as above;
rankable at 8 non-neutral people (`min_category_rated`).

**Badges**, one column, cut at percentiles at every rebuild so they keep their
meaning as the corpus grows. The lines are taken over rankable places the
boards can show (not on the city's chain list, not closed), then every
rankable place is badged against them:

- busy: recommenders at or above the top 10% (`busy_pct = 0.10`)
- share_line: median `lb` (`share_pct = 0.50`)
- gem_line: 85th percentile of `lb` among rankable places that are not busy (`gem_pct = 0.85`)
- `consensus` = busy and lb ≥ share_line; `overhyped_mixed` = busy and lb <
  share_line; `hidden_gem` = not busy and lb ≥ gem_line; otherwise none.

Measured Nov 3, 2026: 1,316 rankable places; busy at 76 recommenders,
share_line 0.661, gem_line 0.823; 82 consensus, 52 overhyped / mixed, 179
hidden gems.

**Boards.** Each ranks by one value; the rest are filters. Top: busy places by
lb. Popular: by recommenders, among places with lb ≥ share_line. Hidden gems:
by lb. Category boards: by the category's lb, among places rankable in it.
Overhyped / mixed is a badge, not a board. There is no Divisive badge.

**Click-through.** `place_voices`, `place_recommenders` and
`place_category_voices` keep the one mention each person was counted by, so
every count lists exactly its comments (`/voices?voice=pos` totals the card's
pos, `voice=opinions` its pos + neg, `voice=recommenders` its recommenders),
with permalinks suppressed where `was_deleted_later` is set.

**Rollout order.** The web app reads these views and never builds them.
Apply `scoring.sql` first (`refresh.py --apply`, or the poller's boot), then
deploy the web app. A web app that finds them missing (deployed first, or
after a rollback dropped them) checks once every 30 seconds and meanwhile
serves `rating: null` on the ledger and the detail page and 503 on
`/api/boards` and `/voices`, rather than failing.

Known limits: v6 codes lukewarm words (fine, meh, mid) as knocks and almost
nothing as neutral (0.6%), so `neg_share` sits close to `1 - pct_pos` until
the prompt fix lands. Generic keys ("grill", "modern", "joes") still merge
several places; that is identity's problem (resolve.sql), not the rating's.

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

**The model.** `qwen/qwen3-embedding-8b` through OpenRouter, pinned to one
DeepInfra endpoint with no fallback. DeepInfra and Nebius disagree (cos 0.9976).
The pin is the endpoint's exact tag, `deepinfra/us` (`order` and `only`),
plus its quantization label, `unknown` (`quantizations`), as OpenRouter's
endpoint listing gave them on 2026-10-19. A bare `deepinfra` would match
every DeepInfra endpoint, so a second region or a quantized variant could be
mixed in while the response still said DeepInfra. The response names only
the provider, so that is all `embedding.py` can check on the way back; the
tag and quantization rest on the routing. If the endpoint is renamed or
relabelled, requests get a 404 and the run stops; nothing is stored.
The model returns 4,096 dims; the first 1,024 are kept and L2-renormalised, stored as
`halfvec(1024)`. That scored within noise of full size on comments, and HNSW
cannot index a halfvec over 4,000 dims. OpenRouter's `dimensions: 1024` was
checked to give the same vector, so it is sent to shrink responses.
Documents are embedded raw. Queries get the model card's instruction
(`embedding.format_query`), because OpenRouter ignores `input_type` for Qwen.
All of it lives in `embedding.py`. `model` in the tables is
`embedding.MODEL_KEY` (`qwen/qwen3-embedding-8b@1024:deepinfra/us:unknown`:
model, dims, endpoint tag, quantization), and vectors are only comparable
within one value.

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
psql "$DATABASE_URL" -f embed_schema.sql     # once: pgvector, the tables, mentions_created_idx
python embed.py --dry-run                    # rows, tokens, projected cost; no call, no write
python embed.py --max-usd 0.50               # comments, then threads; resumable
python embed.py --build-index                # HNSW, only after the backlog has loaded
```

In this order, and with these preconditions:
1. **Deploy before the dry run.** Both candidate queries filter on `comments.subreddit`
   and `threads.subreddit`, which the multi-city deploy adds. Production did
   not have `comments.subreddit` yet on 2026-10-19, so until then even
   `embed.py --dry-run` fails on the missing column.
2. **The migration** (`embed_schema.sql`, or the boot after the deploy as a
   superuser). It can go before the deploy: it reads no `subreddit` column.
   Its index on `mentions` takes a SHARE lock, which blocks writes to
   `mentions`, and gives up after waiting 5 s for it. The build itself is
   well under a second, but the lock is held until the transaction commits.
   Applied by hand that is the file's own `commit`, right after. Left to the
   boot it is the end of the whole `schema.sql` transaction, v6 block
   included. Applying the file by hand first keeps it off the boot.
3. **Check the routing with one request**, right after the deploy and
   before any run. The quantization filter (`quantizations: ["unknown"]`)
   could not be tried without a paid call while this was built. This sends
   the exact routing `embedding.ROUTING` sends, for one short input, at a
   cost of about four tokens ($0.00000004). It writes nothing:
   ```
   curl -s https://openrouter.ai/api/v1/embeddings \
     -H "Authorization: Bearer $EMBED_OPENROUTER_API_KEY" -H 'Content-Type: application/json' \
     -d '{"model": "qwen/qwen3-embedding-8b", "input": ["NYCEats routing check"],
          "dimensions": 1024, "encoding_format": "base64",
          "provider": {"order": ["deepinfra/us"], "only": ["deepinfra/us"],
                       "quantizations": ["unknown"], "allow_fallbacks": false}}' \
     | jq '{provider, usage, error}'
   ```
   - A 200 with `"provider": "DeepInfra"` and a `usage` block: the pin works.
   - A 404 (no endpoint matches) or a 400 about the routing: first read the
     free listing,
     `curl -s https://openrouter.ai/api/v1/models/qwen/qwen3-embedding-8b/endpoints | jq '.data.endpoints[] | {tag, quantization}'`.
     If it still shows `deepinfra/us` with `"unknown"`, the filter is what
     fails. Delete the `"quantizations"` entry from `embedding.ROUTING`,
     keeping `only` and `order` (and update `PIN` in
     `tests/test_embedding.py`). `MODEL_KEY` stays as it is: the endpoint is
     the same, and the key's quantization records the listing's label. If
     the tag is gone or the label changed, that is a different endpoint:
     change `ENDPOINT`/`QUANTIZATION`, which is a model swap (below).
   `embed.py` would hit the same 404 on its first request and stop without
   storing or marking anything, so a skipped check costs nothing worse than a
   failed run.
4. **The dry run**, then the backlog. Only one run at a time: `embed.py`
   exits if the poller's embed pass holds the lock, and the pass skips while
   `embed.py` holds it. The lock belongs to a Postgres session. If the
   connection holding it goes half-open (the client vanished, say a dropped
   proxy, and the server never saw the connection close), the server keeps
   that session, and the lock, until its TCP keepalive reaps it. Until then
   every run reports "holds the lock". It heals by itself. To see who holds
   it (read-only):
   `select a.pid, a.state, a.backend_start, a.client_addr from pg_locks l join pg_stat_activity a using (pid) where l.locktype = 'advisory' and l.classid = 28281 and l.objid = 1667591522`
   (`embed.LOCK_KEY` split into its high and low 32 bits).
   `pg_terminate_backend(pid)` frees it at once, with the owner's go-ahead.
5. **The index build** needs at least 1 GB of free disk and about 256 MB
   of RAM headroom (`--index-mem 256MB`, serial). Expect the database to grow
   by about 0.75 GB in all: roughly 0.3 GB of `halfvec(1024)` rows for 141k
   vectors, and as much again for the two HNSW graphs. That is an estimate,
   not a measurement; check free disk on the Railway volume before the build.

A row is due when it has no vector for the current `MODEL_KEY`, or its stored
`input_hash` (sha256 of the exact text) no longer matches. Kill and restart
freely. A refused input is isolated by splitting its batch, then recorded in
`embedding_errors`. A recorded error is retried by itself once a day has
passed since it failed, while it has failed fewer than 3 times on the same
text, by `embed.py` and the poller alike (the poller retries them wherever
they fall in time). After that it waits for a new text, which starts the
count again, or `--retry-errors`. A 400 can also be about the request rather than the input
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
`POLL_EMBED_DAYS` (3). For comments that window is on when a mention was
stored (`mentions.created_at`, indexed by `mentions_created_idx`), not when
the comment was written: a comment can get its first mention long after it
was posted (a v6 backfill, an extraction retry), and a window on
`comments.created_utc` never embedded those. Inside the window only rows
with no vector yet are taken. Nothing the poller does rewrites a comment's
or a thread's text, and without that filter a backfill that touched every
mentioned comment would have each pass walk all of them for three days.
Changed text is found by a run without `--since-days`. Threads are
windowed on when they were posted.
**After every extraction backfill, run `python embed.py --max-usd <N>`.**
The poller would get there, but at 2,000 rows a pass, and only for mentions
stored in its last 3 days; anything it has not reached by then is left for
`embed.py`.
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

**A model, endpoint or quantization swap** is new rows, not a migration:
1. Change `MODEL`/`DIMS`/`PROVIDER`/`ENDPOINT`/`QUANTIZATION` in
   `embedding.py`. That gives a new `MODEL_KEY`, and a new index name (a
   long one ends in a hash of the key, so two keys never share one).
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
  This matters more here than on the board: vectors are kept when a comment
  is later deleted (nothing in `embed.py` removes them, and the text they
  were made from stays in `comments`), so a deleted comment can still be a
  top search hit. Search must read `was_deleted_later` from `comments` for
  every hit and return no permalink when it is set, as `app/queries.py`
  does for the board's comment lists.
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
