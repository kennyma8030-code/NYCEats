# Why Haiku 5.5 (v6 round 3, low reasoning) gets comments wrong

Source: the Opus review in `eval/review_v6/judgments/` (600 comments). The 58 items listed in
`.sealed/key.json` are excluded (their outputs were planted), leaving **542 real items with 615
Haiku mentions**. An *error* is any `compare` entry whose `final` differs from Haiku's value
(`right` = `judge` or `neither`), plus every place in `missed` with no `_mention` entry. That gives
**535 errors in 261 items**: 504 where the judge's first read was upheld and 31 `neither`, most of
which need context Haiku could not see.

Every error was classified by reading the comment, what Haiku saw, Haiku's whole output and the
judge's reason. It does not rely on the reason text alone. One line per error, with cause, pattern
and a one-line analysis, is in `errors.jsonl` next to this file.

Cause codes:
**A** rule missing from the prompt · **B** rule present but unclear or ambiguous · **C** rule present
and clear but ignored · **D** the rubric has a calibration the round-3 prompt lacks or contradicts ·
**E** the schema invites it · **F** input or context problem · **G** likely model limit ·
**H** the judge may be wrong, or the case is genuinely ambiguous (the owner needs to decide).

## Headline

- **About 60% of the errors (≈320 of 535) can realistically be fixed** without changing models:
  ≈300 by prompt and schema changes and ≈17 by showing more context. About 12% (64) look like
  model limits (sarcasm, implicit references, long rants), and about 6% (34) are judge or rubric
  ambiguity that the owner has to settle before anyone can be graded on them. The rest is the
  expected miss rate of the fixes themselves (see §6).
- **The biggest single lever is the prompt's own text.** Five lines in round 3 tell Haiku to do what
  the rubric marks wrong (cause D, 70 errors, plus about 30 B errors that the same lines trigger):
  1. the very_negative row is labelled "strong" and lists "never again" and "regretted going";
  2. rule 5 says a comparison loser "far worse" is very_negative;
  3. the overall field's example says "go early to beat the line" has no overall;
  4. the overall field says "Best slice in the city" makes overall very_positive;
  5. the timeframe field says "a visit years ago with nothing about now" is past.
  The prompt also has no "bottom line / strongest point" rule for overall.
- **Over-scaling is systematic.** Haiku used very_negative 71 times and the judges cut 36 of them
  (51%). It used very_positive 60 times and 36 were cut (60%). Neutral overall was right in only
  6 of 15 uses.
- **Experience is broken in both directions.** "secondhand" was wrong in 32 of 43 uses (74%), and
  "none" in 44 of 128 (34%). Haiku reads "no visit described" as "none" and "replying about
  someone else's pick" as "secondhand", although the prompt says firsthand is the default.
- **Overall is null too often.** 139 mentions had overall null, and 54 of those were overturned
  (39%). Usually there was a judgment on one aspect or dish, or a pick, and Haiku did not lift it
  into overall.
- **Notes soak up structure.** 15 complaints and 23 dishes were recorded only in `notes`, which have
  their own `level` and `dish` slots.
