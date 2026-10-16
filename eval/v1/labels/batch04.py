"""Batch 4: c0101-c0125."""
from common import M

L = {}
L["c0101"] = ([M("Lobster Place", named_in="parent", type="stall_vendor", food=2, hood="Chelsea Market",
                 dishes=[("sushi", 2, False)], terms=["sushi"], why="'And seriously great sushi.' continuing the Lobster Place rec")], "")
L["c0102"] = ([M("Din Tai Fung", also=("dtf",), named_in="title", type="chain", food=-1, alt={"food": [None]},
                 dishes=[("chocolate dumplings", 1, False)], terms=["dumplings", "chocolate dumplings"], first=None,
                 why="'The only unique dish there is the chocolate dumplings everything else is basic cuisine'")], "")
L["c0103"] = ([M("Kam Rai", alt={"food": [1]}, dishes=["massaman curry"], terms=["massaman curry"],
                 why="'I had the massaman at Kam Rai, it was the worst to you??' — surprised, implies it was fine")], "")
L["c0104"] = ([
    M("Rolo's", named_in="title", food=-1, service=-2, value=-1, exp=2, vc=True, neg_ok=True,
      alt={"food": [0], "service": [-3], "value": [-2, None], "expensiveness": [1]},
      dishes=[("steaks", 2, False), ("polenta bread", -1, False), ("ramp and taleggio polenta bread", -2, False),
              ("shrimp", 2, False), ("porkchop", None, False)],
      terms=["steak", "polenta bread", "fine dining", "wine", "cocktails"],
      why="'service is really inconsistent... they get combative'; 'expensive, overhyped, and kinda mid'; 'would never travel to go here'"),
    M("cassette", "Cassette", type="bar", food=2, alt={"food": [1]}, terms=["cocktails"],
      why="'cassette is more creative and better executed' for cocktails"),
    M("hellbender", "Hellbender", food=-2, neg_ok=True, alt={"food": [-3]}, first=None,
      why="'hellbender sucks. full stop. nothing good there.'"),
], "")
L["c0105"] = ([M("Sams", "Sam's Restaurant", also=("sams",), food=2, atmosphere=2, alt={"food": [1]},
                 dishes=[("pizza", None, False), ("parms", 2, False)], terms=["pizza", "chicken parm"],
                 why="'Love Sams... The parms and the vibes were awesome'; pizza 'not better than Lucali'"),
               M("Lucali", food=1, alt={"food": [2, None]}, first=None, why="wins the pizza comparison")], "")
L["c0106"] = ([M("hmart", "H Mart", type="grocery_market", oos=True, why="store-bought dumplings link")], "")
L["c0107"] = ([M("Dame", named_in="title", food=1, atmosphere=2, alt={"food": [2], "atmosphere": [1]},
                 dishes=[("grilled oysters", 2, False), ("crispy polenta", 2, False), ("sticky toffee pudding", 2, False),
                         ("fish and chips", -1, False), ("squid and scallion skewers", None, False),
                         ("citrus salad with peekytoe crab", None, False)],
                 terms=["grilled oysters", "fish and chips", "sticky toffee pudding", "wine by the glass", "bar seating"],
                 why="favorites listed; fish and chips 'did not understand the hype'; 'amazing vibes'")], "")
L["c0108"] = ([M("El Califa de Leon", named_in="title", amb=True, conf="low", first=None, alt={"food": [-1]},
                 why="'what does Michelin know about tacos' — dismisses the star; whether it knocks the place is unclear")], "")
L["c0109"] = ([], "Grocery logistics, no place.")
L["c0110"] = ([M("Chick Fil A", "Chick-fil-A", type="chain", first=None, alt={"food": [-1]},
                 why="example of tourist chain lists; reference"),
               M("Five Guys", type="chain", first=None, alt={"food": [-1]}, why="same")], "")
L["c0111"] = ([M("Santa Fe BK", named_in="parent", food=-2, alt={"food": [-1]},
                 why="'It's so bland. I don't get the hype'")], "")
L["c0112"] = ([M("Rosa's", "Rosa's Pizza", named_in="ancestor", food=1, hood="Williamsburg", rc=False, rt=True,
                 dishes=[("penne vodka", None, False), ("eggplant parm slices", 1, False)],
                 terms=["penne vodka", "eggplant parm slice"],
                 why="regular for the eggplant parm slices; will try the penne vodka; name two levels up")], "")
L["c0113"] = ([M("Nom Wah Tea Parlor", food=-2, atmosphere=1, neg_ok=True, alt={"atmosphere": [None]},
                 terms=["historic"], why="'I regret trying... decor/atmosphere are interesting but... the food was bad'")], "")
