"""Batch 7: c0176-c0200."""
from common import M

L = {}
L["c0176"] = ([M("Mongolian Momo King", hood="Park and 54th", first=None, terms=["mongolian"],
                 why="'The only Mongolian food... Maybe they know how to find it': reference")],
              "Colombian grocery stores are generic.")
L["c0177"] = ([M("02 Hot Stone BBQ House", food=0, alt={"food": [1]},
                 dishes=[("seafood pancake", 0, False), ("sauce", -1, False), ("kimchi", -1, False)],
                 terms=["korean seafood pancake"],
                 why="'Pretty good crisp... big pieces of shrimp... but some gluggy bits... sweeter sauce I did not prefer'")], "")
L["c0178"] = ([M("5iron golf", "Five Iron Golf", named_in="title", type="bar", amb=True, first=None,
                 why="accuses the post of spam; no opinion on the place itself")], "")
L["c0179"] = ([], "Cuisine classification argument.")
L["c0180"] = ([], "Grade-display rules in general.")
L["c0181"] = ([M("Angel", "Angel Indian Restaurant", also=("angel",), named_in="parent", food=3, alt={"food": [2]},
                 hood="Jackson Heights", terms=["indian"],
                 why="'+1 to this, haven't found anywhere else that comes close in Queens'")], "")
L["c0182"] = ([M("L'industrie", "L'Industrie Pizzeria", also=("lindustrie",), named_in="ancestor", wait=1,
                 alt={"wait": [None]}, rc=False, rt=False,
                 why="'went when it was raining and there was NO line' (tip); name only upthread outside both inputs")], "")
L["c0183"] = ([], "Unnamed places.")
L["c0184"] = ([M("The Corner Store", named_in="title", food=-1, wait=-1, neg=True, neg_ok=True, alt={"wait": [-2]},
                 first=None, why="'not that great and definitely not worth the long line + reservation hassle'")], "")
L["c0185"] = ([M("Edward's", named_in="title", food=-1, neg_ok=True, alt={"food": [None]}, conf="low", first=None,
                 why="'They aren't making it in store' — implies it's just canned Skyline"),
               M("Skyline", "Skyline Chili", named_in="title", type="chain", oos=True, why="Cincinnati chain / canned product")], "")
L["c0186"] = ([M("Hmart", "H Mart", type="grocery_market", oos=True, hood="bayside", why="retail")], "")
L["c0187"] = ([M("Nepali Bhancha Ghar", food=2, hood="Jackson Heights", terms=["nepali"], why="'probably my favorite'"),
               *[M(n, food=1, hood="Jackson Heights", terms=["nepali"], why="listed")
                 for n in ["Lali Guras", "Himalayan Yak", "Lakeside", "Ghorkali", "Tawa", "Aama Kitchen", "Woodside Cafe"]]], "")
L["c0188"] = ([M("Abuqir", named_in="parent", amb=True, first=False, why="'I'll put it on my to-try list' — nameless, no opinion"),
               M("Hamido", named_in="parent", amb=True, first=False, why="same")], "")
L["c0189"] = ([M("2bros", "2 Bros Pizza", also=("2bros", "2 bros"), type="chain", food=1, dishes=[("dollar slice", 1, False)],
                 terms=["dollar slice"], why="'2bros dollar slice is still pretty decent'")], "")
L["c0190"] = ([M("Wu's Wonton", "Wu's Wonton King", named_in="title", amb=True, why="posts an Instagram link; nameless, no opinion")], "")
L["c0191"] = ([], "Agrees about a dish distinction; no place judged.")
L["c0192"] = ([M("Soothr", food=-1, why="'personally not a huge fan'"),
               M("When in Bangkok", food=2, alt={"food": [3]}, hood="Flushing", terms=["thai"],
                 why="'blows it out of the water'")], "")
L["c0193"] = ([M("Jacobs Pickles", "Jacob's Pickles", named_in="title", food=-3, atmosphere=-2, neg_ok=True,
                 alt={"atmosphere": [-1]}, dishes=[("cornbread", -2, False)], terms=["cornbread"],
                 why="'food was terrible, bordering on disgusting... cornbread was a literal brick... we will never go back'")], "")
L["c0194"] = ([M("Tomi's", "Tomi Jazz", named_in="title", type="bar", wait=-2, neg=True, neg_ok=True, alt={"wait": [-3]},
                 terms=["jazz"], why="'constant barrage of tourists just waiting... totally not worth it'"),
               *[M(r, c, type="bar", food=1, alt={"food": [None]}, terms=["jazz"], why="offered as jazz alternatives")
                 for r, c in [("Ginny’s", "Ginny's Supper Club"), ("Bill's supper club", "Bill's Supper Club"),
                              ("birdland", "Birdland"), ("iridium", "Iridium")]]], "")
L["c0195"] = ([M("LA Sweets", food=2, alt={"food": [3]}, hood="Harlem, 125th", type="cafe_bakery_dessert",
                 dishes=[("cake", 2, False)], terms=["cake"], why="'has excellent cake... never disappoints'"),
               M("Magnolia", "Magnolia Bakery", type="chain", food=-2, alt={"food": [-3]}, why="'Magnolia is trash'"),
               M("Mia’s", "Mia's Bakery", type="cafe_bakery_dessert", food=-1, why="'Mia's is meh'")], "")
L["c0196"] = ([M("h mart", "H Mart", type="grocery_market", oos=True, why="retail")], "")
L["c0197"] = ([M(r, c, food=1, why="'Other recs' list")
               for r, c in [("Hyderabadi Zaiqa", None), ("Uncle Ray’s Chicken Rice", "Uncle Ray's Chicken Rice"),
                            ("Ariana Afghan Kebab", None), ("Toribro", None), ("Lum Lum", None),
                            ("Jerk House Caribbean Restaurant", None)]],
              "'The fries stuck to the cheeseburger' comments on the post photo (Lovely's or Cubby's, unclear); not labeled.")
L["c0198"] = ([M("Soothr", named_in="ancestor", amb=True, first=False,
                 why="'That is what I was afraid of' re Soothr's spice; nameless, no own opinion")], "")
L["c0199"] = ([], "Unnamed tamale vendor.")
L["c0200"] = ([], "")
