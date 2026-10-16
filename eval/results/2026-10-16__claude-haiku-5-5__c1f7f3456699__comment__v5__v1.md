# claude-haiku-5-5__c1f7f3456699__comment__v5__v1

mode: comment; schema: v5; reps used 1 of 1; labeled comments not in run: 0
calls 769, errors 0 (inputs refused for good: 0), parse failures 0.000, cost $0.3168 ($0.412 per 1k comments), latency p50 2.8s p90 5.0s
input tokens 7,624,314 (cache reads 7,441,152, cache writes 9,689; read share 0.976), output tokens 447,741
normalizer repairs per 100 mentions: 0.145 (dishes_disliked_missing:2); bad thread ids: 0.000

## Headline (owner priorities, in order)

| metric | overall | reweighted | single_comments | threads |
|---|---|---|---|---|
| a. comment drop rate (lower is better) | 0.031 | 0.035 | 0.047 | 0.011 |
| b. mention recall | 0.958 | 0.951 | 0.952 | 0.969 |
| c. negative-mention recall | 0.786 | 0.714 | 0.784 | 0.791 |
| d. value-complaint recall | 0.850 | 0.804 | 0.824 | 1.0 |
| e. dish-negative recall | 0.543 | 0.517 | 0.600 | 0.467 |
| f. sign accuracy | 0.987 | 0.995 | 0.985 | 0.992 |
| f. aspect levels used (of 7) | 7 | 7 | 7 | 7 |

## v5 fields

| metric | overall | reweighted | single_comments | threads |
|---|---|---|---|---|
| reference_only_precision | 0.554 | 0.573 | 0.627 | 0.452 |
| reference_only_recall | 0.862 | 0.920 | 0.841 | 0.905 |
| bare_endorsement_precision | 0.779 | 0.716 | 0.782 | 0.771 |
| bare_endorsement_recall | 0.934 | 0.923 | 0.929 | 0.949 |
| is_negated_precision | 0.714 | 0.627 | 0.667 | 1.0 |
| is_negated_recall | 1.0 | 1.0 | 1.0 | 1.0 |
| experience_acc | 0.860 | 0.820 | 0.878 | 0.826 |
| price_exact_acc | 1.0 | 1.0 | 1.0 | 1.0 |
| price_within1_acc | 1.0 | 1.0 | 1.0 | 1.0 |
| price_presence_f1 | 0.810 | 0.798 | 0.828 | 0.769 |
| dishes_liked_precision | 0.929 | 0.979 | 0.956 | 0.891 |
| dishes_liked_recall | 0.812 | 0.714 | 0.811 | 0.814 |
| dishes_disliked_precision | 0.864 | 0.859 | 0.857 | 0.875 |
| dishes_disliked_recall | 0.613 | 0.565 | 0.667 | 0.538 |
| dishes_any_recall | 0.830 | 0.831 | 0.846 | 0.806 |
| judgment_question_acc | 1.0 | 1.0 | 1.0 | – |

## Everything else

| metric | overall | reweighted | single_comments | threads |
|---|---|---|---|---|
| comments | 769 | 198003.0 | 395 | 374 |
| mention_precision | 0.908 | 0.941 | 0.950 | 0.833 |
| mention_f1 | 0.932 | 0.946 | 0.951 | 0.896 |
| fn_model_error | 13 | 2363.378 | 6 | 7 |
| fn_context_gap | 16 | 5976.558 | 16 | 0 |
| neg_miss_model_error | 21 | 7241.695 | 12 | 9 |
| neg_miss_context_gap | 7 | 2096.947 | 7 | 0 |
| negative_to_positive_rate | 0.015 | 0.006 | 0.011 | 0.023 |
| negative_to_bare_rate | 0.008 | 0.000 | 0.000 | 0.023 |
| negative_softened_rate | 0.009 | 0.003 | 0.012 | 0.000 |
| reference_mention_recall | 0.961 | 0.943 | 0.975 | 0.917 |
| closed_mention_recall | 1.0 | 1.0 | 1.0 | 1.0 |
| closed_handled_rate | 0.231 | 0.439 | 0.250 | 0.000 |
| search_terms_recall | 0.522 | 0.490 | 0.479 | 0.690 |
| food_presence_f1 | 0.955 | 0.930 | 0.960 | 0.945 |
| food_exact_acc | 0.943 | 0.943 | 0.942 | 0.946 |
| food_within1_acc | 0.994 | 0.999 | 0.995 | 0.991 |
| food_mae_levels | 0.063 | 0.059 | 0.063 | 0.063 |
| value_presence_f1 | 0.917 | 0.966 | 0.889 | 1.0 |
| value_exact_acc | 0.864 | 0.988 | 0.938 | 0.667 |
| service_presence_f1 | 0.919 | 1.0 | 1.0 | 0.571 |
| atmosphere_presence_f1 | 0.938 | 0.989 | 0.929 | 1.0 |
| wait_presence_f1 | 0.840 | 0.957 | 0.870 | 0.815 |
| food_spearman | 0.867 | 0.891 | 0.891 | 0.821 |
| sign_err_model_error | 5 | 466.914 | 4 | 1 |
| sign_err_context_gap | 0 | 0 | 0 | 0 |
| neg_mention_n | 131 | 32638.331 | 88 | 43 |
| vc_n | 20 | 9010.022 | 17 | 3 |
| dishneg_n | 35 | 2037.266 | 20 | 15 |
| jq_n | 1 | 181.417 | 1 | 0 |

