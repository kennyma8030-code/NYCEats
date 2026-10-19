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
- **Every city polled, only r/FoodNYC's history swept by default.** Full
  history for the six other cities is ~3.5M comments, about 3.1 GB plus the
  WAL to write it, and the 5,000 MB Railway volume held 1.34 GB on
  2026-10-19. So the history sweep is opt-in (`BACKFILL_SUBREDDITS`,
  `BACKFILL_YEARS_OTHER`, below) and stops at `BACKFILL_MAX_DB_MB`. Polling
  stays on for all seven unless `POLL_SUBREDDITS` says otherwise.

## How the poller works (`poller.py`)

- Each subreddit has its own due time. The interval is
  `clamp(50 / busiest_hour_last_7d × 1h, 10 min, 60 min)`, recomputed from
  the database after every poll. In the busiest hour, one poll takes half a page.
- `fetch_new` takes the newest page and pages back (`before = oldest + 1`
  so same-second ties aren't lost) until it is `POLL_LAG_HOURS` (default 8)
  behind the newest comment the **previous poll of that city saw**. The lag
  is there because Arctic Shift publishes out of order: on r/FoodNYC a
  comment turns up as much as 8.8 hours (p99) after newer ones, and stopping
  at the previous newest lost about 1% of comments (production on
  2026-10-19: 466 of the 15,524 RSS comments older than a day are not in
  `comments`). It costs two or three pages per poll instead of one; the
  overlap is deduped. The interval affects how fresh the data is, never
  whether comments are lost. Capped at 20 pages (2,000 comments) per poll.
- A comment whose post the archive does not have yet is dropped (it cannot
  satisfy the foreign key), and its thread is remembered in memory, at most
  1,000 per city for 48 hours. Every later poll of that city asks for those
  posts again (one request per 50) and pulls the whole thread of each one
  that has appeared, which brings the dropped comments back. Posts can trail
  their comments by about 20 hours.
- The chores pass re-sweeps each polled city's last `POLL_RESWEEP_HOURS`
  (48) forward from the archive every `POLL_RESWEEP_EVERY_HOURS` (6), with
  the same tie-safe paging as the backfill. It catches what was later than
  the lag and orphans whose post came late. About 6,000 comments, ~60
  requests across the seven cities, four times a day. The log line
  `re-swept r/X's last 48h: N comment(s), M were missing` is the poll's
  loss rate; M should be near zero.
- "What the previous poll saw" is kept in memory per city, not read as
  `max(created_utc)`: pulling a newly found thread stores replies newer than
  the poll's page, and the backfill pages up to the present, so the table's
  max can run ahead of what the poll has actually covered. At boot it is
  seeded from the table; the boot backfill closes anything older.
- A sudden burst (e.g. double the week's peak) costs one extra page on the
  next poll. After that poll the peak is updated, so the interval tightens
  immediately.
- Settling scores, the re-sweep, `--extract`, the scoring refresh and the
  opt-in embed step (`POLL_EMBED`, r/FoodNYC only) run on their own
  30-minute timer, the "chores" pass. It starts by logging the database size
  (`database 1,340 MB (backfill limit 3,500 MB)`).
- Every step runs in its own try. A step that fails because the connection
  itself went (Postgres restart, dropped proxy) gets a new connection rather
  than ending the process; a failed reconnect is retried by the next step.
  `db.connect()` sets TCP keepalives so a dead connection is noticed within
  a minute. Read helpers commit, and the loop commits before it sleeps, so
  the connection is never "idle in transaction" through a sleep. The poller,
  the backfill thread and the RSS thread share one helper for this,
  `db.recover`, which never raises.
- On boot, `backfill.start_background` sweeps the cities `backfill.scope()`
  picks, in order, FoodNYC first (its gap-fill is short). By default that is
  FoodNYC alone. A failure retries the same sub after 5 min
  from its cursor; after 3 failures in a row the sub goes to the back of the
  queue with a loud `FAILED` line, so one bad city never stalls the rest. The
  thread survives a failed connect too. With `--once` the sweep runs in the
  foreground, as it did before this branch, and gives up on a sub after two
  rounds instead of hanging.
- The backfill pages forward with `after = newest - 1` and drops ids it has
  already seen (`arctic.forward`). Arctic's `after` is exclusive, so the old
  `after = newest` lost every comment from a page's last second that did not
  fit on the page. Thread pulls (`arctic.all_thread_comments`) and the
  re-sweep use the same helper.
- At the start and every 10 pages of another city's history, the sweep checks
  `pg_database_size`. Past `BACKFILL_MAX_DB_MB` (default 3,500) it stops
  that city and every other non-HOME city, loudly (`[backfill] STOPPED`),
  and keeps the cursors. r/FoodNYC's sweep is never stopped.
- New flag: `--subreddit X` (repeatable) on both `poller.py` and
  `backfill.py`. On the poller it narrows both lists.

### Settings (Railway service variables)

| Variable | Default | Meaning |
|---|---|---|
| `POLL_SUBREDDITS` | all seven | comma list or `all`; which cities are polled |
| `BACKFILL_SUBREDDITS` | `FoodNYC` | comma list or `all`; which cities the boot sweep covers |
| `BACKFILL_YEARS_OTHER` | `0` | history for a city other than r/FoodNYC: `0` = none (the city is skipped even if listed), `N` = last N years, `all` |
| `BACKFILL_MAX_DB_MB` | `3500` | stop sweeping other cities past this database size |
| `POLL_LAG_HOURS` | `8` | how far behind the last poll's newest each poll pages back |
| `POLL_RESWEEP_HOURS` / `POLL_RESWEEP_EVERY_HOURS` | `48` / `6` | the chores re-sweep |

Names are matched case-insensitively and stored in `subreddits.py`'s
spelling; an unknown name fails the boot. Once a city has a cursor, the
cursor wins over its years: to deepen a city's history later, clear its
cursor (`poller.py --rescan --subreddit X` or `backfill.py --restart`).

**What polling the six other cities adds.** 2,514 comments a day between
them (30-day rates in the table above), at ~900 bytes a comment with its
indexes (production: 657 MB for 759k), is about **2.3 MB a day, 70 MB a
month, 0.85 GB a year**, plus their posts (~0.5 KB each, negligible). To
opt into history: `BACKFILL_SUBREDDITS=all` and `BACKFILL_YEARS_OTHER=all`
(about 3.1 GB) or `=N` for the last N years; check the volume first.

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
921 MB on a 5,000 MB volume (1.34 GB used with WAL),
`max_parallel_workers_per_gather = 0` set on the database, `backfill_progress`
holding both the `posts` and `comments` rows (both are carried into
`backfill_cursors`), pgvector 0.8.6 **available but not installed**. The
deployed worker is the old code, and it was found **idle in transaction**
holding ACCESS SHARE on `comments` and `threads` (it read, then slept).

Everything is applied by `db.init` + `refresh.apply_sql` on the next poller
boot; there is no separate migration script.

### What a boot does, and what it locks

- `schema.sql` runs in one transaction with `lock_timeout = 5s`. Every ALTER
  and CREATE INDEX on `comments`, `threads` and `mentions` is checked in the
  catalog first, so **a boot of a current database takes no lock on them**
  beyond a read (tested under an EXCLUSIVE lock held by another session).
- The **first** boot needs ACCESS EXCLUSIVE on `comments` once, for
  `add column subreddit` (catalog-only), and builds three indexes under it:
  `comments_sub_created_idx`, `threads_sub_created_idx`, and the rebuilt
  `comments_unextracted_idx`. On production-shaped data that is **3.1 s**
  during which reads of `comments` wait.
- If the lock is not granted in 5 s, the whole transaction rolls back and is
  retried after 10, 30, 60 and 120 s, each retry logging who holds it
  (`holders: pid 81409 idle in transaction for 56s`). After that the boot
  fails and Railway's `ON_FAILURE` policy restarts it. While it waits, reads
  of `comments` wait at most 5 s per try.
- `refresh.apply_sql` skips any scoring file whose views already carry its
  hash (a comment on each view), so a normal boot rebuilds nothing. When a
  file changed, it and every file after it are re-run **in one
  transaction**: board reads wait for the commit instead of failing with
  `relation "entity_leaderboard_v2" does not exist`. Same lock timeout and
  retries.

Measured on a throwaway Postgres 18.6 holding production's rows (copied
read-only), from the ee72a46 schema, with a session idle in transaction on
`comments`/`threads` that lets go after 60 s:

| | main (fa26141) | this branch |
|---|---|---|
| boot 1, `db.init` | 61.3 s, blocked the whole time behind the holder; every `comments` read blocked 61 s | 117.7 s of retries; `comments` reads waited at most 5.0 s |
| boot 1, `apply_sql` | 144.3 s (`entity_longevity` alone 123 s) | 25.1 s (`entity_longevity` 1.4 s), once |
| board reads during boot 1 | blocked up to 138 s, and 19 `does not exist` errors | blocked up to 24.8 s, no errors |
| boot 2, total | 147.0 s, the same again | 0.1 s, no lock on the raw tables |
| boot 1 with no holder | — | `db.init` 3.1 s, `apply_sql` 25–40 s |
| boot 1 after the pre-step below | — | `db.init` 0.1 s, `comments` reads never waited |

### Steps, each with the owner's go-ahead

1. **Make sure the old worker is not idle in transaction.** Check:

       select pid, state, now() - xact_start as open_for, left(query, 60)
       from pg_stat_activity where datname = current_database() and state like 'idle in%';

   The old code reads and then sleeps inside the transaction, so it will
   hold its lock for minutes at a time. Either stop the old worker before
   pushing (Railway: remove the active deployment, or scale it to zero),
   or, once the new deployment is booting and its log shows
   `holders: pid N idle in transaction`, end that session with
   `select pg_terminate_backend(N);`. The new code never sits idle in a
   transaction, so this is needed once.
2. **Optional, recommended: pre-build the new indexes without blocking.**
   With the old worker stopped (CONCURRENTLY waits for every open
   transaction, including an idle one), from the backend worktree:

       psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
         -c "set lock_timeout = '5s'" \
         -c "alter table comments add column if not exists subreddit text not null default 'FoodNYC'" \
         -c "create index concurrently if not exists comments_sub_created_idx on comments(subreddit, created_utc)" \
         -c "create index concurrently if not exists threads_sub_created_idx on threads(subreddit, created_utc)" \
         -c "create index concurrently if not exists comments_unextracted_home_idx on comments(thread_id) where subreddit = 'FoodNYC' and extracted_at is null and extract_error is null" \
         -c "drop index concurrently if exists comments_unextracted_idx" \
         -c "alter index comments_unextracted_home_idx rename to comments_unextracted_idx"

   Rehearsed on the production-shaped copy: the ALTER held its lock 6 ms,
   the indexes took 1.8 s and 2.4 s without blocking anyone, and the boot
   that followed did nothing to `comments`. If a CONCURRENTLY build is
   interrupted it leaves an INVALID index; drop it
   (`drop index concurrently <name>`) and run the line again.
3. **pgvector.** The guarded block in `schema.sql` runs
   `create extension if not exists vector` and creates the three empty
   embedding tables. pgvector is not a trusted extension, so this needs a
   superuser role. Check before deploying:
   `select rolsuper from pg_roles where rolname = current_user;`
   If that is false, the block logs a notice and skips; the boot carries on
   and embedding stays off until a superuser runs `embed_schema.sql`.
4. **Deploy order.** The web service does not apply the schema, but it
   filters on `comments.subreddit`. If it starts before the worker has run
   `schema.sql`, the feed and stats return errors until the worker boots.
   Deploy the worker first and let it finish booting, or do step 2 (or
   `psql "$DATABASE_URL" -1 -f schema.sql`) first. `-1` matters: without it
   each statement is its own transaction and the file's lock timeout covers
   only itself.
5. **Scoring views.** The first boot rebuilds all three scoring files in one
   transaction (25–40 s on production-sized data, board reads wait, nothing
   errors). Every later boot skips them until a file changes.
6. **Backfill.** By default only r/FoodNYC's gap-fill runs. The other six
   cities are polled from the first boot (2.3 MB a day). Their history waits
   for the owner: see Settings above, and check the volume first.

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
nothing older is running. To go back to older code, see
[rollback.md](rollback.md): it is not a plain redeploy.

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

- **A gap past the 20-page cap** stays until the next boot's backfill, or
  the next re-sweep if it is younger than 48 hours. Only reachable at ~40×
  Chicago's current peak. A gap from before a boot is the backfill's too:
  the first poll after a boot starts from the table's newest, having no
  memory of its own yet. For a city not in `BACKFILL_SUBREDDITS`, downtime
  longer than 48 hours leaves a gap nothing closes, unless the city is
  added to the sweep (with `BACKFILL_YEARS_OTHER` set to cover it).
- **Orphan threads are remembered in memory.** A restart forgets them; the
  re-sweep and r/FoodNYC's boot gap-fill pick them up again if the post has
  appeared by then.
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
