# Round 4: where each rule lives

The judges' rules are the prompt's text, so prompt and rubric cannot disagree: the
"rules the model was given" half of `RUBRIC.md` is generated from
`eval/prompts/v6_common.py` and `v6_comment.py` by `rubric.py`, and `eval/v6_selftest.py`
fails when it is out of date. The hand-written half of `RUBRIC.md` is only procedure:
what a judge sees, the blind read, the compare format, the files a judge may not open.

This list is the checklist the code review and the pre-check asked for: each decision,
and the prompt section that states it (the rubric states it in the same words).

| decision | prompt section |
|---|---|
| Bare name answering a negative question: opinion stated, overall knock | rules 6; fields `opinion`; checklist; example "Most overrated restaurant around?" |
| Endorse fills overall praise only when overall is missing (validator) | `v6_validate.r_endorse_positive` |
| A price word or figure alone is price, not value; a price fact is not a complaint | fields `value`; rules 1 |
| A price said as a complaint is value; a complaint about one dish's cost is value only | fields `value` |
| A bar or supper club with music is a bar; venues count only for their food or drink | fields `kind` |
| A tasting menu, room or counter is part of its restaurant | what_counts |
| Surprise fees and card surcharges are value | fields `value` |
| Policies ("no substitutions", "tasting menu only") are service | fields `service` |
| Seating is atmosphere; fun or lively is atmosphere praise | fields `atmosphere` |
| A comparison or pick the commenter only reports is secondhand | fields `experience`; rules 5, 8 |
| A place named only to identify a person: a mention, opinion none | what_counts |
| `other` is not a food place; every food or drink place gets a counted kind (dessert, bubble tea, juice: cafe; bodega: deli; pop-up: restaurant) | fields `kind`; checklist |
| Specialty food shops, gourmet grocers' prepared food, bazaars, supplier bakeries take a food kind; grocery only for grocery shopping | what_counts; fields `kind` |
| One branch closing, even with regret: no verdict, opinion none, status null | rules 7; fields `status`; example "Bagel spots you miss?" |
| A whole place closing, regretted or under a closed-places title: fond verdict, closed, past | rules 7 |
| Thread example picks under "Best noodles in Queens?" get dish noodles praise | thread prompt, `<thread_example>` |
| Only what this comment says; earlier verdicts (post by "you", "you, earlier") are not copied | `<input>` (comment mode), thread `<input>` |
| A place named in a `<quote>` the comment answers is referred to | `<input>` |
| A reply that neither names nor judges a place is not a mention | what_counts; `<input>` |
| When opinion is none, experience is none | fields `experience`; checklist |
| Reactions to someone else's report: no verdict | rules 3 |
| Untried wins over a verdict on something only seen | rules 3 |
| "Haven't been, but heard it's great": secondhand; "haven't gone lately": been; "going today": untried | rules 3 |
| A pick whose only words are about getting in: endorse, overall praise, wait as stated | fields `overall` |
| The wait never sets or lowers overall, even "favorite, but not worth the line" | fields `overall`; checklist |
| Bare answers take the question's aspect only when the question is about it; a worry in the post is not | rules 6 |
| Answers given with facts are picks; names given as examples are opinion none | rules 6 |
| Mixed taste needs an even weighing; one knocked dish among praised ones stays praise | fields `taste`; levels `mixed` |
| A dish praised by "get the X" or the question's framing sets taste praise | fields `taste`; example 1 |
| Dated or old visits are current unless tied to then | fields `timeframe` |
| "gross" is a knock; extremes only inedible, disgusting, got sick, food poisoning, worst ever, avoid at all costs | levels |
| Unnamed vendors identifiable by what and where are mentions, named by the description | what_counts |
| Healthiness is a tag, not taste | fields `taste`, `tags` |
| Second-guessing a business decision, fake reviews, workaround fees: a note, no level | fields `notes`; rules 2, 10 |
| A boycott sets no level, but a food or service jab in the same comment counts | rules 10 |
| A story about someone's occasion at a place, surprise at a recipe change: opinion none | fields `opinion` |
| A plain word for what a place sells is a dish; the losing dish in a dish comparison gets a knock | fields `dishes` |
| Trend counts a change in one dish; not booking, prices or service alone | fields `trend` |
| A complaint about what a place now sells lowers overall, not taste | fields `overall` |
| A skip aimed at some readers is not avoid | fields `avoid` |
| A swap for fit gives the other place no level, even "similar food but more relaxed" | rules 5 |
| A pick that answers the question is its bottom line even when one dish disappoints | fields `overall` |
| "X is your safest pick" is an endorsement | fields `opinion` |
| Owner decisions of round 4 (untried, wait, mild words, extremes, scores, comparisons, boycotts, stores and halls, old visits, branches, timing tips, "for the price") | levels; fields; rules 2 to 10 |

Judge-only rules (procedure, not extraction): judge against what the model could see
("needs wider context" is `neither`); places of an excluded kind are already removed from
the output shown, so a real food place among them is a miss; open no file but the rubric
and the packet.
