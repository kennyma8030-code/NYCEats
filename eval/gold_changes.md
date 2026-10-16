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

---

# v5: the gold under the v5 schema

`eval/gold_v5.jsonl` and `eval/v2/gold_v5.jsonl` hold the v1 and v2 gold in the
v5 schema (`label_version: 3`). `eval/convert_gold_v5.py` writes them. It maps
the blind labels mechanically, then applies the hand decisions in
`labels_v5/overrides.py`, then the provisional conventions. The old gold files
are untouched; the old scorer still reads them. Every override names its
comment and mention and gives a reason, so each change can be audited against
the blind label.

Every mention the new schema treats differently was re-read: every old food
+1 (434), every all-null mention (338), every dish without a verdict, every
price, every avoid, every mixed level, every comment saying "not worth" and
every thread whose question carries a judgment. An override exists only where
the mechanical default was wrong: 292 entries over 265 mentions.

## Rules applied

- **Bare endorsement.** v1 scored a name given as an answer, with nothing
  said, as food +1. v5 leaves every aspect null (contract rule 1). Old +1s
  that were real mild judgments ("solid", "I like", "looks so good", "pretty
  decent") were restored to `decent` by hand. A food +1 that came with a dish
  verdict is never bare: where the comment judges only dishes, c1 takes food
  from them (48); where it gives an overall verdict, the label stays (9).
- **Reference only.** An all-null mention (v1 already gave every bare answer
  +1) and every closed place became `reference_only`. A v1 food +1
  alternative on an all-null mention meant "could be read as an answer", so
  those mentions mark `reference_only` uncertain rather than keeping a food
  alternative.
- **Comparison losers** (convention 5): a place that loses a comparison and is
  not praised became food `meh` instead of a reference. A place used only as a
  yardstick stays a reference.
- **"ok / fine / alright / mid"** are `meh`, never `mixed` or `decent`.
- **Dishes.** A positive level is liked, a negative level or an avoid is
  disliked, a null or 0 level is mentioned (v5 has no mixed-dish list). Praise
  of the meal that covers named dishes moves them to liked (rule 6). On a
  reference, every dish is mentioned, including dishes remembered at a closed
  place (convention 8).
- **Price** maps from expensiveness (-3/-2 cheap, -1 cheap with moderate
  accepted, 0 moderate, +1 pricey with moderate accepted, +2 pricey with
  very_pricey accepted, +3 very_pricey), but only when the price is stated in
  words (convention 7). A price taken only from a dollar figure became null.
- **Descriptors** are the old descriptors plus the old `search_terms` that are
  not part of a dish name, minus anything only asked about (rule 4), plus the
  evaluative words the review added. They are a recall target only: v1 never
  labeled evaluative descriptors, so descriptor precision cannot be scored.
- **Experience.** `is_firsthand` true/false/null became ate_there/secondhand/
  unclear, a bare endorsement became unclear, and the conventions below
  adjusted the rest.
- **Judgment-carrying questions** (rule 2) are classified per thread in
  `labels_v5/threads.py` and scored at the level the question's own words
  carry ("worst service" is service awful, "most overrated" food meh). The
  first relay said "plain level"; that was corrected before this was built.

## Provisional conventions, tagged for reversal

Conventions 1-4 are not yet confirmed with the user. Each mention a convention
decided carries `conventions: {id: {field: value without it}}`, so reversing
one is a mechanical rewrite of those mentions.

| convention | rule | mentions (scored) |
|---|---|---:|
| c1 | with no overall food verdict, food takes the dishes' own level (a disliked dish is at most meh), or mixed when they disagree; value or the wait do not stop it | 50 (50) |
| c1_assumed | a c1 liked dish with no v1 level, taken as good | 0 |
| c2 | an avoid with no negative aspect gets food bad (13); bare "skip X" scored meh in v1 moved to bad (4) | 17 (17) |
| c2_nonquality | also tagged: an avoid for a reason that is not quality (Sweetgreen's politics, "it's all seafood") | 3 (3) |
| c3 | a verdict in the commenter's own voice is ate_there (93); a reference is unclear unless it shows a visit (157); an explicit experience decision always wins | 250 (124) |
| c4 | bare "not worth it" as advice is an avoid (5); "not worth the price / the line" is value or wait bad and not an avoid (15, two of them were avoids in v1) | 20 (20) |

## Change counts

Counted over unique comments (v2's 244 v1 comments count once).

| change | mentions |
|---|---:|
| mentions | 1369 |
| override entries / mentions with an override | 292 / 265 |
| not scored (ambiguous or out of scope) | 172 |
| old food +1 alone | 434 |
| food +1 with no dish verdict (v1's "named as an answer") | 377 |
| &nbsp;&nbsp;-> bare endorsement (food null) | 284 |
| &nbsp;&nbsp;-> kept as a mild judgment | 88 |
| &nbsp;&nbsp;-> reference_only | 5 |
| food +1 with a dish verdict | 57 |
| &nbsp;&nbsp;-> judges only dishes: food from the dishes (c1) | 48 |
| &nbsp;&nbsp;-> an overall food verdict: label kept | 9 |
| old all-null | 338 |
| &nbsp;&nbsp;-> reference_only | 315 |
| &nbsp;&nbsp;-> not a reference (avoid, comparison loser, dish verdict) | 23 |
| closed -> reference_only | 41 |
| reference_only marked uncertain | 67 |
| judgment_question set | 1 |
| became meh (fine/ok/alright, comparison loser, disliked dish) | 11 |
| other levels changed by review (food 6, value 1, wait 1) | 8 |
| dish level 0 -> mentioned | 8 |
| dishes moved to liked by meal-level praise | 3 |
| descriptors edited by review | 7 |
| price kept (stated in words) / nulled (dollar figure only) | 39 / 31 |
| experience ate_there -> unclear | 440 |
| experience unclear -> ate_there | 48 |
| experience secondhand -> ate_there / unclear | 2 / 1 |
| experience unclear -> secondhand | 1 |

`labels_v5/changes_v5.py` reproduces this table.

## Borderline calls, by item

| item | mention | call |
|---|---|---|
| c0025 | The Modern, Per Se | an answer to a factual question (who sells gift cards) inside a request for places: bare endorsement, reference_only uncertain |
| c0087 | Hi-Collar, Konbon, Ichiban Tei | relays what other comments suggested: reference, uncertain |
| c0246 | Beer Street South | answers a business question (bars that host pop-ups): reference, uncertain |
| c0264 | Radio Bakery | says what they ordered and will try, no judgment: reference, uncertain |
| c0045 | Serafina | the one bare name answering a judgment-carrying question ("poor quality yet expensive, for an enemy"): food bad, value bad, judgment_question |
| c0214 | Mama's Too and 3 others | "just avoid all these spots tomorrow" warns about a 184-person crawl: wait bad, not food |
| t005 | Sweetgreen (2 comments) | an avoid for a political reason: c2 still sets food bad, tagged |
| v0259 | Chef's Table at Brooklyn Fare | "avoid, it's all seafood and uncooked" is a reason about the asker's diet: c2 food bad, tagged |
| v0274 | Dominique Ansel | skip the cronut line, the cookie is awesome: dishes disagree, food mixed (c1) |
| v0420 | Golden Bull handmade noodles | a terrible sandwich, but "good enough for my regular rotation": the overall verdict wins, food good |
| v0420 | Joju, MalaTang | "both fine and I'd go again": fine is meh, mixed accepted |
| v0294 | Dallas BBQ | good wings, bad brisket, "those wings make a trip worth it": decent, mixed accepted |
| v0329 | Fette Sau | closed, remembered as "the worst ribs": still a reference with null aspects |
| t004 p67vvqn | Mama's Too | "dying to try their elote slice": eager but untried, so the dish is mentioned, not liked |
| v0258 | Gray's Papaya | loses a comparison but "Love Grays": praised, so not meh |
| v0363 | Radio Bakery | "the tomato croissant was just ok": ok is meh, so the croissant is disliked and food is mixed (c1) |
