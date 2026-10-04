"""Batch 1: c0001-c0050. Relabeled 2026-10-04 under the owner's rules (label v2)."""
from common import M

LABELED_AT = "2026-10-04"
L = {}
L["c0001"] = ([M("Beets Cafe", named_in="parent", food=1, conf="low", amb=True, alt={"food": [None]},
                 terms=["haitian food"],
                 why="'Haitian food is seriously underrated' praises the cuisine; readable as seconding the parent's Beets Cafe rec, or cuisine-only")],
              "Cuisine-level remark under a named rec.")
L["c0002"] = ([], "Defends diner food in general; judges no named place.")
L["c0003"] = ([M("Shake Shack", type="chain", food=-2, value=-2, exp=1, vc=True, alt={"food": [-3], "value": [-3], "expensiveness": [2]},
                 dishes=[("cheeseburger", -2, False), ("fries", -1, False), ("milkshake", 1, False)],
                 terms=["burger", "fries", "milkshake", "vegan"],
                 why="'burger is just awful, overpriced, overhyped'; '$20 for a tiny cheeseburger... expensive for no reason' = value complaint; shakes 'not too bad'")], "")
L["c0004"] = ([M("Tony’s di Napoli", "Tony's Di Napoli", food=2, service=2, hood="Times Square",
                 alt={"food": [3], "service": [3]},
                 why="'the real deal. One of the best meals we've had lately' (+2, 'lately' hedges); 'service is top notch' +2")], "")
L["c0005"] = ([M(r, c, food=1, why="bare list answering the solo walk-in question: named as an answer")
               for r, c in [("Raouls", "Raoul's"), ("Via carota", "Via Carota"), ("Minetta tavern", "Minetta Tavern"),
                            ("Cervos", "Cervo's"), ("Penny", None), ("L Artusi", "L'Artusi"), ("Semma", None),
                            ("Torrisi", None)]], "Bare 8-name list.")
L["c0006"] = ([
    M("Via Carota", wait=1, alt={"wait": [None], "food": [1]}, terms=["walk-ins"],
      why="'they'd give a table for 4 for walk ins for early dinners' = walk-in ease; food not judged"),
    M("l’artusi", "L'Artusi", wait=1, alt={"wait": [None], "food": [1]}, terms=["walk-ins"],
      why="'same with l'artusi'"),
    M("Shmone wine bar", "Shmoné Wine Bar", type="bar", food=1, alt={"food": [None]},
      terms=["wine bar", "small plates", "walk-ins only"],
      why="suggested; 'same dishes from the restaurant next door with a star' = mild food endorsement"),
    M("Bad Roman", wait=1, first=False, alt={"wait": [None], "food": [1]}, unc=["is_firsthand"],
      why="'looks like they have an opening' = availability; not firsthand"),
], "Beli/ResX are apps; Gramercy Tavern only in the post.")
L["c0007"] = ([
    *[M(r, c, type=t, first=None, conf="medium", alt={"food": [1]}, terms=tm,
        why="named as an EXAMPLE of a common category; reference mention, no opinion")
      for r, c, t, tm in [("Xi’an", "Xi'an Famous Foods", "chain", []), ("Ippudo", None, "restaurant", []),
                          ("GAI", None, "restaurant", []), ("Mr Bao", None, "restaurant", []),
                          ("pokeworks", "Pokeworks", "chain", []), ("wagamama", "Wagamama", "chain", [])]],
    M("num pang", "Num Pang", food=1, alt={"food": [2]}, conf="medium", terms=["banh mi", "bowls"],
      why="'damn I really miss num pang now' = fond, mild positive"),
], "'any banh mi shop, kati roll places' are categories.")
L["c0008"] = ([M("DCP", "Double Chicken Please", also=("the coop at dcp", "coop"), type="bar", first=False,
                 terms=["drinks"], why="asks what to order at DCP: reference mention, no opinion")], "")
L["c0009"] = ([M("Mekelburg's", named_in="selftext", closed=True,
                 why="closed (post says so); 'i miss it so much' is remembered: closed => aspects null")], "")
L["c0010"] = ([M("Portale", named_in="title", food=1, alt={"food": [2]},
                 dishes=[("insalata", 1, False), ("pappardelle", 1, False), ("duck breast", 1, False), ("olive cake", 1, False)],
                 terms=["insalata", "pappardelle", "duck breast", "olive cake"],
                 why="answers 'what should I order at Portale' with dishes: endorsement +1")], "")
L["c0011"] = ([M("Cho Dang Gol", named_in="parent", food=3, dishes=[("kimchi biji jigae", 3, False)],
                 terms=["tofu", "kimchi biji jigae"],
                 why="'This is the answer' + 'even better than anything I've had in Korea'")], "")
