# Handoff: v6 extraction pipeline

Built on branch `extraction-pipeline`, on top of `main` at `5bb3344` (which
includes `integrate-embed-poller` and its review fixes). It puts the benchmarked v6 setup from
branch `extraction-v6` into production code, switched off. Nothing has been
run against Railway: no migration, no API call, no backfill. Every test ran
against throwaway local Postgres 17 and 18.6 servers, with a fake Anthropic
server standing in for the API.

## What is in it

| File | What it is |
|---|---|
| `prompts_v6/` | `v6_common.py`, `v6_comment.py`, `v6_schema.json`, `v6_adapter.py` from `extraction-v6`, byte for byte |
| `prompt_v6.py` | loads them; reads the rows the renderer needs from the database |
| `anthropic_v6.py` | the request (the benchmark's `anthropic_backend.params` at effort medium), pricing, error sorting, batch calls |
| `extract_v6.py` | candidates, writer, direct and batch runs, dry run, status, the read switch |
| `extract_v6_schema.sql` | the migration (also the last block of `schema.sql`) |
| `scoring.sql`, `resolve.sql`, `app/queries.py`, `refresh.py` | read `live_mentions` instead of `mentions` |
| `poller.py` | `EXTRACT_VERSION=v6` runs the v6 step in the chores pass |

`extract.py --v6 ...` is the same as `extract_v6.py ...`.

## What runs, and how it matches the benchmark

- Prompt: round 4, comment mode `979dcd6b9267`, post mode `436d834d7edd`.
  `tests/test_prompt_v6.py` pins the sha256 of every vendored file and diffs
  each one against `extraction-v6` when the branch is in the repository.
- Request: `claude-haiku-5-5`, `max_tokens` 16,000, `thinking: adaptive`,
  `output_config: {effort: medium, format: json_schema}`, the strict schema
  with nullable unions rewritten as `anyOf`, `cache_control: ephemeral` on the
  system prompt, no temperature. `tests/test_anthropic_v6.py` checks it is
  equal to the benchmark backend's `params()` (vendored verbatim as
  `tests/oracle_v6/anthropic_backend.py`) and checks what the real SDK puts
  on the wire.
- Input: the benchmark's `build_user_message`, fed rows read the way
  `eval/build_comment_rows.fetch_rows` read them. On a fixture database the
  rows are equal to the benchmark builder's (vendored verbatim as
  `tests/oracle_v6/build_comment_rows.py`), and the rendered bytes match.
- No code validators, as decided for medium.
- Batch API for the backlog, direct calls for the poller.

### Deviations, and why

- **Client retries.** The benchmark's client let the SDK retry 4 times. This
  one turns SDK retries off and retries 429/5xx/connection errors itself
  (6 attempts, honouring `retry-after`), so it can charge possibly-billed
  timeouts against the cap. Timeout is 300 s. Nothing the model sees changes.
- **Ancestor walk.** It has a guard against a cycle in parent ids. The
  benchmark's walk has none, and on any real chain it makes no difference.
- **Post mode body cut** is 4,000 characters, as in the benchmark's
  `build_post_message`. The brief said "title + selftext". This is the
  benchmarked cut.

## Behaviour worth knowing

- **Candidates.** r/FoodNYC only. Every comment except `[deleted]`,
  `[removed]` and blank, however short. Every post. The cursor is
  `extraction_state (item_id, version='v6')`, so the old extractor's
  `comments.extracted_at` neither hides comments from v6 nor is touched by
  it. The candidate query does not use `comments_unextracted_idx`, which
  belongs to the old cursor. With `--since` it uses `comments_sub_created_idx`.
  The full backlog is one anti-join. `--since` is on `created_utc`, so it
  misses late arrivals (comments that land days after they were written,
  about 280 a week, and posts likewise); a run with no `--since` selects
  exactly what is due, late arrivals included.
