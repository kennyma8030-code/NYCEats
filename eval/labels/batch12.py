"""Batch 12: c0301-c0325."""
from common import M

L = {}
L["c0301"] = ([M("Harlem Public", named_in="parent", food=2, dishes=[("loaded grilled cheese", 2, False)],
                 terms=["loaded grilled cheese"], why="'Their loaded grilled cheese is something else.'")], "")
L["c0302"] = ([M("LoveMama", food=-3, why="'the worst Asian food I've ever had'; alleges bribed ratings")], "")
L["c0303"] = ([], "Jack's Dining Room is an influencer; no place judged.")
L["c0304"] = ([], "Website bug report.")
L["c0305"] = ([M("Viniero's", "Veniero's", also=("vinieros",), type="cafe_bakery_dessert", food=1, terms=["delivery"],
                 why="named as the answer")], "")
L["c0306"] = ([], "Praises the rainbow-cookie project, not a place.")
L["c0307"] = ([], "Mod notice.")
L["c0308"] = ([M("L’Industrie", "L'Industrie Pizzeria", food=2, wait=-1, alt={"wait": [None]}, dishes=[("pizza", 2, False)],
                 terms=["pizza"], why="'Overhyped, sure, but... It's great pizza, dude, even if the line is long'")], "")
L["c0309"] = ([], "Mod notice.")
L["c0310"] = ([M("Don Angie", food=1, first=False, why="'seem like the obvious choice instead of Carbone'"),
               M("Via Carota", food=1, first=False, why="same"),
               M("Carbone", alt={"food": [-1]}, first=False, why="the option being dropped; not judged")], "")
L["c0311"] = ([], "Link only.")
L["c0312"] = ([M("Balthazar", named_in="ancestor", food=-1, first=False, alt={"food": [None]}, rc=False, rt=False,
                 why="'Sad to hear a place... had gone downhill' — past praise, current hearsay knock; name upthread outside both inputs")], "")
L["c0313"] = ([M("Pakistani Tea House", "Pakistan Tea House", named_in="comment", closed=True,
                 why="closed-restaurants thread: 'kept me happily & cheaply fed'"),
               M("Christy’s", "Christy's Jamaican Patties", closed=True, why="closed: 'their patties were so good'"),
               M("Hancos", "Hanco's", value=-1, vc=True, alt={"value": [None]}, dishes=["banh mi"], terms=["banh mi"], conf="medium",
                 why="'I miss the old Hancos and their prices... prices are at least twice that'")], "")
L["c0314"] = ([M("Molly’s", "Molly's Shebeen", named_in="parent", type="bar", food=1, alt={"food": [None, 2]},
                 why="'You be quiet now' — gatekeeping joke = endorsement")], "")
L["c0315"] = ([M("tacos el bronco", "Tacos El Bronco", named_in="parent", type="food_truck", alt={"food": [1]}, rc=True, rt=False,
                 why="'I gotta try their truck spot, I've only ever had at the restaurant'")], "")
L["c0316"] = ([M("The Black Hound", "Black Hound", closed=True, hood="Battery Park City South",
                 why="'closed with paper on the windows... completely gutted inside'")], "")
L["c0317"] = ([M("Ernesto’s", "Ernesto's", food=2, why="'Ernesto's for sure! That place is great.'")], "")
L["c0318"] = ([], "Elmhurst in general.")
L["c0319"] = ([M("Mias Brooklyn bakery", "Mia's Bakery", type="cafe_bakery_dessert", food=1,
                 dishes=[("half cheesecake half red velvet slice", None, False)], terms=["cheesecake", "red velvet"],
                 why="'might do it for you... half cheesecake and half red velvet'")], "")
L["c0320"] = ([M("Pranakhon", named_in="parent", food=2, why="'This spot and Mitr are way better than Soothr'"),
               M("Mitr", food=2, why="same"),
               M("Soothr", alt={"food": [-1]}, first=None, why="loses the comparison")], "")
L["c0321"] = ([M("Djon Djon", named_in="title", food=-2, first=False, neg_ok=True, alt={"food": [None, -3]}, conf="medium",
                 why="reported the kitchen to DOH based on OP's photos: hygiene complaint")], "")
L["c0322"] = ([M("Buenos Aires", named_in="ancestor", food=2, rc=False, rt=True, terms=["steakhouse", "casual"],
                 why="'not classic NYC steakhouse... super casual and high quality... for meat heads it's great'")], "")
L["c0323"] = ([M("barking dog", "Barking Dog", named_in="parent", amb=True, first=False, why="'Thanks! We will check it out!'")], "")
L["c0324"] = ([], "About David Chang the person.")
L["c0325"] = ([M("Strip house", "Strip House", named_in="parent", amb=True, hood="west village",
                 why="location correction only")], "")