L["c0012"] = ([M("shukette", "Shukette", food=3, why="'one of the best restaurants in New York'")], "")
L["c0013"] = ([], "Houston vs NYC generalization.")
L["c0014"] = ([M("Salt Hank", first=False, alt={"wait": [-1], "food": [1]}, unc=["is_firsthand"], conf="medium",
                 terms=["pickup"], why="logistics tip (GrubHub pickup skips the line); no opinion")], "")
L["c0015"] = ([M("Sam’s", "Sam's Restaurant", also=("sams",), food=1, hood="Cobble Hill", alt={"food": [None]},
                 unc=["is_firsthand"], why="'Also, Sam's in Cobble Hill just reopened' offered as a dinner suggestion")], "")
L["c0016"] = ([M("Katz", "Katz's Delicatessen", also=("katzs", "katz deli", "katzs deli"), named_in="title",
                 atmosphere=-2, alt={"atmosphere": [-1], "food": [-1]}, hood="Brooklyn", amb=True, conf="low",
                 terms=["food hall"],
                 why="'That food hall sucks' about Katz's Brooklyn outpost in the DeKalb hall; target is the hall as much as Katz's")],
              "Target ambiguous.")
L["c0017"] = ([M(r, c, also=a, food=1, why="bare list of steakhouse alternatives: named as an answer")
               for r, c, a in [("Le TetE D’Or", "Le Tête d'Or", ()), ("Salt + Charcoal", None, ()),
                               ("Dolmenicos", "Delmonico's", ()),
                               ("Porterhouse Steakhouse", "Porter House Bar and Grill", ("porterhouse",)),
                               ("Quality Italian", None, ())]], "'Dolmenicos' = Delmonico's.")
L["c0018"] = ([], "Generic ordering rule of thumb.")
L["c0019"] = ([], "Unnamed street vendor; no name.")
L["c0020"] = ([], "Chopped cheese history.")
L["c0021"] = ([M("Lovely's Old Fashioned", named_in="parent", food=2, dishes=[("burger", 2, False)], terms=["burger"],
                 why="'Great burger too' replying to the Lovely's rec")], "")
L["c0022"] = ([], "Acoustics question.")
L["c0023"] = ([M("the Grill", "The Grill", food=1, alt={"food": [2]}, terms=["eat at the bar"],
                 why="'walk to the Grill... eat at the bar' as the answer")], "Rest is a generic Midtown rant.")
L["c0024"] = ([], "Cuisine/country comparison; no named place.")
L["c0025"] = ([M("The modern", "The Modern", food=1, alt={"food": [None]}, unc=["is_firsthand"], terms=["gift cards"],
                 why="answer to which 2-3 star place sells gift cards"),
               M("per se", "Per Se", food=1, alt={"food": [None]}, unc=["is_firsthand"], terms=["gift cards"], why="same")], "")
L["c0026"] = ([M("zabars", "Zabar's", type="grocery_market", oos=True, food=1, hood="upper west",
                 terms=["smoked fish"], why="retail grocery: out of scope"),
               M("acmesmokedfish", "Acme Smoked Fish", type="grocery_market", oos=True, hood="brooklyn",
                 why="factory/wholesale fish store named via URL: retail, out of scope"),
               M("costco", "Costco", type="grocery_market", oos=True, why="retail")], "All retail.")
L["c0027"] = ([M(r, c, food=2, alt={"food": [1]}, why=w)
               for r, c, w in [("Mariscos El Submarino", None, "'Personal favs' + 'definitely Mariscos El Submarino'"),
                               ("East Harbor Seafood", "East Harbor Seafood Palace", "under 'Personal favs'"),
                               ("Wu’s Wonton King", "Wu's Wonton King", "under 'Personal favs'"),
                               ("Abuqir", None, "under 'Personal favs'"), ("Hamido Seafood", "Hamido", "under 'Personal favs'"),
                               ("Astoria Seafood", None, "under 'Personal favs'"), ("Chuan Tian Xia", None, "under 'Personal favs'"),
                               ("Hug Esan", None, "under 'Personal favs'"), ("Zaab Zaab", None, "under 'Personal favs'")]],
              "Header 'Personal favs' => +2 each.")
L["c0028"] = ([], "Drink brands, not places.")
L["c0029"] = ([M("Fish Cheeks", named_in="title", wait=1, alt={"wait": [None]},
                 why="'around 4/4:40 there's always one or two free tables' = easy walk-in")], "")
L["c0030"] = ([M("Cannelle Patisserie", type="cafe_bakery_dessert", food=1, dishes=[("chocolate mousse cake", 1, False)],
                 terms=["chocolate mousse cake"], why="named as an answer with a dish")], "")
L["c0031"] = ([M("S&P", named_in="parent", food=1, first=False, alt={"food": [None]}, conf="medium",
                 why="'Marked, looks so nice' = mild positive, has not been")], "")
