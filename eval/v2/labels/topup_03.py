"""v2 top-ups u0065-u0099, labeled blind."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "labels"))
from common import M  # noqa: E402

L = {}
L["t1_omzt4s3"] = ([M("Hearth", named_in="title", first=False, alt={"food": [-1]}, dishes=["variety burger"],
                      why="'I want to try it but... it was sickeningly rare' (from a video): reference")], "")
L["t1_ohdl53k"] = ([M("Smorgasburg", type="food_hall", food=1, alt={"food": [2]}, terms=["food market"], hood="Williamsburg",
                      why="'I would recommend checking it out... worth visiting if you're a tourist'"),
                    M("Queens Night Market", type="food_hall", first=None, why="'a trek': reference"),
                    *[M(n, type="stall_vendor", first=None, why="vendors that opened their own locations: reference")
                      for n in ["Noodle Lane", "Birria LES", "Hen House"]],
                    M("So Sarap", type="stall_vendor", food=2, dishes=[("filipino bbq skewers", 2, False)],
                      terms=["filipino bbq", "skewers"], why="'I personally LOVE the So Sarap stand'")], "")
L["t1_laknyez"] = ([], "Unnamed place on Rivington.")
L["t1_ox5azfi"] = ([M("the place in guilford CT", "The Place", oos=True, why="Guilford, CT: outside NYC")], "")
L["t1_o3ka0u8"] = ([M("Manhattan Fruit Exchange", named_in="ancestor", type="grocery_market", oos=True, closed=True,
                      why="produce retailer, closed: 'a shadow of what it used to be'")], "")
L["t1_nnbinpp"] = ([M("chipotle", "Chipotle", named_in="title", type="chain", value=2, alt={"value": [1]}, hood="1st and 15th next to Stuytown",
                      why="'has been hooking it up lately... almost too much food'")], "")
L["t1_oeh8yt4"] = ([M("Popup bagels", "Pop Up Bagels", named_in="title", type="chain", wait=-2, alt={"wait": [-1], "food": [-1]},
                      first=None, why="'Why is there always a line down the block for this place? Makes NO sense'")], "")
L["t1_oklcs99"] = ([M(r, c, food=1, why="lunch list") for r, c in [("Mamouns", "Mamoun's Falafel"), ("Desi stop and deli", "Desi Stop & Deli"),
                                                                 ("Zaragoza", None), ("Butter smashburger", "Butter Smashburger"),
                                                                 ("Punjabi deli", "Punjabi Grocery & Deli"), ("Kisa", None)]], "")
L["t1_ou5l7y7"] = ([M("Deli Board", food=1, dishes=[("dutch crunch", 1, False)], terms=["dutch crunch"],
                      why="'Deli Boards Dutch crunch is pretty soft fwiw'")], "")
L["t1_npnx24o"] = ([M("One White Street", food=3, alt={"food": [2]}, dishes=[("desserts", 2, False)], terms=["tasting menu", "desserts"],
                      why="'still a top choice for a great tasting menu... amazing meal from start to finish'")], "")
L["t1_oisorrc"] = ([M(r, c, type="food_truck", food=1, why="food-truck list")
                    for r, c in [("Birria Landia", None), ("Mahmoud’s Corner", "Mahmoud's Corner"), ("Grand St Skewer Cart", None),
                                 ("Tortas Neza", None), ("Tacos El Bronco", None), ("Tacos El Lobo", None), ("Mido’s", "Mido's"),
                                 ("Xinjiang BBQ Stand", None), ("Tony Dragon’s Grill", "Tony Dragon's Grill")]],
                   "Fuchka carts / cheong fun cart unnamed.")
L["t1_jrsadb8"] = ([M("Beauty & Essex", food=2, atmosphere=-1, alt={"atmosphere": [None]},
                      why="'always had great experiences... can be hectic and overcrowded'"),
                    *[M(n, food=2, why="'I've always had great experiences here'")
                      for n in ["Buddakan", "Catch", "Chinese Tuxedo", "One if by land two if by sea", "Tao"]]], "")
L["t1_ovw97rt"] = ([M("Place des fetes", "Place des Fêtes", named_in="comment", atmosphere=2, alt={"atmosphere": [1], "food": [1]},
                      why="'+1 on Place des fetes. You can rent out the back room and it's great.'")], "")
L["t1_orirtjy"] = ([M("Theodora", named_in="title", food=-1, why="'This place is overrated'")], "")
L["t1_of9onsd"] = ([], "Generic takeout places with map links.")
L["t1_o682miv"] = ([M("Crispy Heaven", named_in="title", food=3, wait=-2, neg_ok=True, alt={"food": [2], "wait": [-1]},
                      dishes=[("baguette", 3, False)], terms=["baguette", "breakfast"],
                      why="'legit... best baguette in the city... I avoid it for anything other than a weekday breakfast... as it's popping'")], "")
L["t1_nktelej"] = ([M("One More Thai", food=1, alt={"food": [2]}, why="'my go tos'"),
                    M("Lava Shawarma", food=1, alt={"food": [2]}, why="same")], "")
L["t1_oyo66a4"] = ([M("La Grande Boucherie", named_in="parent", food=-2, alt={"food": [-3]}, why="'This place is genuinely terrible'")], "")
L["t1_nvqlhvm"] = ([M("Radio bakery", "Radio Bakery", named_in="title", type="cafe_bakery_dessert", food=-2, wait=-2, value=-2, exp=2,
                      vc=True, alt={"expensiveness": [3]}, dishes=[("focaccia", -2, False), ("pastries", -2, False)],
                      why="'Mid level bland fauxcoccia. Shop Rite quality pastries. Long painful waits. Priced to kill.'")], "")
L["t1_nuyw195"] = ([M("Fette Sau", named_in="title", closed=True, dishes=["ribs"],
                      why="closing; 'worst ribs... outrageous price. Good riddance.' — closed => aspects null")], "")
L["t1_nvkdlkl"] = ([M("Ham Ji Bach", food=-1, neg_ok=True, alt={"food": [-2]}, terms=["korean"],
                      why="old location loved; 'We tried the new location once and never went back'")],
                   "'Too expensive for what you get' is about Korean restaurants in general.")
L["t1_nxfa85m"] = ([M("keens", "Keens Steakhouse", food=2, atmosphere=1, alt={"food": [1]}, dishes=[("prime rib", 2, False)],
                      terms=["prime rib", "old feel"], why="'I like keens for prime rib (and old feel)'"),
                    M("quality meats", "Quality Meats", food=2, alt={"food": [1]}, dishes=[("ribeye", 1, False)], terms=["ribeye"],
                      why="'quality meats for ribeye'")], "'$100 for a steak' is general.")
L["t1_m665kap"] = ([M("Jack's Wife Freda", named_in="parent", value=-2, vc=True, rc=True, rt=False,
                      why="'It's way overpriced for what it is'"),
                    M("Westville", food=1, exp=-1, value=1, alt={"value": [None]}, why="'basically the same thing but less expensive'")], "")
L["t1_ol8bujz"] = ([M("Ceres", "Ceres Pizza", first=False, exp=1, alt={"expensiveness": [2], "value": [1]},
                      why="'I haven't had Ceres, but is their base pizza that overpriced?... $30': reference")], "")
L["t1_o8mptug"] = ([M("Koma", named_in="title", food=2, value=3, exp=2, alt={"expensiveness": [1]},
                      dishes=["fatty tuna", "kamatoro"], terms=["omakase", "ayce", "fatty tuna", "kamatoro"],
                      why="'For that price it's a crazy deal... no better deal in the city'")], "")
L["t1_o5h0upt"] = ([M("Theodora", first=None, why="'not just Theodora': reference in a pricing rant")], "")
L["t1_p26hc2j"] = ([M("Dirt Candy", food=2, value=2, service=2, atmosphere=1, exp=1, alt={"food": [3], "expensiveness": [None]},
                      dishes=[("swe'pea daiquiri", 2, False), ("fennel", 2, False), ("eggplant with chives", 2, False), ("tomato", 3, False),
                              ("fried okra", 3, False), ("onion", 2, False), ("zucchini", 1, False), ("corn", 0, False),
                              ("cookies with bell pepper jelly", 1, False)],
                      terms=["vegetables", "michelin", "open kitchen", "living wage"],
                      why="dish-by-dish; '$150, which I thought was super reasonable'; 'Service was great... open kitchen'")], "")
L["t1_lak5pcf"] = ([M("food gallery", "Food Gallery 32", named_in="parent", type="food_hall", food=-1, alt={"food": [-2]},
                      why="'Most of that whole first floor food court kinda sucks'"),
                    M("pelicana fried chicken", "Pelicana Chicken", type="chain", food=1, alt={"food": [2]}, why="'is good'")],
                   "Unnamed churro and kimbap places.")
L["t1_ooko90w"] = ([M("Sushi by M", food=2, value=2, exp=1, alt={"expensiveness": [0]}, terms=["omakase", "casual"],
                      why="'has never disappointed... $100 for their 16 piece omakase... Great value'")], "")
L["t1_p062dvv"] = ([M("Suprema", "NY Pizza Suprema", named_in="comment", food=3, atmosphere=-1, alt={"atmosphere": [None]},
                      hood="Penn Station", terms=["ny slice"],
                      why="'It is to this day my favorite pizza spot in nyc. The platonic ideal NY slice joint'"),
                    *[M(r, c, first=None, why="comparison reference") for r, c in
                      [("L’Industrie", "L'Industrie Pizzeria"), ("John’s of Bleecker", "John's of Bleecker Street"),
                       ("Mama’s Too", "Mama's Too"), ("Ceres", "Ceres Pizza"), ("Joe’s", "Joe's Pizza")]]], "")
L["t1_nt84xmq"] = ([M("Taiwan Pork Chop House", food=2, value=2, exp=-2, dishes=[("pork chop over rice", 2, False)],
                      terms=["pork chop over rice", "cheap"], why="'$10 Great pork chop over rice' in a best-value thread"),
                    M("Taskent Supermarket", "Tashkent Market", type="grocery_market", oos=True, why="supermarket"),
                    M("E-MO", food=2, exp=-1, dishes=[("veg kim bap", 2, False)], terms=["kimbap"], why="'$11 for delicious veg kim bap'")], "")
L["t1_ol0j9y2"] = ([M("sushi blossoms", "Sushi Blossom", food=2, exp=1, alt={"expensiveness": [0]}, hood="Chelsea", terms=["omakase"],
                      why="'You MUST go... $120 for a 17 course Omakase... beautiful presentations'")], "")
L["t1_matyk0w"] = ([M("Roscioli", exp=2, first=False, terms=["valentine's day dinner"], why="reservation transfer, $348 for 2: reference")], "")
L["t1_ob86ly5"] = ([M("utopia bagel", "Utopia Bagels", food=2, why="'a notch above Apollo bagel'"),
                    M("Apollo bagel", "Apollo Bagels", food=1, wait=-2, why="'That doesn't mean Apollo isn't good but I'm not about to wait 45 minutes'"),
                    M("Joes pizza", "Joe's Pizza", food=1, value=1, why="'the standard... fairly priced standard tasting New York slice'"),
                    M("Patsys", "Patsy's Pizzeria", food=2, value=2, exp=-1, alt={"food": [3]}, hood="1st Ave and 118",
                      terms=["coal fire oven"], why="'My personal favorite... $16 for a whole pie'")], "")
L["t1_nvl594g"] = ([], "Sushi prices in general.")
