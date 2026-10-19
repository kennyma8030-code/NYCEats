# Rule decisions from the Opus review of Haiku round 3

The 24 Opus judges raised 111 rule questions on 110 items (`report.md`,
`judgments/*.jsonl`). This file groups them into 26 decisions. Each decision
has the question, the items where it came up, real quotes, the options, a
recommendation, and the wording to put in the prompt. The first ten are the
ones that move the most per-place counts.

**What the counts are for.** Each place shows how many *people* sit at each of
five levels, for Overall and for taste, value, service, atmosphere and wait.
Readers search by popular, niche, momentum, cheap and best taste. So every
call below asks one thing: does this make the count of people at each level
more honest?

**Owner** means a taste or product call that the owner has to make.
**Settle** means a consistency call that follows from rules the owner has
already set; the recommendation can go straight in.

Prompt wording uses invented places, because no eval comment may appear in a
prompt (`v6_common.py`). Whatever is adopted should go into `RUBRIC.md` too, so
the judges stop splitting.

## Three places where the live prompt and the rubric disagree

The judges spent most of their corrections on these, and the owner has
already ruled on the first.

1. **very_negative list.** `v6_common.SCALE` lists "never again" and
   "regretted going" as very_negative. The owner's calibration in the rubric
   makes them negative. The judges moved 32 Haiku levels from very_negative
   down to negative (decision 2).
2. **Old visits.** `FIELDS` says timeframe is past for "a visit years ago with
   nothing about now". The judges moved 12 of Haiku's `past` back to
   `current` because nothing in the comment said the place had changed
   (decision 10).
3. **Wait tips and overall.** `FIELDS` says "go early to beat the line" has no
   overall. The rubric says overall follows the strongest point. The judges
   set overall from a single aspect 225 times and left it null 17 times,
   almost all on wait (decision 3).

## Summary

| # | decision | questions | call | recommendation |
|---|---|---:|---|---|
| 1 | Reactions from people who haven't been | 12 (+7 more items) | Owner | Mention only: opinion none, no levels |
| 2 | Which words are very_negative | 8 (+32 corrections) | Owner | Extremes only; "terrible", "awful", "never again" are negative. Fix the prompt list |
| 3 | A remark only about the wait: does overall follow it? | 6 | Owner | No. Overall follows a lone taste, value, service or atmosphere verdict, but not a lone wait remark |
| 4 | What a bare answer takes from the question | 8 | Owner | Polarity, the aspect asked about, and the dish asked about. Never the superlative |
| 5 | How broad very_positive has to be | 6 (+42 corrections) | Settle | City-wide or wider. Local, recent and classless hyperbole are positive |
| 6 | What a comparison loss lowers | 4 | Owner | Only what the comparison is about; a swap made only for fit lowers nothing |
| 7 | One branch of a chain closes, opens or moves | 7 | Settle | Status stays null; the branch goes in location and a note |
| 8 | Is a timing tip wait positive or negative? | 3 | Settle | Negative when you have to plan around a wait; positive when getting in is easy |
| 9 | Gourmet grocers and markets with food counters | 7 | Owner | A mention when the comment is about food they serve to eat; not for groceries |
| 10 | Timeframe for old visits | 6 | Owner | Past only when the comment ties the verdict to an earlier time |
| 11 | Boycotts over politics, deals or a chef's persona | 3 | Owner | No level; a note only |
| 12 | Food halls and night markets | 3 | Owner | A mention, and so is each named stall |
| 13 | Ranked lists, near misses, unnamed and low-bar winners | 5 | Settle | Ranked picks all positive; "close but not the same" negative; no loser without a named winner |
| 14 | Where seating, format and "fit" complaints go | 4 | Settle | Format under service, seating under atmosphere, fit as a tag |
| 15 | Hygiene, health violations, food poisoning | 4 | Settle | Overall, not service; taste only if flavor is judged |
| 16 | What counts as avoid | 3 | Settle | An instruction to skip the place itself |
| 17 | Nameless replies and places with no name | 6 | Settle | Neither named nor judged means no mention |
| 18 | Music clubs, comedy clubs, game bars | 3 | Settle | Not places unless their food or drink is discussed |
| 19 | Brands, companies, chefs, rooms inside restaurants | 5 | Settle | Not places; a room is part of its restaurant |
| 20 | "RIP X", "too bad it closed" | 2 | Settle | A fond verdict: positive, closed, past |
| 21 | What trend means | 4 | Settle | A change in quality; not business health, predictions or one aspect |
| 22 | Remarks about a whole category or list | 3 | Settle | They lower a place only when applied to it |
| 23 | Lukewarm defenses, middling prices, "like it but not worth it" | 4 | Settle | The owner's lukewarm and bottom-line rules apply as written |
| 24 | Jokes and banter | 6 | Settle | They count only when the joke's point is a verdict |
| 25 | Agreement replies that agree with something else | 2 | Settle | Rule 9 needs agreement with the verdict on the place |
| 26 | Judging items that need unseen context | 2 | Settle | Rubric only; no prompt change |

