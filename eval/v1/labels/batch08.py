"""Batch 8: c0201-c0225."""
from common import M

L = {}
L["c0201"] = ([], "Housing remark; Ilis not judged.")
L["c0202"] = ([M("Hawksmoor", named_in="ancestor", amb=True,
                 why="'might now [visit] to judge for myself' — nameless, no opinion in this comment")], "")
L["c0203"] = ([M("David's", "David's Brisket House", named_in="parent", food=-3, neg_ok=True,
                 why="'We got sick from the food more than once. We haven't gone back. Used to be AMAZING.'")], "")
L["c0204"] = ([], "Melbourne vs NYC liveability.")
L["c0205"] = ([M("Super Burrito", named_in="comment", food=-2, value=-3, exp=2, vc=True, neg=True, neg_ok=True,
                 alt={"food": [-3], "value": [-2], "expensiveness": [1]}, hood="WV", dishes=[("burrito", -2, False)],
                 terms=["burrito"],
                 why="'It fucking sucks... extremely expensive... No one... should pay $20+ for that shitty ass burrito'"),
               M("Chipotle", type="chain", first=None, alt={"food": [1]}, why="'better burritos in NY (even Chipotle ffs)': backhanded reference")], "")
L["c0206"] = ([M("dunkin", "Dunkin'", type="chain", first=True, why="'I get dunkin or mcd if i want caffeine': reference"),
               M("mcd", "McDonald's", type="chain", why="same"),
               M("devocion", "Devoción", also=("devocion",), type="cafe_bakery_dessert", food=1, alt={"food": [2]},
                 terms=["coffee"], why="'even chains like devocion are just better'")], "")
L["c0207"] = ([M("Sho", "Sushi Sho", also=("sho",), wait=-2, exp=3, alt={"wait": [-1], "food": [2]}, first=None,
                 terms=["omakase", "sushi"],
                 why="'Extremely hard to get a reservation... Cost somewhere $300-$400... similar to Yoshino and Sho'"),
               M("Yoshino", alt={"food": [2]}, first=True, terms=["omakase"], why="compared to top Tokyo omakase")], "")
L["c0208"] = ([], "Generic dining-hours advice.")
L["c0209"] = ([M("Traif", named_in="parent", amb=True, first=False, why="'it's on my list' — nameless question, no opinion")], "")
L["c0210"] = ([M("Best bagel & coffee", "Best Bagel & Coffee", food=1, alt={"food": [2]}, terms=["bagels", "freezer"],
                 why="'hold up well in the freezer!'")], "")
L["c0211"] = ([M("Soothr", named_in="ancestor", amb=True, why="'Interesting thank you! I will revisit' — nameless, no opinion")], "")
L["c0212"] = ([], "California produce.")
L["c0213"] = ([], "Unnamed takeout spot.")
L["c0214"] = ([M(r, c, named_in="selftext", amb=True, neg=True, why="'Just avoid all these spots tomorrow' — a crowd joke, not a judgment")
               for r, c in [("Mama’s TOO!", "Mama's Too"), ("Faicco’s", "Faicco's Italian Specialties"),
                            ("Porto Rico Importing Co.", "Porto Rico Importing"), ("Rocco’s Pastry Shop", "Rocco's Pastry Shop")]], "")
L["c0215"] = ([M("Eataly", type="food_hall", food=1, first=False, alt={"food": [None]},
                 why="'Pretty sure they have at Eataly. Haven't been for a min'")], "")
L["c0216"] = ([M("Shake Shack", named_in="ancestor", type="chain", amb=True, rc=False, rt=False,
                 why="'They don't use that blend any more??' — nameless reaction")], "")
L["c0217"] = ([M(r, c, food=1, terms=[], why="list of banh mi alternatives")
               for r, c in [("Ba Xuyen", "Bánh Mì Ba Xuyên"), ("Banh Mo Co Ut", "Bánh Mì Cô Út"),
                            ("Banh Mi Saigon", None), ("Saigon Vietnamese Deli", None)]], "")
L["c0218"] = ([M("gargiulos", "Gargiulo's", named_in="parent", atmosphere=1, alt={"atmosphere": [None], "food": [1]},
                 hood="Coney Island", terms=["old school", "red sauce"], rc=False, rt=True,
                 why="'they wanted old school. So it is that.' defending the Gargiulo's rec; name only in d0 URL")], "")
L["c0219"] = ([], "Unnamed farmers-market vendors.")
L["c0220"] = ([], "")
L["c0221"] = ([M("Momofuku Ssam Bar", named_in="ancestor", closed=True, amb=True,
                 why="'Thanks for the memories!' to the ex-chef; nameless, closed")], "")
L["c0222"] = ([M("Xing fu tang", "Xing Fu Tang", named_in="ancestor", amb=True, dishes=["brown sugar boba"],
                 terms=["brown sugar boba"], why="factual note on sugar levels; nameless")], "")
L["c0223"] = ([M("Rowdy Rooster", named_in="title", closed=True, dishes=["sandwiches"], terms=["spicy chicken sandwich"],
                 why="closed; recalls sandwiches 'too spicy... inedible' when it opened")],
              "Unapologetic Foods is a restaurant group, not labeled.")
L["c0224"] = ([], "Delivery apps.")
L["c0225"] = ([M("Penny", food=1, why="answer"), M("Wildair", food=1, why="answer")], "")
