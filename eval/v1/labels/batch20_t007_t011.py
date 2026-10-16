"""Threads t007-t011. Every comment labeled."""
from common import M

L = {}
A = "t007/"


def S(**kw):
    kw.setdefault("named_in", "title")
    return M("Sofreh", **kw)


L[A + "t1_omfwqb1"] = ([S(food=2, dishes=[(d, 2, False) for d in ["tahini and date salad", "cauliflower", "eggplant dip", "squash",
                                                                   "pomegranate beef", "half chicken", "desserts"]],
                         terms=["date salad", "eggplant dip", "pomegranate beef"], why="'...desserts are all great'")], "")
L[A + "t1_omg1q43"] = ([S(food=1, alt={"food": [None]}, terms=["herbs"], why="'Anything that highlights frag herbs'")], "")
L[A + "t1_omhbn0q"] = ([S(food=2, alt={"food": [1]}, terms=["sharing"], why="'Literally anything, sharing recommended.'")], "")
L[A + "t1_omhd90x"] = ([S(food=3, alt={"food": [2]}, dishes=[("steak", 3, False)], terms=["steak"],
                         why="'The steak is amazing, one of my favorite steaks in the city.'")], "")
L[A + "t1_omhspkf"] = ([S(food=2, dishes=[("lamb shank", 2, False)], terms=["lamb shank"], why="'Lamb shank is a must order!'")], "")
L[A + "t1_omhymzz"] = ([S(food=2, dishes=[("lamb shank", 2, False)], why="'agreed it is so so good! you can't go wrong'")], "")
L[A + "t1_omjt4y7"] = ([S(food=2, alt={"food": [3]}, dishes=[("lamb shank", 3, False)],
                         why="'Everything was delish but that was a showstopper'")], "")
L[A + "t1_omhtigm"] = ([S(food=2, dishes=[("shallot and yogurt dip", None, False), ("date salad", None, False), ("meatballs", None, False),
                                          ("rice", None, False), ("tahdig", None, False)],
                         terms=["tahdig"], why="'enjoyed it... I don't think you can go wrong anywhere'")], "")
L[A + "t1_omja0eq"] = ([S(food=1, dishes=[("rosewater ice cream", 1, False)], terms=["rosewater ice cream"],
                         why="'Rosewater ice cream was really fun.'")], "")

B = "t008/"
L[B + "t1_nlee9b4"] = ([M("Zoom Zib", food=2, value=1, wait=1, alt={"value": [None], "wait": [None], "expensiveness": [-1]},
                          terms=["thai", "quick"], why="'super quick, reasonable price and delicious Thai food'")], "")
L[B + "t1_nleeujt"] = ([M("Zoom Zib", named_in="parent", amb=True, first=False, why="OP thanks; nameless, no opinion")], "")
for cid in ["t1_nlehol4", "t1_nleiqbh", "t1_nlelf2z", "t1_nlfcobk", "t1_nlfzk04"]:
    L[B + cid] = ([], "Sightseeing/Times Square/politics; no place.")
L[B + "t1_nlf0n8d"] = ([M(r, c, type=t, food=1, why="list answer")
                        for r, c, t in [("joe’s pizza", "Joe's Pizza", "restaurant"), ("los tacos no 1", "Los Tacos No. 1", "restaurant"),
                                        ("urban hawker", "Urban Hawker", "food_hall"), ("eataly", "Eataly", "food_hall"),
                                        ("jollibee", "Jollibee", "chain"), ("krispy kreme", "Krispy Kreme", "chain"),
                                        ("daily provisions", "Daily Provisions", "chain")]], "'koreatown' is a neighborhood; bodega BEC generic.")

C = "t009/"
for cid in ["t1_p7lvq9p", "t1_p7ly3qf", "t1_p7m8fkf", "t1_p7lvxm6", "t1_p7mghpt", "t1_p7mleh2", "t1_p7lvz2k", "t1_p7lw7nf",
            "t1_p7lwbu7", "t1_p7lwc33", "t1_p7lxsg4"]:
    L[C + cid] = ([], "Parody banter; 4 Charles not judged.")
