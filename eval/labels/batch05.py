"""Batch 5: c0126-c0150."""
from common import M

L = {}
L["c0126"] = ([M("Zabar's", "Zabar's Cafe", also=("zabars",), named_in="comment", type="cafe_bakery_dessert", oos=True,
                 alt={"food": [2]}, why="name correction for their own Zabar's cafe froyo rec; 'zabars' is a production excluded entity")], "")
L["c0127"] = ([
    M("Jolibee", "Jollibee", type="chain", food=1, terms=["filipino fast food"], why="list answer"),
    M("Chatti", food=1, why="list answer"),
    M("Go Go Curry", type="chain", food=1, terms=["japanese curry"], why="'the rare Japanese style curry place'"),
    M("El Sabroso", food=1, terms=["ecuadorian"], why="list answer"),
    M("Bluestone Lane", type="chain", food=1, why="list answer"),
    M("Gyu Kaku", "Gyu-Kaku", type="chain", food=2, alt={"food": [1]}, terms=["sit down", "group"],
      why="'one of my sit down restaurant go to's in this area'"),
    M("Smashburger", type="chain", food=2, terms=["burger"], why="'super underrated burger chain'"),
    M("Sky Pavilion", food=1, terms=["sichuan"], why="list answer"),
    M("NY pizza suprema", "NY Pizza Suprema", food=1, why="list answer"),
    M("PENN 1 food hall", "Penn 1 Food Hall", type="food_hall", food=1, alt={"food": [None]}, why="list answer"),
    M("pollo campero", "Pollo Campero", type="chain", alt={"food": [1]}, why="'has a pollo campero... in it': reference"),
    M("blue bottle", "Blue Bottle Coffee", type="chain", alt={"food": [1]}, why="reference inside Penn 1"),
    M("H&H", "H&H Bagels", type="cafe_bakery_dessert", alt={"food": [1]}, why="reference inside Penn 1"),
    M("Zaro’s", "Zaro's Family Bakery", type="chain", alt={"food": [1]}, why="reference inside Penn 1"),
], "")
L["c0128"] = ([M("Burgers and tacos", amb=True, conf="low", food=1, hood="Lexington Avenue and 80th St",
                 why="could be a place literally named 'Burgers and Tacos' or a description of an unnamed spot")], "")
L["c0129"] = ([], "")
L["c0130"] = ([M("Brennan and Carr", "Brennan & Carr", food=1, dishes=[("burger", 1, False)], terms=["cheese"],
                 why="'They'll douse it in cheese too'")], "")
L["c0131"] = ([M("Daily Provisions", type="chain", food=1, terms=["quick bite"],
                 why="'just a solid place for a quick bite'")], "")
L["c0132"] = ([M("los tacos", "Los Tacos No. 1", also=("los tacos 1",), type="food_truck", dishes=["breakfast burrito"],
                 terms=["breakfast burrito", "cart"], why="confirms the breakfast-burrito cart's hours and cards: informational")], "")
L["c0133"] = ([M("keens", "Keens Steakhouse", service=-3, food=-1, exp=3, neg_ok=True,
                 alt={"food": [-2], "service": [-2], "expensiveness": [2]}, dishes=[("steak", -2, False)], terms=["steak"],
                 why="'The staff treated us like shit... rude comments... a terrible experience'; cold steak; $400")], "")
L["c0134"] = ([M("Banh Anh Em", food=2, wait=-1, alt={"wait": [-2]}, dishes=[("banh mi", 2, False)], terms=["banh mi", "takeout"],
                 why="'lives up to the hype'; 'order for takeout and avoid a crazy wait'")], "")
L["c0135"] = ([M("Penny", named_in="parent", food=2, alt={"food": [3]}, dishes=[("confit oysters", 2, False)],
                 terms=["confit oysters"], why="'So. Dang. Good.'")], "")
L["c0136"] = ([M("Economy candy", "Economy Candy", type="grocery_market", oos=True, why="retail candy store"),
               M("fairway", "Fairway", type="grocery_market", oos=True, why="retail"),
               M("Sonnyboy", food=2, dishes=[("kangaroo burger", 2, False), ("chicken parmy", 2, False)],
                 terms=["australian", "kangaroo burger", "chicken parmy"], why="'has a good kangaroo burger and chicken parmy'")], "")
L["c0137"] = ([M(r, c, food=1, hood=h, why="list answer")
               for r, c, h in [("sailor", "Sailor", "Brooklyn"), ("gator", "Gator", "Brooklyn"), ("harts", "Hart's", "Brooklyn"),
                               ("third falcon", "Third Falcon", "Brooklyn"), ("Opto", None, "Manhattan"),
                               ("American bar", "American Bar", "Manhattan"), ("monkey bar", "Monkey Bar", "Manhattan"),
                               ("Zimmis", "Zimmi's", "Manhattan"), ("little maven", "Little Maven", "Manhattan")]], "")
L["c0138"] = ([M("Chick-Fil-A", "Chick-fil-A", type="chain", service=2, hood="Times Square",
                 why="cashier gave samples of every sauce: kind service")], "")
L["c0139"] = ([M("Hani's", "Hani's Bakery", named_in="parent", type="cafe_bakery_dessert", food=2, alt={"food": [3]},
                 dishes=[("honey cake", 2, False)], terms=["honey cake"], why="'that honey cake is sooooo good... slaps so hard'")], "")
L["c0140"] = ([], "'Dont eat there' = Times Square as an area.")
L["c0141"] = ([M("Mermaid Inn", named_in="parent", food=2, alt={"food": [3]}, rc=True, rt=False,
                 why="'This place is amazing'; parent not in the thread chunk")], "")
L["c0142"] = ([M("Lucali", named_in="ancestor", wait=-2, first=False, neg_ok=True, alt={"wait": [-1]}, rc=False, rt=True,
                 why="'I don't have the time for that gimmick... won't play into their ploy. Lines are for suckers.'")], "")
L["c0143"] = ([], "AI menus in general.")
L["c0144"] = ([M("P.J. Clarke’s", "P.J. Clarke's", named_in="title", food=1, alt={"food": [0, None]},
                 why="'Worth it from Long Beach - not worth it from Montauk': moderately worth it")], "")
L["c0145"] = ([M("Cote", named_in="parent", atmosphere=1, service=1, alt={"atmosphere": [0], "service": [None]},
                 dishes=["butcher's feast"], terms=["butcher's feast", "late night", "midnight"],
                 why="'It wasn't rushed at all... at midnight a much calmer feel' vs loud at 7pm")], "")
L["c0146"] = ([M("7/11", "7-Eleven", type="grocery_market", oos=True, why="convenience store")], "")
L["c0147"] = ([M("crown shy", "Crown Shy", named_in="ancestor", food=2, value=1, alt={"value": [2]},
                 dishes=[("gruyère fritters", 0, False), ("ora king salmon", None, False), ("spicy tuna", 2, False),
                         ("beef kibbeh", 2, False), ("grilled marinated chicken", -1, False), ("pork katsu", 2, False),
                         ("sticky toffee pudding", 2, False), ("gnocchi", 2, False), ("wine flight", 2, False)],
                 terms=["pork katsu", "sticky toffee pudding", "wine flight", "cocktails"],
                 why="dish-by-dish; 'Great food and cocktails, and pretty good bang for your buck'")], "")
L["c0148"] = ([M("katz deli", "Katz's Delicatessen", named_in="title", amb=True, first=False,
                 why="suggests changing Katz's ticket system; no opinion of the place")], "")
L["c0149"] = ([], "Vague complaint, no place.")
L["c0150"] = ([], "")
