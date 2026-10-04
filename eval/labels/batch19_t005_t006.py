"""Threads t005 (weight-loss veg orders) and t006 (Eleven Madison Park lunch). Every comment labeled."""
from common import M

L = {}
A = "t005/"


def SG(raw="Sweet Greens", named_in="comment", **kw):
    return M(raw, "Sweetgreen", also=("sweet greens", "sweet green", "sweetgreen"), named_in=named_in, type="chain", **kw)


for cid in ["t1_o253pyu", "t1_o2548ih", "t1_o256vt2", "t1_o25h9wp", "t1_o2573bi", "t1_o257o2x", "t1_o257x2w",
            "t1_o2587x9", "t1_o25quyx", "t1_o2843ho", "t1_o258091", "t1_o25pnrx", "t1_o25f89b", "t1_o25l73o"]:
    L[A + cid] = ([], "Diet advice, generic dishes (mapo tofu), meal-prep services; no place.")
L[A + "t1_o251gud"] = ([SG(neg=True, neg_ok=True, first=None,
                           why="'looking into Sweet Greens \"partnerships\" before giving them any more of your money' — avoid for political reasons")], "")
L[A + "t1_o255ayj"] = ([SG(food=1, alt={"food": [2]}, terms=["calories"], why="'I like sweet greens because I can see the calories'")], "")
L[A + "t1_o255ea6"] = ([SG(named_in="parent", food=-1, alt={"food": [None]}, dishes=[("sauce", -1, False)],
                           why="'they only have very unhealthy sauce options'")], "")
L[A + "t1_o258pnt"] = ([SG(raw="Sweet Green", first=None, why="clarifies the partnership issue: reference")], "")
L[A + "t1_o25cmbj"] = ([SG(named_in="parent", neg_ok=True, why="'Didn't know this def gonna avoid now' — self-avoid")], "")
L[A + "t1_o251zd6"] = ([M("Westville", food=2, alt={"food": [1]}, terms=["healthy", "filling"],
                          why="'good for healthy and filling meals'")], "")
L[A + "t1_o256pyx"] = ([M("westville", "Westville", food=0, alt={"food": [1, -1]}, dishes=[("market sides", 2, False)],
                          terms=["market sides"], why="'I like westville... but their food is really on the oily side... wouldn't call their menu healthy'")], "")
L[A + "t1_o3fr46i"] = ([M("westville", "Westville", named_in="parent", food=-1, alt={"food": [-2]},
                          why="'I agree. The quality of the food is like suburban diners in the 1990's'")], "")
L[A + "t1_o252jjg"] = ([M("Juicy Cube", food=1, value=1, alt={"value": [None]}, dishes=[("smoothies", 1, False)],
                          terms=["smoothies", "sugar free", "superfood"], why="'more reasonably priced superfood/sugar free smoothies'")], "")
L[A + "t1_o255q7c"] = ([SG(raw="Sweetgreen", neg=True, why="'Sweetgreen is partnering with an anti vaxer so would avoid them'"),
                        M("lenwich", "Lenwich", type="chain", food=1, dishes=[("veggie sandwiches", 1, False), ("veggie bowl", None, False)],
                          terms=["veggie sandwich", "filling"], why="'Veggie sandwiches from lenwich are filling'")], "")
L[A + "t1_o25705p"] = ([M("Le Botaniste", food=1, dishes=[("warm bowl", 1, False)], terms=["calorie labelled", "warm bowl"],
                          why="suggested for weekday lunch")], "")
L[A + "t1_o25bxps"] = ([M("Le Botaniste", named_in="parent", food=1, first=False, why="'Omg this looks so good. Def gonna order'")], "")
L[A + "t1_o25j5zj"] = ([M("Little Beet", type="chain", food=1, terms=["customizable bowls"], why="'has customizable bowls'"),
                        M("Rooted", food=-1, alt={"food": [0]}, terms=["healthy"], why="'not terribly exciting taste-wise but definitely healthy'"),
                        M("Carrot Express", type="chain", first=False, why="'Haven't been, but I've been eyeing': reference"),
                        SG(raw="sweetgreen", food=-1, why="'I feel like they'd been going downhill'"),
                        M("Pret", "Pret A Manger", type="chain", food=1, dishes=[("falafel salad bowl", 1, False)],
                          why="'I also actually like Pret's falafel salad bowl!'")], "")
