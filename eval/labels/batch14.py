"""Batch 14: c0351-c0375."""
from common import M

L = {}
L["c0351"] = ([], "'Wow bravo amazing list' — blanket praise of OP's list; not expanded per place.")
L["c0352"] = ([], "Credit cards.")
L["c0353"] = ([M("Sho", "Sushi Sho", also=("sho",), food=3, why="'favorite meal in the US. Truly unforgettable.'"),
               M("Cesar", "César", also=("cesar",), food=-2, alt={"food": [-3]}, why="'it was a terrible experience for us'"),
               M("Aska", food=3, alt={"food": [2]}, why="'catapult Aska to the top of the list, firmly behind Sushi Sho'"),
               M("LB", "Le Bernardin", also=("lb",), food=1, alt={"food": [None, 2]}, first=None, why="'Glad to see the LB love'")], "")
L["c0354"] = ([M("newsbar cafe", "Newsbar Cafe", type="cafe_bakery_dessert", food=2, dishes=[("chicken sausage hash wrap", 2, False)],
                 terms=["breakfast", "chicken sausage hash wrap"], why="'is great. love the chicken sausage hash wrap'")], "")
L["c0355"] = ([], "")
L["c0356"] = ([M("Kat'z", "Katz's Delicatessen", also=("katz",), food=2, wait=1, terms=["breakfast"],
                 why="'for breakfast... walked in with no queue, definitely recommend! Been twice and love it!'")], "")
L["c0357"] = ([M("fish market", "Fish Market", named_in="parent", amb=True, first=False,
                 why="'What's your fave thing to get there? It's on my list' — nameless question")], "")
L["c0358"] = ([M("Avra", food=1, hood="next to the Pierre Hotel", why="answer; 'I've been there once'")], "")
L["c0359"] = ([M("Pavé", "Pavé", also=("pave",), type="cafe_bakery_dessert", hood="46th St", alt={"food": [1]},
                 why="'a bakery/cafe but they've sold French butter in the past': reference")], "")
L["c0360"] = ([M("Gui", "Gui Steakhouse", food=2, why="'Gui is a great option'")], "")
L["c0361"] = ([M("Dani's", "Dani's House of Pizza", named_in="ancestor", amb=True, hood="on top of the LIRR stop",
                 why="'They do huge late night volume' — nameless info")], "")
L["c0362"] = ([M("Bar Kabawa", food=1, value=-2, exp=2, vc=True, dishes=[("jamaican patties", 1, False)],
                 terms=["jamaican patties"], why="'4 (pretty small) Jamaican patties for 80 bucks... tasty but I was so annoyed'")],
              "Kirby's (title) not discussed.")
L["c0363"] = ([], "About Mario Carbone and Rich Torrisi the people.")
L["c0364"] = ([M("musaafer", "Musaafer", atmosphere=2, why="'musaafer is beautiful'")], "")
L["c0365"] = ([M("Bar Goto Niban", type="bar", food=3, alt={"food": [2]}, hood="close to Barclays",
                 why="'perfection and perfect for this'")], "")
L["c0366"] = ([M("McDonald’s", "McDonald's", named_in="parent", type="chain", amb=True, hood="Penn station",
                 why="'They don't deserve the cleavage' — joke")], "")
L["c0367"] = ([M("Balthazar", service=1, alt={"service": [None]}, first=None,
                 why="'They do that @ Balthazar too' (comps for solo diners at the bar)")], "")
L["c0368"] = ([M("Hillstone", type="chain", food=1, alt={"food": [None], "atmosphere": [-1]}, conf="low",
                 why="dry joke rec for French dip: 'has a nice view of 27th and Park I guess'")], "")
L["c0369"] = ([M("Pata Market", named_in="comment", type="grocery_market", oos=True, hood="Elmhurst",
                 why="Thai grocery/prepared-food store")], "")
L["c0370"] = ([M("Taskin Bakery", type="cafe_bakery_dessert", food=1, hood="midtown east", conf="medium",
                 dishes=["gözleme"], terms=["gözleme"], why="answer; a reply says the city location may have closed")], "")
L["c0371"] = ([M("Four and Twenty Blackbirds", type="cafe_bakery_dessert", food=2, dishes=[("pie crust", 2, False)],
                 terms=["pie", "crust"], why="'I find their crust to be flaky and buttery'")], "")
L["c0372"] = ([M("Strange Delight", atmosphere=-2, value=-2, service=-1, exp=1, vc=True, neg=True, neg_ok=True,
                 alt={"expensiveness": [2, None], "service": [-2]}, hood="Ft Greene", terms=["seafood"],
                 why="'loud, overpriced, and they got all fussy... Cannot recommend.'")], "")
L["c0373"] = ([M("Becco", named_in="parent", amb=True, first=False, why="'Will check them out, thank you' — nameless")], "")
L["c0374"] = ([M("SEA", "SEA Thai", also=("sea",), food=-3, neg_ok=True, hood="Williamsburg",
                 why="'Found a roach in the food'")], "")
L["c0375"] = ([], "")
