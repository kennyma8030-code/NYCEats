# Gold changes after adjudication

v1 gold was labeled blind (labels/batch01–batch21). It was then scored
against the ORIGINAL production extraction
(`eval/baseline/production__stored__all.jsonl`), and every disagreement was
re-read; there were 259 comments with at least one disagreement
(`eval/baseline/disagreements.jsonl`). A change was made only where the
model's reading turned out to be defensible, or where I had broken one of my
own rules. Disagreements that held up stayed as model failures.

The corrections live in `labels/adjudication.py` as patches on top of the
untouched blind labels, so every change can be audited. Each patched gold
line carries `"adjudicated": true`. That is 23 patches over 19 comments: 5
added mentions, 14 widened alternatives, 2 flags changed, plus one fix made
before scoring.

## Before scoring (consistency)

| comment | change | why |
|---|---|---|
| c0126 | Zabar's (cafe) → `out_of_scope` | `zabars` is one of production's excluded entities, so no model output could ever count for it |

## After re-reading disagreements

| comment | mention | change | why |
|---|---|---|---|
| c0014 | Salt Hank | wait alt +1/+2 | "order for pickup and skip the line" reads fairly as easy wait |
| c0065 | Cote | atmosphere alt +1 | "in a modern environment. It works." is a mild room positive |
| c0067 | The Great Nosh | **added** (ambiguous) | a multi-vendor food event; the in-scope reading (like Smorgasburg) is defensible |
| c0094 | Oven Slice | value alt -1/-2 | "not worth anything other than being closest" is a value knock |
| c0094 | Johnny's | value alt +1 | "a much better slice for 1.50 more" |
| c0114 | 4 Charles | value alt -2 | "not worth all that" |
| c0125 | The Modern Kitchen Table | **added** (ambiguous) | a named sub-venue the model emitted separately |
| c0176 | Mongolian Momo King | food alt +1 | offered as a lead in answer to the question: my own rule 2 |
| c0206 | Dunkin', McDonald's | food alt +1 | "I get dunkin or mcd if i want caffeine" is a mild positive |
| c0242 | Amanda's Good Morning Cafe | value alt +1/+2 | "don't want to break the bank" |
| c0282 | Katz's | food alt -1 | "a measly sandwich" judges the food |
| c0345 | Brooklyn DOP | atmosphere alt +1 | "Looked quite clean" |
| c0353 | César | `is_negated` uncertain | "I'd dump Cesar" can be read as an avoid |
| c0363 | Carbone | **added** (required) | "I worked for Mario at Carbone": a named reference I missed while labeling |
| c0365 | Bar Goto Niban | atmosphere alt +2/+3 | "perfect for this" (a quiet, romantic date) is about the room |
| c0368 | Hillstone | atmosphere alt +1/+2 | "nice view" read literally rather than as sarcasm |
| t004 p6732eo | L'Industrie | → ambiguous | "I don't like their pizza like lindustry" also reads as "not the way I like L'Industrie" |
| t001 owksvvi, owp4j06 | Pressed | **added** (ambiguous) | nameless remarks about the post's subject |
| t005 o2c1yf4 | Mangia | value alt +1/+2 | "not cheap, but the quality is very good" |
| t010 ozsqh90 | Mama's Too, Red Gate | **added** (ambiguous) | "just these 2 places": a nameless reference |

## Scorer fix found in the same pass

"Mangia's" did not match "mangia". The fuzzy match now also accepts a
possessive or plural `s` on either key.

## Effect on the original model's headline (reweighted)

| metric | before | after |
|---|---|---|
| comment drop rate | 0.232 | 0.230 |
| mention recall | 0.730 | 0.733 |
| negative-mention recall | 0.464 | 0.464 |
| value-complaint recall | 0.490 | 0.490 |
| sign accuracy | 0.958 | 0.972 |

The headline barely moves: the original model's failures were real.
