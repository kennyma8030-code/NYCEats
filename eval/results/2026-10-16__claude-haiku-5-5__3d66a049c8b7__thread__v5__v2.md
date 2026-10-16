# claude-haiku-5-5__3d66a049c8b7__thread__v5__v2

mode: thread; schema: v5; reps used 1 of 1; labeled comments not in run: 0
calls 355, errors 0 (inputs refused for good: 0), parse failures 0.031, cost $1.4209 ($0.193 per 1k comments), latency p50 27.8s p90 41.2s
input tokens 3,363,794 (cache reads 2,835,740, cache writes 0; read share 0.843), output tokens 2,679,508
normalizer repairs per 100 mentions: 0.861 (dishes_disliked_missing:96, extra_key:4, reference_with_aspects:3, dish_in_two_lists:1, aspect_null_string:1); bad thread ids: 0.000

## Headline (owner priorities, in order)

| metric | overall | single_comments |
|---|---|---|
| a. comment drop rate (lower is better) | 0.079 | 0.079 |
| b. mention recall | 0.816 | 0.816 |
| c. negative-mention recall | 0.709 | 0.709 |
| d. value-complaint recall | 0.679 | 0.679 |
| e. dish-negative recall | 0.522 | 0.522 |
| f. sign accuracy | 0.972 | 0.972 |
| f. aspect levels used (of 7) | 7 | 7 |

## v5 fields

| metric | overall | single_comments |
|---|---|---|
| reference_only_precision | 0.596 | 0.596 |
| reference_only_recall | 0.793 | 0.793 |
| bare_endorsement_precision | 0.727 | 0.727 |
| bare_endorsement_recall | 0.908 | 0.908 |
| is_negated_precision | 0.893 | 0.893 |
| is_negated_recall | 0.926 | 0.926 |
| experience_acc | 0.752 | 0.752 |
| price_exact_acc | 1.0 | 1.0 |
| price_within1_acc | 1.0 | 1.0 |
| price_presence_f1 | 0.667 | 0.667 |
| dishes_liked_precision | 0.892 | 0.892 |
| dishes_liked_recall | 0.719 | 0.719 |
| dishes_disliked_precision | 0.818 | 0.818 |
| dishes_disliked_recall | 0.581 | 0.581 |
| dishes_any_recall | 0.789 | 0.789 |
| judgment_question_acc | 1.0 | 1.0 |

## Everything else

| metric | overall | single_comments |
|---|---|---|
| comments | 481 | 481 |
| mention_precision | 0.958 | 0.958 |
| mention_f1 | 0.881 | 0.881 |
| fn_model_error | 155 | 155 |
| fn_context_gap | 11 | 11 |
| neg_miss_model_error | 66 | 66 |
| neg_miss_context_gap | 5 | 5 |
| negative_to_positive_rate | 0.053 | 0.053 |
| negative_to_bare_rate | 0.008 | 0.008 |
| negative_softened_rate | 0.029 | 0.029 |
| reference_mention_recall | 0.842 | 0.842 |
| closed_mention_recall | 0.909 | 0.909 |
| closed_handled_rate | 0.364 | 0.364 |
| search_terms_recall | 0.394 | 0.394 |
| food_presence_f1 | 0.928 | 0.928 |
| food_exact_acc | 0.878 | 0.878 |
| food_within1_acc | 0.987 | 0.987 |
| food_mae_levels | 0.140 | 0.140 |
| value_presence_f1 | 0.849 | 0.849 |
| value_exact_acc | 0.806 | 0.806 |
| service_presence_f1 | 0.829 | 0.829 |
| atmosphere_presence_f1 | 0.833 | 0.833 |
| wait_presence_f1 | 0.847 | 0.847 |
| food_spearman | 0.899 | 0.899 |
| sign_err_model_error | 14 | 14 |
| sign_err_context_gap | 0 | 0 |
| neg_mention_n | 244 | 244 |
| vc_n | 28 | 28 |
| dishneg_n | 69 | 69 |
| jq_n | 1 | 1 |

