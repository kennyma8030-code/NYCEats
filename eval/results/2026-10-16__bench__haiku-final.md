# Bench haiku-final

Rows are compared on the comments every row in the table covered. Scope is `reweighted` (the population estimate) where the set has strata, else `overall`. Values are the mean across reps; ± is the sd across reps. Old-schema rows are read through the adapter, so their reference_only numbers are derived (see eval/docs/schema_v5.md).

## v1 / comment mode (769 common comments), scope reweighted

| row | schema | reps used | rep 0 partial | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | levels_used | mention_precision | reference_only_recall | reference_only_precision | bare_endorsement_recall | bare_endorsement_precision | is_negated_recall | experience_acc | price_exact_acc | dishes_disliked_recall | dishes_liked_recall | judgment_question_acc | refused_inputs | parse_failure_rate | repairs_per_100_mentions | bad_id_rate | cost_per_1k_comments | latency_p50 | cache_read_share |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 / v5 (c1f7f3456699) | v5 | 1 of 1 |  | 0.035 | 0.951 | 0.714 | 0.804 | 0.517 | 0.995 | 7.0 | 0.941 | 0.920 | 0.573 | 0.923 | 0.716 | 1.0 | 0.820 | 1.0 | 0.565 | 0.714 | 1.0 | 0 | 0.000 | 0.145 | 0.000 | 0.412 | 2.838 | 0.976 |
| claude-haiku-5-5 / revised (0d75b20b5f83) | old (adapted) | 1 of 1 |  | 0.051 | 0.947 | 0.871 | 0.980 | n/a | 0.997 | 7.0 | 0.962 | 0.718 | 0.908 | 0.898 | 0.664 | 1.0 | 0.596 | 1.0 | n/a | n/a | 1.0 | 0 | 0.000 | 0.000 | 0.000 | 0.263 | 2.266 | 0.922 |
| deepseek-v4-flash / revised (current) | old (adapted) | 1 of 1 |  | 0.048 | 0.935 | 0.801 | 0.794 | n/a | 0.997 | 7.0 | 0.962 | 0.667 | 0.756 | 0.797 | 0.565 | 1.0 | 0.616 | 1.0 | n/a | n/a | 0.000 | 0 | 0.021 | 0.000 | 0.000 | 0.258 | 5.305 | 0.000 |
| deepseek-v4-flash / original (production's prompt) | old (adapted) | 1 of 3 |  | 0.171 | 0.834 | 0.642 | 0.638 | n/a | 0.967 | 7.0 | 0.976 | 0.722 | 0.907 | 0.926 | 0.699 | 1.0 | 0.648 | 1.0 | n/a | n/a | 1.0 | 0 | 0.017 | 0.000 | 0.000 | 0.382 | 5.901 | 0.000 |
| production / stored output (mixed modes) | old (adapted) | 1 of 1 |  | 0.235 | 0.714 | 0.408 | 0.405 | n/a | 0.977 | 7.0 | 0.984 | 0.672 | 0.824 | 0.934 | 0.519 | 1.0 | 0.674 | 1.0 | n/a | n/a | 0.000 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | – |

## v1 / thread mode (374 common comments), scope overall

| row | schema | reps used | rep 0 partial | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | levels_used | mention_precision | reference_only_recall | reference_only_precision | bare_endorsement_recall | bare_endorsement_precision | is_negated_recall | experience_acc | price_exact_acc | dishes_disliked_recall | dishes_liked_recall | judgment_question_acc | refused_inputs | parse_failure_rate | repairs_per_100_mentions | bad_id_rate | cost_per_1k_comments | latency_p50 | cache_read_share |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 / v5 (3d66a049c8b7) | v5 | 1 of 1 |  | 0.047 | 0.956 | 0.744 | 1.0 | 0.400 | 0.985 | 6.0 | 0.904 | 0.913 | 0.429 | 0.821 | 0.842 | 1.0 | 0.814 | 1.0 | 0.462 | 0.729 | – | 0 | 0.017 | 0.861 | 0.000 | 0.169 | 24.257 | 0.842 |
| deepseek-v4-flash / revised (current) | old (adapted) | 1 of 1 | yes | 0.047 | 0.920 | 0.884 | 1.0 | n/a | 0.993 | 7.0 | 0.945 | 0.857 | 0.429 | 0.821 | 0.727 | 1.0 | 0.710 | 1.0 | n/a | n/a | – | 0 | 0.000 | 0.000 | 0.000 | 0.064 | 63.726 | 0.000 |
| deepseek-v4-flash / original (production's prompt) | old (adapted) | 1 of 1 | yes | 0.526 | 0.540 | 0.419 | 0.333 | n/a | 1.0 | 6.0 | 0.976 | 0.615 | 0.800 | 0.946 | 0.673 | 1.0 | 0.595 | 1.0 | n/a | n/a | – | 0 | 0.000 | 0.000 | 0.000 | 0.082 | 29.058 | 0.000 |
| production / stored output (mixed modes) | old (adapted) | 1 of 1 |  | 0.495 | 0.482 | 0.488 | 1.0 | n/a | 1.0 | 6.0 | 0.893 | 0.900 | 0.529 | 0.811 | 0.769 | – | 0.596 | 1.0 | n/a | n/a | – | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | – |

## v2 / comment mode (244 common comments), scope overall

| row | schema | reps used | rep 0 partial | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | levels_used | mention_precision | reference_only_recall | reference_only_precision | bare_endorsement_recall | bare_endorsement_precision | is_negated_recall | experience_acc | price_exact_acc | dishes_disliked_recall | dishes_liked_recall | judgment_question_acc | refused_inputs | parse_failure_rate | repairs_per_100_mentions | bad_id_rate | cost_per_1k_comments | latency_p50 | cache_read_share |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 / v5 (c1f7f3456699) | v5 | 1 of 1 |  | 0.054 | 0.931 | 0.720 | 0.786 | 0.543 | 0.979 | 7.0 | 0.950 | 0.818 | 0.493 | 0.814 | 0.583 | 1.0 | 0.844 | 1.0 | 0.613 | 0.805 | 1.0 | 0 | 0.000 | 0.145 | 0.000 | 0.577 | 3.710 | 0.974 |
| claude-haiku-5-5 / revised (0d75b20b5f83) | old (adapted) | 1 of 1 |  | 0.083 | 0.903 | 0.860 | 0.929 | n/a | 0.984 | 7.0 | 0.964 | 0.718 | 0.824 | 0.750 | 0.493 | 1.0 | 0.634 | 1.0 | n/a | n/a | 1.0 | 0 | 0.000 | 0.000 | 0.000 | 0.400 | 3.013 | 0.913 |
| deepseek-v4-flash / revised (current) | old (adapted) | 1 of 1 |  | 0.129 | 0.864 | 0.770 | 0.786 | n/a | 0.987 | 7.0 | 0.971 | 0.629 | 0.595 | 0.911 | 0.477 | 1.0 | 0.681 | 1.0 | n/a | n/a | 0.000 | 0 | 0.008 | 0.000 | 0.000 | 0.335 | 8.747 | 0.000 |
| deepseek-v4-flash / original (production's prompt) | old (adapted) | 1 of 3 |  | 0.338 | 0.742 | 0.620 | 0.786 | n/a | 0.989 | 7.0 | 0.986 | 0.795 | 0.756 | 0.950 | 0.543 | 1.0 | 0.646 | 1.0 | n/a | n/a | 1.0 | 0 | 0.009 | 0.000 | 0.000 | 0.882 | 9.606 | 0.000 |
| production / stored output (mixed modes) | old (adapted) | 1 of 1 |  | 0.662 | 0.379 | 0.340 | 0.286 | n/a | 0.962 | 7.0 | 0.897 | 0.478 | 0.917 | 1.0 | 0.468 | 1.0 | 0.626 | 1.0 | n/a | n/a | 0.000 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | – |

## v2 / thread mode (122 common comments), scope overall

| row | schema | reps used | rep 0 partial | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | levels_used | mention_precision | reference_only_recall | reference_only_precision | bare_endorsement_recall | bare_endorsement_precision | is_negated_recall | experience_acc | price_exact_acc | dishes_disliked_recall | dishes_liked_recall | judgment_question_acc | refused_inputs | parse_failure_rate | repairs_per_100_mentions | bad_id_rate | cost_per_1k_comments | latency_p50 | cache_read_share |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 / v5 (3d66a049c8b7) | v5 | 1 of 1 |  | 0.076 | 0.933 | 0.694 | 1.0 | 0.400 | 0.978 | 6.0 | 0.986 | 1.0 | 0.375 | 0.615 | 0.889 | 1.0 | 0.784 | – | 0.462 | 0.686 | – | 0 | 0.031 | 0.861 | 0.000 | 0.193 | 27.796 | 0.843 |
| deepseek-v4-flash / revised (current) | old (adapted) | 1 of 1 | yes | 0.067 | 0.893 | 0.861 | 1.0 | n/a | 0.989 | 6.0 | 0.985 | 0.857 | 0.316 | 0.714 | 0.526 | 1.0 | 0.797 | 1.0 | n/a | n/a | – | 0 | 0.000 | 0.000 | 0.000 | 0.057 | 91.838 | 0.000 |
| deepseek-v4-flash / original (production's prompt) | old (adapted) | 1 of 1 | yes | 0.706 | 0.427 | 0.417 | 0.500 | n/a | 1.0 | 4.0 | 0.985 | 0.636 | 0.778 | 0.917 | 0.550 | 1.0 | 0.651 | – | n/a | n/a | – | 0 | 0.000 | 0.000 | 0.000 | 0.066 | 47.175 | 0.000 |
| production / stored output (mixed modes) | old (adapted) | 1 of 1 |  | 0.790 | 0.220 | 0.389 | 1.0 | n/a | 1.0 | 4.0 | 0.717 | 1.0 | 1.0 | 1.0 | 0.846 | – | 0.636 | 1.0 | n/a | n/a | – | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | – |

