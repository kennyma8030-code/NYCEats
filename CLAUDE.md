# NYCEats

Ranks NYC restaurants by how r/FoodNYC talks about them. `SPEC.md` is the
source of truth for the algorithm; read it before touching ingestion,
extraction or scoring.

## Roles

There are two kinds of session here. Know which one you are.

- **Orchestrator** — the session started in the repo root (`/Users/kenny/NYCEats`)
  on `main`. It talks to the user, delegates features, reviews, and merges.
- **Worker** — a background agent or session running in a worktree under
  `.claude/worktrees/`. It builds one feature on its own branch and reports back.

## Orchestrator

When the user says "build X in a worktree" (or similar), that is standing
permission to spawn a background agent with `isolation: "worktree"`. Do not
build the feature yourself.

- **Brief the worker fully.** A fresh agent starts cold. Give it the goal, the
  files that matter, the relevant `SPEC.md` sections, and what "done" means.
  Use a fork instead only when the design was worked out in this conversation
  and re-explaining it would lose something.
- **Match the model to the task.** Pipeline, scoring, identity, extraction
  prompts and schema changes (`scoring.sql`, `resolve.sql`, `schema.sql`,
  `extract*.py`, `prompt*.py`) get the strongest model. Frontend, endpoints,
  plumbing and docs can use a lighter one.
- **Stay lean.** Delegate code exploration rather than reading large files
  yourself; this session has to last across many features.
- **Review before merge.** When a worker finishes, run `/code-review` on its
  branch, then summarize the result for the user.
- **Never merge to `main` or push without the user's go-ahead.** Prefer
  `--ff-only` when the branch is already on top of `main`.
- Keep a short running list of what is in flight: feature, branch, status.

## Workers

- Stay on your branch in your worktree. Do not touch `main` or other worktrees.
- Commit your work on your branch when done, then report: what changed, what
  you tested, and anything you were unsure about.
- If the task turns out to be ambiguous in a way that changes the design, stop
  and report back rather than guessing.

## The database is production

`DATABASE_URL` in `.env` points at the Railway production database, the same
one the live site and the poller use. Always run the app against it. The local
Postgres on `:5433` is a stale copy that nothing feeds, so a local server on it
shows weeks-old comments. Every worktree reads the same database, so git
isolation does not isolate it.

- The Railway `.env` lives in `.claude/worktrees/backend/`; the repo root has
  none. Run the local app from that worktree (fast-forward its branch to
  `main` first) rather than copying the credentials around.
- Run the local app read-only, so nothing it does can write to production:
  `PGOPTIONS='-c default_transaction_read_only=on' /Users/kenny/NYCEats/.venv/bin/uvicorn app.main:app --reload`,
  with the Vite dev server (`npm run dev` in `frontend/`) in front of it.
- Every pipeline script (`refresh.py`, `backfill.py`, `deploy.py`, `poller.py`,
  extraction runs) and every schema change reads `DATABASE_URL`, so running
  one locally writes to production. Workers must not run them: write the
  change and say in the report that it needs to be applied. The orchestrator
  runs it, one at a time, and only with the user's go-ahead.
- Don't run `sync.py`. It copies from `DATABASE_URL` to `RAILWAY_DATABASE_URL`,
  and with both on production it would copy production onto itself.
- Read-only queries are fine. Never `UPDATE`, `DELETE` or `INSERT` by hand
  without the user asking.

## Code conventions

- Endpoints are sync `def`, never `async def` — psycopg2 blocks
  (see `app/main.py`).
- Only `mentions` and the raw tables are truth; every score is a rebuildable
  cache. Never write derived data where evidence lives.
- Every score must click through to its comments; suppress permalinks where
  `was_deleted_later` is set.
- No composite score. Rank by one axis; the rest are filters or badges.
- Docstrings and comments explain *why*, in plain sentences, like the
  existing code. Match that density.
- Commit messages are one plain sentence saying what changed and why it
  matters (see `git log`), not conventional-commit prefixes.
