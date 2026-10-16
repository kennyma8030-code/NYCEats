# v4 comparison, reference = same_input labels

Reference: 504 comments, 327 with a required mention. 'weighted' is re-weighted to real traffic; ceilings are Claude against itself.

## comment weighted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.050 | 0.970 | 0.950 | 0.924 | 0.795 | 1.0 | 0.960 | 0.986 | 1.0 | 0.989 | 200 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 0.970 | 22 |

## comment

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.018 | 0.986 | 0.923 | 0.750 | 0.714 | 1.0 | 0.886 | 0.963 | 1.0 | 0.972 | 250 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.957 | 25 |

## comment weighted tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.064 | 0.964 | 0.956 | 0.920 | 0.889 | 1.0 | 0.932 | 0.991 | 1.0 | 0.988 | 160 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 0.969 | 20 |

## comment weighted holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.995 | 0.924 | 1.0 | 0.724 | 1.0 | 1.0 | 0.946 | 1.0 | 0.995 | 40 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 2 |

## thread weighted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.026 | 0.952 | 0.652 | 0.211 | 0.489 | 0.997 | 1.0 | 0.961 | 1.0 | 0.967 | 254 |
| claude self-consistency (same_input) | 0.000 | 0.969 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.789 | 46 |

## thread

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.049 | 0.945 | 0.767 | 0.667 | 0.700 | 0.992 | 1.0 | 0.979 | 1.0 | 0.961 | 254 |
| claude self-consistency (same_input) | 0.000 | 0.959 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.870 | 46 |

## thread weighted tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.022 | 0.953 | 0.648 | 0.211 | 0.448 | 0.997 | 1.0 | 0.961 | 1.0 | 0.967 | 213 |
| claude self-consistency (same_input) | 0.000 | 0.969 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.789 | 46 |

## thread weighted holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.082 | 0.927 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | – | 0.977 | 41 |

## By draw, stratum and heuristic

### comment draw:overlap_v1

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | – | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 0.958 | 50 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | – | 1.0 | – | 1.0 | 3 |

### comment draw:random

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.067 | 0.971 | 0.800 | 1.0 | – | 1.0 | 1.0 | 0.982 | – | 0.981 | 60 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | – | – | 1.0 | 2 |

### comment draw:targeted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.990 | 0.929 | 0.727 | 0.833 | 1.0 | 0.840 | 0.926 | 1.0 | 0.972 | 140 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 0.950 | 20 |

### comment holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.986 | 0.857 | 1.0 | 0.400 | 1.0 | 1.0 | 0.909 | 1.0 | 0.973 | 50 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 2 |

### comment stratum:avoid_or_strong_negative

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | 1.0 | 0.000 | 1.0 | 0.500 | 0.750 | 1.0 | 1.0 | 12 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 2 |

### comment stratum:deep_chain_context_gap

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | 0.000 | – | 0.889 | 17 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 3 |

### comment stratum:dish_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | 0.667 | 0.875 | 1.0 | – | 1.0 | – | 1.0 | 14 |

### comment stratum:long_list

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | – | – | – | – | – | 1.0 | – | 0.935 | 10 |
| claude self-consistency (same_input) | – | – | – | – | – | – | – | – | – | – | 1 |

### comment stratum:neg_wording_nonneg_score

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | – | 1.0 | 14 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 2 |

### comment stratum:none

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.057 | 0.967 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 44 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 1 |

### comment stratum:overlap_v1

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | – | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 0.958 | 50 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | – | 1.0 | – | 1.0 | 3 |

### comment stratum:price_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 0.833 | 0.833 | – | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 14 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 1.0 | 3 |

### comment stratum:question_or_unvisited

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 0.857 | – | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 14 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 0.750 | 4 |

### comment stratum:reply_ancestor_named

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.053 | 0.955 | 1.0 | – | – | 1.0 | 0.833 | – | – | 1.0 | 24 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | – | – | – | 1.0 | 2 |

### comment stratum:short_opinion_reply

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.889 | 0.667 | – | – | 1.0 | – | 1.0 | – | 0.889 | 14 |
| claude self-consistency (same_input) | – | – | – | – | – | – | – | – | – | – | 1 |

### comment stratum:stuck_default_with_opinion

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 0.000 | 0.000 | 1.0 | 1.0 | 0.500 | 0.833 | – | 1.0 | 13 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 2 |

### comment stratum:zero_mentions_suspicious

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.500 | – | – | – | – | 1.0 | – | – | 0.333 | 10 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 1 |

