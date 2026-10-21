# Handoff: v6 thread mode

Built on a worktree branch off `main` at `1ab4191`. It adds a thread mode to
the v6 pipeline: one request per chunk of a thread (the post and up to about
25 comments) instead of one per comment, because comment mode cannot fit the
~755k-comment backlog in the owner's $95. Nothing was run against
production: no migration, no API call, no write. Production was read only,
with read-only SELECTs, to build the eval slices and to size the backlog.
Every test ran against a throwaway Postgres 18 (pgvector image) in Docker,
with `tests/fake_anthropic.py` standing in for the API.

Thread mode is off unless asked for (`--mode thread`). Comment and post mode,
the poller and the board are unchanged.

## What is in it

| File | What it is |
|---|---|
| `thread_chunks.py` | the chunker and the call to the renderer: pure functions, shared by production and the eval |
| `prompts_v6/v6_thread.py` | round 4's thread prompt and `render_chunk`, plus two additions (below) |
| `tests/v6_thread_additions.py` | exactly those additions, as replacements on the benchmark's file; a test applies them to the branch's bytes and compares |
| `prompt_v6.py` | exposes `SYSTEM_PROMPT_THREAD`, `PROMPT_HASH_THREAD` (`ac9b063da8e6`), `SCHEMA_THREAD`, `fetch_thread_rows` |
| `anthropic_v6.py` | `params`/`worst_case`/`parse` take thread mode's effort, 32k and schema; comment mode's request is unchanged |
| `extract_v6.py` | the thread mode section: candidates, jobs, direct and batch runs, answers, failures, dry run, status, CLI |
| `extract_v6_schema.sql`, `schema.sql` | `extract_chunks` and two indexes, at the end of the mirrored block |
| `extract.py` | `--reset` also refuses the thread hash |
| `.gitattributes` | `prompts_v6/** eol=lf`, so the pinned hashes hold on Windows checkouts |
| `eval/` | the benchmark harness from `origin/extraction-v6` (no `runs/` except round 4's two comment runs), plus `eval/thread_v6/` |

## The chunking rules

As decided with the owner, in `thread_chunks.py`:

- A **group** is a top-level comment and every reply under it, depth-first,
  siblings by posting time. A reply whose parent is not in the database
  starts a group of its own. A corrupt cycle in parent ids loses nothing.
- Whole groups are **packed** until a soft budget: 15 items or 3,000
  estimated tokens of comment text (characters / 4, each comment cut at
  1,500), whichever comes first. One group may stay whole past the budget up
  to the hard max of 25 comments. `--chunk-comments`, `--chunk-tokens` and
  `--chunk-max` set them.
- Only a group over 25 comments is **split**, depth-first, and only between
  branches; a branch that alone is over 25 is split inside it. The comment
  whose branches were split goes at the head of the chunk with its first
  replies, not alone at the end of the one before.
- Only **due** items count and are numbered (the same QUEUED rule as comment
  mode). A comment already done under v6, or `[deleted]`/`[removed]`/blank,
  is never an item; it appears only as context when a due reply hangs under it.
- The **post** is item `[0]` of a thread's first chunk while it is due, with
  its body cut at post mode's 4,000 characters, and it counts as one item
  against the soft budget (not against the hard max). Everywhere else, and
  whenever it is already done (1,988 posts were done in post mode), it is
  context, cut at 800. `--scope comments` keeps it context everywhere.
- A chunk whose comments hang under comments outside it **quotes each such
  comment's whole ancestor chain**, from the top-level comment down to the
  direct parent, at full text (cut at 1,500), with no depth cap. The chain
  stops at a comment that is in the chunk, since that one is drawn anyway.
  Quoted lines have no number, so no mention can be filed under them, and
  they are never items or billed as items.

Measured on the eval slices: chunks average 9 to 13 items; quoted context is
0.1% to 1.3% of the user message.

## What changed in the renderer and the prompt

`prompts_v6/v6_thread.py` is `origin/extraction-v6:eval/prompts/v6_thread.py`
plus exactly the six replacements in `tests/v6_thread_additions.py`. No
import needed fixing (the file loads `v6_common.py` from its own folder).

1. A docstring paragraph saying what production added.
2. Constants: `POST_ITEM_CHARS = 4000`, `CONTEXT_CHARS = 1500`, and the
   context block's header line.
3. `render_chunk(title, selftext, rows, outside=None, above=None, post_item=None)`.
   Called without the two new arguments it returns exactly round 4's bytes
   (tested against the branch's function).
4. Rendering: `post_item` (the thread id) numbers the post `[0] POST: ...`
   and cuts its body at 4,000; `above` draws, between the post and the
   comments,

   ```
   Earlier comments in this thread, quoted as context (not in this chunk; never extract from them):
   u/zed: "Noodle Lab for knife-cut, skip the dumplings"
     u/yan (reply to u/zed): "they closed"
       (a deleted comment, reply to [2])
   ```

   A quoted comment says what it answers, like a numbered one: `[n]` when its
   parent is in the chunk (a done or deleted comment between two numbered
   ones), else the parent's author. Numbered comments keep round 4's markers,
   including the 140-character stub for a parent outside the chunk.
5. The id map gets `{0: thread_id}` when the post is an item.
6. The prompt: a `<post_item>` section right after `</input>`, everything
   else round 4 verbatim. Its middle sentences are post mode's own
   (`SYSTEM_PROMPT_POST`'s `<input>`), with "here" made "for item 0":

   > When the post itself is numbered, "[0] POST: ...", it is an item too:
   > extract its title and body, written by the poster, and its mentions
   > carry "id" 0. Extract the places the post names and what the poster says
   > about them, their own visits and verdicts included. A place the post only
   > asks about ("is X worth it?") is a mention with opinion "none". named_in
   > is always "comment" for item 0. A post with no number is context only.

   The hash moves from round 4's thread hash to `ac9b063da8e6`. The prompt
   says nothing about the quoted context block; the block's header line
   carries the instruction. That is a judgment call worth watching in the
   eval (see open questions).

## Request, answers, storage

- **Request**: the thread system prompt (cached), strict `SCHEMA_THREAD` (an
  integer `id` first in every mention), adaptive thinking, `--effort low|medium`
  (default medium), `max_tokens` 32,000. The worst case held per chunk is all
  input as cache writes plus 32,000 out (about $0.0093 a chunk in a batch,
  twice that direct), so `--max-usd` stays a hard cap on both paths.
- **Ids**: a mention counts only when its `id` is an integer that numbers an
  item of the chunk. Out of range, `0` when the post was context, `"1"`,
  `true`, `1.0` or null are dropped and logged (`bad_ids` on the chunk row),
  never guessed. The whole answer, bad ids included, is kept.
- **Items**: every numbered item gets its own `extraction_state` row, done
  even with no mentions: the thread hash, its own mentions as its output
  (`{"mentions": [...], "chunk_id": ...}`), and an equal share of the chunk's
  cost (the shares sum to the chunk's cost exactly). `usage` on the item says
  which chunk it was and how many items shared it; the chunk's real usage is
  on its row. Mention rows are written by the same writer as comment mode
  (`write`, `to_legacy`, the same conflict targets): a comment's rows have
  `comment_id`, the post's have `comment_id` null and `thread_id` set and use
  `mentions_post_unique_idx`, and its state row is keyed by the thread id with
  kind `post`. Permalink and `was_deleted_later` rules are untouched.
- **`extract_chunks`**: one row per chunk: id (the batch custom_id), thread,
  prompt hash, effort, whether the post was `[0]`, members in bracket order,
  quoted context ids, generation, the chunk it was split from, status
  (`queued`, `batched`, `done`, `failed`, `dropped`), `fallback`, batch id,
  error, bad ids, the whole answer, usage, cost, timestamps. A chunk and its
  items commit in one transaction; if the database refuses one item, the
  chunk's row is committed on its own and the items are retried one at a
  time, as in comment mode.
- **One cursor**: both modes read and write `extraction_state` under the
  same advisory lock, so they never both extract an item. Items in a thread
  batch carry its id, so comment mode cannot take them. `live_mentions`'
  hash check works as before, and post mentions stay off the board as they
  do in post mode.

## Failures

A chunk that stops at `max_tokens`, refuses, returns invalid JSON, or errors
or expires inside a batch is recorded as failed and split in half (the post
stays in the first half); both halves are queued in `extract_chunks`. A half
that fails too is marked `fallback`, and its items go out one at a time in
comment and post mode, where they get comment mode's own retry and are then
parked with a coded `extract_error`. A failed chunk's cost stays on its row.
No due item is left without a row saying what happened to it. The direct
path does all of this in the same run, page by page; the batch path sends
the halves and the items alone in the next sub-batches of the same run, and a
re-run picks up anything still queued, retries first. A queued half whose
items were all extracted since is marked `dropped`.

## Batches

One request per chunk, custom_id the chunk id. Before submitting, one
transaction writes the `extract_batches` row, every chunk's row (`batched`)
and every member's state row with the batch id. A re-run re-attaches to
batches in flight, and any run (comment or thread mode) collects either kind:
a thread batch is recognised by its `extract_chunks` rows. Pending
submissions are matched or settled as before; settling as none, or dropping
a lost batch, puts its chunks back to `queued` as recorded. Holds are per
chunk, sub-batches are cut to what remains under the cap, `--max-inflight`
applies.

## CLI

`--mode thread` rather than `--scope threads`: `--scope` already says which
items (comments, posts, both), and thread mode is how they are sent, so the
two combine (`--mode thread --scope comments` keeps posts as context;
`--scope posts` is refused, since posts alone are post mode's).

```
python extract_v6.py --mode thread --dry-run --newest-first --limit 2000   # read-only: threads, chunks, sizes, context, price at medium and low
python extract_v6.py --mode thread --batch --max-usd N [--effort low] [--since 2026-08-01] [--newest-first] [--ids t3_a,t3_b] [--limit THREADS]
python extract_v6.py --status        # adds per-prompt-hash lines and chunks by status, effort and cost
python extract_v6.py --reset-hash ac9b063da8e6 [--yes]   # undo thread mode only
```

With `--mode thread`, `--limit` counts threads, `--ids` takes thread ids and
`--since` is on the post's date. `--effort`, `--newest-first` and the chunk
sizes are refused in comment mode, which runs as benchmarked.

## The schema step

`extract_chunks` and its two indexes are new, at the end of the mirrored v6
block in `extract_v6_schema.sql` and `schema.sql`, guarded like the rest
(`create table if not exists`, indexes behind `to_regclass` checks,
`lock_timeout` 5 s). A new table takes no lock anything else waits on. It
needs applying before any thread-mode run (thread mode refuses to start
without it; comment mode does not need it):

```
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f extract_v6_schema.sql; echo "exit $?"
```

The poller's next boot would apply it too. It was applied only to the
throwaway test database.

## How much the backlog costs: read this before the eval

A read-only count of r/FoodNYC's reply groups (755,054 live comments in
36,624 threads with comments), packed as the chunker packs them, gives about
**75,000 chunks at 10.5 items each**. Priced with the output model fitted to
the benchmark's round-1 thread runs (`anthropic_v6.THREAD_OUTPUT`: 2,950 +
550 tokens an item at medium, 2,250 + 345 at low), that is about **$180 at
medium and $125 at low**, $0.24 and $0.17 per 1,000 comments: not inside $95.
Two things make that estimate pessimistic, and the eval measures both:

- those runs were on v2's diagnostic chunks, 1.1 places a comment; the
  backlog has fewer (the old extractor found 0.73 per comment it read, and it
  skipped the short ones);
- the fit's fixed part (about 2,950 tokens a chunk at medium) is most of the
  cost at 10 items a chunk. If it is real, bigger chunks are cheaper per
  comment, the opposite of the 12-vs-15 comparison in the plan.

So after the eval, fit `THREAD_OUTPUT` to the measured runs (every record
has its chunk size and output tokens), then run the read-only production dry
run above for the real price. I would also add one cheap run that measures
the fixed part directly (see the plan).

## The eval (offline, through `eval/run.py`)

The head-to-head runs through the harness, never through `extract_v6.py`
(a production comment holds one v6 state row). `eval/run.py --threads SLICE`
chunks and draws with `thread_chunks.py` and `prompt_v6`, imported, and
caches each chunk to `eval/runs/` as before. `eval/thread_v6/`:

| File | What it does |
|---|---|
| `slices.py` | builds the slices from production, read-only (done; committed in `slices/`) |
| `chunked.py` | the run jobs for a slice: production's chunker, renderer and prompt |
| `plan.py` | prices every run (the table below), writes `plan.json` |
| `review.py` | round 4's finals, provisional scores, packets with planted errors, check, score, posts vs post mode |
| `score_gold.py` | v1 and v2half against gold, side by side on the comments every run covers |
| `RUBRIC_THREAD.md` | what the round-4 rubric needs added for chunks and the post |
| `selftest.py` | the whole harness offline: the fake API through `run.py --batch` under a ledger, review and scoring |

The slices (built from production on 2026-10-21; the post is graded wherever
it is item `[0]` of a chunk that is sent, and never sent for):

- **fresh**: the 300 held-out comments in their 296 threads; only the
  chunk(s) holding a target are sent. Graded with the round-4 rubric:
  `review.py finals` rebuilds round 4's sealed key from the committed run
  files (build.py is deterministic), checks that the rebuilt packets equal
  the committed ones byte for byte, and rescoring comment mode's fresh-med
  gives 0.791 again. A thread output equal to its comment's round-4 finals is
  right without a judge; every other one is judged blind. So item_ok_rate
  compares directly with comment mode's 0.791.
- **v1**: the 17 whole threads (425 comments now, 374 of them gold), against
  `eval/gold.jsonl`.
- **v2half**: 240 of v2's 481 comments (seed `nyceats-thread-v6-slices`,
  listed in `slices/v2half.items.txt`), in their threads, against
  `eval/v2/gold.jsonl`.
- **big**: 10 threads of the last 12 months holding a reply group over 25
  comments, at most 150 comments each (888 in all), whole.
- **recent**: 40 of the owner's 100 post-reviewed threads (Aug 1 to Oct 21
  2026), whole; `review.py posts` sets each `[0]` beside post mode's answer.

Grading for big and recent is a sample of chunks (default 12 a run), every
item in them, so a mention filed under the wrong comment is counted
(`misattributed_mentions`). About 8% of judged items carry a planted change:
round 3's five kinds plus a place moved in from another item of the chunk.
The key and its salt are in `eval/thread_v6/.sealed/`, which git ignores; the
salt is random, so the key cannot be rebuilt from the repo.

### Cost plan (batch prices)

"Expected" assumes the system prompt is read from cache (the benchmark's
batches hit it on 99% of requests); "uncached" bills it fresh every time;
"worst" is what the ledger holds before a chunk goes out. The post as `[0]`
adds $0.05 in all.

| run | slice | effort | chunks | items numbered | graded | expected | uncached | worst case | cap |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| fresh-med32k | fresh | medium | 300 | 3,877 | 430 | $0.80 | $1.01 | $2.78 | $1.40 |
| fresh-low | fresh | low | 300 | 3,877 | 430 | $0.55 | $0.76 | $2.78 | $0.95 |
| v1-med32k | v1 | medium | 35 | 434 | 434 | $0.09 | $0.11 | $0.32 | $0.20 |
| v1-low | v1 | low | 35 | 434 | 434 | $0.06 | $0.09 | $0.32 | $0.15 |
| v2half-med32k | v2half | medium | 197 | 2,666 | 302 | $0.54 | $0.68 | $1.83 | $1.10 |
| big-med32k | big | medium | 67 | 873 | 873 | $0.18 | $0.23 | $0.62 | $0.40 |
| recent-med32k | recent | medium | 73 | 712 | 712 | $0.16 | $0.21 | $0.67 | $0.35 |
| big-med32k-c12 | big | medium, soft 12 | 82 | 873 | 873 | $0.19 | $0.25 | $0.76 | $0.45 |
| **total** | | | 1,089 | 13,746 | 4,488 | **$2.58** | $3.34 | $10.09 | **$5.00** |

That is below the orchestrator's $4.04, mostly because the fresh chunks come
out at 13 items, not 25. The output model leans high (dense chunks), so the
real bill should be at or under "expected". Each cap is about 1.75 times its
run's expected cost, and the caps sum to $5.00. A cap below a run's worst case
still runs, in smaller sub-batches one turnaround after another, so a run
may take several batch turnarounds.

Optional, not in the owner's plan: `big-med32k-c25` (`--chunk-comments 25`,
42 chunks, $0.16 expected, $0.39 worst) measures whether bigger chunks are
cheaper per comment, which is the question the $95 turns on. To fit it under
$5.00, cap fresh-med32k at $1.25 and v2half-med32k at $0.95 and give it $0.30.

