# Opus review of Haiku round 4

Judged items: 1327 of 1327; auto-resolved outputs: {'r600-med': 367, 'hard-med': 36, 'fresh-med': 190}.

- Planted errors caught: 0.943 {"drop_dish": {"caught": 11, "n": 13}, "drop_mention": {"caught": 26, "n": 27}, "flip_overall": {"caught": 23, "n": 24}, "upgrade_negative": {"caught": 10, "n": 10}, "wrong_experience": {"caught": 30, "n": 32}}
- Judge first read overturned by its own re-read: 0.223 ({'judge': 1267, 'haiku': 368, 'neither': 16})

## raw output

| | fresh-low | fresh-med | hard-low | hard-med | r600-low | r600-med |
|---|---:|---:|---:|---:|---:|---:|
| items | 300 | 300 | 60 | 60 | 600 | 600 |
| item_ok_rate | 0.634 | 0.791 | 0.627 | 0.686 | 0.637 | 0.753 |
| mention_recall | 0.891 | 0.935 | 0.883 | 0.913 | 0.916 | 0.961 |
| mention_precision | 0.974 | 0.972 | 0.968 | 0.979 | 0.987 | 0.981 |
| negative_recall | 0.818 | 0.884 | 0.708 | 0.833 | 0.873 | 0.918 |
| overall | 0.912 | 0.937 | 0.893 | 0.943 | 0.921 | 0.935 |
| aspects.taste | 0.828 | 0.938 | 0.89 | 0.894 | 0.849 | 0.918 |
| aspects.value | 0.985 | 0.985 | 0.989 | 1.0 | 0.984 | 0.989 |
| aspects.service | 0.992 | 0.989 | 0.989 | 1.0 | 0.993 | 0.993 |
| aspects.atmosphere | 0.958 | 0.967 | 1.0 | 1.0 | 0.99 | 0.994 |
| aspects.wait | 0.985 | 0.996 | 0.978 | 0.947 | 0.964 | 0.977 |
| experience | 0.926 | 0.944 | 0.91 | 0.946 | 0.934 | 0.963 |
| opinion | 0.893 | 0.93 | 0.857 | 0.904 | 0.916 | 0.945 |
| avoid | 1.0 | 1.0 | 0.978 | 0.979 | 0.994 | 0.992 |
| timeframe | 0.996 | 0.993 | 1.0 | 1.0 | 0.982 | 0.987 |
| trend | 0.996 | 0.996 | 1.0 | 1.0 | 0.994 | 0.996 |
| status | 1.0 | 1.0 | 0.989 | 0.989 | 0.991 | 0.994 |
| price | 0.996 | 1.0 | 1.0 | 1.0 | 1.0 | 0.999 |
| dishes | 0.661 | 0.807 | 0.71 | 0.656 | 0.701 | 0.82 |

## with validators

| | fresh-low | fresh-med | hard-low | hard-med | r600-low | r600-med |
|---|---:|---:|---:|---:|---:|---:|
| items | 300 | 300 | 60 | 60 | 600 | 600 |
| item_ok_rate | 0.666 | 0.787 | 0.627 | 0.686 | 0.646 | 0.756 |
| mention_recall | 0.891 | 0.935 | 0.883 | 0.913 | 0.916 | 0.961 |
| mention_precision | 0.974 | 0.972 | 0.968 | 0.979 | 0.987 | 0.981 |
| negative_recall | 0.818 | 0.884 | 0.708 | 0.833 | 0.873 | 0.918 |
| overall | 0.923 | 0.926 | 0.893 | 0.943 | 0.921 | 0.937 |
| aspects.taste | 0.832 | 0.934 | 0.89 | 0.894 | 0.853 | 0.92 |
| aspects.value | 0.985 | 0.985 | 1.0 | 1.0 | 0.984 | 0.989 |
| aspects.service | 0.992 | 0.989 | 0.989 | 1.0 | 0.991 | 0.993 |
| aspects.atmosphere | 0.962 | 0.967 | 1.0 | 1.0 | 0.99 | 0.994 |
| aspects.wait | 0.985 | 0.996 | 0.978 | 0.947 | 0.964 | 0.977 |
| experience | 0.942 | 0.944 | 0.899 | 0.946 | 0.956 | 0.96 |
| opinion | 0.893 | 0.93 | 0.857 | 0.904 | 0.916 | 0.945 |
| avoid | 1.0 | 1.0 | 0.978 | 0.979 | 0.994 | 0.992 |
| timeframe | 0.996 | 0.993 | 1.0 | 1.0 | 0.982 | 0.987 |
| trend | 0.996 | 0.996 | 1.0 | 1.0 | 0.994 | 0.996 |
| status | 1.0 | 1.0 | 0.989 | 0.989 | 0.991 | 0.994 |
| price | 0.996 | 1.0 | 1.0 | 1.0 | 1.0 | 0.999 |
| dishes | 0.661 | 0.798 | 0.677 | 0.656 | 0.711 | 0.823 |

