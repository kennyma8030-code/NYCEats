# Pre-run check: would round 4 decide round 3's errors correctly?

No API calls. Every one of the 535 classified round-3 errors (`errors.jsonl`) was re-read
against the round-4 prompt (`eval/prompts/v6_common.py`, `v6_comment.py`, `v6_schema.json`),
the round-4 rubric (`eval/review_v6r4/RUBRIC.md`), the validators (`eval/v6_validate.py`
DEFAULT, actually run on Haiku's round-3 output) and the owner's rulings (`decisions.md`).
Each comment was read with the round-4 input as `v6_comment.build_user_message` renders it
from `items.comment_rows.jsonl` / `v2/items.comment_rows.jsonl` (all 600 covered).
Then 75 round-3 items the judges marked fully right (110 mentions) were checked for answers
round 4 would now break. One line per error and per regression item is in
`precheck_r4.jsonl` (`kind: "error"` / `"regression_check"`), with the class, the new
target, the deciding text, whether a validator fixes it, and `p_fix`, an estimate that
Haiku at low effort gets the field right in round 4 with validators applied.

## Counts

| class | errors | mean p_fix | meaning |
|---|---:|---:|---|
| FIXED_BY_RULE | 218 | 0.67 | round-4 prompt text now targets the case |
| FIXED_BY_VALIDATOR | 121 | 0.95 | a DEFAULT validator turns Haiku's round-3 value into the final |
| MODEL_LIMIT | 69 | 0.39 | the prompt is clear; it needs a better reader |
| STILL_UNCLEAR | 55 | | the prompt doesn't decide it (24 distinct gaps, below) |
| ANSWER_CHANGED | 40 | 0.61 | round-4 rules move the target; Haiku's old value is now right in 24 |
| NEEDS_CONTEXT | 29 | 0.58 | all 29 are now visible in `<thread_above>` or the 1,200-char post |
| CONTRADICTION | 3 | | two prompt parts disagree (e018, e336, e534) |

The mean p_fix over all 535 is 0.66, so about 350 of the 535 errors should go away and about 185
should remain, before any regressions.

By round-3 pattern (R rule, V validator, A answer changed, N context, M model limit,
U unclear, C contradiction):

| pattern | n | classes | p_fix |
|---|---:|---|---:|
| exp_none_default | 34 | V28 R4 U1 C1 | 0.88 |
| overscale_pos | 33 | V23 R9 C1 | 0.85 |
| missing_verdict | 33 | V18 U8 A4 R3 | 0.73 |
| overscale_neg | 32 | V25 R3 A3 U1 | 0.86 |
| untried_scored | 29 | R25 A4 | 0.76 |
| exp_secondhand_uncredited | 25 | V21 C1 R1 U1 M1 | 0.87 |
| dish_omitted | 23 | R18 M4 U1 | 0.51 |
| endorse_missed | 22 | M10 U5 R3 N3 V1 | 0.48 |
| missed_needs_context | 19 | N19 | 0.59 |
| comparison_side_missed | 18 | R8 A6 M3 V1 | 0.57 |
| aspect_not_set | 18 | R11 U4 M2 A1 | 0.60 |
| complaint_only_in_note | 15 | R7 U4 A3 M1 | 0.50 |
| sarcasm_missed | 11 | M9 A2 | 0.23 |

These patterns stay weak, and nothing in round 4 changes them much:
- sarcasm;
- implicit endorsements ("Do it!", "another good one");
- names missed in long lists;
- dishes that are named but not leveled.

### Where the target moved (ANSWER_CHANGED, 40)

Haiku's round-3 value is now right in 24 of them:
- wait-only overall null: e161, e522, e243, e407;
- fit swap lowers nothing: Carbone e270, e271, e272;
- untried photo reactions: e330, e530, e463 taste;
- the store rule: Zabar's e034, Pomegranate e048;
- hygiene is not service: e315, e396, e441;
- one branch closing: Pressed e207, e334 timeframe;
- trend not for one aspect: e133, e523;
- general talk is not a mention: e051, e331;
- the prompt's own mixed example: Semma e157;
- a dish superlative doesn't lift a full restaurant's overall: e148;
- a fit remark: Bar Moga e113.

In the other 16, Haiku is still wrong against the new target:
- boycott, no level: Sweetgreen e131;
- untried, opinion none: e360, e393, e395;
- no loser without a named winner: Fu Zhou e246, e249;
- low-bar winner: Mama's Too e172 overall;
- a pick with only availability words is endorse: Bad Roman e302;
- Katz's e281, now overall negative from "my favorite but probably not worth the line" (see the risks below);
- unnamed places are no longer mentions: Malaysian jerky place e381, e382; tamale lady e459–e461; the coconut place e425;
- Di Palo's e103, now kind grocery.

## STILL_UNCLEAR and CONTRADICTION: the gaps, with wording

Grouped by gap; the error ids are the evidence. Proposed text uses invented places, as the
prompt requires, and should go into `RUBRIC.md` too.

1. **The commenter's own earlier verdicts, now visible** (e132, e196–e199; the regression
   check found the same in Q0073, Q0094, Q0325, Q0399). Round 4 labels the post
   `author="you"` and earlier comments `you, earlier`, and `<input>` says a context claim is
   the commenter's "when they wrote it". That invites copying the post's "I love this place" or
   roaches into a wait-only or 311 reply, which would count one person twice. Add to `<input>`:
   > Use the post and your earlier comments only to understand this comment. Levels,
   > opinion and experience come only from what <comment_to_extract> says; your earlier
   > verdicts were counted where you wrote them.

   In the rubric's Context places, change "A claim in the context is the commenter's only
   when they wrote it ... or agree with it" to "...only when this comment agrees with it".
