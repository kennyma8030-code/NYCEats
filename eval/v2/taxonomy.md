# v2 weakness taxonomy

v2 is a **diagnostic** set: 481 comments, each tagged with one or more
weaknesses of the ORIGINAL extraction (deepseek-v4-flash,
`ca5439be83b3` / `1d5bac550078`). It is biased toward that model's failures
by construction. **Model comparisons are made on v1** (reweighted); v2 shows
*why* a model fails and whether a prompt change fixed a specific failure.
**No v2 comment may be used as a prompt example**, and neither may any v1
comment.

## How it was built

1. **Score.** The original extraction was scored against v1 gold
   (`eval/baseline/production__stored__all.jsonl`).
2. **Re-read.** `eval/adjudicate.py` listed every disagreement with proposed
   tags, 259 comments in all, and each one was re-read. Twenty-three were
   gold errors; they were patched (`labels/adjudication.py`,
   `gold_changes.md`). Everything else was confirmed as a model failure and
   tagged. 244 v1 comments carry at least one tag.
3. **Top up.** Every weakness with fewer than 25 items was topped up. The
   miner (`v2/mine_topups.py`) finds similar comments with SQL heuristics;
   the stored output is used only to find them. The top-ups were then
   labeled **blind** (`v2/labels/topup_*.py`): 237 comments.
4. **Confirm.** The original extraction was then scored on the top-ups.
   `confirmed: true` marks those where it really showed the mined weakness.
   Most top-ups are "same situation" items that the original happened to
   handle, which still makes them useful controls.
5. **Split.** dev/test is fixed and stratified by first weakness
   (md5-ordered, alternating): **dev 246, test 235**. Tune prompts on dev;
   report on test.

## Weaknesses

| tag | definition | owner priority |
|---|---|---|
| `dropped_nameless_reply` | a reply judges a place named only in the parent, ancestors or post title; the model emits nothing for it | volume, negatives |
| `dropped_in_list` | the comment names 3+ places; the model drops some | volume |
| `dropped_named_mention` | a place typed in the comment (few names) is dropped, with no context excuse | volume |
| `dropped_reference_mention` | a named place with no opinion ("haven't been", "the chef moved to X", a question) is dropped | volume |
| `closed_place` | a closed place is dropped, or given sentiment (rule: required, aspects null, "closed") | volume |
| `context_gap` | the place or its polarity is not determinable from what the mode sends (an ancestor outside comment mode or outside the thread chunk). A pipeline gap, not a model error | diagnostic |
| `missed_negative` | gold has an aspect at -1 or below; the model has no negative (aspect or `is_negated`) | **negatives** |
| `negative_softened_to_positive` | gold negative, model positive (e.g. sarcasm: "second this" in a worst-place thread) | **negatives** |
| `softened_negative` | negative kept but too mild beyond tolerance ("got sick" scored -0.6) | **negatives** |
| `wrong_sign` | aspect sign flipped outside accepted alternatives | negatives |
| `missed_value_complaint` | "overpriced / not worth the money / rip-off" not captured | **value complaints** |
| `missed_dish_negative` | a dish-level negative or "avoid the X" not captured. The production prompts have no field for this, so every one is missed by design | **dish negatives** |
| `negation_scope` | `is_negated` wrong: an avoid instruction missed, or a bad review read as an avoid | negatives |
| `inferred_aspect` | an aspect scored that the comment does not address | precision |
| `default_0.3` | food 0.3 (the "named as an answer" anchor) where the comment says more (praise, a reference, or another aspect) | quantization |
| `hallucinated_place` | a non-place or placeholder emitted as a restaurant ("the one on 23rd st", "Cart on 61st and 8th ave", a meal-prep company) | precision |
| `dish_as_place` | a dish or phrase emitted as a restaurant ("Their pistachio gelato", "Great pizza", "bodega bacon egg & cheese") | precision |
| `wrong_target` | the opinion is attached to the wrong place (e.g. "their parm" at The Palm emitted as Parm) | attribution |

`dish_as_place` and `placeholder` names (inside `hallucinated_place`) are
additions to the original list; they made up most of thread mode's false
positives.

## Counts

"total" counts items carrying the tag (an item can carry several).
"confirmed" counts the top-ups where the original model actually showed the
weakness.

| weakness | total | from v1 failures | top-ups | top-ups confirmed | dev | test |
|---|---:|---:|---:|---:|---:|---:|
| dropped_nameless_reply | 143 | 143 | 0 | – | 71 | 72 |
| dropped_in_list | 25 | 13 | 12 | 0 | 14 | 11 |
| dropped_named_mention | 25 | 21 | 4 | 2 | 13 | 12 |
| dropped_reference_mention | 25 | 23 | 2 | 1 | 14 | 11 |
| closed_place | 25 | 7 | 18 | 7 | 13 | 12 |
| context_gap | 25 | 6 | 19 | 3 | 13 | 12 |
| missed_negative | 54 | 54 | 0 | – | 27 | 27 |
| negative_softened_to_positive | 25 | 4 | 21 | 1 | 14 | 11 |
| softened_negative | 25 | 7 | 18 | 2 | 12 | 13 |
| wrong_sign | 25 | 5 | 20 | 2 | 12 | 13 |
| missed_value_complaint | 25 | 9 | 16 | 1 | 13 | 12 |
| missed_dish_negative | 29 | 29 | 0 | – | 15 | 14 |
| negation_scope | 25 | 0 | 25 | 2 | 13 | 12 |
| inferred_aspect | 25 | 12 | 13 | 3 | 15 | 10 |
| default_0.3 | 25 | 14 | 11 | 3 | 13 | 12 |
| hallucinated_place | 25 | 7 | 18 | 6 | 12 | 13 |
| dish_as_place | 25 | 9 | 16 | 6 | 13 | 12 |
| wrong_target | 25 | 1 | 24 | 0 | 12 | 13 |
| **items** | **481** | 244 | 237 | | **246** | **235** |

## Reading v2 results

```bash
python eval/score.py RUN.jsonl --gold eval/v2/gold.jsonl --items eval/v2/items.jsonl --stats '' --tag __v2
```

The "By group" table has one column per weakness, plus `split_dev` and
`split_test`. For a weakness, compare the column against the original
model's (`eval/baseline/results/*production__stored__v2.md`). Where
`confirmed` is low, the top-ups behave mostly like controls: a prompt change
should not make them worse.
