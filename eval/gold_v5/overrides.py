"""Hand decisions for the v5 gold, applied on top of the mechanical conversion.

convert_gold_v5.py first maps every v1/v2 gold mention to the v5 schema with
fixed rules (see its docstring). This file holds every place where reading the
comment again gave a different answer than those rules. Each entry names the
comment and the mention (by canonical_name), says why, and lists only the v5
fields it sets. The blind v1/v2 labels stay untouched, so every change can be
audited against them.

Fields an entry may set:
    reference_only, is_negated, price, experience, judgment_question,
    neighborhood_hint, descriptors (replaces), dishes_liked / dishes_disliked /
    dishes_mentioned (each replaces), and any aspect by name (food=..., wait=...).
    alts={aspect: [labels or None]} replaces those aspect_alternatives entries.
    uncertain=[...] adds fields to uncertain_fields (not scored).
    add_desc=[...], drop_desc=[...] edit descriptors without replacing them.
    ambiguous=True/False changes the mention's ambiguous flag.
    conv={id: {field: value without it}} tags a convention decided by hand.
    no_c3=True keeps convention 3 from touching experience.
    food=None on a mention with dish verdicts lets c1 take food from them.

A name that repeats within one comment is keyed "name#n" (n counts from 0 in
mention order), as convert_gold_v5.mention_keys builds it.

Every food +1, every all-null mention and every dish without a verdict was
re-read; an entry exists only where the default was wrong. Entries are grouped
by the review class that surfaced them.
"""

OVERRIDES = []


def O(comment_id, name, why, **fields):
    OVERRIDES.append(dict(comment_id=comment_id, name=name, why=why, fields=fields))


# ---------------------------------------------------------------------------
# food +1 review. Default: a +1 with nothing else scored is a bare
# endorsement (food null, experience unclear). Entries keep "decent" where
# the +1 was a real mild judgment, or reclassify the mention.
# ---------------------------------------------------------------------------

