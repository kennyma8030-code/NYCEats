# Handoff: multi-city subreddit poller

Branch `worktree-subreddit-poller`, on top of `main` at `ee72a46`. Nothing on
this branch has been run against the local database or Railway — no schema
change, no poller, no backfill, no extraction.

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
  newer than anything stored for that sub, pages back (`before = oldest + 1`
  so same-second ties aren't lost) until it overlaps. The interval affects
  how fresh the data is, never whether comments are lost. Capped at 20 pages (2,000
  comments) per poll.
- A sudden burst (e.g. double the week's peak) costs one extra page on the
  next poll. After that poll the peak is updated, so the interval tightens
  immediately.
- Settling scores and `--extract` run on their own 30-minute timer.
- On boot, `backfill.start_background` sweeps every sub in order, FoodNYC
  first (its gap-fill is short). A failed sweep retries the same sub after 5
  min from its cursor. With `--once` the sweep runs in the foreground, as it
  did before this branch.
- New flag: `--subreddit X` (repeatable) on both `poller.py` and
  `backfill.py`.

## Files changed

| File | Change |
|---|---|
| `subreddits.py` (new) | `HOME` and the seven `SUBREDDITS`, spelled as Arctic Shift returns them |
| `schema.sql` | `comments.subreddit` (default `'FoodNYC'`), indexes on `(subreddit, created_utc)` for comments and threads, new `backfill_cursors` table seeded from `backfill_progress` |
| `db.py` | `insert_comments` stores `subreddit`; both inserts sort by id (consistent lock order, so the poller and backfill threads can't deadlock); cursors keyed per subreddit; `clear_cursors`, `newest_stored_utc`, `busiest_hour` |
| `arctic.py` | `newest_comments(..., before=)` |
| `poller.py` | per-subreddit timing, paging back to stored comments, background backfill |
| `backfill.py` | takes a subreddit throughout; `run_all`, `start_background`; stale-tree scan scoped per sub |
| `extract.py`, `extract_threads.py`, `seed_mentions.py` | candidate queries filter `subreddit = HOME` |
| `scoring.sql` | `scoring_params.subreddit = 'FoodNYC'`; `mention_weights`, the volume denominator and `momentum_windows` filter on it |
| `app/queries.py`, `api.py` | live feed, stats and extraction progress filter on `HOME` |
| `SPEC.md` | ingestion section updated |

`scoring.sql` cannot import Python, so `'FoodNYC'` is in two places:
`subreddits.HOME` and `scoring_params.subreddit`. Change both or neither.

## Applying it (orchestrator)

Everything is applied by `db.init` + `refresh.apply_sql` on the next poller
boot; there is no separate migration script.

1. **Schema.** `alter table comments add column ... default 'FoodNYC'` is
   metadata-only. The two `create index` statements are not concurrent and
   briefly block writes on `comments` and `threads` while they build.
2. **Scoring views.** `scoring.sql` adds a column to the end of
   `scoring_params` and rebuilds the views that depend on it; then refresh
   the materialized views.
3. **Backfill starts on its own** at boot: roughly 3.5M comments across the
   six new subs, many hours of Arctic Shift requests. **Check the Railway
   volume has room** — that is about 5× the current corpus. No inference
   cost: extraction never reads those comments.

Older code sharing the database keeps working. Its comment inserts get the
`'FoodNYC'` default, which is correct for it, and it still writes to
`backfill_progress`, which this branch leaves in place. Drop that table once
nothing older is running.

## Testing

- Every module compiles; `poller.py --help` parses.
- In-memory tests with Arctic Shift and Postgres faked (no network, no
  database):
  - paging back across 4 pages with 0 of 320 newer comments missed,
    including same-second ties at page boundaries;
  - the 20-page cap;
  - interval maths at several peaks;
  - `insert_comments` columns, placeholders and values lining up;
  - `run_all` retrying a failing sub, then continuing in order.
- **Not tested:** none of the SQL has been run against Postgres. Things worth
  checking first: the `scoring_params` replace, the `backfill_cursors` seed,
  and the feed query's plan with the new `subreddit` filter.

## Known limits and follow-ups

- **A gap past the 20-page cap** stays until the next boot's backfill. Only
  reachable at ~40× Chicago's current peak. Fix if wanted: have the
  background thread run a catch-up sweep whenever a poll hits the cap.
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
