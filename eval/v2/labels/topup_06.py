"""v2 top-ups u0170-u0204, labeled blind."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "labels"))
from common import M  # noqa: E402

G = dict(type="grocery_market", oos=True)
L = {}
L["t1_o2c0eer"] = ([M("Grand St. Pizza", "Grand Street Pizza", food=2, value=1, exp=-1, atmosphere=2, alt={"value": [None]},
                      terms=["neighborhood slice", "cozy", "wine"],
                      why="'a very good neighborhood slice at friendlier neighborhood prices. It's also super cozy'"),
                    M("Ceres", "Ceres Pizza", food=2, wait=-1, alt={"wait": [None]},
                      why="'Ceres is my favorite but it's pies only and there's a fucked up ordering system'"),
                    M("Scarr's", "Scarr's Pizza", food=-1, wait=-1, why="'overrated and not worth it if you have to wait in line'"),
                    M("The Pickle Guys", **G, why="retail"), M("Sweet Pickle Books", type="other", oos=True, why="bookstore")], "")
L["t1_ok57sgz"] = ([M("bungalow", "Bungalow", wait=-2, first=None, why="'A bungalow res is basically impossible.'"),
                    M("adels halal", "Adel's Famous Halal Food", type="food_truck", wait=-2, neg_ok=True, why="'adels halal isnt worth the line'"),
                    M("soothr", "Soothr", food=-1, alt={"food": [0]}, why="'soothr isnt the best thai in the city'")], "")
L["t1_njjterg"] = ([M("rubirosa", "Rubirosa", atmosphere=2, food=-1, alt={"food": [0]}, dishes=[("pizza", -1, False)],
                      why="'I love rubirosa as a vibe and a restaurant, but that is not the second best pizza even in the neighborhood'")], "")
L["t1_oyz8k9n"] = ([M("Chama Mama", food=1, why="'I like Chama Mama and have recommended it... but... not one of the best 38'")], "")
L["t1_od9a6hm"] = ([M("Tanoreen", named_in="parent", food=-1, alt={"food": [-2]},
                      why="'everything just tastes like it's drowning in pomegranate molasses'")], "")
L["t1_pb1y8yh"] = ([M("Golden Bull handmade noodles", food=1, alt={"food": [2]},
                      dishes=[("noodles", 2, False), ("rou jia mo", -3, True)], terms=["handmade noodles"],
                      why="'pretty good noodles! Don't get the sandwiches / rou jia mo though, it was terrible'"),
                    M("Xing Fu Tang", food=1, terms=["boba"], why="'welcome additions... definitely the best in the area'"),
                    M("Joju", food=1, alt={"food": [0]}, terms=["vietnamese"], why="'fine and I'd go again'"),
                    M("MalaTang", food=1, alt={"food": [0]}, why="same")], "Unnamed coconut place.")
L["t1_nhwr3g4"] = ([M("Utopia bagels", "Utopia Bagels", food=-1, hood="Whitestone",
                      why="'I was completely underwhelmed compared to the hype. Too pillowy soft inside for me.'"),
                    M("Zabar’s", "Zabar's", **G, why="grocery")], "")
L["t1_o1kxy8f"] = ([], "Meal-prep companies (Factor, Eat Clean Bro, Daily Harvest), not places.")
L["t1_on3wlkb"] = ([M("Cafe Panna", "Caffe Panna", type="cafe_bakery_dessert", food=0, alt={"food": [-1]},
                      why="'I think Cafe Panna is 'fine'... falls down on flavors'"),
                    M("il laboratorio del gelato", "Il Laboratorio del Gelato", type="cafe_bakery_dessert", food=2,
                      dishes=[("sorbets", -1, False)], terms=["gelato"], why="'my favorite ice cream shop in the city atm... sorbets tend to have a bad texture'"),
                    M("Supermoon Bakehouse", type="cafe_bakery_dessert", food=2, dishes=[("passionfruit", 2, False)],
                      why="'flavors tend to be super punchy, which makes me happy'"),
                    M("Salt and Straw", type="chain", food=-2, alt={"food": [-1]}, dishes=[("ice cream", -2, False), ("sorbets", 1, False)],
                      why="'ice cream is pants on head bad... but the sorbets are good'"),
                    M("ice and vice", "Ice & Vice", closed=True, why="'rip ice and vice'")], "")
L["t1_nivanw4"] = ([M("Mido's", type="food_truck", food=2, why="'second favorite behind Adel's'"),
                    M("Adel's", "Adel's Famous Halal Food", type="food_truck", food=2, alt={"food": [3]}, why="favorite"),
                    M("Sammy's", "Sammy's Halal", type="food_truck", food=-1, why="'over the last 15 years they've gone down'"),
                    M("Santa", type="food_truck", food=1, why="carts in front of Trader Joe's: enjoyed platters"),
                    M("Farook", type="food_truck", food=1, why="same"),
                    M("Trader Joe's", **G, why="landmark")], "Unnamed carts on 74th & 35th Ave.")
L["t1_nl13u2v"] = ([M("Royal Queen", food=1, wait=1, alt={"food": [2]}, terms=["dim sum"], why="'Royal Queen, always. Never have to worry about a wait'"),
                    M("Golden Mall", type="food_hall", food=2, alt={"food": [1]}, terms=["desserts"], why="'for the best desserts'"),
                    M("Good Coconut", type="stall_vendor", food=2, why="'Good Coconut is so good I ate it on the subway'"),
                    M("Jing fong", "Jing Fong", food=-1, why="'isn't as good since they moved'"),
                    M("Asian jewels", "Asian Jewels Seafood", food=1, exp=1, alt={"value": [-1]}, why="'is good, but kinda pricey'"),
                    M("East Harbor", "East Harbor Seafood Palace", food=1, wait=-2, why="'also good, but the wait is too much on weekends'")], "")
L["t1_p7swuq4"] = ([M("Los tacos", "Los Tacos No. 1", named_in="comment", food=1, value=-1, exp=1, vc=True, alt={"food": [0, 2]},
                      why="'may be the best tacos in NY but they aren't up to par... you need to spend 25 dollars to be full'")], "")
L["t1_oleo8tw"] = ([M("Kabawa", named_in="ancestor", food=-1, value=-2, vc=True, rc=False, rt=False,
                      dishes=[("duck sausage", 1, False), ("goat", 1, False), ("matrimony", -2, False), ("starters", 2, False)],
                      why="'not inventive... enough to justify the price. Duck sausage and goat where just nice. Matrimony... ridiculous'"),
                    M("Tatiana", food=0, alt={"food": [-1]}, first=None, why="'I actually prefer Tatiana to Kabawa, and I don't rate Tatiana too highly'")], "")
L["t1_np1rzga"] = ([M("H&H", "Hale and Hearty", also=("hale hearty",), named_in="comment", food=1, exp=-1, alt={"food": [2]},
                      hood="Metrotech Center", terms=["quick lunch", "soup"],
                      why="'my go-to for a quick inexpensive lunch... Glad to know they've risen from the ashes'")], "")
L["t1_nt72q0q"] = ([M("Rosemary's Pantry", closed=True, dishes=["chicken parm sub"], why="closed; 'an amazing chicken parm sub that I miss dearly'"),
                    M("rosemary's east", "Rosemary's East", alt={"food": [-1]}, why="'the sandwich they put on the lunch menu to replace it... its not the same'")], "")
L["t1_nt1f4q9"] = ([M("Rose Bar", type="bar", closed=True, hood="Gramercy Park Hotel", why="drink-spiking story; 'Rose Bar closed during the pandemic'"),
                    M("Spin", type="bar", first=True, why="ping pong club: reference")], "")
L["t1_nxx9fju"] = ([M("Pig and Khao", closed=True, hood="LES", why="'Pig and Khao on the LES closed'")], "")
L["t1_oi4olgd"] = ([M("Honest Chops", named_in="parent", **G, closed=True, why="butcher shop (retail), closed")], "")
L["t1_ovl5qns"] = ([], "About the 311 response.")
L["t1_opfxsbm"] = ([M("Fried Dumpling", hood="Mosco street", first=None, why="'is this the same one that used to be on 99 Allen?': reference")], "")
L["t1_oulahyh"] = ([M("Stage Restaurant", closed=True, why="'RIP Stage Restaurant too'")], "")
L["t1_kehkdzw"] = ([M("Hop Shing", closed=True, dishes=["char siu bao"], why="'Hop Shing's char siu bao was better but now that it's closed'"),
                    M("Mei Lai Wah", food=3, alt={"food": [2]}, dishes=[("char siu bao", 3, False)], terms=["char siu bao"],
                      why="'now that it's closed Mei Lai Wah is the best'")], "")
L["t1_ouzhcwi"] = ([M("Mars 2112", closed=True, why="permanently closed favorites thread")], "")
L["t1_nt6vofp"] = ([M("King Yum", named_in="comment", closed=True, why="'When we went for the last time before they closed'")], "")
L["t1_nt7m9b9"] = ([M("Norma’s", "Norma's", named_in="comment", closed=True, why="'Norma's closed?! Oh no, they were my favorite brunch'")], "")
L["t1_nq2pbq7"] = ([M("Meadow Lane", named_in="title", food=-2, atmosphere=-1, alt={"atmosphere": [None]}, first=None,
                      why="'devoid of any personality or taste'"),
                    M("Gourmet Garage", **G, why="grocery"), M("Citarella", **G, why="grocery"),
                    M("Jefferson Market", **G, closed=True, why="grocery (RIP)")], "")
L["t1_o0w008w"] = ([M("Menkoi Sato", named_in="parent", closed=True, conf="medium",
                      why="'I believe they closed for good' (a reply says they plan to reopen)")], "")
L["t1_nwqkz99"] = ([M("mama finas", "Mama Fina's", named_in="comment", closed=True, why="'Looks like mama finas is permanently closed'")], "")
L["t1_o78zhdw"] = ([M("Frenchette", food=-1, first=False, dishes=[("croissants", -1, False)],
                      why="'haven't even tried Frenchette bc I saw what their croissants look like and knew it wouldn't come close'"),
                    M("Petrossian", closed=True, why="'Petrossian (it was near Central Park before covid)... now they only sell caviar'"),
                    M("arcade", "Arcade Bakery", closed=True, why="'after those two closed'")], "")
L["t1_o3g6sz7"] = ([M("Chikalicious", named_in="comment", closed=True, why="'Chikalicious closed'")], "")
L["t1_ocj2aaa"] = ([M("Village Yokocho", closed=True, why="'Too bad it closed down'")], "")
L["t1_o0ygykz"] = ([M("katz", "Katz's Delicatessen", named_in="ancestor", wait=1, alt={"wait": [None]}, rc=False, rt=True,
                      why="'I never had to stand in line outside before COVID in probably a dozen visits'")], "")
L["t1_o4r2lzd"] = ([M("Eataly", named_in="parent", type="food_hall", food=1, value=1, alt={"value": [None]},
                      why="'I stock up during the sales on good pasta and olive oil'")], "")
L["t1_nusknxy"] = ([M("Penny", named_in="title", amb=True, dishes=["carrot cake ice cream sandwich"],
                      why="explains the brioche con gelato; no new opinion")], "")
L["t1_p601jsj"] = ([], "Vodka-name joke.")
