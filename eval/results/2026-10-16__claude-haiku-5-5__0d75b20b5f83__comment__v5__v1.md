# claude-haiku-5-5__0d75b20b5f83__comment__v5__v1

mode: comment; schema: old (adapted); reps used 1 of 1; labeled comments not in run: 0
calls 769, errors 0 (inputs refused for good: 0), parse failures 0.000, cost $0.2024 ($0.263 per 1k comments), latency p50 2.3s p90 4.3s
input tokens 2,259,770 (cache reads 2,083,584, cache writes 2,713; read share 0.922), output tokens 327,840
normalizer repairs per 100 mentions: 0.000 (none); bad thread ids: 0.000
Old-schema run, read through the adapter: reference_only is derived (every aspect null, no avoid) and bare endorsement is food 0.3 alone; see docs/schema_v5.md.

## Headline (owner priorities, in order)

| metric | overall | reweighted | single_comments | threads |
|---|---|---|---|---|
| a. comment drop rate (lower is better) | 0.049 | 0.051 | 0.059 | 0.037 |
| b. mention recall | 0.940 | 0.947 | 0.941 | 0.938 |
| c. negative-mention recall | 0.893 | 0.871 | 0.864 | 0.953 |
| d. value-complaint recall | 0.950 | 0.980 | 0.941 | 1.0 |
| e. dish-negative recall | n/a | n/a | n/a | n/a |
| f. sign accuracy | 0.985 | 0.997 | 0.992 | 0.973 |
| f. aspect levels used (of 7) | 7 | 7 | 7 | 6 |

## v5 fields

| metric | overall | reweighted | single_comments | threads |
|---|---|---|---|---|
| reference_only_precision | 0.758 | 0.908 | 0.833 | 0.654 |
| reference_only_recall | 0.783 | 0.718 | 0.769 | 0.810 |
| bare_endorsement_precision | 0.663 | 0.664 | 0.633 | 0.775 |
| bare_endorsement_recall | 0.834 | 0.898 | 0.848 | 0.795 |
| is_negated_precision | 0.833 | 0.789 | 0.800 | 1.0 |
| is_negated_recall | 1.0 | 1.0 | 1.0 | 1.0 |
| experience_acc | 0.552 | 0.596 | 0.516 | 0.626 |
| price_exact_acc | 1.0 | 1.0 | 1.0 | 1.0 |
| price_within1_acc | 1.0 | 1.0 | 1.0 | 1.0 |
| price_presence_f1 | 0.571 | 0.402 | 0.556 | 0.609 |
| dishes_liked_precision | n/a | n/a | n/a | n/a |
| dishes_liked_recall | n/a | n/a | n/a | n/a |
| dishes_disliked_precision | n/a | n/a | n/a | n/a |
| dishes_disliked_recall | n/a | n/a | n/a | n/a |
| dishes_any_recall | 0.822 | 0.827 | 0.833 | 0.804 |
| judgment_question_acc | 1.0 | 1.0 | 1.0 | – |

## Everything else