### Commands, in order

From the worktree root. `KEYFILE` is a file holding the extraction key; each
run has its own ledger, so its cap is its own. `--batch` waits for each
sub-batch before the next.

```
python eval/thread_v6/selftest.py                  # offline; must print ok
python eval/thread_v6/plan.py                      # the table above
python eval/thread_v6/review.py finals             # rebuild round 4's key; must print 0.791

R="python eval/run.py --api anthropic --model claude-haiku-5-5 --mode thread --schema --cache --max-tokens 32000 --batch --key-file KEYFILE --key-var EXTRACT_ANTHROPIC_API_KEY"
S=eval/thread_v6/slices
L=eval/thread_v6/ledgers
$R --threads $S/fresh.threads.jsonl  --reasoning medium --tag fresh-med32k   --budget-file $L/fresh-med32k.json   --budget 1.40
$R --threads $S/fresh.threads.jsonl  --reasoning low    --tag fresh-low      --budget-file $L/fresh-low.json      --budget 0.95
$R --threads $S/v1.threads.jsonl     --reasoning medium --tag v1-med32k      --budget-file $L/v1-med32k.json      --budget 0.20
$R --threads $S/v1.threads.jsonl     --reasoning low    --tag v1-low         --budget-file $L/v1-low.json         --budget 0.15
$R --threads $S/v2half.threads.jsonl --reasoning medium --tag v2half-med32k  --budget-file $L/v2half-med32k.json  --budget 1.10
$R --threads $S/big.threads.jsonl    --reasoning medium --tag big-med32k     --budget-file $L/big-med32k.json     --budget 0.40
$R --threads $S/recent.threads.jsonl --reasoning medium --tag recent-med32k  --budget-file $L/recent-med32k.json  --budget 0.35
$R --threads $S/big.threads.jsonl    --reasoning medium --tag big-med32k-c12 --chunk-comments 12 --budget-file $L/big-med32k-c12.json --budget 0.45
```

