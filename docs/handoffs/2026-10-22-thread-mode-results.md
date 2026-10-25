# Handoff: thread mode results and where everything is (2026-10-22)

Written on the Windows desktop for whoever picks this up next, most likely
a session on the laptop. Read `docs/handoffs/extraction-v6-thread.md` for how
thread mode works; this file is the state of play and the decision left.

## Where things are

- **Production (Railway).** `main` is `1ab4191` (staging-oct21), deployed on
  2026-10-21. The poller runs the multi-city code polling r/FoodNYC only
  (`POLL_SUBREDDITS=FoodNYC`) with extraction off (`POLL_EXTRACT` removed).
  The v6 and multi-city schema was applied by hand before the deploy. The
  board still reads the old rows (`extraction_settings.read_version =
  'legacy'`).
- **v6 rows in production:** 1,988 posts (all of Aug and Oct 2026, 671 of
  Sep) in post mode and 20 test comments in comment mode, all Haiku 5.5 at
  medium. Nothing else. None of it is on the board.
- **This branch** (`worktree-agent-ac58f1a7c0ba83592`) holds thread mode for
  `extract_v6.py`, the eval harness for it, the test's raw outputs and the
  review. It is **not merged**. Two code reviews were run and fixed
  (`122dcdd`, `b843d37`); 422 tests pass against a throwaway Postgres.
- **Not in git on purpose:** the planted-error keys
  (`eval/thread_v6/.sealed/`), every `.env`. The desktop's `.env` holds the
  production `DATABASE_URL` and the Anthropic key; the laptop has its own.

## Spend

The owner's ceiling for all extraction is **$95**. Spent so far: $0.94 for
the posts and the 20 test comments, $2.19 for the thread-mode test, about
**$3.13** in all, so about **$91.87** is left.

## What the test found

Nine batch runs, 1,125 chunks, no failures, nothing truncated (the longest
answer used 29.8k of the 32k limit). Graded blind by Opus reviewers with
round 4's rubric; they caught 57 of 59 planted errors. The full report is
`eval/thread_v6/review/report.md`; the cost lines come from
`python eval/thread_v6/review.py cost <runs>`.

On the fresh 300 (the same comments round 4's comment mode was graded on),
each comment's two answers were judged side by side:

| | thread mode | comment mode (round 4) | thread better / comment better / same |
|---|---:|---:|---|
| medium | 0.766 | 0.771 (0.791 when first graded) | 31 / 44 / 225 |
| low | 0.704 | 0.62 | 82 / 40 / 178 |

- At medium the two modes tie. Thread mode finds a few more places (recall
  0.955 against 0.935) and is a little less precise (0.951 against 0.972)
  and softer on complaints (negative recall 0.837 against 0.884).
- At low, thread mode is clearly better than comment mode, because the whole
  conversation makes up for the lighter reasoning.
- Threads with split reply groups scored 0.85, so splitting and the quoted
  parent chain work. Only 4 mentions were filed under the wrong comment.
- Posts extracted as item `[0]` scored 0.81, in line with post mode.
- Both modes share the same weak spots, which are prompt work (round 5):
  short replies that only point back at a place, superlatives raised without
  a city-wide word, overall praise copied into taste, and reactions to a
  photo or a story treated as verdicts.

## What it costs

| | per 1,000 comments | the backlog (about 755k comments) |
|---|---:|---:|
| thread, medium | about $0.17 (about $0.15 in chunks of 25) | about $115–128 |
| thread, low | about $0.12 (about $0.11 in chunks of 25) | about $82–91 |
| comment, medium, batch | about $0.23–0.30 | about $175–225 |

New comments in a daily thread batch at medium come to about $3 a month.
Chunks of 25 were about 10% cheaper than 15 but their quality was not
graded; grading a sample of the `big-med32k-c25` run costs nothing but
reviewer time.

## The decision left for the owner

1. Thread medium, newest first, keeping about $15 in reserve: about the last
   two years at comment mode's quality.
2. Thread low for everything: six points under medium, still above comment
   mode at low, and it uses nearly the whole budget.
3. A mix: medium for the last one to two years, low for the older history.
   This was the recommendation.

## Steps before any production thread run

1. A last look at the branch, then merge it to `main` with the owner's
   go-ahead. Move the main checkout's unrelated untracked `eval/` folder
   aside first, since this branch adds a tracked `eval/`.
2. Apply `extract_v6_schema.sql` again to create `extract_chunks`
   (`psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f extract_v6_schema.sql`).
   After the merge, every `extract_v6.py` run refuses until it exists.
3. Put the measured output fit into `anthropic_v6.THREAD_OUTPUT`, then run
   `extract_v6.py --mode thread --dry-run` to price the backlog read-only.
4. Then the backfill in batch, newest first, in capped steps.
5. Later: the daily thread-mode batch in the poller (decided, not built),
   prompt round 5, and scoring v3, which blocks the board's switch to v6.

## Things learned on this machine

- Windows can lock a file for a moment while `eval/budget.py` replaces its
  ledger (`os.replace` raised PermissionError once, probably an antivirus
  scan). The run lost nothing and resumed cleanly. A short retry around that
  `os.replace` would stop it recurring.
- Git checks files out with CRLF on Windows. This branch adds a
  `.gitattributes` rule for `prompts_v6/` so the pinned prompt hashes match.
- `python -I` ignores `PYTHONIOENCODING`, and Windows' default console
  encoding cannot print emoji, so scripts that print comment text set
  stdout to UTF-8 themselves.
- Keep the machine awake during batch runs. One run here took six and a half
  hours instead of ten minutes, most likely because the PC slept.