experience confusion (gold>model, rep 0, overall): ate_there>ate_there:352 ate_there>secondhand:5 ate_there>unclear:139 secondhand>secondhand:15 secondhand>unclear:25 unclear>ate_there:11 unclear>secondhand:1 unclear>unclear:183
aspect level histogram (rep 0, overall): -3:20 -2:121 -1:71 +0:15 +1:22 +2:245 +3:31
stop reasons: end_turn:344, max_tokens:11

## By group

| metric | closed_place | context_gap | default_0.3 | dish_as_place | dropped_in_list | dropped_named_mention | dropped_nameless_reply | dropped_reference_mention | hallucinated_place | inferred_aspect | missed_dish_negative | missed_negative | missed_value_complaint | negation_scope | negative_softened_to_positive | softened_negative | split_dev | split_test | wrong_sign | wrong_target |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| drop_rate | 0.000 | 0.417 | 0.000 | 0.042 | 0.042 | 0.217 | 0.091 | 0.120 | 0.000 | 0.040 | 0.034 | 0.130 | 0.083 | 0.208 | 0.000 | 0.040 | 0.077 | 0.082 | 0.000 | 0.000 |
| mention_recall | 0.889 | 0.333 | 0.964 | 0.909 | 0.673 | 0.786 | 0.887 | 0.731 | 0.956 | 0.891 | 0.889 | 0.811 | 0.857 | 0.577 | 1.0 | 0.909 | 0.787 | 0.852 | 0.929 | 0.900 |
| negative_mention_recall | 0.667 | 0.000 | 0.429 | 0.625 | 0.462 | 0.615 | 0.609 | 0.667 | 0.857 | 0.583 | 0.867 | 0.576 | 0.500 | 0.596 | 0.857 | 0.857 | 0.675 | 0.742 | 0.926 | 0.625 |
| value_complaint_recall | 0.000 | – | 0.333 | 1.0 | 0.000 | 1.0 | 0.750 | – | 1.0 | 0.500 | 0.833 | 0.714 | 0.545 | 0.000 | 0.667 | 0.800 | 0.750 | 0.625 | 0.500 | 0.500 |
| dish_negative_recall | 1.0 | 0.000 | – | 0.800 | 0.000 | 0.333 | 0.600 | – | 0.000 | 0.000 | 0.457 | 0.375 | 0.250 | 1.0 | 0.600 | 0.600 | 0.625 | 0.432 | 0.429 | 0.750 |
| sign_accuracy | 1.0 | 1.0 | 0.947 | 0.905 | 1.0 | 1.0 | 0.963 | 0.923 | 1.0 | 0.920 | 1.0 | 0.956 | 0.939 | 0.962 | 0.977 | 0.978 | 0.980 | 0.964 | 0.982 | 1.0 |
| levels_used | 6 | 1 | 6 | 6 | 6 | 5 | 7 | 3 | 6 | 6 | 7 | 6 | 4 | 6 | 6 | 6 | 7 | 7 | 7 | 6 |
| reference_only_recall | 0.667 | 1.0 | 0.600 | 0.500 | 0.889 | 1.0 | 1.0 | 0.929 | 0.667 | 0.714 | – | 0.500 | 0.750 | 1.0 | 0.500 | 0.000 | 0.732 | 0.854 | 0.250 | 1.0 |
| bare_endorsement_recall | 1.0 | – | 0.889 | 1.0 | 0.950 | 0.000 | 0.556 | 1.0 | 1.0 | 0.667 | 0.000 | 0.857 | – | 0.967 | 1.0 | – | 0.939 | 0.870 | 0.000 | – |
| comments | 25 | 25 | 25 | 25 | 25 | 25 | 143 | 25 | 25 | 25 | 29 | 54 | 25 | 25 | 25 | 25 | 246 | 235 | 25 | 25 |
| mention_precision | 0.952 | 0.571 | 0.982 | 0.968 | 0.987 | 0.917 | 0.980 | 1.0 | 0.843 | 0.976 | 0.952 | 0.984 | 1.0 | 0.979 | 0.983 | 1.0 | 0.966 | 0.950 | 0.929 | 0.900 |
| fn_model_error | 5 | 1 | 2 | 1 | 36 | 6 | 19 | 21 | 2 | 4 | 5 | 14 | 5 | 69 | 0 | 4 | 101 | 54 | 4 | 3 |
| fn_context_gap | 0 | 7 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 6 | 5 | 0 | 0 |
