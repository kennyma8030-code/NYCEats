# v4 comparison, reference = full_context labels

Reference: 504 comments, 349 with a required mention. 'weighted' is re-weighted to real traffic; ceilings are Claude against itself.

## comment weighted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.026 | 0.980 | 0.870 | 0.824 | 0.725 | 1.0 | 0.956 | 0.983 | 1.0 | 0.984 | 200 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 1.0 | 22 |
| claude same_input vs full_context | 0.016 | 0.985 | 0.910 | 0.892 | 1.0 | 1.0 | 1.0 | 0.981 | 1.0 | 0.962 | 200 |

## comment

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.057 | 0.959 | 0.873 | 0.692 | 0.625 | 1.0 | 0.879 | 0.961 | 1.0 | 0.959 | 250 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 25 |
| claude same_input vs full_context | 0.040 | 0.970 | 0.945 | 0.923 | 1.0 | 1.0 | 1.0 | 0.976 | 1.0 | 0.957 | 250 |

## comment weighted tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.021 | 0.983 | 0.861 | 0.815 | 0.889 | 1.0 | 0.933 | 0.987 | 1.0 | 0.981 | 160 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 1.0 | 20 |
| claude same_input vs full_context | 0.016 | 0.988 | 0.894 | 0.886 | 1.0 | 1.0 | 1.0 | 0.988 | 1.0 | 0.956 | 160 |

## comment weighted holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.042 | 0.967 | 0.924 | 1.0 | 0.618 | 1.0 | 1.0 | 0.938 | 1.0 | 0.994 | 40 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.017 | 0.974 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.905 | 1.0 | 0.984 | 40 |

## thread weighted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.040 | 0.932 | 0.684 | 1.0 | 0.448 | 0.997 | 1.0 | 0.961 | 1.0 | 0.960 | 254 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.986 | 46 |
| claude same_input vs full_context | 0.021 | 0.978 | 0.922 | 1.0 | 0.763 | 1.0 | 1.0 | 0.990 | 1.0 | 0.981 | 254 |

## thread

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.069 | 0.907 | 0.667 | 1.0 | 0.667 | 0.992 | 1.0 | 0.979 | 1.0 | 0.949 | 254 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.980 | 46 |
| claude same_input vs full_context | 0.040 | 0.956 | 0.879 | 1.0 | 0.889 | 1.0 | 1.0 | 0.980 | 1.0 | 0.971 | 254 |

## thread weighted tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.037 | 0.932 | 0.681 | 1.0 | 0.448 | 0.997 | 1.0 | 0.961 | 1.0 | 0.959 | 213 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.986 | 46 |
| claude same_input vs full_context | 0.023 | 0.977 | 0.921 | 1.0 | 0.763 | 1.0 | 1.0 | 0.990 | 1.0 | 0.980 | 213 |

## thread weighted holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.080 | 0.928 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | 0.977 | 41 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 41 |

## By draw, stratum and heuristic

### comment draw:overlap_v1

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.115 | 0.917 | 1.0 | – | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 0.936 | 50 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | – | 1.0 | – | 1.0 | 3 |
| claude same_input vs full_context | 0.115 | 0.917 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.917 | 50 |

### comment draw:random

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.065 | 0.962 | 0.571 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.971 | 60 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.065 | 0.962 | 0.714 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.962 | 60 |

### comment draw:targeted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.038 | 0.968 | 0.907 | 0.667 | 0.714 | 1.0 | 0.840 | 0.898 | 1.0 | 0.959 | 140 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 1.0 | 20 |
| claude same_input vs full_context | 0.010 | 0.986 | 0.977 | 0.917 | 1.0 | 1.0 | 1.0 | 0.939 | 1.0 | 0.964 | 140 |

### comment holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.073 | 0.932 | 0.857 | 1.0 | 0.286 | 1.0 | 1.0 | 0.882 | 1.0 | 0.945 | 50 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.024 | 0.959 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.941 | 1.0 | 0.934 | 50 |

### comment stratum:avoid_or_strong_negative

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | 1.0 | 0.000 | 1.0 | 0.500 | 0.700 | 1.0 | 1.0 | 12 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.900 | 1.0 | 1.0 | 12 |

