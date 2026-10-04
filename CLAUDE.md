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

## The database is shared

Every worktree reads the same `DATABASE_URL` from `.env`, so git isolation
does not isolate the database.

- Workers must not run schema changes, `refresh.py`, `sync.py`, `deploy.py`,
  `backfill.py`, or extraction runs against it. Write the change; say in the
  report that it needs to be applied. The orchestrator runs it, one at a time.
- Read-only queries are fine.
- Never touch the Railway database (`RAILWAY_DATABASE_URL`) without the user
  asking.

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