Each writes `eval/runs/claude-haiku-5-5__ac9b063da8e6__thread__<tag>_schema.jsonl`
(call it `RUN(<tag>)`). A run stopped by its cap exits 3; re-running the same
command resumes. Then, with no API:

```
python eval/thread_v6/review.py cost RUN(fresh-med32k) RUN(fresh-low) ... RUN(big-med32k-c12)   # $/1k comments, output fit
python eval/thread_v6/review.py provisional RUN(fresh-med32k) RUN(fresh-low)    # against round 4's finals, before judging
python eval/thread_v6/score_gold.py v1 RUN(v1-med32k) RUN(v1-low)
python eval/thread_v6/score_gold.py v2half RUN(v2half-med32k) --baseline eval/runs/claude-haiku-5-5__979dcd6b9267__comment__bench6-med-r4_schema.jsonl
python eval/thread_v6/review.py packets RUN(fresh-med32k) RUN(fresh-low) RUN(recent-med32k) RUN(big-med32k) --sample-chunks 12
#   -> eval/thread_v6/review/packets/tNNN.md; one Opus judge per packet, with
#      eval/review_v6r4/RUBRIC.md and eval/thread_v6/RUBRIC_THREAD.md
python eval/thread_v6/review.py check
python eval/thread_v6/review.py score                  # -> eval/thread_v6/review/report.md
python eval/thread_v6/review.py posts RUN(recent-med32k) --postreview DIR_WITH_batchN.txt
```

