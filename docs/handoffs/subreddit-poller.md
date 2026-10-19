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
  `comments`). It costs more pages per poll: two or three for r/FoodNYC,
  up to ~8 for r/chicagofood in its busiest hours (8 h at ~100 comments an
  hour), where one used to do. The overlap is deduped. The interval affects how fresh the data is, never
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
  the lag and orphans whose post came late. It never reaches back before the
  oldest comment held for the city, so a newly polled city is re-read only
  from its first poll, and it fetches a new thread's post but not the rest
  of the thread (the sweep reads its own window whole). About 6,000
  comments, ~60 requests across the seven cities, four times a day; the
  first one waits one interval after boot. The log line
  `re-swept r/X since <time>: N comment(s), M were missing` is the poll's
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
- The board is refreshed after a pass that extracted something, and
  otherwise at least every `POLL_REFRESH_HOURS` (6). Boots no longer rebuild
  it every time (see below), so a boot that did not rebuild the scoring
  views refreshes them in its first chores pass, which picks up a replaced
  `live_mentions` or anything else `schema.sql` changed. Edits to
  `alias_overrides` or `excluded_entities` reach the board within six
  hours; for sooner, run `python refresh.py` from the backend worktree.
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
| `POLL_REFRESH_HOURS` | `6` | refresh the board at least this often, extraction or not |

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
  `add column subreddit` (catalog-only), and builds under it
  `comments_sub_created_idx`, `threads_sub_created_idx`, the rebuilt
  `comments_unextracted_idx` and v6's `comments_first_seen_idx`; it also
  alters `mentions` for v6 and builds `mentions_post_unique_idx` and, with
  pgvector, `mentions_created_idx`. All of that holds until the file
  commits: **2.6 s** of `db.init` on production-shaped data, during which
  reads of `comments` wait (worst measured 2.5 s). Step 2 below takes it to
  nothing.
- If a lock is not granted in 5 s, the whole transaction rolls back and is
  retried after 10, 30, 60 and 120 s, each retry logging the oldest open
  transactions (`holders: pid 81409 idle in transaction for 56s`). After
  that the boot fails and Railway's `ON_FAILURE` policy restarts it. While
  an attempt waits for its lock, new reads of `comments` queue behind it,
  for up to those 5 s (worst measured 4.85 s); between attempts nothing
  waits; the attempt that gets the lock holds it to the end of `db.init`
  (the 2.6 s above). A lock timeout inside the embedding block now reaches
  this retry too instead of quietly skipping the embedding tables.
- `refresh.apply_sql` skips any scoring file whose views already carry its
  hash (a comment on each view), so a normal boot rebuilds nothing. When a
  file changed, it and every file after it are re-run **in one
  transaction**, so no reader ever sees `relation "entity_leaderboard_v2"
  does not exist`. Readers wait for the commit instead, and that wait is
  long: **25–53 s** on production-sized data, the first time. The web app
  cancels a statement after `DB_STATEMENT_TIMEOUT_MS` (10 s, lock waits
  included), so for most of that minute board requests answer **503** with
  Retry-After rather than waiting. Same lock timeout and retries.

Measured on a throwaway Postgres 18.6 holding production's rows (copied
read-only, since deleted), from the ee72a46 schema, with a session idle in
transaction on `comments`/`threads` that lets go after 60 s. "This branch"
is the branch merged with main at 13a4176 (v6, embedding and app fixes):