### comment stratum:deep_chain_context_gap

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.455 | 0.643 | 0.333 | 0.000 | 1.0 | 1.0 | 1.0 | – | – | 0.900 | 17 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 3 |
| claude same_input vs full_context | 0.364 | 0.714 | 0.333 | 0.000 | 1.0 | 1.0 | 1.0 | – | – | 1.0 | 17 |

### comment stratum:dish_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.071 | 0.964 | 1.0 | 0.667 | 0.700 | 1.0 | – | 1.0 | – | 1.0 | 14 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | – | 1.0 | – | 1.0 | 14 |

### comment stratum:long_list

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | – | – | – | – | – | 1.0 | – | 0.935 | 10 |
| claude self-consistency (full_context) | – | – | – | – | – | – | – | – | – | – | 1 |
| claude same_input vs full_context | 0.000 | 1.0 | – | – | – | 1.0 | – | 1.0 | – | 1.0 | 10 |

### comment stratum:neg_wording_nonneg_score

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.957 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | – | 0.957 | 14 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 0.957 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | – | 0.957 | 14 |

### comment stratum:none

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 44 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 1 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.967 | 44 |

### comment stratum:overlap_v1

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.115 | 0.917 | 1.0 | – | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 0.936 | 50 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | – | 1.0 | – | 1.0 | 3 |
| claude same_input vs full_context | 0.115 | 0.917 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.917 | 50 |

### comment stratum:price_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 0.857 | 0.833 | – | 1.0 | – | 1.0 | 1.0 | 1.0 | 14 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | – | – | – | 1.0 | 3 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | – | 1.0 | 1.0 | 0.947 | 14 |

### comment stratum:question_or_unvisited

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 0.857 | – | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 14 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 4 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | 0.952 | 14 |

### comment stratum:reply_ancestor_named

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.053 | 0.909 | 0.750 | – | – | 1.0 | 0.857 | 0.500 | – | 0.952 | 24 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 0.909 | 0.750 | – | – | 1.0 | 1.0 | 0.000 | – | 0.870 | 24 |

### comment stratum:short_opinion_reply

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.889 | 0.667 | – | – | 1.0 | – | 1.0 | – | 0.727 | 14 |
| claude self-consistency (full_context) | – | – | – | – | – | – | – | – | – | – | 1 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | – | 1.0 | – | 1.0 | – | 0.818 | 14 |

### comment stratum:stuck_default_with_opinion

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 0.000 | 0.000 | 1.0 | 1.0 | 0.500 | 0.909 | – | 1.0 | 13 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | – | 0.971 | 13 |

### comment stratum:zero_mentions_suspicious

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.500 | – | – | – | – | 1.0 | – | – | 0.333 | 10 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 1 |
| claude same_input vs full_context | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 0.667 | 10 |

### comment tag:avoid_or_strong_negative

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | 1.0 | 0.667 | 1.0 | 0.750 | 0.700 | 1.0 | 1.0 | 25 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.900 | 1.0 | 0.980 | 25 |

### comment tag:deep_chain_context_gap

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.438 | 0.632 | 0.600 | 0.000 | 1.0 | 1.0 | 1.0 | – | – | 0.923 | 25 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 3 |
| claude same_input vs full_context | 0.375 | 0.684 | 0.600 | 0.000 | 1.0 | 1.0 | 1.0 | – | – | 1.0 | 25 |

### comment tag:dish_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.071 | 0.964 | 1.0 | 0.667 | 0.700 | 1.0 | – | 1.0 | – | 1.0 | 14 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | – | 1.0 | – | 1.0 | 14 |

### comment tag:extracted_no_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.217 | 0.680 | 0.600 | 0.000 | 1.0 | 1.0 | 0.800 | 0.000 | 1.0 | 0.810 | 64 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | – | – | 1.0 | 8 |
| claude same_input vs full_context | 0.174 | 0.760 | 0.600 | 0.000 | 1.0 | 1.0 | 1.0 | 0.000 | 1.0 | 0.792 | 64 |

