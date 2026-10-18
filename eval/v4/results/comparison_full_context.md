# v4 comparison, reference = full_context labels

Reference: 504 comments, 370 with a required mention. 'weighted' is re-weighted to real traffic; ceilings are Claude against itself. score.py's scorer fixes: on.

## comment weighted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.029 | 0.973 | 1.0 | 1.0 | – | 1.0 | 1.0 | 22 |
| claude same_input vs full_context | 0.023 | 0.983 | 0.940 | 0.972 | 0.911 | 0.998 | 0.992 | 200 |

## comment

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.053 | 0.960 | 1.0 | 1.0 | – | 1.0 | 0.960 | 25 |
| claude same_input vs full_context | 0.059 | 0.958 | 0.928 | 0.867 | 0.826 | 0.992 | 0.971 | 250 |

## comment weighted tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.030 | 0.972 | 1.0 | 1.0 | – | 1.0 | 1.0 | 20 |
| claude same_input vs full_context | 0.018 | 0.985 | 0.934 | 0.971 | 1.0 | 0.998 | 0.990 | 160 |

## comment weighted holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 2 |
| claude same_input vs full_context | 0.042 | 0.972 | 0.978 | 1.0 | 0.614 | 0.994 | 1.0 | 40 |

## thread weighted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.016 | 0.989 | 1.0 | 1.0 | – | 1.0 | 1.0 | 46 |
| claude same_input vs full_context | 0.020 | 0.985 | 0.916 | 0.677 | 0.807 | 0.992 | 0.997 | 254 |

## thread

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.030 | 0.983 | 1.0 | 1.0 | – | 1.0 | 1.0 | 46 |
| claude same_input vs full_context | 0.022 | 0.985 | 0.915 | 0.750 | 0.923 | 0.986 | 0.996 | 254 |

## thread weighted tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.016 | 0.989 | 1.0 | 1.0 | – | 1.0 | 1.0 | 46 |
| claude same_input vs full_context | 0.022 | 0.984 | 0.936 | 0.657 | 0.778 | 0.998 | 0.997 | 213 |

## thread weighted holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.000 | 1.0 | 0.335 | 1.0 | 1.0 | 0.898 | 1.0 | 41 |

## By draw, stratum and heuristic

### comment draw:overlap_v1

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 0.500 | 3 |
| claude same_input vs full_context | 0.103 | 0.902 | 1.0 | – | 1.0 | 1.0 | 0.885 | 50 |

### comment draw:random

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 2 |
| claude same_input vs full_context | 0.064 | 0.961 | 0.750 | 1.0 | 1.0 | 1.0 | 0.980 | 60 |

### comment draw:targeted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.062 | 0.955 | 1.0 | 1.0 | – | 1.0 | 1.0 | 20 |
| claude same_input vs full_context | 0.046 | 0.969 | 0.944 | 0.857 | 0.789 | 0.987 | 0.986 | 140 |

### comment holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 2 |
| claude same_input vs full_context | 0.073 | 0.947 | 0.917 | 1.0 | 0.556 | 0.986 | 0.947 | 50 |

### comment stratum:avoid_or_strong_negative

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 0.000 | 0.947 | 1.0 | 12 |

### comment stratum:deep_chain_context_gap

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 3 |
| claude same_input vs full_context | 0.364 | 0.714 | 0.667 | 1.0 | 1.0 | 1.0 | 1.0 | 17 |

### comment stratum:dish_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.071 | 0.964 | 0.857 | 0.500 | 0.769 | 0.973 | 1.0 | 14 |

### comment stratum:long_list

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | – | – | – | – | – | – | – | 1 |
| claude same_input vs full_context | 0.000 | 1.0 | – | – | – | 1.0 | 0.984 | 10 |

### comment stratum:neg_wording_nonneg_score

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.077 | 0.917 | 0.800 | – | 1.0 | 1.0 | 1.0 | 14 |

### comment stratum:none

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 1.0 | 1 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 44 |

### comment stratum:overlap_v1

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 0.500 | 3 |
| claude same_input vs full_context | 0.103 | 0.902 | 1.0 | – | 1.0 | 1.0 | 0.885 | 50 |

### comment stratum:price_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 3 |
| claude same_input vs full_context | 0.000 | 0.950 | 1.0 | 1.0 | 1.0 | 1.0 | 0.950 | 14 |

