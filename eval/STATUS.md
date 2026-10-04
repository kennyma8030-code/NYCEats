# Status (2026-10-04)

## Done

- **v1 gold is complete** (`gold.jsonl`, sources in `labels/`). It covers
  all 395 single comments plus every one of the 374 comments in the 17
  whole threads: 769 comment lines and 825 mentions, of which 426 comments
  have at least one required mention.
  - Labeled blind under the owner's rules (README).
  - Every mention carries expensiveness, dish_sentiment, search_terms,
    value_complaint, out_of_scope, and resolvability per mode.
  - c0001–c0050 were relabeled when the rules changed.
- **Canonical keys** use production's 1,901 alias overrides; its 279
  excluded entities count as out of scope.
- **Original extraction scored** (`baseline/`). Production's stored output
  for these comments comes from the local snapshot and is identical to
  production for them. Reweighted to the population:

  | metric | value |
  |---|---|
  | drop rate | 0.230 |
  | mention recall | 0.733 |
  | negative-mention recall | 0.464 |
  | value-complaint recall | 0.490 |
  | dish-negative recall | n/a (no field) |
  | sign accuracy | 0.972 |

  Thread mode is much worse than single comments: drop rate 0.486, recall
  0.490. Nearly all of the gap is nameless replies about the post's subject.
- **Adjudication.** All 259 disagreeing comments were re-read, producing 23
  gold patches (`gold_changes.md`). The rest are confirmed model failures.
- **v2 diagnostic set** (`v2/`): 481 items, 18 weaknesses, each with at
  least 25 items (237 blind-labeled top-ups); dev 246 / test 235. See
  `v2/taxonomy.md`.
- **score.py** leads with the owner-priority headline (drop rate → mention
  recall → negative-mention recall → value-complaint recall → dish-negative
  recall → sign accuracy and levels used). It handles both the production
  and the rubric output shapes. `--self-test` passes on v1 and v2.

## Notes and caveats

- **Excluded entities.** Production's `excluded_entities.json` contains a
  few real in-scope places: `56709` (a LIC bar), `hudson eats` (a food
  hall), and numeric or short keys. Mentions of these are ignored in
  scoring, matching production's choice. Revisit if those entries were
  mistakes.
- **v2 confirmations.** Only a minority of top-ups were actually failed by
  the original model (`confirmed` per item; see the table in
  taxonomy.md). The mining heuristics found the right *situations*, not
  necessarily failures, so treat unconfirmed top-ups as controls.
- **Dish negatives.** The production prompts cannot express a dish-level
  negative. Every gold dish negative (31 on v1) is missed by design, and the
  metric reads n/a for those runs.
- **Missing parents.** Two thread comments (t015) reply to parents missing
  from the DB. They are labeled from what is visible.

## Next

1. Run the model grid (coordinator) on v1 in both modes, with 3 reps for
   nondeterminism, and compare on **reweighted** and **random**.
2. Use v2 (dev) to iterate on prompts; report v2 (test) once per candidate.
3. Owner review: the excluded_entities edge cases, and whether bars and
   food events (The Great Nosh) should count.
