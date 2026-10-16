# claude-haiku-5-5__c1f7f3456699__comment__v5__v2

mode: comment; schema: v5; reps used 1 of 1; labeled comments not in run: 0
calls 481, errors 0 (inputs refused for good: 0), parse failures 0.000, cost $0.2777 ($0.577 per 1k comments), latency p50 3.7s p90 6.8s
input tokens 4,784,675 (cache reads 4,660,409, cache writes 0; read share 0.974), output tokens 437,418
normalizer repairs per 100 mentions: 0.145 (dishes_disliked_missing:2); bad thread ids: 0.000

## Headline (owner priorities, in order)

| metric | overall | single_comments |
|---|---|---|
| a. comment drop rate (lower is better) | 0.041 | 0.041 |
| b. mention recall | 0.947 | 0.947 |
| c. negative-mention recall | 0.820 | 0.820 |
| d. value-complaint recall | 0.786 | 0.786 |
| e. dish-negative recall | 0.609 | 0.609 |
| f. sign accuracy | 0.976 | 0.976 |
| f. aspect levels used (of 7) | 7 | 7 |

## v5 fields

| metric | overall | single_comments |
|---|---|---|
| reference_only_precision | 0.622 | 0.622 |
| reference_only_recall | 0.804 | 0.804 |
| bare_endorsement_precision | 0.741 | 0.741 |
| bare_endorsement_recall | 0.946 | 0.946 |
| is_negated_precision | 0.902 | 0.902 |
| is_negated_recall | 1.0 | 1.0 |
| experience_acc | 0.829 | 0.829 |
| price_exact_acc | 1.0 | 1.0 |
| price_within1_acc | 1.0 | 1.0 |
| price_presence_f1 | 0.677 | 0.677 |
| dishes_liked_precision | 0.878 | 0.878 |
| dishes_liked_recall | 0.839 | 0.839 |
| dishes_disliked_precision | 0.792 | 0.792 |
| dishes_disliked_recall | 0.677 | 0.677 |
| dishes_any_recall | 0.854 | 0.854 |
| judgment_question_acc | 1.0 | 1.0 |

## Everything else

| metric | overall | single_comments |
|---|---|---|
| comments | 481 | 481 |
| mention_precision | 0.957 | 0.957 |
| mention_f1 | 0.952 | 0.952 |
| fn_model_error | 29 | 29 |
| fn_context_gap | 19 | 19 |
| neg_miss_model_error | 35 | 35 |
| neg_miss_context_gap | 9 | 9 |
| negative_to_positive_rate | 0.041 | 0.041 |
| negative_to_bare_rate | 0.008 | 0.008 |
| negative_softened_rate | 0.030 | 0.030 |
| reference_mention_recall | 0.947 | 0.947 |
| closed_mention_recall | 0.970 | 0.970 |
| closed_handled_rate | 0.515 | 0.515 |
| search_terms_recall | 0.508 | 0.508 |
| food_presence_f1 | 0.941 | 0.941 |
| food_exact_acc | 0.884 | 0.884 |
| food_within1_acc | 0.989 | 0.989 |
| food_mae_levels | 0.130 | 0.130 |
| value_presence_f1 | 0.874 | 0.874 |
| value_exact_acc | 0.763 | 0.763 |
| service_presence_f1 | 0.875 | 0.875 |
| atmosphere_presence_f1 | 0.829 | 0.829 |
| wait_presence_f1 | 0.837 | 0.837 |
| food_spearman | 0.901 | 0.901 |
| sign_err_model_error | 14 | 14 |
| sign_err_context_gap | 0 | 0 |
| neg_mention_n | 244 | 244 |
| vc_n | 28 | 28 |
| dishneg_n | 69 | 69 |
| jq_n | 1 | 1 |

experience confusion (gold>model, rep 0, overall): ate_there>ate_there:441 ate_there>secondhand:5 ate_there>unclear:105 secondhand>secondhand:23 secondhand>unclear:23 unclear>ate_there:11 unclear>secondhand:1 unclear>unclear:239
aspect level histogram (rep 0, overall): -3:21 -2:141 -1:85 +0:21 +1:26 +2:270 +3:34
stop reasons: end_turn:481

