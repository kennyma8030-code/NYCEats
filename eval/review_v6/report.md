# Opus review of Haiku round 3

Items judged: 600 (real round-3 output on 542; the rest were planted checks).

- Haiku items fully right: 0.517
- Mention recall / precision (judge's final view): 0.938 / 0.959
- Negative mentions caught: {'final_negative_mentions': 172, 'haiku_caught': 148, 'recall': 0.86}
- Planted errors caught: 0.862 {"drop_dish": {"caught": 5, "n": 5, "rate": 1.0}, "drop_mention": {"caught": 15, "n": 15, "rate": 1.0}, "flip_overall": {"caught": 9, "n": 9, "rate": 1.0}, "r1_substitute": {"caught": 6, "n": 10, "rate": 0.6}, "upgrade_negative": {"caught": 3, "n": 4, "rate": 0.75}, "wrong_experience": {"caught": 12, "n": 15, "rate": 0.8}}
- Judge first read overturned by its own re-read: 0.194 (resolution {'judge': 639, 'haiku': 162, 'neither': 32})

## Haiku field accuracy (against final values)

| field | accuracy | n |
|---|---:|---:|
| aspects.atmosphere | 0.98 | 590 |
| aspects.service | 0.976 | 590 |
| aspects.taste | 0.912 | 590 |
| aspects.value | 0.976 | 590 |
| aspects.wait | 0.981 | 590 |
| avoid | 0.985 | 590 |
| dishes | 0.779 | 263 |
| experience | 0.864 | 590 |
| opinion | 0.903 | 590 |
| overall | 0.805 | 590 |
| price | 0.988 | 590 |
| status | 0.985 | 590 |
| timeframe | 0.971 | 590 |
| trend | 0.983 | 590 |

## Judge first-read accuracy

| field | accuracy | n |
|---|---:|---:|
| aspects.atmosphere | 0.995 | 623 |
| aspects.service | 1.0 | 623 |
| aspects.taste | 0.965 | 623 |
| aspects.value | 0.997 | 623 |
| aspects.wait | 0.992 | 623 |
| avoid | 1.0 | 623 |
| experience | 0.973 | 623 |
| opinion | 0.968 | 623 |
| overall | 0.971 | 623 |

## Notes, tags, location

{"location:missing": 6, "location:ok": 595, "location:wrong": 8, "notes:missing": 49, "notes:ok": 537, "notes:wrong": 23, "tags:missing": 3, "tags:ok": 579, "tags:wrong": 27}

## Rule questions (111)

- Q0004: Does a not-yet-tried 'looks so nice' (an impression from photos) count as a stated positive or as opinion none?
- Q0007: Same as the S&P case: an untried 'looks so good, gonna order' reply; should it be none or an endorse?
- Q0008: A comment attacking the chef (David Chang) personally, under a Momofuku thread, without naming or judging the restaurant: I treated it as no mention; should a knock on the owner count against the place?
- Q0009: When a bare list answers 'easiest places to walk in', should the post's framing set wait positive on each endorsement, or do endorsements keep all aspects null?
- Q0020: When the only remark is a wait complaint put as a fact ('line started at 4:15'), should overall stay null or follow the strongest point to negative?
- Q0025: Untried-place impressions ('looks tasty', 'looks so good') recur often; the rubric should say whether they are stated levels or opinion none.
- Q0031: Zabar's (a grocery store with a famous deli counter) praised for its deli pickles: grocery store excluded, or a deli mention?
- Q0043: A chain used as a rhetorical jab in an argument (McDonald's 'pink slime' nuggets): should it count as a judged mention, and is 'pink slime' extreme enough for very_negative?
- Q0048: Supermarkets praised for prepared food (Pomegranate's chicken salad, Zabar's pickles): exclude as grocery stores even when the comment gives no hint that they are stores?
- Q0059: 'That is what I was afraid of' under a 'too spicy' complaint about an untried place: an agreement reply (stated, negative) or a worry/question (none)?
- Q0071: When the place is named only in an ancestor Haiku did not see, should the missed object still be listed (as here), given Haiku could not have named it?
- Q0078: Is a packaged-food brand (Grillo's Pickles) that runs a one-off NYC pop-up a mention, or a product like a grocery item?
- Q0081: When the commenter is evidently the asker reacting to recommendations ('seem like the obvious choice ... Thanks'), should their picks be firsthand by default or none as not-yet-tried?
- Q0083: Is 'not the best or worst price' a neutral value verdict or lukewarm (negative) like 'fine'?
- Q0084: Are multi-vendor food markets such as Queens Night Market or Smorgasburg mentions, or venues like the rubric's non-places?
- Q0087: Is a joking gatekeeping reply ('you be quiet now', 'don't tell anyone') under a recommendation an endorsement of the recommended place?
- Q0091: When a place is named only to identify a person ('the Una Pizza Napoletana guy'), is it a name-in-passing mention or part of a person reference?
- Q0096: When a commenter's past firsthand praise is overridden by someone else's report of decline, is the current verdict firsthand or secondhand?
- Q0098: Should a bare list answer to a dish question ('best chicken salad sandwich?') carry that dish as a dish entry, and at what level?
- Q0101: Should a chain's announced-but-not-yet-open new branch set status 'opened', or stay null with a note?
- Q0107: Which aspect takes a complaint about format or menu structure (prix-fixe only, no a la carte): service as 'how the place is run', or overall?
- Q0113: Is 'terrible' / 'awful experience' very_negative or negative under the owner's extremes-only calibration?
- Q0114: Is enthusiasm about an untried new place ('so cool, can't wait to try') a stated positive opinion or opinion none?
- Q0115: Pig and Khao is closed according to a reply the model could not see; the missed object records status closed, but should a list recommendation of a since-closed place be scored as positive in the past?
- Q0118: When a commenter's only visit was years ago but they endorse current criticism, is the timeframe current or past?
- Q0120: Is a plain list of names given as examples of a trend (answering 'which places do you mean?') endorse like a list item under a recommendation request, or opinion none?
- Q0123: Is a suitability caveat ('not somewhere I'd take a young kid') a complaint that lowers atmosphere, or a neutral fit note?
- Q0124: Does a prediction that a place will get worse (e.g. after a private-equity deal) count as a current negative verdict?
- Q0127: Is hyperbole without a comparison ('to die for', 'unreal') positive, or very_positive like 'god tier' and 'life-changing'?
- Q0129: Is a sentimental-occasion anecdote ('a friend proposed there, it'll never close. Sweet.') a positive verdict on the place or opinion none?
- Q0131: Is 'the closest substitute, but not the same' a negative (comparison loser) verdict, or mild praise?
- Q0132: When the only judgment is a wait aspect ('free tables at 4', 'never had a problem walking in'), should overall follow it or stay null as a tip?
- Q0135: Is a restaurant group (Unapologetic Foods) a mention when criticized, or a company outside the place list?
- Q0140: Should a boycott over a company's politics (not food or service) lower overall at all, given rankings are about the food place?
- Q0143: Does trend cover a change in a single aspect such as booking difficulty, or only the overall verdict?
- Q0149: Is 'that sounds amazing' about an untried place secondhand (based on the parent's report) or experience none (not yet tried)?
- Q0153: Should a verdict from a visit years ago ('I used to work a few blocks away') be timeframe past when the comment gives no sign the place changed?
- Q0156: Should an unnamed place the commenter can't recall ('that place on Christopher St around the corner') be a mention when no name appears anywhere in the context?
- Q0178: When the only judgment is about one aspect (here the wait), should overall follow it as the strongest point or stay null? Haiku leaves it null; I followed 'strongest point'.
- Q0179: Is a reply that only excuses a place's flaw ('it's a small business, one person doing everything') a judgment of the place, or a fact with opinion none?
- Q0184: Should a closed place with no verdict at all still get timeframe past, as rule 10 says, when there are no levels for it to describe?
- Q0188: When a place loses a comparison about its food ('X is better'), should the loser's taste be set, or only overall?
- Q0200: Is 'looks amazing' about photos of a place the commenter has not tried a stated positive verdict, or opinion none?
- Q0214: Is 'best on the UES' (a neighborhood-limited superlative) broad enough for very_positive?
- Q0218: Is a mild lament like 'too bad it closed' enough for a positive verdict, or only an explicit 'I miss it'?
- Q0223: When the only judgment is on one aspect (value here, wait in Q0209), should overall follow it or stay null? Judges so far have done both.
- Q0224: Does a reply saying 'I did' file a health complaint about the post's place count as a negative verdict on it, when the commenter may not be the poster?
- Q0232: Whether a reply that answers the post's question about a named place only with a general rule (no name, no judgment) counts as an opinion-none mention of that place.
- Q0238: Whether an unnamed reply that implicitly ranks the post's place below an unnamed alternative counts as a comparison loser (negative) or as no mention.
- Q0242: Whether a ranked list of recommendations ('A, B, C, D in that order') makes the lower-ranked picks comparison losers (negative) or keeps them all as endorsements.
- Q0243: Whether music/comedy clubs that serve drinks (The Groove, Terra Blues, Comedy Cellar) are bars (mentions) or venues (not places).
- Q0249: Whether a bookable room or counter inside a restaurant (the Modern's Kitchen Table) is its own mention or part of the restaurant's mention.
- Q0251: When one location of a still-open chain closes, whether the chain mention gets status closed / timeframe past.
- Q0267: Whether 'do your worst' framing on an enemy-recommendation thread makes a seconded pick very_negative or only negative.
- Q0268: Whether food poisoning should also set taste (the food) very_negative, or only overall.
- Q0272: Whether Zabar's (a gourmet food store that sells bagels and has a cafe) counts as a place or as an excluded store.
- Q0281: Whether a booking tip like 'book at the specific time slots open' is wait negative (like 'be there by 11:30') when it answers 'easiest to get a reservation'.
- Q0283: Whether 'barely any seating' / 'no seating' is wait (getting a table) or atmosphere (the room).
- Q0284: Whether 'replace X with Y' tells others to avoid X (avoid true) or is only a comparison loss.
- Q0286: Whether a reaction to a post photo ('real mood') counts as a mention of the place the photo most likely shows.
- Q0288: Whether a comparison loser on bookability alone ('Carbone picks you') gets overall negative or only wait negative.
- Q0294: Whether an insincere superlative walked back in favor of an unnamed favorite makes the place a negative comparison loser or leaves overall null.
- Q0295: Whether 'temporarily closed' should set status closed or stay null, since status has no temporary value.
- Q0297: Whether a chain's visibly declining business (empty stores, closures) counts as trend declined when quality isn't mentioned.
- Q0299: Whether a bare 'RIP X' is a fond (positive) verdict like 'I miss it' or only a closure fact.
- Q0304: Does a 'go to A instead' suggestion motivated by fit (casualness for a tween) rather than quality count as a comparison that makes B negative?
- Q0307: When a post announces one location of a chain is closing and the comment is about another location, should status be closed?
- Q0309: 'avoid the Times Sq location' of a chain otherwise called worth a visit: avoid stays false for the place?
- Q0309: 'You've basically listed the standard tourist spots' knocks the post's list collectively without naming them; are those places mentions?
- Q0334: A remembered favorite that moved and changed its offering ('now they only sell caviar. So lame'): rule 9 current negative, or rule 10 remembered verdict with timeframe past?
- Q0354: Jazz clubs that serve food and drink (Birdland, Iridium) are called 'venues' in the comment; are they bars (mentions) or venues (excluded)?
- Q0358: Is 'one of the best meals we've had lately' a broad superlative (very_positive) or does 'lately' make it positive?
- Q0367: Does a bare pick answering 'where did you have the best X?' inherit the superlative (very_positive) from the question's framing, or stay an endorsement?
- Q0370: A list posted under 'terrible restaurants with great reviews' followed by 'I've always had great experiences here': does thread framing make the list negative, or does the explicit praise win?
- Q0374: Are 'terrible' and 'awful' extremes (very_negative) or strong plain knocks (negative) under the owner's calibration?
- Q0385: Whether enthusiasm about a dish the commenter has not yet tried ('sounds FIRE') counts as stated or endorse is not decided by the rubric.
- Q0392: Whether a wait complaint from someone who has not yet been, with no other verdict, should set overall negative or leave it null is not decided by the rubric.
- Q0400: Zabar's is a gourmet grocery store that sells bagels; the rubric excludes grocery stores, but it is discussed here as a bagel source, so whether it counts is unclear.
- Q0404: When one branch of a chain closes, the rubric does not say whether status should be closed on the chain mention or left null.
- Q0405: When the praised place is only 'this place' and the comment that named it is deleted, the rubric does not say whether to keep an unnamed mention or drop it.
- Q0416: Zabar's is a grocery store with an attached cafe; when the cafe is what is meant, the rubric's grocery-store exclusion is unclear.
- Q0420: 'Great at what they do great' plus 'a ton of things that are pretty mid', applied to Chinatown spots in general, reads as hit-or-miss (neutral), but the rubric does not say whether a generalization should count against the named place.
- Q0425: An unnamed, unidentifiable place ('a place on rivington') with a strong complaint: the rubric does not say whether it is a mention.
- Q0427: Whether a pedantic category objection ('it's not a slice') counts as a complaint about the place or is opinion-free.
- Q0438: How to treat praise for an untried place based on a photo ('looks so good, never been'): stated with experience none, or endorse.
- Q0442: Whether a sexual-innuendo joke replying to a price complaint ('if I'm going to lick a chalupa I'm not paying for it') is a value judgment or opinion-free.
- Q0444: Whether reporting a place to the Health Department over kitchen hygiene is an extreme (very_negative) verdict without extreme words, and whether hygiene belongs under service.
- Q0445: Whether 'terrible' alone counts as an extreme (very_negative) or a plain negative; the calibration list does not name it.
- Q0453: When a commenter says they like a place very much but it is not worth the money, is not worth it a bottom line (negative) or a balanced verdict (neutral)?
- Q0457: Does a nostalgic joke reply under a recommendation (memories, or lack thereof) count as an endorsement or as opinion none?
- Q0460: When a bare recommendation names a dish as the answer (the X at Y), is the dish level positive like get the X, or null as only named?
- Q0461: When vendors are listed as examples of Smorgasburg alumni that Redditors can enjoy, is that an endorsement or a name in passing?
- Q0462: Is it not that bad used to defend a place against a knock still lukewarm and negative, or does the defensive framing make it positive?
- Q0468: Do gourmet food stores with deli counters, like Zabar, count as delis (mentions) or as grocery stores (not places)?
- Q0469: Should a general money complaint about a whole category (100 dollars for a steak is wacky) lower value for the specific places the commenter just named in that category?
- Q0475: When one location of a still-open chain closes, should the mention carry status closed, or only a note that a location closed?
- Q0476: When the comparison winner is framed as a low bar (even Chipotle is better), is the winner positive by default, neutral, or negative?
- Q0482: Are health-code violations and shutdowns a service complaint (how the place is run) or an overall-only complaint?
- Q0488: Is a chain named only as a supermarket product brand (frozen Arbys curly fries) a mention of the chain?
- Q0491: Is a food court or food hall (Food Gallery 32, Smorgasburg) a mention in its own right, or only its stalls?
- Q0500: Is a ping-pong bar like Spin a bar (mention) or a venue (not a place)?
- Q0506: Does a superlative about one dish (serves the best baked ziti) make the place overall very_positive?
- Q0513: Does clarifying another commenter complaint (they meant the partnership, here is the link) count as a secondhand negative opinion or as a fact?
- Q0515: Gourmet Garage, Citarella and Jefferson Market are gourmet grocers with prepared food; are they grocery stores (not places) or delis?
- Q0540: Is a former go-to offered as a current recommendation ('used to work here and my go tos were X') timeframe past or current?
- Q0541: When an agreement reply ('Get Out Of My Head!') mostly agrees with the parent's analogy rather than its restaurant verdict, does rule 8 still carry the parent's verdict on the place?
- Q0550: When a terse reply ('Damn if it aint delicious though') could point at the parent's place or the post's place, should the extractor prefer the post's subject?
- Q0556: Is 'terrible' with nothing else extreme enough for very_negative, or negative under the strict calibration?
- Q0565: Does hyperbole like 'should be burned to the ground' count as telling others to avoid the place?
- Q0587: When a comment says it would rather go to B for 'less the headache' than A, should the unspecified headache count as wait?
- Q0589: Is a best-time-to-go tip given in reply to 'those lines are brutal' wait negative (like 'be there by 11:30') or opinion none?
