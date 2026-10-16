"""Threads t012-t017. Every comment labeled."""
from common import M

L = {}
A = "t012/"
for cid in ["t1_ojzcs5d", "t1_ojzeatr", "t1_ojzeulj", "t1_ojzfzdw", "t1_ojzi91m", "t1_ojzge12", "t1_okmb4p6"]:
    L[A + cid] = ([], "Generic bars / home-mixing advice.")
L[A + "t1_ok0j332"] = ([M("La petit joie", "La Petite Joie", type="bar", food=1, why="'if you need a specific name'")], "")
L[A + "t1_ok1wi05"] = ([M("Maison Provence", hood="Williamsburg", food=1, why="answer")], "")

B = "t013/"
G = dict(type="grocery_market", oos=True)
for cid in ["t1_oh1f7re", "t1_oh1v770", "t1_oh30pt9", "t1_oh28ta4", "t1_oh2m5qm", "t1_oh36mnz", "t1_oh37te5", "t1_oh5tcgr",
            "t1_ohgk0rn"]:
    L[B + cid] = ([], "Prices, knife tips, generic grocers.")
for cid in ["t1_oh349n3", "t1_oh230gb", "t1_oh323nw", "t1_oh4osgk"]:
    L[B + cid] = ([M("Market Basket", **G, why="New England supermarket")], "")
L[B + "t1_oh27w07"] = ([M("Lidl", **G, why="supermarket")], "")
L[B + "t1_oh291ix"] = ([M("Zabars", "Zabar's", **G, why="grocery deli counter")], "")
L[B + "t1_oh3dsah"] = ([M("western beef", "Western Beef", **G, why="supermarket")], "")

C = "t014/"
for cid in ["t1_olbg6or", "t1_olbon02"]:
    L[C + cid] = ([], "No place.")
L[C + "t1_olbm9d1"] = ([M("Choice Brooklyn", "Choice Market", food=2, dishes=[("chicken salad sandwich", 2, False)],
                          terms=["chicken salad sandwich"], why="'I love the chicken salad sandwich from Choice Brooklyn'")], "")
L[C + "t1_olbw2fg"] = ([M("S&P lunch", "S&P", also=("s p lunch",), food=1, why="answer"),
                        M("Schaller and Weber", "Schaller & Weber", **G, why="butcher/grocery")], "")
L[C + "t1_oldcm9c"] = ([M("Poulet San Tete", "Poulet Sans Tête", also=("poulet sans tete",), food=3,
                          dishes=[("thanksgiving chicken gobbler sandwich", 3, False)], why="'is to die for'")], "")
L[C + "t1_olcgbgb"] = ([M("Daily Provisions", type="chain", food=1, why="answer")], "")
L[C + "t1_olcktdv"] = ([M("Utopia Bagel", "Utopia Bagels", food=1, dishes=[("country chicken salad", 1, False)],
                          terms=["chicken salad", "everything bagel"], why="answer with the order")], "")
L[C + "t1_olcp8f9"] = ([M("Utopia", "Utopia Bagels", food=2, dishes=[("country chicken salad", 2, False)],
                          why="'This is my go to order for Utopia'")], "")
L[C + "t1_olcu2zd"] = ([M("Utopia", "Utopia Bagels", named_in="ancestor", food=1, alt={"food": [2]},
                          dishes=[("egg salad with bacon", 1, False)], why="'I also enjoy the egg salad with bacon'")], "")
L[C + "t1_olcuujb"] = ([M("Utopia", "Utopia Bagels", food=1, alt={"food": [None]}, why="'Imma go to Utopia today... craving'")], "")
L[C + "t1_olcw9wi"] = ([M("Utopia", "Utopia Bagels", named_in="parent", food=1, alt={"food": [None]},
                          why="'I'm waiting for their new location to open by me'")], "")
L[C + "t1_olgbqfg"] = ([M("Utopia", "Utopia Bagels", named_in="parent", food=2, dishes=[("chicken salad", 2, False)],
                          why="'Damn was that good'")], "")
L[C + "t1_olcmr0w"] = ([M("Toasties", type="chain", food=2, dishes=[("chicken salad sandwich", 2, False)],
                          why="'Nothing fancy, but Toasties does a great chicken salad sandwich'")], "")
L[C + "t1_olcqrts"] = ([M("Rafettos", "Raffetto's", hood="Houston", **G, why="pasta/specialty retail shop; 'does a great one'")], "")
L[C + "t1_olcr1za"] = ([M("S&P", food=1, alt={"food": [2]}, why="'My pick would be S&P'")], "")
L[C + "t1_olcssr7"] = ([M("40 Carrots", food=2, alt={"food": [3]}, hood="Bloomingdales", dishes=[("sonoma chicken salad", 2, False)],
                          terms=["sonoma chicken salad", "cranberry walnut bread"], why="recommends with a trophy")], "")
L[C + "t1_oldge8t"] = ([M("Mangia", type="chain", food=2, why="'Mangia's is really good'")], "")
L[C + "t1_oldj5eb"] = ([M("Citarella", **G, why="grocery; curried chicken salad")], "")
L[C + "t1_olfe5mv"] = ([M("Pomegranate", **G, why="kosher supermarket"), M("everfresh", "Everfresh", **G, why="kosher grocery")], "")
L[C + "t1_olffk94"] = ([M("Winner", food=2, alt={"food": [3]}, hood="Park Slope", dishes=[("chicken salad sando", 2, False)],
                          why="'has an amazing chicken salad sando!'")], "")