## By group

| metric | closed_place | context_gap | default_0.3 | dish_as_place | dropped_in_list | dropped_named_mention | dropped_nameless_reply | dropped_reference_mention | hallucinated_place | inferred_aspect | missed_dish_negative | missed_negative | missed_value_complaint | negation_scope | negative_softened_to_positive | softened_negative | split_dev | split_test | wrong_sign | wrong_target |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| drop_rate | 0.000 | 0.500 | 0.000 | 0.042 | 0.000 | 0.000 | 0.063 | 0.000 | 0.000 | 0.000 | 0.034 | 0.056 | 0.000 | 0.000 | 0.042 | 0.040 | 0.036 | 0.045 | 0.000 | 0.000 |
| mention_recall | 0.978 | 0.333 | 0.964 | 0.970 | 0.964 | 0.964 | 0.905 | 0.974 | 1.0 | 0.978 | 0.889 | 0.892 | 0.952 | 0.982 | 0.949 | 0.932 | 0.956 | 0.935 | 0.964 | 0.933 |
| negative_mention_recall | 0.667 | 0.000 | 0.429 | 0.625 | 0.692 | 0.846 | 0.630 | 1.0 | 1.0 | 0.667 | 0.833 | 0.661 | 0.625 | 0.936 | 0.857 | 0.893 | 0.817 | 0.823 | 0.926 | 0.625 |
| value_complaint_recall | 0.000 | – | 0.333 | 1.0 | 0.000 | 1.0 | 1.0 | – | 1.0 | 0.500 | 0.833 | 0.857 | 0.727 | 1.0 | 0.333 | 0.800 | 0.750 | 0.812 | 0.500 | 0.500 |
| dish_negative_recall | 1.0 | 0.000 | – | 0.800 | 1.0 | 0.333 | 0.800 | – | 0.000 | 0.000 | 0.543 | 0.750 | 0.750 | 0.500 | 0.800 | 0.800 | 0.781 | 0.459 | 0.429 | 1.0 |
| sign_accuracy | 1.0 | 1.0 | 0.941 | 0.864 | 0.984 | 1.0 | 0.991 | 1.0 | 0.950 | 0.962 | 0.917 | 0.981 | 0.932 | 0.976 | 1.0 | 1.0 | 0.970 | 0.982 | 0.982 | 0.968 |
| levels_used | 5 | 1 | 6 | 6 | 6 | 5 | 7 | 4 | 5 | 7 | 6 | 6 | 6 | 6 | 6 | 7 | 7 | 7 | 7 | 6 |
| reference_only_recall | 0.806 | 1.0 | 1.0 | 0.500 | 0.700 | 1.0 | 1.0 | 0.824 | 0.667 | 0.800 | – | 0.000 | 1.0 | 0.667 | 0.750 | 1.0 | 0.804 | 0.804 | 1.0 | 1.0 |
| bare_endorsement_recall | 1.0 | – | 0.941 | 1.0 | 0.964 | 0.000 | 0.222 | 1.0 | 1.0 | 0.667 | 1.0 | 0.429 | – | 0.986 | 1.0 | – | 0.961 | 0.921 | 1.0 | – |
| comments | 25 | 25 | 25 | 25 | 25 | 25 | 143 | 25 | 25 | 25 | 29 | 54 | 25 | 25 | 25 | 25 | 246 | 235 | 25 | 25 |
| mention_precision | 0.936 | 0.500 | 0.964 | 1.0 | 1.0 | 0.931 | 0.962 | 0.974 | 0.804 | 1.0 | 0.909 | 0.985 | 0.976 | 1.0 | 1.0 | 1.0 | 0.962 | 0.952 | 0.931 | 0.903 |
| fn_model_error | 1 | 1 | 1 | 0 | 4 | 1 | 7 | 2 | 0 | 1 | 4 | 3 | 2 | 3 | 2 | 2 | 16 | 13 | 2 | 2 |
| fn_context_gap | 0 | 7 | 1 | 1 | 0 | 0 | 9 | 0 | 0 | 0 | 1 | 5 | 0 | 0 | 1 | 1 | 6 | 13 | 0 | 0 |