| metric | overall | reweighted | single_comments | threads |
|---|---|---|---|---|
| comments | 769 | 198003.0 | 395 | 374 |
| mention_precision | 0.946 | 0.962 | 0.964 | 0.910 |
| mention_f1 | 0.943 | 0.954 | 0.953 | 0.924 |
| fn_model_error | 25 | 3071.148 | 11 | 14 |
| fn_context_gap | 16 | 5976.558 | 16 | 0 |
| neg_miss_model_error | 7 | 2122.359 | 5 | 2 |
| neg_miss_context_gap | 7 | 2096.947 | 7 | 0 |
| negative_to_positive_rate | 0.008 | 0.003 | 0.011 | 0.000 |
| negative_to_bare_rate | 0.000 | 0.000 | 0.000 | 0.000 |
| negative_softened_rate | 0.007 | 0.002 | 0.010 | 0.000 |
| reference_mention_recall | 0.903 | 0.922 | 0.911 | 0.875 |
| closed_mention_recall | 1.0 | 1.0 | 1.0 | 1.0 |
| closed_handled_rate | 0.308 | 0.439 | 0.250 | 1.0 |
| search_terms_recall | 0.682 | 0.666 | 0.654 | 0.793 |
| food_presence_f1 | 0.909 | 0.918 | 0.881 | 0.958 |
| food_exact_acc | 0.947 | 0.956 | 0.973 | 0.904 |
| food_within1_acc | 1.0 | 1.0 | 1.0 | 1.0 |
| food_mae_levels | 0.053 | 0.044 | 0.027 | 0.096 |
| value_presence_f1 | 0.816 | 0.852 | 0.806 | 0.857 |
| value_exact_acc | 0.903 | 0.869 | 0.960 | 0.667 |
| service_presence_f1 | 0.952 | 0.995 | 0.968 | 0.909 |
| atmosphere_presence_f1 | 0.857 | 0.916 | 0.864 | 0.800 |
| wait_presence_f1 | 0.878 | 0.938 | 0.810 | 0.950 |
| food_spearman | 0.885 | 0.908 | 0.908 | 0.838 |
| sign_err_model_error | 6 | 338.333 | 2 | 4 |
| sign_err_context_gap | 0 | 0 | 0 | 0 |
| neg_mention_n | 131 | 32638.331 | 88 | 43 |
| vc_n | 20 | 9010.022 | 17 | 3 |
| dishneg_n | 35 | 2037.266 | 20 | 15 |
| jq_n | 1 | 181.417 | 1 | 0 |

experience confusion (gold>model, rep 0, overall): ate_there>ate_there:313 ate_there>secondhand:71 secondhand>ate_there:2 secondhand>secondhand:41 unclear>ate_there:56 unclear>secondhand:158
aspect level histogram (rep 0, overall): -3:11 -2:88 -1:56 +0:13 +1:26 +2:243 +3:24
stop reasons: end_turn:769

## By group

| metric | ambiguous_name | avoid_list_negation | deep_chain | long_list | messy_text | nameless_reply | out_of_scope | random | strong_negative | thread_long | thread_title_names_place | thread_where_to_eat | zero_mentions_suspicious |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| drop_rate | 0.036 | 0.000 | 0.267 | 0.029 | 0.053 | 0.040 | 0.000 | 0.049 | 0.095 | 0.039 | 0.047 | 0.043 | 0.174 |
| mention_recall | 0.966 | 0.979 | 0.667 | 0.970 | 0.937 | 0.963 | 0.957 | 0.948 | 0.920 | 0.941 | 0.923 | 0.915 | 0.696 |
| negative_mention_recall | 0.800 | 0.962 | 0.500 | 0.889 | 1.0 | 1.0 | 0.714 | 0.875 | 0.875 | 0.957 | 0.962 | 1.0 | 0.818 |
| value_complaint_recall | 0.667 | 1.0 | – | 1.0 | 1.0 | – | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| dish_negative_recall | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sign_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.867 | 1.0 | 1.0 | 0.964 | 0.961 | 0.954 | 1.0 |
| levels_used | 6 | 5 | 4 | 6 | 6 | 5 | 5 | 7 | 5 | 6 | 6 | 6 | 5 |
| reference_only_recall | 1.0 | 1.0 | 1.0 | 0.800 | 0.500 | 0.000 | 1.0 | 0.714 | 0.800 | 0.933 | 0.571 | 1.0 | 1.0 |
| bare_endorsement_recall | 0.917 | 0.167 | 0.000 | 0.870 | 0.889 | 0.500 | 0.933 | 0.929 | 1.0 | 0.667 | 0.727 | 0.880 | – |
| comments | 28 | 39 | 30 | 38 | 38 | 43 | 32 | 100 | 35 | 201 | 176 | 174 | 70 |
| mention_precision | 1.0 | 0.979 | 0.824 | 0.980 | 0.983 | 0.963 | 1.0 | 0.961 | 0.958 | 0.903 | 0.923 | 0.915 | 0.727 |
| fn_model_error | 1 | 0 | 0 | 5 | 3 | 1 | 2 | 1 | 0 | 7 | 10 | 9 | 2 |
| fn_context_gap | 1 | 1 | 7 | 1 | 1 | 0 | 0 | 3 | 2 | 0 | 0 | 0 | 5 |