L[A + "t1_o25k2z0"] = ([M("Ben's Fast Food", food=1, conf="medium", dishes=["vegetarian dumplings", "sushi"],
                          why="'might be a good option'")], "")
L[A + "t1_o25uojf"] = ([M("Matter", food=1, alt={"food": [None]}, hood="Noho", terms=["build your own bowls", "calories"],
                          why="'build your own bowls with all the nutritional facts and calories'")], "")
L[A + "t1_o2c1yf4"] = ([M("Mangia", type="chain", food=2, exp=1, terms=["salads", "healthy"],
                          why="'excellent variety of salads... not cheap, but the quality is very good'")], "")
L[A + "t1_o2ekx7n"] = ([M("matter", "Matter", food=1, alt={"food": [None]}, hood="noho", terms=["macros"],
                          why="'You can set your exact macros at matter'")], "")

B = "t006/"


def E(named_in="title", **kw):
    return M("Eleven Madison Park", also=("emp",), named_in=named_in, **kw)


for cid in ["t1_p2ym4d8", "t1_p2ym7g6", "t1_p31z3t5", "t1_p2ymc6r", "t1_p320q1f", "t1_p3gilw5", "t1_p3khzo2"]:
    L[B + cid] = ([], "Banter or OP questions; no new opinion.")
L[B + "t1_p2w5997"] = ([E(food=1, first=False, alt={"food": [2, None]}, why="'bucket list place for sure'")], "")
L[B + "t1_p2xrsms"] = ([E(amb=True, why="describes the chocolate game; no judgment")], "")
L[B + "t1_p2wsyml"] = ([E(amb=True, first=None, why="'That's cool they give you a kids activity too' — likely sarcastic")], "")
L[B + "t1_p2x4xyc"] = ([E(atmosphere=2, terms=["lunch", "natural lighting"],
                          why="'lunch > dinner... the natural lighting that comes in is beautiful. Cute chocolate game'")], "")
L[B + "t1_p2ymh7y"] = ([E(atmosphere=2, alt={"atmosphere": [1]}, why="'Early afternoon is such a wonderful time of day to be there'")], "")
L[B + "t1_p2xigq9"] = ([E(food=1, first=False, alt={"food": [None]}, why="'Lovely! Did you have to book far in advance?'")], "")
L[B + "t1_p31ynva"] = ([E(wait=1, why="'Couple of weeks for lunch... it has not been difficult to find a spot'")], "")
L[B + "t1_p2xkakg"] = ([E(food=1, alt={"food": [2]}, first=None,
                          why="'This is the best that EMP has looked to me in a hot minute'")], "")
L[B + "t1_p32za1o"] = ([E(food=1, alt={"food": [2]},
                          why="last fall 'limping your way through the hits... I would not return'; this menu 'I would be willing to go back'"),
                        M("Per Se", first=None, dishes=["oysters and pearls"], why="comparison reference"),
                        M("Le Bernardin", first=None, dishes=["pounded tuna and foie"], why="comparison reference")], "")
L[B + "t1_p33kjx9"] = ([M("Per Se", first=True, why="'I just went to Per Se for the first time': reference"),
                        M("Le Bernardin", food=2, alt={"food": [1]}, terms=["lunch"], why="'discovered how nice lunch at Le Bernardin is'")], "")
L[B + "t1_p2xn5ux"] = ([E(food=-1, first=False, why="'This looks pretty uninspired IMO'")], "")
L[B + "t1_p37yl05"] = ([E(food=-1, alt={"food": [-2]}, first=False, why="'I would probably walk out after reading that boring menu'")], "")
L[B + "t1_p2ys5to"] = ([E(food=1, first=False, why="'How much? Looks amaze'")], "")
L[B + "t1_p30rnwb"] = ([E(food=1, alt={"food": [0]}, why="'went during the vegan period and it was good but definitely left something to be desired'")], "")
L[B + "t1_p31zbsv"] = ([E(amb=True, why="menu-format info only")], "")
L[B + "t1_p31jzrz"] = ([E(food=1, first=False, alt={"food": [None]}, why="'This looked beautiful!'")], "")
L[B + "t1_p3jmrdd"] = ([E(amb=True, first=None, why="'Fine dining is on repeat. All the same.' — about fine dining generally")], "")
