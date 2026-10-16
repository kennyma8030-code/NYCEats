# claude-haiku-5-5__0d75b20b5f83__comment__v5__v2

mode: comment; schema: old (adapted); reps used 1 of 1; labeled comments not in run: 0
calls 481, errors 0 (inputs refused for good: 0), parse failures 0.000, cost $0.1924 ($0.400 per 1k comments), latency p50 3.0s p90 5.8s
input tokens 1,429,219 (cache reads 1,304,953, cache writes 0; read share 0.913), output tokens 333,770
normalizer repairs per 100 mentions: 0.000 (none); bad thread ids: 0.000
Old-schema run, read through the adapter: reference_only is derived (every aspect null, no avoid) and bare endorsement is food 0.3 alone; see docs/schema_v5.md.

## Headline (owner priorities, in order)

| metric | overall | single_comments |
|---|---|---|
| a. comment drop rate (lower is better) | 0.057 | 0.057 |
| b. mention recall | 0.931 | 0.931 |
| c. negative-mention recall | 0.914 | 0.914 |
| d. value-complaint recall | 0.929 | 0.929 |
| e. dish-negative recall | n/a | n/a |
| f. sign accuracy | 0.984 | 0.984 |
| f. aspect levels used (of 7) | 7 | 7 |

## v5 fields

| metric | overall | single_comments |
|---|---|---|
| reference_only_precision | 0.862 | 0.862 |
| reference_only_recall | 0.644 | 0.644 |
| bare_endorsement_precision | 0.670 | 0.670 |
| bare_endorsement_recall | 0.867 | 0.867 |
| is_negated_precision | 0.881 | 0.881 |
| is_negated_recall | 1.0 | 1.0 |
| experience_acc | 0.560 | 0.560 |
| price_exact_acc | 1.0 | 1.0 |
| price_within1_acc | 1.0 | 1.0 |
| price_presence_f1 | 0.496 | 0.496 |
| dishes_liked_precision | n/a | n/a |
| dishes_liked_recall | n/a | n/a |
| dishes_disliked_precision | n/a | n/a |
| dishes_disliked_recall | n/a | n/a |
| dishes_any_recall | 0.818 | 0.818 |
| judgment_question_acc | 1.0 | 1.0 |

## Everything else

| metric | overall | single_comments |
|---|---|---|
| comments | 481 | 481 |
| mention_precision | 0.972 | 0.972 |
| mention_f1 | 0.951 | 0.951 |
| fn_model_error | 43 | 43 |
| fn_context_gap | 19 | 19 |
| neg_miss_model_error | 12 | 12 |
| neg_miss_context_gap | 9 | 9 |
| negative_to_positive_rate | 0.012 | 0.012 |
| negative_to_bare_rate | 0.000 | 0.000 |
| negative_softened_rate | 0.011 | 0.011 |
| reference_mention_recall | 0.895 | 0.895 |
| closed_mention_recall | 1.0 | 1.0 |
| closed_handled_rate | 0.515 | 0.515 |
| search_terms_recall | 0.701 | 0.701 |
| food_presence_f1 | 0.914 | 0.914 |
| food_exact_acc | 0.876 | 0.876 |
| food_within1_acc | 0.998 | 0.998 |
| food_mae_levels | 0.126 | 0.126 |
| value_presence_f1 | 0.794 | 0.794 |
| value_exact_acc | 0.759 | 0.759 |
| service_presence_f1 | 0.915 | 0.915 |
| atmosphere_presence_f1 | 0.852 | 0.852 |
| wait_presence_f1 | 0.881 | 0.881 |
| food_spearman | 0.905 | 0.905 |
| sign_err_model_error | 10 | 10 |
| sign_err_context_gap | 0 | 0 |
| neg_mention_n | 244 | 244 |
| vc_n | 28 | 28 |
| dishneg_n | 69 | 69 |
| jq_n | 1 | 1 |

