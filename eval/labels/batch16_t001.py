"""Thread t001 (t3_1us3txb): Pressed Juicery closing. Every comment labeled."""
from common import M

T = "t001/"


def P(raw="Pressed", named_in="title", **kw):
    return M(raw, "Pressed Juicery", also=("pressed", "pressed juicery", "pj"), named_in=named_in, type="chain", **kw)


L = {}
NONE = ["t1_owksvvi", "t1_owlb7yv", "t1_owln6y9", "t1_owlxohd", "t1_owlyrkr", "t1_owm2qt2", "t1_owm5nx5",
        "t1_owmbvpo", "t1_owmfxmy", "t1_owml8r9", "t1_owmlh53", "t1_owmob1x", "t1_owmphip", "t1_owmvykk",
        "t1_own36s3", "t1_own8acf", "t1_ownuojk", "t1_owu41bl", "t1_ox6u9r5", "t1_owm349b", "t1_owp7pum",
        "t1_owlhmv1", "t1_owlz6cg", "t1_owobmqu", "t1_owv75vo", "t1_owv9t77", "t1_owvtc6s", "t1_ox5h50u",
        "t1_owozz25", "t1_owzr573", "t1_owp4j06", "t1_owx1azt", "t1_owsdb8z", "t1_owtdezk", "t1_ox41sx2",
        "t1_oxci02s"]
for cid in NONE:
    L[T + cid] = ([], "Vegan/protein/juice-economics talk or location questions; no place judged or named.")

L[T + "t1_owkutga"] = ([P(food=1, alt={"food": [None]}, dishes=[("vegan soft serve", 1, False)], terms=["vegan soft serve"],
                          why="'I care more about their vegan soft serve'")], "")
L[T + "t1_owlw11x"] = ([P(food=1, alt={"food": [2]}, dishes=[("freezes", 1, False)], terms=["freezes"],
                          why="'I enjoy the taste of their freezes'")], "")
L[T + "t1_owma05g"] = ([M("McDonalds", "McDonald's", type="chain", food=-2, alt={"food": [-1]}, first=None,
                          dishes=[("nuggets", -2, False)], why="'the nugget-shaped pink slime McDonalds sells'")], "")
L[T + "t1_owmaom5"] = ([M("McNuggets", "McDonald's", also=("mcdonalds",), named_in="parent", type="chain", food=1,
                          alt={"food": [2, 0]}, dishes=[("mcnuggets", 2, False)], conf="medium",
                          why="'McNuggets with their honey is bomb. Its far from chicken though'")], "")
L[T + "t1_owkw9rr"] = ([P(food=-2, first=None, why="'Pressed sucks if we are being honest'")], "")
L[T + "t1_owlz2bg"] = ([P(named_in="parent", value=-2, exp=1, vc=True, alt={"expensiveness": [None, 2]}, first=None,
                          why="'Its overpriced produce in liquid form.'")], "")
L[T + "t1_owl1bu4"] = ([P(food=1, alt={"food": [2]}, terms=["healthy", "on-the-go"],
                          why="'I enjoyed Pressed for a healthy on-the-go option'")], "")
L[T + "t1_owl51n5"] = ([P(food=-1, alt={"food": [-2]}, dishes=[("freezes", -1, False)], terms=["freezes"],
                          why="'used to love their freezes... ingredients had completely changed... cut corners'")], "")
L[T + "t1_owl6tyt"] = ([P(food=2, dishes=[("vanilla freeze", 2, False)], terms=["freeze", "vanilla"],
                          why="'changed their vanilla flavor and it's sooo good this time'")], "")
L[T + "t1_owl7op2"] = ([P(food=1, alt={"food": [None]}, dishes=[("vegan soft serve", 1, False)], terms=["vegan soft serve"],
                          why="'RIP to their vegan soft serve!'")], "")
L[T + "t1_owlc9ce"] = ([P(value=2, service=-2, neg_ok=True, alt={"service": [-3]}, terms=["vip membership"],
                          why="'quality/price... you cant beat them with the VIP membership'; '42nd st food hall' pickup 'a disaster'; canceled")], "")
L[T + "t1_owlz7zx"] = ([P(named_in="parent", amb=True, why="'Had to scroll to find this one.' — agreeing with an unclear part of the parent")], "")
L[T + "t1_owtn36n"] = ([M("erewhon", "Erewhon", named_in="parent", oos=True, why="LA grocery; outside NYC / excluded")], "")
L[T + "t1_owpjzac"] = ([M("Juice Press", type="chain", first=None, why="lost its Equinox locations: reference"),
                        M("Earth bar", "Earthbar", type="chain", first=None, why="replacement vendor: reference")], "")
L[T + "t1_ox2u9mb"] = ([M("juice press", "Juice Press", type="chain", first=True, alt={"food": [None]},
                          why="'business was visibly dead'; 2-for-1 smoothie deals: reference")], "")
L[T + "t1_owq530y"] = ([M("starbucks", "Starbucks", type="chain", hood="aster place", first=None,
                          why="'the starbucks on aster place closed down cuz rent': reference (one location)")], "")
L[T + "t1_owsv3nx"] = ([P(food=-1, why="'I was never impressed with them'")], "")
L[T + "t1_owywwpe"] = ([P(raw="the pressed", named_in="comment", first=None,
                          why="'the pressed wasn't getting enough foot traffic': reference")], "")
L[T + "t1_oxfe4z8"] = ([P(raw="PJ", named_in="comment", why="'most accessible PJ for me... 4 locations left': reference")], "")
L[T + "t1_oxhflrb"] = ([P(food=-1, alt={"food": [None]}, dishes=[("vanilla freeze", -1, False)], terms=["freeze"],
                          why="'changed their freeze recipe for vanilla they added cashew... sucks'")], "")
L[T + "t1_oxhp4t5"] = ([P(amb=True, hood="Williamsburg", why="'the one in Williamsburg is closing its doors too' — nameless location news")], "")
L[T + "t1_oxitb7w"] = ([P(amb=True, why="'What??? Nooooo. I just went there last week!!!' — nameless")], "")
L[T + "t1_oxj6xbh"] = ([P(food=1, alt={"food": [2]}, dishes=[("ginger shots", 2, False)], terms=["ginger shots"],
                          why="'I loved their ginger shots :('")], "")
