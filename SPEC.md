# NYCEats — algorithm spec

Supersedes the working notes where they conflict. Everything under **Decided**
is settled and measured; **Open** is still unresolved.

---

## Pipeline

```
Arctic Shift  ->  comments + threads  ->  mentions  ->  derived scores
   (raw)          (append-only)          (LLM)         (recomputable cache)
```

Only `mentions` and the raw tables are truth. Every score is a cache that can be
dropped and rebuilt.

---

## Decided — ingestion

**Source: Arctic Shift.** Reddit's `.json` API is WAF-blocked and OAuth
registration requires manual approval since late 2025. Arctic Shift retrieves via
the official API, captures ~20s after posting, and re-captures at 36h.

- Poll `/comments/search?subreddit=FoodNYC&limit=100&sort=desc` every 30 min.
- Unknown thread -> fetch the post, then every comment in it, before inserting.
- Dedup on the `t1_`/`t3_` fullname. All inserts idempotent.
- History available back to 2014-08-24 (~747k comments, ~47k posts).

**Score settles once, at 36h.** Arctic Shift's second pass is the only update;
re-fetching later returns the same number. Track with `score_settled`.

**`_meta.was_deleted_later`** flags comments gone from Reddit. Required for the
permalink click-through rule — never link evidence that 404s.

---

## Decided — extraction context

A comment alone is not enough context. Pass:

1. **Post title** (~61 chars avg)
2. **Post selftext** (~1,087 chars avg, present on 82% of posts) — carries the
   real ask: budget, neighborhood, what they've already tried
3. **Immediate parent comment** (~82 chars avg)

**Not the full ancestor chain.** Measured on a 215-comment thread: 70% of
comments are top-level, and only 15 of 215 sit deeper than one reply. Walking to
root costs tokens and usually lands on something unrelated.

`selftext` dominates the prompt. If cost matters, truncate it or extract
per-thread instead of per-comment.

---

## Decided — storage

Two raw tables (`schema.sql`): `threads`, `comments`.

- `comments.thread_id` is a real FK; the poller guarantees the post exists first.
- `comments.parent_comment_id` is **not** a FK — 56% of replies arrive before
  their parent. `fill_tree` resolves `root_comment_id` and `depth` after insert
  with a recursive CTE, and self-heals when late parents land.
- Facts get copied in (`restaurant_raw`), conclusions get referenced
  (`entity_id`) so re-resolution never destroys evidence.

---

## Decided — scoring

Unchanged from the working notes:

- **Volume** — decayed mention count, half-life ~180d.
- **Momentum** — 7d decayed count ÷ volume. Cancels "famous", leaves "changing".
- **Lazy decay** — store `(value, last_updated)`, shrink on next touch. Do the
  shrink-and-add in one `on conflict do update` so concurrent mentions can't
  clobber each other.
- **Weighting at mention time** — per-author cap, `N/sqrt(N)` thread divisor,
  momentum floor ~5 weighted mentions, separate "new" label for no-baseline
  entities.
- **Price is two fields** — `expensiveness` (fact) and `value` (opinion).
- **Aspects** — per `(entity, aspect)` decayed `W` and `S`, mean `S/W`, shrunk
  toward city mean. Missing renders as absent, never neutral. A 0 is "mixed".

### Upvotes (new)

**Score does not multiply volume.** Volume measures attention; a mention is a
mention.

Score weights the **aspect sentiment** mean only:

```
w = 1 + log(1 + max(score, 0))
```

Log-compressed, or one +347 comment outweighs 300 others. Floor negatives at 0.

Caveats: 49% of comments sit at score 1, so it adds signal for a minority. And
score partly measures *posted early*, not *is right* — the same correlation the
thread divisor already fights.

**`controversiality`** is Reddit's own mixed-vote flag. Free input to the
deferred polarization work, though it describes the comment's reception rather
than the restaurant's.

---

## Open

- **Entity resolution.** Still the hardest part and most likely to sink it.
  pgvector is available in Postgres, so embedding + gazetteer blocking can live
  in the same database.
- Unresolved names: pending-cluster, drop, or manual queue.
- Chains, closed restaurants.
- Exact half-lives, pseudo-count, momentum floor. All still placeholders.
- Whether aspects beyond `food` and `value` produce signal at low volume.
- Frontend framework.

---

## Deferred — now buildable

The original notes deferred these for lack of history. **The history exists** —
12 years of it — so these are buildable as soon as backfill runs, not in two
years:

- **Polarization** — 5-bucket decayed histogram per aspect.
- **Longevity** — undecayed `first_seen`, `total_mentions`, monthly coverage
  bitmap. Note ~145 months of history, so one 64-bit int is not enough.
- **Sentiment momentum**, separate from volume momentum.

---

## Non-negotiable

Every score clicks through to the comments that produced it, with live Reddit
permalinks. Suppress links where `was_deleted_later` is set.

## Rejected

A single composite score. Rank by whichever axis the user picks; everything else
is a filter or a badge.