experience confusion (gold>model, rep 0, overall): ate_there>ate_there:425 ate_there>secondhand:121 secondhand>ate_there:1 secondhand>secondhand:43 unclear>ate_there:58 unclear>secondhand:187
aspect level histogram (rep 0, overall): -3:17 -2:177 -1:109 +0:14 +1:47 +2:321 +3:25
stop reasons: end_turn:481

## By group

| metric | closed_place | context_gap | default_0.3 | dish_as_place | dropped_in_list | dropped_named_mention | dropped_nameless_reply | dropped_reference_mention | hallucinated_place | inferred_aspect | missed_dish_negative | missed_negative | missed_value_complaint | negation_scope | negative_softened_to_positive | softened_negative | split_dev | split_test | wrong_sign | wrong_target |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| drop_rate | 0.000 | 0.500 | 0.000 | 0.042 | 0.000 | 0.087 | 0.091 | 0.040 | 0.000 | 0.000 | 0.069 | 0.074 | 0.000 | 0.000 | 0.042 | 0.040 | 0.050 | 0.064 | 0.000 | 0.000 |
| mention_recall | 0.956 | 0.333 | 0.875 | 0.909 | 0.973 | 0.893 | 0.863 | 0.897 | 1.0 | 0.935 | 0.911 | 0.892 | 0.952 | 0.988 | 0.949 | 0.932 | 0.946 | 0.912 | 0.964 | 0.900 |
| negative_mention_recall | 1.0 | 0.000 | 0.714 | 0.875 | 0.846 | 0.923 | 0.826 | 1.0 | 1.0 | 0.750 | 0.900 | 0.847 | 0.875 | 1.0 | 0.952 | 0.964 | 0.942 | 0.887 | 1.0 | 0.875 |
| value_complaint_recall | 1.0 | – | 0.667 | 1.0 | 1.0 | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | 0.909 | 1.0 | 1.0 | 1.0 | 1.0 | 0.875 | 0.750 | 1.0 |
| dish_negative_recall | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sign_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.957 | 0.976 | 1.0 | 0.957 | 0.973 | 1.0 | 1.0 | 1.0 | 0.990 | 1.0 | 0.980 | 0.991 | 0.975 | 0.982 | 0.967 |
| levels_used | 5 | 1 | 5 | 6 | 6 | 5 | 7 | 5 | 4 | 6 | 6 | 6 | 5 | 5 | 4 | 5 | 7 | 7 | 6 | 6 |
| reference_only_recall | 0.733 | 0.000 | 0.625 | 0.000 | 0.800 | 1.0 | 0.333 | 0.690 | 0.667 | 0.571 | – | 0.500 | 0.222 | 0.667 | 0.250 | 0.000 | 0.628 | 0.659 | 0.200 | 0.000 |
| bare_endorsement_recall | 0.667 | – | 0.750 | 1.0 | 0.893 | 0.000 | 0.400 | 1.0 | 1.0 | 0.667 | 0.500 | 0.286 | – | 0.886 | 1.0 | – | 0.904 | 0.806 | 1.0 | – |
| comments | 25 | 25 | 25 | 25 | 25 | 25 | 143 | 25 | 25 | 25 | 29 | 54 | 25 | 25 | 25 | 25 | 246 | 235 | 25 | 25 |
| mention_precision | 0.956 | 0.667 | 0.961 | 1.0 | 0.991 | 0.962 | 0.980 | 0.959 | 0.900 | 1.0 | 0.932 | 0.985 | 1.0 | 0.994 | 1.0 | 1.0 | 0.979 | 0.963 | 0.947 | 0.931 |
| fn_model_error | 2 | 1 | 6 | 2 | 3 | 3 | 14 | 8 | 0 | 3 | 3 | 3 | 2 | 2 | 2 | 2 | 21 | 22 | 2 | 3 |
| fn_context_gap | 0 | 7 | 1 | 1 | 0 | 0 | 9 | 0 | 0 | 0 | 1 | 5 | 0 | 0 | 1 | 1 | 6 | 13 | 0 | 0 |