### comment tag:long_list

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 1.0 | 1.0 | 0.500 | 1.0 | – | 0.965 | 1.0 | 0.962 | 23 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | – | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 0.992 | 23 |

### comment tag:mixed_prompt_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | – | – | – | 1.0 | 0.333 | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 2 |

### comment tag:neg_wording_nonneg_score

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.963 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | – | 0.963 | 17 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 0.963 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | – | 0.963 | 17 |

### comment tag:never_extracted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.041 | 0.982 | 0.943 | 0.778 | 0.857 | 1.0 | 0.944 | 0.964 | 1.0 | 0.974 | 125 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 1.0 | 10 |
| claude same_input vs full_context | 0.031 | 0.982 | 0.971 | 1.0 | 1.0 | 1.0 | 1.0 | 0.976 | 1.0 | 0.970 | 125 |

### comment tag:original_thread_prompt

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.082 | 0.915 | 0.750 | 0.500 | 0.444 | 1.0 | 0.875 | 0.953 | 1.0 | 0.930 | 114 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 14 |
| claude same_input vs full_context | 0.055 | 0.946 | 0.900 | 0.750 | 1.0 | 1.0 | 1.0 | 0.977 | 1.0 | 0.932 | 114 |

### comment tag:price_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 0.900 | 0.750 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | 16 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | – | – | – | 1.0 | 3 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 0.955 | 16 |

### comment tag:question_or_unvisited

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 1.0 | 0.875 | – | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 17 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 5 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | 0.955 | 17 |

### comment tag:reply_ancestor_named

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.135 | 0.841 | 0.800 | – | 1.0 | 1.0 | 0.900 | 0.500 | 1.0 | 0.925 | 52 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | – | – | 1.0 | 6 |
| claude same_input vs full_context | 0.108 | 0.841 | 0.800 | – | 1.0 | 1.0 | 1.0 | 0.000 | 1.0 | 0.881 | 52 |

### comment tag:short_opinion_reply

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.941 | 0.857 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | 0.842 | 24 |
| claude self-consistency (full_context) | – | – | – | – | – | – | – | – | – | – | 1 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 0.750 | 1.0 | 0.895 | 24 |

### comment tag:stuck_default_with_opinion

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.000 | 0.983 | 0.333 | 0.000 | 1.0 | 1.0 | 0.714 | 0.957 | – | 0.952 | 21 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 3 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | – | 0.938 | 21 |

### comment tag:zero_mentions_suspicious

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.167 | 0.667 | – | – | – | – | 1.0 | – | – | 0.667 | 23 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 5 |
| claude same_input vs full_context | 0.167 | 0.833 | – | – | – | 1.0 | 1.0 | – | – | 0.714 | 23 |

### comment tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__c1f7f3456699__comment__v4 | 0.052 | 0.966 | 0.875 | 0.667 | 0.889 | 1.0 | 0.840 | 0.973 | 1.0 | 0.963 | 200 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 23 |
| claude same_input vs full_context | 0.044 | 0.973 | 0.938 | 0.917 | 1.0 | 1.0 | 1.0 | 0.982 | 1.0 | 0.963 | 200 |

### thread draw:random

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.036 | 0.924 | 0.700 | – | 0.333 | 1.0 | 1.0 | 0.950 | 1.0 | 0.948 | 85 |
| claude same_input vs full_context | 0.054 | 0.962 | 0.900 | – | 0.667 | 1.0 | 1.0 | 1.0 | 1.0 | 0.987 | 85 |

### thread draw:targeted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.085 | 0.899 | 0.652 | 1.0 | 0.833 | 0.989 | 1.0 | 1.0 | – | 0.950 | 169 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.980 | 46 |
| claude same_input vs full_context | 0.034 | 0.953 | 0.870 | 1.0 | 1.0 | 1.0 | 1.0 | 0.964 | – | 0.964 | 169 |

### thread holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.074 | 0.939 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | 0.969 | 41 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 41 |

### thread stratum:chunk_failure_dense

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.033 | 0.968 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | 0.984 | 40 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 1.0 | – | 0.975 | 21 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | 0.984 | 40 |

