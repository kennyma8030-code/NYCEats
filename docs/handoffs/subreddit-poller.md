# Handoff: multi-city subreddit poller

Built on branch `worktree-subreddit-poller`, then integrated with the
embedding pipeline on `integrate-embed-poller` (on top of `main` at
`ee72a46`). Nothing has been run against Railway: no schema change, no
poller, no backfill, no extraction. The SQL has been run against a
throwaway local Postgres 18 with pgvector 0.8.6 (see Testing).

## Goal

Collect the seven largest city food subreddits, each polled as often as its
own activity needs, with full history. Keep the NYC board exactly as it is:
the other cities are stored, not extracted or scored.

| Subreddit | Subscribers | Comments/day (30d) | Busiest hour (30d) | Poll interval at that peak |
|---|---|---|---|---|
| r/FoodLosAngeles | 279,808 | 438 | 142 | ~21 min |
| r/FoodNYC | 203,317 | 554 | 118 | ~25 min |
| r/FoodSanDiego | 166,430 | 166 | 74 | ~40 min |
| r/austinfood | 159,103 | 511 | not measured | — |
| r/chicagofood | 128,591 | 613 | 211 | ~14 min |
| r/denverfood | 71,895 | 347 | 101 | ~30 min |
| r/FoodToronto | 68,789 | 439 | 190 | ~16 min |

Subscriber counts are from Arctic Shift's saved copy of each subreddit's
details, measured 2026-10-18. The activity numbers come from Arctic Shift's
daily and hourly aggregate endpoint.

## Decisions

- **One set of tables, `subreddit` as the partition column.** Not a table
  per city: that would mean seven copies of `scoring.sql` and every
  migration. Reddit ids are globally unique, so the raw tables cannot
  collide. Every reader filters on `subreddit` first.
- **`subreddit`, not `city`.** The subreddit is a fact about a comment; the
  city is a conclusion drawn from it (SF could have two subs). A mapping to
  city belongs with multi-city scoring, which this branch does not build.
- **Only `subreddits.HOME` (r/FoodNYC) is extracted.** Other cities have no
  restaurant list to resolve names against. Because extraction is the only
  writer of `mentions`, `mentions` stays NYC-only by construction.
- **Full history for every city**, swept in a background thread so polling
  never waits behind it.

## How the poller works (`poller.py`)

- Each subreddit has its own due time. The interval is
  `clamp(50 / busiest_hour_last_7d × 1h, 10 min, 60 min)`, recomputed from
  the database after every poll. In the busiest hour, one poll takes half a page.