`--baseline` in `score_gold.py` narrows to the comments every run covers;
round 4's comment runs saw only part of v2, so that comparison is on the
overlap. `big-med32k` against `big-med32k-c12` compares by `review.py cost`
(per 1,000 comments, and the fitted fixed and per-item output) and by the
judged sample. Put the fit from all the runs into
`anthropic_v6.THREAD_OUTPUT` before the production dry run prices the
backlog.

## Open questions

- **The budget.** The read-only projection above puts the backlog over $95
  even at low unless the eval's measured output is well under the dense
  fit. The decision (effort, chunk size, or a subset of years) needs the
  eval's numbers.
- **The quoted context block is not described in the prompt.** Its header
  line says it is context. I did not add prompt text for it, because the
  owner approved only the `<post_item>` change; if the eval shows mentions
  taken from quoted lines (they would be dropped as bad ids, or misfiled
  under a reply), that is the place to look.
- **The post's body cut in `[0]` is 4,000** (post mode's), against 800 when it
  is context. I read "extracted under the same rules post mode uses" as
  including post mode's input cut.
- **A thread whose comments are all done but whose post is due** gets a chunk
  with only `[0]`, in the thread prompt; post mode would also do. Left in
  so that thread mode alone covers a backfill.
- **Effort is not in the hash.** Low and medium runs share `ac9b063da8e6`,
  so `--reset-hash` cannot undo one effort alone; `extract_chunks.effort`
  records it. Stamping effort into the hash would change what the hash means
  everywhere else.