### thread stratum:chunk_misattached

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.138 | 0.759 | 0.571 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.786 | 75 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 25 |
| claude same_input vs full_context | 0.138 | 0.828 | 0.714 | 1.0 | – | 1.0 | 1.0 | 0.000 | – | 0.923 | 75 |

### thread stratum:chunk_parent_outside

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.032 | 0.864 | 0.667 | 1.0 | 0.800 | 0.971 | 1.0 | – | – | 0.927 | 43 |
| claude same_input vs full_context | 0.000 | 0.932 | 0.889 | 1.0 | 1.0 | 1.0 | 1.0 | – | – | 0.932 | 43 |

### thread stratum:chunk_title_names_place

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.152 | 0.875 | – | – | 1.0 | 1.0 | 1.0 | – | – | 0.972 | 36 |
| claude same_input vs full_context | 0.091 | 0.925 | – | – | 1.0 | 1.0 | 1.0 | – | – | 1.0 | 36 |

### thread stratum:none

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.020 | 0.959 | 0.714 | – | 0.333 | 1.0 | 1.0 | 0.950 | 1.0 | 0.986 | 60 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | 0.667 | 1.0 | 1.0 | 1.0 | 1.0 | 0.986 | 60 |

### thread tag:avoid_or_strong_negative

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.222 | 0.920 | 0.625 | 1.0 | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 13 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | – | 1.0 | – | 1.0 | 2 |
| claude same_input vs full_context | 0.111 | 0.960 | 0.875 | 1.0 | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 13 |

### thread tag:chunk_failure_dense

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.039 | 0.936 | 0.667 | 1.0 | 0.800 | 0.976 | 1.0 | 1.0 | – | 0.967 | 65 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 1.0 | – | 0.975 | 21 |
| claude same_input vs full_context | 0.000 | 0.979 | 0.889 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | – | 0.968 | 65 |

### thread tag:chunk_later

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.105 | 0.796 | 0.625 | 1.0 | 0.800 | 0.969 | 1.0 | 1.0 | – | 0.830 | 75 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 25 |
| claude same_input vs full_context | 0.105 | 0.857 | 0.833 | 1.0 | 1.0 | 1.0 | 1.0 | 0.000 | – | 0.913 | 75 |

### thread tag:chunk_misattached

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.138 | 0.759 | 0.571 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.786 | 75 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 25 |
| claude same_input vs full_context | 0.138 | 0.828 | 0.714 | 1.0 | – | 1.0 | 1.0 | 0.000 | – | 0.923 | 75 |

### thread tag:chunk_never_extracted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.079 | 0.906 | 0.652 | 1.0 | 0.714 | 0.988 | 1.0 | 1.0 | 1.0 | 0.969 | 125 |
| claude same_input vs full_context | 0.030 | 0.964 | 0.913 | 1.0 | 0.857 | 1.0 | 1.0 | 1.0 | 1.0 | 0.978 | 125 |

### thread tag:chunk_parent_outside

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.083 | 0.803 | 0.640 | 1.0 | 0.800 | 0.976 | 1.0 | 1.0 | – | 0.845 | 93 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 25 |
| claude same_input vs full_context | 0.083 | 0.869 | 0.840 | 1.0 | 1.0 | 1.0 | 1.0 | 0.000 | – | 0.914 | 93 |

### thread tag:chunk_title_names_place

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.159 | 0.843 | 0.500 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | – | 0.915 | 61 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 25 |
| claude same_input vs full_context | 0.091 | 0.902 | 0.750 | 1.0 | 1.0 | 1.0 | 1.0 | 0.000 | – | 0.958 | 61 |

### thread tag:deep_chain_context_gap

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | 0.000 | – | – | 1.0 | 1.0 | – | – | 1.0 | 7 |
| claude self-consistency (full_context) | – | – | – | – | – | – | – | – | – | – | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | – | – | 0.800 | 7 |

### thread tag:dish_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | 1.0 | – | 0.500 | 1.0 | – | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | – | 1.0 | 2 |

