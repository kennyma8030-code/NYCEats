# Judge agreement: a second review of 150 fresh comments (round 4, medium)

Items compared: 150 of 150 judged in the second review.

## 1. Field agreement (final values, A against B)

| field | agree | n | rate |
|---|---:|---:|---:|
| _mention | 115 | 118 | 0.975 |
| aspects.atmosphere | 114 | 115 | 0.991 |
| aspects.service | 115 | 115 | 1.0 |
| aspects.taste | 111 | 115 | 0.965 |
| aspects.value | 115 | 115 | 1.0 |
| aspects.wait | 113 | 115 | 0.983 |
| avoid | 115 | 115 | 1.0 |
| dishes | 56 | 59 | 0.949 |
| experience | 111 | 111 | 1.0 |
| opinion | 114 | 115 | 0.991 |
| overall | 109 | 111 | 0.982 |
| price | 114 | 115 | 0.991 |
| status | 114 | 115 | 0.991 |
| timeframe | 115 | 115 | 1.0 |
| trend | 115 | 115 | 1.0 |

## 2. Item verdict (overall_item_ok)

Agree on 128 of 137 unplanted items (0.934); A called 120 fully right, B 117.

## 3. Haiku's accuracy under each review (the error bar)

| metric | under A | under B | B − A |
|---|---:|---:|---:|
| item_ok_rate | 0.876 | 0.854 | -0.022 |
| mention_recall | 0.966 | 0.966 | 0.0 |
| mention_precision | 0.974 | 0.966 | -0.008 |
| negative_recall | 0.882 | 0.833 | -0.049 |
| overall | 0.936 | 0.926 | -0.01 |
| aspects.taste | 0.912 | 0.893 | -0.019 |
| dishes | 0.804 | 0.833 | 0.029 |
| experience | 0.954 | 0.963 | 0.009 |
| opinion | 0.947 | 0.946 | -0.001 |

## 4. Planted changes caught by B: 1.0 {"drop_dish": {"caught": 1, "n": 1}, "drop_mention": {"caught": 3, "n": 3}, "flip_overall": {"caught": 1, "n": 1}, "upgrade_negative": {"caught": 2, "n": 2}, "wrong_experience": {"caught": 2, "n": 2}}

## 5. Disagreements by cause

### levels: other (3)

- S071 / R0955 **Kabisera** `aspects.taste`: A null, B "positive". Title: 'Best Filipino spots in the city - Go!'. Comment: "Was impressed by this little shop too, a super underrated spot to work/hang as well"
  - A: 'impressed by this little shop too' judges the shop, not the parent's desserts specifically; no '+1'-style adoption of the food claim; B: 'impressed ... too' agrees with the parent's dessert praise (rule 8)
- S129 / R1270 **Le'Baratin** `aspects.atmosphere`: A null, B "positive". Title: 'Cute West Village restaurants'. Comment: "Le’Baratin is great"
  - A: (agreed with Haiku); B: a pick answering 'cozy/cute restaurants' takes the atmosphere the question asks about
- S005 / R1241 **ovelia** `aspects.taste`: A "positive", B null. Title: 'What ethnic foods can we agree that NY is a top 3 city for?'. Comment: "for super traditional greek - bahari estiatorio has just as good of food as kyclades for better prices but half the crowds!! for greek with a few twists - ovelia is great but honestly, I think it'd be hard for a bad greek restaurant to survive long in astoria, there's too much competition."
  - A: 'for greek with a few twists, ovelia is great' judges its food style; B: 'ovelia is great' judges the place; taste is never copied from overall

### dish naming and dish levels (3)

- S094 / R0332 **Sisters** `dish:veggie burger`: A {"level": "negative", "avoid": false}, B null. Title: 'Veggie burgers'. Comment: "Sisters is just okay to me tbh. Like. It’s fine ..?"
  - A: 'just okay' replies to the parent's praise of Sisters' lentil veggie burger, the dish the thread asks about; B: the comment names no dish; the knock on the food sits in taste
- S008 / R1253 **Raku** `dish:Kani Maze`: A {"level": "neutral", "avoid": false}, B {"level": "negative", "avoid": false}. Title: 'Raku reservation ?'. Comment: "My friend had the kaisen don that iirc is only at the HK location. I had the Kani Maze which was good but i just didn't enjoy it as much as id hoped. I did enjoy the pork gyoza. Have a great dinner!"
  - A: (agreed with Haiku); B: 'good but didn't enjoy it as much as I'd hoped': the disappointment is the bottom line (rule 4)
- S097 / R1248 **terroir** `dish:wine list`: A {"level": "positive", "avoid": false}, B null. Title: 'My procrastinating ass can’t find a bar to accommodate 15 for Saturday'. Comment: "Try terroir since youre already in tribeca. I see plenty of large reservations on resy (and you can definitely flex to fit more given their setup). Incredible wine list and a great vibe"
  - A: 'Incredible wine list' is a drink verdict; every drink named goes in dishes; B: a wine list is the selection, not a dish or drink; the praise sits in taste

### wait and overall (2)

