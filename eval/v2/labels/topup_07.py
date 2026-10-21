"""v2 top-ups u0205-u0236, labeled blind."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "labels"))
from common import M  # noqa: E402

L = {}
L["t1_osaesfi"] = ([], "'r/brandnewsentence' joke.")
L["t1_oomo9hx"] = ([M("pig beach", "Pig Beach", named_in="ancestor", food=-1, atmosphere=2, alt={"atmosphere": [None]}, rc=False, rt=False,
                      dishes=[("burger", 1, False), ("bbq", -1, False)], hood="gowanus",
                      why="'The old gowanus was a vibe and I liked their burger more than the bbq'")], "")
L["t1_oiqd95d"] = ([], "Chili recipe trivia.")
L["t1_oc8074c"] = ([M("Spicy Moon", named_in="parent", food=1, dishes=["dumplings", "spring rolls"], terms=["vegan", "dumplings"],
                      why="'not a full meal every week, but quite often some dumplings or spring rolls'")], "")
L["t1_njccozj"] = ([M("Yasuda", "Sushi Yasuda", named_in="ancestor", service=-1, first=False, alt={"service": [None]}, rc=False, rt=False,
                      why="'That's unfortunate that they are so rigid.'")], "")
L["t1_oe25n6l"] = ([], "Grinding advice.")
L["t1_ojv05wi"] = ([M("Eleven Madison Park", named_in="ancestor", amb=True, why="'Like so many other vegans before them' — joke")], "")
L["t1_p1rt0bm"] = ([], "Birthday wishes.")
L["t1_nzd62ue"] = ([], "Egg-tart styles in general.")
L["t1_nz8oeas"] = ([M("Carmine’s", "Carmine's", named_in="ancestor", amb=True, first=False, why="'No such thing as too much cheese!' — reacting to a dish warning")], "")
L["t1_p5wa3tc"] = ([], "Restaurant economics.")
L["t1_nrx66ox"] = ([M("King Umberto", oos=True, why="Elmont, Long Island: outside NYC"),
                    M("Umberto", "Umberto's", hood="Greenpoint", first=None, why="founding-year trivia: reference")], "")
L["t1_p90bhi5"] = ([M("Los Tacos", "Los Tacos No. 1", named_in="ancestor", amb=True, why="private-equity zombie joke; nameless")], "")
L["t1_oc13tyf"] = ([M("Taqueria Ramirez", named_in="title", amb=True, dishes=["al pastor"], why="'They have al pastor which is pork' — info")], "")
L["t1_o0ljqwh"] = ([], "Argument about virtue signaling.")
L["t1_oacgsiu"] = ([M("blockheads", "Blockheads", named_in="parent", type="bar", closed=True, rc=True, rt=False,
                      why="'RIP blockheads' — 'Best bar to drink outside at'")], "")
L["t1_nxu54gy"] = ([M("The 787", "787 Coffee", type="cafe_bakery_dessert", atmosphere=0, alt={"atmosphere": [-1, 1]}, hood="Tribeca",
                      why="'always hopping... lots of seating... Not sure if I'd call it cozy... small, packed'")], "")
L["t1_nfqsrj4"] = ([M("Katz", "Katz's Delicatessen", also=("katzs",), named_in="title", food=-1, atmosphere=-2, neg=True,
                      hood="brooklyn location", alt={"food": [None]},
                      why="'I would advise against this. Quality isn't going to be as high, zero vibes. Food hall spots are never as good'")], "")
L["t1_os1bcbf"] = ([M("Le Bonne Soupe", "La Bonne Soupe", named_in="parent", food=1, why="'Yes, was going to suggest this place.'"),
                    M("Boucherie", food=1, atmosphere=1, alt={"atmosphere": [None]}, hood="midtown",
                      why="'has kind of an outdoor courtyard (although it's covered)'")], "")
L["t1_o6chj7z"] = ([M("manhatta", "Manhatta", named_in="comment", atmosphere=2, food=1, alt={"food": [None]}, terms=["drinks", "view"],
                      why="'a good choice... pretty nice classy place that friends enjoy'")], "")
L["t1_nhtx2nj"] = ([M("Lavagna", food=1, atmosphere=2, alt={"food": [2]}, hood="East Village", terms=["cozy", "italian"],
                      why="'Been there 27 years and so so cozy'")], "")
L["t1_o06sgso"] = ([M("Dennino’s", "Denino's", also=("deninos",), food=1, alt={"food": [2]}, terms=["pizza", "large group"],
                      why="'I like Dennino's and it's big and isn't a tourist place.'")], "")
L["t1_o4gb64l"] = ([M("fay da", "Fay Da Bakery", named_in="comment", type="cafe_bakery_dessert", food=-1, neg_ok=True,
                      alt={"food": [1, -2]},
                      why="'after finding a hair in my food for the second time I had to say goodbye forever... I really do like the food'")], "")
L["t1_nq2klr6"] = ([M("laojie", "Lao Jie Hotpot", food=1, why="'I second going to laojie instead'"),
                    M("99 favor taste", "99 Favor Taste", named_in="title", type="chain", atmosphere=-2, neg_ok=True, alt={"food": [1]},
                      why="'99 is a good time but never clean'")], "")
L["t1_nsp8gdj"] = ([M("Papillon", food=1, atmosphere=1, alt={"atmosphere": [None]}, terms=["christmas"], why="'Papillon for sure'"),
                    M("Pete’s tavern", "Pete's Tavern", type="bar", atmosphere=2, terms=["christmas"], why="'they do a great job'")], "")
L["t1_oem5sml"] = ([M("Abraço", "Abraço", also=("abraco",), type="cafe_bakery_dessert", food=2, atmosphere=2, alt={"food": [3]},
                      dishes=[("coffee", 2, False), ("olive oil cake", 2, False)], terms=["coffee", "olive oil cake"],
                      why="'Fantastic coffee and olive oil cake, and also just a beautiful experience'")], "")
L["t1_nx5jd1n"] = ([M("bCD tofu house", "BCD Tofu House", type="chain", food=1, alt={"atmosphere": [1]}, terms=["korean", "tofu"],
                      why="'bCD tofu house is fun'"),
                    M("Saperavi", food=2, alt={"food": [1]}, terms=["georgian cheese boat"], why="'Prefer Saperavi over Chama Mama'"),
                    M("Chama Mama", food=-1, alt={"food": [0, None]}, why="less preferred")], "")
L["t1_nl2b0mq"] = ([M("Monkey Bar", food=1, atmosphere=1, alt={"food": [None], "atmosphere": [2]}, why="'Monkey Bar is most similar'"),
                    M("4 Charles", "4 Charles Prime Rib", atmosphere=1, wait=-2, why="'a more intimate version but a rez will be hard'"),
                    M("Twin Tails", atmosphere=1, why="'similarly maximalist'")], "")
L["t1_o4pc0ku"] = ([M("Wheated", food=1, alt={"food": [2]}, terms=["pizza"], why="'They've very humble... just care about making good food'")], "")
L["t1_ojxoaow"] = ([], "Unnamed failed doner places.")
L["t1_o49ytec"] = ([], "Flour suppliers.")
L["t1_pc1wgff"] = ([M("Dig inn", "Dig Inn", also=("dig",), named_in="comment", type="chain", food=-1, value=-2, vc=True, alt={"food": [None]},
                      why="'Dig inn was never worth the dig! ...how much can you make people pay for leftovers'")], "")