L[C + "t1_olge6vu"] = ([M("Comfortland", food=1, why="answer"), M("spitfire provisions", "Spitfire Provisions", food=1, why="answer")], "")
L[C + "t1_olo4yxm"] = ([M("Foster Sundry", hood="Bushwick", **G, why="specialty grocery; smoked chicken salad")], "")
L[C + "t1_olo70ja"] = ([M("EJs", "EJ's Luncheonette", food=1, why="answer"), M("40 Carrots", hood="Bloomingdale’s", food=1, why="answer")], "")

D = "t015/"
L[D + "t1_nl09j1g"] = ([M("Tracks", type="bar", food=1, alt={"food": [None], "atmosphere": [-1]}, conf="medium",
                          why="'This. Tracks as long as it's not before/after a rangers or Knicks game' (parent missing)")], "")
L[D + "t1_nl0iekk"] = ([M("Jimmy's", "Jimmy's Corner", type="bar", amb=True, rc=False, rt=False, conf="low",
                          why="anecdote about 'Jimmy's seat'; parent missing")], "")
L[D + "t1_nl1nui2"] = ([], "'This place was sick as hell' — parent missing from the DB; referent unknown.")
L[D + "t1_nl21xm0"] = ([], "'truly a cathedral' — same unknown referent.")
L[D + "t1_nl035ov"] = ([M("Mr Biggs", type="bar", food=1, exp=-2, alt={"expensiveness": [-3]}, terms=["$4 shots", "cheap drinks"],
                          why="'$4 Shots/$4 Beers/$4 Drinks/ $5 margs'")], "")
L[D + "t1_nl03gou"] = ([M("District Local", type="bar", food=1, hood="14 and 7th", why="answer")], "")
L[D + "t1_nl0i8nt"] = ([M("Rudy’s", "Rudy's Bar & Grill", type="bar", amb=True, why="song-lyric joke naming Rudy's")], "")
L[D + "t1_nl1njov"] = ([], "Lyric joke.")
L[D + "t1_nl13un0"] = ([M("peter mc manus", "Peter McManus Cafe", type="bar", food=1, hood="7th and 18th", why="answer")], "")
L[D + "t1_nl1no67"] = ([M("Fanelli’s", "Fanelli Cafe", also=("fanellis",), type="bar", food=1, why="answer")], "")
L[D + "t1_nl4f0x5"] = ([M("Nothing Really Matters", type="bar", food=1, why="answer: on the 1 line")], "")
L[D + "t1_nl4zysc"] = ([M("Wakamba bar", "Wakamba", type="bar", food=2, hood="37th and 8th", why="'Gotta go wakamba.'")], "")

E = "t016/"
for cid in ["t1_orhm9e4", "t1_owfwxrp", "t1_orl5o81", "t1_owfxlof", "t1_owgwm3v"]:
    L[E + cid] = ([], "AutoMod / Weee delivery app talk.")
L[E + "t1_oriu0mi"] = ([M("Moc mac", "Moc Mac", hood="east village", food=1, dishes=["la lot"], terms=["la lot"], why="'does this'")], "")
L[E + "t1_orlc6qq"] = ([M("Tan Tin Hung Supermarket", **G, why="Vietnamese grocery")], "")
L[E + "t1_os7xlb1"] = ([M("Tan Tin Hung Supermarket", named_in="parent", **G, why="nameless; grocery")], "")
L[E + "t1_owfwvay"] = ([M("Tan Ting Hung", "Tan Tin Hung Supermarket", **G, why="grocery")], "Unnamed 'wagyu bo la lot' restaurant.")

F = "t017/"
for cid in ["t1_oon31k0", "t1_ooov81u", "t1_oonvqx1"]:
    L[F + cid] = ([], "Banter.")
L[F + "t1_oomo25u"] = ([M("Java", food=1, hood="Park Slope", terms=["indonesian"], why="answer")], "")
L[F + "t1_oomq531"] = ([M("Java", named_in="parent", food=-2, why="'we ordered delivery and it sucked'")], "")
L[F + "t1_oomuqgw"] = ([M("indo mix", "Indo Mix", food=1, hood="clinton hill", why="answer")], "")
L[F + "t1_oon6ugv"] = ([M("Taste good", "Taste Good", food=2, hood="east elmhurst", why="'it's so good'")], "")
L[F + "t1_ooni9fm"] = ([M("Little House Restoran", food=1, hood="Brooklyn", dishes=["mie goreng"], why="'You can find it at...'")], "")
L[F + "t1_oooau1k"] = ([M("Hainan chicken house", "Hainan Chicken House", food=1, why="answer")], "")
L[F + "t1_ooomg70"] = ([M("Indonesian bazaar at Masjid al-Hikmah", type="food_hall", food=1, alt={"food": [2]}, hood="Astoria",
                          terms=["indonesian", "bazaar"], why="'definitely worthwhile even if you don't find your specific dish'")], "")
L[F + "t1_op0hl57"] = ([M("Indonesian bazaar at Masjid al-Hikmah", named_in="parent", type="food_hall", amb=True, first=False,
                          why="'Great rec!!' — nameless thanks")], "")