### comment tag:avoid_or_strong_negative

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | 1.0 | 0.667 | 1.0 | 0.667 | 0.750 | 1.0 | 1.0 | 25 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 2 |

### comment tag:deep_chain_context_gap

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | 0.000 | – | 0.917 | 25 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 3 |

### comment tag:dish_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | 0.667 | 0.875 | 1.0 | – | 1.0 | – | 1.0 | 14 |

### comment tag:extracted_no_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.050 | 0.909 | 1.0 | – | 1.0 | 1.0 | 0.800 | – | 1.0 | 0.909 | 64 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | – | – | 1.0 | 8 |

### comment tag:long_list

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | 1.0 | 0.500 | 1.0 | 1.0 | 0.957 | 1.0 | 0.969 | 23 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 1.0 | 2 |

### comment tag:mixed_prompt_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | – | – | – | 1.0 | 0.333 | – | – | 1.0 | 2 |

### comment tag:neg_wording_nonneg_score

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | – | 1.0 | 17 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 2 |

### comment tag:never_extracted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.022 | 0.991 | 0.970 | 0.778 | 0.857 | 1.0 | 0.952 | 0.966 | 1.0 | 0.982 | 125 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 0.900 | 10 |

### comment tag:original_thread_prompt

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.015 | 0.976 | 0.842 | 0.667 | 0.571 | 1.0 | 0.857 | 0.955 | 1.0 | 0.953 | 114 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 14 |

### comment tag:price_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 0.889 | 0.750 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 16 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 1.0 | 3 |

### comment tag:question_or_unvisited

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 0.875 | – | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 17 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 0.750 | 5 |

### comment tag:reply_ancestor_named

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.031 | 0.974 | 1.0 | – | 1.0 | 1.0 | 0.889 | 0.000 | 1.0 | 0.974 | 52 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | – | – | 1.0 | 6 |

### comment tag:short_opinion_reply

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.938 | 0.857 | 1.0 | – | 1.0 | – | 1.0 | 1.0 | 0.938 | 24 |
| claude self-consistency (same_input) | – | – | – | – | – | – | – | – | – | – | 1 |

### comment tag:stuck_default_with_opinion

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.984 | 0.333 | 0.000 | 1.0 | 1.0 | 0.714 | 0.917 | – | 0.968 | 21 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 3 |

### comment tag:zero_mentions_suspicious

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.800 | – | – | – | – | 1.0 | – | – | 0.667 | 23 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 5 |

### comment tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.024 | 0.986 | 0.933 | 0.727 | 0.889 | 1.0 | 0.846 | 0.973 | 1.0 | 0.972 | 200 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.947 | 23 |

### thread draw:random

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.019 | 0.948 | 0.700 | 0.000 | 0.333 | 1.0 | 1.0 | 0.950 | 1.0 | 0.948 | 85 |

### thread draw:targeted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.064 | 0.944 | 0.800 | 1.0 | 0.857 | 0.989 | 1.0 | 1.0 | – | 0.968 | 169 |
| claude self-consistency (same_input) | 0.000 | 0.959 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.870 | 46 |

### thread holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.077 | 0.938 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | – | 0.968 | 41 |

### thread stratum:chunk_failure_dense

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.097 | 0.937 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | 0.983 | 40 |
| claude self-consistency (same_input) | 0.000 | 0.951 | – | – | – | 1.0 | 1.0 | 1.0 | – | 0.951 | 21 |

### thread stratum:chunk_misattached

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.043 | 0.917 | 0.800 | 1.0 | 1.0 | 1.0 | 1.0 | – | – | 0.846 | 75 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 0.615 | 25 |

### thread stratum:chunk_parent_outside

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.033 | 0.952 | 0.812 | 1.0 | 0.800 | 0.972 | 1.0 | – | – | 1.0 | 43 |

### thread stratum:chunk_title_names_place

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.071 | 0.943 | – | – | 1.0 | 1.0 | 1.0 | – | – | 0.917 | 36 |

### thread stratum:none

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.020 | 0.959 | 0.625 | 0.000 | 0.333 | 1.0 | 1.0 | 0.950 | 1.0 | 0.986 | 60 |

### thread tag:avoid_or_strong_negative

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.125 | 0.958 | 0.714 | 1.0 | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 13 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | – | 1.0 | – | 1.0 | 2 |