L["c0032"] = ([], "Asks about a panettone product.")
L["c0033"] = ([], "Mod notice.")
L["c0034"] = ([], "'Fancy food is boring... Skip it' targets a category.")
L["c0035"] = ([M("John’s", "John's of Bleecker Street", also=("johns of bleecker", "johns of bleeker st", "johns of bleecker st"),
                 food=1, alt={"food": [2]}, terms=["coal oven"], desc=["coal oven"],
                 why="picks John's in the comparison ('out of spite, plus they got a coal oven')"),
               M("L’industrie", "L'Industrie Pizzeria", also=("lindustrie",), named_in="title", food=-1, amb=True, conf="low",
                 alt={"food": [None]}, why="loses the comparison 'out of spite'; not named in the comment")], "")
L["c0036"] = ([M("Arbys", "Arby's", type="chain", amb=True, conf="low", first=None, alt={"food": [1]},
                 terms=["curly fries"],
                 why="joke: frozen Arby's curly fries from the supermarket; a product more than the restaurant")], "")
L["c0037"] = ([M(r, c, type="bar", food=1, alt={"food": [None]}, terms=["pub crawl"],
                 why="bare list answering a bar-crawl request")
               for r, c in [("Wilfie", "Wilfie & Nell"), ("Grove street social", "Grove Street Social"),
                            ("Spaniard", "The Spaniard"), ("Parkgate", None),
                            ("Barrow Street ale house", "Barrow Street Ale House"),
                            ("Bayard’s ale house", "Bayard's Ale House"), ("White horse", "White Horse Tavern")]], "")
L["c0038"] = ([M("Monkey Bar", wait=-1, first=False, alt={"wait": [None]},
                 why="'never able to get a reservation'; never went")], "")
L["c0039"] = ([M("shopsins", "Shopsin's", named_in="ancestor", food=2, alt={"food": [3]}, rc=False, rt=True,
                 terms=["breakfast", "pancakes"],
                 why="'100%, those breakfasts are insane'; name two levels up, absent from comment mode")], "")
L["c0040"] = ([M("Tommy Bahamas", "Tommy Bahama", type="chain", food=2, dishes=[("coconut shrimp", 2, False)],
                 terms=["coconut shrimp"], why="'is great and they serve a lovely coconut shrimp'")], "")
L["c0041"] = ([M("Verlain", named_in="parent", type="bar", amb=True, conf="low", alt={"food": [1]},
                 why="'Ahh the memories... or lack thereof' = drunk joke about the lychee martinis; no real judgment, nameless")], "")
L["c0042"] = ([M("Wonder", named_in="ancestor", type="food_hall", amb=True, conf="low", first=None, rc=False, rt=False,
                 why="'Didn't they purchase GrubHub?' about Wonder, unnamed and no opinion; ancestors with the name are outside both inputs")], "")
L["c0043"] = ([], "Dogs-in-restaurants rant; does not discuss Ceres Pizza.")
L["c0044"] = ([M("Rubirosa", food=-1, first=False, neg_ok=True, alt={"food": [None]}, conf="medium",
                 why="self-skip on hearsay ('I'd rather skip it'): negative scored, is_negated false (true accepted)")], "")
L["c0045"] = ([M("Serafina", food=-2, value=-2, exp=1, vc=True, neg=True, neg_ok=True, first=None,
                 alt={"food": [-1, -3], "value": [-1, -3], "expensiveness": [2, None]}, conf="medium",
                 why="'Second this. Came here to write Serafina.' answering 'poor quality yet expensive... for an enemy'")],
              "Sarcasm thread: endorsement = negative.")
L["c0046"] = ([M("Costco", type="grocery_market", oos=True, why="retail")], "InKind app + Costco deal.")
L["c0047"] = ([
    M("15 East", closed=True, conf="medium", why="renamed/revived as Sushi Aozora: closed"),
    M("Jewel Bako", closed=True, why="'still great after Masato left' but owners retired: closed"),
    M("Sushi Ann", first=None, why="reference (where a chef went)"),
    M("Sushi Azabu", first=None, why="reference"),
    M("Sushi Aozora", first=None, why="reference (15 East's new name)"),
    M("Omakase by Mitsu", first=False, terms=["omakase"], why="'still havent visited': reference"),
    M("Hasaki", food=2, value=1, exp=-1, alt={"value": [2, None], "expensiveness": [None]},
      why="'now pretty awesome and reasonably priced'"),
    M("Joji", first=None, why="reference (Yuba's chef runs it)"),
    M("Yuba", first=None, why="reference"),
], "Sushi-insider history.")
L["c0048"] = ([], "App self-promo.")
L["c0049"] = ([M("jacks wife freda", "Jack's Wife Freda", food=2, value=-2, exp=1, vc=True,
                 alt={"value": [-3], "expensiveness": [2]},
                 dishes=[("grapefruit and yogurt", 2, False)], terms=["yogurt", "grapefruit and yogurt"],
                 why="'really good'; '$15 is highway robbery' = value complaint")], "")
L["c0050"] = ([], "Subreddit title rules.")