Two item ids appear under two decisions: Q0309 asked two questions, and some
items raise two issues. All 111 questions are covered.

---

## The ten most consequential

### 1. Reactions from people who haven't been — **Owner**

**Question.** When someone who hasn't eaten there reacts with praise or worry
("looks so good", "sounds amazing", "can't wait to try", "saved it, thanks"),
is that a person at a level, or a mention with no opinion?

**Came up.** 12 questions: Q0004, Q0007, Q0025, Q0059, Q0081, Q0096, Q0114,
Q0149, Q0200, Q0385, Q0392, Q0438. Judges also corrected Q0033, Q0047, Q0063,
Q0313, Q0363, Q0544 and Q0597 on the same point. Their rulings split. Q0004,
Q0007, Q0025, Q0033, Q0047 and Q0063 went to opinion none. Q0114, Q0200,
Q0363, Q0385 and Q0438 went to stated positive, and Q0149 to secondhand
positive. It is the most frequent open question and the most inconsistent.

**Examples.**
- Q0007, under a Le Botaniste recommendation: *"Omg this looks so good. Def
  gonna order"*.
- Q0438, under a Mama's Too photo post: *"Oooo this looks so good. I've never
  been and I think I need to change that."*

**Options.**
- (a) A mention with experience none, opinion none and every level null.
- (b) Stated, with the praise or worry as the level and experience none.
- (c) Endorse, overall positive.

**Recommendation: (a).** A photo reaction measures hype, not the food. If
these count as praise, photogenic and viral places look loved by people who
have never eaten there, and their Overall counts are inflated by exactly the
crowd that hasn't been. The mention is still kept, so the reaction still
counts toward popular and momentum.

This doesn't conflict with the owner's earlier calls:
- "+1" counts because the commenter vouches for the verdict.
- Secondhand counts because the commenter passes on a verdict as information
  ("my friend got sick there").
- "Sounds amazing", by contrast, only reacts to someone else's report, so
  counting it would count the same evidence twice.

The rule applies in both directions. Q0059 ("That is what I was afraid of",
about Soothr's spice) and Q0392 ("we not doing that, we'll be there at
11:30") also give no level.

**Prompt wording** (add to RULES, and narrow the `experience` field to match):
> A commenter who says or shows they haven't been ("looks so good", "sounds
> amazing", "can't wait to try", "saved it", "thanks, will check it out",
> "that's what I was afraid of") gives no verdict, even with a praise or
> complaint word. The place is a mention with experience "none", opinion
> "none" and every level null. Keep what they said in a note. This is not
> secondhand: secondhand is a verdict passed on as information about the
> place ("my friend swears by Golden Lotus"), not a reaction to another
> comment's report.

### 2. Which words are very_negative — **Owner** (partly decided)

**Question.** Are "terrible", "awful", "gross", "pink slime", "should be
burned to the ground", a health-department report or "do your worst"
framing extreme enough for very_negative?

**Came up.** 8 questions: Q0043, Q0113, Q0267, Q0374, Q0444, Q0445, Q0556,
Q0565. Beyond those, the judges moved 32 Haiku levels from very_negative to
negative and 3 from negative to very_negative. On "terrible" alone the judges
split: Q0113 and Q0374 ruled negative, while Q0445 and Q0556 first read it as
very_negative. The live prompt still lists "never again" and "regretted
going" under very_negative, against the owner's rule.

**Examples.**
- Q0374: *"This place is genuinely terrible"*.
- Q0565: *"Cocodaq though is an abomination and should be burned to the
  ground."*

**Options.**
- (a) Keep a short list of extremes. Every other knock, however strong, is
  negative.
- (b) Also count strong general words ("terrible", "awful", "horrible") as
  very_negative.

**Recommendation: (a), drawn as the mirror of very_positive.**
- very_positive needs a broad superlative, and "amazing" is only positive. So
  "terrible", the mirror of "amazing", is negative.
- What maps to very_negative is the mirror of "best in the city" or "god
  tier": a worst against a broad class, food unfit to eat, getting sick, or
  "avoid at all costs".
- This keeps the very_negative bucket small and meaningful, the same size as
  very_positive. Otherwise angry writing style decides which places look
  dangerous.

The owner may want to move individual words across the line, "garbage",
"slop" and "abomination" in particular. The design note already uses "turned
into slop" as very_negative.