L[C + "t1_p7lvvvg"] = ([M("Au Cheval", first=None, why="reference to another post about Au Cheval")], "")
L[C + "t1_p7lxy78"] = ([M("Daniel", why="ambulance anecdote on their anniversary: reference, no opinion")], "")

D = "t010/"


def MT(**kw):
    kw.setdefault("named_in", "title")
    return M("Mama’s Too", "Mama's Too", also=("mamas too", "mamas"), **kw)


def RG(**kw):
    kw.setdefault("named_in", "title")
    return M("Red Gate Bakery", also=("red gate",), type="cafe_bakery_dessert", **kw)


for cid in ["t1_ozsqh90", "t1_ozssl7r", "t1_ozst10n"]:
    L[D + cid] = ([], "Portion-size banter.")
L[D + "t1_ozstbki"] = ([MT(food=2, alt={"food": [3]}, why="'the food was good. All hits, no misses. 10/10 would do it again.'"),
                        RG(food=2, alt={"food": [3]}, why="same")], "")
L[D + "t1_ozujedh"] = ([M("faiccos", "Faicco's Italian Specialties", also=("faiccos",), food=1,
                          dishes=[("chicken cutlet sando", 1, False)], terms=["chicken cutlet sandwich"],
                          why="'try faiccos for a chicken cutlet sando!'")], "")
L[D + "t1_ozulzk6"] = ([M("faiccos", "Faicco's Italian Specialties", named_in="parent", amb=True, first=False,
                          why="'Yum. I've been meaning to try that place!'")], "")
L[D + "t1_p0h8kmt"] = ([M("Faicco's", "Faicco's Italian Specialties", food=2,
                          dishes=[("chicken cutlet sandwich with broccoli rabe", 2, False)], terms=["cutlet sandwich", "broccoli rabe"],
                          why="'I want to +1 this... almost pesto out of the broccoli rabe is so good'")], "")
L[D + "t1_p0htz5m"] = ([M("Faicco's", "Faicco's Italian Specialties", named_in="parent", food=-1, alt={"food": [0]},
                          dishes=[("cold sandwiches", 1, False), ("hot sandwiches", -3, True)],
                          why="'It's only good for cold. Don't get the hot. The hot sandwiches r foul'")], "")
L[D + "t1_p0hwhxl"] = ([M("Faiccos", "Faicco's Italian Specialties", food=-2, dishes=[("cutlet sandwich", -2, False)],
                          why="'their cutlet sandwich is so disappointing... Faiccos is too cold'"),
                        M("Parisi", "Parisi Bakery", food=-1, dishes=[("cutlet sandwich", -1, False)], why="'Parisi not enough breading'"),
                        M("Parm", food=-1, dishes=[("cutlet sandwich", -1, False)], why="'Parm too thick'"),
                        MT(named_in="comment", food=-1, first=False, alt={"food": [-2, None]},
                           why="'looks overly popular so... the quality is probably shite' (hearsay)"),
                        M("Caponne", food=-1, conf="low", why="'Caponne meh'"),
                        M("emilios ballato", "Emilio's Ballato", food=1, exp=1, alt={"food": [None]}, why="named as a real (pricey) option"),
                        M("Arthur and sons", "Arthur & Sons", food=1, exp=1, alt={"food": [None]}, why="same")], "")
for cid in ["t1_ozw7l3p", "t1_ozw7m48"]:
    L[D + cid] = ([RG(named_in="comment", food=-2, neg_ok=True, alt={"food": [-1]}, dishes=[("pumpkin loaf", -2, False)],
                      why="'not great experience... pumpkin loaf slice was just raw... hesitant to go back'")], "Duplicate post of the same comment.")
L[D + "t1_ozw890q"] = ([RG(food=2, wait=-1, alt={"food": [3], "wait": [-2]},
                          dishes=[("chocolate chip cookie", 2, False), ("pb&j bars", 2, False)], terms=["chocolate chip cookie", "pb&j bars"],
                          why="'Everything I've had there has been amazing!... deterrents are the weird hours... long lines'")], "")
L[D + "t1_ozwbi85"] = ([RG(food=1, alt={"food": [2]}, why="'I've been happy with everything I had there... you got unlucky'")], "")
L[D + "t1_ozx0nmo"] = ([MT(food=1, value=-2, exp=2, vc=True, alt={"food": [0], "expensiveness": [1]},
                          dishes=[("chicken sandwich", -1, False), ("house slice", 1, False)],
                          why="'$25 for a chicken sandwich was a disappointment, solid house slice though'")], "")