## round 3 on the 600, same finals

| | r600-low (r3) | r600-low (r3, validators) |
|---|---:|---:|
| items | 600 | 600 |
| item_ok_rate | 0.403 | 0.469 |
| mention_recall | 0.938 | 0.938 |
| mention_precision | 0.984 | 0.984 |
| negative_recall | 0.904 | 0.911 |
| overall | 0.756 | 0.829 |
| aspects.taste | 0.724 | 0.753 |
| aspects.value | 0.971 | 0.975 |
| aspects.service | 0.982 | 0.988 |
| aspects.atmosphere | 0.975 | 0.98 |
| aspects.wait | 0.94 | 0.942 |
| experience | 0.835 | 0.89 |
| opinion | 0.829 | 0.829 |
| avoid | 0.974 | 0.974 |
| timeframe | 0.968 | 0.968 |
| trend | 0.982 | 0.982 |
| status | 0.969 | 0.969 |
| price | 0.981 | 0.981 |
| dishes | 0.58 | 0.623 |

## Rule questions (95)

- R0006: The rules don't say whether two branches of one place compared in one comment are one mention or one per branch (Haiku split Milano Market into UWS and UES entries).
- R0016: Whether questions to OP about their visit ('did you have to book far ahead? what did it cost?') under a single-restaurant post count as referring to that place is not decided.
- R0030: When a commenter says 'Avoid X' only because X doesn't fit the asker's stated preference (all raw seafood for someone who wants cooked meat), the rules don't say whether opinion is stated with no level or whether the skip sets overall.
- R0034: A jab like 'They don't deserve the cleavage' (the place isn't worth dressing up for) sits between a joke with no verdict and an insult; the rules don't say which.
- R0104: When a list answering a negative question is followed by 'I've always had great experiences here', it is unclear whether 'here' covers the whole list or only the next-named place.
- R0109: An asker who hasn't been saying a place 'seems to be the leader' among the thread's recs could be read as a secondhand pick or as an untried plan; the rules don't say which.
- R0123: Whether 'Also ...' extending the parent's knock counts as agreement with that verdict (rule 8) is not decided.
- R0171: A packaged brand that also runs a pop-up (named in the parent) is not decided: brand, or a counted pop-up when the comment only praises the product?
- R0180: Whether 'I live near Levain and it breaks my heart to see visitors hitting up Crumbl' is a comparison with Levain as winner, or only a knock on Crumbl, is not decided by rule 5.
- R0195: An unnamed food hall pinned down only as 'that food hall' where a named place has a stall: should it be a mention named by description, and must it be kept apart from the stall's own name?
- R0242: A place that moved ("Jing Fong's old location") named under a 'places you miss' title: the rules treat one branch closing as no verdict, but don't say whether a relocated restaurant's old address is a branch or a fond verdict tied to the old address.
- R0267: A hearsay verdict on a chain known only abroad ('I've heard Dishoom is bland') before its NYC branch opens: the rules give secondhand verdicts and also say the NYC one gets only what is said about it, without saying which wins.
- R0277: A pick answering a non-food question ('best restaurant merch?' -> 'Katz's has sweet hats'): the rules make any answer a pick, but don't say whether praise of merchandise is a verdict on the place.
- R0307: 'No way A gets 10/10, and B and C get 9s' can mean all three are overrated or that B and C deserve more than A; the rules don't say which.
- R0308: Whether timeframe should be past for a mention that is only about a closed branch is not stated (status says null, timeframe is silent).
- R0314: Whether picks answering 'best restaurants that you can actually get into' take wait praise from the framing when the reply says 'my faves' (not a bare answer) is not spelled out.
- R0331: Whether 'their prices have continued to rise', said among complaints, is a value knock or only a price fact is not decided by the rules.
- R0333: Whether a defense of a dish's price that concedes 'it's a bit ridiculous' should set overall through the lone value knock is not clearly decided.
- R0336: When a question names two criteria (cozy and easy to book), whether a near-bare answer takes both aspects is not spelled out.
- R0344: Whether an unscoped 'X is the best' counts as the city-wide superlative is not stated.
- R0355: 'Skip X since you're going near Y, which makes the same buns better' says 'skip' but is a swap; the rules don't say which wins for avoid.
- R0366: Whether a reply that offers only an alternative ('Midos is the only option') under a post knocking B makes B a mention is not clearly decided when B is not named or pronoun-referenced.
- R0373: Whether a steakhouse's filet mignon counts as 'the dish is what it sells' for lifting overall to superlative is not spelled out.
- R0385: 'Overrated, maybe an 8/10' pits a knock word against a praise score; the rules don't say whether the score sets taste while 'overrated' sets overall.
- R0394: Whether 'I really miss X' alone (no closed-places title) is the closed-place fond verdict of rule 7 is not decided.
- R0401: Whether a hedged '/s' on a tourist-chain pick ('not sure if /s is needed') makes it opinion none or flips it to a knock is not decided.
- R0412: Whether a joke about a wait the post reports ('faster to take the Jitney to Sag Harbor. Yikes.') is an untried reaction or a wait knock is not decided.
- R0418: A reply that refers to a context place only by pronoun with no verdict ('like so many vegans before them') sits between 'refers to it as they' and 'a reply that neither names nor judges a place is not a mention'.
- R0427: When a cart's likely name contains 'Best' ('Best Halal food truck'), whether it counts as a superlative is not decided.
- R0450: Whether a reply defending one's own earlier pick with only a fact ('they wanted old school, so it is that') is a fresh endorse or opinion none is not decided.
- R0458: Whether 'NY food scene is so much better than this' from someone who shows no visit counts as a jab at the food (rule 10) or an untried reaction (rule 3) is not decided.
- R0460: When the question asks about two dishes ('French dip or roast beef'), which dish a bare pick takes is not decided.
- R0463: Whether a free extra served with a dish ('the additional milk is so fun') is service, taste or only a dish level is not decided.
- R0464: A vendor based outside NYC that sells at NYC fairs and a seasonal Bryant Park stall: the rules don't say whether it counts as an NYC place.
- R0465: A pick answering 'easiest to get a reservation?' whose own words say you must book when slots drop: the framing (wait praise) and the alarm rule (wait knock) collide.
- R0468: Whether 'seems fairly reasonable' about prices read off a linked menu is a value verdict or a menu-only reaction (rule 3) is not decided.
- R0471: When the commenter's own praise is old and the current decline is only heard from another user, rule 9 (levels are what they think now) and timeframe past pull in different directions.
- R0489: A commenter (the OP) restating their own post's complaint: whether a passing 'recipe changed for a dip I'd enjoyed' re-sets the dish knock is not decided.
- R0505: When the comment reports the last remaining branch closing ('that's also closed'), the rules don't say whether that is a branch closing (status null) or the whole place (closed).
- R0509: A pronoun reference ('their') makes a mention, but a reply that neither names nor judges is not one; the rules don't say which wins for a no-verdict joke that refers by pronoun.
- R0520: A comment made only of a quote (possibly the commenter quoting their own words, here praising Semma) has no rule saying whether the quoted verdicts count.
- R0528: Whether avoid can be true for a boycott told to readers ('I would steer clear on principle') when rule 10 makes the mention opinion none.
- R0532: Rule 6 says a place offered as an answer is a pick; it doesn't say whether an answer to an identification question ('which bakery is this from?') is a pick or a fact.
- R0541: A superlative the commenter half-retracts in the same breath ('best in the city (actually I'm gatekeeping, my fave is elsewhere)') isn't covered by the takeback rule, which only names retracted names.
- R0543: Whether 'abomination' counts as an extreme word like 'disgusting' for extreme_knock is not listed.
- R0549: Rule 5 makes 'go to A instead' answering 'is B worth it?' a knock on B but a swap for fit ('same food, more casual') no level; this comment is both, and the fit reading was taken.
- R0556: Rule 6 doesn't say whether a side preference in the post ('somewhere quiet') counts as the question asking about that aspect.
- R0558: Whether an unscoped 'best spot' in an NYC thread counts as a city-wide superlative is not stated.
- R0561: 'I miss the old X and their prices' about a place still open isn't covered: whether it is a past-tied verdict or only a price fact.
- R0568: Whether an annual street festival (Feast of San Gennaro) counts as a night market/food hall mention or as a venue/event is not stated.
- R0571: A chain with no NYC branch (CiCi's) can't be told from the text alone; the rules don't say whether to extract it.
- R0574: Whether a 'best time to go' tip under a complaint about lines is a wait knock (plan around it) or just a tip note isn't stated.
- R0575: When a chain closed everywhere and one location returns ('risen from the ashes'), the rules don't say whether that is the place reopening or a branch opening.
- R0578: Whether 'X is the only reason I go' is lone-exception praise (taste knock) like 'only good for X' is not settled.
- R0601: Whether a cuisine/format heading like "sushi -" set beside "omakase -" counts as a dish heading (dish praise) or only a tag.
- R0623: Whether a superlative scoped by price tier ("the king of under \$100") counts as city-wide superlative_praise.
- R0671: Whether a criterion in the post body ("looking for somewhere quiet") counts as the question asking about atmosphere, so bare picks take atmosphere praise as walk-in picks take wait praise.
- R0673: In a "NY region" thread, whether a place the text does not locate (possibly NJ, compared with an Edison NJ place) should be extracted or skipped.
- R0681: When regret at a whole place closing comes with a mild knock on its food ("never the biggest fan of their food, but sad to see them go"), whether overall is the rule-7 fond praise or a knock.
- R0732: Whether 'I agree with your takes on everything you had' adopts only the OP's dish verdicts or also the OP's wait, price, room and staff complaints.
- R0738: Where a bar with live music ('the groove (live music venue)', 'Terra blues (blues club)') falls between bar-with-music and venue is not decided.
- R0776: Whether a broad 'head to Woodside, plenty of Filipino food there' list under 'Best tocino?' still takes the tocino dish for each pick.
- R0794: Whether an unscoped 'Best X' ('Best Burger', 'the best fried chicken') counts as a city-wide superlative or only as praise.
- R0804: Whether a comment that is only a place's website URL counts as naming the place is not decided by the rules.
- R0845: Whether a nameless timing tip that answers a post about one specific place's line refers to that place, and whether such a tip sets a wait knock, is not spelled out.
- R0847: When an untried commenter restates the parent's verdict as their own conclusion ('execution is not there right now'), the rules don't say whether that is rule 3's untried reaction or a secondhand verdict.
- R0864: When the compared loser is an out-of-NYC branch (San Jose Din Tai Fung), the rules don't say whether the NYC winner still takes the comparison's level.
- R0925: Whether a question asking for pizza places like Sally's counts as asking about the dish pizza (rule 6), giving each pick dish pizza and taste praise.
- R0988: Whether an unscoped 'the best X' (no 'in the city' or 'ever') counts as a city-wide superlative for superlative_praise.
- R0998: When the question asks for two dishes ('French dip or roast beef'), whether a bare answer takes either dish under rule 6.
- R1007: Does a requirement inside a broader request ('and I need to be able to get a table Saturday') make bare picks wait praise under rule 6, or only a question mainly about the wait?
- R1022: Is a 'best time to go' tip under a complaint about lines a wait knock (planning around it) or a tip with no level?
- R1030: Does a chain named only to make a rhetorical point in an argument (McDonald's 'pink slime' nuggets) count as a mention with a knock?
- R1036: Jazz clubs like Birdland and Iridium serve food and drink but are named for music: venue (not counted) or bar?
- R1045: Is a place named only inside a URL ('This place. yelp.com/biz/financier-patisserie') a mention?
- R1081: Is 'at opening you get a table right away or in 45-90 minutes' a wait knock (plan around it) or praise relative to the post's 5-hour wait?
- R1083: When the loser of a dish comparison is called good overall ('it really is'), does its losing dish still take a knock?
- R1103: Whether 'the pizza is definitely not worth the wait' is a bottom-line knock on overall or a wait-only remark the rules keep out of overall.
- R1121: Two bare numbers after names under a 'related to?' question: the rules don't say whether to read them as years or scores.
- R1132: Whether 'skip the overrated tourist clusterF at X and go to Y' is a swap (avoid false) or a tourist-trap skip (avoid true).
- R1149: How far 'I agree with your takes on everything you had' carries a post's verdicts: dishes only, or also the post's wait and price complaints.
- R1174: Whether 'a long way to go for a BEC' is a not-worth-the-trip knock or a fit note about distance.
- R1177: Whether sarcastic mockery of a knock ('Brave and courageous stance!' under 'Overrated AF') implies the opposite verdict or none.
- R1180: Whether a price verdict read off a posted menu ('seems fairly reasonable') counts as an untried menu reaction or a stated value verdict.
- R1194: 'Overrated - maybe an 8/10': the rules make 8/10 praise and 'overrated' a knock, and don't say which wins.
- R1223: Two branches of one place compared in the same comment: one mention or one per branch is not decided by the rules.
- R1226: Praise of a brewery for hosting pop-ups (a business practice toward vendors): service level or no verdict is not decided.
- R1239: Whether an unscoped 'the best' (no 'in the city' or 'ever') counts as a city-wide superlative is not decided.
- R1254: An Asian market named as the best spot to buy durian fruit to eat: grocery (uncounted) or a counted food kind is not clearly decided.
- R1260: Praise for a restaurant's merchandise (hats) answering a merch question: verdict on the place or a note only is not decided.
- R1271: A national chain with no NYC branch, named without a place: the rules don't say whether to extract it.
- R1286: When the last remaining NYC branch closes ('that's also closed'), whether that is a branch closing or the whole place closing is not decided.
- R1290: 'X is the only option' under a post knocking Y: whether Y is a mention with an overall knock (a swap) is not clearly decided.
- R1300: Whether a '+1'/'seconding' inherits the parent's unscoped superlative ('the best Turkish food') or stays at endorse praise.
- R1302: Whether a boycott told to readers ('steer clear on principle') sets avoid true when rule 10 makes it opinion none.
