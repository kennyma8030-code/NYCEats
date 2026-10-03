# Sampling

Built by `eval/build_items.py` (deterministic, seed `nyceats-eval-v1`), with
raw numbers in `eval/sampling_stats.json`.

## Data source

These items were drawn from the **local dev snapshot** at
`postgresql://postgres:dev@localhost:5433/foodnyc`, not from production
Railway. `DATABASE_URL` was not set in the build environment. The snapshot
holds 755,851 comments and 143,831 mentions, with comments through
2026-09-26. Every production prompt hash with real volume is present:
`ca5439be83b3` (177,078 comments) and `1d5bac550078` (21,326). Only the
371-comment `0d75b20b5f83` run from Oct 2 is missing, and it is not needed.
Comment ids are Reddit ids, so every item resolves the same way against
production.

The snapshot reproduces the problems that motivated this eval: 82.8% of food
scores are exactly 0.3 or 0.6, and 93,176 of 198,404 extracted comments (47%)
have at least one mention. It has only 3 `alias_overrides` rows (cote,
republic, otto). If production has more, refresh `eval/alias_overrides.json`.

Every connection is opened with `set_session(readonly=True)`.

## Pool

These are extracted comments (`extracted_at is not null`), with bodies other
than `[deleted]`/`[removed]` and longer than 15 characters (the same filter as
`extract.next_batch`). That gives 198,404 rows; in this snapshot every
extracted comment passes the filter. Of those, 27 are **replies whose parent
comment is missing** from the DB and are excluded. Across the whole table
there are 229 such replies; most were never extracted. The 374 comments in
the 17 sampled whole threads are also removed from the single-comment pool,
which leaves **198,003**.

The stored extraction is used only to *find* candidates: a comment's mention
count, its parent's, its grandparent's, and its entity keys. None of it is
written into `items.jsonl`.

## Risk-group heuristics

The regexes are in `build_items.py` (`flags_for`). `n`, `pn` and `gn` are the
stored mention counts of the comment, its parent and its grandparent. Depth 0
means top-level.