L[D + "t1_ozyeh95"] = ([MT(food=2, exp=1, alt={"value": [1]}, dishes=[("chicken sandwich", 2, False)],
                          why="'Definitely pricy, but it was very good. Still need to try their cheesesteak!'")], "")
L[D + "t1_ozx3229"] = ([RG(named_in="comment", first=None, why="'Does Red Gate have lines now?': reference")], "")
L[D + "t1_ozyedi1"] = ([RG(wait=0, alt={"wait": [-1, 1]}, why="'every time I've gone, I've had to wait in line. It moves quickly though!'")], "")

E = "t011/"


def R(**kw):
    kw.setdefault("named_in", "title")
    return M("Red Hook Tavern", **kw)


for cid in ["t1_obhgoy5", "t1_obj5hsr", "t1_obhoh06", "t1_oboxx5i"]:
    L[E + cid] = ([], "Plans or questions; no opinion.")
L[E + "t1_obhcwcx"] = ([R(wait=1, terms=["lunch"], why="'go on a Thursday for lunch... I was seated immediately'")], "")
L[E + "t1_obhfu84"] = ([R(amb=True, first=False, why="'We've decided to go for lunch today' — plan, nameless")], "")
L[E + "t1_obiye2l"] = ([R(wait=-1, alt={"wait": [-2]}, why="'Had to wait about an hour, but we did it!'")], "")
L[E + "t1_obj6a5w"] = ([R(food=1, alt={"food": [0]}, why="worth the wait? 'Debatable but yes'")], "")
L[E + "t1_obkq0rr"] = ([R(food=1, alt={"food": [None]}, dishes=[("smoked pork chop", 2, False), ("burger", None, False)],
                         terms=["smoked pork chop", "burger"], why="'missing arguably the best dish, the smoked pork chop!'")], "")
L[E + "t1_obhdci5"] = ([R(wait=-2, alt={"wait": [-1]}, why="reservations difficult, few walk-in seats, tourists lined up early")], "")
L[E + "t1_obhn859"] = ([R(named_in="comment", wait=-2, atmosphere=-1, alt={"atmosphere": [None]},
                         why="'reaaally small space... waiting an hour plus just to get told there's no spots'")], "")
L[E + "t1_obkg08l"] = ([R(amb=True, why="'not super easy to get to without a car' — location remark")], "")
L[E + "t1_obibaj3"] = ([R(wait=1, alt={"wait": [None]}, first=None, why="'go late on a week night' tip")], "")
L[E + "t1_objjsjv"] = ([R(wait=-2, why="'It would be faster to get on the Jitney and go to their place in Sag Harbor. Yikes.'")], "")
L[E + "t1_obk6ris"] = ([R(amb=True, first=False, alt={"food": [-1]}, why="'what's the draw?' — question")], "")
L[E + "t1_obki27g"] = ([R(food=2, why="'Figured it would be overhyped….i was wrong. It's great.'")], "")
L[E + "t1_obkmoig"] = ([R(wait=-1, alt={"wait": [None]}, first=False, why="'even on a sticky and rainy saturday it was busy'")], "")
L[E + "t1_obkhwb2"] = ([R(wait=-1, alt={"wait": [None]}, why="'the line started around 4:15'")], "")
L[E + "t1_obkr35o"] = ([R(wait=1, why="'went once at like 6p and was able to sit at the bar'")], "")
L[E + "t1_obm7ztv"] = ([R(wait=0, alt={"wait": [-1, 1]}, why="'table right away, or after the first seating between 45-90 minutes'"),
                        M("Sunny’s", "Sunny's Bar", type="bar", food=1, alt={"food": [None]}, why="'Perfect amount of time to get a beer at Sunny's'")], "")
L[E + "t1_obopdo7"] = ([R(wait=1, why="'I walked right in for lunch'")], "")
L[E + "t1_obpxgdx"] = ([R(wait=-1, alt={"wait": [None]}, why="'Be there at 11:30' (before opening)")], "")
