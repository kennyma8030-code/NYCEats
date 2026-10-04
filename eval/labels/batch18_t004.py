"""Thread t004 (t3_1vzfd60): Mama's Too slices. Every comment labeled."""
from common import M

T = "t004/"


def MT(named_in="title", **kw):
    return M("Mama’s Too", "Mama's Too", also=("mamas too", "mamas"), named_in=named_in, **kw)


L = {}
for cid in ["t1_p64gzqa", "t1_p65aoi0", "t1_p64he5x", "t1_p64i28h", "t1_p64ix6m", "t1_p64mafl", "t1_p69al9a",
            "t1_p69cwoh", "t1_p69feyp", "t1_p6ahbyv", "t1_p69bw81", "t1_p69u9at", "t1_p69ujb6", "t1_p6aeqff",
            "t1_p6ktrxn", "t1_p795a0l"]:
    L[T + cid] = ([], "Banter, questions, or Portnoy talk; no place judged.")

L[T + "t1_p65fvfr"] = ([MT(food=1, alt={"food": [2]}, why="'not even a hot take at this point' — agrees it's a favorite")], "")
L[T + "t1_p64fv4j"] = ([MT(food=2, why="'It's one of my nyc favs as well!'")], "")
L[T + "t1_p64gakh"] = ([M("Paulie Gee’s", "Paulie Gee's Slice Shop", also=("paulie gees",), food=3, alt={"food": [2]},
                          dishes=[("pepperoni square", 3, False)], terms=["pepperoni square", "sesame crust"],
                          why="'was blown away. The sesame crust on the bottom was next level'")], "")
L[T + "t1_p64hx5p"] = ([M("Paulie Gee’s", "Paulie Gee's Slice Shop", named_in="ancestor", amb=True, first=None,
                          why="'Do they still have a C health rating?' — nameless question")], "")
L[T + "t1_p64kbxl"] = ([M("Centro", food=2, conf="medium", why="'it had Grade Pending, but tasted great'")], "")
L[T + "t1_p64l1oi"] = ([M("Paulie Gee’s", "Paulie Gee's Slice Shop", named_in="ancestor", amb=True, hood="east village",
                          why="'They have a slice shop in east village now that I think is rated better'")], "")
L[T + "t1_p64h3jf"] = ([MT(food=2, alt={"food": [1]}, dishes=[("slice", 0, False)], terms=["thin slice"],
                          why="'It's very good. My only issue with a slice is it's SO big'")], "")
L[T + "t1_p64kpir"] = ([MT(food=2, dishes=[("round pies", 2, False)], why="'Their round pies are excellent too'")], "")
L[T + "t1_p64hhkf"] = ([MT(food=2, dishes=[("slices", 2, False), ("sandwiches", 2, False)],
                          why="'I've tasted 5 different slices... two sandwiches, and all were great'")], "")
L[T + "t1_p65mhpf"] = ([MT(food=2, why="'Even the ones that sound weird are good'")], "")
L[T + "t1_p69yfzg"] = ([MT(food=1, alt={"food": [2]}, dishes=[("pear slice", 2, False)], why="'oh i love that one!'")], "")
L[T + "t1_p69zka5"] = ([MT(food=2, dishes=[("pear slice", 2, False)], why="'much better than expected. I may go again'")], "")
L[T + "t1_p6ak2ii"] = ([MT(food=2, dishes=[("pear slice", 2, False)], why="'it's really good I was surprised'")], "")
L[T + "t1_p64hhwb"] = ([MT(food=2, alt={"food": [3]}, why="'That place was so good, I liked it more than L'Industrie'"),
                        M("L’Industrie", "L'Industrie Pizzeria", alt={"food": [1]}, first=None, why="loses the comparison")], "")
L[T + "t1_p64o0fe"] = ([MT(food=1, why="'I like both for different reasons'"),
                        M("L’Industrie", "L'Industrie Pizzeria", named_in="parent", food=1, why="same")], "")
L[T + "t1_p64jhq5"] = ([MT(food=3, dishes=[("philly cheese steak", 3, False)], terms=["philly cheesesteak"],
                          why="'Their Philly cheese steak also might be the best I've ever had'")], "")
L[T + "t1_p64to3h"] = ([M("Coops", "Danny & Coop's", also=("coops",), food=3, dishes=[("cheesesteak", 3, False)], terms=["cheesesteak"],
                          why="'Coops is the best'"),
                        MT(named_in="parent", food=2, dishes=[("philly cheese steak", 2, False)], why="'that's a close second'")], "")