| group | rule |
|---|---|
| zero_mentions_suspicious | `n = 0` and a place word (`try / went to / spot / place / recommend / favorite / pizzeria / deli / ...`) and (a capitalized token mid-sentence, or a `'s` possessive, or a top-level comment in a thread whose title asks for recs) |
| nameless_reply | depth ≥ 1, `pn > 0`, length ≤ 120, and either starts with `mid / overrated / this / same / agree / hard disagree / +1 / meh / nah / lol no / fine / ...` or is ≤ 50 chars |
| avoid_list_negation | `avoid / skip / tourist trap / don't go / don't bother / not worth / overrated / stay away / overhyped` |
| strong_negative | `got sick / food poisoning / rude / worst / never again / never going back / regret / disgusting / inedible` |
| long_list | ≥ 8 line breaks, or ≥ 4 bullet / numbered lines, or `n ≥ 6` |
| deep_chain | depth ≥ 3, `gn > 0`, `pn = 0`, length ≤ 400 (place named above the immediate parent: the comment-mode context gap) |
| ambiguous_name | a stored entity_key that is in `alias_overrides`, or a single-token key with ≥ 15 mentions that prefixes ≥ 3 DOHMH restaurant names (91 keys: joes, modern, johns, grill, smith, penny, ...) |
| out_of_scope | Whole Foods, Zabar's, Trader Joe's, Chelsea/Essex/DeKalb Market, Eataly, food hall, big chains (McDonald's, Chipotle, Shake Shack, Starbucks, Dunkin, Sweetgreen), H Mart, Fairway, Costco, wine/cocktail bar, bodega, grocery, supermarket |
| messy_text | length ≥ 1,500, or ≥ 60 chars with no capital letters |
| random | uniform over the pool |

## Draw

Within each group, candidates are ordered by `md5(seed || comment_id)` and
the first *k* not already drawn are taken. Groups draw in the order below. An
item is drawn once but tagged with **every** group it matches, so the tagged
counts are larger than the drawn counts.

| group | candidates in pool | drawn | tagged in sample | stratum population |
|---|---:|---:|---:|---:|
| nameless_reply | 14,350 | 40 | 43 | 14,350 |
| deep_chain | 2,899 | 30 | 30 | 2,899 |
| strong_negative | 2,392 | 35 | 35 | 2,270 |
| avoid_list_negation | 3,358 | 35 | 39 | 3,105 |
| ambiguous_name | 5,000 | 25 | 28 | 4,354 |
| out_of_scope | 4,773 | 25 | 32 | 4,060 |
| long_list | 4,237 | 30 | 38 | 3,134 |
| zero_mentions_suspicious | 11,119 | 50 | 70 | 9,688 |
| messy_text | 5,773 | 25 | 38 | 4,689 |
| random | 198,003 | 100 | 100 | (none: 149,454) |
| **total single comments** | | **395** | | 198,003 |

There are 295 targeted items (75%) and 100 random ones (25%). Production
prompt for the single items: 349 `ca5439be83b3` (thread mode) and 46
`1d5bac550078` (comment mode).

**Strata** are used for population reweighting in `score.py`. Each pool
comment belongs to exactly one stratum: the first group in draw order that it
matches, or `none`. The stratum population is the pool count, and each item
carries its `stratum`. Within a stratum the draws are md5-uniform, so
weighting each stratum by population / labeled-count gives an approximately
unbiased population estimate. It is approximate because random items and
targeted items share strata. The 100 random items also stand alone as the
plain representative slice.

## Whole threads

The candidates are threads whose eligible comments (same filter) are **all**
extracted and number between 8 and 60. That is 4,560 threads: 1,366 long
(more than 25 comments, so chunked), 957 whose title names a place (one of the
300 most-mentioned keys, or a `'s` possessive), and 1,420 "where should I eat"
titles. Draws are md5-ordered: 5 long threads with 26–60 comments, then 6
title-names-place and 6 where-to-eat threads with ≤ 30 comments each, under a
budget of 400 comments.

| item | thread | drawn for | comments | title |
|---|---|---|---:|---|
| t001 | t3_1us3txb | thread_long | 59 | Another Pressed Juicery location bites the dust... |
| t002 | t3_1qvx95d | thread_long | 26 | Noona's Ice Cream |
| t003 | t3_1u5t5ql | thread_long | 28 | Best deli pickles in NYC (preferably near manhattan) |
| t004 | t3_1vzfd60 | thread_long | 57 | Mama’s Too in NYC has some of my favorite slices ever!! |
| t005 | t3_1qoyhc6 | thread_long | 31 | Weightloss veg orders in NYC |
| t006 | t3_1vktrj1 | title_names_place | 24 | Eleven Madison Park, Lunch. Menu, drinks, and a game. |
| t007 | t3_1tgc53s | title_names_place | 9 | Anyone been to Sofreh in Prospect Heights ... |
| t008 | t3_1og6uol | title_names_place | 8 | A Brit's first time |
| t009 | t3_1w6chew | title_names_place | 13 | Finally went to 4 Charles: Im appalled. Anyone else? |
| t010 | t3_1v6qq5o | title_names_place | 17 | Solid day of eats @ Mama’s Too & Red Gate Bakery |
| t011 | t3_1ryvvhd | title_names_place | 22 | red hook tavern dinner walk in - how early ... |
| t012 | t3_1t41slb | where_to_eat | 9 | Where can I get a kir royale in Brooklyn? |
| t013 | t3_1spkzwx | where_to_eat | 16 | Help Finding Cheap Prosciutto Chunks? |
| t014 | t3_1tarwra | where_to_eat | 23 | ... best chicken salad sandwich? |
| t015 | t3_1oeazb6 | where_to_eat | 12 | Looking for a dive bar along the 1 train ... |
| t016 | t3_1u5380k | where_to_eat | 9 | ... Vietnamese La Lot leaves? |
| t017 | t3_1trcpi3 | where_to_eat | 11 | Where can we get mie gorang? ... |

That is 374 comments, all extracted in production by `ca5439be83b3`.

## What each item stores

- `inputs.comment.user_message` comes from `prompt.build_user_message(body,
  title, selftext, parent_body)`, with the parent fetched exactly as
  `extract.next_batch` does.
- `inputs.thread` comes from `prompt_thread.build_message` over **all**
  eligible comments in the thread (not only the pending ones production saw),
  ordered by `(coalesce(root_comment_id, id), created_utc)` and chunked 25 at a
  time. It holds the chunk containing the comment, the comment's short id, and
  the short-id → comment-id map. Thread items carry every chunk plus a
  comment-mode input per comment.
- `production` records `extracted_with`, the prompt hash, and the production
  mode.
- `context` holds the full untruncated ancestor chain and the direct replies;
  the rest of the thread is referenced by `thread_id` / `permalink`.

## Caveats

- The heuristics use the original model's own output (`n = 0`, `pn > 0`), so
  the risk groups lean toward its failure modes by design. Headline numbers
  should come from the reweighted or random figures, not the raw pooled ones.
- `zero_mentions_suspicious` items are, by construction, ones the original
  model returned nothing for. This is visible in the group name, so the
  labeling packets omit risk groups.
- The renderer is identical across all four prompt versions; only
  `SYSTEM_PROMPT` changed. A future prompt that changes rendering needs
  `build_items.py` re-run with that renderer.
