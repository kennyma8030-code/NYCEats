"""v2 top-ups u0000-u0029, labeled blind (no stored/model output, no mined_for shown)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "labels"))
from common import M  # noqa: E402

L = {}
L["t1_ok6aidm"] = ([
    M("Central Park Boathouse", food=-1, value=-2, vc=True, neg=True, alt={"value": [-1]},
      why="'Skip... do not waste your money on the mediocre food'"),
    M("Tavern on the Green", food=-1, value=-2, vc=True, neg=True, alt={"value": [-1]}, why="same"),
    M("Grand Central Oyster Bar", food=2, alt={"food": [1]}, terms=["martinis", "oysters"],
      why="'go to the bar... strongest martinis in NYC'"),
    M("Sylvia's", food=1, hood="Harlem", why="'Harlem is wonderful: Sylvia's'"),
    M("Marcus Samuelsons Red Rooster", "Red Rooster", food=1, hood="Harlem", why="same"),
    M("Hamburger America", food=1, value=1, exp=-1, alt={"value": [None], "expensiveness": [None]}, terms=["burger", "affordable"],
      why="'If you need a good affordable meal'"),
    M("Lure Bar", "Lure Fishbar", food=1, hood="Soho", why="'a New Yorker classic'"),
    M("Balthazar", food=1, why="'a New Yorker classic'"),
    M("Veseleka", "Veselka", food=1, hood="East Village", terms=["ukrainian"], why="'the iconic Veseleka'"),
    M("Theodora", food=1, terms=["fire grill", "mediterranean"], why="'Try to nab a resy at Theodora'"),
    M("Greenpoint Fish and Lobster company", "Greenpoint Fish & Lobster Co.", food=1, why="same list"),
], "")
L["t1_obxc98y"] = ([
    *[M(n, food=1, hood="UES", why="local recs list") for n in ["Au Zaatar", "Bagel Works", "The Jeffrey"]],
    M("Space Market", food=1, hood="UES", dishes=["BEC"], terms=["late night", "bec"], conf="medium", why="for late night or morning BEC"),
    M("Tramway Diner", food=-2, neg=True, alt={"food": [-1, None]}, why="'Only spot to avoid... so many violations they've been shut down'"),
    M("Ritz Diner", first=None, why="reference: combined with Tramway"),
], "")
L["t1_ngokxjl"] = ([
    M("Wolfgang’s", "Wolfgang's Steakhouse", named_in="comment", food=2,
      dishes=[("porterhouse for two", 1, False), ("ny sirloin", 1, False), ("onion rings", 2, False),
              ("creamed spinach", 1, False), ("fillet", -1, True)],
      terms=["porterhouse", "steakhouse", "onion rings"], why="'Can't go wrong'; 'Skip the fillet'"),
    M("Benjamin", "Benjamin Steakhouse", food=2, why="'Can't go wrong with Wolfgang's or Benjamin'"),
    M("Luger", "Peter Luger", also=("luger",), food=-1, neg=True, alt={"food": [None]}, why="'Forget about Luger.'"),
], "")
L["t1_p831xj4"] = ([
    M("Wonder", type="food_hall", food=-2, why="'Wonder food is reheated microwave food'"),
    M("pop salad", "Pop Salad", food=1, value=1, exp=-1, alt={"value": [None]}, why="'$10 bowls that are decent'"),
    M("el diez", "El Diez", food=1, value=1, exp=-1, alt={"value": [None]}, why="same"),
    M("chipotle", "Chipotle", type="chain", first=None, why="'Like a cheaper chipotle': reference"),
], "Grubhub is an app; bodegas generic.")
L["t1_nxp7fd1"] = ([
    M("Petit Chou", type="cafe_bakery_dessert", food=-1, neg=True, alt={"food": [None]}, why="'I'd easily skip Petit Chou and Hanis'"),
    M("Hanis", "Hani's Bakery", type="cafe_bakery_dessert", food=-1, neg=True, alt={"food": [None]}, why="same"),
    M("Smor", "Smør", also=("smor",), type="cafe_bakery_dessert", food=1, why="'Choose one between Smor and la cabra'"),
    M("la cabra", "La Cabra", type="cafe_bakery_dessert", food=1, why="same"),
    M("From Lucie", type="cafe_bakery_dessert", food=1, dishes=[("cake", 1, False)], why="'get a cake from From Lucie'"),
], "")
L["t1_obvlp3r"] = ([
    M("sushi yasaka", "Sushi Yasaka", food=2, hood="upper west side", why="'It is very good... it's worth it'"),
    M("Los tacos No. 1", "Los Tacos No. 1", wait=1, alt={"wait": [None]}, why="'would probably have a shortish line for dinner'"),
    M("levain bakery", "Levain Bakery", type="cafe_bakery_dessert", food=1, alt={"food": [None]},
      why="lives close; sad visitors pick Crumbl instead"),
    M("crumble cookies", "Crumbl", also=("crumble",), type="chain", food=-1, alt={"food": [None]},
      why="'You can get crumble cookies in a random strip mall in Virginia!'"),
], "")
L["t1_nobth7a"] = ([
    M("Taqueria Ramirez", food=2, wait=-1, atmosphere=-1, dishes=[("al pastor tacos", 2, False)], terms=["al pastor", "tacos"],
      why="'very good al pastor tacos. There might be a line and there's barely any seating'"),
    M("Russ and Daughter’s", "Russ & Daughters", food=2, wait=1, alt={"food": [1]}, hood="Hudson Yard's",
      dishes=[("lox and cream cheese", 3, False), ("bagels", -1, False)], terms=["lox", "cream cheese"],
      why="'go to the Hudson Yard's location for no wait... Lox and cream cheese are elite but... the bagels themselves aren't up to par'"),
    M("Tompkins Square Bagels", food=2, wait=-1, atmosphere=-1, alt={"atmosphere": [None]}, terms=["bagels"],
      why="'consistently good but will have a line and barely any seating'"),
    M("Los Tacos #1", "Los Tacos No. 1", food=-1, wait=-2, alt={"wait": [-1]}, terms=["tacos"],
      why="'idk why everyone is raving... average tacos with huge lines'"),
    M("Ramirez", "Carnitas Ramirez", food=2, conf="medium", why="'Ramirez and El Bronco are way better'"),
    M("El Bronco", "Tacos El Bronco", food=2, why="same"),
    M("L’Industrie", "L'Industrie Pizzeria", food=3, wait=-1, dishes=[("fig jam bacon", 3, False), ("burrata", 3, False)],
      hood="Williamsburg", terms=["fig jam bacon", "burrata"], why="'the hype is worth it. Fig jam bacon and Buratta slices are elite'"),
    M("Joe’s", "Joe's Pizza", food=-1, neg=True, alt={"food": [None]}, why="'Joe's + Prince St: skip entirely'"),
    M("Prince St", "Prince Street Pizza", food=-1, neg=True, alt={"food": [None]}, why="same"),
    *[M(r, c, food=1, why="pizza alternatives list") for r, c in [
        ("Village Square", "Village Square Pizza"), ("Bleeker St. Pizza", "Bleecker Street Pizza"), ("Slicehaus", None),
        ("Scarr’s", "Scarr's Pizza"), ("Upside", "Upside Pizza"), ("Grand Street", "Grand Street Pizza"),
        ("Cello’s", "Cello's Pizzeria"), ("NY Pizza Suprema", None), ("Unregular", "Unregular Pizza"), ("Marinara", "Marinara Pizza")]],
    M("Wah Fung", "Wah Fung No. 1", food=2, value=2, exp=-2, wait=-2, atmosphere=-1, alt={"value": [3], "wait": [-1]},
      dishes=[("char siu", 1, False), ("crackling pork belly", 1, False)], terms=["char siu", "crackling pork belly", "cheap"],
      why="'extremely consistent and unbelievably cheap for the quality... 30min + line... No seating'"),
    M("Katz’s", "Katz's Delicatessen", food=2, value=1, exp=1, wait=-1, service=1, alt={"value": [None]},
      why="'Worth it. Sandwich is expensive but the portions are huge. Line is long and service is snappy'"),
], "Long annotated list.")
L["t1_off9oh7"] = ([
    M("Magnolia", "Magnolia Bakery", type="chain", food=-1, neg=True, alt={"food": [None]}, dishes=[("banana pudding", 1, False)],
      why="'skip Magnolia (unless you're looking for banana pudding)'"),
    M("Mollys Cupcakes", "Molly's Cupcakes", type="cafe_bakery_dessert", food=1, why="'try Mollys Cupcakes instead'"),
    M("2 bros", "2 Bros Pizza", type="chain", food=-1, why="'not a fan'"),
], "")
L["t1_ow8iwda"] = ([
    *[M(r, c, food=1, why="bagel list") for r, c in [("Tompkins square", "Tompkins Square Bagels"), ("liberty", "Liberty Bagels"),
                                                    ("Leo’s", "Leo's Bagels")]],
    M("joes", "Joe's Pizza", food=1, neg_ok=True, alt={"value": [-1]},
      why="'an institution and def worth a visit but avoid the times sq location (and carmine st seems to have raised prices)'"),
    M("Lucia", "Lucia Pizza", food=2, hood="ave x", why="'for actual great slices'"),
    M("Jonnys", "Johnny's Pizzeria", food=2, why="same"),
    M("diamond slice", "Diamond Slice", food=2, why="same"),
    M("Lori Jane", food=2, alt={"food": [3]}, terms=["steak frites"], why="'the best default option' for steak frites"),
], "Halal cart is generic.")
L["t1_o4dhki9"] = ([
    M("Nakazawa", "Sushi Nakazawa", named_in="comment", food=-1, alt={"food": [-2]}, terms=["omakase", "hikarimono"],
      why="'my experience at Nakazawa... pretty underwhelming'"),
    M("Noz 17", food=2, why="'a much better choice at a similar price point'"),
], "")
L["t1_obtv49c"] = ([], "Media sources, not places.")
L["t1_onfmvcv"] = ([
    M("Black Seed", "Black Seed Bagels", food=1, why="'I'm fond of Black Seed'"),
    M("Kossar’s", "Kossar's Bagels & Bialys", food=1, why="'Kossar's is the OG'"),
    M("Tompkins", "Tompkins Square Bagels", food=1, first=None, why="'lots of people swear by Tompkins'"),
    M("Russ and Daughters", "Russ & Daughters", food=2, atmosphere=-2, neg_ok=True, alt={"atmosphere": [-1]},
      why="'I mostly try to avoid Russ and Daughters because it's a zoo, but it's great'"),
], "")
L["t1_nw0uyng"] = ([
    M("Apollo Bagels", food=1, hood="EV", why="rec"),
    M("Joe & Pats", "Joe & Pat's", food=1, hood="EV", why="rec"),
    M("L’Industrie", "L'Industrie Pizzeria", food=1, why="rec"),
    M("Mama Too’s", "Mama's Too", food=1, why="rec"),
    M("John’s on Bleecker St", "John's of Bleecker Street", food=1, why="rec"),
    M("4 Charles", "4 Charles Prime Rib", neg=True, alt={"food": [-1]}, why="'For burgers, I'd skip 4 Charles'"),
    M("Wild Cherry", food=1, terms=["burgers"], why="rec for burgers"),
    M("Minetta Tavern", food=1, terms=["burgers"], why="rec for burgers"),
    M("Bubby’s", "Bubby's", neg=True, alt={"food": [-1]}, why="'I'd skip Bubby's'"),
    M("Clinton St Bakery", "Clinton St. Baking Company", food=1, terms=["pancake breakfast"], why="for pancakes"),
    M("Carnitas Ramirez", food=1, terms=["tacos"], why="rec"),
    M("El Chato", food=1, terms=["tacos"], why="rec"),
    M("Los Tacos", "Los Tacos No. 1", food=1, alt={"food": [None]}, why="'just for diversity'"),
], "")
L["t1_odz9pr0"] = ([
    M("S&P", food=1, why="'Add S&P'"),
    M("Milano market", "Milano Market", neg=True, alt={"food": [-1]}, why="'skip Milano market'"),
    M("Cafe Habana", neg=True, alt={"food": [-1]}, why="'skip... Cafe Habana'"),
    M("Saigutte", "Saiguette", neg=True, alt={"food": [-1]}, why="'replace Saigutte with Banh And Em'"),
    M("Banh And Em", "Banh Anh Em", food=1, why="replacement pick"),
    M("Grays", "Gray's Papaya", food=1, why="'Love Grays but it's way out of your way'"),
    M("Katz's", "Katz's Delicatessen", food=2, dishes=[("hotdogs", 2, False)], why="'Katz's has better hotdogs'"),
    M("Taqueria Ramirez", food=1, why="'Add in Taqueria Ramirez'"),
    M("Frankel's", alt={"food": [-1]}, first=None, why="'a long way to go for a BEC'"),
], "")
L["t1_o81a1qc"] = ([
    M("Per Se", service=1, alt={"service": [None]}, dishes=["oysters and pearls"], first=None,
      why="'at Per Se they would be MOST accommodating to you'"),
    M("chefs table", "Chef's Table at Brooklyn Fare", neg=True, alt={"food": [-1]}, terms=["seafood"],
      why="'Avoid chefs table as it's all seafood and largely uncooked'"),
], "")
L["t1_o4hrti2"] = ([
    M("Amy Ruth's", food=-1, neg=True, terms=["soul food"], why="'I say avoid... NOT the best Soul Food'"),
    M("Sylvia's", food=-1, neg=True, terms=["soul food"], why="same"),
], "")
L["t1_nogqeaw"] = ([
    M("superbueno", "Superbueno", type="bar", neg=True, alt={"food": [-1]}, why="'I would skip superbueno'"),
    M("Paradise Lost", type="bar", food=1, why="alternative"),
    M("Attaboy", type="bar", food=1, why="alternative"),
], "")
L["t1_nocjaxw"] = ([
    M("L’Industrie", "L'Industrie Pizzeria", food=2, why="'Definitely go to L'Industrie'"),
    M("Joe’s", "Joe's Pizza", food=-1, neg=True, why="'Skip Joe's and Prince St entirely - so much better pizza in the city'"),
    M("Prince St", "Prince Street Pizza", food=-1, neg=True, why="same"),
    M("Mama’s Too", "Mama's Too", food=2, why="'for something great but a little different'"),
    M("Katz’", "Katz's Delicatessen", food=3, dishes=[("pastrami", 3, False)], terms=["pastrami"],
      why="'Still the best pastrami in the city'"),
    M("Sarge’s", "Sarge's Deli", first=None, why="'don't think you need to do Katz and Sarge's': reference"),
], "")
L["t1_ozm1y4a"] = ([
    *[M(r, c, type="cafe_bakery_dessert", food=-1, alt={"food": [-2]}, terms=["robusta"], first=None,
        why="listed as robusta shops to avoid for good coffee")
      for r, c in [("Remi Flower & Coffee", None), ("Züri Coffee", "Zuri Coffee"), ("Matto", "Matto Espresso"), ("Cinco", None)]],
    *[M(r, c, type="cafe_bakery_dessert", food=1, alt={"food": [2]}, terms=["3rd wave coffee"], why="'If you want to try good 3rd wave coffee, head to'")
      for r, c in [("Watch house", "WatchHouse"), ("Little Collins", None), ("Current Coffee", None), ("Devocion", "Devoción"),
                   ("Dae Day", None)]],
], "")
L["t1_oo61234"] = ([
    M("The Coop", "The Coop at Double Chicken Please", type="bar", neg=True, alt={"food": [-1]}, why="'Skip The Coop'"),
    M("DCP", "Double Chicken Please", also=("dcp",), type="bar", food=1, why="'just do the main bar at DCP if you can actually get in'"),
    M("Superbueno", type="bar", food=1, atmosphere=2, why="'way better vibes and the food is actually solid'"),
    M("Sip", "Sip & Guzzle", also=("sip guzzle",), type="bar", wait=-2, atmosphere=1, alt={"atmosphere": [None], "value": [-1]},
      why="'cool for the novelty... wait times can be brutal for what you get'"),
], "")
L["t1_ocf83gy"] = ([
    M("Rubrirosa", "Rubirosa", first=None, alt={"wait": [-1]}, why="'Switch out Rubrirosa... unless you have a reservation'"),
    M("Joe and Pats", "Joe & Pat's", food=1, why="replacement"),
    M("Katz’s", "Katz's Delicatessen", food=-1, atmosphere=-1, neg=True, alt={"atmosphere": [None]},
      why="'skip the overrated tourist clusterF at Katz's'"),
    M("S&P Lunch", "S&P", food=1, why="alternative"),
    M("Win Son Bakery", type="cafe_bakery_dessert", food=1, why="alternative"),
], "")
L["t1_palow1a"] = ([
    M("Red hook", "Red Hook Tavern", also=("rht",), food=-1, neg=True, alt={"food": [None]},
      why="'Red hook pretty much copied the Peter Luger burger... I'd skip RHT'"),
    M("PL", "Peter Luger", also=("luger", "pl"), food=1, wait=1, alt={"food": [2]}, dishes=[("luger burger", 1, False)],
      terms=["burger", "lunch"], why="'much easier to get at PL... go for the Luger burger'"),
], "")
L["t1_pa086iq"] = ([
    M("Mermaid Inn", food=2, terms=["happy hour", "oysters"], neg_ok=True, why="'Really solid happy hour oysters and drinks... skip Times Square location'"),
    M("Maison Premiere", food=1, first=False, alt={"food": [None]}, terms=["oysters"], why="'Ive never been here but... impressed'"),
    M("Grand Central Oyster bar", "Grand Central Oyster Bar", food=1, alt={"food": [None]}, why="'10 years ago... really cool'"),
    M("Seawolf", food=-2, neg=True, why="'Can skip Seawolf... Seawolf is actively bad'"),
    M("Grey Lady", neg=True, alt={"food": [-1]}, why="'Can skip... Grey Lady'"),
], "")
L["t1_ok6its6"] = ([
    M("Sistina", food=-1, why="'Sistina isn't too exciting'"),
    M("Marcel", food=1, first=None, hood="Upper East Side", why="'try the brand new Marcel'"),
    M("Chez Fifi", food=1, alt={"food": [2]}, first=None, why="'the top rated Chez Fifi'"),
    M("Le V’eau D’Or", "Le Veau d'Or", food=1, why="rec"),
    M("Benelman’s", "Bemelmans Bar", also=("bemelmans",), type="bar", food=1, why="'Classic drinks'"),
    M("The Mark", type="bar", food=1, why="'Classic drinks'"),
    *[M(r, c, food=1, why="'if you want Italian check out'") for r, c in [("Rezdora", None), ("I Sodi", None), ("Via Carota", None),
                                                                          ("Roscioli", None)]],
    M("The Plaza", food=-1, alt={"food": [-2]}, why="'went downhill ages ago and has been boring'"),
    M("Baccarat hotel", "Baccarat Hotel", food=2, atmosphere=2, terms=["afternoon tea"], why="'the nicest one with lovely ambience'"),
    *[M(n, food=1, exp=-1, alt={"expensiveness": [None]}, terms=["afternoon tea"], why="lower-cost afternoon tea")
      for n in ["The Whitby", "The Crosby", "The Warren"]],
    M("The Fulton", food=1, atmosphere=0, alt={"atmosphere": [1, -1]}, why="'better than Carne Mare... better view; it is kind of corporate'"),
    M("Carne Mare", alt={"food": [-1]}, first=None, why="loses the comparison"),
    *[M(n, type="bar", food=1, terms=["cocktails"], why="cocktail bar recs") for n in
      ["Manhatta", "Overstory", "Little Shop", "The Red Room", "Sip & Guzzle", "Angel’s Share", "Martiny’s",
       "Experimental Cocktail Club", "Tigre"]],
    M("Boathouse", "Central Park Boathouse", neg=True, alt={"food": [-1]}, why="'I would skip Boathouse and Tavern'"),
    M("Tavern", "Tavern on the Green", neg=True, alt={"food": [-1]}, why="same"),
], "")
L["t1_o1xbybo"] = ([
    M("casa mono", "Casa Mono", food=-1, neg=True, why="'skip casa mono... I was not a big fan'"),
    M("golden swan", "Golden Swan", food=1, why="'I liked golden swan'"),
    M("gramercy tavern", "Gramercy Tavern", food=1, why="'try for gramercy tavern'"),
    M("ci Simao", "Ci Siamo", also=("ci simao",), food=1, why="same"),
], "")
L["t1_nib6ys7"] = ([], "Cuisines only.")
L["t1_o0ygtv8"] = ([M("Parm", food=2, dishes=[("spicy rigatoni", 2, False)], terms=["spicy rigatoni"],
                      why="viral food 'actually worth the hype': spicy rigatoni at Parm")], "")
L["t1_o935pxc"] = ([], "")
L["t1_nqgqxyg"] = ([], "")
L["t1_nmzla94"] = ([
    M("cipriani", "Cipriani", food=2, dishes=[("merengue cake", 2, False)], terms=["merengue cake"], why="'The merengue cake... is fantastic!'"),
    M("Lucia", "Lucia Pizza", food=1, why="'have good slices'"), M("prince street", "Prince Street Pizza", food=1, why="same"),
    M("la esquina", "La Esquina", food=1, terms=["tacos"], why="'The taco stand above la esquina is good'"),
    *[M(r, c, food=2, terms=["mediterranean"], why="'all serve excellent Mediterranean food'")
      for r, c in [("12 chairs", "12 Chairs"), ("Shuka", None), ("Cleveland", "The Cleveland")]],
    M("Rubirosa", food=-1, why="'I think its overrated'"),
    M("Parm", food=3, dishes=[("baked ziti", 3, False)], terms=["baked ziti"], why="'Parm serves the best baked ziti'"),
    M("Dominique Ansel", type="cafe_bakery_dessert", food=1, alt={"food": [2]}, dishes=[("cronut", None, True), ("chocolate chip cookie", 2, False)],
      why="'Don't bother waiting on line for a cronut... chocolate chip cookie is awesome'"),
    M("Black Seed", "Black Seed Bagels", food=2, alt={"food": [3]}, why="'probably the best bagels'"),
    M("Russ and Daughters", "Russ & Daughters", food=2, alt={"food": [3]}, why="same"),
    M("Balthazar", atmosphere=2, alt={"food": [2], "atmosphere": [3]}, wait=-1,
      why="'one of the best restaurants in NYC. Not necessarily the food, but... total package. A bit busy'"),
], "")
