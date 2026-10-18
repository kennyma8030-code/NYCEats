# Claude's v6 labels: agreement with themselves

a = primary copy (self-consistency) or full_context (same_input_vs_full); b = the other.

| comparison | comments | comment_presence_agreement | mention_agreement_f1 | overall_presence_agreement | overall_sign_agreement | overall_exact_agreement | matched_negative_f1 | comments_materially_different |
|---|---|---|---|---|---|---|---|---|
| self_consistency:same_input | 71 | 0.915 | 0.964 | 0.988 | 1.0 | 0.915 | 1.0 | 0.099 |
| self_consistency:full_context | 71 | 0.958 | 0.982 | 0.988 | 1.0 | 0.979 | 1.0 | 0.056 |
| same_input_vs_full | 504 | 0.966 | 0.975 | 0.971 | 0.998 | 0.958 | 0.96 | 0.093 |

## Aspects on matched mentions (presence / sign / exact)

| comparison | taste | value | service | atmosphere | wait |
|---|---|---|---|---|---|
| self_consistency:same_input | 0.975 / 1.0 / 0.9 (n=12) | 0.963 / 1.0 / 1.0 (n=12) | 0.988 / 1.0 / 1.0 (n=14) | 1.0 / None / None (n=0) | 1.0 / None / None (n=0) |
| self_consistency:full_context | 0.988 / 1.0 / 0.9 (n=11) | 1.0 / 1.0 / 0.909 (n=11) | 0.976 / 1.0 / 1.0 (n=14) | 1.0 / None / None (n=0) | 0.988 / None / None (n=1) |
| same_input_vs_full | 0.96 / 0.969 / 0.939 (n=156) | 0.985 / 1.0 / 0.9 (n=39) | 0.989 / 1.0 / 0.88 (n=32) | 0.995 / 1.0 / 1.0 (n=22) | 0.995 / 1.0 / 0.955 (n=25) |

## same_input vs full_context by group (most different first)

| group | comments | materially different | mention F1 | overall sign | matched negative F1 |
|---|---|---|---|---|---|
| stratum:deep_chain_context_gap | 17 | 0.294 | 0.833 | 1.0 | 1.0 |
| stratum:dish_complaint | 14 | 0.286 | 0.982 | 0.955 | 0.96 |
| tag:dish_complaint | 16 | 0.25 | 0.984 | 0.962 | 0.966 |
| tag:deep_chain_context_gap | 32 | 0.219 | 0.85 | 1.0 | 1.0 |
| stratum:neg_wording_nonneg_score | 14 | 0.214 | 0.957 | 1.0 | 0.889 |
| tag:neg_wording_nonneg_score | 19 | 0.211 | 0.966 | 1.0 | 0.923 |
| draw:overlap_v1 | 50 | 0.18 | 0.893 | 1.0 | 1.0 |
| stratum:overlap_v1 | 50 | 0.18 | 0.893 | 1.0 | 1.0 |
| tag:reply_ancestor_named | 80 | 0.163 | 0.908 | 1.0 | 1.0 |
| depth:reply 2+ | 138 | 0.138 | 0.902 | 1.0 | 0.945 |
| mode:comment | 250 | 0.12 | 0.964 | 0.997 | 0.97 |
| stratum:chunk_title_names_place | 36 | 0.111 | 1.0 | 1.0 | 0.0 |
| tag:original_thread_prompt | 201 | 0.109 | 0.945 | 1.0 | 0.988 |
| tag:zero_mentions_suspicious | 28 | 0.107 | 0.8 | 1.0 | None |
| tag:long_list | 29 | 0.103 | 0.997 | 0.994 | 0.933 |
| tag:extracted_no_mentions | 138 | 0.101 | 0.879 | 1.0 | 1.0 |
| stratum:long_list | 10 | 0.1 | 0.992 | 1.0 | None |
| tag:chunk_title_names_place | 61 | 0.098 | 0.982 | 1.0 | 0.952 |
| tag:never_extracted | 250 | 0.092 | 0.988 | 0.996 | 0.941 |
| tag:chunk_never_extracted | 125 | 0.088 | 1.0 | 1.0 | 0.912 |
| draw:targeted | 309 | 0.087 | 0.983 | 0.997 | 0.964 |
| stratum:avoid_or_strong_negative | 12 | 0.083 | 1.0 | 1.0 | 0.952 |
| stratum:reply_ancestor_named | 24 | 0.083 | 0.933 | 1.0 | 1.0 |
| depth:reply | 140 | 0.079 | 0.982 | 1.0 | 0.951 |
| tag:avoid_or_strong_negative | 38 | 0.079 | 1.0 | 0.984 | 0.943 |
| stratum:stuck_default_with_opinion | 13 | 0.077 | 1.0 | 1.0 | 1.0 |
| draw:random | 145 | 0.076 | 0.981 | 1.0 | 0.93 |
| depth:top-level | 226 | 0.075 | 0.992 | 0.997 | 0.972 |
| tag:stuck_default_with_opinion | 27 | 0.074 | 0.984 | 1.0 | 1.0 |
| stratum:price_complaint | 14 | 0.071 | 0.95 | 1.0 | 1.0 |
| stratum:question_or_unvisited | 14 | 0.071 | 0.977 | 1.0 | 1.0 |
| stratum:short_opinion_reply | 14 | 0.071 | 0.9 | 1.0 | 1.0 |
| mode:thread | 254 | 0.067 | 0.99 | 1.0 | 0.945 |
| stratum:none | 104 | 0.058 | 0.996 | 1.0 | 0.909 |
| tag:price_complaint | 18 | 0.056 | 0.96 | 1.0 | 1.0 |
| stratum:chunk_misattached | 75 | 0.053 | 0.971 | 1.0 | 0.963 |
| tag:chunk_misattached | 75 | 0.053 | 0.971 | 1.0 | 0.963 |
| tag:question_or_unvisited | 19 | 0.053 | 0.98 | 1.0 | 1.0 |
| stratum:chunk_failure_dense | 40 | 0.05 | 0.985 | 1.0 | 1.0 |
| tag:short_opinion_reply | 40 | 0.05 | 0.971 | 1.0 | 0.963 |
| stratum:chunk_parent_outside | 43 | 0.047 | 1.0 | 1.0 | 0.971 |
| tag:chunk_failure_dense | 65 | 0.046 | 0.99 | 1.0 | 0.973 |
| tag:chunk_parent_outside | 93 | 0.043 | 0.985 | 1.0 | 0.984 |
| tag:chunk_later | 75 | 0.04 | 0.982 | 1.0 | 0.983 |
| tag:mixed_prompt_mentions | 30 | 0.033 | 0.992 | 1.0 | 1.0 |
| stratum:zero_mentions_suspicious | 10 | 0.0 | 1.0 | 1.0 | None |

