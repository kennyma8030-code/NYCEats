"""Batch 6: c0151-c0175."""
from common import M

L = {}
L["c0151"] = ([], "OP clarifying needs; Katz's not judged.")
L["c0152"] = ([M("Yasaka", "Sushi Yasaka", also=("sushi yasaka",), named_in="ancestor", atmosphere=-1,
                 alt={"atmosphere": [-2], "food": [1]}, first=None, rc=False, rt=True, conf="medium",
                 why="'such a solid spot for decades... have not refreshed anything since then' (dated room); name upthread")], "")
L["c0153"] = ([], "Mod notice.")
L["c0154"] = ([M("Ceres Pizza", named_in="title", food=-2, value=-2, exp=1, vc=True, first=None,
                 alt={"food": [-1], "value": [-1], "expensiveness": [2, None]},
                 why="'the overhyped overpriced crypto pizza and it wasn't good!'")], "")
L["c0155"] = ([M("Pop up bagels", "Pop Up Bagels", named_in="title", type="chain", food=-1, value=-1, vc=True,
                 alt={"food": [0], "value": [-2]}, conf="medium",
                 why="'Straight up. 80% normal bagel size too. They're not bad. But Tal is a million times better'"),
               M("Tal", "Tal Bagels", food=2, alt={"food": [3]}, terms=["bagels"], why="'a million times better'")], "")
L["c0156"] = ([M("Sweetgreen", also=("sourbrown",), type="chain", food=-2, neg_ok=True, alt={"food": [-1]},
                 why="'Slop indeed. I have been boycotting Sweetgreen aka SourBrown'"),
               M("Chipotle", named_in="parent", type="chain", food=-1, alt={"food": [-2]}, conf="medium",
                 why="'Slop indeed' agreeing with the parent's slop-bowl list"),
               M("Cava", named_in="parent", type="chain", food=-1, alt={"food": [-2]}, conf="medium", why="same")], "")
L["c0157"] = ([], "Budget advice, no place.")
L["c0158"] = ([], "Joke about German tourists; taqueria unnamed.")
L["c0159"] = ([], "'the one on 46th and 6th' is an unnamed cart.")
L["c0160"] = ([], "Asks where to go; Tomi Jazz not judged.")
L["c0161"] = ([M("Danny and Coop", "Danny & Coop's", named_in="ancestor", food=2, amb=True, conf="low",
                 why="'Damn if it aint delicious though' — 'it' is either Fedoroff's (just defended) or the Danny & Coop's/Mama's style")],
              "Two readings of 'it'.")
L["c0162"] = ([M("Babbo", named_in="ancestor", food=-1, neg=True, alt={"food": [-2, -3, None]}, rc=False, rt=True,
                 why="'Definitely skip it.' about Babbo, named upthread"),
               M("I Sodi", food=1, alt={"food": [2]}, why="'But don't skip I Sodi'")], "")
L["c0163"] = ([M("Chateau Royale", named_in="title", service=-3, food=1, neg=True, neg_ok=True,
                 alt={"service": [-2], "food": [2, 0]}, dishes=[("artichoke", -3, False)],
                 why="'Went once. Will never go back. Go to Chez Fifi instead.' review: 'decent food but be treated like shit'; inedible artichoke"),
               M("Chez Fifi", food=1, why="'Go to Chez Fifi instead'")], "")
L["c0164"] = ([
    M("Royal Grill", type="food_truck", food=0, alt={"food": [1, -1]}, terms=["halal", "punch card"],
      why="'I like both... their food can be a bit inconsistent'"),
    M("Kwik", "Kwik Meal", also=("kwik meal",), type="food_truck", food=2, terms=["halal", "tzatziki", "spicy green sauce"],
      why="'It's great but it may not be what you're looking for'"),
    M("ADel's", "Adel's Famous Halal Food", also=("adels",), type="food_truck", food=2, wait=-2, alt={"food": [1], "wait": [-3]},
      dishes=[("hot sauce", 2, False)], terms=["halal"],
      why="'not worth waiting an hour+ on line... It is good though... better hot sauce'"),
    M("Biryani Cart", type="food_truck", food=1, alt={"food": [2]}, dishes=[("kati roll", 2, False)], terms=["kati roll", "biryani"],
      why="'solid and also do a pretty tasty kati roll selection'"),
], "")
L["c0165"] = ([M(r, c, food=1, why="ranked list answer ('in that order')")
               for r, c in [("Apollo", "Apollo Bagels"), ("Liberty", "Liberty Bagels"), ("Ess-a", "Ess-a-Bagel"),
                            ("Leos", "Leo's Bagels")]], "")
