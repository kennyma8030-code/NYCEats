# Extraction conventions

These are the owner's rules for what a mention is and how it is leveled. One
rule per case. The v6 prompt (`eval/prompts/v6_common.py`), the scorer
(`eval/score.py`) and the gold should all follow them. Where the v1/v2 gold
disagrees, the counts are below, and candidate patches are listed in
`eval/labels/proposed_convention_patches.py`. Those patches are **not
applied**. Each needs a human read before it moves into
`labels/adjudication.py`.

Levels are the owner's five: very_positive, positive, neutral, negative,
very_negative, or null for not mentioned. The gold's 7 points map onto them
as ±3 → very, ±1/±2 → positive/negative, 0 → neutral.

## The rules

Round 4 adds the owner's final decisions below the first table; where a row of the
first table disagrees with them (line tips, very negative, closed and past), the
decision wins. `eval/review_v6r4/RUBRIC.md` and the round-4 prompt state them in full.

| case | rule | example |
|---|---|---|
| **Comparison losers** | The loser gets a level. Negative by default. Very_negative when the comment says it is far worse. Positive when the comment says both are good ("both great, I just prefer A"). Note the comparison on both places. | "Prefer Saperavi over Chama Mama": Saperavi positive, Chama Mama negative |
| **Landmarks and asides** | Every named place is a mention, including one used as a landmark, an example or a comparison. With nothing judged it is `opinion: none`, all levels null. | "near Kossar's Bialys and the Doughnut Plant": two mentions, opinion none |
| **Question replies** | A reply that only asks about a place, or names it in passing, is a mention with `opinion: none` and no levels, and nothing more. | "Where is it located?" under a rec: a mention of that place, opinion none |
| **Line and timing tips** | A line, a wait, a timing tip or "it was busy" is wait negative, even when phrased as advice. | "the line started at 4:15", "be there by 11:30", "busy even in the rain" |
| **Lukewarm** | "fine", "ok", "not bad", "meh", "mid" are negative. Neutral is only for a balanced verdict, good and bad weighed evenly. A lukewarm *dish* is a negative dish entry; the place's level follows the rest of the comment. | "Hamburger America was fine. Not bad, not exceptionally good.": negative |
| **Very positive** | Only a superlative about this place against a broad class. "Great", "amazing", "so good", "love it", "my favorite", "my go-to" and "a must" are positive. This matches the gold, where "my favorite" is +2 and "my favorite in the city" +3. | "best slice in the city": very_positive; "my favorite": positive |
| **List headers** | A heading covers every item under it. "My favorites:" makes each item positive, and very_positive only for an item given its own superlative. An avoid heading makes each item avoid, overall negative. | "Personal favs: A, B, C": three positives |
| **Bare endorsements** | A name offered as a pick with nothing said is `opinion: endorse`, overall positive, aspects null. It counts as "praised". | "Lucali" under "best pizza?" |
| **Secondhand** | Secondhand opinions are extracted and leveled like firsthand ones (`experience: secondhand`), and scoring counts them the same. A verdict in the commenter's own voice ("mid", "overrated", "get the X") is firsthand unless they say they haven't been. | "heard it's great": positive, secondhand |
| **Closed and past** | A closed place keeps its mention, with `status: closed` and its remembered verdict (`timeframe: past`). Rankings exclude closed places, but their pages stay. Past-only opinions count, dated by the comment. "Used to be great, now mid" counts the current verdict (negative) with `trend: declined`. | "I loved Alta, but it closed": positive, closed, past |

## Owner decisions for round 4 (final)

| case | rule |
|---|---|
| **Untried reactions** | "looks so good", "sounds amazing", "can't wait to try", "saved it": a mention with opinion none and no levels. |
| **Wait-only remarks** | The wait never sets or lowers overall: a remark only about the wait sets wait and leaves overall null, and "my favorite, but not worth the line" is overall positive with wait negative. A pick whose only words are about getting in is an endorsement, overall positive. A lone taste, value, service or atmosphere verdict does set overall; otherwise overall follows the bottom line, else the strongest non-wait point. |
| **Mild words** | "decent", "solid", "good for what it is": positive. "average", "mediocre", "not worth the trip", "fine", "ok", "not bad", "meh", "mid": negative. |
| **Extremes** | "terrible", "awful", "never again", "regretted going" are negative. very_negative only for extremes (worst ever, inedible, disgusting, got sick, avoid at all costs). very_positive only for city-wide-or-broader superlatives; local, recent and classless hyperbole ("to die for", "unreal", "10/10", "best on the UES") is positive. |
| **Scores** | 8/10 and up positive; 5 to 7 negative; below 5 negative, very_negative only with extreme words. |
| **Bare answers** | take the question's polarity and dish, and its aspect only when the question asks about that aspect (a reservation worry in the post doesn't count), never its superlative. A bare name answering a negative question is opinion stated with the knock. A place offered as an answer is a pick even when only facts are given; names given only as examples are opinion none. |
| **Comparisons** | the loser loses only on what was compared; a swap for fit lowers nothing; no loser without a named winner; ranked picks are all positive. |
| **Boycotts** | politics, business deals, a chef's persona: no level, a note only. |
| **Stores, halls** | a gourmet grocer is a mention when the comment is about food it serves to eat, not groceries. A food hall or night market is a mention, and so is each named stall. |
| **Old visits** | timeframe current unless the comment ties the verdict to an earlier time. |
| **Chain branches** | one branch closing, opening or moving: status null, the branch in location and a note. |
| **Timing tips** | wait negative when you plan around a wait, positive when getting in is easy. |
| **"for the price"** | praise or complaint by the word before it. A price word alone is price, not value. |
| **Mild and extreme words** | "gross" is negative; very_negative only with inedible, disgusting, got sick, food poisoning, worst ever, avoid at all costs. |
| **Untried, refined** | reactions to someone else's report with nothing from their own visit carry no level; "haven't been, but heard it's great" is secondhand with that verdict; "haven't been in a while" means they have been; "going today" is untried. |
| **Earlier verdicts** | levels come only from what this comment says; the commenter's earlier comment or post is counted where they wrote it, never copied into this one. |
| **No opinion, no experience** | when opinion is none, experience is none. |
| **Described vendors** | an unnamed vendor identifiable by what and where ("the tamale lady at X", "the halal cart on 53rd and 6th") is a mention, named by that description. |
| **Tags, not levels** | "healthy" is a tag, not taste; second-guessing a business decision is a note, no level. |