O("t1_o306hvo", "Shmoné Wine Bar", "'same dishes from the restaurant next door with a star' is a mild food claim", food="decent", alts={"food": [None]})
O("t1_nhlarx7", "Num Pang", "'damn I really miss num pang' is fondness, a mild positive", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_ohvuhag", "Portale", "answers what to order with dishes: bare endorsement of the place, but naming dishes to order implies they ate there", experience="ate_there", uncertain=["experience"])
O("t1_olehg3u", "The Modern", "answers a factual question (who sells gift cards) inside a request for places to go: endorsement or reference", uncertain=["reference_only"])
O("t1_olehg3u", "Per Se", "same as The Modern", uncertain=["reference_only"])
O("t1_orfx26n", "S&P", "'Marked, looks so nice': a mild positive from someone who has not been", food="decent", alts={"food": [None]})
O("t1_nr4ka8q", "John's of Bleecker Street", "picks John's in the comparison: a mild positive", food="decent", alts={"food": ["good", None]})
O("t1_nqjinf6", "Rollin Bagels", "'That's a good one' judges the cart", food="decent", alts={"food": ["good"]}, experience="unclear")
O("t1_nkagudu", "Cafe Pri", "'I like Cafe Pri' is a mild positive", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_obdge1y", "Hi-Collar", "relays what other comments suggested, as an example of a focused place: reference or endorsement", reference_only=True, uncertain=["reference_only"])
O("t1_obdge1y", "Konbon", "same as Hi-Collar", reference_only=True, uncertain=["reference_only"])
O("t1_obdge1y", "Ichiban Tei", "same as Hi-Collar", reference_only=True, uncertain=["reference_only"])
O("t1_m5nm6jq", "Denny's", "'they're consistent' defends Denny's against the parent: a mild positive, not an answer to the thread's question", food="decent", alts={"food": ["good", None]})
O("t1_ol6radh", "Lucali", "wins the comparison against Sam's: a mild positive from someone who has had both", food="decent", alts={"food": ["good", None]}, experience="ate_there", uncertain=["experience"])
O("t1_p02lovg", "Rosa's Pizza", "a regular for the eggplant parm slices: a mild positive", food="decent", alts={"food": [None, "good"]}, experience="ate_there")
O("t1_o72a7gw", "Hi-Collar", "'Get the ...' with four dishes implies they have eaten there", experience="ate_there", uncertain=["experience"])
O("t1_p2d1ocg", "Daily Provisions", "'just a solid place for a quick bite'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_o9nxtrs", "P.J. Clarke's", "'worth it from Long Beach, not from Montauk' is a mild, qualified positive", food="decent", alts={"food": ["mixed", None]}, experience="ate_there", uncertain=["experience"])
O("t1_nopix7b", "Biryani Cart", "'solid and also do a pretty tasty kati roll selection'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_nwow1zf", "2 Bros Pizza", "'2bros dollar slice is still pretty decent'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_o8stpy7", "Devoción", "'even chains like devocion are just better' is a mild positive", food="decent", alts={"food": ["good"]})
O("t1_ojiehi2", "Best Bagel & Coffee", "'hold up well in the freezer!' judges the bagels on the property asked about", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_ocpsj0b", "Eataly", "answers the question with a hedge ('pretty sure they have it'); 'haven't been for a min' is a past visit, not hearsay", experience="unclear", uncertain=["reference_only"])
O("t1_ogg7wk0", "Suited", "'Runners up' under 'Best coffee' is praise by placement", food="decent", alts={"food": ["good", None]})
O("t1_ogg7wk0", "Simpl", "same as Suited", food="decent", alts={"food": ["good", None]})
O("t1_ou6dg5t", "Saigon Shack", "'looks great thanks!' from someone who has not been: a mild positive", food="decent", alts={"food": [None, "good"]})
O("t1_p1kjgvj", "Gramercy Tavern", "'The additional milk at Gramercy is so fun' judges the experience", food="decent", alts={"food": ["good", None]}, experience="ate_there")
O("t1_p8sl8rh", "Beer Street South", "answers a business question (bars that host pop-ups), not where to eat: a reference", reference_only=True, uncertain=["reference_only"])
O("t1_o4x8du3", "Biriyani Bol", "'I was skeptical, but it looks tasty' from a non-visitor", food="decent", alts={"food": [None, "good"]})
O("t1_ohmk0kd", "Magnolia Bakery", "'Magnolia's banana pudding still great though' defends the place through one dish", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_opqrd0l", "Radio Bakery", "says what they ordered and what they'll try next, with no judgment of either", reference_only=True, experience="ate_there", uncertain=["reference_only"])
O("t1_o744v4c", "Felo Deli", "'that sounds amazing' about the parent's rec, secondhand", food="decent", alts={"food": ["good", None]})
O("t1_p86dbyw", "Milano Market", "'a solid 7-8/10 - an ol' reliable'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_o7x674w", "Librae", "'deserves an honorable mention' is a mild positive", food="decent", alts={"food": [None, "good"]})
O("t1_ofoiqcv", "Los Burritos Juárez", "awesome as a local spot, underwhelming as a hyped one: explicitly weighed", food="decent", alts={"food": ["mixed", "good"]}, experience="ate_there")
O("t1_oce5l5t", "Mia's Bakery", "answer plus what they saw at the Brooklyn location", experience="ate_there")
O("t1_omzxv6c", "The Palm", "'I remember it being very good' (years ago): a mild positive they still hold", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_ozwvgmy", "Le Bernardin", "'Glad to see the LB love' sides with the praise", food="decent", alts={"food": [None, "good"]})
O("t1_nk7lo0e", "Avra", "bare answer; 'I've been there once' shows a visit", experience="ate_there")
O("t1_ohbnvvg", "Zaytinya", "'Zaytina is a solid option as well'", food="decent", alts={"food": ["good"]})
O("t1_ongtrb0", "Kabawa", "agrees every menu item sounds good: a mild positive, likely from the parent who listed dishes", food="decent", alts={"food": ["good", None]}, experience="ate_there", uncertain=["experience"])
O("t1_noallnr", "Elea", "'I have not been, but heard Elea on the UWS is great': secondhand praise", food="decent", alts={"food": ["good"]})
O("t1_oorklyc", "Manu's Dabeli Station", "'Looks tasty' from a non-visitor; 'how spicy is that?' asks, so 'spicy' is not a descriptor", food="decent", alts={"food": [None]}, drop_desc=["spicy"])
O("t1_paqzw96", "Lucy's", "'they should make this combo its own named menu item' is praise", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_owkutga", "Pressed Juicery", "'I care more about their vegan soft serve': a mild positive through one item", food="decent", alts={"food": [None]}, experience="ate_there")
O("t1_owl1bu4", "Pressed Juicery", "'I enjoyed Pressed for a healthy on-the-go option'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_owl7op2", "Pressed Juicery", "'RIP to their vegan soft serve!' mourns an item they liked", food="decent", alts={"food": [None, "good"]}, experience="ate_there")
O("t1_owlw11x", "Pressed Juicery", "'I enjoy the taste of their freezes'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_owmaom5", "McDonald's", "'McNuggets with their honey is bomb. Its far from chicken though'", food="decent", alts={"food": ["good", "mixed"]}, experience="ate_there")
O("t1_oxj6xbh", "Pressed Juicery", "'I loved their ginger shots :('", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_o3l05q2", "Noona's Ice Cream", "'Wow it looks so good! Will definitely try!!' from a non-visitor", food="decent", alts={"food": ["good"]})
O("t1_o3l27ui", "Noona's Ice Cream", "'passionfruit ice cream sounds FIRE' from a non-visitor", food="decent", alts={"food": ["good"]})
O("t1_o3l32yp", "Noona's Ice Cream", "'looks so yummy!' from a non-visitor, then a price question", food="decent", alts={"food": [None]})
O("t1_o3l7buy", "Noona's Ice Cream", "'that lotus flavor looks incredible' from a non-visitor", food="decent", alts={"food": ["good"]})
O("t1_o3m9fu3", "Noona's Ice Cream", "'looks delicious' with a question", food="decent", alts={"food": [None]})
O("t1_o3nc7xi", "Noona's Ice Cream", "'the flavors she makes truly showcase her Korean heritage' is mild praise from a friend of the founder", food="decent", alts={"food": ["good", None]})
O("t1_orndi7d", "Liebman's Deli", "'Otherwise I go to Liebmans': a bare answer from a regular", experience="ate_there")
O("t1_ornj05g", "Mason Pickle", "'I have enjoyed the pickle cake'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_p64o0fe", "Mama's Too", "'I like both for different reasons'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_p64o0fe", "L'Industrie Pizzeria", "same as Mama's Too", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_p65ak1y", "Mama's Too", "'this looks so good. I've never been'", food="decent", alts={"food": ["good"]})
O("t1_p65fvfr", "Mama's Too", "'not even a hot take at this point' agrees it is a favorite", food="decent", alts={"food": ["good"]})
O("t1_p65qu6a", "Pizza Hut", "'still decent enough'", food="decent", alts={"food": [None]})
O("t1_p65u95m", "Mama's Too", "'Their sandwiches > their slices' judges between items; the slices only lose the comparison", food="decent", alts={"food": [None]}, dishes_liked=["sandwiches"], dishes_mentioned=["slices"], experience="ate_there")
O("t1_p66vnfc", "Mama's Too", "'You need to try their elote slice': a recommendation that implies they had it", experience="ate_there", uncertain=["experience"])
O("t1_p67gw25", "Mama's Too", "'Both of these pizzas look delicious' from a non-visitor", food="decent", alts={"food": ["good"]})
O("t1_p67vvqn", "Mama's Too", "'dyingg to try their August elote slice': eager, but the dish is untried, so it is named rather than liked", food="decent", alts={"food": [None]}, dishes_liked=[], dishes_mentioned=["elote slice"])
O("t1_p69yfzg", "Mama's Too", "'oh i love that one!' (the pear slice)", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_p6puvov", "Mama's Too", "'Mamas too is pretty good, but ...'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_p6vw2ux", "Mama's Too", "'It's good' before naming a place they like better", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_o255ayj", "Sweetgreen", "'I like sweet greens because I can see the calories'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_o255q7c", "Lenwich", "'Veggie sandwiches from lenwich are filling' judges the property asked for", food="decent", alts={"food": [None]}, experience="ate_there")
O("t1_o25bxps", "Le Botaniste", "'Omg this looks so good. Def gonna order' from a non-visitor", food="decent", alts={"food": ["good"]})
O("t1_o25j5zj", "Pret A Manger", "'I also actually like Pret's falafel salad bowl!'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_p2w5997", "Eleven Madison Park", "'bucket list place for sure' from a non-visitor", food="decent", alts={"food": ["good", None]})
O("t1_p2xigq9", "Eleven Madison Park", "'Lovely!' then booking questions, from a non-visitor", food="decent", alts={"food": [None]})
O("t1_p2xkakg", "Eleven Madison Park", "'the best that EMP has looked to me in a hot minute' judges from the photos", food="decent", alts={"food": ["good"]})
O("t1_p2ys5to", "Eleven Madison Park", "'Looks amaze' with a price question", food="decent", alts={"food": ["good", None]})
O("t1_p30rnwb", "Eleven Madison Park", "'it was good but definitely left something to be desired'", food="decent", alts={"food": ["mixed"]}, experience="ate_there")
O("t1_p31jzrz", "Eleven Madison Park", "'This looked beautiful!' from someone who never goes to places like it", food="decent", alts={"food": [None]})
O("t1_p32za1o", "Eleven Madison Park", "the old menu lacked; this one shows inventiveness and they would go back: a mild positive now", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_omja0eq", "Sofreh", "'Rosewater ice cream was really fun.'", food="decent", alts={"food": ["good", None]}, experience="ate_there")
O("t1_ozwbi85", "Red Gate Bakery", "'I've been happy with everything I had there'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_obj6a5w", "Red Hook Tavern", "worth the wait? 'Debatable but yes'", food="decent", alts={"food": ["mixed"]})
O("t1_obkq0rr", "Red Hook Tavern", "lunch menu facts plus a dish verdict; no judgment of the place itself", experience="ate_there")
O("t1_olcu2zd", "Utopia Bagels", "'I also enjoy the egg salad with bacon'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_olcuujb", "Utopia Bagels", "'Imma go to Utopia today, i suddenly have a craving': a mild positive", food="decent", alts={"food": [None]})
O("t1_ooomg70", "Indonesian bazaar at Masjid al-Hikmah", "'definitely worthwhile even if you don't find your specific dish'", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_ow8iwda", "Joe's Pizza", "'an institution and def worth a visit but avoid the times sq location'", food="decent", alts={"food": ["good"]})
O("t1_onfmvcv", "Black Seed Bagels", "'I'm fond of Black Seed'", food="decent", alts={"food": ["good"]})
O("t1_onfmvcv", "Kossar's Bagels & Bialys", "'Kossar's is the OG' is an evaluative descriptor, a mild positive", food="decent", alts={"food": [None, "good"]}, add_desc=["the OG"])
O("t1_onfmvcv", "Tompkins Square Bagels", "'lots of people swear by Tompkins' reports others' praise", food="decent", alts={"food": [None, "good"]}, experience="secondhand")
O("t1_odz9pr0", "Gray's Papaya", "'Love Grays but it's way out of your way': praised, so losing the hot dog comparison does not make it meh", food="decent", alts={"food": ["good"]})
O("t1_ozm1y4a", "WatchHouse", "listed under 'If you want to try good 3rd wave coffee, head to'", food="decent", alts={"food": ["good"]})
O("t1_ozm1y4a", "Little Collins", "same header", food="decent", alts={"food": ["good"]})
O("t1_ozm1y4a", "Current Coffee", "same header", food="decent", alts={"food": ["good"]})
O("t1_ozm1y4a", "Devoción", "same header", food="decent", alts={"food": ["good"]})
O("t1_ozm1y4a", "Dae Day", "same header", food="decent", alts={"food": ["good"]})
O("t1_pa086iq", "Maison Premiere", "'Ive never been here but ... was really impressed' by the variety at an interview", food="decent", alts={"food": [None]})
O("t1_pa086iq", "Grand Central Oyster Bar", "'like 10 years ago and thought it was really cool'", food="decent", alts={"food": [None]})
O("t1_ok6its6", "Chez Fifi", "'the top rated Chez Fifi' reports a rating; a bare recommendation", add_desc=["top rated"])
O("t1_ok6its6", "Marcel", "'try the brand new Marcel': a bare recommendation", add_desc=["brand new"])
O("t1_o1xbybo", "Golden Swan", "'I liked golden swan'", food="decent", alts={"food": ["good"]})
O("t1_nmzla94", "Lucia Pizza", "'have good slices'", food="decent", alts={"food": ["good"]})
O("t1_nmzla94", "Prince Street Pizza", "same", food="decent", alts={"food": ["good"]})
O("t1_nmzla94", "La Esquina", "'The taco stand above la esquina is good'", food="decent", alts={"food": ["good"]})
O("t1_nmzla94", "Dominique Ansel", "the comment judges only dishes and they disagree (skip the cronut line, the cookie is awesome)", food="mixed", alts={"food": ["good", "decent"]}, conv={"c1": {"food": None}})
O("t1_p7vut7z", "Red Hook Tavern", "judges only the burger: 'fine. Great even.'; praised, so losing to better burgers is not meh", conv={"c1": {"food": None}})
O("t1_laijt60", "Dallas BBQ", "'those wings make a trip worth it' is a verdict on going, despite the bad brisket", food="decent", alts={"food": ["good", "mixed"]})
O("t1_nqdzwed", "Parm", "'great for kids. It's not too shabby for adults either.'", food="decent", alts={"food": ["good"]})
O("t1_jrqd79z", "Parm", "'basically live at Parm' against returned undercooked meatballs: explicitly weighed", food="mixed", alts={"food": ["decent", "meh"]})
O("t1_ou5l7y7", "Deli Board", "judges only the bread: 'Dutch crunch is pretty soft fwiw', a mild positive", food="decent", alts={"food": [None]}, conv={"c1": {"food": None}})

# c1 follow-ups to entries above: these comments judge only dishes, so food
# takes the dishes' level (later entries for the same mention merge over
# earlier ones).
O("t1_ohmk0kd", "Magnolia Bakery", "c1: only the banana pudding is judged ('still great')", food="good", alts={"food": ["decent"]}, conv={"c1": {"food": None}})
O("t1_ornj05g", "Mason Pickle", "c1: only the pickle cake is judged ('enjoyed')", conv={"c1": {"food": None}})
O("t1_p1kjgvj", "Gramercy Tavern", "c1: only the extra milk with the cookie is judged ('so fun')", food="good", alts={"food": ["decent", None]}, conv={"c1": {"food": None}})
O("t1_o25j5zj", "Pret A Manger", "c1: only the falafel salad bowl is judged", conv={"c1": {"food": None}})
O("t1_paqzw96", "Lucy's", "c1: only the combo is judged", food="good", alts={"food": ["decent"]}, conv={"c1": {"food": None}})
O("t1_owkutga", "Pressed Juicery", "c1: only the vegan soft serve is judged", conv={"c1": {"food": None}})
O("t1_owl7op2", "Pressed Juicery", "c1: only the vegan soft serve is judged", conv={"c1": {"food": None}})
O("t1_owlw11x", "Pressed Juicery", "c1: only the freezes are judged", conv={"c1": {"food": None}})
O("t1_oxj6xbh", "Pressed Juicery", "c1: only the ginger shots are judged ('loved')", food="good", alts={"food": ["decent"]}, conv={"c1": {"food": None}})
O("t1_owmaom5", "McDonald's", "c1: only the McNuggets are judged ('bomb')", food="good", alts={"food": ["decent", "mixed"]}, conv={"c1": {"food": None}})
O("t1_p02lovg", "Rosa's Pizza", "c1: only the eggplant parm slices are judged, by being a regular for them", conv={"c1": {"food": None}})
O("t1_olcu2zd", "Utopia Bagels", "c1: only the egg salad is judged", conv={"c1": {"food": None}})
O("t1_omja0eq", "Sofreh", "c1: only the rosewater ice cream is judged", conv={"c1": {"food": None}})
O("t1_p65u95m", "Mama's Too", "c1: only the sandwiches vs slices are judged", conv={"c1": {"food": None}})
O("t1_p69yfzg", "Mama's Too", "c1: only the pear slice is judged ('oh i love that one!')", food="good", alts={"food": ["decent"]}, conv={"c1": {"food": None}})
O("t1_nwow1zf", "2 Bros Pizza", "c1: only the dollar slice is judged", conv={"c1": {"food": None}})
O("t1_o255q7c", "Lenwich", "c1: only the veggie sandwiches are judged", conv={"c1": {"food": None}})
O("t1_o3l27ui", "Noona's Ice Cream", "c1: only the passionfruit flavor is judged", conv={"c1": {"food": None}})
O("t1_o3l7buy", "Noona's Ice Cream", "c1: only the lotus flavor is judged", conv={"c1": {"food": None}})
O("t1_omzxv6c", "The Palm", "c1: only the parm is judged ('very good')", food="good", alts={"food": ["decent"]}, conv={"c1": {"food": None}})
O("t1_nktelej", "One More Thai", "'my go tos' from someone who used to work there", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_nktelej", "Lava Shawarma", "same", food="decent", alts={"food": ["good"]}, experience="ate_there")
O("t1_lak5pcf", "Pelicana Chicken", "'pelicana fried chicken on third floor is good', an exception inside a complaint", food="decent", alts={"food": ["good"]})
O("t1_opr5fyf", "Davelle", "'Another good one is Davelle'", food="decent", alts={"food": ["good"]})
O("t1_nwffz4v", "Manhatta", "'it's not that bad. I've had some pretty mid Michelin before' defends it mildly", food="decent", alts={"food": ["mixed", None]})
O("t1_p6tebe7", "Radio Bakery", "c1: only dishes are judged and they disagree: the focaccia 'really makes it special', the croissant 'was just ok' (ok is meh)", food="mixed", alts={"food": ["good", "decent"]}, dishes_liked=["tomato feta mint focaccia sandwich"], dishes_disliked=["tomato croissant"], dishes_mentioned=[], conv={"c1": {"food": None}})
O("t1_onna4nk", "Noodle Village", "'great at what they do great' is a verdict on the place, qualified by naming what to order", food="good", alts={"food": ["decent", "mixed"]})
O("t1_p05qskq", "Grand Street Pizza", "'very good most of the time, I have got a dud slice there once or twice'", food="good", alts={"food": ["decent", "mixed"]})
O("t1_p05qskq", "Cello's Pizzeria", "'Cellos is good'", food="decent", alts={"food": ["good"]})
O("t1_p82pm1d", "Pick A Bagel", "'Also like Pick A Bagel'", food="decent", alts={"food": ["good"]})
O("t1_onliuvm", "Court Street Bagels", "'The rest are pretty good.'", food="decent", alts={"food": ["good"]})
O("t1_onliuvm", "Smith Street Bagels", "same", food="decent", alts={"food": ["good"]})
O("t1_njicv92", "Village Square Pizza", "held up as better than the place with the line next door", food="decent", alts={"food": ["good"]})
O("t1_oyz8k9n", "Chama Mama", "'I like Chama Mama and have recommended it... but it is very much not one of the best 38'", food="decent", alts={"food": ["good", "mixed"]})
O("t1_pb1y8yh", "Golden Bull handmade noodles", "a terrible sandwich, but 'the noodles are good enough to make my regular rotation' is a verdict on going back", food="good", alts={"food": ["mixed", "decent"]})
O("t1_pb1y8yh", "Xing Fu Tang", "'welcome additions... definitely the best in the area'", food="decent", alts={"food": ["good"]})
O("t1_pb1y8yh", "Joju", "'both fine and I'd go again': fine is meh, softened by going again", food="meh", alts={"food": ["mixed"]})
O("t1_pb1y8yh", "MalaTang", "same as Joju", food="meh", alts={"food": ["mixed"]})
O("t1_nivanw4", "Santa", "enjoyed the platters at the carts in front of Trader Joe's", food="decent", alts={"food": ["good"]})
O("t1_nivanw4", "Farook", "same as Santa", food="decent", alts={"food": ["good"]})
O("t1_nl13u2v", "Asian Jewels Seafood", "'Asian jewels is good, but kinda pricey'", food="decent", alts={"food": ["good"]})
O("t1_np1rzga", "Hale and Hearty", "'my go-to for a quick inexpensive lunch... I missed it greatly'", food="decent", alts={"food": ["good"]})
O("t1_oc8074c", "Spicy Moon", "eats there 'quite often': a mild positive by habit", food="decent", alts={"food": [None]})
O("t1_o06sgso", "Denino's", "'I like Dennino's and it's big and isn't a tourist place.'", food="decent", alts={"food": ["good"]})
O("t1_nx5jd1n", "BCD Tofu House", "'bCD tofu house is fun'", food="decent", alts={"food": [None]})
O("t1_o4pc0ku", "Wheated", "'just care about making good food'", food="decent", alts={"food": ["good"]})

# ---------------------------------------------------------------------------
# all-null review. Default: a mention with nothing scored is reference_only.
# Entries turn comparison losers into meh (convention 5), drop descriptors
# that were only asked about (rule 4), and null prices that came only from a
# dollar figure (convention 7).
# ---------------------------------------------------------------------------
O("t1_oo83agu", "Double Chicken Please", "asks which drinks to order: 'drinks' is asked, not stated", drop_desc=["drinks"])
O("t1_p27rra0", "Atera", "c7: the price is only a dollar figure ($707 for two)", price=None, alts={"price": None})
O("t1_nuwfkcx", "Junoon", "c5: 'Indian Accent is miles better than Junoon' - loses the comparison, not praised", reference_only=False, food="meh", alts={"food": [None]}, uncertain=["reference_only"])
O("t1_paar0f1", "Mekelburg's", "closed; 'i was there weekly' shows visits", experience="ate_there")
O("t1_nzycbn4", "15 East", "closed; a former regular", experience="ate_there")
O("t1_nzycbn4", "Jewel Bako", "closed; 'I started going to Jewel Bako'", experience="ate_there")
O("t1_ofr3erg", "Kam Rai", "'I had the massaman at Kam Rai, it was the worst to you??' implies it was fine for them", experience="ate_there", alts={"food": ["decent"]})
O("t1_o20dcxe", "King's Kitchen", "'I had it as a special promotion'", experience="ate_there")
O("t1_nt7oq88", "Lin's Garden", "closed; 'Our favorite spot forever' shows visits", experience="ate_there")
O("t1_oo1wae7", "Sammy's Halal", "'Back in the days it was Sammy's': a past favorite, so a reference now", experience="ate_there")
O("t1_nkagudu", "Patok by Rach", "'have only tried their food as popup vendors'", experience="ate_there")
O("t1_nyp7285", "Mama's Too", "'Just avoid all these spots tomorrow': a crowd warning about the 184-person crawl, so the negative is the wait, not the food", wait="bad", experience="unclear", no_c3=True)
O("t1_nyp7285", "Faicco's Italian Specialties", "same crowd warning", wait="bad", experience="unclear", no_c3=True)
O("t1_nyp7285", "Porto Rico Importing", "same crowd warning", wait="bad", experience="unclear", no_c3=True)
O("t1_nyp7285", "Rocco's Pastry Shop", "same crowd warning", wait="bad", experience="unclear", no_c3=True)
O("t1_paceu0a", "Los Tacos No. 1", "c7: '$6 tacos' is only a dollar figure", price=None, alts={"price": None})
O("t1_ogcr192", "Rowdy Rooster", "closed; recalls the sandwiches from when it opened", experience="ate_there")
O("t1_nqeiorr", "Carbone", "c5: dropped for 'the obvious choice instead of Carbone', by someone who has not been", reference_only=False, food="meh", alts={"food": [None]}, uncertain=["reference_only"])
O("t1_ntamyvd", "Pakistan Tea House", "closed; 'kept me happily & cheaply fed multiple times a week for years'", experience="ate_there")
O("t1_ntamyvd", "Christy's Jamaican Patties", "closed; 'their patties were so good' - remembered dishes are mentioned", experience="ate_there", dishes_mentioned=["patties"])
O("t1_p8t9z4m", "Tacos El Bronco", "'I've only ever had at the restaurant'", experience="ate_there")
O("t1_o88qxrt", "Soothr", "c5: 'This spot and Mitr are way better than Soothr'", reference_only=False, food="meh", alts={"food": [None]}, uncertain=["reference_only"])
O("t1_ntvaqyf", "Essen", "closed; 'used to make a good one'", experience="ate_there")
O("t1_o3l3uo7", "Noona's Ice Cream", "c7: 'around $8' is only a dollar figure", price=None, alts={"price": None})
O("t1_ox2u9mb", "Juice Press", "'I was in pretty much every morning' for the deals", experience="ate_there")
O("t1_orqe0gm", "Big Nick's", "closed; 'miss that joint'", experience="ate_there")
O("t1_oxitb7w", "Pressed Juicery", "'I just went there last week!!!'", experience="ate_there")
O("t1_p64hhwb", "L'Industrie Pizzeria", "c5: 'I liked it more than L'Industrie' - loses the comparison and is not praised", reference_only=False, food="meh", alts={"food": [None, "decent"]}, uncertain=["reference_only"])
O("t1_p33kjx9", "Per Se", "'I just went to Per Se for the first time'", experience="ate_there")
O("t1_p7lxy78", "Daniel", "went for their anniversary", experience="ate_there")
O("t1_ok6its6", "Carne Mare", "c5: loses the comparison to The Fulton and is not praised", reference_only=False, food="meh", alts={"food": [None]}, uncertain=["reference_only"])
O("t1_nuwhimj", "Fette Sau", "closing; 'never the biggest fan of their food' shows visits", experience="ate_there")
O("t1_nuyw195", "Fette Sau", "closing; 'had some of the worst ribs at this place' - closed, so aspects stay null; the ribs are remembered", experience="ate_there")
O("t1_ol8bujz", "Ceres Pizza", "c7: only dollar figures ($68, $30); 'overpriced' is asked, not stated", price=None, alts={"price": None})
O("t1_matyk0w", "Roscioli", "c7: '$348' is only a dollar figure", price=None, alts={"price": None})
O("t1_padzyzp", "Atera", "c7: '$707' is only a dollar figure", price=None, alts={"price": None})
O("t1_p4vqhgx", "Per Se", "c7: '$300' is only a dollar figure", price=None, alts={"price": None})
O("t1_nt8pi72", "'ino", "closed; 'were the best' shows visits", experience="ate_there")
O("t1_nt8pi72", "'inoteca", "closed; same", experience="ate_there")
O("t1_nx532u2", "Semilla", "closed; 'had the BEST BREAD' - the bread is remembered", experience="ate_there", dishes_mentioned=["bread"], drop_desc=["bread"])
O("t1_nt72q0q", "Rosemary's Pantry", "closed; 'an amazing chicken parm sub that I miss dearly'", experience="ate_there")
O("t1_kehkdzw", "Hop Shing", "closed; compares its char siu bao from experience", experience="ate_there")
O("t1_nt6vofp", "King Yum", "closed; 'When we went for the last time'", experience="ate_there")
O("t1_nt7m9b9", "Norma's", "closed; 'they were my favorite brunch'", experience="ate_there")
O("t1_ocj2aaa", "Village Yokocho", "closed; 'I remember ... you walked upstairs'", experience="ate_there")
O("t1_o78zhdw", "Petrossian", "closed; 'my two faves for pastries'", experience="ate_there")
O("t1_o78zhdw", "Arcade Bakery", "closed; same", experience="ate_there")
O("t1_oacgsiu", "Blockheads", "closed; 'Best bar to drink outside at'", experience="ate_there")

# ---------------------------------------------------------------------------
# dishes without a verdict. Rule 6: praise of the meal that covers named
# dishes makes them liked; the rest stay mentioned.
# ---------------------------------------------------------------------------
O("t1_omhtigm", "Sofreh", "'enjoyed it - got the dip, date salad, meatballs, rice and tahdig... can't go wrong': meal praise covering the dishes", dishes_liked=["shallot and yogurt dip", "date salad", "meatballs", "rice", "tahdig"], dishes_mentioned=[])
O("t1_ozkzz26", "Javelina", "'Javelina is the best answer' for queso praises the queso", dishes_liked=["queso"], dishes_mentioned=[])
O("t1_o3l0elu", "Noona's Ice Cream", "'my favorite is the pandan and ube with the mochi toppings'", dishes_liked=["pandan", "ube", "mochi toppings"], dishes_mentioned=[])

# ---------------------------------------------------------------------------
# c7: price only when stated in words. A bare dollar figure leaves it null.
# ---------------------------------------------------------------------------
O("t1_og6m8pu", "Salt Hank", "c7: only a dollar figure ('34 dollars')", price=None, alts={"price": None})
O("t1_nyp0jwq", "Sushi Sho", "c7: only a dollar figure ('$300-$400')", price=None, alts={"price": None})
O("t1_nx08rpe", "Spongies", "c7: only a dollar figure ('$1.50')", price=None, alts={"price": None})
O("t1_ni0888n", "Queens Night Market", "c7: only a dollar figure ('$6 or under')", price=None, alts={"price": None})
O("t1_ois3ta6", "Los Tacos No. 1", "c7: only a dollar figure ('nearing 30 bucks')", price=None, alts={"price": None})
O("t1_oqqr8vp", "Kossar's Bagels & Bialys", "c7: only a dollar figure ('$20.00')", price=None, alts={"price": None})
O("t1_oqqr8vp", "Joe & The Juice", "c7: only a dollar figure ('$12.00 smoothie')", price=None, alts={"price": None})
O("t1_p7w3ib3", "Bar Kabawa", "c7: only a dollar figure ('80 bucks')", price=None, alts={"price": None})
O("t1_ozx0nmo", "Mama's Too", "c7: only a dollar figure ('$25 for a chicken sandwich')", price=None, alts={"price": None})
O("t1_nl035ov", "Mr Biggs", "c7: only a dollar figure ('$4 Shots/$4 Beers')", price=None, alts={"price": None})
O("t1_o7qhqc2", "Sake No Hana", "c7: only a dollar figure ('the 50% increase in price' is a change, not a level)", price=None, alts={"price": None})
O("t1_o9kg4m0", "Los Tacos No. 1", "c7: only a dollar figure (only 'peeked at their menu')", price=None, alts={"price": None})
O("t1_o8mptug", "Koma", "c7: only a dollar figure ('other omakase... above 125')", price=None, alts={"price": None})
O("t1_p26hc2j", "Dirt Candy", "c7: only a dollar figure ('$150, which I thought was super reasonable'; 'too expensive' was about starred places in general)", price=None, alts={"price": None})
O("t1_ooko90w", "Sushi by M", "c7: only a dollar figure ('$100 for their 16 piece omakase')", price=None, alts={"price": None})
O("t1_nt84xmq", "Taiwan Pork Chop House", "c7: only a dollar figure ('$10')", price=None, alts={"price": None})
O("t1_nt84xmq", "E-MO", "c7: only a dollar figure ('$11')", price=None, alts={"price": None})
O("t1_ol0j9y2", "Sushi Blossom", "c7: only a dollar figure ('around $120')", price=None, alts={"price": None})
O("t1_oqtv3vz", "Heaven's Hot Bagels", "c7: only a dollar figure ('$12 for way more')", price=None, alts={"price": None})
O("t1_nxy8aoe", "Wayan", "c7: only a dollar figure ('charges $40 for a tiny plate')", price=None, alts={"price": None})
O("t1_p7swuq4", "Los Tacos No. 1", "c7: only a dollar figure ('spend 25 dollars to be full')", price=None, alts={"price": None})
O("t1_nl5kv2z", "Keens Steakhouse", "c7: only a dollar figure ('close to $400 bucks')", price=None, alts={"price": None})
O("t1_ob86ly5", "Patsy's Pizzeria", "c7: only a dollar figure ('$16 for a whole pie')", price=None, alts={"price": None})
O("t1_o72a7gw", "Little Myanmar", "c7: only a dollar figure ('under 30$ per person')", price=None, alts={"price": None})
O("t1_o3kxbbu", "Noona's Ice Cream", "c7: '$16 each?' is a dollar guess, so no price alternative", alts={"price": None})
O("t1_p7m31w0", "Los Tacos No. 1", "c7: '$8 great taco' is a dollar figure, so no price alternative", alts={"price": None})
O("t1_o72a7gw", "Trapizzino", "c7: the price alternative came from dollar figures", alts={"price": None})

# ---------------------------------------------------------------------------
# Judgment-carrying questions (rule 2, convention 4). The thread table is in
# threads.py; only one bare name in v1/v2 answers such a question.
# ---------------------------------------------------------------------------
O("t1_npw80ui", "Serafina", "'Second this. Came here to write Serafina.' answers 'poor quality yet expensive restaurant to give to an enemy': the question's judgment applies at its plain level", judgment_question=True, food="bad", value="bad", add_desc=["poor quality", "expensive"])

# ---------------------------------------------------------------------------
# c2: an avoid with no stated reason is food "bad". v1 scored several bare
# skips as -1 (meh); those move to bad, with meh still accepted.
# ---------------------------------------------------------------------------
O("t1_oxom6g5", "Lenwich", "c2: 'jeeze skip lenwich' gives no reason", food="bad", alts={"food": ["meh"]}, conv={"c2": {"food": "meh"}})
O("t1_ngokxjl", "Peter Luger", "c2: 'Forget about Luger.' gives no reason", food="bad", alts={"food": ["meh"]}, conv={"c2": {"food": "meh"}})
O("t1_nxp7fd1", "Petit Chou", "c2: 'I'd easily skip Petit Chou and Hanis' gives no reason", food="bad", alts={"food": ["meh"]}, conv={"c2": {"food": "meh"}})
O("t1_nxp7fd1", "Hani's Bakery", "c2: same", food="bad", alts={"food": ["meh"]}, conv={"c2": {"food": "meh"}})

# experience corrections found in the secondhand sweep
O("t1_ocmker2", "Balthazar", "'the first truly nice restaurant I took my husband to, twenty something years ago' is a visit", experience="ate_there")
O("t1_o9kg4m0", "Los Tacos No. 1", "'I haven't been in a while' means they have been", experience="ate_there")

# "ok / fine / alright" are meh, never mixed or decent (contract).
O("t1_on3wlkb", "Caffe Panna", "'I think Cafe Panna is fine' - fine is meh", food="meh", alts={"food": ["mixed"]})
O("t1_onliuvm", "Bergen Bagels", "'Bergen bagels is alright' - alright is ok, which is meh", food="meh", alts={"food": ["mixed"]})

# ---------------------------------------------------------------------------
# c4 (provisional): bare 'not worth it' as advice is an avoid; 'not worth the
# price / the line / the hype' names what fails and is not an avoid. The
# tag records the opposite is_negated reading.
# ---------------------------------------------------------------------------
O("t1_no81lir", "Chef's Table at Brooklyn Fare", "c4: 'Def not worth it' as advice is an avoid", conv={"c4": {"is_negated": False}})
O("t1_ocd2pxq", "4 Charles Prime Rib", "c4: 'It's not worth all that, I promise' as advice is an avoid", conv={"c4": {"is_negated": False}})
O("t1_ob4i1hy", "Tomi Jazz", "c4: 'totally not worth it' as advice is an avoid", conv={"c4": {"is_negated": False}})
O("t1_p4ai0t6", "Bench Flour Bakers", "c4: 'are not worth it' as advice is an avoid", conv={"c4": {"is_negated": False}})
O("t1_p4ai0t6", "Little Flower Cafe", "c4: same", conv={"c4": {"is_negated": False}})
O("t1_opczj0l", "The Corner Store", "c4: 'not worth the long line + reservation hassle' names what is not worth it: the wait, not an avoid", is_negated=False, wait="bad", alts={"wait": ["meh"]}, conv={"c4": {"is_negated": True, "wait": "meh"}})
O("t1_orndi7d", "Jacob's Pickles", "c4: 'not worth the time or money' is value bad, not an avoid", is_negated=False, value="bad", alts={"value": ["meh"]}, conv={"c4": {"is_negated": True, "value": "meh"}})
O("t1_og6m8pu", "Salt Hank", "c4: 'not worth 34 dollars' is value bad, not an avoid", conv={"c4": {"is_negated": True}})
O("t1_ois3ta6", "Los Tacos No. 1", "c4: 'nearing 30 bucks ... very not worth it' is value bad, not an avoid", conv={"c4": {"is_negated": True}})
O("t1_o11xk4e", "Levain Bakery", "c4: 'Not worth the wait' is wait bad, not an avoid", conv={"c4": {"is_negated": True}})
O("t1_nopix7b", "Adel's Famous Halal Food", "c4: 'not worth waiting an hour+' is wait bad, not an avoid", conv={"c4": {"is_negated": True}})
O("t1_olqwkwe", "Katz's Delicatessen", "c4: 'just not worth it to me' is their own verdict, not advice, so not an avoid", conv={"c4": {"is_negated": True}})
O("t1_nxolwat", "Katz's Delicatessen", "c4: 'probably not worth the line' is wait bad, not an avoid", conv={"c4": {"is_negated": True}})
O("t1_onwkswn", "L'Industrie Pizzeria", "c4: 'definitely not worth the wait' is wait bad, not an avoid", conv={"c4": {"is_negated": True}})
O("t1_nr4xixk", "John's of Bleecker Street", "c4: 'not worth waiting a long time' is the wait, not an avoid", conv={"c4": {"is_negated": True}})
O("t1_nr4xixk", "L'Industrie Pizzeria", "c4: same", conv={"c4": {"is_negated": True}})
O("t1_notfai2", "Lilia", "c4: 'not worth how hard it is to go' is the wait, not an avoid", conv={"c4": {"is_negated": True}})
O("t1_o2c0eer", "Scarr's Pizza", "c4: 'not worth it if you have to wait in line' is conditional on the wait, not an avoid", conv={"c4": {"is_negated": True}})
O("t1_ok57sgz", "Adel's Famous Halal Food", "c4: 'isnt worth the line' is wait bad, not an avoid", conv={"c4": {"is_negated": True}})
O("t1_pc1wgff", "Dig Inn", "c4: 'never worth the dig' (the money) is value bad, not an avoid", conv={"c4": {"is_negated": True}})

# ---------------------------------------------------------------------------
# Old food +1 with a dish verdict is not a bare endorsement. Where the
# comment judges only dishes, v1's +1 is dropped and c1 takes food from the
# dishes' own level. Where it gives an overall verdict, an entry above keeps
# the food label and c1 does not fire.
# ---------------------------------------------------------------------------
O("t1_ohvuhag", "Portale", "c1: names only dishes to order", food=None)
O("t1_nt99vmo", "Cannelle Patisserie", "c1: names only the chocolate mousse cake", food=None)
O("t1_o72a7gw", "Hi-Collar", "c1: 'Get the Siphon Pour Over, Fluffy Pancakes, Omurice and a Sando' judges only dishes", food=None)
O("t1_oa1tbql", "Brennan & Carr", "c1: 'They'll douse it in cheese' is about the burger only", food=None)
O("t1_nw1301j", "Russ & Daughters", "c1: listed for its bagel and lox only", food=None)
O("t1_owwu0q6", "Great NY Noodletown", "c1: 'for soft shell crab' only", food=None)
O("t1_owwu0q6", "Noodle Village", "c1: 'for soup dumplings and curry oxtail' only", food=None)
O("t1_owwu0q6", "Banh Mi Saigon", "c1: 'for the #1 special' only", food=None)
O("t1_owwu0q6", "Bánh Mì Cô Út", "c1: 'for the more traditional sandwich' only", food=None)
O("t1_p1j5f2c", "El Malecon", "c1: 'Get extra green sauce' only", food=None)
O("t1_p66vnfc", "Mama's Too", "c1: 'You need to try their elote slice' only", food=None)
O("t1_o25705p", "Le Botaniste", "c1: suggested for its warm bowl only", food=None)
O("t1_ozujedh", "Faicco's Italian Specialties", "c1: 'try faiccos for a chicken cutlet sando' only", food=None)
O("t1_obkq0rr", "Red Hook Tavern", "c1: judges only the smoked pork chop ('arguably the best dish')", food=None)
O("t1_olcktdv", "Utopia Bagels", "c1: names only its country chicken salad", food=None)
O("t1_nxp7fd1", "From Lucie", "c1: 'get a cake from From Lucie' only", food=None)
O("t1_oq8ykks", "Szechuan Mountain House", "c1: suggested for the twice cooked pork only", food=None)
O("t1_oq8ykks", "Spy C Cuisine", "c1: suggested for the farmhouse style pork only", food=None)
O("t1_oq8ykks", "886", "c1: suggested for the fly's head only", food=None)
O("t1_m5ovv4r", "Raising Cane's", "c1: judges only the tenders ('bland but the texture... bomb')", food=None)
O("t1_ntgkxkl", "Russ & Daughters", "c1: judges only the bagels ('very meh')", food=None)
O("t1_o65rrko", "Bungalow", "c1: judges only dishes, and they disagree (biryani underwhelming, lamb amazing)", food=None)
O("t1_oofppn4", "Hill Country", "c1: judges only dishes, and they disagree (brisket very good, sides terrible)", food=None)
O("t1_oanwd0s", "Hunter's Steak and Ale", "c1: judges only the burger (a favorite memory)", food=None)
O("t1_o251gud", "Sweetgreen", "an avoid for a political reason, not quality: tagged so it can be flipped on its own", conv={"c2_nonquality": {"food": None}})
O("t1_o255q7c", "Sweetgreen", "same: avoided for the partnership", conv={"c2_nonquality": {"food": None}})
O("t1_o81a1qc", "Chef's Table at Brooklyn Fare", "avoided because it is all seafood, a reason about the asker's diet", conv={"c2_nonquality": {"food": None}})
# @@END@@
