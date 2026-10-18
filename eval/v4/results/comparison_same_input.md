# v4 comparison, reference = same_input labels

Reference: 504 comments, 357 with a required mention. 'weighted' is re-weighted to real traffic; ceilings are Claude against itself.

## comment weighted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.971 | 22 |

## comment

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.056 | 0.958 | 1.0 | 1.0 | – | 1.0 | 0.958 | 25 |

## comment weighted tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.970 | 20 |

## comment weighted holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 2 |

## thread weighted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.901 | 46 |

## thread

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.935 | 46 |

## thread weighted tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.901 | 46 |

## By draw, stratum and heuristic

### comment draw:overlap_v1

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.500 | 0.500 | – | – | – | 1.0 | 1.0 | 3 |

### comment draw:random

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 2 |

### comment draw:targeted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.952 | 20 |

### comment holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 2 |

### comment stratum:avoid_or_strong_negative

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 2 |

### comment stratum:deep_chain_context_gap

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | 3 |

### comment stratum:long_list

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | – | – | – | – | – | – | – | 1 |

### comment stratum:neg_wording_nonneg_score

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | 2 |

### comment stratum:none

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 1 |

### comment stratum:overlap_v1

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.500 | 0.500 | – | – | – | 1.0 | 1.0 | 3 |

### comment stratum:price_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 3 |

### comment stratum:question_or_unvisited

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 0.750 | 4 |

### comment stratum:reply_ancestor_named

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 2 |

### comment stratum:short_opinion_reply

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | – | – | – | – | – | – | – | 1 |

### comment stratum:stuck_default_with_opinion

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 2 |

### comment stratum:zero_mentions_suspicious

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | 1 |

### comment tag:avoid_or_strong_negative

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 2 |

### comment tag:deep_chain_context_gap

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | 3 |

### comment tag:extracted_no_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.167 | 0.833 | 1.0 | – | – | 1.0 | 1.0 | 8 |

### comment tag:long_list

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 2 |

### comment tag:neg_wording_nonneg_score

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | 2 |

### comment tag:never_extracted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.900 | 10 |

### comment tag:original_thread_prompt

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.091 | 0.917 | 1.0 | – | – | 1.0 | 1.0 | 14 |

### comment tag:price_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 3 |

### comment tag:question_or_unvisited

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 0.750 | 5 |

### comment tag:reply_ancestor_named

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.250 | 0.750 | 1.0 | – | – | 1.0 | 1.0 | 6 |

### comment tag:short_opinion_reply

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | – | – | – | – | – | – | – | 1 |

### comment tag:stuck_default_with_opinion

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 3 |

### comment tag:zero_mentions_suspicious

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.250 | 0.750 | – | – | – | – | 1.0 | 5 |

### comment tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.062 | 0.950 | 1.0 | 1.0 | – | 1.0 | 0.950 | 23 |

### thread draw:targeted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.935 | 46 |

### thread stratum:chunk_failure_dense

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 0.977 | 21 |

### thread stratum:chunk_misattached

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.842 | 25 |

### thread tag:avoid_or_strong_negative

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 2 |

### thread tag:chunk_failure_dense

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 0.977 | 21 |

### thread tag:chunk_later

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.842 | 25 |

### thread tag:chunk_misattached

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.842 | 25 |

### thread tag:chunk_parent_outside

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.842 | 25 |

### thread tag:chunk_title_names_place

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.842 | 25 |

### thread tag:deep_chain_context_gap

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | – | – | – | – | – | – | – | 2 |

### thread tag:extracted_no_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.833 | 29 |

### thread tag:long_list

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 4 |

### thread tag:mixed_prompt_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 0.974 | 13 |

### thread tag:original_thread_prompt

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.842 | 25 |

### thread tag:question_or_unvisited

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | 1 |

### thread tag:reply_ancestor_named

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 9 |

### thread tag:short_opinion_reply

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | – | – | – | – | – | – | – | 2 |

### thread tag:stuck_default_with_opinion

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 5 |

### thread tag:zero_mentions_suspicious

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | – | – | – | – | – | – | 0.000 | 3 |

### thread tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 0.935 | 46 |

## Claude vs v1 hand gold (overlap items)

| drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|
| 0.130 | 0.932 | 1.0 | 0.500 | 1.0 | 1.0 | 0.854 | 50 |