L["c0166"] = ([M("Carlos grocery", "Carlo's Grocery", food=1, hood="Brooklyn, Ave I", terms=["italian sandwich"],
                 why="answer to best Italian sandwich")], "Italian sandwich deli, in scope.")
L["c0167"] = ([
    M("Russ and Daughters", "Russ & Daughters", food=1, dishes=[("bagel and lox", 1, False)], terms=["bagel and lox"], why="listed"),
    M("Barney Greengrass", food=1, terms=["bagel and lox"], why="listed"),
    M("Murray's Sturgeon", food=1, terms=["bagel and lox"], why="listed"),
    M("Keen's", "Keens Steakhouse", also=("keens",), food=2, terms=["steak", "oldskool steakhouse"], why="'they're all great'"),
    M("Peter Luger", food=2, terms=["steak", "cash only"], desc=["cash only"], why="'they're all great'"),
    M("Gage & Tollner", food=2, terms=["steak"], why="'they're all great'"),
    M("Flor de Mayo", food=2, hood="UWS", dishes=[("roast chicken", 2, False)],
      terms=["peruvian-chinese", "chino latino", "roast chicken"], why="'My personal local fav... their killer roast chicken'"),
    M("La Victoria", food=1, terms=["chino latino"], why="listed option"),
    M("La Dinastia", food=1, terms=["chino latino"], why="listed option"),
    M("La Caridad", food=1, terms=["chino latino"], why="listed option"),
    M("El Malecon", food=2, terms=["dominican"], why="'straight-up excellent Dominican'"),
    M("Mis Mamie's Spoonbread", "Miss Mamie's Spoonbread Too", food=2, alt={"food": [3]}, hood="110th St",
      dishes=[("fried chicken", 2, False), ("sides", 2, False)], terms=["soul food", "fried chicken"],
      why="'Incredible fried chicken and sides'"),
    M("Amy Ruth's", alt={"food": [1]}, terms=["soul food"], first=None, why="'the famous ones are...': reference"),
    M("Sylvia's", alt={"food": [1]}, terms=["soul food"], first=None, why="reference"),
    M("Red Rooster", alt={"food": [1]}, terms=["soul food"], first=None, why="reference"),
    M("4 Charles", "4 Charles Prime Rib", first=False, why="'if you can't get a res at 4 Charles': reference"),
], "Long tourist guide.")
L["c0168"] = ([], "Generic advice.")
L["c0169"] = ([M("booby trap", "Booby Trap", type="bar", terms=["dive bar"],
                 why="'simply a dive bar... not necessarily a recommendation': reference"),
               M("lucky charlie", "Lucky Charlie", named_in="comment", first=None, why="reference: 'after lucky charlie'")], "")
L["c0170"] = ([M("Mitsitam Native Foods Cafe", named_in="parent", oos=True, why="in Washington DC: out of scope")], "")
L["c0171"] = ([M("Uncle Lou", named_in="title", value=1, alt={"value": [None]}, desc=["cash discount"],
                 why="'They do offer a 9% cash discount' answering 'more expensive'")], "")
L["c0172"] = ([], "Generic dessert idea.")
L["c0173"] = ([M("Nabhya", named_in="ancestor", atmosphere=-2, food=-1, alt={"atmosphere": [-1], "food": [None]},
                 first=None, rc=False, rt=True,
                 why="'Blue is the worst color lighting'; 'edible orchids... make the food look cheap'")], "")
L["c0174"] = ([M("Son Del North", named_in="title", food=-1, alt={"food": [-2]}, first=None,
                 why="'Extremely overrated once again. Don't understand all the hype'")], "")
L["c0175"] = ([M("Sammy's", "Sammy's Halal", type="food_truck", alt={"food": [1]}, terms=["halal"],
                 why="'Back in the days (early 2000s) it was Sammy's': past reference")], "")