### thread tag:chunk_failure_dense

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.078 | 0.946 | 0.812 | 1.0 | 0.800 | 0.976 | 1.0 | 1.0 | – | 0.989 | 65 |
| claude self-consistency (same_input) | 0.000 | 0.951 | – | – | – | 1.0 | 1.0 | 1.0 | – | 0.951 | 21 |

### thread tag:chunk_later

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.032 | 0.952 | 0.800 | 1.0 | 0.800 | 0.970 | 1.0 | – | – | 0.909 | 75 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 0.615 | 25 |

### thread tag:chunk_misattached

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.043 | 0.917 | 0.800 | 1.0 | 1.0 | 1.0 | 1.0 | – | – | 0.846 | 75 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 0.615 | 25 |

### thread tag:chunk_never_extracted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.053 | 0.947 | 0.727 | 0.500 | 0.750 | 0.988 | 1.0 | 1.0 | 1.0 | 0.969 | 125 |

### thread tag:chunk_parent_outside

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.024 | 0.944 | 0.810 | 1.0 | 0.800 | 0.977 | 1.0 | – | – | 0.927 | 93 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 0.615 | 25 |

### thread tag:chunk_title_names_place

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.056 | 0.953 | 0.667 | 1.0 | 1.0 | 1.0 | 1.0 | – | – | 0.911 | 61 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 0.615 | 25 |

### thread tag:deep_chain_context_gap

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | 0.000 | – | – | 1.0 | – | – | – | 1.0 | 7 |
| claude self-consistency (same_input) | – | – | – | – | – | – | – | – | – | – | 2 |

### thread tag:dish_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | 1.0 | – | 0.500 | 1.0 | – | – | – | 1.0 | 2 |

### thread tag:extracted_no_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.136 | 0.818 | 0.667 | 1.0 | – | 1.0 | 1.0 | – | – | 0.947 | 74 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 0.636 | 29 |

### thread tag:long_list

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | – | – | – | 1.0 | – | 1.0 | – | 1.0 | 6 |
| claude self-consistency (same_input) | 0.000 | 0.923 | – | – | – | 1.0 | – | 1.0 | – | 0.923 | 4 |

### thread tag:mixed_prompt_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 0.982 | 1.0 | – | 0.500 | 1.0 | 1.0 | 0.971 | – | 0.982 | 28 |
| claude self-consistency (same_input) | 0.000 | 0.947 | – | – | – | 1.0 | 1.0 | 1.0 | – | 0.947 | 13 |

### thread tag:neg_wording_nonneg_score

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | – | 1.0 | 2 |

### thread tag:never_extracted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.053 | 0.947 | 0.727 | 0.500 | 0.750 | 0.988 | 1.0 | 1.0 | 1.0 | 0.969 | 125 |

### thread tag:original_thread_prompt

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.027 | 0.935 | 0.857 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.915 | 87 |
| claude self-consistency (same_input) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 0.615 | 25 |

### thread tag:price_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | – | – | – | 1.0 | 2 |

### thread tag:question_or_unvisited

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | – | – | – | 1.0 | – | – | – | 1.0 | 2 |
| claude self-consistency (same_input) | – | – | – | – | – | – | – | – | – | – | 1 |

### thread tag:reply_ancestor_named

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.250 | 0.765 | 0.000 | – | – | 1.0 | 1.0 | – | – | 1.0 | 28 |
| claude self-consistency (same_input) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 9 |

### thread tag:short_opinion_reply

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.111 | 0.909 | 0.600 | – | 1.0 | 1.0 | 1.0 | – | – | 0.769 | 16 |
| claude self-consistency (same_input) | – | – | – | – | – | – | – | – | – | – | 2 |

### thread tag:stuck_default_with_opinion

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | – | – | – | 1.0 | – | 1.0 | – | 1.0 | 6 |
| claude self-consistency (same_input) | 0.000 | 0.917 | – | – | – | 1.0 | – | 1.0 | – | 0.917 | 5 |

### thread tag:zero_mentions_suspicious

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | – | – | – | 1.0 | – | – | – | 1.0 | 5 |
| claude self-consistency (same_input) | – | – | – | – | – | – | – | – | – | – | 3 |

### thread tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.044 | 0.946 | 0.759 | 0.667 | 0.667 | 0.990 | 1.0 | 0.977 | 1.0 | 0.960 | 213 |
| claude self-consistency (same_input) | 0.000 | 0.959 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.870 | 46 |

## Claude vs v1 hand gold (overlap items)

| drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.087 | 0.955 | 0.800 | 0.000 | 1.0 | 0.947 | 0.000 | 0.950 | – | 0.894 | 50 |

