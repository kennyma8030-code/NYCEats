"""Batch 13: c0326-c0350."""
from common import M

L = {}
L["c0326"] = ([], "An unnamed omakase years ago.")
L["c0327"] = ([], "")
L["c0328"] = ([], "BBQ consistency in general.")
L["c0329"] = ([M("Essens", "Essen", also=("essens",), type="chain", closed=True,
                 why="'used to make a good one, but I think they're all gone now'")], "")
L["c0330"] = ([], "Unnamed pizza place.")
L["c0331"] = ([M("Kossars", "Kossar's Bagels & Bialys", also=("kossars",), named_in="title", value=-3, exp=2, vc=True, first=None,
                 alt={"value": [-2], "expensiveness": [1]}, why="'$20.00. Without consience. No way.'"),
               M("Joe and the Juice", "Joe & The Juice", type="chain", value=-2, exp=2, vc=True, alt={"expensiveness": [1]},
                 dishes=[("smoothie", None, False)], why="'$12.00 smoothie I encountered at Joe and the Juice'")], "")
L["c0332"] = ([M("Sunn’s", "Sunn's", also=("sunns",), named_in="comment", food=2, value=-1, exp=2, vc=True,
                 alt={"value": [-2], "expensiveness": [1]}, dishes=[("banchan", 1, False)],
                 terms=["korean", "banchan", "wine list", "trendy"],
                 why="'they charge $25 for the banchan... The wine list and the other food is fantastic but priced for a trendy spot'")], "")
L["c0333"] = ([M("Kabawa", named_in="title", food=2, alt={"food": [3]}, terms=["prix-fixe", "caribbean"],
                 why="'Kinda weird they only do prix-fixe... but still a superb restaurant'")], "")
L["c0334"] = ([M("Hungry Spicy", named_in="parent", food=-1, terms=["spicy", "thai spicy"],
                 why="'This is the right answer. It's not very tasty IMO but if you want to challenge yourself with spice'")], "")
L["c0335"] = ([M("2 Bros", "2 Bros Pizza", named_in="title", type="chain", amb=True, alt={"value": [-1]},
                 why="'Recession indicator' about the $2 slice; nameless, no direct judgment")], "")
L["c0336"] = ([], "")
L["c0337"] = ([M("Old John's Luncheonette", food=1, why="answer near Lincoln Center")], "")
L["c0338"] = ([M("queen's night market", "Queens Night Market", type="food_hall", first=False,
                 why="'I might go to one after the other': reference")], "")
L["c0339"] = ([M("Elder", named_in="title", food=-1, atmosphere=1, first=False, why="'Interiors look decent food looks mid'")], "")
L["c0340"] = ([], "")
L["c0341"] = ([M("palm", "The Palm", named_in="parent", food=1, alt={"food": [2]}, dishes=[("chicken parm", 2, False)],
                 terms=["chicken parm"], why="'I haven't had their parm in years.....but I remember it being very good'")], "")
L["c0342"] = ([], "Asks for wings; no place.")
L["c0343"] = ([M("lakotafrybreadco", "Lakota Frybread Co", named_in="selftext", type="stall_vendor", amb=True, first=False,
                 rc=False, alt={"food": [1]}, why="'This is so cool, can't wait to try' — nameless enthusiasm")], "")
L["c0344"] = ([M("Fu Zhou Wei Zhong Wei Jia Xiang Feng Wei", named_in="selftext", food=3, dishes=[("dumplings", 3, False)],
                 terms=["dumplings"], why="'Yes - these dumplings are best in the city'")], "")
L["c0345"] = ([M("Brooklyn DOP", named_in="title", food=3, service=2, wait=1, alt={"wait": [None]},
                 dishes=[("slice", 3, False)], terms=["pizza", "slice", "san marzano"],
                 why="'Stellar pizza... service was lovely, did not take forever... best slice I've had in years'")], "")
L["c0346"] = ([], "")
L["c0347"] = ([M("fish cheeks", "Fish Cheeks", food=-1, why="'Had such a mid experience at fish cheeks'")], "")
L["c0348"] = ([M("Bar Bete", named_in="parent", food=2, amb=True, conf="low", alt={"food": [None]},
                 dishes=[("yellow cake with chocolate frosting", 2, False)],
                 why="'I'm constantly searching for a recipe for this cake' — 'this cake' may be Bar Bete's or the cake in general")], "")
L["c0349"] = ([], "DJs in cafes in general.")
L["c0350"] = ([], "")
