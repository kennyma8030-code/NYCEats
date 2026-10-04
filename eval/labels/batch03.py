"""Batch 3: c0076-c0100."""
from common import M

L = {}
L["c0076"] = ([M("Hong Kong supermarket", "Hong Kong Supermarket", also=("hks",), type="grocery_market", oos=True,
                 why="retail grocery")], "")
L["c0077"] = ([M(r, c, food=2, alt={"food": [1]}, hood="Williamsburg", why="'Some of my faves in Williamsburg'")
               for r, c in [("Antidote", None), ("Rule of Thirds", None), ("Nura", None), ("Birds of a Feather", None),
                            ("Montesacro", None), ("Misi", None)]], "")
L["c0078"] = ([M("Sweet Chick", food=-2, neg_ok=True, hood="Bedford", alt={"food": [-1]},
                 why="'my order came out undercooked and haven't been back'; the hayday praise is past")], "")
L["c0079"] = ([], "OP's restaurant is unnamed.")
L["c0080"] = ([M("Le Chêne", "Le Chene", first=False, why="quotes the article about its turbot price; reference")], "")
L["c0081"] = ([M("Lin's Garden", named_in="parent", closed=True,
                 why="'Our favorite spot forever' in a closed-restaurants thread")], "")
L["c0082"] = ([M("Indian Accent", food=2, alt={"food": [3]}, why="'Indian Accent is miles better than Junoon'"),
               M("Junoon", alt={"food": [-1]}, first=None, why="loses the comparison; not judged on its own")], "")
L["c0083"] = ([], "Street-vendor risk in general.")
L["c0084"] = ([M("Salt Hank", named_in="parent", food=1, value=-2, exp=2, vc=True, neg_ok=True,
                 alt={"food": [2], "value": [-1], "expensiveness": [1, 3]}, dishes=[("sandwich", 1, False)],
                 terms=["sandwich"], why="'not worth 34 dollars for a sandwich. It was good, but not worth that much'")], "")
L["c0085"] = ([M("Mia's", "Mia's Bakery", type="cafe_bakery_dessert", food=1, hood="Times Square",
                 why="'has many options' as the answer")], "")
L["c0086"] = ([M("times square mcdonalds", "McDonald's", type="chain", hood="times square", first=None,
                 why="proposal anecdote: reference, no opinion of the food")], "")
L["c0087"] = ([M("hi collar", "Hi-Collar", food=1, alt={"food": [None]},
                 terms=["kissaten", "japanese fluffy pancakes", "omelette rice"], why="suggested for pancakes/omurice"),
               M("Bar Moga", first=None, why="reference ('not somewhere I'd take a young kid')"),
               M("kon bon", "Konbon", food=1, alt={"food": [None]}, terms=["izakaya"], first=None,
                 why="cited as an izakaya option"),
               M("ichibani tei", "Ichiban Tei", food=1, alt={"food": [None]}, terms=["fried foods"], first=None,
                 why="suggested for fried foods"),
               M("ootoya", "Ootoya", type="chain", food=-1, alt={"food": [0, 1]}, terms=["japanese chain"],
                 why="'a Japanese chain. They do a variety of foods and its passable'")], "")
L["c0088"] = ([], "Congratulations only.")
L["c0089"] = ([M("lou yau kee", "Lou Yau Kee", food=2, alt={"food": [3]}, dishes=[("chicken", 2, False)],
                 terms=["chicken"],
                 why="'always ends up being my favorite... chicken texture tastes way better than most spots in the city'")], "")
L["c0090"] = ([M("Keen’s", "Keens Steakhouse", also=("keens",), first=False, why="'Never been to Keen's': reference"),
               M("Strip House", food=2, atmosphere=2, service=2,
                 why="'the atmosphere, food, and service at the Strip House make it my favorite'")], "")
L["c0091"] = ([M("Katz's", "Katz's Delicatessen", named_in="parent", food=2, dishes=[("pickle bowls", 2, False)],
                 terms=["pickles"], why="'Absolutely. Good pickle bowls there too.'")], "")
L["c0092"] = ([M("Dennys", "Denny's", type="chain", food=1, first=None, conf="medium",
                 why="'they're consistent' defending Denny's")],
              "Juniors is the target upthread but this comment only defends Denny's.")
L["c0093"] = ([M("Gramercy tavern", "Gramercy Tavern", food=-3, dishes=[("chicken", -3, False)], terms=["lunch"],
                 why="'the most disgusting meal I've ever had in my life'")], "")
L["c0094"] = ([M("oven slice", "Oven Slice", food=-2, hood="LES", alt={"food": [-1]}, terms=["slice", "cheese slice"],
                 why="'not worth anything other than being closest... why did I do this'"),
               M("Johnny's", "Johnny's Pizzeria", also=("johnnys",), food=2, terms=["slice"],
                 why="'a much better slice for 1.50 more'")], "")
L["c0095"] = ([M("Bagel Pub", named_in="parent", food=2, alt={"food": [3]},
                 dishes=[("spread", 2, False), ("salmon", 2, False)], terms=["bagels"],
                 why="'It really is!!!... the spread and their salmon is amazing'"),
               M("Apollo", "Apollo Bagels", food=2, alt={"food": [1]}, terms=["bagels", "crunchy"],
                 why="'I personally prefer the style of bagels of Apollo'")], "")
L["c0096"] = ([M("56709", named_in="title", type="bar", value=1, alt={"value": [None]},
                 terms=["cocktail bar", "taiwanese"],
                 why="'Seems fairly reasonable for a cocktail bar'; key is in production excluded_entities")], "")
L["c0097"] = ([M(r, c, food=2, dishes=[(d, 2, False) for d in ds], why="'some of my favorite places... I love all these'")
               for r, c, ds in [("Don Angie", None, ["lasagne", "potatoes"]),
                                ("Double chicken please", "Double Chicken Please", ["chicken sandwich", "key lime pie drink"]),
                                ("Katzs", "Katz's Delicatessen", ["pastrami"]),
                                ("Golden hof", "Golden HOF", ["honey butter pancakes"]),
                                ("Rivareno", "Rivareno Gelato", []), ("Mary o’s", "Mary O's", ["scone"]),
                                ("Apollo bagels", "Apollo Bagels", ["tomato bagel"]),
                                ("Gray’s papaya", "Gray's Papaya", ["papaya drink"])]], "")
L["c0098"] = ([], "Review-posting advice; says nothing about 888 Hudson Thai itself.")
L["c0099"] = ([], "Texas tacos vs NYC, no place.")
L["c0100"] = ([M("Ammazzacaffee", "Ammazzacaffè", named_in="ancestor", alt={"food": [1]}, rc=False, rt=False,
                 dishes=["reginette", "garganelli", "agnolotti"], terms=["regional italian"],
                 why="defends its menu as regional Italian; name only at d0, outside both inputs")], "")
