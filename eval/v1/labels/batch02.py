"""Batch 2: c0051-c0100."""
from common import M

L = {}
L["c0051"] = ([M("Rollin Bagels", named_in="parent", type="food_truck", food=1, alt={"food": [2]},
                 why="'That's a good one' endorsing the parent's added cart")], "")
L["c0052"] = ([], "Argues about downvotes; judges no place.")
L["c0053"] = ([M("Luigi’s", "Luigi's Pizza", also=("luigis",), named_in="ancestor", food=-3,
                 dishes=[("pizza", -3, False)], terms=["pizza"], rc=False, rt=True, conf="medium",
                 why="'So hard it was inedible' continuing their own Luigi's complaint two levels up; comment mode sees only 'Too crunchy?'")], "")
L["c0054"] = ([], "'Avoid' targets pizzeria meatballs in general, no named place.")
L["c0055"] = ([M("Luigi’s", "Luigi's Pizza", also=("luigis",), food=1, hood="Park Slope",
                 why="named as the answer to 'most worth-it pizza'")], "")
L["c0056"] = ([M("Costco", type="grocery_market", oos=True, food=1, value=1, why="retail lox; out of scope"),
               M("Zabars", "Zabar's", type="grocery_market", oos=True, why="retail; quality reference")], "Kossar's only in title.")
L["c0057"] = ([M("Atera", exp=3, first=False, terms=["chef's counter"],
                 why="reservation transfer: reference mention; $707 for two = very expensive")], "")
L["c0058"] = ([], "No NYC tonkatsu place named.")
L["c0059"] = ([], "")
L["c0060"] = ([M("Nabila’s", "Nabila's", hood="cobble hill", food=1, why="named as the answer to the knafeh question")], "")
L["c0061"] = ([M("two doors down", "Two Doors Down", named_in="parent", type="bar", amb=True, first=False,
                 why="nameless question about the parent's happy hour; no opinion")], "")
L["c0062"] = ([M("balaboosta", "Balaboosta", hood="west village", first=None, terms=[],
                 why="reference: where the chef works now"),
               M("bar bolonat", "Bar Bolonat", closed=True, first=None,
                 why="combined into Balaboosta: closed")], "")
L["c0063"] = ([M("Peter Luger", named_in="title", food=2, service=1, alt={"food": [3], "service": [None]},
                 terms=["classic steakhouse"],
                 why="'never had a meal that wasn't excellent... for a classic steakhouse it's excellent'; 'never had a rude waiter'")], "")
L["c0064"] = ([M("Chef’s Table at Brooklyn Fare", "Chef's Table at Brooklyn Fare", also=("ctbf", "ctfb"), named_in="parent",
                 service=-2, value=-2, vc=True, neg=True, neg_ok=True, alt={"service": [-3], "value": [-1]},
                 why="'Service is horrible. Def not worth it'")], "")
L["c0065"] = ([M("Cote", food=2, alt={"food": [1]}, terms=["korean", "korean bbq"],
                 why="'Cote is quite good... traditional Korean in a modern environment. It works.'"),
               M("Cocodaq", food=-3, first=None, neg_ok=True,
                 why="'an abomination and should be burned to the ground'")], "")
L["c0066"] = ([M("Cafe Pri", type="cafe_bakery_dessert", food=1, alt={"food": [2]}, hood="Ridgewood", terms=["filipino"],
                 why="'I like Cafe Pri, a Filipino owned cafe'"),
               M("Patok by Rach", type="stall_vendor", hood="Dekalb Market", first=True,
                 why="'opened at Dekalb Market but have only tried their food as popup': reference"),
               M("Dekalb Market", "DeKalb Market Hall", type="food_hall", amb=True, why="location of Patok only"),
               *[M(r, c, food=1, hood="Woodside", terms=["filipino"], why="named as answers: 'start with...'")
                 for r, c in [("Ihawan", None), ("Renee's", "Renee's Kitchenette"), ("Kalye bistro", "Kalye Bistro"),
                              ("Tito Rad's", "Tito Rad's Grill")]]], "")
L["c0067"] = ([M("gertie", "Gertie", food=-2, alt={"food": [-1]}, dishes=[("gertie and kabawa crossover", -2, False)],
                 why="collab item at The Great Nosh: 'felt super letdown'"),
               M("kabawa", "Kabawa", food=-2, alt={"food": [-1]}, dishes=[("gertie and kabawa crossover", -2, False)],
                 why="same collab"),
               M("oneg", "Oneg Bakery", type="cafe_bakery_dessert", food=2, dishes=[("babka", 2, False)], terms=["babka"],
                 why="'the oneg Babka... were great'"),
               M("kfar", "Kfar", food=2, why="'the kfar... were great'"),
               M("sailor", "Sailor", food=2, dishes=[("borek", 2, False)], terms=["borek"], why="'sailor borek were great'"),
               M("ops", "OPS", food=2, dishes=[("potato pie", 2, False)], terms=["potato pie"],
                 why="'The ops potato pie was really good'")],
              "The Great Nosh is an event; '$40 overpriced' is about its tickets.")
L["c0068"] = ([], "Unnamed closed Thai place.")
L["c0069"] = ([], "")
L["c0070"] = ([M("Quique Crudo", named_in="title", amb=True, conf="low",
                 why="'thats nyc for ya' shrugging off the small space; no real judgment")], "")
L["c0071"] = ([M("Mapo", "Mapo Korean BBQ", also=("mapo",), food=2, dishes=[("banchan", 2, False)], terms=["banchan"],
                 why="'Mapo banchans are so good'")], "")
L["c0072"] = ([], "Queso recipe banter.")
L["c0073"] = ([M("Indian Accent", first=None, why="reference: example of a list entry with no reasoning"),
               M("Hutong", first=None, why="reference: same")],
              "Critiques the crowd-sourced worst list.")
L["c0074"] = ([M("lenwich", "Lenwich", type="chain", food=-1, neg=True, alt={"food": [-2, None]},
                 why="'jeeze skip lenwich' telling OP to skip it")], "")
L["c0075"] = ([M("chipotle", "Chipotle", type="chain", food=-1, first=None, alt={"food": [-2, None]},
                 why="'don't know why anyone goes to chipotle in NYC'"),
               M("dos toros", "Dos Toros", type="chain", food=2, terms=["mexican"],
                 why="'we have dos toros, los tacos and a million other amazing Mexican places'"),
               M("los tacos", "Los Tacos No. 1", also=("los tacos",), food=2, terms=["mexican"], why="same")], "")