- S026 / R1305 **Lucali** `aspects.wait`: A null, B "negative". Title: 'Lucali wait'. Comment: "Thanks man! It was awesome, showed up at like 4:10, got a pickup time for 5:45 and it was incredible, went to luigis in the mean time and sadly luigis did not live up to the hype. Lucali the best I’ve had in NY, new haven is still incredible it’s almost impossible to say which is better 😂"
  - A: (agreed with Haiku); B: showed up at 4:10 for a 5:45 pickup slot: a long wait they planned around
- S129 / R1270 **Le'Baratin** `aspects.wait`: A null, B "positive". Title: 'Cute West Village restaurants'. Comment: "Le’Baratin is great"
  - A: (agreed with Haiku); B: the question asks for places not impossible to book, so the pick takes wait praise, as in the walk-ins example

### it/they references and context places (2)

- S105 / R1254 **Pata Market** `_mention`: A "present", B null. Title: 'What’s the strangest food you have ever tried in NYC?'. Comment: "Best spot unless you order the pricey stuff from Miami Fruit is at Pata Market in Elmhurst. They also have some durian snacks"
  - A: named as the best spot for durian to eat, plus durian snacks: a food place, missing (dropped or kinded grocery); B: (agreed with Haiku)
- S024 / R1223 **Milano Market UES** `_mention`: A "present", B null. Title: 'Chicken caesar wrap from Milano Market UWS (left) vs. UES (right)'. Comment: "UWS for the win with the drenched -in-dressing look but UES has better -looking chicken imo"
  - A: two branches compared; I merged them, a mention per branch is fine; B: same place as the UWS entry; a place named twice is one mention

### mixed versus a bottom line (2)

- S008 / R1253 **Raku** `overall`: A "positive", B "neutral". Title: 'Raku reservation ?'. Comment: "My friend had the kaisen don that iirc is only at the HK location. I had the Kani Maze which was good but i just didn't enjoy it as much as id hoped. I did enjoy the pork gyoza. Have a great dinner!"
  - A: (agreed with Haiku); B: no bottom line; strongest point is the mixed food verdict
- S008 / R1253 **Raku** `aspects.taste`: A "positive", B "neutral". Title: 'Raku reservation ?'. Comment: "My friend had the kaisen don that iirc is only at the HK location. I had the Kani Maze which was good but i just didn't enjoy it as much as id hoped. I did enjoy the pork gyoza. Have a great dinner!"
  - A: (agreed with Haiku); B: one dish knocked, one praised: taste mixed

### superlatives: is 'the best' city-wide? (2)

- S133 / R1301 **Halal food truck on E 225th St (White Plains Rd), Bronx** `overall`: A "positive", B "very_positive". Title: 'What’s your favorite “hole in the wall” that you swear is deserves more hype?'. Comment: "Best Halal food truck is right outside on E 225th st Bronx, white plains road. I‘ve been going to that truck religiously for over 7 years"
  - A: 'Best Halal food truck' has no city-wide scope (and 'Best Halal' is also a truck name); praise; B: 'Best Halal food truck', unqualified, ranks the truck against all others
- S133 / R1301 **Halal food truck on E 225th St (White Plains Rd), Bronx** `aspects.taste`: A null, B "very_positive". Title: 'What’s your favorite “hole in the wall” that you swear is deserves more hype?'. Comment: "Best Halal food truck is right outside on E 225th st Bronx, white plains road. I‘ve been going to that truck religiously for over 7 years"
  - A: the praise is of the truck as a place; no food verdict; B: a halal truck's ranking is a ranking of its food, so taste is set, at the superlative level

### time, trend and closure (1)

- S038 / R0869 **Chito Grvito** `status`: A null, B "opened". Title: 'i\'ve been to NYC multiple times now and have tried all of the "must eats." what are local favorites?'. Comment: "Try Chito Grvito, my fave of the new Georgian spots opening up. Georgian food is so good."
  - A: (agreed with Haiku); B: 'my fave of the new Georgian spots opening up': a newly opened place

### price and value (1)

- S095 / R0644 **Mamouns** `price`: A "cheap", B null. Title: "Is Adel's Famous Halal Food really better than Halal Guys?". Comment: "For my taste and my personal opinion: Mamouns is good for Falafel but strictly the actual fried falafel is respectable. Everything else is bodega grade quality: the lettuce , tahini , tomatoes are just there as filler and the pita is just a container / vessel with no taste. Same goes for their spicy"
  - A: (agreed with Haiku); B: 'cheap eat' describes the past under-$2 price, not now

### untried reactions (1)

- S146 / R0008 **Monterey** `opinion`: A "endorse", B "stated". Title: 'Replacements for Monkey Bar for a nice, classic NYC restaurant?'. Comment: "I’ve never been, but my friend loved it - Monterey"
  - A: rule 8: a pick passed on from a friend ('my friend loved it') is secondhand endorse; B: 'my friend loved it' passes on a judging word, not just a pick, so it is stated

### whether a name counts (kind, passing names, non-places) (1)

- S001 / R0227 **Lori Jayne** `_mention`: A null, B "present". Title: 'Following on the spirited debate re: food influencers, what are some smaller publications/sources you trust to learn about nyc food/restaurant news (i.e., NOT infatuation, grub street, eater, etc.)?'. Comment: "I found out about Lori Jayne from Rob Martinez and I'll always love him for that, he"s awesome"
  - A: (agreed with Haiku); B: a named NYC restaurant the commenter loves having found; Haiku dropped it

