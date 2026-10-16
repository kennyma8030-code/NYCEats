# Scoring (`score.py`)

`score_v5.py` scores the same runs against the v5 gold, with the rules in
`schema_v5.md`. This page describes `score.py`, which scores against the v1
gold. Back to the index: `../README.md`.

The **headline** is reported first, in the owner's priority order:

1. **Comment drop rate.** Among comments with at least one required gold
   mention, the share where the model returned none. Lower is better.
2. **Mention recall.** Required gold mentions matched ("how many people are
   talking").
3. **Negative-mention recall.** Gold mentions with any aspect at -1 or
   below, counted only when the match carries a negative (an aspect below 0
   after bucketing, or `is_negated`).
4. **Value-complaint recall.** The model's `value_complaint` field if the
   prompt emits it; otherwise value below 0.
5. **Dish-negative recall.** Gold dish entries at -1 or below, or marked
   avoid. The model counts with a `dish_sentiment` entry whose name matches
   leniently (normalized substring, or token overlap of at least half) and
   whose level is below 0 or which is marked avoid. It is **n/a** for runs
   that never emit `dish_sentiment`, such as the production prompts.
6. **Sign accuracy** over valued aspect pairs, and **levels used** (distinct
   7-point levels after bucketing).

Then everything else:

- **Search-terms recall.** Gold `search_terms` matched leniently against the
  model's descriptors ∪ dishes ∪ dish_sentiment names.
- **Expensiveness** presence F1 and exact / within-1 agreement.
- Reference-mention and closed-mention recall, and the
  negative-to-positive rate.
- **Mention P/R/F1:** greedy one-to-one matching per comment on the key
  (`normalize_entity`, then alias_overrides). A model key matches a gold
  mention if it equals the `canonical_key` or an `accept_keys` entry;
  failing that, a fuzzy match counts: extra trailing words, or a
  possessive/plural `s`. Ambiguous and out-of-scope gold, and model keys in
  `excluded_entities`, are ignored both ways.
- **Aspects**, on matched required mentions:
  - presence F1 (null vs not), lenient to alternatives;
  - over pairs both sides valued: sign accuracy, exact-level accuracy,
    within-one-level accuracy, and MAE in levels;
  - Spearman correlation for food;
  - quantization: distinct raw food values, the share at 0.3/0.6, and the
    top values;
  - the negative-softened rate (gold negative, model level higher).
- **`is_negated`** accuracy and recall, and **`is_firsthand`** accuracy, skip
  uncertain or null gold.
- **Error attribution:** a missed mention or aspect sign error is a
  `context_gap` when the gold marks it not resolvable in the run's mode, and
  a `model_error` otherwise. For stored production output, the mode comes
  from each comment's prompt hash.
- **Breakdowns:** per risk group (an item counts in every group it is tagged
  with), plus `reweighted`, a population estimate over single-comment
  strata. Each stratum is weighted by its pool size over its labeled count;
  the share of the population with labels is reported. Thread items appear
  under `threads` and the thread groups.
- **Repeats:** mean ± sd across reps, plus the rate at which a gold
  mention's matched or missed status flips between reps.
- Run cost, tokens, latency, error count and JSON validity come from
  `run.py`'s records.