## Comments that differ (full_context -> same_input)

- s0059 t1_in412eo (dish_complaint): ['Tiger Sugar:positive', 'Yi Fang:positive', 'Ten Ren:positive', 'Taiyaki:negative', 'Chinatown Ice cream factory:positive', 'Minus Celcius Ice Cream:neutral', 'Eileen Cheese cake:very_positive', 'T-Swirl Crepe:positive', 'Keki Modern Cake:positive', 'Jing Fong:positive', 'Golden Unicorn:positive', 'Nom Wah:positive'] -> ['Tiger Sugar:positive', 'Yi Fang:positive', 'Ten Ren:positive', 'Taiyaki:-', 'Chinatown Ice cream factory:positive', 'Minus Celcius Ice Cream:neutral', 'Eileen Cheese cake:very_positive', 'T-Swirl Crepe:positive', 'Keki Modern Cake:positive', 'Jing Fong:positive', 'Golden Unicorn:positive', 'Nom Wah:positive']
- s0166 t1_in735l5 (price_complaint): ['Margon:positive', 'Park Gourmet:positive', 'B and H dairy:positive', 'Jin Fong:positive'] -> ['Margon:positive', 'Park Gourmet:positive', 'B and H dairy:positive', 'Jin Fong Dim Sum:positive']
- s0219 t1_ja08qkn (reply_ancestor_named): ['Carbone:-'] -> []
- t006 t1_jet6pjh (chunk_title_names_place): ['Wildair:-'] -> ['Wildair:positive']
- t006 t1_jetx5gt (chunk_title_names_place): ['Aquavit:-'] -> ['Aquavit:positive']
- t006 t1_jeweq3l (chunk_title_names_place): ['contra:-', 'wildair:-'] -> ['wildair:positive', 'contra:positive']
- s0160 t1_jrq379k (dish_complaint): ['Dominique Ansel’s Bakery:negative'] -> []
- s0113 t1_jzi07eu (dish_complaint): ['Xiang Hot Pot:positive'] -> ['Xiang Hot Pot:neutral']
- t009 t1_ke2vnjx (none): ['Moono:positive', 'Her Name is Han:-'] -> ['Moono:-', 'Her Name is Han:-']
- t009 t1_ke4os0n (none): ['CDG:very_positive'] -> ['CDG:very_positive']
- t009 t1_ke5j7eg (none): ['Cho Dang Gol:-'] -> ['Cho Dang Gol:positive']
- t010 t1_ktrqlp1 (chunk_parent_outside): ['Guissepinas:-'] -> ['Guissepinas:negative']
- s0128 t1_ktu7nch (deep_chain_context_gap): ['Rowdy Rooster:-'] -> []
- s0032 t1_l4t6lks (short_opinion_reply): [] -> ['Los Tacos:negative', 'Los Mariscos:negative']
- s0068 t1_l93oz1p (question_or_unvisited): ['Bungalow:-'] -> []
- s0004 t1_lp2rzev (avoid_or_strong_negative): ['Panna Too:neutral', 'Woojrip:positive', 'Picnic Garden:positive', 'Antoya:positive', 'HanGawi:very_negative:avoid', 'Pio Pio:positive'] -> ['Panna Too:neutral', 'Woojrip:positive', 'Picnic Garden:positive', 'Antoya:positive', 'HanGawi:very_negative:avoid', 'Pio Pio:positive']
- s0074 t1_lqmn4ll (deep_chain_context_gap): ["Artichoke Basille's:very_negative"] -> ["Artichoke Basille's:-"]
- t002 t1_m0mq79b (chunk_misattached): ["Keen's:-"] -> ["Keen's:positive"]
- t002 t1_m0oqg68 (chunk_misattached): ["Keen's:-"] -> ["Keen's:-"]
- s0212 t1_m3nx9r7 (deep_chain_context_gap): ['Zabb PuTawn:positive'] -> []
- t007 t1_mbs3npn (none): ['Fiacco’s:-'] -> ['Fiacco’s:-']
- t014 t1_mg3ddyn (chunk_title_names_place): ['Atomix:-'] -> ['Atomix:-']
- s0131 t1_myb1xfg (none): ['Gammeok:-'] -> ['Gammeok:negative']
- s0045 t1_n6yt6bq (deep_chain_context_gap): ["Jack's Wife Freda:negative"] -> []
- s0052 t1_nmr9d4o (neg_wording_nonneg_score): ['Kopitiam:positive'] -> ['Kopitiam:-']
- t012 t1_nvy9q9g (chunk_failure_dense): ['Nakazawa:-'] -> []
- s0236 t1_nwekg2n (overlap_v1): ['gargiulos:positive'] -> []
- s0033 t1_nzlqfr1 (neg_wording_nonneg_score): ['Stretch Pizza:-'] -> ['Stretch Pizza:-']
- t008 t1_o0pgywp (chunk_failure_dense): ['Sigiri:very_positive'] -> []
- t013 t1_o3bt6da (chunk_parent_outside): ['dokodemo:-'] -> ['dokodemo:negative']
- s0146 t1_o8txycc (long_list): ['Phayul:positive', 'Awash:positive', 'New World food court:positive', 'Masalawala and Sons:positive', 'Between the Bagel:positive', 'Ukrainian East Village Restaurant:positive'] -> ['Phayul:positive', 'Awash:positive', 'New World food court:positive', 'Uyghur place:positive', 'Masalawala and Sons:positive', 'Between the Bagel:positive', 'Ukrainian East Village Restaurant:positive']
- s0165 t1_o9jchty (overlap_v1): ["Dani's:positive"] -> ['Lucky Charlie:positive']
- t011 t1_o9y91ml (none): ['Ohayo:very_positive'] -> []
- s0132 t1_oh61yef (overlap_v1): ['the Modern:very_positive'] -> ['torrisi:very_positive', 'Kabawa:very_positive', 'the Modern:very_positive', 'Kitchen Table:very_positive']
- t004 t1_oo7b7dn (chunk_misattached): ['Isla& co:negative'] -> ['Isla& co:-', 'Boqueria:-']
- t004 t1_ooaak08 (chunk_misattached): ['Boqueria:-'] -> []
- s0144 t1_orfx26n (overlap_v1): ['S&P:-'] -> ['S&P:positive']
- s0100 t1_os4cd1h (overlap_v1): ['Molly’s:positive'] -> []
- s0007 t1_ot7m1z7 (overlap_v1): ['Ammazzacaffee:-'] -> []
- s0111 t1_ouru1xq (deep_chain_context_gap): ['Po:-'] -> []
- s0093 t1_ower5z6 (overlap_v1): ['Verlain:positive'] -> ['Verlain:-']
- s0155 t1_p066j3d (reply_ancestor_named): ['Joe’s:negative'] -> ['L’industrie:negative']
- s0037 t1_p0vu820 (overlap_v1): [] -> ['Pies n Thighs:-']
- s0230 t1_p0xw8lm (overlap_v1): ['lakotafrybreadco:positive'] -> ['Indigenous Frybread Pop-Up Stand:positive']
- s0149 t1_p3oqld2 (dish_complaint): ['Roma:neutral'] -> ['Roma:-']
- s0195 t1_p913sta (neg_wording_nonneg_score): ['Goldees:very_positive', 'Bark:positive'] -> []
- s0002 t1_p98iff5 (stuck_default_with_opinion): ['Boishakhi:-', 'Hyderabadi Ziaqa:very_positive'] -> ['Boishakhi:negative', 'Hyderabadi Ziaqa:very_positive']
