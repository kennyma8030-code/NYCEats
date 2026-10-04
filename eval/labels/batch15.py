"""Batch 15: c0376-c0395."""
from common import M

L = {}
L["c0376"] = ([], "OP on 311 response times; no new opinion.")
L["c0377"] = ([M("corner store", "The Corner Store", wait=-2, first=False, alt={"wait": [-1], "food": [-1]},
                 why="'huge crowd standing outside 2 hours before it opened... what could they possibly be serving that's that good?'")], "")
L["c0378"] = ([M("Shukette", food=1, why="picked over Zou Zou's"),
               M("Zou Zou", "Zou Zou's", named_in="title", atmosphere=-1, first=None, alt={"atmosphere": [None]},
                 why="'isn't the other one in Hudson Yards? Corporate city.'"),
               M("Zaytina", "Zaytinya", also=("zaytina",), food=1, why="'Zaytina is a solid option as well'")], "")
L["c0379"] = ([], "Review-removal logistics.")
L["c0380"] = ([M("Matto", "Matto Espresso", type="chain", alt={"food": [1]}, first=None, terms=["banana coffee drink"],
                 why="'I think Matto has a banana-related coffee drink': tentative answer")], "")
L["c0381"] = ([M("Hometown", "Hometown Bar-B-Que", food=-1, alt={"food": [-2], "value": [-2]}, first=None, terms=["bbq"],
                 why="'Hometown can't hold a candle to… Salt Lick or even Rudy's'; 'NYC BBQ is laughably overpriced' (general)"),
               M("Salt Lick", oos=True, why="Texas"), M("Rudy's BBQ", oos=True, why="Texas chain")], "")
L["c0382"] = ([], "Argues about low-effort posts.")
L["c0383"] = ([M("Kabawa", named_in="title", food=1, alt={"food": [2, None]}, rc=True, rt=True,
                 why="'Yeah pretty much the case' (every menu item sounds good); order what you're feeling")], "")
L["c0384"] = ([M("Mangia", type="chain", food=3, dishes=[("french toast", 3, False)],
                 terms=["french toast", "brunch", "self-serve", "catering"],
                 why="'the best French toast I've ever had... Everything there is genuinely delicious'")], "")
L["c0385"] = ([M("Semma", food=-1, alt={"food": [0]}, dishes=[("dosa", 2, False)], terms=["dosa", "indian"],
                 why="'I agree with you on Semma' (overhyped); 'The dosa was amazing... Other dishes lacked the depth'")], "")
L["c0386"] = ([M("Elea", food=1, alt={"food": [2]}, first=False, hood="UWS", terms=["greek"],
                 why="'I have not been, but heard Elea on the UWS is great'")], "")
L["c0387"] = ([], "")
L["c0388"] = ([], "Bagel shops in general.")
L["c0389"] = ([], "AutoModerator.")
L["c0390"] = ([M("Manu's Dabeli Station", named_in="title", type="food_truck", food=1, first=False, alt={"food": [None]},
                 terms=["spicy", "dabeli"], why="'How spicy is that? Looks tasty'")], "")
L["c0391"] = ([M("lucy's", "Lucy's", named_in="title", food=1, alt={"food": [2]},
                 dishes=[("pork cheese broccoli rabe long hots combo", 2, False)], terms=["broccoli rabe", "long hots", "braciole"],
                 why="'they should make this combo... its own named menu item'")], "")
L["c0392"] = ([M("Lady Wong", type="cafe_bakery_dessert", food=2, alt={"food": [3]}, why="'Hands down Lady Wong'")], "")
L["c0393"] = ([], "")
L["c0394"] = ([M("Nam Son", food=0, exp=-1, alt={"food": [-1, 1]}, hood="Chinatown", terms=["cheap", "pho"],
                 why="'If you want something cheap... like Nam Son, it's not the best but it'll do'")], "")
L["c0395"] = ([M("Red Hook Tavern", named_in="parent", food=3, dishes=[("burger", 3, False)], terms=["burger"],
                 why="'the best burger I have ever eaten it is perfect'")], "")