The "settle" decisions in `review_v6/analysis/decisions.md` (13 to 25) and the wording fixes in `review_v6/analysis/precheck_r4.md` apply as recommended.

## Where the v1/v2 gold disagrees

Counts come from a read-only scan of the 1,006 gold comments (1,369
mentions). v1 is used where a comment is in both sets. Each scan is a
heuristic: the counts are **candidates**, not confirmed disagreements.

| rule | gold agrees | candidate disagreements | proposed patch |
|---|---|---|---|
| Comparison losers | all 3 losers the pattern finds are already negative (Soothr, Kabawa, Chama Mama). The v1 labels scored losers −1 | 0. The round-1 benchmark misses here were v6's old rule, not the gold | none |
| Landmarks and asides | gold requires reference mentions (eval/README) | 2 references named in the comment that v6 emitted and the gold lacks; 72 gold reference mentions marked `ambiguous` | 2 `add` candidates |
| Question replies | – | 45 context-named, no-opinion mentions v6 emitted that the gold lacks; 13 gold question replies marked `ambiguous` | 45 `add` + 13 `set ambiguous: false` |
| Line and timing tips | the v1 rule already makes "never able to get a reservation" wait −1 | 46 gold mentions in comments with line or timing words but no wait level. Noisy: the scan can't tell which place the tip is about | 46 `alt wait: [-1]` |
| Lukewarm | "meh" is −1 in 8 of 11 gold mentions, "not bad" −1 in both | 4. One is place-level (Russ & Daughters, "their bagels are very meh", food +1). Three are a lukewarm dish beside praise for the rest, which agrees with the dish rule | 1 `alt food: [-1]` |
| Very positive | gold food is +3 on 43 mentions and +2 on 242. The prompt now follows the gold's convention | none (the 107 of 314 +2 mentions v6 r1 called very_positive were the old prompt's error) | none |
| List headers | the 9 gold items under a favorites header are all +2 (positive). None is +3 | 0 | none |
| Bare endorsements | 430 gold mentions are food +1 and nothing else. +1 collapses to positive, which is the endorsement's overall | 0 | none |
| Secondhand | 40 gold mentions are secondhand with a verdict, leveled like firsthand | 0 (a scoring note only) | none |
| Closed and past | 37 closed gold mentions have aspects nulled by the v1 rule. The adapter nulls a closed v6 mention's aspects too, so scores agree | 0 for scoring. If the remembered verdict is ever scored, these need levels | none |

**Proposed patches:** 107 in total (63 on v1 labels, 44 on v2 top-ups).

| type | count |
|---|---:|
| line tip | 46 |
| question reply marked ambiguous | 13 |
| reference v6 found and the gold lacks | 47 |
| lukewarm | 1 |

Top-up items have no patch hook. `eval/v2/build_v2.py` would need one that
applies patches by v2 item id. Some candidates are visibly wrong: one line
tip is about Via Carota but attaches to Shmone, and "Deep Queens" is not a
place. They must be read before any is applied.

## How the scorer follows these rules

`score.py` applies three fixes by default. `--legacy-scorer` (or
`fixes=False`) reproduces the old numbers.
- A v6 mention whose overall verdict is negative counts as a negative
  mention, even when no aspect is ("most overrated restaurant on the
  planet… good pizza").
- Street words match their short forms ("2nd avenue deli" = "2nd ave deli").
- An unmatched mention named from context with `opinion: none` is not a
  false positive, in comment and thread mode alike. This follows the
  question-reply rule while the gold still lacks most of them.

New metrics, all on the five levels: per-aspect accuracy, a food confusion
table (gold → model, nulls included), overall-verdict agreement (gold
verdict = food, or else the strongest aspect), and opinion-type accuracy
where the gold can tell (all-null → none; anything beyond a lone +1 food →
stated; a lone +1 food is skipped, since the gold can't separate an
endorsement from mild praise there).