experience confusion (gold>model, rep 0, overall): ate_there>ate_there:335 ate_there>secondhand:2 ate_there>unclear:51 secondhand>secondhand:21 secondhand>unclear:24 unclear>ate_there:11 unclear>secondhand:3 unclear>unclear:205
aspect level histogram (rep 0, overall): -3:16 -2:64 -1:40 +0:14 +1:25 +2:217 +3:25
stop reasons: end_turn:769

## By group

| metric | ambiguous_name | avoid_list_negation | deep_chain | long_list | messy_text | nameless_reply | out_of_scope | random | strong_negative | thread_long | thread_title_names_place | thread_where_to_eat | zero_mentions_suspicious |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| drop_rate | 0.036 | 0.000 | 0.267 | 0.029 | 0.000 | 0.040 | 0.000 | 0.033 | 0.095 | 0.010 | 0.019 | 0.022 | 0.130 |
| mention_recall | 0.983 | 0.958 | 0.667 | 0.985 | 0.968 | 0.963 | 0.957 | 0.948 | 0.920 | 0.966 | 0.962 | 0.943 | 0.739 |
| negative_mention_recall | 0.700 | 0.923 | 0.500 | 0.778 | 0.833 | 1.0 | 0.714 | 0.688 | 0.875 | 0.826 | 0.731 | 0.889 | 0.636 |
| value_complaint_recall | 0.667 | 0.857 | – | 0.000 | 0.667 | – | 1.0 | 0.800 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| dish_negative_recall | 0.500 | 0.667 | – | 0.556 | 0.750 | 0.000 | 0.750 | – | 0.750 | 0.375 | 0.625 | 0.250 | 0.500 |
| sign_accuracy | 0.966 | 0.962 | 1.0 | 0.976 | 0.975 | 1.0 | 1.0 | 1.0 | 1.0 | 0.987 | 0.989 | 0.984 | 1.0 |
| levels_used | 6 | 6 | 4 | 7 | 7 | 5 | 2 | 7 | 5 | 7 | 6 | 6 | 6 |
| reference_only_recall | 0.000 | 1.0 | 1.0 | 0.842 | 0.636 | 0.000 | 1.0 | 1.0 | 0.800 | 0.867 | 1.0 | 1.0 | 1.0 |
| bare_endorsement_recall | 0.958 | 0.333 | 1.0 | 0.987 | 1.0 | 0.000 | 1.0 | 0.929 | 1.0 | 1.0 | 0.900 | 0.960 | – |
| comments | 28 | 39 | 30 | 38 | 38 | 43 | 32 | 100 | 35 | 201 | 176 | 174 | 70 |
| mention_precision | 1.0 | 0.958 | 0.737 | 0.980 | 0.938 | 0.963 | 1.0 | 0.936 | 0.958 | 0.839 | 0.812 | 0.855 | 0.739 |
| fn_model_error | 0 | 1 | 0 | 2 | 1 | 1 | 2 | 1 | 0 | 4 | 5 | 6 | 1 |
| fn_context_gap | 1 | 1 | 7 | 1 | 1 | 0 | 0 | 3 | 2 | 0 | 0 | 0 | 5 |
