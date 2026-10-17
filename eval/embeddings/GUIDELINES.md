# Relevance judging guidelines

Written before any retrieval results were seen. Every judge, first pass and
re-judge pass, gets this file verbatim.

## The setting

NYCEats is a search box over r/FoodNYC. Someone types a query ("date night",
"cheap tasting menu"). The system returns Reddit comments, then groups them by
the restaurants they mention. You are deciding whether a comment is good
evidence for the searcher's need. A comment is shown as the thread title it was
posted under, followed by the comment body. Judge the **comment body**; the
title is context that can tell you what the comment is answering (for example,
a bare "Lilia" under the title "Best date night spot?" is a date-night
recommendation).

Each query comes with an `intent` line written by the query author. Grade
against the intent, not the literal words.

## Grades

- **2: clearly answers the query.** The comment recommends, endorses or
  describes a specific place (or places) as fitting the need. "Lilia is perfect
  for a date, dim and cozy" for *date night*. A recommendation in reply to a
  thread that asked exactly this question counts, even if the comment just names
  the place.
- **1: partially relevant.** On topic but weaker evidence. It mentions the need
  in passing, is about the right dish/cuisine but not clearly recommending a
  place for it, fits part of a compound query (the right cuisine in the wrong
  neighborhood, a tasting menu that isn't cheap), or is a lukewarm or hedged
  endorsement ("it's fine for a date I guess").
- **0: not relevant.** Off topic, generic chatter, or a place mention with no
  connection to the need. **Also 0: negated or opposite comments**, where the
  comment is on the topic but says the place does *not* fit: "Don't bring a
  date here, it's deafening" is 0 for *date night*; "the soup dumplings were
  doughy and bland, skip them" is 0 for *best soup dumplings*.

### Avoid-intent queries

Some queries ask for places to avoid ("overrated spots", "tourist traps",
"not worth the hype", "worst service"). For these, a comment that **calls a
place** overrated / a tourist trap / bad service is the answer: grade it 2 if it
clearly does, 1 if it's hedged. A comment that *defends* a place against that
charge ("people say it's a tourist trap but it's actually great") is 1 at most,
because it names the topic but argues the opposite. A comment recommending a
place with no avoid angle is 0.

### Compound and exclusion queries

For "X that isn't Y" queries ("pizza that isn't a dollar slice", "a steakhouse
other than peter luger"), a comment that recommends Y itself is 0, a comment
about X that also satisfies the exclusion is 2, and one about X that doesn't
clearly satisfy it is 1.

## The `opposite` flag

When you give a 0 because the comment is **on the query's topic but negated or
opposite** (says the place is bad for that need, says not to go for that
reason, says the feature is absent: "no outdoor seating", "way too loud to
talk"), set `opposite: true`. For any other 0, and for every 1 or 2, set
`opposite: false`. This flag measures how often a system mistakes "not a date
spot" for "date spot".

## Practicalities

- Judge each pair on its own. Do not try to guess which system found it; you
  are not told and the order is shuffled.
- Do not reward length. A one-line "Lilia." under a date-night thread can be a
  2; a long review that never touches the need is 0.
- If the comment is unreadable, a bot, or only a link, grade 0.
- Missing context you can't infer: grade what the text supports, leaning to 1
  rather than 2 when it's genuinely ambiguous.
- Output one JSON object per pair: `{"pair_id": ..., "grade": 0|1|2,
  "opposite": true|false}`.
