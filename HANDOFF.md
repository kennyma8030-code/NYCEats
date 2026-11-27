# Hand-off: fix the review findings on `integrate-current`

This branch is `main` plus three merged features: search by meaning
(`app/search.py`, `app/parse.py`, `app/routers/search.py`, the search
components in `frontend/src`), place labels (`place_labels.py`, `schema.sql`,
`scoring.sql`) and dish merging (`app/dishes.py`, `app/data/dish_groups_*.json`).
A code review of the combined branch found the problems below. Fix them here,
so the branch can be merged to `main`.

Read `CLAUDE.md` first. You are a Worker: stay on this branch, do not touch
`main`, do not merge, and do not run any pipeline script or schema change.
You have no database and do not need one. Delete this file in your last commit.

## Fix

1. **Text search outside New York is lost** (`app/search.py` ~615, `Search.tsx`,
   `Home.tsx`, `Leaderboard.tsx`). The search box used to call `go({ topic })`,
   and the ledger's text match worked in every city. It now goes to
   `/api/search`, whose `_semantic` returns None unless the city is
   `subreddits.HOME`, so Austin, Chicago and Los Angeles get the unfiltered
   board with "Matching by meaning is not available right now". Where meaning
   search is not available for a city, fall back to the `topic` text match so
   the typed words still filter the list.
2. **Stuck skeleton rows after opening a search result**
   (`frontend/src/components/city/Leaderboard.tsx` ~222, `App.tsx`). `go({ place })`
   keeps `q`, so `useRanking(route, inCity && !route.q)` is disabled while the
   compact list still renders it: eight `row-skel` rows that never resolve, an
   eyebrow naming a sort that is not in effect, and no list pins. The compact
   list beside an open place must show the search results it came from, or a
   loaded ranking, never placeholders.
3. **Negations rank what the reader ruled out** (`app/search.py` ~547). A
   fast-mode or fallback query with unexplained words embeds the whole raw
   text, so "not italian" lists Italian places first, against the comment at
   that line. When the query was not understood (no key, rate limit, timeout,
   `ParseFailed`), do not present a meaning-ranked list as the answer without
   saying so; at the least, tell the reader the query was matched as plain
   text.
4. **A slow vector query fails the whole search** (`app/search.py` ~629).
   `_semantic` falls back to the board only for `_NO_VECTORS` errors. A
   statement timeout (`QueryCanceled`) or other psycopg2 error on the vector
   query should degrade the same way, not surface as a 503.
5. **Vocabulary build under one global lock** (`app/search.py` ~299). The first
   build for a city runs several full scans inside `_vocab_lock`, blocking
   every other city, and a failed build is not remembered, so queued requests
   retry it one after another. Use the shape `app/rankcache.py` already has:
   one computation per key whose result or failure every waiter receives, a
   bounded wait, and no global lock held while a query runs.
6. **A search runs twice and logs twice** (`app/search.py` ~724). A query with
   unexplained words is retrieved in fast mode and again in full mode, with two
   `search_log` rows and two embedding calls. Log one row per search the reader
   made, and do not repeat retrieval or embedding that the second pass can
   reuse.
7. **`people` does not click through** (`app/search.py` ~644,
   `SearchResults.tsx`). The project rule is that every score clicks through to
   its comments. A result ranked with `people = 14` returns at most three
   mention ids. Make the count reachable: either the row opens the comments it
   counts, or the number shown is the number of comments the reader can open.
   Keep permalinks suppressed where `was_deleted_later` is set.
8. **Dish names both grouped and dropped** (`app/dishes.py` ~176, the
   `dish_groups_*.json` files). `top()` tests the drop list first, so a name in
   both a group and the same place's `drop` vanishes. Four shipped entries have
   the conflict: "from lucie" → "cooky" (FoodNYC), "thorough bread"
   (austinfood), "portillos" → "salad" (chicagofood), "connie teds" → "chowder"
   (FoodLosAngeles). Fix the four entries by reading what the group means, and
   make `_place` reject the conflict so the loader's validation catches the
   next one.
9. **`place_labels.neighborhood` is never read** (`scoring.sql` ~90). The table
   holds a neighbourhood for 8,909 places and the `places` view joins only
   `cuisine`. Do not change `scoring.sql` for this. Say in the report where the
   neighbourhood would have to be read for the other cities' boards to show it,
   and what that change would cost, so it can be decided separately.

## Leave alone, but note in the report

- `scoring.sql` now depends on the `place_labels` table and its changed text
  triggers a full scoring rebuild on the next poller boot. That is a deploy
  decision, not a code fix.
- Search needs keys and a vector index on the web service that a push does not
  create. List exactly which environment variables and which index the code
  reads, with file and line.

## Done means

- `python -m pytest -q` passes with no database configured, `npx tsc --noEmit -p .`
  is clean and `npm test` passes in `frontend/`. Add tests for what you change.
  `tests/test_app_search.py` needs `TEST_DATABASE_URL`; if you can bring up a
  throwaway local Postgres run it, otherwise say it was skipped.
- Work committed on this branch and pushed, in commits whose messages are one
  plain sentence saying what changed and why it matters.
- A report per item: fixed, or not fixed and why, plus anything you were
  unsure about.
