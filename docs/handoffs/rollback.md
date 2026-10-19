# Runbook: rolling the worker back

Going back to older code is not a plain "redeploy the previous deployment".
Each boot of the worker re-applies its own `schema.sql` and scoring files
to the shared database, and older files do not fit what newer ones left
there. Everything below was rehearsed on a throwaway Postgres 18.6 holding a
read-only copy of production's rows. Every step writes to production, so
each one needs the owner's go-ahead. Run them from
`.claude/worktrees/backend`, whose `.env` holds `DATABASE_URL`.

Railway builds from `origin/main`, and "redeploy" of an old deployment
reuses its old build. A rollback that needs a patched file (below) has to be
a commit on `main` (a revert plus the patch), not a redeploy.

## First, what is in the database

    select subreddit, count(*) from comments group by 1 order by 1;      -- other cities?
    select count(*) from mentions where schema_version = 6;                -- v6 rows?
    select read_version from extraction_settings;                          -- what the board reads

| Target | Fine when | Needs |
|---|---|---|
| `fa26141` (main before the deploy-safety fixes) | always | a start command that keeps the six-city history off |
| `ee72a46` (before multi-city and v6) | no other city's comments and no v6 rows | the `scoring_params` fix below |
| `ee72a46` with v6 rows | no other city's comments | a patched commit, the fix, an index |
| `ee72a46` with other cities' comments | never | use `fa26141` |

## Back to fa26141

- **Start command.** fa26141 has no `BACKFILL_SUBREDDITS` or
  `BACKFILL_YEARS_OTHER`: plain `python poller.py` there polls all seven
  cities **and sweeps all seven full histories**, ~3.1 GB on a 5 GB volume.
  Set the Railway start command to `python poller.py --subreddit FoodNYC`
  (r/FoodNYC only, polled and gap-filled), or `python poller.py --no-backfill`
  (all seven polled, nothing swept, no gap-fill after downtime).
- **Every boot of it** drops and rebuilds every scoring view, file by file
  (about 140 s on production-sized data; for part of it the board answers
  `relation "entity_leaderboard_v2" does not exist`). Its `schema.sql`
  takes ACCESS EXCLUSIVE on `comments` with no lock timeout, so nothing may
  be idle in transaction when it boots. The newer code never is.
- Nothing else. Its boots drop the hash comments on the scoring views, so
  the first boot after rolling forward again rebuilds them once (25–53 s,
  with the web app's 503s for most of it; see subreddit-poller.md, step 5).

## Back to ee72a46

### 1. Its boot crash-loops on `scoring_params`

`scoring_params` now ends with a `subreddit` column, and ee72a46's
`scoring.sql` replaces it without one: `ERROR: cannot drop columns from
view`, every boot. Drop it and rebuild the scoring layer from ee72a46's
files, in one transaction, before its first boot:

    mkdir -p /tmp/rb
    for f in scoring.sql scoring_v2.sql resolve.sql; do git show ee72a46:$f > /tmp/rb/$f; done
    # (step 2: if v6 rows exist, patch the three files here)
    psql "$DATABASE_URL" -1 -v ON_ERROR_STOP=1 \
      -c "set local lock_timeout = '5s'" \
      -c 'drop view scoring_params cascade' \
      -f /tmp/rb/scoring.sql -f /tmp/rb/scoring_v2.sql -f /tmp/rb/resolve.sql

The cascade takes every scoring view and materialized view with it, and the
three files put them back. `-1` keeps that one transaction: board reads wait
(measured 137 s) instead of seeing a missing view, though past the web app's
10 s statement timeout they answer 503, and an error rolls all of it back. After
this, ee72a46's own boots apply its files cleanly.

### 2. If v6 rows exist: exclude them, permanently

ee72a46 reads `mentions` directly (`live_mentions` came later), so it would
count every v6 row beside the legacy row for the same comment. A one-off
psql run does not fix that: ee72a46 re-applies its own `scoring.sql` and
`resolve.sql` on every boot. Rehearsed: after the step-1 fix with patched
files the board counted 0 of 500 v6 rows; one plain ee72a46 boot later it
counted all 500. So the rollback commit has to carry the patch:

    git checkout -b rollback-ee72a46 ee72a46        # in a scratch worktree
    sed -i '' \
      -e 's/from mentions m$/from (select * from mentions where schema_version is null) m/' \
      -e 's/from mentions)/from mentions where schema_version is null)/' \
      scoring.sql resolve.sql
    grep -c 'schema_version is null' scoring.sql resolve.sql   # 5 and 1

That covers all six reads (`entity_alias`, `mention_weights`, both halves
of `entity_longevity`, `entity_confidence`, `mention_resolution`). Use the
same patched files in step 1. Then land it on `main` (owner), and deploy.
`read_version` does not matter to ee72a46: it never reads it.

The **web app at ee72a46** also reads `mentions` directly (detail pages,
search, stats), so it would show v6 rows twice. Once v6 rows exist, keep
the web service on fa26141 or later.

Nothing is deleted. v6 rows stay in `mentions`, `extraction_state` and
`extract_batches` keep their state, and rolling forward picks them up.

### 3. The old extractor and the HOME-only index

`comments_unextracted_idx` now carries `subreddit = 'FoodNYC'` in its
predicate. ee72a46's candidate query does not say that, so Postgres cannot
use the index and walks `comments_thread_idx` across the whole table for
every batch. ee72a46's `schema.sql` keeps the index as it is (same name,
`if not exists`). If ee72a46 will extract (`POLL_EXTRACT=1`), give it an
index it can use, without blocking writes:

    psql "$DATABASE_URL" -c "create index concurrently if not exists comments_unextracted_legacy_idx on comments(thread_id) where extracted_at is null and extract_error is null"

Rehearsed: its candidate query then reads that index. When rolling forward
again, drop it:

    psql "$DATABASE_URL" -c "drop index concurrently if exists comments_unextracted_legacy_idx"

### 4. Why not with other cities' comments

ee72a46 has no subreddit filter anywhere. Its volume and momentum
denominators would count every city's comments, so r/FoodNYC's volume share
and momentum would shrink. Its extractor would treat every other city's
unextracted comment as a candidate, pay to extract it, and put those
mentions on the board. Roll back to fa26141 instead.

### 5. What else to expect from ee72a46

- Its `backfill.py` resumes from `backfill_progress`, which newer code no
  longer updates (it writes `backfill_cursors`). Its first boot re-sweeps
  r/FoodNYC from that older cursor. Every insert is `on conflict do
  nothing`, so this costs requests, not data.
- Its comment inserts get `subreddit = 'FoodNYC'` from the column default,
  which is right for it.
- Every boot takes ACCESS EXCLUSIVE on `comments` (`add column if not
  exists`) with no timeout, and rebuilds the scoring views in about 140 s.

## Rolling forward again

Nothing to do by hand except dropping `comments_unextracted_legacy_idx` if
it was made. The first boot finds the scoring views without their hash
comments and rebuilds all three files in one transaction (25–53 s, reads
wait). `schema.sql` finds the columns and indexes in place and locks nothing.
