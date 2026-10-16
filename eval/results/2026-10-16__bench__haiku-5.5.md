# Bench haiku-5.5

Rows are compared on the comments every row in the table covered. Scope is `reweighted` (the population estimate) where the set has strata, else `overall`. Values are the mean across reps; ± is the sd across reps. Old-schema rows are read through the adapter, so their reference_only numbers are derived (see eval/docs/schema_v5.md).

## v1 / comment mode (769 common comments), scope reweighted

| row | schema | reps used | rep 0 partial | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | levels_used | mention_precision | reference_only_recall | reference_only_precision | bare_endorsement_recall | bare_endorsement_precision | is_negated_recall | experience_acc | price_exact_acc | dishes_disliked_recall | dishes_liked_recall | judgment_question_acc | refused_inputs | parse_failure_rate | repairs_per_100_mentions | bad_id_rate | cost_per_1k_comments | latency_p50 | cache_read_share |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 / revised (0d75b20b5f83) | old (adapted) | 1 of 1 |  | 0.051 | 0.947 | 0.871 | 0.980 | n/a | 0.997 | 7.0 | 0.962 | 0.718 | 0.908 | 0.898 | 0.664 | 1.0 | 0.596 | 1.0 | n/a | n/a | 1.0 | 0 | 0.000 | 0.000 | 0.000 | 0.263 | 2.266 | 0.922 |

## v2 / comment mode (481 common comments), scope overall

| row | schema | reps used | rep 0 partial | drop_rate | mention_recall | negative_mention_recall | value_complaint_recall | dish_negative_recall | sign_accuracy | levels_used | mention_precision | reference_only_recall | reference_only_precision | bare_endorsement_recall | bare_endorsement_precision | is_negated_recall | experience_acc | price_exact_acc | dishes_disliked_recall | dishes_liked_recall | judgment_question_acc | refused_inputs | parse_failure_rate | repairs_per_100_mentions | bad_id_rate | cost_per_1k_comments | latency_p50 | cache_read_share |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 / revised (0d75b20b5f83) | old (adapted) | 1 of 1 |  | 0.057 | 0.931 | 0.914 | 0.929 | n/a | 0.984 | 7.0 | 0.972 | 0.644 | 0.862 | 0.867 | 0.670 | 1.0 | 0.560 | 1.0 | n/a | n/a | 1.0 | 0 | 0.000 | 0.000 | 0.000 | 0.400 | 3.013 | 0.913 |