- **Errors do not concentrate in long, many-place comments; they concentrate in short replies.**
  The share of mentions with any error falls from 61% in one-place comments to 31% in comments
  with five or more places. Places named only in the context (replies about the parent's or the
  post's place) carry an error 53% of the time, against 40% for places the comment names. Lists
  do produce *correlated* errors: four list comments account for 33 errors (§5).

## 1. Cause × field

| field | A | B | C | D | E | F | G | H | total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| overall | 11 | 22 | 15 | 54 | 1 | · | 10 | 2 | 115 |
| taste | 1 | 25 | 11 | 5 | 4 | · | 2 | 4 | 52 |
| value | · | 3 | 3 | 2 | 2 | · | 2 | 2 | 14 |
| service | · | 1 | 2 | 3 | 5 | · | · | 3 | 14 |
| atmosphere | 1 | 2 | 2 | · | 1 | · | 2 | 4 | 12 |
| wait | · | 2 | 5 | 1 | · | · | 2 | 1 | 11 |
| experience | 4 | 18 | 45 | · | · | · | 7 | 6 | 80 |
| opinion | 11 | 19 | 15 | · | · | · | 9 | 3 | 57 |
| avoid | · | 6 | 1 | · | · | · | 1 | 1 | 9 |
| dish | 1 | 16 | 9 | 5 | 18 | 1 | 12 | 2 | 64 |
| price | · | 2 | 5 | · | · | · | · | · | 7 |
| timeframe | · | 14 | 3 | · | · | · | · | · | 17 |
| trend | · | 7 | 1 | · | · | · | 1 | 1 | 10 |
| status | · | 4 | 3 | · | · | · | 2 | · | 9 |
| mention | 2 | 5 | 15 | · | · | 23 | 14 | 5 | 64 |
| **total** | **31** | **146** | **135** | **70** | **31** | **24** | **64** | **34** | **535** |

Reading the table:
- Most **overall** errors are D (54): the scale calibration and the missing bottom-line rule.
- **experience** is mostly C (45): a clear default that Haiku ignores, discussed below.
- **dish** errors are mostly E (18): the dish was recorded in a note.
- **mention** errors are mostly F (23): the place is named only in an ancestor, or past the 400-character cut of the post.

## 2. Cause × pattern

"est. fixable" is my expected number of these errors that a realistic prompt, schema or input
change would fix (per-pattern rate × count; G counted at 10% and H at 0). §6 has the method.

| pattern | A | B | C | D | E | F | G | H | total | items | est. fixable |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| exp_none_default | · | 5 | 27 | · | · | · | 1 | 1 | 34 | 27 | 22 |
| overscale_pos | · | 15 | 17 | · | · | · | · | 1 | 33 | 22 | 22 |
| missing_verdict | · | · | 3 | 28 | · | · | 2 | · | 33 | 25 | 25 |
| overscale_neg | · | · | · | 31 | · | · | · | 1 | 32 | 23 | 28 |
| untried_scored | 29 | · | · | · | · | · | · | · | 29 | 14 | 23 |
| exp_secondhand_uncredited | · | 7 | 15 | · | · | · | 1 | 2 | 25 | 21 | 15 |
| dish_omitted | · | 1 | 1 | · | 17 | · | 4 | · | 23 | 18 | 14 |
| endorse_missed | · | 7 | 6 | · | · | · | 9 | · | 22 | 8 | 7 |
| missed_needs_context | · | · | · | · | · | 19 | · | · | 19 | 18 | 13 |
| comparison_side_missed | · | 6 | 9 | · | · | · | 3 | · | 18 | 9 | 9 |
| aspect_not_set | · | 14 | · | · | 1 | · | 1 | 2 | 18 | 16 | 11 |
| complaint_only_in_note | · | · | · | · | 13 | · | 1 | 1 | 15 | 12 | 11 |
| endorse_vs_stated | · | 7 | 6 | · | · | · | · | · | 13 | 8 | 8 |
| dish_get_x_unleveled | · | 10 | 2 | · | · | · | · | · | 12 | 5 | 10 |
| non_place_extracted | 2 | · | 4 | · | · | · | 3 | 3 | 12 | 12 | 4 |
| sarcasm_missed | · | · | · | · | · | · | 11 | · | 11 | 4 | 1 |
| timeframe_wrong_past | · | 11 | · | · | · | · | · | · | 11 | 11 | 10 |
| neutral_not_bottom_line | · | · | · | 10 | · | · | · | · | 10 | 8 | 8 |
| underscale | · | · | 5 | · | · | · | 4 | · | 9 | 6 | 3 |
| missed_in_passing | · | 1 | 4 | · | · | · | 3 | 1 | 9 | 7 | 3 |
| missed_implicit_reply | · | · | 4 | · | · | · | 4 | 1 | 9 | 9 | 2 |
| wait_tip_not_scored | · | · | 7 | · | · | · | 1 | 1 | 9 | 6 | 4 |
| nonverdict_scored | · | · | 2 | · | · | · | 4 | 3 | 9 | 5 | 1 |
| post_place_attributed | · | · | 3 | · | · | 5 | · | · | 8 | 7 | 5 |
| avoid_false_positive | · | 6 | 1 | · | · | · | · | 1 | 8 | 4 | 6 |
| closed_fondness_missed | · | 8 | · | · | · | · | · | · | 8 | 3 | 7 |
| aspect_spurious | · | 4 | · | · | · | · | · | 3 | 7 | 6 | 2 |
| trend_spurious | · | 7 | · | · | · | · | · | · | 7 | 7 | 6 |
| status_missed | · | · | 4 | · | · | · | 2 | · | 6 | 4 | 2 |
| polarity_flip | · | 5 | · | 1 | · | · | · | · | 6 | 2 | 4 |
| passing_name_endorsed | · | 6 | · | · | · | · | · | · | 6 | 1 | 4 |
| timeframe_closed_not_past | · | 3 | 2 | · | · | · | · | · | 5 | 5 | 4 |
| business_news_as_verdict | · | 5 | · | · | · | · | · | · | 5 | 2 | 4 |
| status_wrong | · | 4 | · | · | · | · | · | · | 4 | 4 | 3 |
| mixed_aggregation | · | 2 | · | · | · | · | · | 2 | 4 | 4 | 1 |
| post_verdict_imported | · | · | · | · | · | · | · | 4 | 4 | 1 | 0 |
| dish_wrong_level | · | · | · | · | · | · | 2 | 1 | 3 | 3 | 0 |
| trend_missed | · | · | 1 | · | · | · | 1 | 1 | 3 | 3 | 0 |
| spurious_context_mention | · | 3 | · | · | · | · | · | · | 3 | 3 | 2 |
| value_from_price | · | 2 | · | · | · | · | · | 1 | 3 | 3 | 1 |
| price_from_value | · | · | 3 | · | · | · | · | · | 3 | 3 | 2 |
| wrong_referent | · | · | · | · | · | · | 3 | · | 3 | 2 | 0 |
| agreement_ambiguous | · | · | · | · | · | · | · | 2 | 2 | 1 | 0 |
| neutral_vs_negative | · | · | · | · | · | · | · | 2 | 2 | 2 | 0 |
| dish_wrong_place | · | · | · | · | · | · | 2 | · | 2 | 2 | 0 |
| comparison_misapplied | · | · | 2 | · | · | · | · | · | 2 | 2 | 1 |
| price_from_relative | · | 2 | · | · | · | · | · | · | 2 | 2 | 2 |
| agreement_aspects_missed | · | 2 | · | · | · | · | · | · | 2 | 1 | 1 |
| price_missed | · | · | 2 | · | · | · | · | · | 2 | 1 | 1 |
| avoid_missed | · | · | 1 | · | · | · | 1 | · | 2 | 2 | 1 |
| aspect_from_overall | · | · | 2 | · | · | · | · | · | 2 | 1 | 1 |
| endorse_not_positive | · | · | 1 | · | · | · | · | · | 1 | 1 | 1 |
| value_complaint_missed | · | · | 1 | · | · | · | · | · | 1 | 1 | 0 |
| missed_unusual_name | · | · | · | · | · | · | 1 | · | 1 | 1 | 0 |
| missed_excluded_as_nonplace | · | 1 | · | · | · | · | · | · | 1 | 1 | 1 |
| dish_duplicate | · | 1 | · | · | · | · | · | · | 1 | 1 | 0 |
| exp_firsthand_for_reaction | · | 1 | · | · | · | · | · | · | 1 | 1 | 0 |

## 3. Patterns: what Haiku did, examples, cause, fix

Quotes are verbatim from the comment (or from the parent or post where noted). The fixes are
written as replacement prompt text for `eval/prompts/v6_common.py` unless they say schema or input.

### 3.1 Level calibration

#### overscale_neg (32 errors, D 31, H 1)
**What Haiku did:** gave very_negative to strong but ordinary knocks, on overall, taste, service,
value, wait and dishes alike, often on every field at once.
- Q0311 El Taco: *"it was awful the second time. That was enough for me to not go back ever again"* → overall and taste very_negative.
- Q0509 Radio Bakery: *"Mid level bland fauxcoccia. Shop Rite quality pastries. Long painful waits. Priced to kill."* → six fields very_negative.
- Q0570 Soothr: *"This spot and Mitr are way better than Soothr"* → Soothr very_negative.

Others: "sucks" (Q0065, Q0250), "genuinely terrible" (Q0374), "the service was terrible" (Q0485),
"def gonna avoid now" (Q0140), "Cannot recommend" (Q0298), "miles better than Junoon" (Q0595).
**Cause D.** The round-3 SCALE row reads `very_negative  strong: ... "never again", "regretted
going" ...`, and rule 5 says the loser is "very_negative if the comment says it is far worse".
Both contradict the rubric ("extremes only; never again, regretted going, disappointing, overpriced
are negative").
**Fix:** replace the two scale rows and rule 5's middle clause:
```
  negative       any knock, however mild, polite or strong: "fine", "ok", "meh", "mid", "nothing special",
                 "overrated", "bland", "disappointing", "overpriced", "a ripoff", "rude", "hard to book",
                 "the line is insane", "bad", "terrible", "awful", "sucks", "never again", "won't go back",
                 "regretted going", "cannot recommend", "don't waste your time", "I'm boycotting it"
  very_negative  ONLY an extreme: "worst I've ever had", "inedible", "disgusting", "gross", "got sick",
                 "food poisoning", "avoid at all costs". Swearing, emphasis and stacking several knocks do
                 not make a knock extreme. Set it only on the field the extreme word is about.
5. ... The loser is negative ("I prefer A over B", "A is way / miles better than B": B negative), and
   positive if the comment says both are good. It is very_negative only when the loser itself is
   described in extreme words.
```

#### overscale_pos (33 errors, C 17, B 15, H 1)
**What Haiku did:** gave very_positive for enthusiasm with no broad superlative. It also lifted a
dish-level or local superlative to taste or overall, and inherited the asker's "best".
- Q0050 Mama's Too: *"They are my favorite!"* → overall and taste very_positive, although the prompt lists "my favorite" as positive (C).
- Q0358 Tony's di Napoli: *"One of the best meals we've had lately and the service is top notch!"* → overall, taste and service very_positive. The prompt lists "one of the best meals of my life", and "lately" bounds it (B).
- Q0556 Bagel Pub: *"Bagel pub is best (and makes the best breakfast sandwiches)"*, asked about near Barclays → very_positive (B, a local frame).

Others: "bomb af" (Q0102), "superb restaurant" (Q0107), "so so cozy" (Q0174), "to die for" (Q0127),
"pretty damn incredible" (Q0406), "does not miss" (Q0302), "showstopper" (Q0034); a dessert
superlative turned into taste very_positive (Q0211); "Utopia Bagel's country chicken salad" given
very_positive taste because the title asked for "the best" (Q0367).
**Cause C/B.** The positive row already lists "amazing" and "my favorite", but the very_positive row
gives only positive examples of a superlative and none of what is *not* one. The example "Best
slice in the city is overall and taste very_positive" teaches Haiku to lift a dish superlative to
overall (Vato, Q0070).
**Fix:**
```
  very_positive  ONLY when the commenter ranks THIS place (or this dish) at the top of a broad class: "best in
                 the city", "best X I've ever had", "my favorite in NYC", "one of the best meals of my life",
                 "nowhere else comes close". NOT very_positive: "my favorite", "my go-to", "amazing",
                 "incredible", "superb", "to die for", "bomb", "top notch", "does not miss", "a showstopper",
                 "something else", "so so cozy", "beautiful"; a superlative over a small class or time
                 ("best on the UES", "best near Barclays", "best I've had lately", "better than most spots");
                 and a bare pick answering a "where's the best X?" question (the asker's "best" is not the
                 commenter's).
overall     ... A superlative about one dish sets that dish (and taste) very_positive; overall is
            very_positive only when the commenter ranks the place itself.
```

#### neutral_not_bottom_line (10 errors, D)
**What Haiku did:** when a comment had good and bad points, it averaged them to neutral even
though the commenter gave a bottom line.
- Q0453 Los Tacos: *"I like it very much, but when 3 tacos and a drink is nearing 30 bucks it becomes very not worth it very fast"* → neutral, final negative.
- Q0558 Westville: *"Eh, I like westville and order from them quite a bit, but seems like their food is really on the oily side"* → neutral, final positive.
- Q0456 Hungry Spicy: *"This is the right answer. It's not very tasty IMO but if you want to challenge yourself with spice, this is the place to go."* → neutral, final positive.

Also Q0173 (agreeing Semma is overhyped), Q0190 (cancelled the membership), Q0251 ("some people
don't like them. Valid but RIP to their vegan soft serve"), Q0258 ("It is good though"), and Q0465
("welcome additions... the best in the area").
**Cause D.** The rubric says overall "follows the commenter's bottom line if they give one, otherwise
their strongest point". The prompt defines neutral as "good and bad weighed evenly" and says
nothing about a bottom line.
**Fix:** this is the overall text in §7. Add to the neutral row: "never when the commenter gives a
bottom line; other people's views ('some people hate it') are not the commenter's".

#### polarity_flip (6 errors, B 5, D 1)
- Q0370: a list under the title *"List of terrible restaurants in NYC with great customer reviews"*, followed by *"I've always had great experiences here"*. Haiku made 5 of the 6 places negative and avoid (and Beauty & Essex positive).
- Q0281 Bungalow: *"Biryani was underwhelming but the lamb was amazing"*, as the answer to the question → overall negative.

**Cause:** rule 11 ("thread framing ... decide polarity") has no precedence clause (B). For Bungalow,
the missing strongest-point rule (D).
**Fix:** rule 11 becomes "Thread framing and sarcasm decide polarity only when the comment gives
none of its own: 'second this' under 'worst meal you've had?' is negative. The commenter's own
words win over the framing ('I've always had great experiences here' makes the list positive).
Framing never sets avoid."

#### underscale (9 errors, C 5, G 4) and mixed_aggregation (4: B 2, H 2)
- Q0167 Red Hook Tavern: *"It is the best burger in nyc currently"*, from a commenter whose whole comment is a defense of the place → overall positive.
- Q0005 / Q0567: *"overpriced and gross"*, *"gross sandwich"* → taste and dish only negative.
- Q0334: *"nowhere really exceptional after those two closed"* is an implicit best-in-city (G).

Mixed: Q0137 *"The brisket at Hill Country is very good most of the time, though the sides are kinda
terrible"* → taste positive with overall neutral; Q0519 Bagel Pub taste neutral where final is
positive.
**Fix:** the new very_negative row names "gross" and "disgusting". For taste, use the aggregation
sentence in the aspects text of §7.

### 3.2 Missing verdicts

#### missing_verdict (33 errors, D 28, C 3, G 2)
**What Haiku did:** marked the place stated and set an aspect or dish level, but left overall null.
- Q0571 Mama's Too: *"Those lines are brutal"* → wait negative, overall null.
- Q0533 Centro: *"Well I went to Centro and it had Grade Pending, but tasted great"* → taste positive, overall null.
- Q0408: *"Great NY Noodle town for soft shell crab / Noodle village for soup dumplings..."* → five recommendation-list items marked stated, dish positive, overall null.

Also Q0090 ("Mapo banchans are so good"), Q0177 ("$12.00 smoothie"), Q0178 ("It would be faster
to get on the Jitney ... Yikes."), Q0317 ("Katz's is my favorite but probably not worth the line"),
Q0337 (meatballs returned), and Q0335 (Via Carota and L'Artusi offered as walk-in picks).
**Cause D.** The rubric: overall follows the bottom line, else the strongest point, and is null only
with no verdict. The prompt's only guidance points the other way: *"'go early to beat the line' has
no overall (null)"*, and *"aspects ... never infer one aspect from another or from overall"*, which
Haiku also applies in reverse.
**Fix:** the overall field text in §7. Delete the "go early" example and replace it with "a neutral
tip with no judgment ('they open at 11', 'go on a weekday') has no overall; 'the line is brutal' is
overall and wait negative". Schema/validator: if `opinion` is stated or endorse, every non-null
aspect or dish level agrees in sign, and overall is null, set overall to that sign (deterministic),
or re-ask.
*(Owner question: the judges did not flag a pure booking tip, "Be there at 11:30" (Q0037), with
overall null, but did flag "the lines are brutal". The rule above keeps that split.)*

#### comparison_side_missed (18 errors, C 9, B 6, G 3) and comparison_misapplied (2, C)
**What Haiku did:** judged one side of a comparison and left the other side opinion none or overall
null, or set the right side but not the compared aspect.
- Q0010: *"Except the food wasn't like Carbone. Parm was bad."* → Carbone opinion none (the winner).
- Q0186: *"Mamas too is pretty good, but Village Square is only a couple blocks away, cheaper, and never has a line"* → Mama's Too gets no value or wait knock, and Village Square no overall.
- Q0455: *"Switch out Rubrirosa with Joe and Pats unless you have a reservation at Rubirosa."* → Rubirosa overall null.

Also: "Carbone's picks you so Don Agnie is probably your best bet" (Q0288); "Take them to parm"
answering "is Carbone worth it" (Q0304); "walk a bit to Heaven's Hot Bagels... $12 for way more"
(Q0562); and Q0156 *"It's good... The corner is better"*, where Haiku made the loser's taste
negative although both are called good.
**Cause:** rule 5 is clear about the loser (C), but it doesn't say that "instead" or "switch"
phrasing is a comparison, or which aspect the compared trait goes to (B).
**Fix:** rule 5:
```
5. A comparison judges both sides, including "go to A instead", "switch B for A", "B is impossible
   to book, so A", "A is better / cheaper / has no line". Both places are mentions with opinion
   stated. The winner is overall positive; the loser overall negative unless the comment calls it
   good too. The compared trait sets the aspect on both sides: food → taste, cheaper or more for
   the money → value, line or booking → wait. Note the comparison on each.
```

#### wait_tip_not_scored (9 errors, C 7, G 1, H 1)
- Q0070 Sunday Morning: *"Recommend getting there just before they open."* → no wait level.
- Q0326 Los Tacos No. 1: *"would probably have a shortish line for dinner compared to lunch"* → opinion none, wait null.
- Q0335 Bad Roman: *"looks like they have an opening"* → opinion none.

**Cause C.** Rule 1 gives "be there by 11:30" as wait negative and "free tables at 4" as wait
positive. **Fix:** move these examples into the `wait` aspect definition itself (`wait: ... "be
there before they open", "go late on a weeknight to get in" are wait negative; "shortish line at
dinner", "they have an opening", "easy walk-ins" are wait positive`), so they sit where Haiku sets
the field.

#### closed_fondness_missed (8 errors, B), status_missed (6: C 4, G 2), endorse_not_positive (1, C)
- Q0299: *"RIP Stage Restaurant too"* → opinion none.
- Q0218: *"Too bad it closed down like plenty of other businesses."* → opinion none.
- Q0369: *"rip ice and vice."* → opinion none, status null. Haiku's own note says "possibly implies it is gone".
- Status: Q0080, under *"If you could bring back one closed restaurant"*, timeframe past but status null; Q0520 *"The new space"* (moved); Q0463 *"K-Paul's had a branch here..."*.
- Q0139: *"Or Brennan and Carr. They'll douse it in cheese too."* → endorse with overall null.

**Fix:** rule 10 becomes "A closed place remembered fondly ('I miss it', 'RIP X', 'too bad it
closed', named under 'which closed place would you bring back') is stated, overall positive,
status closed, timeframe past." Validator: endorse ⇒ overall positive.

### 3.3 Who is speaking, and is it an opinion at all

#### untried_scored (29 errors in 14 items, A)
**What Haiku did:** scored reactions from people who have not been as endorse or stated positive,
often as "secondhand".
- Q0007: *"Omg this looks so good. Def gonna order"* → secondhand, endorse, positive, and a dish from the parent.
- Q0025: *"I was skeptical, but it looks tasty"* → stated, overall and taste positive.
- Q0597: *"🙂 Thanks! We will check it out!"* → secondhand, endorse, positive.

Also "Thank you!! Marked, looks so nice" (Q0004), "Lovely! Did you have to book far in advance?"
(Q0033), "Awesome. Been meaning to try" (Q0047), "Seems like woodside is the place to be" (Q0313),
and "I gotta try their truck spot" (Q0544).
**Cause A.** Nothing in the prompt covers impressions of an untried place, and the rubric doesn't
either: judges raised it in seven rule questions. **The judges also split.** In 10 items they
wanted opinion none and overall null. In 4 they wanted stated or positive: Q0363 "looks delicious",
Q0385 "sounds FIRE", Q0438 "looks so good. I've never been", Q0596 "that lotus flavor looks
incredible". The owner must pick one.
**Fix (recommended, matching the 10-item majority):**
```
13. A place the commenter has not tried. Reactions to the post's photos or someone's description
    ("looks so good", "Lovely!", "sounds amazing"), plans ("def gonna order", "marked", "been meaning
    to try", "we will check it out") and thanks for a recommendation are experience "none", opinion
    "none", overall null, every aspect and dish null. They are not "secondhand" (no one's verdict
    is passed on) and not "endorse" (nothing is recommended to readers).
```

#### exp_none_default (34 errors, C 27, B 5, G 1, H 1)
**What Haiku did:** gave experience "none" to picks and verdicts in the commenter's own voice, in
20 cases to a bare endorse.
- Q0467: *"Java in Park Slope"* → none.
- Q0546: *"jeeze skip lenwich"* → none.
- Q0323 (B): *"They have it in Taskin Bakery outpost, midtown east."* → none (a pick phrased as a fact).

Others: "spicy rigatoni at Parm" (Q0060), "Add S&P" (Q0284), "Blue haven in murray hill will
undoubtedly be crazy" (Q0429), "Cocodaq though is an abomination" (Q0565), and the comparison
losers above.
**Cause C,** with a B overlap: the prompt says firsthand covers "any pick, list item or verdict in
their own voice", but also "none ... for bare facts". Haiku apparently asks whether a visit is
described, and treats a fact-shaped pick ("you can find it at X") as a bare fact.
**Fix (prompt):** the experience text in §7 ("Do not ask whether a visit is described...").
**Fix (schema, optional):** rename the values so the default reads as the default:
`"source": "own" | "others" | "not_tried"`, ordered with `own` first in the enum, and put the field
after `opinion` so it is decided once the model knows whether there is a pick.

#### exp_secondhand_uncredited (25 errors, C 15, B 7, H 2, G 1)
**What Haiku did:** used "secondhand" for own-voice picks, hedges and replies about someone else's
place. Of its 43 secondhand outputs, 32 were overturned.
- Q0213: *"Gallagher's, Bobby Van's, Keene's, Smith and Wollensky (not in order of preference)"* → all four secondhand.
- Q0127: parent *"By The Way Bakery is by far the best I've had"*, comment *"Their coconut cake is to die for"* → secondhand.
- Q0384 (B): *"I think Matto has a banana-related coffee drink"* → secondhand.

**Fix:** "secondhand only when the comment names someone else as the source of the opinion: 'my
friend swears by it', 'heard great things', 'people here recommend it', 'reviews say'. A hedge ('I
think', 'might be'), a plain list, or a reply about a place someone else named is firsthand."
Validator: secondhand requires a source phrase. Without one, downgrade to firsthand.

#### endorse_missed (22: G 9, B 7, C 6), endorse_vs_stated (13: B 7, C 6), passing_name_endorsed (6, B)
**What Haiku did:** confused endorse, stated and none at the edges.
- Missed endorsements: Q0254 *"Yes, was going to suggest this place. Also in midtown ... is Boucherie"* → none (C); Q0497 *"Yeah pretty much the case"* under "every menu item sounds good" → none (C, rule 9); Q0101 *"Do it!"* to someone going to Utopia (G).
- Endorse where a praise word means stated: Q0540 *"my go tos were One More Thai and Lava Shawarma"*; Q0527 *"I also enjoy the egg salad with bacon"* (and no dish entry); Q0386 *"Another good one is Davelle"*.
- Stated where the judge wanted endorse: Q0408's "X for the Y" lists; Q0288 *"probably your best bet"*.
- Over-endorsed: Q0461, where *"vendors who have gone on to opening their own ... (Noodle Lane, Birria LES, Hen House comes to mind)"* got three endorsements.

**Cause:** the endorse definition ("a bare name or 'try X' with no word of praise") doesn't cover
"X for the Y", fact-shaped picks, "do it!" or agreement replies. It also doesn't separate names
given as examples from picks. **Fix:** the opinion text in §7. For scoring, endorse and stated both
count as praise, so this pattern mostly affects the opinion field, not rankings. The overall=null
side effect is covered by missing_verdict.

#### nonverdict_scored (9: G 4, H 3, C 2), business_news_as_verdict (5, B), post_verdict_imported (4, H)
- Q0128: a Steely Dan lyric naming Rudy's → endorse (G).
- Q0380 Wu's: *"Such a fun shot!"* (about a camera trick) → atmosphere positive (G).
- Q0231 / Q0297 Pressed and Juice Press: *"wasn't getting enough foot traffic"*, *"business was visibly dead"* → stated negative, trend declined, secondhand (B).
- Q0185 and Q0505: stated with every level null, for a question and for a general pricing essay (C; a validator can catch this).
- Q0224 (H): *"I did. They said they cannot investigate for up to 36 days"*. The poster may be the commenter, so whether the title's roach claims belong to this comment is unclear.

**Fix:** add to opinion none: "news about the business (closures, foot traffic, rent, expansion,
lawsuits) is not a judgment of the place". Validator: opinion stated ⇒ at least one level is set.

#### sarcasm_missed (11 errors in 4 items, G)
- Q0294: *"these dumplings are best in the city (actually, I'm a gatekeeping asshole and happy for traffic to grow at this spot instead - my fave is busy enough as it is!)"*.
- Q0495: *"Let me guess… $16 each?"*
- Q0022: *"They don't deserve the cleavage"*.
- Q0446: *"Hillstone has a nice view of 27th and Park I guess"*.

Rule 11 already covers sarcasm. Medium reasoning or a stronger model is the lever; a prompt line
won't move these much.

### 3.4 Where the judgment is stored: aspects, dishes, notes

#### complaint_only_in_note (15 errors, E 13)
**What Haiku did:** wrote the complaint as a note with level negative and left the aspect, dish or
overall unchanged.
- Q0449 Il Buco: *"they removed the flowers that we brought in during the meal"*, *"there was a leak on one side of the room"* → notes negative, service and atmosphere stay positive.
- Q0107 Kabawa: *"Kinda weird they only do prie-fixe"* → negative note only.
- Q0575: *"Their side kimchi was not tangy in a way that balanced the pancake"* → note only, no dish.

Also Q0118 (non-seasonal neta), Q0197 ("should have never leaned in to the delivery food stuff"),
Q0459 (bribing for ratings), Q0482 (health violations), and Q0504 ("that boring menu").
**Cause E.** Rule 2 says a note "never holds a complaint alone", but the note schema has a `level`
slot, so writing the note *feels* like recording the complaint. Some cases also lack a home: is
hygiene, menu format or a business choice "service"? (B)
**Fix (schema):** drop `level` from notes, so notes hold only text, or allow only null there. The
level then has to go into a structured field.
**Fix (prompt):** "service also covers how the place is run: hygiene and health violations, menu
format ('prix-fixe only'), ordering rules, business choices, fake reviews."
**Fix (validator):** a negative note with no negative aspect, dish or overall triggers a re-ask.

#### dish_omitted (23 errors, E 17, G 4)
**What Haiku did:** named the dish in a note (often in the note's `dish` slot) but not in `dishes`.
- Q0160 Malecón: *"Get extra green sauce."* → only a note "[tip|positive] get extra green sauce".
- Q0519 Bagel Pub: *"the spread and their salmon is amazing!"* → salmon is a dish, the spread only a note.
- Q0258 ADel's: *"Adel's has better hot sauce"*, *"equal rice seasoning and protein"* → notes only.

Also coffee (Q0148), beer (Q0480), chalupa (Q0442), "oysters and pearls" (Q0492), and smoothies
(Q0297). The G cases are dish attachment in long rants: Q0123, Q0342, Q0580.
**Cause E.** `notes[].dish` duplicates `dishes[]`, and the instruction "no note that only repeats
a level" pushes the model to put it in one place, and it picks the note.
**Fix (schema):** remove `dish` from the note object, or add a validator: every `note.dish` must
appear in `dishes`, with the note's level, and is added otherwise. Prompt: "every dish or drink
named for the place goes in dishes, even if it is also in a note".

#### dish_get_x_unleveled (12 errors, B 10, C 2)
- Q0295: *"Mazemen: - Shuya - Susuru Ramen ..."* → mazemen null at each place (6 errors). The same comment's "Standout vegetarian ramen:" heading was leveled positive.
- Q0012: *"You need to try their elote slice"* → null.
- Q0482: *"Space Market for late night or morning BEC"* → null.

**Fix:** dish level "positive for 'get / try the X', 'X for the Y', a dish heading over a list
answering 'where for Y' ('Mazemen: A, B'), and 'either the steak frites or the burger'".

#### aspect_not_set (18 errors, B 14, E 1, G 1, H 2) and aspect_from_overall (2, C)
**What Haiku did:** praised or knocked a dish but left taste null, the reverse of copying overall
into taste.
- Q0103: *"newsbar cafe is great. love the chicken sausage hash wrap"* → dish positive, taste null.
- Q0524: *"Slop indeed."* → overall negative for three chains, taste null.
- Q0337: *"Magnolia Bakery is only good for that Banana Pudding"* → overall negative, taste null.
- The opposite: Q0556 *"Black seed is terrible. Bergen bagels is alright."* → overall copied into taste.

**Cause B.** "Only what is said; never infer one aspect from another or from overall" reads to
Haiku as "a dish is not the food". **Fix:** the aspects text in §7.

#### aspect_spurious (7: B 4, H 3), agreement_aspects_missed (2, B), dish_wrong_level / place / duplicate (6: G 4, B 1, H 1)
- Q0055: *"Vibe wise both are great. Both will be packed and lively."* → wait negative. The prompt's "busy even in the rain" example invites this (B).
- Q0304: *"more casual"* (fit for a tween) → atmosphere positive; Q0492 *"all seafood and largely uncooked"* (fit for the asker) → taste negative.
- Q0530: *"Skip the fillet"*, advice for the poster's Wolfgang's reservation, was also attached to Benjamin (G).
- Q0267: *"Second this"* under *"Poor quality yet expensive restaurant recommendation"* → overall negative, but taste and value not set.

**Fix:** in the wait definition, "'packed', 'lively', 'popping' said as praise of the vibe is
atmosphere". Add "a remark about fit for one person (casual, kid-friendly, all seafood) is a note,
not a level". Rule 9: "an agreement reply also takes the aspects the agreed text names ('poor
quality yet expensive' → taste and value negative)".

### 3.5 Which places are mentions

#### missed_needs_context (19, F) and post_place_attributed (8: F 5, C 3)
- Q0071: *"Seconding the focaccia... The tomato croissant was just ok."* Radio Bakery is named only in the grandparent.
- Q0150: *"Its not that far from the queen's night market i think?"* The place, Rolo's, is in the post after the 400-character cut.
- Q0397: the parent's "this place" is Hani's (named in the ancestors), so Haiku guessed Petit Chou, the only bakery visible.
- C cases: Q0357 and Q0560 extracted Oases and Sweetgreen from the post (*"I have tried oases but their tofu is fried"*) although the comment never mentions them.

Of the 24 F errors, 21 need an ancestor above the parent, 1 is past the 400-character post cut
(Q0150), and 2 need both (Q0397).
**Fix (input):** in comment mode, add the nearest ancestor that names a place: either the
grandparent, or every ancestor trimmed to about 300 characters. Raise the post cut from 400 to
about 1,200 characters. Thread mode sees all of this already, which argues for routing replies
whose parent has no place name through thread mode.
**Fix (prompt, for the C cases):** "A place named only in the post or parent is a mention only if
the comment refers to it: by name, by 'it / they / this place / their', or by replying to what was
said about it. A comment that answers the post's general question, or talks about restaurants in
general, does not mention the places the post names. The post's or parent's verdict is not the
commenter's unless they agree with it."

#### non_place_extracted (12: C 4, G 3, H 3, A 2), spurious_context_mention (3, B), missed_excluded_as_nonplace (1, B)
- C: Q0076 *"Hanam is the only one I know of in NJ"* (outside NYC, said in the comment); Q0484 and Q0569 H Mart (a supermarket); Q0068 Tan Ting Hung, where the asker wants raw leaves to cook at home.
- A: Q0078 *"I have to say I love Grillos pickles!"* (a packaged brand); Q0135 *"Unapologetic Foods ... is selling the public the idea..."* (a restaurant group).
- G: Market Basket, Western Beef, Erewhon ("Air Juan"). Each needs world knowledge.
- H: Zabar's (Q0031, Q0468) and Pomegranate. The rubric itself is unsure about groceries with deli counters.
- The reverse: *"Carlos grocery in Brooklyn"* (Q0393), a sandwich deli, was dropped.

**Fix:** extend SCOPE's not-places list:
```
Not places: ... supermarkets and grocery stores (H Mart, Western Beef, Whole Foods), packaged-food
brands sold in stores, restaurant groups and companies, places outside the five boroughs (NJ, LA,
Long Island). A deli or sandwich counter with "grocery" or "market" in its name is a place.
```
The owner must rule on Zabar's, Pomegranate-style supermarkets with prepared food, and food halls.

#### missed_in_passing (9: C 4, G 3, B 1, H 1), missed_implicit_reply (9: C 4, G 4, H 1), wrong_referent (3, G), missed_unusual_name (1, G)
- Q0167: in a 400-word Red Hook Tavern essay, *"inspired by chef Durney's memories of the Peter Luger burger ... and Minetta Tavern's use of dry aged steak ... JG Mellon style"* → none of the three extracted (G).
- Q0476: *"There's certainly better burritos in NY (even Chipotle ffs)"* → Chipotle missed (C).
- Q0482: *"they recently combined with Ritz Diner"* → missed (C).
- Implicit replies: Q0134 *"They have al pastor which is pork"*; Q0352 *"They will avoid low density low traffic areas"*; Q0364 *"We've decided to go for lunch today"*; Q0116 *"Do you know roughly how much it is per pound?"* (all C).

**Fix:** SCOPE: "Every named food place counts, even as a comparison side ('even Chipotle is
better'), an inspiration ('inspired by the Peter Luger burger'), a style ('JG Mellon style'), a
merger ('combined with Ritz Diner') or a supplier ('anything that carries Shewolf'). A reply about
the post's or parent's place in any form (a fact, a plan, a question, a jab) is a mention of it.
Before answering, re-read the comment once for names you have not listed."

### 3.6 Time, status, price, avoid

#### timeframe_wrong_past (11, B) and timeframe_closed_not_past (5: B 3, C 2)
- Q0153: *"I used to work a few blocks away and we went for a work lunch there"* → past.
- Q0401: *"I went two years ago and had a similar experience"*, with present-tense criticism → past.
- Q0070 Vato: *"one of the best cinnamon rolls I had recently"* → past.
- The opposite: Q0044 *"Pig and Khao on the LES closed"* and Q0184 *"Chikalicious closed"* → status closed, timeframe current.

**Cause B.** The trigger is the prompt's own parenthetical, *"a visit years ago with nothing about
now"*. **Fix:** "timeframe 'past' when the place is closed (always, even with no levels) or the
comment says it has changed since ('used to be', 'back then'). An old or recent visit with nothing
about change is 'current'."

#### trend_spurious (7, B) and trend_missed (3: C 1, G 1, H 1)
- Q0211: *"Despite them just losing a star, they're still a top choice"* → trend declined.
- Q0404: *"Killed by proteinmaxing"* → declined.
- Q0344: the commenter stopped going → declined.
- Missed: Q0573 *"it's gotten to the point where you need to spend 25 dollars to be full"*; Q0137 *"kinda terrible these days"*.

**Fix:** "trend only when the comment says the place's food, service or experience got worse or
better. Not for closures, fewer customers, a lost Michelin star, a branch closing, the commenter
stopping going, or others' memories."

#### status_wrong (4, B)
- Q0482: *"they've been shut down a couple times"* → closed.
- Q0297: a few branches closing → the chain closed.
- Q0101: *"waiting for their new location to open"* → opened.
- Q0516: a parent's *"Allegedly reopening"* → opened.

**Fix:** "status describes the place, not one branch. A branch opening or closing, a temporary
shutdown and an alleged reopening are notes."

#### price and value confusion (10: price_from_value 3 C, price_from_relative 2 B, price_missed 2 C, value_from_price 3: B 2, H 1)
- Q0372: *"For some outrageous price"* → price expensive.
- Q0214: *"Lucia is pricier"* → price expensive and value negative.
- Q0208: *"quick inexpensive lunch"* → value positive as well as price cheap.
- Q0342: *"it's gonna be pricey"* → price null.

**Fix:** the price and value text in §7.

#### avoid_false_positive (8: B 6, C 1, H 1) and avoid_missed (2)
- Q0370: thread framing alone → avoid on five places (B).
- Q0451: *"If you're a tourist I would skip this, but ... Parm low key has an incredible roast beef sandwich"* → avoid (B).
- Q0153: the dish "chicken" marked avoid from a bad review alone (C).
- Missed: Q0476 *"No one ... should pay $20+ for that shitty ass burrito"*.

**Fix:** "avoid needs an instruction to readers in general: 'skip it', 'don't bother', 'make it
yourself instead', 'no one should pay $20 for that'. A conditional skip next to a recommendation,
thread framing, or a bad review alone is false."

### 3.7 H: where the judge may be wrong or the rubric is silent (34 errors)

These should not be "fixed" in the prompt until the owner rules:
- Untried impressions (above; the judges split 10:4).
- Groceries with deli counters (Zabar's ×2, Pomegranate).
- Whether a fit remark ("not somewhere I'd take a young kid") is an atmosphere knock.
- "is fun" as atmosphere; a kids activity as service.
- Hedged value ("much better at a similar price, though only 12 pieces"); "just pay the mark up".
- Debatable credit (Q0123 Bar Moga, Q0155 "the T-Swift favorite").
- Q0224, where the commenter may be the poster.
- Q0598: an observed opening time, firsthand vs none.
- Q0565: "should be burned to the ground" as avoid.
- Q0542: "disgusting" about roaches, setting service.
- Q0143: trend on a single aspect (booking).

## 4. Owner decisions needed before round 4

1. Untried impressions: opinion none (my recommendation) or stated positive with experience none.
2. Does a wait- or price-only remark carry overall? The rubric says yes ("strongest point"), but
   judges let a pure booking tip ("Be there at 11:30") stay null.
3. Zabar's and similar grocery-delis, supermarkets praised for prepared food, food halls and food
   courts, and packaged brands.
4. Whether "terrible" and "awful" are negative. The rubric's list implies yes, and this analysis
   assumed it.
5. Conditional avoid, and hyperbolic curses as avoid.

## 5. Long and multi-place comments

| final mentions in item | items | mentions | errors | mentions with ≥1 error | errors per mention |
|---|---:|---:|---:|---:|---:|
| 0 | 155 | 0 | 16 (wrongly extracted) | – | – |
| 1 | 292 | 292 | 300 | 61% | 1.03 |
| 2 | 44 | 88 | 80 | 58% | 0.91 |
| 3–4 | 29 | 99 | 56 | 39% | 0.57 |
| 5+ | 22 | 150 | 83 | 31% | 0.55 |

| comment length (chars) | items | errors per item | errors per mention |
|---|---:|---:|---:|
| <150 | 328 | 0.79 | 0.87 |
| 150–399 | 158 | 1.11 | 0.81 |
| 400–799 | 42 | 1.86 | 0.84 |
| 800+ | 14 | 1.71 | 1.00 |

- **Per mention, error rates fall as places per comment rise, and are flat in comment length.**
  The single-place reply is the riskiest unit. Mentions named only in the context (`named_in:
  context`, 182 mentions) carry an error 53% of the time and average 1.0 errors each. Mentions the
  comment names (433) are at 40% and 0.66. These replies are where untried impressions, over-scaling,
  agreement replies, null overall and the secondhand misuse live.
- **Lists produce correlated errors.** One misread rule is copied to every item:
  - Q0408, "X for the Y": 11 errors;
  - Q0370, framing beats explicit praise: 10;
  - Q0295, dish headings: 6;
  - Q0461, examples endorsed: 6.

  These 4 items hold 33 errors (6%), all B or D, so all prompt-fixable.
- **What genuinely degrades with length** is attachment: names in passing (Q0167's three
  inspirations), dishes bound to the wrong place (Q0530, Q0342, Q0123, Q0580), and implicit
  winners and losers (Q0326). G is 20% of the errors in 3–4-place items, against 13% in
  one-place items. That is about 15 errors in total: a real but small model-limit pocket.

## 6. How much can be fixed

Method: each pattern got an expected fix rate for the lever that addresses it:
- calibration word lists (overscale_neg, timeframe, closed places): 0.9;
- new rules (untried, bottom line, the overall rule): 0.8;
- schema plus a validator (complaint or dish only in a note): 0.7–0.8;
- reworded clear rules that Haiku already ignores (experience, secondhand, over-praise): 0.6–0.7;
- extraction recall and comparisons: 0.4–0.6;
- the context-input change: 0.7.

G errors count at 0.1 and H at 0. The summed expectation:

| cause | errors | expected fixed | via |
|---|---:|---:|---|
| A rule missing | 31 | ≈24 | prompt (after owner rules on untried) |
| B unclear | 146 | ≈106 | prompt wording |
| C ignored | 135 | ≈86 | prompt wording + validators (lower confidence) |
| D calibration | 70 | ≈59 | prompt (port rubric calibration) |
| E schema | 31 | ≈23 | schema + validator |
| F input | 24 | ≈17 | rendering (ancestors, longer post) |
| G model limit | 64 | ≈6 | stronger model or more reasoning |
| H ambiguous | 34 | 0 | owner rulings |
| **total** | **535** | **≈320 (60%)** | |

A conservative reading (C at 0.4 instead of 0.64) gives about 290 (54%). Field by field, these are
the field-level changes I expect if the fixes land:
- **overall:** most of its 115 errors are D or B; I expect about 80 to be fixed, taking overall
  accuracy from 0.81 to about 0.94.
- **experience:** about 48 of 80 fixed, from 0.86 to about 0.95.
- **dishes:** about 38 of 64 fixed.
- **mentions:** about 30 of 64 fixed, half of them through the input change.

Roughly 75 of the 535 errors would remain as model limit plus judge ambiguity, and the rest as
partial misses on the fixed rules.

**Cheap deterministic post-processing** (code, not the model) can fix some of these with certainty
before any prompt change:
- endorse ⇒ overall positive;
- a single-signed aspect or dish with overall null ⇒ overall takes that sign;
- note.dish ∉ dishes ⇒ add the dish;
- a negative note with no negative field ⇒ flag;
- secondhand without a source phrase ⇒ firsthand;
- closed ⇒ timeframe past;
- stated with all levels null ⇒ none.

## 7. Consolidated prompt and schema changes for round 4

Replacements in `v6_common.py`, in field order:

```
experience  Who the verdict comes from, not whether a visit is described. "firsthand" is the default: anything
            in the commenter's own voice, including a bare pick ("Java in Park Slope"), a list, "try X", "skip X",
            a tip, a fact offered as an answer ("they have it at X"), a hedge ("I think X has it", "might be a
            good option"), and a reply about a place someone else named. "secondhand" only when the comment
            names someone else as the source: "my friend swears by it", "heard great things", "people here
            recommend it". "none" only when the commenter has not been ("never been", "gonna try", "will check
            it out"), asks a question, or relays news or a correction that is not offered as a pick.
opinion     "none": a fact, a question, news about the business (closures, foot traffic, rent, expansion), or a
            name in passing that recommends nothing ("vendors like A and B went on to open restaurants", "near
            X"). "endorse": offered as a pick with no word of praise or knock: a bare name, "try X", "X for the
            soft shell crab", "they have it at X", "Do it!" to someone planning to go, "this" / "+1" / "yeah,
            pretty much" under praise. "stated": any word judging the place or its food, even one ("good",
            "great", "my go-to", "I enjoy the egg salad"). A dish leveled by "get the X" alone keeps a pick
            "endorse".
overall     LEVEL. The verdict on the place as a whole. If the commenter gives a bottom line (what they'd tell a
            friend: "worth it", "I like it and order often", "the right answer", "not worth it", "skip it",
            "never going back"), overall follows it even when they list points on the other side. Otherwise it
            follows the strongest point, usually the food. When the only judgment is one aspect or one dish,
            overall takes its level ("Those lines are brutal": overall and wait negative; "tasted great":
            overall positive). Null only when nothing judges the place: a fact, a question, a neutral tip
            ("they open at 11"). Always "positive" for "endorse". Other people's views are not the commenter's.
            A superlative about one dish makes the dish and taste very_positive, not overall.
aspects     ... Set each from what is said about that side of the place. Dishes are the food: praise or a knock on
            a dish also sets taste ("love the hash wrap": taste positive; "good brisket, terrible sides": taste
            neutral; "only good for the banana pudding": taste negative). Never copy overall into an aspect.
              service: staff, and how the place is run, including hygiene and health violations, menu format
              ("prix-fixe only"), ordering rules and business choices.
              wait: ... "be there before they open", "go late on a weeknight to get in", "Yikes" at the line are
              negative; "shortish line at dinner", "they have an opening", "easy walk-ins" are positive.
              "Packed and lively" said as praise of the vibe is atmosphere, not wait.
            A remark about fit for one person ("more casual", "all seafood") is a note, not a level.
avoid       true only when the comment tells readers in general not to go or not to bother: "skip it", "don't
            bother", "make it yourself instead", "no one should pay $20 for that". A conditional skip next to a
            recommendation, thread framing, or a bad review alone is false.
dishes      Every dish or drink named for this place, also when it is in a note, a tip or a comparison. "positive"
            for "get / try the X", "X for the Y", a dish heading over a list answering "where for Y"
            ("Mazemen: A, B"), "either the steak frites or the burger"; null only when named with no view. One
            dish named two ways is one entry. Advice about a dish at one place does not apply to the others.
price       Only an absolute price word: "cheap", "inexpensive", "pricey", "expensive". Not "cheaper / pricier
            than X", not a dollar figure, not a complaint about worth ("outrageous price", "highway robbery").
value       (in aspects) needs a judgment of worth ("a steal", "$12 for way more", "not worth $30"); a price
            word alone is not value.
timeframe   "past" when the place is closed (always) or the comment says it changed since ("used to be", "back
            then"). Any visit, old or recent, with nothing about change is "current".
trend       Only when the comment says the place's food, service or experience got worse or better. Not for
            closures, fewer customers, a lost Michelin star, a branch closing, or the commenter stopping going.
status      The place, not one branch. "closed": gone ("closed", "RIP X", named under "which closed place would
            you bring back"); "moved": a new space; "opened": new or reopened. A branch opening or closing, a
            temporary shutdown and an alleged reopening are notes.
```

- **SCALE:** the replacement rows in §3.1 (overscale_neg and overscale_pos).
- **RULES:**
  - rule 5 as in §3.2;
  - rule 9: add "and the aspects the agreed text names";
  - rule 10: add the RIP / "too bad it closed" examples;
  - rule 11: add "only when the comment gives no polarity of its own; framing never sets avoid";
  - new rule 13 (untried places);
  - the context-reference rule from §3.5.
- **SCOPE:** the added not-places list, and the "every named place, even in passing" sentence with
  its re-read instruction (§3.5).
- **Schema:**
  - drop `level` from notes, or allow only null;
  - drop `dish` from notes, or validate it against `dishes`;
  - optionally rename the experience values to `own | others | not_tried` and move the field after
    `opinion`.
- **Input:** add the nearest place-naming ancestor (or all ancestors, about 300 characters each), and
  raise the post cut to about 1,200 characters.
- **Example:** the single invented example covers only a negative reply. Add a second invented
  example with a list answer, a comparison and an untried reaction. Several of the largest patterns
  (endorse lists, comparisons, untried, experience default) have no worked example in the prompt,
  though the rubric gives the judges eight.