L["c0114"] = ([M("4 Charles", "4 Charles Prime Rib", also=("4 charles",), named_in="title", food=-1, neg=True, neg_ok=True,
                 alt={"food": [None], "value": [-1]}, first=None, conf="medium",
                 why="'It's not worth all that, I promise.' telling OP not to chase the reservation")], "")
L["c0115"] = ([
    M("Hi Collar", "Hi-Collar", food=1, hood="East Village", terms=["kissaten", "yoshoku", "fluffy pancakes", "omurice"],
      dishes=[("siphon pour over", 1, False), ("fluffy pancakes", 1, False), ("omurice", 1, False), ("sando", 1, False)],
      why="'Get the Siphon Pour Over, Fluffy Pancakes, Omurice and a Sando'"),
    M("Sobaya", food=1, hood="East Village", terms=["michelin bib gourmand"], why="listed; 'has a michelin Bibgourmand'"),
    M("Raku", food=3, hood="East Village", dishes=[("udon", 3, False)], terms=["udon"], why="'has best udon in the city'"),
    M("Little Mynamar", "Little Myanmar", food=2, wait=1, exp=-2, hood="East Village", alt={"food": [1], "expensiveness": [-1]},
      terms=["cash only", "burmese", "family run", "michelin bib gourmand"],
      why="'NYC top 100, Michelin Bib Gourmand... under 30$ per person... I usually walk in'"),
    M("Gazab", food=2, value=2, exp=-1, alt={"value": [1]}, dishes=[("dum biriyani", 1, False)], terms=["indian", "dum biriyani"],
      why="'a surprisingly affordable high quality indian restaurant... Get the Dum Biriyani for sure'"),
    M("Saigon social", "Saigon Social", food=1, alt={"food": [2]}, terms=["vietnamese"], why="'for unique vietnamese'"),
    M("Pig and Khao", closed=True, terms=["family style"], why="recommended, but a reply says 'Pig and Khao closed.'"),
    M("Trappazino", "Trapizzino", food=1, terms=["trapizzini", "roman street food", "pastas"], alt={"expensiveness": [-1]},
      why="described as roman street food, affordable for three"),
], "Big East Village list.")
L["c0116"] = ([M("Barney Greengrass", food=1, why="named as the answer"),
               M("Zabars", "Zabar's", type="grocery_market", oos=True, why="retail")], "")
L["c0117"] = ([
    M("Red Hook Tavern", named_in="title", food=3, alt={"wait": [-1]},
      dishes=[("burger", 3, False), ("cottage fries", None, False), ("pickle", 2, False), ("ham and cheese croquettes", 2, False),
              ("kale salad", 2, False), ("wedge with bacon", None, False)],
      terms=["burger", "dry-aged burger", "cottage fries", "croquettes"],
      why="'It is the best burger in nyc currently'; get a reservation instead of the line"),
    M("Peter Luger", first=None, why="reference: burger inspiration"),
    M("Minetta Tavern", first=None, why="reference: dry-aged blend inspiration"),
    M("JG Mellon", "J.G. Melon", type="restaurant", first=None, why="reference: 'JG Mellon style' fries"),
], "")
L["c0118"] = ([], "No place.")
L["c0119"] = ([M("ok canaan", "OK Canaan", closed=True, why="suggested sister restaurant; a reply says 'Ok Canaan closed!'"),
               M("OK Ryan", named_in="parent", amb=True, why="'their sister restaurant' — nameless nod to the parent's place")], "")
L["c0120"] = ([], "Argument about a commenter.")
L["c0121"] = ([], "Sarcasm at a commenter.")
L["c0122"] = ([M("kings kitchen", "King's Kitchen", named_in="ancestor", rc=False, rt=True, alt={"food": [-1]},
                 dishes=["hk roast goose"], terms=["hk roast goose", "roast goose"],
                 why="confirms it is HK roast goose, ordered in person; their 'only okay' is in an earlier comment")], "")
L["c0123"] = ([M("Leon's", "Leon's Bagels", also=("leons",), food=-2, neg_ok=True, dishes=[("bagel", -2, False)], terms=["bagel"],
                 why="'I regret going to Leon's and the bagel tastes like a grocery store bagel'")], "")
L["c0124"] = ([M("Coqodaq", "Coqodaq", also=("cocodaq",), named_in="title", food=-1, neg=True, alt={"food": [-2]},
                 dishes=[("dessert", 1, False)], first=None, why="'Skip, best part of the meal is dessert'")], "")
L["c0125"] = ([M("the Modern", "The Modern", food=2, alt={"food": [1, None]},
                 why="'been to the Modern more times than I can count'; 'Phenomenal choices'")],
              "'Phenomenal choices' also blanket-endorses the post's list; not expanded per place.")