- **Equal cost shares.** Each item gets an equal share of its chunk's cost;
  splitting by text length is easy if per-comment cost matters.
- **The eval/ tree.** It is copied from `origin/extraction-v6` (minus
  `runs/`, `v4/`, `baseline/`, `labels/`, `results/`, the rejudge), with two
  changes: `eval/budget.py` now locks its ledger on Windows too (it used
  `fcntl` only), and `eval/run.py`/`eval/score.py` know thread-slice records.
  Merging this branch puts a tracked `eval/` on `main`, where the main
  checkout has an unrelated untracked `eval/` folder: move that aside first.

## Testing

`TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55461/threadtest python -m pytest tests`
against a throwaway Postgres 18 with pgvector (Docker image
`pgvector/pgvector:pg18`): **402 passed, 3 skipped** (the three skips are the
embedding tests that need the benchmark's local cache). New:

- `tests/test_thread_chunks.py` (18, no database): grouping and packing by
  count and tokens, a big group whole up to 25, splitting only between
  branches and inside an oversized branch, the split comment carried to its
  replies, orphans, cycles, done and deleted comments as context only, a
  20-deep chain quoted in full, chains stopping at members with reply markers,
  the post as `[0]` of the first chunk only and its 4,000 cut, a post-only
  chunk, halves keeping the post, and 300 random trees checking that every due
  item lands in exactly one chunk under the hard max.
- `tests/test_extract_v6_thread_db.py` (22): every due item once with the
  thread hash, the request on the wire, attribution, the post written in post
  mode's row shape, cost shares summing exactly; a post done in post mode
  left as context; `--scope comments`; comment-mode-done comments as context;
  bad ids dropped and logged; duplicate spellings one row; a failed chunk
  split then sent alone; items alone failing twice and parking; the cap never
  exceeded at any moment (direct) and batch holds within the cap; one request
  per chunk; re-attach after a restart with nothing resubmitted; a comment-mode
  run collecting a thread batch; a batch error split and retried in the same
  run; a twice-failed half going out alone in its own batch; pending-none
  requeueing chunks as recorded; `--reset-hash` on the thread hash leaving
  comment rows alone; `live_mentions`; the dry run writing nothing; the CLI;
  newest-first; the schema applied twice; comment mode working without
  `extract_chunks`.
- `tests/test_prompt_v6.py`: the vendored thread file pinned, equal to the
  branch's file with the listed additions, the prompt equal to round 4's
  minus `<post_item>`, the renderer equal to round 4's without the new
  arguments. `branch_file` now also tries `origin/extraction-v6`, so the
  branch comparisons run in a worktree (they were skipping).
- `eval/thread_v6/selftest.py`: offline, passes.

No paid call was made, and production was only read.