- `fetch_new` takes the newest page and, if its oldest comment is still
  newer than what the **previous poll of that city saw**, pages back
  (`before = oldest + 1` so same-second ties aren't lost) until it overlaps.
  The interval affects how fresh the data is, never whether comments are
  lost. Capped at 20 pages (2,000 comments) per poll.
- "What the previous poll saw" is kept in memory per city, not read as
  `max(created_utc)`: pulling a newly found thread stores replies newer than
  the poll's page, and the backfill pages up to the present, so the table's
  max can run ahead of what the poll has actually covered. At boot it is
  seeded from the table; the boot backfill closes anything older.
- A sudden burst (e.g. double the week's peak) costs one extra page on the
  next poll. After that poll the peak is updated, so the interval tightens
  immediately.
- Settling scores, `--extract`, the scoring refresh and the opt-in embed
  step (`POLL_EMBED`, r/FoodNYC only) run on their own 30-minute timer, the
  "chores" pass.
- Every step runs in its own try. A step that fails because the connection
  itself went (Postgres restart, dropped proxy) gets a new connection rather
  than ending the process; a failed reconnect is retried by the next step.
  `db.connect()` sets TCP keepalives so a dead connection is noticed within
  a minute. Read helpers commit, and the loop commits before it sleeps, so
  the connection is never "idle in transaction" through a sleep.
- On boot, `backfill.start_background` sweeps every sub in order, FoodNYC
  first (its gap-fill is short). A failure retries the same sub after 5 min
  from its cursor; after 3 failures in a row the sub goes to the back of the
  queue with a loud `FAILED` line, so one bad city never stalls the rest. The
  thread survives a failed connect too. With `--once` the sweep runs in the
  foreground, as it did before this branch, and gives up on a sub after two
  rounds instead of hanging.
- New flag: `--subreddit X` (repeatable) on both `poller.py` and
  `backfill.py`.

## Files changed

| File | Change |
|---|---|
| `subreddits.py` (new) | `HOME` and the seven `SUBREDDITS`, spelled as Arctic Shift returns them |
| `schema.sql` | `comments.subreddit` (default `'FoodNYC'`), indexes on `(subreddit, created_utc)` for comments and threads, new `backfill_cursors` table seeded from `backfill_progress`, `comments_unextracted_idx` limited to HOME |
| `db.py` | `insert_comments` stores `subreddit`; both inserts sort by id (consistent lock order, so the poller and backfill threads can't deadlock); cursors keyed per subreddit; `clear_cursors`, `newest_stored_utc`, `busiest_hour` |
| `arctic.py` | `newest_comments(..., before=)` |
| `poller.py` | per-subreddit timing, paging back to stored comments, background backfill |
| `backfill.py` | takes a subreddit throughout; `run_all`, `start_background`; stale-tree scan scoped per sub |
| `extract.py`, `extract_threads.py`, `seed_mentions.py` | candidate queries filter `subreddit = HOME` |
| `scoring.sql` | `scoring_params.subreddit = 'FoodNYC'`; `mention_weights`, the volume denominator and `momentum_windows` filter on it |
| `app/queries.py`, `api.py` | live feed, stats and extraction progress filter on `HOME` |
| `SPEC.md` | ingestion section updated |

SQL cannot import Python, so `'FoodNYC'` is spelled out beside
`subreddits.HOME`: `scoring_params.subreddit` in `scoring.sql`, and in
`schema.sql` the column default, the cursor seed and the
`comments_unextracted_idx` predicate. Change all of them or none;
`tests/test_home_literal.py` fails if they disagree.

## Applying it (orchestrator)

Production as checked read-only on 2026-10-19: PostgreSQL 18.6, database
922 MB, `backfill_progress` holds both the `posts` and `comments` rows (both
are carried into `backfill_cursors`), pgvector 0.8.6 **available but not
installed**.

Everything is applied by `db.init` + `refresh.apply_sql` on the next poller
boot; there is no separate migration script. What that boot does:

1. **Schema.** `alter table comments add column ... default 'FoodNYC'` is
   metadata-only. The two new `create index` statements, and the one-time
   rebuild of `comments_unextracted_idx` with its new `subreddit = 'FoodNYC'`
   predicate, are not concurrent and briefly block writes on `comments` and
   `threads` while they build. Later boots find the new definition and skip it.
2. **pgvector.** The guarded block in `schema.sql` runs
   `create extension if not exists vector` and creates the three empty
   embedding tables. pgvector is not a trusted extension, so this needs a
   superuser role. Check before deploying:
   `select rolsuper from pg_roles where rolname = current_user;`
   If that is false, the block logs a notice and skips; the boot carries on
   and embedding stays off until a superuser runs `embed_schema.sql`.
3. **Scoring views.** `scoring.sql` adds a column to the end of
   `scoring_params` and rebuilds the views that depend on it; they are
   populated as they are created.
4. **Backfill starts on its own**: roughly 3.5M comments across the six new
   subs, many hours of Arctic Shift requests. **Check the Railway volume has
   room.** 922 MB holds ~750k comments and ~47k posts with their indexes,
   about 1.2 KB a comment, so 3.5M more is roughly 4–4.5 GB. The embeddings,
   if run, add about 0.3 GB of vectors plus a similar amount for the HNSW
   indexes. No inference cost: extraction and embedding never read those
   comments.

**Deploy order.** The web service does not apply the schema, but it now
filters on `comments.subreddit`. If it starts before the worker has run
`schema.sql`, the feed and stats return errors until the worker boots.
Either deploy the worker first and let it finish booting, or apply the
schema by hand first (`psql "$DATABASE_URL" -f schema.sql`, which is
idempotent), then deploy.

**After the first boot, check the spellings.** `subreddits.py` spells each
name the way Arctic Shift returns it, and the stored `subreddit` comes from
Arctic's response, while every filter uses our spelling. A mismatch (say
`AustinFood` stored, `austinfood` queried) would make that city look empty
forever: every poll pages back the full 20 pages and the interval never
adapts. Once each city has a few polls in:

    select subreddit, count(*), max(created_utc) from comments group by 1 order by 1;

should list exactly the seven names in `subreddits.SUBREDDITS`, nothing else.

Older code sharing the database keeps working. Its comment inserts get the
`'FoodNYC'` default, which is correct for it, and it still writes to
`backfill_progress`, which this branch leaves in place. Drop that table once
nothing older is running.

## Testing

`python -m pytest tests`. The database tests need
`TEST_DATABASE_URL` pointing at a throwaway local Postgres (pgvector for the
embedding ones); without it they skip, and the run says so at the end.

- In memory, Arctic Shift and Postgres faked (`test_poller_polls.py`,
  `test_backfill_runall.py`, `test_home_literal.py`): paging back across
  4 pages with none of 320 newer comments missed, with same-second ties at
  every page boundary; the 20-page cap; interval maths and clamps; the
  per-city overlap point (seeded once, not moved by other writers, not moved
  by a failed insert); a lost connection replaced in `_step` and carried
  through `poll_due`; `run_all` retrying, moving a failing city to the back,
  and `--once` giving up; the backfill thread surviving a failed connect; the
  cursor moving past a page whose posts are all missing; every `'FoodNYC'`
  literal in the SQL equal to `subreddits.HOME`.
- Against Postgres 18 (`test_multicity_db.py`): `insert_comments` columns
  line up; `backfill_cursors` seeded from `backfill_progress` once and never
  over a newer cursor; `clear_cursors`; the unextracted index rebuilt once
  from the old definition and used by the extraction query; scoring
  (`mention_weights`, `entity_volume`, `momentum_windows`) unchanged by 200
  Chicago comments and a Chicago mention; feed and stats NYC-only;
  extraction candidates NYC-only; no read helper, poll, chores pass or the
  main loop's sleep leaves the connection in a transaction; a terminated
  backend is replaced and the next city still stored.
- Not tested: query plans at production size, and the real Arctic Shift
  responses for the six new names (see the spelling check above).

## Known limits and follow-ups

- **A gap past the 20-page cap** stays until the next boot's backfill. Only
  reachable at ~40× Chicago's current peak. Fix if wanted: have the
  background thread run a catch-up sweep whenever a poll hits the cap.
  A gap from before a boot is the backfill's too: the first poll after a
  boot starts from the table's newest, having no memory of its own yet.
- **Mention-based views** (`entity_alias`, `entity_longevity`,
  `entity_confidence`, `resolve.sql`) are NYC-only only because extraction
  is. Before scoring a second city, entity keys need to become
  `(city, entity_key)` and `restaurants.name_key` stops being globally unique.
- **The RSS fallback is still FoodNYC only.** That's deliberate: seven Reddit
  feeds every 5 min invites 429s.
- **The boot sweep is serial.** All of Toronto's history waits behind all of
  Chicago's. Fine for a one-off; parallelising it would put more load on
  Arctic Shift.
- **Austin's busiest hour was not measured** (the aggregate endpoint kept
  timing out). Its interval comes from the database once data is in, like
  every other sub's.