### thread tag:extracted_no_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.125 | 0.750 | 0.500 | 1.0 | – | 1.0 | 1.0 | – | – | 0.818 | 74 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | – | – | 0.889 | 29 |
| claude same_input vs full_context | 0.042 | 0.875 | 0.750 | 1.0 | – | 1.0 | 1.0 | – | – | 0.840 | 74 |

### thread tag:long_list

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | – | – | – | 1.0 | – | 1.0 | – | 1.0 | 6 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | – | 1.0 | – | 1.0 | 4 |
| claude same_input vs full_context | 0.000 | 1.0 | – | – | – | 1.0 | – | 1.0 | – | 1.0 | 6 |

### thread tag:mixed_prompt_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 0.982 | 1.0 | – | 0.500 | 1.0 | 1.0 | 0.971 | – | 0.982 | 28 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 13 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | – | 1.0 | 28 |

### thread tag:neg_wording_nonneg_score

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | – | – | 1.0 | 2 |

### thread tag:never_extracted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.079 | 0.906 | 0.652 | 1.0 | 0.714 | 0.988 | 1.0 | 1.0 | 1.0 | 0.969 | 125 |
| claude same_input vs full_context | 0.030 | 0.964 | 0.913 | 1.0 | 0.857 | 1.0 | 1.0 | 1.0 | 1.0 | 0.978 | 125 |

### thread tag:original_thread_prompt

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.091 | 0.827 | 0.667 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.860 | 87 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 1.0 | 25 |
| claude same_input vs full_context | 0.091 | 0.885 | 0.778 | 1.0 | – | 1.0 | 1.0 | 0.750 | – | 0.939 | 87 |

### thread tag:price_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | – | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | – | – | – | 1.0 | 2 |

### thread tag:question_or_unvisited

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | – | – | – | 1.0 | – | – | – | 1.0 | 2 |
| claude self-consistency (full_context) | – | – | – | – | – | – | – | – | – | – | 1 |
| claude same_input vs full_context | 0.000 | 1.0 | – | – | – | 1.0 | – | – | – | 1.0 | 2 |

### thread tag:reply_ancestor_named

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.188 | 0.824 | 0.000 | – | – | 1.0 | 1.0 | – | – | 1.0 | 28 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | – | – | 0.667 | 9 |
| claude same_input vs full_context | 0.062 | 0.941 | 0.500 | – | – | 1.0 | 1.0 | – | – | 0.889 | 28 |

### thread tag:short_opinion_reply

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.167 | 0.571 | 0.167 | – | 1.0 | 1.0 | 1.0 | – | – | 0.615 | 16 |
| claude self-consistency (full_context) | – | – | – | – | – | – | – | – | – | – | 2 |
| claude same_input vs full_context | 0.250 | 0.643 | 0.500 | – | 1.0 | 1.0 | 1.0 | – | – | 0.818 | 16 |

### thread tag:stuck_default_with_opinion

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.000 | 1.0 | – | – | – | 1.0 | – | 1.0 | – | 1.0 | 6 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | – | 1.0 | – | 1.0 | 5 |
| claude same_input vs full_context | 0.000 | 1.0 | – | – | – | 1.0 | – | 1.0 | – | 1.0 | 6 |

### thread tag:zero_mentions_suspicious

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.500 | 0.500 | – | – | – | 1.0 | – | – | – | 1.0 | 5 |
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 1.0 | – | – | 1.0 | 3 |
| claude same_input vs full_context | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | – | – | 1.0 | 5 |

### thread tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5__3d66a049c8b7__thread__v4 | 0.068 | 0.902 | 0.656 | 1.0 | 0.667 | 0.990 | 1.0 | 0.978 | 1.0 | 0.946 | 213 |
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | – | 0.980 | 46 |
| claude same_input vs full_context | 0.048 | 0.949 | 0.875 | 1.0 | 0.889 | 1.0 | 1.0 | 0.978 | 1.0 | 0.967 | 213 |

## Claude vs v1 hand gold (overlap items)

| drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | reference_only_recall | bare_endorsement_recall | is_negated_recall | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 1.0 | 0.800 | 0.000 | 1.0 | 0.944 | 0.000 | 0.950 | – | 0.978 | 50 |

