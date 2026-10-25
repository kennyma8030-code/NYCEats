# PRD: daily thread-mode extraction in the poller

Status: proposed, not started. Blocks nothing until the board reads v6
(`extract_v6.py --read v6`); before that, extracting new comments only spends
money on results nobody sees.

## Problem

When the poller extracts (`POLL_EXTRACT=1`, `EXTRACT_VERSION=v6`), it runs
`extract_v6_once` every 30-minute chores pass in comment mode: one direct,
full-price request per new comment and per new post, effort medium, written in
the last 7 days, capped at `POLL_EXTRACT_MAX_USD` a pass (default $1). Each
comment is read with only its ancestor chain, never its siblings, and the
poller never uses thread mode, even for a thread that is brand new.

The backlog, meanwhile, will be extracted in thread mode (`--mode thread
--effort medium --batch`). So the same subreddit ends up extracted two ways,
depending on when a comment arrived.

## Proposal

Once a day, the poller extracts recent threads in thread mode through the
Batches API, instead of comment by comment every half hour.

- A brand-new thread goes out as chunks: the post as item `[0]` plus up to
  about 25 comments each.
- A late reply to a thread that is already extracted needs no separate path.
  Thread mode already sends only the due comments, with the done ones quoted
  as context.
- The comment-mode pass stays available behind a switch, for when freshness
  matters more than context.

## Trade-offs

| | Comment mode every 30 min (today) | Thread mode once a day (proposed) |
|---|---|---|
| Delay to the board | under an hour | up to about a day (batch turnaround plus the daily clock) |
| Context the model sees | the comment and its ancestors | the post and the comment's neighbours in its chunk |
| Accuracy (benchmark, medium) | about 79% fully right | about 79% fully right (`docs/handoffs/2026-10-22-thread-mode-results.md`) |
| Price | direct, full price | batch, half price; at about 280 comments a day the difference is pennies |
| One extraction path for backlog and new comments | no | yes |

## Requirements

1. A daily pass in `poller.py`, behind its own switch (for example
   `POLL_EXTRACT_MODE=thread`), that runs thread mode with `--batch` over
   threads with due items, written within a window (default 7 days, matching
   `POLL_EXTRACT_V6_MAX_AGE_DAYS`).
2. It respects a per-day cap (for example `POLL_EXTRACT_DAY_MAX_USD`) and the
   v6 lock (`extract_v6.try_lock`), so it never overlaps a manual backlog run.
3. A batch that is still running at the next chores pass is re-attached and
   collected, not resubmitted. `extract_v6.py`'s pending-submission handling
   already does this for manual runs.
4. It refreshes the board after it stores anything, like the comment-mode
   pass does.
5. Logs say what was sent, collected, held or left, using the existing
   `Stats` lines, so `--status` and the Railway logs tell the same story.
6. Comment mode stays the default until this is switched on, and the
   existing poller tests pass unchanged.

## Out of scope

- The backlog itself; that is the manual `--mode thread` ramp.
- Other cities. Extraction reads `subreddits.HOME` only.
- Switching the board to v6.

## Open questions

- **Delay vs. cost.** Is up to a day acceptable for new comments, or should
  very fresh threads keep a faster path?
- **Daily or more often.** Should the pass run once a day, or every few hours
  with batches, to cut the delay while keeping batch pricing?
- **Low-volume threads.** A thread with one new comment is a one-item chunk,
  which is comment mode at batch price plus the post as context. Is that
  fine, or should those wait until a thread has a few due comments?
