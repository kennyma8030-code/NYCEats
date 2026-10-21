"""v2 top-ups u0135-u0169, labeled blind."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "labels"))
from common import M  # noqa: E402

L = {}
L["t1_nxy8aoe"] = ([M("Wayan", food=-1, value=-2, exp=2, vc=True, alt={"food": [-2]}, dishes=[("elevated noodles", -1, False)],
                      why="'aggressively mid... charges $40 for a tiny plate of \"elevated\" noodles'")], "")
L["t1_onliuvm"] = ([M("Black seed", "Black Seed Bagels", food=-2, alt={"food": [-3]}, why="'Black seed is terrible.'"),
                    M("Bergen bagels", "Bergen Bagels", food=0, alt={"food": [1, -1]}, why="'Bergen bagels is alright.'"),
                    M("Court St. Bagels", "Court Street Bagels", named_in="ancestor", food=1, why="'The rest are pretty good.'"),
                    M("Smith St. Bagels", "Smith Street Bagels", named_in="ancestor", food=1, why="same"),
                    M("Bagel pub", "Bagel Pub", food=3, dishes=[("breakfast sandwiches", 3, False)], terms=["breakfast sandwiches"],
                      why="'Bagel pub is best (and makes the best breakfast sandwiches)'")], "")
L["t1_oomktid"] = ([M("ishq", "Ishq", food=-2, alt={"food": [-3]}, why="'ishq was awful when i went opening week'"),
                    M("bungalow", "Bungalow", food=-1, why="'extremely unremarkable'"),
                    M("adda EV", "Adda", food=0, alt={"food": [1]}, hood="EV", why="'a bit better but still not amazing'"),
                    M("semma", "Semma", food=2, why="'semma and dhamaka are the best options'"),
                    M("dhamaka", "Dhamaka", food=2, why="same")], "")
L["t1_p9js4n6"] = ([M("Mason Pickle", "Maison Pickle", food=-2, dishes=[("french dip", -2, False)],
                      why="'I must have hit Mason Pickle on a bad day. The French Dip was terrible.'"),
                    M("Hillstone", type="chain", food=3, dishes=[("french dip", 3, False)], terms=["french dip"],
                      why="'Hillstone is the Gold Standard in my opinion.'")], "")
L["t1_orgdu27"] = ([M("Theodora", named_in="title", service=-2, alt={"service": [-3]},
                      why="'That's terrible service from a place of that caliber.'")], "")
L["t1_oisnu9l"] = ([M("Los Tacos No 1", "Los Tacos No. 1", food=-3, neg_ok=True, hood="Union Sq",
                      why="'I loved Los Tacos No 1 until I got food poisoning from the one in Union Sq twice. Now I just can't go back'")], "")
L["t1_oigm53n"] = ([M("La Tete d’Or", "Le Tête d'Or", also=("la tete dor",), food=-2, atmosphere=1, dishes=[("steaks", -2, False)],
                      terms=["steak"], why="'Was not impressed... the vibe was good but the steaks were awful'")], "")
L["t1_oofppn4"] = ([M("Hill Country", food=1, alt={"food": [0, 2]}, dishes=[("brisket", 2, False), ("sides", -2, False)], terms=["brisket", "bbq"],
                      why="'The brisket... is very good most of the time, though the sides are kinda terrible these days'")], "")
L["t1_p2axkfn"] = ([M("francie", "Francie", food=-2, alt={"food": [-3]}, why="'francie was terrible'")], "")
L["t1_p8rmvk2"] = ([M("El Taco", food=-2, neg_ok=True, why="'it was awful the second time. That was enough for me to not go back ever again'"),
                    M("Los Tacos", "Los Tacos No. 1", food=2, alt={"food": [1]}, why="'where the tacos are always consistent'")], "")
L["t1_p0ypxkl"] = ([M("Brennan and Carr", "Brennan & Carr", food=-3, service=-2, dishes=[("fries", -2, False), ("sandwich", -3, False)],
                      why="'our food was so bad we... said this is cold and awful... Cold fries, gross sandwich... sodaa never arrived'")], "")
L["t1_p536xrh"] = ([M("Glin Thai Bistro", food=2, alt={"food": [3]}, exp=0, hood="Fort Greene/Clinton Hill",
                      dishes=[("mango sticky rice", 2, False)], terms=["mango sticky rice"],
                      why="'amazing mango sticky rice that makes Ayadas feel like dogshit. $13, not the best or worst price'"),
                    M("Ayadas", "Ayada", food=-2, alt={"food": [-1]}, dishes=[("mango sticky rice", -2, False)], why="'feel like dogshit' by comparison")], "")
L["t1_p7uqwca"] = ([M("Il Cortile", named_in="parent", food=-3, value=-1, neg_ok=True, alt={"food": [-2], "value": [None]},
                      dishes=[("filet mignon", -3, False), ("potato side", -2, False)],
                      why="'went to that place once and never again... a well done tire steak... $10 extra for a soggy bland potato'")], "")
L["t1_oqgs3t6"] = ([M("Kabawa", food=2, service=2, why="'Everything I ate was great, and the service was wonderful.'"),
                    M("Tatiana", food=2, service=-2, alt={"food": [1], "service": [-3]},
                      why="'most everything was good, some even great, but the service was terrible'")], "")
L["t1_p3x6c50"] = ([M("Cervos", "Cervo's", named_in="parent", food=-1, value=-2, exp=1, vc=True, alt={"expensiveness": [None]},
                      why="'i don't think it's gross but agree with overrated. mostly think it's overpriced'")], "")
L["t1_nj60vhm"] = ([M("cote", "Cote", named_in="title", service=-2, food=-2, alt={"food": [None]},
                      why="'His restaurants have bad service... actually terrible'"),
                    M("cocodaq", "Coqodaq", also=("cocodaq",), service=-2, food=-2, alt={"food": [-1]},
                      why="'Don't get me started on the cocodaq menu items.'")], "")
L["t1_notfai2"] = ([M("Lillia", "Lilia", food=2, wait=-2, why="'actually was good but not worth how hard it is to go'"),
                    M("Lucali", wait=-2, first=None, why="'lining up at 4 to eat at 6'"),
                    M("Carbone", first=None, alt={"food": [-1]}, why="hype-wave reference"),
                    M("Don Angie", first=None, alt={"food": [-1]}, why="hype-wave reference")], "")
L["t1_o024rzs"] = ([*[M(r, c, food=1, terms=["tacos"], why="taco-crawl list") for r, c in
                      [("La Contenta", None), ("Biria LES", "Birria LES"), ("Essex Taqueria", None), ("Taco morles", "Tacos Morales")]],
                    M("Carnita Ramirez", "Carnitas Ramirez", food=2, terms=["tacos"], why="'But I would put Ramirez on your taco crawl.'")], "")
L["t1_ozkzz26"] = ([M("Javelina", food=2, alt={"food": [3]}, dishes=["queso"], terms=["queso"], why="'Javelina is the best answer'"),
                    M("cowgirl", "Cowgirl", food=1, hood="the village", terms=["queso"], why="other option"),
                    M("kelloggs diner", "Kellogg's Diner", food=1, hood="Brooklyn", terms=["queso"], why="other option")], "")
L["t1_njpbhzm"] = ([M("Minetta tavern", "Minetta Tavern", food=1, why="rec"),
                    M("the groove", "The Groove", type="bar", food=1, terms=["live music"], why="'(live music venue)'"),
                    M("Terra blues", "Terra Blues", type="bar", food=1, terms=["blues club"], why="'(blues club)'")],
                   "Comedy Cellar is a comedy club.")
L["t1_nx532u2"] = ([M("Rolos", "Rolo's", food=1, terms=["bread"], why="answer for bread and butter"),
                    M("Shewolf", "She Wolf Bakery", type="cafe_bakery_dessert", food=1, terms=["bread"], why="'anything that carries Shewolf'"),
                    M("Diner", hood="Brooklyn", food=1, why="'Diner in Brooklyn is the one I can think of'"),
                    M("Semilla", closed=True, why="'Pour one out for the ghost of Semilla… had the BEST BREAD.'")], "")
L["t1_ofnmpk3"] = ([M("Carbone's", "Carbone", wait=-2, alt={"wait": [-1]}, first=None, why="'Carbone's picks you'"),
                    M("Don Agnie", "Don Angie", food=1, why="'probably your best bet'")], "")
L["t1_nt8pi72"] = ([M("‘ino", "'ino", also=("ino",), closed=True, why="closed-restaurants thread: 'were the best'"),
                    M("‘inoteca", "'inoteca", also=("inoteca",), closed=True, why="same")], "")
L["t1_o8a9ipa"] = ([M("Blue haven", "Blue Haven", type="bar", atmosphere=1, alt={"atmosphere": [2]}, hood="murray hill",
                      terms=["college bar", "march madness"], why="'will undoubtedly be crazy' (high-energy crowd)")], "")
L["t1_oanwd0s"] = ([M("Hunter's Steak and Ale", food=1, alt={"food": [2]}, dishes=[("burger", 1, False)], conf="medium",
                      why="'One of my favorite memories... eating the burger'")], "")
L["t1_nx972eu"] = ([M("Saravana Bhavan", food=1, terms=["indian"], why="rec"),
                    M("King Dumpling", food=1, terms=["dumplings"], why="rec"),
                    M("Regina's Grocery", food=3, dishes=[("italian sandwich", 3, False)], terms=["italian sandwich"],
                      why="'the best Italian sandwich the city has to offer'")], "")
L["t1_nl7lu2c"] = ([M("Via Carota", first=None, why="'Via Carota is the T-Swift favorite': reference")], "")
L["t1_ngyenua"] = ([M("Sey", "Sey Coffee", type="cafe_bakery_dessert", food=1, terms=["coffee"], why="answer"),
                    M("suited", "Suited", type="cafe_bakery_dessert", food=1, terms=["coffee"], why="answer")], "")
L["t1_njicv92"] = ([M("L’industrie", "L'Industrie Pizzeria", food=-1, wait=-2, why="'NOT the best pizza, it's just in the West Village and trendy... that long ass line'"),
                    M("Village Square", "Village Square Pizza", food=1, alt={"food": [2]}, why="implied better, next door"),
                    M("Mama’s Too", "Mama's Too", food=2, alt={"food": [1]}, why="'Even Mama's Too around the corner is better.'")], "")
L["t1_ogzd5yc"] = ([M("Nangma", "Nangma Restaurant", named_in="title", first=False, why="'Been meaning to try their breakfast option': reference"),
                    M("Asian bowl", "Asian Bowl", food=2, dishes=[("mohinga", 2, False)], terms=["mohinga", "burmese"],
                      why="'Asian bowl does my favorite mohinga'"),
                    M("little Myanmar", "Little Myanmar", food=-2, alt={"food": [-1]}, why="'a shadow of its former glory... Food there is barely flavored'"),
                    M("yuns Asian cafe", "Yun Cafe", closed=True, why="former incarnation; a reply misses it")], "")
L["t1_oegqv6e"] = ([M("Popup bagels", "Pop Up Bagels", type="chain", alt={"food": [-1]}, dishes=[("hotel butter", -1, False)],
                      why="'I prefer many other bagel places... the recipe changed for a DIP that I had previously enjoyed'")], "")
L["t1_o5wpinw"] = ([M("Chinese Tuxedo", food=0, atmosphere=2, alt={"food": [1, -1]}, why="'the best interior, but the food is just solid, nothing particularly good'"),
                    M("Potluck Club", food=1, atmosphere=2, alt={"food": [2]}, terms=["cantonese banquet"],
                      why="'a wonderful kitschy vibe and some very fun takes on Cantonese banquet classics'"),
                    M("Phoenix Palace", food=2, alt={"food": [3]}, dishes=[("crab egg noodle", 2, False), ("lobster sticky rice", 2, False)],
                      why="'I think they have the best food of the four. Their crab egg noodle is amazing'"),
                    M("Kisa", food=-1, alt={"food": [0]}, terms=["korean"],
                      why="'I don't think the food is really that much better than your average traditional Korean joint'")], "")
L["t1_or4qg3r"] = ([M("El Nuevo Amanecer", food=0, atmosphere=1, alt={"food": [1]}, hood="Essex", why="'not amazing but fun'")], "")
L["t1_oxx2xny"] = ([M("Pinch", "Pinch Chinese", first=None, alt={"food": [-1]}, dishes=["soup dumpling"],
                      why="'most chinese people probably don't think Pinch has the best soup dumpling'"),
                    M("Tonchin", first=None, alt={"food": [-1]}, terms=["ramen"], why="'highly contestable if Tonchin is better'")], "")
L["t1_p7sh9cd"] = ([M("Cote", food=-2, neg_ok=True, alt={"food": [-1]},
                      why="'Cote is westernized inauthentic fusion food... automatically a no go for me'"),
                    M("Hanam", "Hanam BBQ", oos=True, hood="Palisades Park NJ", why="New Jersey")], "Sonamu House only in the parent.")