L[T + "t1_p67js92"] = ([M("coops", "Danny & Coop's", food=2, why="'Man, coops is so good'")], "")
L[T + "t1_p64kv7q"] = ([MT(food=2, dishes=[("pistachio gelato", 2, False)], terms=["pistachio gelato"],
                          why="'Their pistachio gelato is so so good'")], "")
L[T + "t1_p64o4wn"] = ([MT(food=2, dishes=[("philly cheesesteak", 2, False), ("chicken parm sandwich", 2, False)],
                          terms=["philly cheesesteak", "chicken parm"], why="'They are my favorite!'")], "")
L[T + "t1_p64pxoc"] = ([MT(food=2, service=-2, alt={"service": [-3]}, why="'Great pizza. Horrible staff'")], "")
L[T + "t1_p64ylgw"] = ([MT(food=2, alt={"food": [3]}, why="'This is my favorite pizza shop.'")], "")
L[T + "t1_p6522gh"] = ([MT(named_in="comment", food=2, alt={"food": [3]},
                          why="'LOVE THEM... done EXTREMELY WELL'"),
                        M("domino’s", "Domino's", type="chain", first=None, why="comparison reference"),
                        M("pizza hut", "Pizza Hut", type="chain", first=None, why="comparison reference")], "")
L[T + "t1_p65mo5j"] = ([M("Pizza Hut", type="chain", alt={"food": [1]}, first=None, why="'Old school Pizza Hut maybe'")], "")
L[T + "t1_p65qu6a"] = ([M("pizza hut", "Pizza Hut", type="chain", food=1, why="'current pizza hut at a good location is still decent enough'")], "")
L[T + "t1_p6549gx"] = ([MT(named_in="comment", food=2, dishes=[("vodka slice", 2, False)], terms=["vodka slice"],
                          why="'Everything from Mama's Too does not miss'")], "")
L[T + "t1_p65ak1y"] = ([MT(food=1, first=False, why="'this looks so good. I've never been'")], "")
L[T + "t1_p65me6j"] = ([MT(food=2, alt={"food": [1]}, why="'It's worth a trip'")], "")
L[T + "t1_p65u95m"] = ([MT(food=1, alt={"food": [None]}, dishes=[("sandwiches", 1, False), ("slices", None, False)],
                          why="'Their sandwiches > their slices'")], "")
L[T + "t1_p66vnfc"] = ([MT(food=1, dishes=[("elote slice", 1, False)], terms=["elote slice"], why="'You need to try their elote slice'")], "")
L[T + "t1_p6732eo"] = ([MT(food=-2, alt={"food": [-1]}, why="'I don't like their pizza'"),
                        M("lindustry", "L'Industrie Pizzeria", food=-1, alt={"food": [-2]}, first=None,
                          why="'like lindustry' — also not liked")], "")
L[T + "t1_p67gw25"] = ([MT(food=1, first=False, why="'Both of these pizzas look delicious'")], "")
L[T + "t1_p67vvqn"] = ([MT(food=1, first=False, dishes=[("elote slice", 1, False)], why="'dyingg to try their August elote slice'")], "")
L[T + "t1_p685xca"] = ([MT(amb=True, why="'That might be delicious but... its not a slice' — format quibble")], "")
L[T + "t1_p68y8e7"] = ([MT(amb=True, alt={"food": [-1]}, first=None, why="Portnoy's 2018 6.8 review — someone else's opinion")], "")
L[T + "t1_p6aylfm"] = ([MT(food=2, alt={"food": [3]}, dishes=[("gorgonzola pear", -1, False)],
                          why="'Gorgonzola pear was meh. The rest tho....heaven!'")], "")
L[T + "t1_p6b7wr9"] = ([MT(wait=-2, why="'Those lines are brutal'")], "")
L[T + "t1_p6b9zgz"] = ([MT(wait=1, alt={"wait": [None]}, why="'Weekdays 12-2 is the best time to go'")], "")
L[T + "t1_p6lhixf"] = ([MT(food=-1, first=False, why="'Doesn't look appealing'")], "")
L[T + "t1_p6puvov"] = ([MT(named_in="comment", food=1, alt={"food": [2]}, why="'Mamas too is pretty good, but...'"),
                        M("Village Square", "Village Square Pizza", food=1, wait=1, exp=-1, alt={"food": [2]},
                          why="'only a couple blocks away, cheaper, and never has a line'")], "")
L[T + "t1_p6vw2ux"] = ([MT(food=1, why="'It's good'")], "Unnamed place on Christopher St.")