**Prompt wording** (replace the very_negative line in SCALE):
> very_negative  only an extreme: a worst against a broad class ("worst I've
> had", "worst in the city"), food unfit to eat ("inedible", "disgusting",
> "gross", "slop", "an abomination"), getting sick or finding bugs in the
> food, or "avoid at all costs". "Terrible", "awful", "horrible", "sucks",
> "trash", "never again", "regretted going", "don't waste your time" and any
> price complaint are negative. Thread framing sets the sign, never the
> extreme: "second this" under "worst place to send an enemy?" is negative.

### 3. A remark only about the wait: does overall follow it? — **Owner** (the design note's open question 7)

**Question.** When the only thing said is about one aspect, does overall take
that level, or stay null as a tip? The case that matters is the wait: "line
started at 4:15", "Yikes", "free tables at 4".

**Came up.** 6 questions: Q0020, Q0132, Q0143, Q0178, Q0223, Q0392. The
judges' blind reads set overall from a single aspect 225 times and left it
null 17 times. Of those 17, 16 were wait. Even wait remarks split, though:
Q0571 ("Those lines are brutal") and Q0178 got overall negative, while
Q0020, Q0132 and Q0209 stayed null. The prompt says a line tip has no
overall; the rubric says overall follows the strongest point.

**Examples.**
- Q0178, on Red Hook Tavern: *"It would be faster to get on the Jitney and go
  to their place in Sag Harbor. Yikes."*
- Q0020, on the same place: *"Went a few sundays ago, the line started around
  4:15 I think"*.

**Options.**
- (a) Overall follows any lone aspect.
- (b) Overall follows a lone verdict on taste, value, service or atmosphere,
  but a lone wait remark leaves overall null unless the commenter draws a
  bottom line from it.
- (c) Overall is null for any lone aspect.

**Recommendation: (b).** Lines and hard reservations are mostly a symptom of
popularity. If they drive Overall negative, the most-loved places get pulled
down because they are loved, and the Wait tab already counts every one of
these remarks. A lone taste or service verdict ("the pasta was bland", "the
waiter was rude"), by contrast, does answer "is it worth going?".

**Prompt wording** (replace the `overall` example in FIELDS):
> A lone verdict on taste, value, service or atmosphere sets overall to the
> same level. A remark only about the wait (lines, booking, selling out, when
> to go) sets wait and leaves overall null, unless the commenter draws a
> bottom line from it ("not worth the wait", "skip it, the line is absurd").

### 4. What a bare answer takes from the question — **Owner**

**Question.** Owner rule 11 says thread framing decides polarity. Does a bare
pick also take the aspect the thread asks about ("easiest walk-ins?"), the
dish ("best chicken salad sandwich?") or the superlative ("best X?")? And
does a name count as a pick when it is given as an example?

**Came up.** 8 questions: Q0009, Q0098, Q0120, Q0267, Q0367, Q0370, Q0460,
Q0461. Judges also added positive dishes from list headings (Q0295,
"Mazemen: Shuya…") and from "X for the Y" picks (Q0408).

**Examples.**
- Q0009, under "Easiest upper level NYC restaurants to walk in as a solo
  diner?": *"Raouls / Via carota / Minetta tavern / Cervos / Penny…"*.
- Q0098, under "Where in the city did you have the best chicken salad
  sandwich?": *"EJs and Bloomingdale's/40 Carrots"*.

**Options.**
- (a) Polarity only, which is the rule now.
- (b) Polarity, plus the aspect the question asks about, plus the dish it
  asks about as a positive dish entry, but never the superlative.
- (c) Everything, the superlative included.

**Recommendation: (b).** Someone answering "where can I walk in?" is vouching
for the walk-in. Someone answering "where's the best chicken salad?" is
vouching for that dish. Those are exactly the signals the Wait filter and
dish search need, and (a) throws them away.

The superlative is the asker's word, not the answerer's. People answer "best"
questions with their favorites, so (c) would flood very_positive.

Framing applies only to picks:
- Names given as examples or facts are opinion none, for instance answering
  "which places do you mean?" (Q0120) or "vendors who went on to open
  restaurants" (Q0461).
- Any words the commenter adds override the framing. In Q0370, "I've always
  had great experiences here" under "terrible restaurants" is positive.

**Prompt wording** (extend RULES 8 and 11):
> A bare answer takes from the question what the question asks, and nothing
> more. Under "where for spicy noodles?" each pick is endorse, positive, with
> the dish "spicy noodles" positive. Under "easiest places to walk in?" each
> pick also gets wait positive. Under "worst meal you've had?" each pick is
> negative. Under "best X?" a bare pick is positive, never very_positive.
> Framing covers picks only: names given as examples, as facts or in answer
> to "which places do you mean?" are opinion "none". Any word the commenter
> adds about a place outranks the framing.

### 5. How broad very_positive has to be — **Settle** (the owner's rule is "broad class")

**Question.** Is "best on the UES", "one of the best meals we've had lately",
"to die for", or a superlative about one dish very_positive?

**Came up.** 6 questions: Q0127, Q0214, Q0358, Q0367, Q0506, Q0556. Beyond
those, the judges moved 42 Haiku levels from very_positive to positive and 6
the other way. The judges also split on "best on the UES": Q0214 accepted it,
and Q0556 rejected "best" near Barclays.

**Examples.**
- Q0214: *"Lucia is pricier but probably the best on the UES imo"*.
- Q0358: *"One of the best meals we've had lately and the service is top
  notch!"*

**Options.**
- (a) Any superlative.
- (b) City-wide or wider only, plus the owner's listed absolutes ("god tier",
  "life-changing").

