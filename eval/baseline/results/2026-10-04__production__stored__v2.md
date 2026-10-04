# production__stored__v2

mode: stored; reps: 1; labeled comments not in run: 0
calls 481, errors 0, invalid JSON 0, cost $0.0000, tokens 0 in / 0 out, latency p50 0.0s p90 0.0s

## Headline (owner priorities, in order)

| metric | overall | single_comments |
|---|---|---|
| a. comment drop rate (lower is better) | 0.384 | 0.384 |
| b. mention recall | 0.654 | 0.654 |
| c. negative-mention recall | 0.593 | 0.593 |
| d. value-complaint recall | 0.360 | 0.360 |
| e. dish-negative recall | n/a | n/a |
| f. sign accuracy | 0.961 | 0.961 |
| f. aspect levels used (of 7) | 7 | 7 |

## Everything else

| metric | overall | single_comments |
|---|---|---|
| comments | 481 | 481 |
| mention_precision | 0.891 | 0.891 |
| mention_f1 | 0.754 | 0.754 |
| fn_model_error | 288 | 288 |
| fn_context_gap | 13 | 13 |
| neg_miss_model_error | 80 | 80 |
| neg_miss_context_gap | 5 | 5 |
| negative_to_positive_rate | 0.072 | 0.072 |
| negative_softened_rate | 0.109 | 0.109 |
| reference_mention_recall | 0.625 | 0.625 |
| closed_mention_recall | 0.818 | 0.818 |
| search_terms_recall | 0.256 | 0.256 |
| expensiveness_presence_f1 | 0.786 | 0.786 |
| expensiveness_exact_acc | 0.576 | 0.576 |
| expensiveness_within1_acc | 0.970 | 0.970 |
| food_presence_f1 | 0.948 | 0.948 |
| food_exact_acc | 0.819 | 0.819 |
| food_mae_levels | 0.308 | 0.308 |
| food_spearman | 0.832 | 0.832 |
| food_distinct_values | 13 | 13 |
| food_share_0.3_or_0.6 | 0.739 | 0.739 |
| is_negated_acc | 0.994 | 0.994 |
| is_negated_recall | 0.969 | 0.969 |
| is_firsthand_acc | 0.916 | 0.916 |
| sign_err_model_error | 22 | 22 |
| sign_err_context_gap | 0 | 0 |
| neg_mention_n | 209 | 209 |
| vc_n | 25 | 25 |
| dishneg_n | 64 | 64 |

food values (rep 0, overall): 0.3:245, 0.6:123, -0.3:53, -0.6:28, 1.0:10, -0.5:10
aspect level histogram (rep 0, overall): -3:2 -2:101 -1:64 +0:3 +1:256 +2:186 +3:10

## By group

| metric | closed_place | context_gap | default_0.3 | dish_as_place | dropped_in_list | dropped_named_mention | dropped_nameless_reply | dropped_reference_mention | hallucinated_place | inferred_aspect | missed_dish_negative | missed_negative | missed_value_complaint | negation_scope | negative_softened_to_positive | softened_negative | split_dev | split_test | wrong_sign | wrong_target |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| drop_rate | 0.000 | 1.0 | 0.000 | 0.083 | 0.125 | 0.857 | 0.872 | 0.571 | 0.235 | 0.000 | 0.154 | 0.796 | 0.174 | 0.000 | 0.000 | 0.000 | 0.391 | 0.378 | 0.000 | 0.125 |
| mention_recall | 0.778 | 0.000 | 0.893 | 0.485 | 0.606 | 0.059 | 0.080 | 0.362 | 0.844 | 0.864 | 0.833 | 0.203 | 0.800 | 0.833 | 0.966 | 0.955 | 0.627 | 0.690 | 0.929 | 0.733 |
| negative_mention_recall | 0.333 | 0.000 | 0.286 | 0.250 | 0.556 | 0.000 | 0.000 | – | 0.429 | 0.700 | 0.852 | 0.040 | 0.214 | 0.794 | 0.650 | 0.889 | 0.543 | 0.644 | 0.870 | 0.375 |
| value_complaint_recall | 0.000 | – | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | – | 1.0 | 0.500 | 0.800 | 0.000 | 0.000 | 0.000 | 0.333 | 0.600 | 0.455 | 0.286 | 0.000 | 0.000 |
| dish_negative_recall | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sign_accuracy | 0.900 | – | 0.872 | 0.929 | 0.983 | 1.0 | 1.0 | 1.0 | 1.0 | 0.897 | 0.977 | 1.0 | 0.880 | 0.947 | 0.932 | 0.894 | 0.958 | 0.964 | 0.855 | 1.0 |
| levels_used | 4 | – | 5 | 4 | 6 | 1 | 2 | 2 | 4 | 4 | 5 | 3 | 5 | 6 | 5 | 5 | 7 | 7 | 7 | 5 |
| comments | 25 | 25 | 25 | 25 | 25 | 25 | 143 | 25 | 25 | 25 | 29 | 54 | 25 | 25 | 25 | 25 | 246 | 235 | 25 | 25 |
| mention_precision | 0.946 | – | 0.980 | 0.421 | 1.0 | 1.0 | 0.591 | 0.962 | 0.704 | 0.974 | 0.972 | 0.867 | 0.970 | 0.944 | 0.966 | 1.0 | 0.880 | 0.904 | 0.929 | 0.629 |
| fn_model_error | 10 | 3 | 6 | 15 | 41 | 16 | 150 | 44 | 7 | 5 | 7 | 51 | 7 | 27 | 2 | 2 | 177 | 111 | 4 | 8 |
| fn_context_gap | 0 | 9 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 6 | 7 | 0 | 0 |
