# claude-haiku-5-5__3d66a049c8b7__thread__v5__v1

mode: thread; schema: v5; reps used 1 of 1; labeled comments not in run: 0
calls 414, errors 0 (inputs refused for good: 0), parse failures 0.017, cost $1.4458 ($0.169 per 1k comments), latency p50 24.3s p90 40.4s
input tokens 3,908,169 (cache reads 3,291,056, cache writes 15,976; read share 0.842), output tokens 2,701,464
normalizer repairs per 100 mentions: 0.861 (dishes_disliked_missing:96, extra_key:4, reference_with_aspects:3, dish_in_two_lists:1, aspect_null_string:1); bad thread ids: 0.000

## Headline (owner priorities, in order)

| metric | overall | reweighted | single_comments | threads |
|---|---|---|---|---|
| a. comment drop rate (lower is better) | 0.059 | 0.067 | 0.068 | 0.047 |
| b. mention recall | 0.892 | 0.894 | 0.861 | 0.956 |
| c. negative-mention recall | 0.733 | 0.610 | 0.727 | 0.744 |
| d. value-complaint recall | 0.800 | 0.794 | 0.765 | 1.0 |
| e. dish-negative recall | 0.457 | 0.403 | 0.500 | 0.400 |
| f. sign accuracy | 0.986 | 0.981 | 0.987 | 0.985 |
| f. aspect levels used (of 7) | 7 | 7 | 7 | 6 |

## v5 fields

| metric | overall | reweighted | single_comments | threads |
|---|---|---|---|---|
| reference_only_precision | 0.505 | 0.434 | 0.580 | 0.429 |
| reference_only_recall | 0.833 | 0.690 | 0.784 | 0.913 |
| bare_endorsement_precision | 0.827 | 0.687 | 0.821 | 0.842 |
| bare_endorsement_recall | 0.905 | 0.918 | 0.939 | 0.821 |
| is_negated_precision | 0.800 | 0.698 | 0.750 | 1.0 |
| is_negated_recall | 0.800 | 0.738 | 0.750 | 1.0 |
| experience_acc | 0.816 | 0.785 | 0.817 | 0.814 |
| price_exact_acc | 1.0 | 1.0 | 1.0 | 1.0 |
| price_within1_acc | 1.0 | 1.0 | 1.0 | 1.0 |
| price_presence_f1 | 0.821 | 0.827 | 0.889 | 0.667 |
| dishes_liked_precision | 0.939 | 0.895 | 0.947 | 0.927 |
| dishes_liked_recall | 0.707 | 0.666 | 0.692 | 0.729 |
| dishes_disliked_precision | 0.842 | 0.768 | 0.833 | 0.857 |
| dishes_disliked_recall | 0.500 | 0.426 | 0.526 | 0.462 |
| dishes_any_recall | 0.778 | 0.724 | 0.733 | 0.847 |
| judgment_question_acc | 1.0 | 1.0 | 1.0 | – |

## Everything else

| metric | overall | reweighted | single_comments | threads |
|---|---|---|---|---|
| comments | 769 | 198003.0 | 395 | 374 |
| mention_precision | 0.940 | 0.967 | 0.961 | 0.904 |
| mention_f1 | 0.916 | 0.929 | 0.908 | 0.929 |
| fn_model_error | 69 | 15687.003 | 59 | 10 |
| fn_context_gap | 5 | 2290.479 | 5 | 0 |
| neg_miss_model_error | 34 | 12532.524 | 23 | 11 |
| neg_miss_context_gap | 1 | 182.792 | 1 | 0 |
| negative_to_positive_rate | 0.046 | 0.100 | 0.045 | 0.047 |
| negative_to_bare_rate | 0.000 | 0.000 | 0.000 | 0.000 |
| negative_softened_rate | 0.018 | 0.063 | 0.026 | 0.000 |
| reference_mention_recall | 0.874 | 0.843 | 0.835 | 1.0 |
| closed_mention_recall | 0.923 | 0.975 | 0.917 | 1.0 |
| closed_handled_rate | 0.077 | 0.205 | 0.083 | 0.000 |
| search_terms_recall | 0.414 | 0.421 | 0.340 | 0.701 |
| food_presence_f1 | 0.944 | 0.890 | 0.945 | 0.944 |
| food_exact_acc | 0.939 | 0.921 | 0.941 | 0.936 |
| food_within1_acc | 0.993 | 0.978 | 0.995 | 0.991 |
| food_mae_levels | 0.067 | 0.101 | 0.064 | 0.073 |
| value_presence_f1 | 0.936 | 0.982 | 0.941 | 0.923 |
| value_exact_acc | 0.909 | 1.0 | 1.0 | 0.667 |
| service_presence_f1 | 0.839 | 0.985 | 0.917 | 0.571 |
| atmosphere_presence_f1 | 0.938 | 0.994 | 0.963 | 0.800 |
| wait_presence_f1 | 0.889 | 0.814 | 0.857 | 0.917 |
| food_spearman | 0.897 | 0.917 | 0.917 | 0.856 |
| sign_err_model_error | 5 | 1772.590 | 3 | 2 |
| sign_err_context_gap | 0 | 0 | 0 | 0 |
| neg_mention_n | 131 | 32638.331 | 88 | 43 |
| vc_n | 20 | 9010.022 | 17 | 3 |
| dishneg_n | 35 | 2037.266 | 20 | 15 |
| jq_n | 1 | 181.417 | 1 | 0 |