**Recommendation: (b).** Neighborhood threads ("best near my hotel") would
otherwise fill very_positive with local picks. "Best taste" ranking needs
very_positive to mean "people call it the best in the city". Counting a
borough as broad is my call; the owner can narrow it.

A superlative about one dish makes the dish and taste very_positive. Overall
is very_positive only when that dish is what the place sells, or when the
commenter says it of the place.

**Prompt wording** (replace the very_positive line in SCALE):
> very_positive  a superlative about THIS place or its food against the whole
> city or wider ("best in NYC", "best in Queens", "best X I've ever had",
> "one of the best meals of my life"), or "god tier", "life-changing". A local
> or recent superlative ("best on the UES", "best near the park", "best I've
> had lately") and hyperbole without a class ("to die for", "unreal",
> "incredible", "phenomenal", "fire", "10/10") are positive. A superlative
> about one dish makes that dish and taste very_positive; overall is
> very_positive only when the dish is what the place sells (a slice shop's
> slice) or the commenter says it of the place.

### 6. What a comparison loss lowers — **Owner** (it extends owner rule 5)

**Question.** Rule 5 makes the loser negative. When the comparison is only
about booking ("Carbone picks you, so Don Angie"), only about price, or only
about fit ("take them to Parm, more casual"), does the loser's overall go
negative? Does a food comparison set the loser's taste?

**Came up.** 4 questions: Q0188, Q0288, Q0304, Q0587. Judges applied rule 5
broadly in Q0010, Q0326, Q0455 and Q0562.

**Examples.**
- Q0304, under "Trying to decide if Carbone is worth it for lunch?" (with a
  tween): *"Take them to parm same menu for the pasta & more casual"*. The
  judge made Carbone overall negative.
- Q0288, under "CARBONES OR DON ANGIE": *"Carbone's picks you so Don Agnie is
  probably your best bet."* The judge set overall and wait negative.

**Options.**
- (a) The loser's overall is negative whatever the comparison is about.
- (b) The loser is leveled only on what the comparison is about, and a swap
  made only for fit lowers nothing.

**Recommendation: (b).** "Go to Parm, it's more casual for a kid" is advice
about the asker, not a verdict on Carbone. Counting it as a person who rates
Carbone negatively puts a person behind a verdict they never gave. "Go
elsewhere" swaps are very common in trip-planning threads, so (a) would
steadily drain the overall counts of famous places.