### comment stratum:question_or_unvisited

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.250 | 0.750 | – | – | – | 1.0 | 1.0 | 4 |
| claude same_input vs full_context | 0.071 | 0.955 | 1.0 | – | – | 1.0 | 1.0 | 14 |

### comment stratum:reply_ancestor_named

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 2 |
| claude same_input vs full_context | 0.050 | 0.913 | 0.750 | – | – | 1.0 | 0.955 | 24 |

### comment stratum:short_opinion_reply

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | – | – | – | – | – | – | – | 1 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 0.818 | 14 |

### comment stratum:stuck_default_with_opinion

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 13 |

### comment stratum:zero_mentions_suspicious

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 1.0 | 1 |
| claude same_input vs full_context | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 10 |

### comment tag:avoid_or_strong_negative

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 0.895 | 0.750 | 0.750 | 0.944 | 1.0 | 25 |

### comment tag:deep_chain_context_gap

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 3 |
| claude same_input vs full_context | 0.375 | 0.684 | 0.800 | 1.0 | 1.0 | 1.0 | 1.0 | 25 |

### comment tag:dish_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.071 | 0.964 | 0.857 | 0.500 | 0.769 | 0.973 | 1.0 | 14 |

### comment tag:extracted_no_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 0.833 | 8 |
| claude same_input vs full_context | 0.154 | 0.750 | 0.857 | 1.0 | 1.0 | 1.0 | 0.840 | 64 |

### comment tag:long_list

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 0.857 | 0.500 | 1.0 | 0.985 | 0.992 | 23 |

### comment tag:mixed_prompt_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 2 |

### comment tag:neg_wording_nonneg_score

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 1.0 | 2 |
| claude same_input vs full_context | 0.062 | 0.929 | 0.857 | – | 1.0 | 1.0 | 1.0 | 17 |

### comment tag:never_extracted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.125 | 0.909 | 1.0 | 1.0 | – | 1.0 | 1.0 | 10 |
| claude same_input vs full_context | 0.049 | 0.974 | 0.950 | 0.818 | 1.0 | 0.987 | 0.987 | 125 |

### comment tag:original_thread_prompt

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 0.917 | 14 |
| claude same_input vs full_context | 0.078 | 0.926 | 0.889 | 1.0 | 0.667 | 1.0 | 0.940 | 114 |

### comment tag:price_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 3 |
| claude same_input vs full_context | 0.000 | 0.957 | 1.0 | 0.889 | 1.0 | 1.0 | 0.957 | 16 |

### comment tag:question_or_unvisited

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.250 | 0.750 | – | – | – | 1.0 | 1.0 | 5 |
| claude same_input vs full_context | 0.067 | 0.957 | 1.0 | – | – | 1.0 | 1.0 | 17 |

### comment tag:reply_ancestor_named

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 0.800 | 6 |
| claude same_input vs full_context | 0.150 | 0.830 | 0.800 | – | 1.0 | 1.0 | 0.929 | 52 |

### comment tag:short_opinion_reply

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | – | – | – | – | – | – | – | 1 |
| claude same_input vs full_context | 0.000 | 1.0 | 0.889 | 1.0 | – | 1.0 | 0.905 | 24 |

### comment tag:stuck_default_with_opinion

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 3 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.953 | 21 |

### comment tag:zero_mentions_suspicious

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 0.750 | 5 |
| claude same_input vs full_context | 0.167 | 0.833 | – | – | – | 1.0 | 0.833 | 23 |

### comment tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.059 | 0.952 | 1.0 | 1.0 | – | 1.0 | 0.952 | 23 |
| claude same_input vs full_context | 0.056 | 0.961 | 0.930 | 0.857 | 1.0 | 0.993 | 0.977 | 200 |

### thread draw:random

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.018 | 0.988 | 0.933 | – | 0.667 | 1.0 | 1.0 | 85 |

### thread draw:targeted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.030 | 0.983 | 1.0 | 1.0 | – | 1.0 | 1.0 | 46 |
| claude same_input vs full_context | 0.023 | 0.983 | 0.906 | 0.750 | 1.0 | 0.979 | 0.994 | 169 |

### thread holdout

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.000 | 1.0 | 0.500 | 1.0 | 1.0 | 0.938 | 1.0 | 41 |

### thread stratum:chunk_failure_dense

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.059 | 0.977 | – | – | – | 1.0 | 1.0 | 21 |
| claude same_input vs full_context | 0.059 | 0.970 | 1.0 | 1.0 | – | 1.0 | 1.0 | 40 |

