# production__stored__all

mode: stored; reps: 1; labeled comments not in run: 0
calls 769, errors 0, invalid JSON 0, cost $0.0000, tokens 0 in / 0 out, latency p50 0.0s p90 0.0s

## Headline (owner priorities, in order)

| metric | overall | reweighted | single_comments | random | threads |
|---|---|---|---|---|---|
| a. comment drop rate (lower is better) | 0.358 | 0.230 | 0.258 | 0.213 | 0.486 |
| b. mention recall | 0.663 | 0.733 | 0.744 | 0.733 | 0.490 |
| c. negative-mention recall | 0.539 | 0.464 | 0.551 | 0.429 | 0.514 |
| d. value-complaint recall | 0.556 | 0.490 | 0.467 | 0.500 | 1.0 |
| e. dish-negative recall | n/a | n/a | n/a | n/a | n/a |
| f. sign accuracy | 0.986 | 0.972 | 0.982 | 0.966 | 1.0 |
| f. aspect levels used (of 7) | 7 | – | 7 | 5 | 6 |

## Everything else

| metric | overall | reweighted | single_comments | random | threads |
|---|---|---|---|---|---|
| comments | 769 | 198003.0 | 395 | 100 | 374 |
| mention_precision | 0.958 | 0.983 | 0.985 | 0.982 | 0.880 |
| mention_f1 | 0.784 | 0.840 | 0.848 | 0.840 | 0.630 |
| fn_model_error | 215 | 41470.464 | 108 | 19 | 107 |
| fn_context_gap | 6 | 2398.548 | 6 | 1 | 0 |
| neg_miss_model_error | 52 | 15068.175 | 34 | 8 | 18 |
| neg_miss_context_gap | 1 | 182.792 | 1 | 0 | 0 |
| negative_to_positive_rate | 0.035 | 0.115 | 0.051 | 0.143 | 0.000 |
| negative_softened_rate | 0.066 | 0.099 | 0.091 | 0.100 | 0.000 |
| reference_mention_recall | 0.648 | 0.723 | 0.694 | 0.750 | 0.474 |
| closed_mention_recall | 0.923 | 0.975 | 0.917 | 1.0 | 1.0 |
| search_terms_recall | 0.306 | 0.353 | 0.290 | 0.379 | 0.369 |
| expensiveness_presence_f1 | 0.830 | 0.760 | 0.765 | 0.750 | 0.947 |
| expensiveness_exact_acc | 0.591 | 0.679 | 0.692 | 0.667 | 0.444 |
| expensiveness_within1_acc | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| food_presence_f1 | 0.966 | 0.959 | 0.967 | 0.953 | 0.966 |
| food_exact_acc | 0.919 | 0.885 | 0.920 | 0.854 | 0.917 |
| food_mae_levels | 0.205 | 0.231 | 0.204 | 0.254 | 0.206 |
| food_spearman | 0.877 | – | 0.874 | 0.901 | 0.892 |
| food_distinct_values | 14 | – | 14 | 6 | 7 |
| food_share_0.3_or_0.6 | 0.816 | – | 0.821 | 0.750 | 0.798 |
| is_negated_acc | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| is_negated_recall | 1.0 | 1.0 | 1.0 | – | – |
| is_firsthand_acc | 0.943 | 0.972 | 0.931 | 1.0 | 0.979 |
| sign_err_model_error | 6 | 3432.137 | 6 | 2 | 0 |
| sign_err_context_gap | 0 | 0 | 0 | 0 | 0 |
| neg_mention_n | 115 | 28479.342 | 78 | 14 | 37 |
| vc_n | 18 | 7450.625 | 15 | 4 | 3 |
| dishneg_n | 31 | 1907.551 | 18 | 0 | 13 |

food values (rep 0, overall): 0.3:208, 0.6:97, -0.3:20, -0.6:18, 1.0:11, -0.5:4
aspect level histogram (rep 0, overall): -3:3 -2:52 -1:25 +0:2 +1:217 +2:126 +3:15

## By group

| metric | ambiguous_name | avoid_list_negation | deep_chain | long_list | messy_text | nameless_reply | out_of_scope | strong_negative | thread_long | thread_title_names_place | thread_where_to_eat | zero_mentions_suspicious |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| drop_rate | 0.000 | 0.214 | 0.467 | 0.059 | 0.053 | 0.333 | 0.071 | 0.316 | 0.484 | 0.676 | 0.385 | 1.0 |
| mention_recall | 0.862 | 0.761 | 0.571 | 0.809 | 0.508 | 0.615 | 0.842 | 0.696 | 0.427 | 0.307 | 0.515 | 0.000 |
| negative_mention_recall | 0.800 | 0.667 | 0.200 | 0.667 | 0.667 | 1.0 | 0.750 | 0.714 | 0.412 | 0.440 | 0.500 | 0.000 |
| value_complaint_recall | 0.333 | 0.500 | – | 0.000 | 0.667 | – | 1.0 | – | 1.0 | 1.0 | 1.0 | 0.000 |
| dish_negative_recall | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sign_accuracy | 0.981 | 0.979 | 1.0 | 0.986 | 0.963 | 1.0 | 1.0 | 0.941 | 1.0 | 1.0 | 1.0 | – |
| levels_used | 5 | 5 | 4 | 6 | 5 | 4 | 4 | 4 | 6 | 5 | 5 | – |
| comments | 28 | 39 | 30 | 38 | 38 | 43 | 32 | 35 | 201 | 176 | 174 | 70 |
| mention_precision | 1.0 | 0.972 | 1.0 | 0.988 | 0.970 | 1.0 | 0.970 | 1.0 | 0.772 | 0.796 | 0.855 | – |
| fn_model_error | 8 | 11 | 8 | 37 | 31 | 9 | 6 | 7 | 59 | 88 | 50 | 19 |
| fn_context_gap | 0 | 0 | 1 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 2 |