**Prompt wording** (add to RULES 5):
> The loser is leveled on what the comparison is about. Food ("Pepper House's
> noodles are better") sets taste and overall. Price sets value. Lines or
> booking ("Golden Lotus is impossible to book, go to Pepper House") set wait
> only. "Go to B instead" in answer to "is A worth it?" sets overall. A swap
> made only for fit ("more casual", "better for kids", "closer to your
> hotel") is not a comparison, and the other place gets no level from it.

### 7. One branch of a chain closes, opens or moves — **Settle**

**Question.** When one location of a multi-location place closes or opens, or
is "temporarily closed", does the mention get status closed or opened, and
timeframe past?

**Came up.** 7 questions: Q0101, Q0115, Q0251, Q0295, Q0307, Q0404, Q0475.
The judges split on the same Pressed Juicery post: Q0251 and Q0404 left
status null, while Q0475 set it to closed.

**Examples.**
- Q0475, under "Another Pressed Juicery location bites the dust...": *"That
  rent too high"*.
- Q0101, on Utopia: *"I'm waiting for their new location to open by me in
  midtown."*

**Recommendation.** Rankings drop closed places, so status closed on a branch
would remove a chain that is still open from every ranking. Status is about
the place under that name. A temporary closure is not closed, because status
has no temporary value. Status also comes only from the text the model sees,
as in Q0115.

**Prompt wording** (add to the `status` field):
> Status describes the place under that name, not one branch. A branch
> closing, moving or opening ("their LES location closed", "a new one opens
> in Midtown next month") leaves status null, with the branch in location
> and a note. "Temporarily closed" or "closed for renovation" is null with a
> note.

### 8. Is a timing tip wait positive or negative? — **Settle**

**Question.** The owner's examples include "be there by 11:30" (wait
negative) and "free tables at 4" (wait positive). Both name a time. Which one
do "weekdays 12-2 is the best time to go" and "book when Resy opens the
slots" follow?

**Came up.** 3 questions: Q0281, Q0589, Q0132. In Q0589 the final ruling was
opinion none, against the convention that a timing tip is wait negative
"even when phrased as advice".

**Examples.**
- Q0589, replying to "Those lines are brutal": *"Weekdays 12-2 is the best
  time to go"*.
- Q0132, under "How hard is it to walk-in to Fish Cheeks?": *"if you go
  around 4/4:40ish there always one or two free tables"*.

**Recommendation.** Ask whether the tip implies a wait you have to plan
around (negative), or reports that getting in is easy (positive). Both owner
examples fit this, and it gives Q0589 and Q0281 a clear answer: both are
negative.

**Prompt wording** (add to RULES 1):
> A tip is wait negative when it implies a wait you have to plan around ("be
> there by 11:30", "the best time is weekdays 12-2", "book the minute slots
> open", "sold out by 2"). It is wait positive when it reports getting in
> easily ("walked right in", "free tables at 4", "no line on weekdays").

### 9. Gourmet grocers and markets with food counters — **Owner**

**Question.** Zabar's, Citarella, Gourmet Garage, Jefferson Market and
Pomegranate are stores. The rubric excludes grocery stores, but people
recommend their bagels, deli pickles and prepared salads. Are they places?

**Came up.** 7 questions: Q0031, Q0048, Q0272, Q0400, Q0416, Q0468, Q0515.
Zabar's alone came up five times. The judges kept it as a bagel place in
Q0272 and as a froyo cafe in Q0416, and dropped it in Q0031, Q0400 and
Q0468.

**Examples.**
- Q0031, under "Best deli pickles in NYC": *"zabars deli pickles for the
  win!"*
- Q0468, under "Help Finding Cheap Prosciutto Chunks?": *"Zabars occasionally
  has them. You could go and ask at the deli counter."*

**Options.**
- (a) Always out.
- (b) A mention when the comment is about food they serve to eat (a deli
  counter, bakery, cafe or prepared food), and not when it is about
  groceries.
- (c) Always in.

**Recommendation: (b).** People really do choose Zabar's for a bagel the way
they choose a bagel shop, so (a) hides real evidence from bagel and deli
searches. Under (b) the Zabar's page holds only opinions about its food,
which is what readers want from it. Downstream can still flag the place as a
store.

**Prompt wording** (replace "supermarkets and grocery stores" in WHAT
COUNTS):
> A store counts only for the food it serves to eat. A gourmet market's deli
> counter, bakery, cafe or prepared food ("Hilltop Market's deli pickles are
> the best") is a mention. A supermarket or grocery store named for groceries
> or packaged goods is not.

### 10. Timeframe for old visits — **Owner** (it depends on how scoring uses timeframe)

**Question.** Is a verdict from a visit years ago `past` when the comment
gives no sign that the place changed?

**Came up.** 6 questions: Q0096, Q0118, Q0153, Q0184, Q0334, Q0540. The
judges moved 12 Haiku `past` values to `current` and 7 `current` values to
`past`. The prompt says "a visit years ago with nothing about now" is past.
The judges mostly overruled that, though not always: Q0540 ("used to work
here and my go tos were…") ended up past.

**Examples.**
- Q0153: *"I used to work a few blocks away and we went for a work lunch
  there… probably the most disgusting meal I've ever had in my life."*
- Q0540: *"Used to work here and my go tos were One More Thai and Lava
  Shawarma."*

**Options.**
- (a) Past only when the comment says the place changed or closed.
- (b) Past also when the visit is clearly long ago (years ago, back in 2015,
  "used to"), unless the commenter says it still holds.

**Recommendation: (b), which keeps the prompt as it is.** The owner already
counts past-only opinions, so (b) removes nobody from the counts. What it
changes is momentum. If an opinion from 2015 is dated by a 2026 comment,
that opinion shows up as recent evidence. Under (b) the label stays honest
about when the meal happened.

The rubric should then be changed to match, because the judges followed (a).
- If the owner never uses timeframe for recency, (a) is simpler.
- A closed place with no verdict (Q0184) is still past.
- A favorite that moved and changed what it sells (Q0334, *"now they only
  sell caviar. So lame"*) is current negative, with trend declined and status
  moved.

**Prompt wording** (replace the `timeframe` field):
> timeframe  "past" when the levels describe the place as it was: it is
> closed, the comment says it changed, or the visit was long ago ("years
> ago", "back in 2015", "when I worked nearby") with nothing tying it to now.
> "current" when the commenter says it still holds ("still great", or they
> agree with a recent report), and for recent visits.

---

## Owner calls with fewer cases

### 11. Boycotts over politics, deals or a chef's persona — **Owner**

**Question.** Should a boycott over a company's politics, or an attack on a
chef's persona, lower a place's levels?

**Came up.** 3 questions: Q0008, Q0140, Q0513. The judges' finals were
negative for Sweetgreen in Q0140 and Q0513, and no mention in Q0008.

**Examples.**
- Q0140, after a link to Sweetgreen's partnership with RFK Jr.: *"Didn't know
  this def gonna avoid now"*.
- Q0008, on David Chang: *"…he claimed to be a ramen expert… What an ass."*

**Options.**
- (a) Overall negative.
- (b) No level, with a note saying why.

**Recommendation: (b).** Overall answers "is it good to eat at?". Boycotts
spike with the news cycle and come mostly from people who aren't judging the
food, so (a) would turn one news story into dozens of "negative" people on a
place page. Conduct the commenter saw *at* the place, such as staff being
berated in front of diners, is still service.

**Prompt wording** (add to RULES 2):
> A reason not to go that isn't about eating there (the owner's politics, a
> business deal, a chef's public persona) is not a complaint about the place.
> It sets no level: opinion "none" unless something else is judged, with a
> note ("boycott: partnership with X"). Conduct the commenter saw at the
> place is service.

### 12. Food halls and night markets — **Owner**

**Question.** Are Smorgasburg, Queens Night Market and Food Gallery 32
mentions, or only their stalls?

**Came up.** 3 questions: Q0084, Q0461, Q0491. The judges said no in Q0084
and yes in Q0461 and Q0491.

**Examples.**
- Q0491: *"Most of that whole first floor food court kinda sucks (pelicana
  fried chicken on third floor is good…)"*.
- Q0084: *"Have you been to queens night market?… it's super kid friendly"*.

**Recommendation: yes, and each named stall too.** People choose these as
destinations, and threads judge them as a whole ("quality has gone down"),
so readers will search for them.

**Prompt wording** (add to WHAT COUNTS):
> Food halls, night markets and other multi-vendor food markets ("Riverside
> Night Market") are mentions, and so is every stall named in them.

---

## Consistency calls (settle)

### 13. Ranked lists, near misses, unnamed and low-bar winners

**Came up.** 5 questions: Q0131, Q0238, Q0242, Q0294, Q0476.

**Examples.**
- Q0242: *"Apollo, Liberty, Ess-a, Leos in that order."*
- Q0476: *"There's certainly better burritos in NY (even Chipotle ffs)"*.

**Recommendation.**
- Ranked picks are all recommendations, so all are positive, with the order
  in a note. Otherwise every ranked list would turn picks two to four into
  complaints.
- "Closest, but not the same" is a loss, so negative.
- The loser rule needs a winner the comment names. With an unnamed favorite
  (Q0294's gatekeeper, Q0238's homemade ice cream), the place is leveled only
  on what is said about it.
- A low-bar winner ("even Chipotle") gives no verdict on the winner.

**Prompt wording** (add to RULES 5):
> Picks ranked against each other ("Golden Lotus, Pepper House, Noodle Lab in
> that order") are all positive; note the order. "Close, but not the same as
> A" makes the other place the loser. The loser rule needs a winner the
> comment names or clearly identifies; with an unnamed winner ("my real
> favorite is elsewhere") level the place only on what is said about it. A
> winner used as a low bar ("even Burger Barn is better") gets no level.

### 14. Where seating, format and fit complaints go

**Came up.** 4 questions: Q0107 (prix fixe only), Q0123 ("not somewhere I'd
take a young kid"), Q0283 ("barely any seating"), Q0587 ("100% less the
headache").

**Recommendation.**
- Format and policy complaints fall under the owner's "how the place is run",
  so they are service.
- Seating is about the room, so it is atmosphere. Waiting for a seat is wait.
- Fit for one person or occasion is not a knock: a bar isn't worse because
  it's no place for a toddler. It goes in a tag or a note.
- A vague "hassle" sets no aspect.

**Prompt wording** (add after the aspect definitions):
> service also covers policies and format said as a complaint ("prix fixe
> only", "no substitutions"). Seating ("barely any seating", "standing room
> only") is atmosphere; waiting for a seat is wait. Fit for one person or
> occasion ("not for young kids", "too fancy for a first date") is a tag or
> note, not a level. An unnamed "hassle" sets no aspect.

### 15. Hygiene, health violations, food poisoning

**Came up.** 4 questions: Q0224, Q0268, Q0444, Q0482. The judges put
violations under service twice.

**Example.** Q0482: *"Only spot to avoid is Tramway Diner… already so many
violations they've been shut down a couple times."*

**Recommendation.**
- Hygiene goes to overall plus a note, not service. Readers who filter by
  service want to know how they will be treated, not inspection grades.
- Getting sick is very_negative (decision 2). Taste stays null unless the
  flavor is judged, because food poisoning is not a taste verdict.
- Filing a complaint over the OP's photos (Q0444), or 311's response time
  (Q0224), is a reaction to someone else's report, so it gives no level
  (decision 1).

**Prompt wording** (add to RULES 2):
> Hygiene and health problems (a dirty kitchen, a bad grade, violations,
> shutdowns) lower overall, not service, with a note "hygiene". Getting sick
> or finding bugs in the food is very_negative; taste stays null unless the
> flavor is judged.

### 16. What counts as avoid

**Came up.** 3 questions: Q0284 ("replace Saigutte with Banh And Em"), Q0309
("avoid the times sq location"), Q0565 ("should be burned to the ground").

**Recommendation.** avoid is an instruction to skip the place itself.
- A swap is a comparison, not an instruction.
- A branch-only warning leaves the place's flag false. Otherwise a
  Times Square warning marks every Joe's.
- An extreme insult with no instruction is a level, not an avoid.

**Prompt wording** (add to the `avoid` field):
> "Replace X with Y" or "go to Y instead" is a comparison, not avoid.
> Avoiding one branch ("avoid the Times Square one") leaves avoid false, with
> the branch in location and a note. An insult with no instruction ("should
> be burned down") is a level, not avoid.

### 17. Nameless replies and places with no name

**Came up.** 6 questions: Q0156 ("that place on Christopher St"), Q0232 (a
general rule about grade cards under a Semma post), Q0286 ("real mood" about
a photo), Q0405 (the naming comment was deleted), Q0425 ("a place on
rivington"), Q0550 (a reply that could mean the parent's place or the
post's).

**Recommendation.**
- A place nobody can name can't get a page, so it can't be counted honestly.
- Treating every nameless reply in a single-place thread as a mention would
  inflate popular.
- For an ambiguous reply, pick the place the reply's words fit, as the judge
  did in Q0550.

**Prompt wording** (add to WHAT COUNTS):
> A reply that neither names nor judges a place is not a mention of it. A
> place neither the comment nor the context names ("a taco spot on
> Rivington", "that place around the corner") is not a mention. When a
> nameless reply could mean the parent's place or the post's, use the one its
> words fit; if neither clearly fits, skip it.

### 18. Music clubs, comedy clubs, game bars

**Came up.** 3 questions: Q0243 (The Groove, Terra Blues, Comedy Cellar),
Q0354 (Birdland, Iridium, called "venues"), Q0500 (Spin).

**Recommendation.** They are not places unless the comment discusses their
food or drink. A bar whose music is part of the draw, such as a jazz bar or a
supper club, is a bar. The rubric already excludes venues; this draws the
line.

**Prompt wording** (add to WHAT COUNTS):
> Entertainment venues (music and comedy clubs, game bars, theaters) are not
> places unless the comment talks about their food or drink; a bar or supper
> club where the music is part of the draw is a bar.

### 19. Brands, companies, chefs, rooms inside restaurants

**Came up.** 5 questions: Q0078 (Grillo's Pickles pop-up), Q0091 ("the una
napoleon pizza guy"), Q0135 (Unapologetic Foods), Q0249 (the Modern's Kitchen
Table), Q0488 (frozen Arby's fries from the supermarket).

**Recommendation.**
- Products, restaurant groups and chefs are not places to eat. A one-off
  brand pop-up is an event, not a place.
- A place named only to identify a person is still a name in passing, which
  the owner counts as a mention.
- A room inside a restaurant is part of that restaurant, the same rule as one
  mention per place.

**Prompt wording** (add to "Not places"):
> packaged brands and grocery products ("a bag of Burger Barn frozen fries"),
> restaurant groups and companies, chefs and owners. A place named only to
> identify a person ("the Golden Lotus chef") is a name in passing, opinion
> "none". A room, counter or tasting menu inside a restaurant is part of that
> restaurant's mention, with a note.

### 20. "RIP X", "too bad it closed"

**Came up.** 2 questions: Q0218 ("Too bad it closed down"), Q0299 ("RIP Stage
Restaurant too"). The judges ruled the same way in Q0251, Q0369 and Q0498.

**Recommendation.** It is a fond verdict, the owner's "I miss it" case. The
judges agreed every time, so this just writes it down.

**Prompt wording** (extend RULES 10):
> Regret that a place closed ("RIP Golden Lotus", "too bad it closed", "nooo,
> I was just there") is a fond verdict: stated, overall positive, status
> closed, timeframe past.

### 21. What trend means

**Came up.** 4 questions: Q0124 (a prediction after a private-equity deal),
Q0143 (booking got easier), Q0297 and Q0404 (business decline).

**Recommendation.** Trend means the quality changed. Readers search by
momentum, and "improved" has to mean the place got better, not that it got
easier to book or lost customers. A prediction is not a verdict. In Q0124 the
comment even calls the current taco great, so I'd overturn the judge's
negative there.

**Prompt wording** (replace the `trend` field):
> trend  "declined" or "improved" when the comment says the place got worse
> or better (the food, or the place as a whole). Not business health (empty
> stores, closing branches), not a prediction ("it'll go downhill after the
> buyout"), and not a change in one aspect such as booking, which goes in
> that aspect and a note.

### 22. Remarks about a whole category or list

**Came up.** 3 questions: Q0309 ("You've basically listed the standard
tourist spots"), Q0420 ("most Chinatown spots… a ton of things that are
pretty mid"), Q0469 ("$100 for a steak these days is wacky").

**Recommendation.** A remark about a whole category lowers a named place only
when the comment applies it to that place. In Q0420 the commenter applies it
to Noodle Village; in Q0469 the commenter does not apply it to Keens. A knock
on a list nobody names in the comment adds no mentions.

**Prompt wording**:
> A remark about a whole category ("$100 steaks are wacky", "most noodle
> shops have a few great dishes") lowers a named place only when the comment
> applies it to that place. A remark about a list that doesn't name its
> places ("you've listed the tourist spots") adds no mentions.

### 23. Lukewarm defenses, middling prices, "like it but not worth it"

**Came up.** 4 questions: Q0083 ("$13, not the best or worst price"), Q0179
("It's a small business get a grip"), Q0453 ("I like it very much, but… it
becomes very not worth it"), Q0462 ("it's not that bad").

**Recommendation.** Apply the owner's rules as written:
- Lukewarm is negative, even in a defense ("not that bad") or about price
  ("not the best or worst"). The judge called Q0083 neutral; this changes
  it.
- An excuse with no verdict is opinion none.
- "Not worth it" is a bottom line, so negative.

If the owner wants "fairly priced" to read as neutral, that would be a
deliberate exception to the lukewarm rule, and it should be written down.

**Prompt wording** (extend RULES 3):
> Lukewarm stays negative in a defense ("it's not that bad") and about price
> ("not the best or worst price"). A reply that only excuses a flaw ("it's a
> small business") is opinion "none". "I like it, but it's not worth it" is
> negative: the bottom line wins.

### 24. Jokes and banter

**Came up.** 6 questions: Q0043 (McDonald's "pink slime" in an argument),
Q0087 ("You be quiet now" under a Molly's rec), Q0129 (a friend's proposal at
the Times Square McDonald's), Q0427 ("its not a slice"), Q0442 (a chalupa
innuendo), Q0457 ("Ahh the memories….or lack thereof…" under Verlain).

**Recommendation.**
- A joke counts when its point is a verdict on the place. The gatekeeping
  "shh" and fond drinking memories are endorsements. A sneer at a chain's
  food is a knock, leveled by decision 2.
- Lyrics, innuendo, other people's anecdotes and pedantry about categories
  ("might be delicious but it's not a slice") give no verdict. The final
  ruling in Q0427 was negative; I'd make it none.

**Prompt wording**:
> A joke counts when its point is a verdict on the place: "shh, don't tell
> anyone" under a rec is endorse; "Burger Barn's cardboard nuggets" is a food
> knock. Lyrics, innuendo, stories about other people and arguments over
> labels ("that's not a real slice") give no verdict: opinion "none".

### 25. Agreement replies that agree with something else

**Came up.** 2 questions: Q0541 ("Get Out Of My Head!", agreeing with the
parent's Springsteen analogy about EMP), Q0550 ("Damn if it aint delicious
though").

**Recommendation.** Rule 9 carries the parent's verdict only when the reply
agrees with what the parent said about the place. If agreeing with a side
point could carry a verdict, people would be counted for opinions they never
gave.

**Prompt wording** (extend RULES 9):
> This only applies when the reply agrees with the verdict on the place;
> agreeing with an analogy or a side point carries no verdict.

### 26. Judging items that need unseen context (rubric only)

**Came up.** 2 questions: Q0071 (Radio Bakery is named only in a grandparent
comment), Q0115 (Pig and Khao is closed according to a reply Haiku couldn't
see).

**Recommendation.** Keep the current procedure. Record the right answer in
`missed` with `right: "neither"` and the reason "needs wider context". Status
comes only from the text the model sees. No prompt change; the scorer should
keep `neither` items out of Haiku's error count.