- **Writer.** Batched, because the backfill runs from a laptop about 325 ms
  from production per round trip. Submitting a batch is one statement for the
  ledger row and every member's state row, in a transaction that ends at once.
  Collecting one parses every answer first, then writes 200 items per
  transaction in a few statements (the previous attempts, the mention rows,
  the state rows: done, the model's whole answer, usage, cost). If the
  database refuses a row, that chunk is written again one item at a time, so
  only the bad item is parked. The direct path writes each item the same way,
  as a chunk of one. Measured through a proxy adding a ~394 ms round trip, a
  2,000-item batch took 3.7 s to submit and 19.5 s to collect, against about
  12 and 67 minutes before. Legacy columns are filled
  through `prompts_v6/v6_adapter.py`'s `to_legacy`. v6 columns hold levels as
  -2..2. `raw` is each mention as returned. Two spellings of one place in one
  item make one row, as before, and the second spelling stays in
  `extraction_state.output`. Chains get `is_chain`. Excluded kinds get their
  `kind`.
- **Failures.** stop_reason `max_tokens` or `refusal`, invalid JSON, a
  database refusal of the row, or a batch request that errored or expired:
  the first time, the item is queued again; the second time, it is parked
  with `extract_error` = `max_tokens: ...`, `refusal: ...`, `invalid_json: ...`,
  `store_error: ...`, `batch_errored: <type>: ...` or `batch_expired`.
  `--retry-errors` returns parked items to the queue. Failed attempts are
  billed, and their cost is recorded too.
- **Fail loud.** A 4xx other than 429 (direct, at batch submit, or an
  `invalid_request_error` inside a batch) logs the API's body and stops the
  run. Nothing unsent is marked. The poller prints `EXTRACTION STOPPED` and
  goes on polling, and the next pass tries once more. Rate limits and outages
  back off, and stop the pass if they last.
- **Spend cap.** `--max-usd` caps one invocation. Each direct request holds
  its worst case before it is sent (all input billed as a cache write plus
  16,000 output tokens: about $0.0103 direct, $0.0051 batched). Each batch
  holds the sum for its requests, and is cut to fit what remains. Holds turn
  into actual cost as results arrive, so the cap bounds real spend plus what
  is in flight. A direct request that times out may have been billed: it is
  charged its worst case, and its retry goes out only if a fresh worst case
  still fits, so retries can never take spend past the cap (the poller's
  `POLL_EXTRACT_MAX_USD` likewise). Batches re-attached from an earlier run
  count against the cap until they are collected. The cost is computed from usage at $0.10/MTok
  in, $0.50 out (thinking included), $0.01 cache read and $0.125 cache write,
  halved in a batch. It is logged per run and per poller pass.
- **Batches.** Each sub-batch is recorded in `extract_batches` before it is
  submitted, and its items carry its id. A re-run re-attaches to
  uncollected batches instead of resubmitting them, and a batch is priced from
  every answer it returned. A submission that times out, drops, or gets a 5xx
  may still have been accepted, so it is never retried: its `pending-...` row
  and hold stay and the run stops. The next run looks for it in the API's
  batch list (created near the row's time, same number of requests) and
  adopts it if exactly one matches. If none matches, the row is over 30
  minutes old (`MATCH_AFTER`), and the listing (read page by page) reached
  back past the row's time minus 5 minutes, and no unowned batch with the
  same number of requests was created at any time after that (a slow upload
  can land past the 30-minute adoption window: that blocks "none" and stops
  for a person), the submission made nothing: the
  row is dropped and its items are due again. Otherwise it stops until
  `--resolve-pending PENDING_ID <batch id from the Console | none | auto>`.
  Reading a batch back (status, results, the batch list) is safe to repeat,
  so a 429, a 5xx, a dropped connection, a results stream cut halfway, or
  the SDK's own errors there (a missing `results_url`) are retried for about
  seven minutes before the run stops. A 404 or another 4xx is not retried.
  A batch the API answers 404 for (past retention, or another key) is marked
  `lost` instead of failing every later run; its items stay out of the queue
  until a person checks the Console and runs `--drop-batch BATCH_ID`.
  At most 4 sub-batches of 2,000 are in flight. The cap limits that further:
  at `--max-usd 70`, about 13,700 requests' worst case fits at once.
- **One run at a time.** Every v6 run that writes takes a Postgres advisory
  lock. A manual run exits if the poller's pass holds it; the poller's pass
  skips if a manual run (the backfill) holds it. Leaving the poller on
  `EXTRACT_VERSION=v6` during a backfill is therefore safe, but its passes
  do nothing until the backfill ends.
- **Ctrl-C** stops a direct run without sending anything more: requests on
  the wire finish, the rest of the page is cancelled.
- **The poller's v6 pass** does posts first, with a tenth of
  `POLL_EXTRACT_LIMIT`, then comments with the rest, so a busy hour cannot
  starve posts. Its window (`POLL_EXTRACT_DAYS`) is on `first_seen_at`, when
  the item reached this database, not on `created_utc`, so late arrivals are
  extracted. `first_seen_at` is NOT NULL with default `now()` on both
  `comments` and `threads`, so no coalesce with `created_utc` is needed; the
  migration adds `comments_first_seen_idx` for it (an optimisation: if its
  build waits over 5 s for a lock it is skipped with a notice, and a later
  boot builds it). The window is also bounded by age: the pass takes only
  items written in the last `POLL_EXTRACT_V6_MAX_AGE_DAYS` (default 7).
  Any bulk insert of old r/FoodNYC comments makes every one of them "first
  seen" now: `backfill.py`, **the poller's own gap-fill backfill on boot**,
  or a re-sweep. Without the bound the poller would buy them at the direct
  price, up to `POLL_EXTRACT_MAX_USD` a pass ($30 to $48 a day). Older late
  arrivals are left for a batch catch-up
  (`extract_v6.py --batch --max-usd N`, no `--since`) at half the price, and
  each pass logs `left N item(s) ... for a batch catch-up`. When that number
  grows, run the catch-up.
- **Redoing a prompt.** `extract_v6.py --reset-hash H [--scope ...]` counts
  the v6 mention rows and cursor rows of prompt hash H; with `--yes` it
  deletes them, 5,000 items per transaction (an item's mentions and its
  state row together), so those items are due again and go out under the
  current prompt. Old (legacy) rows are never touched. It refuses while any
  item of H is in a batch (pending, submitted or lost). `live_mentions`
  counts a v6 row only while its comment's `extraction_state` row carries
  the same prompt hash, so rows of a superseded hash are never live, even
  before they are deleted. The legacy branch of the view is unchanged.
  While the board reads v6, a reset that deleted anything refreshes the
  scoring views, as the switch does.
- **Flip safety.** `--read v6` prints the coverage and refuses (unless
  `--force`) while any r/FoodNYC comment the old extractor read more than
  2 hours ago (`--flip-grace-hours`), and that is not now deleted or
  removed, has no finished v6 extraction, or while more than 0.2% of v6
  items are parked (`FLIP_MAX_PARKED_SHARE`). The old poller keeps
  extracting about 500 comments a day until step 11 switches it, so its
  last pass or two are forgiven and reported as "allowed". Anything older
  must be covered. `--read legacy` is never checked.
- **Old tools.** `extract.py --reset` refuses the v6 hashes (v6 has its own
  cursor). `sync.py` sends only old rows. `migrate_keys.py` keys post rows
  on their thread. `embed.py` embeds comments with mentions of any
  extraction, deliberately: a vector must not need re-buying when the board
  flips.

## Production steps, in order

Each step needs the owner's go-ahead. The orchestrator runs them one at a
time. All of them run from `.claude/worktrees/backend` after
fast-forwarding it to `main`, which reads `DATABASE_URL` from its `.env` and
writes to production. Only `--dry-run`, `--status` and `--reset-hash`
without `--yes` are read-only.

1. **Apply the migration, before deploying.**
   `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f extract_v6_schema.sql; echo "exit $?"`.
   Exit 0 means every step applied. Anything else means psql stopped at the
   failing statement and ran nothing after it: read the error, fix the
   cause (or wait for a quiet moment if it was a lock timeout), and run the
   same command again. Without `ON_ERROR_STOP`, psql reports the error, goes
   on with the rest and still exits 0. It adds nullable columns
   to `mentions` (catalog-only). It drops NOT NULL on `mentions.comment_id`.
   It adds `mentions.thread_id` (FK to threads), two NOT VALID checks, the
   partial unique index `mentions_post_unique_idx` (one read of mentions),
   `extraction_state` and its batch index, `comments_first_seen_idx` (one
   read of comments under a SHARE lock, seconds, during which the poller's
   inserts wait), `extract_batches`, `extraction_settings` (`legacy`)
   and the view `live_mentions`. If an earlier version of that view is in
   place (one without the prompt-hash check), it is replaced, once. Old rows
   are untouched, and the board reads
   exactly what it reads today. The same block is at the end of
   `schema.sql`, so the poller's first boot would apply it anyway. But the
   web app reads `live_mentions` as soon as it deploys. Apply first, or the
   API errors until the worker has booted.
   Lock waits are capped at 5 s (`lock_timeout`). If one fires, that step
   rolls back whole (nothing half-applied); run the file again, ideally at a
   quiet hour. Every later run, and every boot, alters nothing and takes no
   lock on `mentions`, `comments`, `extraction_state` or `live_mentions`. The
   file does not need `comments.subreddit`.
2. **Deploy** (merge to `main`). This changes nothing visible:
   `EXTRACT_VERSION` is unset, so the poller keeps the old extractor, and
   `read_version` is `legacy`.
3. **Add the key.** Put `EXTRACT_ANTHROPIC_API_KEY` in the backend
   worktree's `.env`, for the pilot and the backfill. Give it its own
   Console workspace limit if possible. No other key is ever used.
4. **Dry run, after the deploy.** The candidate query filters on
   `comments.subreddit`, which step 2's deploy adds (`schema.sql`, on the
   poller's boot). Against a database that does not have it yet, the dry run
   fails. Check with
   `select 1 from information_schema.columns where table_name = 'comments' and column_name = 'subreddit'`.
   Then run `python extract_v6.py --dry-run --since 2026-09-15 --limit 3000 --scope comments`,
   then the same with no filters, for the whole backlog. It renders and
   prices, and sends and writes nothing. Check the item counts and the
   estimate.
5. **Pilot** (about $1 expected at the measured $0.30 per 1,000; the dry
   run's estimate is more conservative; $7 of caps in all):
   - `python extract_v6.py --batch --scope comments --since 2026-09-15 --limit 3000 --max-usd 5`
   - `python extract_v6.py --batch --scope posts --since 2026-08-01 --limit 200 --max-usd 1`
   - `python extract_v6.py --batch --scope comments --max-chars 15 --limit 200 --max-usd 1`
   - `python extract_v6.py --status` shows done, parked by code, batches and spend.

   The cap holds each batch request's worst case, about $0.0051 to $0.0053,
   until its batch is collected. So `--max-usd 5` fits about 940 to 980
   requests in flight at once, not 3,000. The first command therefore goes
   out as about **four sub-batches, one after another** (about 960, 900,
   850, then the last 280 or so). Each waits for the one before to end and
   free its hold. Expect four batch turnarounds, not one. `--max-usd 16` would
   send it as two sub-batches at once (2,000 and 1,000), still spending
   about $1.
6. **Review the pilot** (read-only queries). **Two slices were never
   benchmarked and must be checked by hand, explicitly:** post mode (the
   benchmark built it but every measured run was comment mode) and comments
   of 15 characters or fewer (every benchmark item came from production's
   `length > 15` pool). Read a sample of each against its output before the
   backfill: do bare names, "+1" and "this" under a recommendation get the
   verdict the prompt's rules give them, and do posts extract the places the
   poster asks about with opinion "none"? Then compare v6 against the old rows
   on the same comments:
   `select comment_id, entity_key, schema_version, overall_level, aspects from mentions where comment_id in (...)`.
   Look at the parked errors, the excluded kinds
   (`select kind, count(*) from mentions where schema_version = 6 group by 1`),
   the short comments and the post mentions. Check the measured cost per
   1,000 items in the run's summary line.
7. **Full backfill.**
   `python extract_v6.py --batch --max-usd <N>`. The benchmark's measured
   rate is about $0.30 per 1,000 comments in batch, which is about $65 to $70
   per year of r/FoodNYC at today's activity. The whole history (about 747k comments and 47k
   posts) is therefore about $230 to $260. Take N from step 4's dry run, with
   headroom. A larger N also lets more sub-batches run at once. The run is
   resumable: kill it and re-run freely, and it re-attaches.
   **How long.** About 794k items make about 397 sub-batches of 2,000. The
   laptop's share is serial: rendering, submitting and collecting a batch
   take about 20 s of database work at 325 ms a round trip (measured through
   a latency proxy). That is about 2.2 hours for the whole backlog, against
   about 18 days before the writes were batched. Uploading the requests is
   about 58 MB per batch (23 GB in all), so a slow uplink adds hours. The
   rest is the API's batch turnaround T, with `--max-inflight` batches at
   once: about 397 × T / max-inflight. At the default of 4, that is about
   25 hours if batches end in 15 minutes and about 100 hours if they take an
   hour. `--max-inflight 16` cuts that by four. It needs N to cover 16
   holds of about $10.40 each (about $166), which an N of $300 does.
   Watch for disk: the v6 rows plus `extraction_state.output` add roughly
   0.5 GB to a 922 MB database (an estimate, not measured).
   **Then embed what the backfill made eligible:**
   `python embed.py --dry-run`, then `python embed.py --max-usd <N>` (N from
   the dry run, with headroom; the whole comment backlog is about $0.09).
   Do this after every extraction backfill, and after step 9 too. A comment
   whose first mention the backfill wrote has no vector yet. The poller's
   embed pass does pick up mentions stored in its last 3 days, but only
   2,000 rows a pass and only inside that window. Comments that already had
   a vector are not bought again: a vector counts mentions of any extraction.
   `embed.py` exits if the poller's embed pass holds the lock; run it again.
8. **Make scoring v6-aware (scoring v3) BEFORE the flip. The flip is
   blocked until this ships.** Today's scoring reads v6 rows through the
   legacy columns, and three of its rules misread them:
   - v2's bare-mention test compares food to exactly 0.3, but v6 writes 0.33
     for an endorsement, so no v6 bare name is recognised as bare;
   - a v6 knock is -0.67, which crosses v2's -0.6 strong-negative cut, so
     every plain knock counts as a standout negative;
   - the adapter fills food from overall when taste is null, so a verdict on
     the place reads as a verdict on the food.
   Scoring has to read the v6 columns (`overall_level`, `taste_level`,
   `opinion`, ...) or be re-tuned on v6 rows first. `--read v6`'s own check
   (step 10) only checks coverage and parked items. It does not know about
   scoring, so this step is enforced by process, not code.

Steps 9 to 11 go **back to back, at a quiet hour**. The old poller keeps
extracting about 500 comments a day, and setting `extracted_at` on them,
until step 11 switches it. So the closer the last v6 sweep is to the flip,
the less there is between them. `--read v6` forgives only the old
extractor's last 2 hours (`--flip-grace-hours`).

9. **Close the gap.**
   - `python extract_v6.py --batch --max-usd 10`, with **no `--since`**. The
     anti-join selects exactly what is due, which is what arrived since step 7
     began plus every late arrival: comments that landed with an old
     `created_utc` (about 280 a week, and the poller's boot backfills) and
     posts. A `--since` on the day step 7 started would miss those, because
     it filters on `created_utc`. The old extractor kept serving the board
     meanwhile. Then `--status`: nothing should be in a batch or owed a retry.
   - **Immediately before the flip**, sweep what arrived during that batch's
     turnaround with direct calls: `python extract_v6.py --max-usd 1` (no
     filters; usually tens of items, cents).
10. **Flip the board.** `python extract_v6.py --read v6`. It first prints
   the coverage, then refuses while any r/FoodNYC comment the old extractor
   read over 2 hours ago has no finished v6 extraction (run step 9's sweep
   again), or while more than 0.2% of v6 items are parked (see `--status`,
   then `--retry-errors`). What the old poller extracted in the last 2 hours
   is counted and allowed. `--force` overrides both checks. Do not use it to
   get past a coverage refusal: that number is comments whose mentions would
   vanish from the board. Then it sets
   `extraction_settings.read_version = 'v6'` and refreshes the scoring
   views. Not in one transaction: `momentum_windows` cannot refresh
   concurrently, and holding its lock to the end would block board reads.
   So for as long as the refresh takes (minutes), a place's mention list,
   dishes and the feed already read v6 while the leaderboard still ranks the
   old rows. To undo it: `python extract_v6.py --read legacy`.
11. **Flip the poller, right after.** On Railway, set `EXTRACT_VERSION=v6` and
    `EXTRACT_ANTHROPIC_API_KEY`, and optionally `POLL_EXTRACT_MAX_USD` (the
    per-pass cap, default $1.00) and `POLL_EXTRACT_V6_MAX_AGE_DAYS` (default
    7). Keep `POLL_EXTRACT=1`, then redeploy. The
    boot log says `inference on: v6 (claude-haiku-5-5, effort medium, prompt 979dcd6b9267/436d834d7edd)`.
    Between steps 10 and 11 the old poller's new mentions are not on the v6
    board. Its first v6 pass takes those comments, because their
    `first_seen_at` is inside its window. If `EXTRACT_VERSION=v6` is set
    while the board still reads `legacy`, the boot warns that the board
    would get no new mentions. So do 10 before 11, and close together. To
    undo it: unset `EXTRACT_VERSION` and redeploy. Afterwards, watch the
    poller's `left N item(s) ... for a batch catch-up` line (old items that
    a boot backfill or `backfill.py` inserted). Run the batch catch-up when
    it grows.

**After a prompt fix**, re-extract what the old prompt did with
`python extract_v6.py --reset-hash <old hash> [--scope comments|posts]`.
It only counts. Add `--yes` to delete, then run a batch. While the board
reads v6, the reset items' mentions are off the board until they come back
(the reset refreshes the scoring views). Rows of a superseded hash are never
live anyway (see Redoing a prompt).

## Open questions

- **Post mentions are stored but not scored.** `live_mentions` leaves them
  out in v6 mode, because every scoring view joins a mention to a comment
  for its author, date and thread. Counting them needs `scoring.sql` to read
  thread-level mentions (author = the post's author, date = the post's).
- **Chains.** v6 keeps chains.txt mentions (`is_chain`). The v6 view still
  leaves them out, so the board's composition matches today's. To count them,
  delete one line in `live_mentions`.
- **`is_chain` is a write-time snapshot of `chains.txt`.** That is derived
  data on an evidence table. The brief asked for it, and the storage draft
  argued against storing it. If `chains.txt` changes, one `update` recomputes
  it, or it could move into a small `chain_keys` table read by the view.
- **Excluded kinds** follow the benchmark's adapter: grocery, brand, venue,
  company, other. The owner's store policy is that list.
- **Storage size.** `extraction_state.output` duplicates each item's mentions
  next to `mentions.raw`. It is kept because it is the only place a
  duplicate spelling, a blank name or an empty answer survives.
- **Old-extractor statistics.** `/api/stats` `extracted` follows the switch.
  Nothing else in the app reports the old cursor.
- **The dry run's estimate is conservative.** It assumes 1,200 output tokens
  (the benchmark's planning figure for medium) and shows both the
  all-cached and the no-cache price. The measured $0.30/1k sits near the
  cached end.

## Testing

`TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:<port>/<name>test python -m pytest tests`
was run against a throwaway Postgres 18.6 (the first version also against
17.11). The result was 192 passed and 38 skipped. The skipped tests are the
embedding tests: the server had no pgvector. The v6 tests cover:

- prompt and schema parity, by hash and against the branch
- rendering parity with the benchmark's builder, on fixture rows
- the request on the wire
- error sorting: 400, 401, 403, 404 and 413 are fatal; 429, 500, 503 and 529
  back off; a connection failure is counted as possibly billed
- stop reasons
- the spend cap, direct and batch
- re-attaching after an interrupted run, and the pending-row stop
- one retry for errored and expired batch requests; an invalid request
  inside a batch is fatal
- the writer round trip, including the legacy columns, kind flags, chains and
  posts
- short comments included, deleted ones excluded, r/FoodNYC only
- the old cursor ignored
- the read switch, through `scoring.sql`, `mention_weights` and `/api/stats`
- the migration on a pre-v6 database
- the dry run writing nothing
- the CLI
- the poller's v6 step and boot checks
- the review's fixes: an ambiguous batch submission (5xx after acceptance,
  timeout) kept pending and adopted by the next run without resubmitting,
  or stopped for a person when no single batch matches; timeouts unable to
  push spend past `--max-usd` or `POLL_EXTRACT_MAX_USD`; Ctrl-C sending
  nothing more; the advisory lock keeping the poller and a manual run apart;
  a batch priced from all its answers; a 404 batch marked lost and dropped by
  hand; posts' share of the poller's limit; `--reset`, `sync.py` and
  `migrate_keys.py` leaving v6 rows alone; guarded, lock-free re-runs of the
  migration
- the audit's fixes (`tests/test_extract_v6_audit.py`), run against a
  throwaway Postgres 17.11 with 216 passed and 38 skipped (pgvector again):
  submitting a batch in two statements, and collecting it in a few
  statements per 200-item chunk however many mentions it holds (counted on
  the wire); the batched writer matching the per-item one, and a refused
  row parking only its item; the migration and the whole boot schema
  applying at once behind an open write to `extraction_state` and open board
  reads (main's version waits 5 s and fails); the first `live_mentions`
  replaced once, then left alone; batch reads retried through 529, 500, 502,
  429, a truncated results stream and a missing `results_url`, the list paged,
  4xx and 404 not retried; a pending row settled as none only when old and
  covered; the poller's window on `first_seen_at`; `--reset-hash` counting,
  deleting in chunks, refusing a hash with items in a batch, and leaving old
  rows alone; a superseded hash never live, the legacy view unchanged; and
  `--read v6` refusing on coverage and on parked items, and `--force`
- the review's follow-ups (same file; 250 passed, 53 skipped after merging
  main): the old poller's last 2 hours forgiven by the flip check but not
  older ones, nor any with `--flip-grace-hours 0`; a slow upload landing
  after the adoption window blocking "none"; the poller leaving old bulk
  inserts for a batch and saying how many, and `POLL_EXTRACT_V6_MAX_AGE_DAYS`
  moving the bound; `--reset-hash` refreshing the views only when the board
  reads v6 and something was deleted; `comments_first_seen_idx` skipped on a
  lock timeout and built by the next run; a `ValueError` from our own code
  not retried as a stream error

No paid call was made, and production was never connected to.