### thread stratum:chunk_misattached

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 25 |
| claude same_input vs full_context | 0.029 | 0.971 | 0.867 | 0.600 | 1.0 | 0.939 | 0.971 | 75 |

### thread stratum:chunk_parent_outside

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 0.977 | 1.0 | 43 |

### thread stratum:chunk_title_names_place

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.000 | 1.0 | 0.000 | – | 1.0 | 1.0 | 1.0 | 36 |

### thread stratum:none

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.020 | 0.986 | 0.917 | – | 0.667 | 1.0 | 1.0 | 60 |

### thread tag:avoid_or_strong_negative

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 0.000 | 1.0 | 1.0 | 13 |

### thread tag:chunk_failure_dense

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.059 | 0.977 | – | – | – | 1.0 | 1.0 | 21 |
| claude same_input vs full_context | 0.036 | 0.980 | 1.0 | 1.0 | 1.0 | 0.988 | 1.0 | 65 |

### thread tag:chunk_later

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 25 |
| claude same_input vs full_context | 0.023 | 0.982 | 0.967 | 0.714 | 1.0 | 0.981 | 0.982 | 75 |

### thread tag:chunk_misattached

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 25 |
| claude same_input vs full_context | 0.029 | 0.971 | 0.867 | 0.600 | 1.0 | 0.939 | 0.971 | 75 |

### thread tag:chunk_never_extracted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.000 | 1.0 | 0.897 | 1.0 | 0.909 | 0.973 | 1.0 | 125 |

### thread tag:chunk_parent_outside

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 25 |
| claude same_input vs full_context | 0.019 | 0.985 | 0.968 | 0.714 | 1.0 | 0.984 | 0.985 | 93 |

### thread tag:chunk_title_names_place

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 25 |
| claude same_input vs full_context | 0.020 | 0.982 | 0.833 | 0.600 | 1.0 | 1.0 | 0.982 | 61 |

### thread tag:deep_chain_context_gap

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | – | – | – | – | – | – | – | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 7 |

### thread tag:dish_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 2 |

### thread tag:extracted_no_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 29 |
| claude same_input vs full_context | 0.091 | 0.909 | 0.917 | 0.500 | – | 1.0 | 1.0 | 74 |

### thread tag:long_list

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 4 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 6 |

### thread tag:mixed_prompt_mentions

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.077 | 0.974 | – | – | – | 1.0 | 1.0 | 13 |
| claude same_input vs full_context | 0.037 | 0.982 | 1.0 | – | 1.0 | 1.0 | 1.0 | 28 |

### thread tag:neg_wording_nonneg_score

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.000 | 1.0 | – | – | 1.0 | 1.0 | 1.0 | 2 |

### thread tag:never_extracted

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.000 | 1.0 | 0.897 | 1.0 | 0.909 | 0.973 | 1.0 | 125 |

### thread tag:original_thread_prompt

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 25 |
| claude same_input vs full_context | 0.041 | 0.965 | 0.941 | 0.667 | – | 1.0 | 0.982 | 87 |

### thread tag:price_complaint

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 2 |

### thread tag:question_or_unvisited

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | – | 1.0 | 1 |
| claude same_input vs full_context | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 2 |

### thread tag:reply_ancestor_named

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 9 |
| claude same_input vs full_context | 0.050 | 0.952 | 1.0 | – | – | 1.0 | 1.0 | 28 |

### thread tag:short_opinion_reply

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | – | – | – | – | – | – | – | 2 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | 16 |

### thread tag:stuck_default_with_opinion

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | – | – | – | 1.0 | 1.0 | 5 |
| claude same_input vs full_context | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 6 |

### thread tag:zero_mentions_suspicious

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.000 | 1.0 | 1.0 | – | – | 1.0 | 1.0 | 3 |
| claude same_input vs full_context | 0.500 | 0.500 | 0.000 | – | – | 1.0 | 1.0 | 5 |

### thread tuning

| run | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|---|
| claude self-consistency (full_context) | 0.030 | 0.983 | 1.0 | 1.0 | – | 1.0 | 1.0 | 46 |
| claude same_input vs full_context | 0.025 | 0.982 | 0.953 | 0.714 | 0.909 | 0.995 | 0.996 | 213 |

## Claude vs v1 hand gold (overlap items)

| drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | mention_precision | comments |
|---|---|---|---|---|---|---|---|
| 0.000 | 1.0 | 1.0 | 0.000 | 1.0 | 1.0 | 0.957 | 50 |

