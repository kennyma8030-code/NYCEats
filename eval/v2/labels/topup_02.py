"""v2 top-ups u0030-u0064, labeled blind."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "labels"))
from common import M  # noqa: E402

L = {}
L["t1_ngu2q9z"] = ([M("carbone", "Carbone", named_in="title", food=-1, value=-1, vc=True, alt={"food": [0], "value": [None]}, conf="medium",
                      dishes=[("bread service", 2, False)],
                      why="earlier visit great; 'Went last week and was kinda a dud. Food was fine but... Parm... 25% the price'"),
                    M("Parm", food=1, value=1, alt={"value": [None]}, dishes=[("spicy rigatoni", 1, False)], terms=["spicy rigatoni"],
                      why="'I'd rather just go to Parm and get the spicy rigatoni for like 25% the price'")], "")
L["t1_p7m31w0"] = ([M("Los Tacos No. 1", named_in="title", amb=True, alt={"food": [2], "expensiveness": [1]},
                      why="'In the age of the $8 great taco the only place to move is to make it worse' — about the PE deal")], "")
L["t1_nz6olf5"] = ([M("Parm", food=2, alt={"food": [3]}, neg_ok=True, hood="by the WTC",
                      dishes=[("roast beef sandwich", 2, False)], terms=["roast beef sandwich", "arugula", "balsamic glaze"],
                      why="'Parm low key has an incredible roast beef sandwich... it's fantastic' (skip if a tourist)")], "")
L["t1_p8ncw86"] = ([M("Minetta Tavern", named_in="parent", food=3, dishes=[("burger", 3, False)], terms=["burger"],
                      why="'Have had the burger twice and thought it was unreal'")], "")
L["t1_nu30a49"] = ([M("Parm", wait=1, why="'I've never had a problem just walking in at Parm.'")], "")
L["t1_o7qhqc2"] = ([M("Sake No Hana", named_in="title", food=2, wait=1, value=-1, exp=1, vc=True, alt={"expensiveness": [None]},
                      terms=["pizza", "pop-up"],
                      why="'got our first pizza in 10 mins... the 50% increase in price was unpleasant. Food was delicious though'")], "")
L["t1_p7vrpc9"] = ([M("Red Hook Tavern", named_in="title", food=-3, dishes=[("burger", -3, False), ("fries", -2, False)],
                      terms=["burger", "fries"], why="'Horrendous burger... One of my worst dining experiences in the city.'")], "")
L["t1_o93dyfy"] = ([], "")
L["t1_omzsduj"] = ([M("parm", "Parm", food=-2, service=-2, alt={"food": [-3]}, dishes=[("chicken", -2, False)],
                      why="'The last 2 times I went to parm it was lousy... very bad. Service, quality both bad. Chicken was totally over cooked.'")], "")
L["t1_okcrc8i"] = ([], "")
L["t1_obl8lo7"] = ([M("Slice", food=2, conf="low", why="'Slice has really good pizza by Wylie Dufresne'")], "")
L["t1_omzrcs0"] = ([M("parm", "Parm", food=1, atmosphere=1, alt={"atmosphere": [None]}, why="'same menu for the pasta & more casual'")], "")
L["t1_jrqmqu9"] = ([M("Carbone", food=2, why="'I've always really enjoyed Carbone.'"),
                    M("Parm", food=-1, why="'Parm is pretty w/e imo'")], "MFG is a restaurant group.")
L["t1_p71aq8x"] = ([M("Parm", first=None, dishes=["sunday salad"], terms=["sunday salad"], why="'(e.g. Parm has one, as well)': reference")], "")
L["t1_o946m3r"] = ([], "")
L["t1_ohgufj3"] = ([], "")
L["t1_nl76cvp"] = ([], "")
L["t1_p7vut7z"] = ([M("Red Hook Tavern", named_in="title", food=1, alt={"food": [2, 0], "value": [-1]}, dishes=[("burger", 1, False)],
                      why="'Burger was fine. Great even. Other better burgers exist at an equal or lower price point.'")], "")
L["t1_np2lbw8"] = ([M("Ceres", "Ceres Pizza", named_in="title", food=3, wait=-2, alt={"food": [2], "wait": [-1]},
                      dishes=[("pizza", 2, False)], terms=["thin crispy pizza"],
                      why="'Pizza was actually pretty damn incredible... Showed up at 10:30... Worth the trouble'")], "")
L["t1_laijt60"] = ([M("Dallas BBQ", named_in="ancestor", type="chain", food=1, alt={"food": [2]}, rc=False, rt=False,
                      dishes=[("wings", 2, False), ("brisket", -2, False)], terms=["wings"],
                      why="'meatiest wings I've eaten in NYC... brisket... wasn't good'")], "")
L["t1_nyj9osy"] = ([M("Zibetto", "Zibetto Espresso Bar", type="cafe_bakery_dessert", food=3, atmosphere=2, hood="56th and 6th",
                      terms=["espresso", "old school"], why="'Zibetto is the best in NY. Original location for that old school vibe'")], "")
L["t1_p3qu4b4"] = ([M("Their Pizza on 6th Avenue", "Roma Pizza", named_in="selftext", food=-2, alt={"food": [-3]}, hood="6th Avenue",
                      conf="medium", why="'Their Pizza on 6th Avenue is also terrible' — Roma Pizza's other location")], "")
L["t1_nrk3v39"] = ([M("Los Tacos", "Los Tacos No. 1", named_in="parent", food=2, dishes=[("al pastor", 2, False)], terms=["al pastor"],
                      why="'Really? Their al pastor is dripping with juices'")], "")
L["t1_npcc4ce"] = ([M("Lucia's", "Lucia Pizza", named_in="parent", food=3, alt={"food": [2]}, hood="upper east side",
                      why="'Their spot on the upper east side is my favorite pizza in the city right now!'")], "")
L["t1_nqdzwed"] = ([M("Parm", type="chain", food=1, alt={"food": [2]}, terms=["italian american", "kids"],
                      why="'great for kids. It's not too shabby for adults either.'")], "")
L["t1_o236r99"] = ([], "")
L["t1_o9kg4m0"] = ([M("los tacos no 1", "Los Tacos No. 1", named_in="title", exp=2, value=-1, vc=True, first=False,
                      alt={"value": [None], "expensiveness": [1]}, why="'peeked at their menu. You weren't kidding' (prices crazy)")], "")
L["t1_oh7geq3"] = ([M("By The Way Bakery", named_in="parent", type="cafe_bakery_dessert", food=3, dishes=[("coconut cake", 3, False)],
                      terms=["gluten free", "coconut cake"], why="'Their coconut cake is to die for'")], "")
L["t1_pamcjpd"] = ([M("RHT", "Red Hook Tavern", also=("rht",), food=2,
                      dishes=[("burger", 0, False), ("cavatelli", 2, False), ("pork chop", 2, False), ("head on prawns", 2, False),
                              ("chicken", 2, False)], terms=["cavatelli", "pork chop", "head on prawns"],
                      why="'the burger is my least favorite thing... The cavatelli, pork chop, head on prawns, chicken are all excellent'")], "")
L["t1_opc9xq0"] = ([M("Rolo's", named_in="title", food=3, alt={"food": [2]},
                      dishes=[("burger", 2, False), ("crispy potatoes", 2, False), ("polenta", 2, False), ("pork chop", 3, False),
                              ("lasagna", 2, False), ("french toast", 3, False), ("steak", 1, False)],
                      terms=["brunch", "pork chop", "french toast", "cocktails"],
                      why="'Pork chop... maybe the best I ever had... French toast always exceptional. Steak is very good but...'")], "")
L["t1_o0nn1de"] = ([M("Pop up bagels", "Pop Up Bagels", named_in="parent", type="chain", service=-2, alt={"service": [-1]}, rc=True, rt=False,
                      why="'They also won't slice a fucking bagel'")], "")
L["t1_nuwhimj"] = ([M("Fette Sau", named_in="title", closed=True, why="closing; 'never the biggest fan of their food but... sad to see them go'")], "")
L["t1_omzt16d"] = ([M("Parm", food=-2, dishes=[("chicken parm", -2, False), ("pasta", -2, False)],
                      why="'Parm was bad. I have had better chicken parm at a pizzeria... the pasta was overcooked'"),
                    M("Carbone", first=None, why="comparison reference")], "")
L["t1_nxindu5"] = ([M("Parm", food=1, wait=1, alt={"food": [None]}, dishes=["carbone pasta"], terms=["spicy vodka pasta"],
                      why="'You can get the Carbone pasta at Parm with no crazy reservation'"),
                    M("Carbone", wait=-1, alt={"wait": [None]}, first=None, why="'crazy reservation'")], "")
L["t1_jrqd79z"] = ([M("Parm", food=1, alt={"food": [0]}, dishes=[("meatballs", -1, False)],
                      why="'basically live at Parm. Are there once had to return the meatballs cause they seemed undercooked'"),
                    M("Magnolia Bakery", type="chain", food=-1, dishes=[("banana pudding", 2, False)],
                      why="'Magnolia Bakery is only good for that Banana Pudding'")], "")
