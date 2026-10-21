"""v2 top-ups u0100-u0134, labeled blind."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "labels"))
from common import M  # noqa: E402

L = {}
L["t1_oqtv3vz"] = ([M("Heaven's Hot Bagels", hood="Houston", value=2, exp=-1, alt={"value": [1]}, why="'walk a bit to Heaven's Hot Bagels on Houston. $12 for way more.'"),
                    M("Kossars", "Kossar's Bagels & Bialys", named_in="title", amb=True, alt={"value": [-2]}, why="implied comparison only")], "")
L["t1_p2gqmqh"] = ([M("Raoul’s", "Raoul's", food=1, atmosphere=2, alt={"food": [2]},
                      dishes=[("steak frites", 1, False), ("au poivre sauce", 1, False), ("burger", None, False)],
                      terms=["steak frites", "au poivre", "bistro"],
                      why="'Vibe wise both are great... eclectic and goofy (in a good way)... my personal preference is Raoul's'"),
                    M("Minetta", "Minetta Tavern", food=1, atmosphere=2, alt={"food": [2]}, terms=["steakhouse", "pasta"],
                      why="'a beautiful interior with a lot of warm cozy tones... can't go wrong with either'")], "")
L["t1_oq5sptq"] = ([M(r, c, oos=True, why="New Haven, CT: outside NYC")
                    for r, c in [("Frank PePe", "Frank Pepe Pizzeria Napoletana"), ("Modern Apizza", None), ("Sally's", "Sally's Apizza"),
                                 ("Louis Lunch", "Louis' Lunch"), ("Olea", None), ("Heirloom", None), ("Roli", None),
                                 ("Anchor Spa", None), ("The Ordinary", None)]], "")
L["t1_padzyzp"] = ([M("Atera", exp=3, first=False, terms=["chef's counter"], why="reservation transfer, $707 for 2: reference")], "")
L["t1_oq8ykks"] = ([M("Mountain House", "Szechuan Mountain House", food=1, dishes=[("twice cooked pork", 1, False)], terms=["szechuan"],
                      why="suggested dish"),
                    M("Spy C Cuisine", food=1, dishes=[("farmhouse style pork", 1, False)], why="suggested dish"),
                    M("886", food=1, dishes=[("fly's head", 1, False)], terms=["taiwanese"], why="suggested dish")], "")
L["t1_pavx260"] = ([M("Katz", "Katz's Delicatessen", why="'I am pretty sure I was at Katz... Can't remember anything': reference"),
                    M("Chelsea Market", type="food_hall", dishes=["clam chowder"], why="'clam chowder somewhere in Chelsea Market': reference")], "")
L["t1_pbryhwc"] = ([M("Land of Plenty", food=3, dishes=[("salty egg yolk prawns", 3, False), ("jumbo fried shrimp", 3, False)],
                      terms=["szechuan", "salty egg yolk prawns"], why="'the best Jumbo fried shrimp in the city... Unreal'")], "")
L["t1_nxw2fgf"] = ([M("Shuya", food=1, terms=["mazemen", "tsukemen", "vegetarian ramen"], why="listed in three categories"),
                    M("Susuru Ramen", food=1, terms=["mazemen", "vegetarian ramen"], why="listed"),
                    M("Okonomi / Yuji Ramen", "Okonomi", also=("okonomi", "yuji ramen"), food=1, terms=["mazemen"],
                      why="listed (one business; production aliases both names together)"),
                    M("Kajiken", food=1, terms=["mazemen"], why="listed"),
                    M("Ramen Ishida Chelsea", "Ramen Ishida", food=1, terms=["tsukemen", "vegetarian ramen"], why="listed"),
                    M("Tabetomo", food=1, terms=["vegetarian ramen"], why="'Standout vegetarian ramen'"),
                    M("Karazishi Botan", food=1, terms=["vegetarian ramen"], why="same"),
                    M("Menkoi Sato", closed=True, why="'temporarily closed for now'")], "")
L["t1_p3jg7s3"] = ([M("Wo Hop", food=3, value=2, atmosphere=-1, exp=-1, alt={"food": [2], "atmosphere": [0], "expensiveness": [None]},
                      dishes=[("roast duck and roast pork chow mei fun", 2, False), ("lobster with garlic and scallions", 2, False),
                              ("cantonese lobster", 2, False)],
                      terms=["wok hei", "chow mei fun", "cantonese lobster", "classic"],
                      why="'a lot of their dishes are just unbelievably good and reasonably priced... not classy and it is noisy'")], "")
L["t1_p4vqhgx"] = ([M("Per Se", exp=2, first=False, terms=["salon", "tasting menu"], why="reservation transfer: reference")], "")
L["t1_pakr0ya"] = ([M("Il Buco", food=1, service=1, atmosphere=2, value=1, alt={"food": [2], "atmosphere": [1]},
                      terms=["private room", "cellar", "rehearsal dinner"],
                      why="'cellar... really wonderful... professional and the food was good... a really great dinner... price point was competitive'")], "")
L["t1_opr5fyf"] = ([M("Hi Collar", "Hi-Collar", food=2, alt={"food": [1]}, dishes=[("pancakes", 2, False), ("omu rice", 2, False)],
                      terms=["coffee", "kissaten", "yoshoku"], why="'serious coffee program... brunch/lunch program is beloved'"),
                    M("Davelle", food=1, terms=["coffee"], why="'Another good one is Davelle'")], "")
L["t1_oqhkbrq"] = ([M("Someday Bar", food=1, service=2, hood="Atlantic Ave and Hoyt St", dishes=[("burger", 1, False)],
                      terms=["queer owned", "drag brunch", "burger"], why="'great queer bar staff... Get the burger!'"),
                    M("HAGS", food=2, alt={"value": [1]}, terms=["queer owned", "pay what you can brunch"],
                      why="'an amazing fixed menu... pay what you can brunch on Sundays which is fabulous'")], "")
L["t1_nwffz4v"] = ([M("Manhatta", named_in="title", food=1, alt={"food": [None]}, why="'it's not that bad. I've had some pretty mid Michelin before.'")], "")
L["t1_o2jhrex"] = ([M(r, c, food=1, terms=t, why="omakase/sushi list") for r, c, t in [
    ("takumi", "Takumi Omakase", ["omakase", "byob"]), ("mojo east", "Mojo East", ["omakase"]), ("sugarfish", "Sugarfish", ["omakase"]),
    ("yokox", "YOKOX Omakase", ["omakase"]), ("shinzo", "Shinzo Omakase", ["omakase"]), ("momoya", "Momoya", ["sushi"]),
    ("otani", "Otani", ["sushi"]), ("blue ribbon", "Blue Ribbon Sushi", ["sushi"])]], "")
L["t1_oi28i6d"] = ([M("Narkara", food=-1, why="'pretty damn meh. All of their dishes were very one note for Thai'"),
                    M("Godunk", "GoDunk", first=False, alt={"food": [-1]}, why="'their 5* reviews were incentivized'"),
                    M("Bangkok Supper Club", food=1, atmosphere=2, alt={"food": [2]}, terms=["thai", "birthday"],
                      why="'a good Thai spot with nice ambience'")], "")
L["t1_oit3wxb"] = ([], "Unnamed Italian food truck, hearsay.")
L["t1_nxolwat"] = ([M("Katz’s", "Katz's Delicatessen", named_in="comment", food=2, wait=-2, alt={"wait": [-1]},
                      why="'Katz's is my favorite but probably not worth the line... around 9 or 10. There's no line by then'"),
                    M("second ave deli", "2nd Ave Deli", food=1, alt={"food": [None]}, why="'the other big two delis'"),
                    M("pastrami queen", "Pastrami Queen", food=1, alt={"food": [None]}, why="same")], "")
L["t1_p6tebe7"] = ([M("radio bakery", "Radio Bakery", named_in="ancestor", type="cafe_bakery_dessert", food=1, alt={"food": [2]}, rc=False, rt=True,
                      dishes=[("tomato feta mint focaccia sandwich", 2, False), ("tomato croissant", 0, False)],
                      terms=["focaccia", "tomato croissant"],
                      why="'Seconding the focaccia—the fresh oregano really makes it special. The tomato croissant was just ok.'")], "")
L["t1_o8c6kz5"] = ([M("moms", "Mom's NYC", food=-1, dishes=[("mac and cheese pancake", -1, False)],
                      why="'isn't as good as it used to be... the last time I went it was meh'"),
                    M("Thai dinner", "Thai Diner", food=1, why="swap suggestion"),
                    M("golden dinner", "Golden Diner", food=1, why="swap suggestion")], "")
L["t1_np5704j"] = ([M("Hajjii spot", "Hajji's", hood="110th and first ave", first=False, dishes=["chopped cheese"], terms=["chopped cheese"],
                      why="'Hajjii spot used to make them. I never had one': reference")], "")
L["t1_of9nzru"] = ([M("Raos", "Rao's", named_in="title", food=1, atmosphere=2, alt={"food": [0]},
                      why="'Food was good, nothing special. But the atmosphere was interesting... very lively and intimate'")], "")
L["t1_ok9ej8u"] = ([M("Carbone", food=2, why="'Carbone is quite good'"),
                    M("Torrisi", alt={"food": [1]}, first=None, why="'the rep is because it's not Torrisi': reference"),
                    M("Contessa", oos=True, hood="Boston", why="Boston: outside NYC")], "")
L["t1_onna4nk"] = ([M("Noodle village", "Noodle Village", named_in="title", food=1, alt={"food": [2]},
                      dishes=[("clay pot casseroles", 2, False), ("soup dumplings", 2, False), ("wontons in chili oil", 2, False)],
                      terms=["clay pot", "soup dumplings", "wontons in chili oil"],
                      why="'great at what they do great, but the things I order there are limited to...'")], "")
L["t1_lujdud4"] = ([M("K-Paul's", closed=True, why="'had a branch here... in 85... a full restaurant in 89': closed")],
                   "Cajun places generic.")
L["t1_m5ovv4r"] = ([M("Raising Canes", "Raising Cane's", named_in="parent", type="chain", food=1, alt={"food": [2]},
                      dishes=[("chicken tenders", 2, False)], why="'It might be bland but the texture of the chicken and breading are bomb'"),
                    M("Laynes", "Layne's", oos=True, hood="College Station TX", why="Texas")], "")
L["t1_p05qskq"] = ([M("L’Industrie", "L'Industrie Pizzeria", food=3, alt={"food": [2]}, why="'L'Industrie is probably the best.'"),
                    M("Mamas too", "Mama's Too", food=2, why="'very good'"),
                    M("Grand street pizza", "Grand Street Pizza", food=1, alt={"food": [2]}, why="'very good most of the time, I have got a dud slice'"),
                    M("Cellos", "Cello's Pizzeria", food=1, why="'Cellos is good'"),
                    M("Lucia", "Lucia Pizza", food=-1, why="'I found pretty mid but only went once'")], "")
L["t1_ntgkxkl"] = ([M("Thai diner", "Thai Diner", food=1, wait=-1, alt={"wait": [None]}, why="'good brunch options, if you have a resy. I wouldn't line up'"),
                    M("golden diner", "Golden Diner", food=1, wait=-1, alt={"wait": [None]}, why="same"),
                    M("russ and daughters", "Russ & Daughters", food=1, alt={"food": [0]}, dishes=[("bagels", -1, False)],
                      why="'their bagels are very meh'"),
                    M("apollos", "Apollo Bagels", food=-1, why="'not very fond of apollos'"),
                    M("Kossars", "Kossar's Bagels & Bialys", food=1, why="go instead"),
                    M("Tomkins square", "Tompkins Square Bagels", food=1, why="go instead"),
                    M("Scarrs", "Scarr's Pizza", food=-2, alt={"food": [-1]}, why="'Scarrs isn't good imo'"),
                    M("mamas too", "Mama's Too", food=2, why="'much better'")], "'All the bakeries listed are good' not expanded.")
L["t1_onwkswn"] = ([M("Lindustrie", "L'Industrie Pizzeria", food=1, wait=-2, neg_ok=True, alt={"food": [0]},
                      why="'The pizza is definitely not worth the wait. A good slice but only a slight step above'")], "")
L["t1_o65rrko"] = ([M("Bungalow", food=1, alt={"food": [0]}, dishes=[("biryani", -1, False), ("lamb", 2, False)], terms=["indian", "lamb"],
                      why="'Biryani was underwhelming but the lamb was amazing'")], "")
L["t1_p4ai0t6"] = ([M("Librae", type="cafe_bakery_dessert", food=2, alt={"food": [3]}, dishes=[("pistachio rose croissant", 2, False)],
                      terms=["pistachio rose croissant"], why="'Librae is a must!'"),
                    M("Bench Flour", "Bench Flour Bakers", type="cafe_bakery_dessert", food=-1, neg=True, alt={"food": [None]},
                      why="'Unless you're staying in Astoria... not worth it'"),
                    M("Little Flower", "Little Flower Cafe", type="cafe_bakery_dessert", food=-1, neg=True, alt={"food": [None]}, why="same"),
                    M("Diljan", "Diljān Bakery", type="cafe_bakery_dessert", food=-1, why="'I didn't love Diljan'")], "")
L["t1_nr4xixk"] = ([M("John’s Pizza", "John's of Bleecker Street", food=1, wait=-1, alt={"food": [2], "wait": [None]},
                      why="'It's quite good but not worth waiting a long time'"),
                    M("L’Industrie", "L'Industrie Pizzeria", food=1, wait=-1, alt={"food": [0], "wait": [None]},
                      why="'like elevated Joe's Pizza... Also not worth waiting a long time'"),
                    M("Joe’s Pizza", "Joe's Pizza", first=None, alt={"food": [1]}, why="comparison reference")], "")
L["t1_p82pm1d"] = ([M("Apollo Bagels", named_in="title", food=-1, dishes=[("bagels", -1, False)], why="'Don't get the hype... too soft, meh.'"),
                    M("Zabar’s", "Zabar's", type="grocery_market", oos=True, why="grocery"),
                    M("Pick A Bagel", food=1, why="'Also like Pick A Bagel'")], "")
L["t1_p80mwhk"] = ([M("Dame", food=2, service=2, why="'loved it everytime. Great food, warm friendly service'"),
                    M("Crevette", food=-1, service=-2, value=-1, exp=2, vc=True, alt={"food": [-2], "value": [-2]},
                      why="'extremely mid... Everyone seemed unhappy... Food was unmemorable and really expensive'")], "")
L["t1_oa4wcoq"] = ([M("Caffe Panna", named_in="parent", type="cafe_bakery_dessert", food=-2, value=-2, exp=1, wait=-1, vc=True, neg=True,
                      alt={"food": [-3], "wait": [None], "expensiveness": [None]},
                      why="'waited in line there all sold out got what was left overpriced and gross do not waste your time'")], "")