2. **Experience for a no-verdict mention**. This covers the three CONTRADICTIONs (e018, e534) plus
   e121 and e142. FIELDS experience lists "a hedge" and "a tip" as firsthand and "a bare fact" as none,
   so "I think they moved" and "cart is out by 8, takes cards" fit both. Add to FIELDS experience:
   > When opinion is "none" (a fact, a story, a question, a name in passing), experience is
   > "none" too; a tip or hedge is firsthand when it carries a verdict or a pick.

   Validator: `secondhand_needs_credit` should give "none", not "firsthand", when opinion is
   none (it does harm today on e018, e142, e203). A new rule opinion none → experience none is
   worth measuring.
3. **A reaction to someone else's report, from a commenter who doesn't say whether they've been**
   (e181–e183 "That's cool they give you a kids activity"; e490, e491 "Absolutely disgusting"
   under the roach post). Decisions 1 and 15 say no level, but RULES 3 covers only "says or
   shows they haven't been". Append to RULES 3:
   > A reaction to what the post or parent reports ("absolutely disgusting", "that's cool
   > they do X", "wow, $40?") with nothing from their own visit is the same: no verdict.
4. **Untried versus a complaint** (e084, "I want to try it" plus "sickeningly rare" from a
   video). Append to RULES 3:
   > Untried wins: praise or a complaint about something they only saw (a photo, a video,
   > a menu) sets no level; put it in a note.
5. **A pick whose only words are about getting in** (e298–e300, e302). "A remark only about the wait
   leaves overall null" collides with "praise for endorse" and example 1. Add after the wait
   sentence in FIELDS overall:
   > A place recommended to the asker is endorse, overall praise, even when all they say is how
   > to get in ("try Pepper House, they take walk-ins"); overall stays null for a wait remark
   > about a place they aren't recommending.
6. **List answers given only with facts** (e064–e066, Red Gate Bakery under "best cinnamon
   rolls"). RULES 6 "Names given as examples or facts are opinion none" collides with endorse "a
   bare name". Append to RULES 6:
   > A place offered as an answer is a pick even when only facts are given about it (hours,
   > what it serves). "Examples or facts" means names not offered as answers.
7. **How taste weighs mixed dishes** (e277, e306, e472; the regression check found Q0362 and Q0356). The only
   aggregation example, "great brisket, awful sides: mixed", over-triggers, and the judges split on
   the same shape. Add to FIELDS taste:
   > Mixed only when praise and complaints about the food weigh about evenly. One dish knocked
   > among several praised keeps taste praise. Praise framed as the lone exception ("only
   > good for the X") is a taste knock with dish X praise.
8. **A caveat on a praised side** (e108, e398, e399). Replace the SCALE mixed line:
   > mixed  praise and a complaint about the same side with no bottom line for it: "hit or
   > miss", "great room, though it leaked", "much better, though only 12 pieces". Never
   > for lukewarm words.
9. **Dated old visits** (e106 "a couple of years ago", e400 "in 2022"). "back in 2015" is listed
   as tying the verdict to then, but "an old visit with nothing tying it to then is current".
   Change the example to "it was great back in 2015, no idea now" and add:
   > A dated visit ("in 2022", "years ago") is still "current" unless the text says the place
   > may have changed.
10. **A price word as value** (e180 "inexpensive", e191 "pricier"; e354 "outrageous price").
    The rubric says "A price word alone is price, not value", but the prompt doesn't. Append to FIELDS
    value:
    > A price word alone ("cheap", "pricier", "$$$") is price, not value; a price said as a
    > complaint ("outrageous", "a rip-off") is value, not price.
11. **A dish's cost as its level** (e211 "$25 for a chicken sandwich was a disappointment").
    Add after value:
    > A complaint only about what a dish costs is value; it sets neither taste nor the dish.
12. **Is "gross" an extreme?** (e006, e519). It is on neither the extreme_knock list nor
    `v6_validate.EXTREME`, so the validator already cuts it to knock. The owner should pick one and list
    it.
13. **Endorse picks and taste** (CONTRADICTION e336). FIELDS taste says "A verdict on a dish
    sets taste", but example 1 gives a "get the X" pick dish praise with taste unset, and the
    round-3 judges held "endorsements have aspects null". Pick one and state it in both places:
    > A dish praised only by "get the X" or by the question's framing sets taste praise too.
14. **Smaller single-case gaps.** Each line below is the wording to add.
    - Presentation is taste (e045): "taste: the food and drink, including how it looks".
    - "Fun" is atmosphere (e096): "A place called fun or lively is atmosphere praise".
    - A relayed pick (e099, e100): "A pick passed on from someone else ('my friend swears by Y') is
      secondhand endorse, overall praise".
    - The loser rule for dishes (e147): "In 'their sandwiches > their slices' the slices get a
      knock".
    - A question about a recipe change (e165): "A question or surprise about a change
      ('they don't use that blend anymore??') judges nothing".
    - Business strategy (e176): "Second-guessing a business decision is a note, not a level".
      This is an owner call.
    - A fact given only as a cause (e202): "A fact given only as the reason for another verdict
      sets that verdict's aspect".
    - A workaround fee (e223): "A fee they tell you to pay as a workaround is a note".
    - A pick with one weak dish (e233): "A pick that answers the question is its bottom line, even
      when one dish disappoints".
    - "your best bet" (e244): add "'X is your best bet'" to the endorse examples.
    - A plain word for what's sold (e276): "A plain word for what the place sells is a dish ('the
      tacos are always consistent')".
    - Trend in the food (e129): "A change in part of the food counts as trend; 'one aspect' means
      booking, prices or service".
    - A change in what's sold (e293): "A complaint about what a place now sells lowers overall,
      not taste".
    - A skip aimed at some readers (e401): "false for a skip aimed at some readers ('if you're a
      tourist, skip it')".
    - Fake reviews (e415): "Conduct a diner can't see at the table (fake reviews, lawsuits) is a
      note, no level".
    - Healthiness (e462): "Healthiness is a tag, not taste". This is an owner call.
    - Groceries at a deli counter (e428): "Meat, cheese or pickles sold by the pound or packaged
      are groceries, even from a deli counter".
    - A supplier bakery as a brand (e032): "brand is only for packaged goods sold in stores; a
      bakery named as the supplier other places carry is kind bakery".
    - "looks like" as a fact (e303): "'looks like they have an opening' is a fact, not untried".
    - The Carbone swap (e270): "When a swap gives only fit reasons, even 'same menu but more
      casual', the other place gets no overall".
    - A reply that neither names nor judges a place (e331): add "A reply that neither names nor
      judges a place is not a mention of it" to `<input>` (it is in the rubric only).

## New failure risks

From the 75 fully-right round-3 items: 40 are safe, 15 change answer, 20 carry a risk. That is
about 8.8 expected newly wrong fields over 110 mentions, so roughly **6 to 9 per 100 mentions**.
About half of those sit where the new rubric's own answer is unclear. Ranked:

1. **Earlier verdicts counted twice** (gap 1). About 1.3 per 110 mentions, plus e132 and e196–e199.
2. **kind drops real food places.** About 2.4 per 110. Pickle shops, Eataly, Zabar's, Pavé, a
   bazaar, "Carlos grocery", Space Market and a supplier bakery could be labeled grocery,
   brand or other, and `kind_excluded` would remove them silently. The prompt tells Haiku to
   extract brands "with that kind" but gives no guidance for specialty food shops, pop-ups or
   bazaars. Before trusting the counts, measure kind against judge-graded kind on round 4.
3. **Rule 6 over-applied, or colliding with the wait rule.** About 1.0 per 110: wait praise taken
   from a reservation worry in the post (Q0343), "never had a problem walking in" (Q0093), and
   the dish headings in Q0106. In Q0106, "I'd skip 4 Charles and do Wild Cherry" is both "skip it"
   and a swap, and the prompt doesn't say which wins.
4. **Rule 3 fires on real verdicts.** "I have not been, but heard Elea is great" is secondhand
   (Q0592). "Haven't been for a min" means they have been (Q0066). "Imma go to Utopia today" (e387)
   is a repeat visit, and "I haven't been to a lot of these places" sits next to a real wait tip
   (e287–e289). Append to RULES 3:
   > If they pass on what someone told them, it is secondhand with that verdict. "Haven't been in a
   > while" and "going again" mean they have been.
5. **"not worth the wait" as a bottom line on a favorite.** Katz's (e281) becomes overall
   negative, which works against decision 3's reason for keeping wait out of overall. The
   owner should confirm. If not, add: "'favorite, but not worth the line' is wait knock,
   overall praise".
6. **`<quote>` marking hides a place** named only in the quoted line (Q0061, Q0181). Add to
   `<input>`: "a place named in a <quote> that the comment answers is referred to".
7. **Innuendo listed as a non-verdict** may wipe out a joke that is a verdict (e023). The boycott
   example may lead Haiku to drop a food jab inside a boycott comment ("Slop indeed", e476).
8. **Local superlatives move down a level.** "best on the UES" and "best in the area" are now praise,
   but the round-3 judges accepted the first as very_positive. The SUPERLATIVE regex matches any
   "best", so it can't help.

**Validator problems**, all from running `v6_validate.apply`. 18 of the 535 errors have the
validator moving Haiku's round-3 value to another wrong value.
- `lone_aspect_overall` ignores untried words. It sets overall praise on photo reactions
  (e330, e530, e084), copies a wrong aspect into overall (e070, e358, e019), and writes
  positive for Katz's.
- The `UNTRIED` regex runs on the whole comment and matches "looks like", "need to try" (advice
  to the reader), "thanks" and "never been to X before". It then blocks `none_to_firsthand`
  for every other place in the comment (e066, e016, e303, e308, e312). Scope it to the sentence that
  names the place, and narrow `looks?` to praise words.
- `SUPERLATIVE` and `EXTREME` also run on the whole comment. Any "best" (including "your best bet" or
  "best time to go") or "worst" (including "the worst part is") anywhere keeps every very_* level in the
  comment (e193, e325, e504). `EXTREME` also passes words the prompt calls knocks:
  "abomination", "stay away", "rats", "hair in", "inexcusable", "vile". Align the two lists.
- `closed_past` forces timeframe past on a branch closing when Haiku keeps status closed
  (e334, Pressed). Skip it when location is set.
- `very_needs_word` lowers correct implicit city-wide superlatives ("nowhere really exceptional
  after those two closed", e294–e297).

**Two measurement problems for the round-4 review:**
- **The prompt copies eval comments.** About fifteen of its phrases come from the 600 eval
  comments, against its own rule that no eval comment may appear in a prompt: "love the hash
  wrap", "free tables at 4", "brutal lines", "be there by 11:30", "it's not that bad", "not the
  best or worst price", "it's a small business", "that's what I was afraid of", "best on the
  UES", "in that order", "JG Mellon style", "Mazemen: A, B", "best chicken salad", "easiest
  walk-ins", and the rubric's "should be burned down". Gains on those items will be inflated, so
  the hard and fresh sets are the honest measure.
- **`review_v6r4/build.py` reuses stale round-3 finals.** It reuses a round-3 final whenever round 4's
  output equals it, but the target moved on 40 error fields and on about 20% of the fully-right items
  (15 of 75: branch status, rule-6 dishes, untried reactions, wait-only overall, fit swaps). A round-4
  output that repeats an old final which is now wrong would be scored right without a judge. Re-judge
  every comment listed with `cls: ANSWER_CHANGED` or `verdict: answer_changed` in `precheck_r4.jsonl`
  rather than auto-reusing it.

## Expected accuracy under round 4 (low effort, validators on, against round-4 targets)

Remaining errors are the sum of (1 − p_fix) per error. New errors are the regression estimate
scaled to 590 mentions, with round 4 assumed to miss about 35% of the targets that moved.

| field | round 3 | round 4 estimate | range | left from the 535 | new |
|---|---:|---:|---|---:|---:|
| overall | 0.805 | **0.90** | 0.87–0.92 | 36 | ~20 |
| experience | 0.864 | **0.96** | 0.94–0.97 | 16 | ~5 |
| opinion | 0.903 | **0.94** | 0.92–0.95 | 24 | ~9 |
| taste | 0.912 | **0.955** | 0.94–0.965 | 18 | ~7 |
| dishes | 0.779 | **0.87** | 0.83–0.89 | 23 of 58 | ~14 (n grows ~10%: rule 6 adds dishes taken from the question) |
| negative recall | 0.86 | **0.92** | 0.89–0.94 | ~11 of 21 | see below |

How negative recall is estimated:
- Of round 3's 24 missed negatives, 3 are no longer negative under round 4: EMP Q0054 (not a mention), Bar Moga's fit remark, and Carbone's fit swap.
- About 10 of the other 21 should be caught. The rest are sarcasm (Q0022, Q0495), atmosphere jabs (Q0446), mentions missed in long text (Q0043, Q0131, Q0238) and the strategy complaint (Q0197).
- The rule-3 and boycott changes also take some old negatives out of the denominator, which slightly favors recall.

Caveats:
- p_fix is a reading estimate, not a measurement.
- About 52% of low-effort calls in round 3 didn't think at all. The new `<before_answering>` asks them to, but how much a checklist helps at low effort is the biggest unknown.
- The phrases copied from eval comments will lift results on the 600 above these numbers. Expect the fresh set to come in a few points lower.
