"""Batch 11: c0276-c0300."""
from common import M

L = {}
L["c0276"] = ([], "YouTubers, not places.")
L["c0277"] = ([], "Tipping on comps in general.")
L["c0278"] = ([M("Katz’s", "Katz's Delicatessen", named_in="title", amb=True, first=None,
                 why="'Is it not too much meat,' — nameless question")], "")
L["c0279"] = ([M("Tang Maru", food=2, hood="Fort Lee", oos=True, why="Fort Lee, NJ: outside NYC")], "")
L["c0280"] = ([M("Taco Bell", named_in="parent", type="chain", amb=True, first=None,
                 why="chalupa joke about Taco Bell prices; nameless")], "")
L["c0281"] = ([M("Le B", "Le Bernardin", also=("le b",), named_in="title", food=-1, service=-3,
                 alt={"food": [-2, 0], "service": [-2]},
                 why="'first few bites were exceptional... doldrums... unremarkably similar... overwhelmingly salty'; 'service... probably the worst I can recall at a fine dining place'"),
               M("per se", "Per Se", first=None, why="reference in comparison"),
               M("EMP", "Eleven Madison Park", also=("emp",), first=None, why="reference in comparison")], "")
L["c0282"] = ([M("katz", "Katz's Delicatessen", service=-2, atmosphere=-2, value=-1, vc=True, neg_ok=True,
                 alt={"service": [-3], "value": [-2]}, dishes=[("sandwich", -1, False)],
                 why="'bouncer was getting aggressive... so hectic and stressful, it's just not worth it to me for a measly sandwich'")], "")
L["c0283"] = ([
    M("Sunday Morning", type="cafe_bakery_dessert", food=3, alt={"food": [2], "wait": [-1]}, dishes=[("cinnamon roll", 3, False)],
      terms=["cinnamon roll"], why="'Sunday Morning is the #1 answer. Recommend getting there just before they open.'"),
    M("Red Gate Bakery", type="cafe_bakery_dessert", food=1, dishes=[("cinnamon roll", None, False)], terms=["cinnamon roll"],
      why="schedule info for its rolls"),
    M("Hani's", "Hani's Bakery", type="cafe_bakery_dessert", food=0, alt={"food": [-1]}, dishes=[("cinnamon roll", 0, False)],
      terms=["cinnamon roll", "malty cream cheese frosting"],
      why="'a unique take with a malty cream cheese frosting but I prefer something a bit more ooey gooey'"),
    M("Spirals", type="cafe_bakery_dessert", first=False, terms=["cinnamon buns"], why="'Haven't been': reference"),
    M("Benji's Buns", type="cafe_bakery_dessert", first=False, terms=["cinnamon buns"], why="'Haven't been': reference"),
    M("Librae", type="cafe_bakery_dessert", food=1, dishes=[("chai sticky bun", 1, False)], terms=["chai sticky bun"],
      why="'deserves an honorable mention'"),
    M("Vato", type="cafe_bakery_dessert", food=2, alt={"food": [3]}, hood="Park Slope", dishes=[("cinnamon roll", 2, False)],
      terms=["cinnamon roll"], why="'one of the best cinnamon rolls I had recently'"),
], "")
L["c0284"] = ([M("Los Burritos Juárez", also=("lbj",), named_in="title", food=1, alt={"food": [0, 2]},
                 dishes=[("mole", 2, False)], terms=["burrito", "mole"],
                 why="'For a local spot... it's awesome. For a hyped up... underwhelming. Mole is the best one'")], "")
L["c0285"] = ([M(r, c, food=1, why="list answer")
               for r, c in [("Gallagher’s", "Gallaghers Steakhouse"), ("Bobby Van’s", "Bobby Van's"),
                            ("Keene’s", "Keens Steakhouse"), ("Smith and Wollensky", "Smith & Wollensky")]], "")
L["c0286"] = ([], "Celery soda question.")
L["c0287"] = ([], "")
L["c0288"] = ([M("Los tacos", "Los Tacos No. 1", named_in="comment", food=2, value=-2, exp=1, vc=True,
                 alt={"expensiveness": [2]}, dishes=["tacos"], terms=["tacos"],
                 why="'I like it very much, but when 3 tacos and a drink is nearing 30 bucks it becomes very not worth it'")], "")
L["c0289"] = ([], "White borscht with no place.")
L["c0290"] = ([M("Peter Pan", "Peter Pan Bagels", also=("peter pan",), food=3, dishes=[("bagels", 3, False), ("sandwiches", 3, False)],
                 terms=["bagels"], why="'hands down the best bagels I've ever had in my life... flawless'")], "")
L["c0291"] = ([M("4F", "L'Appartement 4F", also=("4f", "lappartement 4f"), type="cafe_bakery_dessert", food=-2,
                 dishes=[("croissant", -2, False)], terms=["croissant"], why="'Poor lamination at 4F, pretty greasy'")], "")
L["c0292"] = ([], "Mod notice.")
L["c0293"] = ([M("levain", "Levain Bakery", named_in="title", type="cafe_bakery_dessert", wait=-2, neg_ok=True,
                 alt={"wait": [-1]}, why="'Not worth the wait though'")], "")
L["c0294"] = ([M("Johnnys", "Johnny's Bar", named_in="parent", type="bar", amb=True, hood="Greenwich Ave",
                 why="'Is this the tiny place in Greenwich Ave I can never find?' — identity question")], "")
L["c0295"] = ([M("Hillstone", named_in="ancestor", type="chain", food=-2, neg_ok=True, alt={"food": [-1]}, rc=False, rt=True,
                 why="'I'm just going to assume you agree these places suck'")], "")
L["c0296"] = ([M("Malecón", "El Malecon", also=("malecon",), named_in="parent", food=1, dishes=[("green sauce", 1, False)],
                 terms=["green sauce"], why="'Get extra green sauce.'")], "")
L["c0297"] = ([M("sweet chick", "Sweet Chick", named_in="parent", food=-3, neg=True, neg_ok=True,
                 why="'i got fricken food poisoning' under 'Skip sweet chick'")], "")
L["c0298"] = ([M("Bong", named_in="title", food=2, value=1, service=2, exp=2, alt={"value": [2], "expensiveness": [1]},
                 dishes=[("crab salad", 2, False), ("shrimp", 2, False), ("whole dorade fish", 2, False),
                         ("ode to chicken", -2, True)],
                 terms=["cambodian", "crab salad", "whole dorade"],
                 why="'Though expensive... a good deal'; dishes excellent; 'ode to chicken... the only one I would skip'; 'incredibly warm and welcoming'")], "")
L["c0299"] = ([], "Influencer economics.")
L["c0300"] = ([], "OP replying about photos.")