| | main (fa26141) | this branch |
|---|---|---|
| boot 1, `db.init` | 61.3 s, blocked the whole time behind the holder; every `comments` read blocked 61 s | 117.8 s of retries; `comments` reads waited at most 4.85 s |
| boot 1, `apply_sql` | 144.3 s (`entity_longevity` alone 123 s) | 33.7 s (`entity_longevity` 1.4 s), once |
| board reads during boot 1 | blocked up to 138 s, and 19 `does not exist` errors | waited up to 33.5 s, no errors (past 10 s the app answers 503) |
| boot 2, total | 147.0 s, the same again | 0.1 s, no lock on the raw tables |
| boot 1 with no holder | — | `db.init` 2.6 s, `apply_sql` 25–53 s across runs |
| boot 1 after the pre-steps below | — | `db.init` 0.0 s, `comments` reads never waited (0.01 s) |

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
2. **Recommended: do the first boot's DDL by hand, without blocking.** With
   the old worker stopped (CONCURRENTLY waits for every open transaction,
   an idle one included), from the backend worktree, in this order:

       psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
         -c "set lock_timeout = '5s'" \
         -c "alter table comments add column if not exists subreddit text not null default 'FoodNYC'" \
         -c "alter table mentions add column if not exists thread_id text references threads(id)" \
         -c "create index concurrently if not exists comments_sub_created_idx on comments(subreddit, created_utc)" \
         -c "create index concurrently if not exists threads_sub_created_idx on threads(subreddit, created_utc)" \
         -c "create index concurrently if not exists comments_unextracted_home_idx on comments(thread_id) where subreddit = 'FoodNYC' and extracted_at is null and extract_error is null" \
         -c "drop index concurrently if exists comments_unextracted_idx" \
         -c "alter index comments_unextracted_home_idx rename to comments_unextracted_idx" \
         -c "create index concurrently if not exists comments_first_seen_idx on comments(first_seen_at)" \
         -c "create index concurrently if not exists mentions_created_idx on mentions (created_at)" \
         -c "create unique index concurrently if not exists mentions_post_unique_idx on mentions(thread_id, entity_key, prompt_hash) where comment_id is null"
       psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f extract_v6_schema.sql

   `thread_id` is added first, alone, with the same definition
   `extract_v6_schema.sql` uses, because the post index cannot be built
   before its column exists; the migration then adds the other v6 columns
   and skips `thread_id`. Each definition here is the one `schema.sql`
   would build, which checks only the name. Measured on the
   production-shaped copy:

   | Statement | Time | Lock |
   |---|---|---|
   | add `comments.subreddit` | 9 ms | ACCESS EXCLUSIVE on comments, for those 9 ms |
   | add `mentions.thread_id` + FK | 1 ms | ACCESS EXCLUSIVE on mentions, SHARE ROW EXCLUSIVE on threads |
   | `comments_sub_created_idx` | 1.35 s | none that blocks reads or writes |
   | `threads_sub_created_idx` | 0.03 s | " |
   | `comments_unextracted_home_idx` | 2.15 s | " |
   | drop old `comments_unextracted_idx`, rename | 3 ms | brief |
   | `comments_first_seen_idx` | 0.71 s | none that blocks reads or writes |
   | `mentions_created_idx` | 0.06 s | " |
   | `mentions_post_unique_idx` | 0.01 s | " |
   | `extract_v6_schema.sql` | longest statement 12 ms (its column ALTER on mentions) | ACCESS EXCLUSIVE on mentions, for that statement |

   The boot that followed changed nothing in `schema.sql` (0.0 s) and no
   read of `comments` waited. If a CONCURRENTLY build is interrupted it
   leaves an INVALID index under its name, which the boot's name check
   would then accept: drop it (`drop index concurrently <name>`) and run
   that line again. `mentions_created_idx` is harmless without pgvector.
3. **pgvector.** The guarded block in `schema.sql` runs
   `create extension if not exists vector` and creates the three empty
   embedding tables. pgvector is not a trusted extension, so this needs a
   superuser role. Check before deploying:
   `select rolsuper from pg_roles where rolname = current_user;`
   If that is false, the block logs a notice and skips; the boot carries on
   and embedding stays off until a superuser runs `embed_schema.sql`.
4. **Deploy order.** The web service does not apply the schema, but it
   filters on `comments.subreddit` and reads `live_mentions`. If it starts
   before step 2 or the worker's first boot, the feed and stats return
   errors until then. Do step 2, or deploy the worker first and let it
   finish booting. Applying `schema.sql` by hand needs
   `psql "$DATABASE_URL" -1 -f schema.sql`: without `-1` each statement is
   its own transaction and the file's lock timeout covers only itself.
5. **Scoring views: about a minute of 503s.** The first boot rebuilds all
   three scoring files in one transaction, 25–53 s on production-sized
   data. Board reads queue for it and the web app gives up after its 10 s
   statement timeout, so expect 503s (with Retry-After) for most of that
   time; nothing errors with a missing view. To have them wait instead,
   set `DB_STATEMENT_TIMEOUT_MS=90000` on the web service before the worker
   deploys and remove it once the worker logs
   `committed 3 scoring file(s)`. Waiting requests hold pool connections, so
   under traffic some still get the pool's 503. Do it at a quiet hour
   either way. Later boots skip the rebuild until a scoring file changes.
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