experience confusion (gold>model, rep 0, overall): ate_there>ate_there:291 ate_there>secondhand:3 ate_there>unclear:76 secondhand>secondhand:14 secondhand>unclear:25 unclear>ate_there:4 unclear>secondhand:4 unclear>unclear:191
aspect level histogram (rep 0, overall): -3:16 -2:59 -1:39 +0:10 +1:18 +2:213 +3:26
stop reasons: end_turn:407, max_tokens:7

## By group

| metric | ambiguous_name | avoid_list_negation | deep_chain | long_list | messy_text | nameless_reply | out_of_scope | random | strong_negative | thread_long | thread_title_names_place | thread_where_to_eat | zero_mentions_suspicious |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| drop_rate | 0.000 | 0.100 | 0.067 | 0.029 | 0.000 | 0.120 | 0.000 | 0.066 | 0.095 | 0.049 | 0.056 | 0.043 | 0.130 |
| mention_recall | 0.931 | 0.854 | 0.952 | 0.811 | 0.540 | 0.889 | 0.935 | 0.909 | 0.880 | 0.950 | 0.954 | 0.953 | 0.696 |
| negative_mention_recall | 0.800 | 0.808 | 0.833 | 0.667 | 0.667 | 1.0 | 0.714 | 0.562 | 0.938 | 0.783 | 0.692 | 0.889 | 0.545 |
| value_complaint_recall | 0.667 | 0.714 | – | 0.000 | 0.667 | – | 1.0 | 0.800 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| dish_negative_recall | 0.000 | 0.167 | – | 0.556 | 0.250 | 0.000 | 0.500 | – | 0.750 | 0.250 | 0.625 | 0.250 | 0.500 |
| sign_accuracy | 0.968 | 1.0 | 0.929 | 1.0 | 1.0 | 1.0 | 1.0 | 0.977 | 1.0 | 0.986 | 0.978 | 0.984 | 1.0 |
| levels_used | 6 | 6 | 6 | 7 | 7 | 5 | 3 | 7 | 5 | 6 | 6 | 6 | 6 |
| reference_only_recall | – | 1.0 | 1.0 | 0.882 | 0.625 | 0.000 | 1.0 | 0.667 | 0.667 | 0.882 | 1.0 | 1.0 | 1.0 |
| bare_endorsement_recall | 0.955 | 0.833 | 0.000 | 0.969 | 0.750 | 0.000 | 1.0 | 0.917 | 0.500 | 0.667 | 0.700 | 0.880 | – |
| comments | 28 | 39 | 30 | 38 | 38 | 43 | 32 | 100 | 35 | 201 | 176 | 174 | 70 |
| mention_precision | 1.0 | 0.932 | 1.0 | 0.976 | 0.944 | 0.960 | 1.0 | 0.972 | 0.957 | 0.919 | 0.886 | 0.953 | 0.727 |
| fn_model_error | 4 | 7 | 0 | 38 | 29 | 2 | 3 | 6 | 3 | 6 | 6 | 5 | 5 |
| fn_context_gap | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 2 |
