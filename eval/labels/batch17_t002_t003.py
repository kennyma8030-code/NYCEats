"""Threads t002 (Noona's Ice Cream) and t003 (deli pickles). Every comment labeled."""
from common import M

L = {}
A = "t002/"


def N(**kw):
    kw.setdefault("named_in", "title")
    return M("Noona's", "Noona's Ice Cream", also=("noonas",), type="cafe_bakery_dessert", **kw)


L[A + "t1_o3kujkq"] = ([], "AutoModerator.")
L[A + "t1_o3kvxe0"] = ([], "Mod note.")
L[A + "t1_o3kxbbu"] = ([N(amb=True, alt={"expensiveness": [2]}, first=None, why="'Let me guess… $16 each?' — sarcastic price guess")], "")
L[A + "t1_o3l05q2"] = ([N(food=1, first=False, why="'Wow it looks so good! Will definitely try!!'")], "")
L[A + "t1_o3l0elu"] = ([N(food=2, service=2, dishes=[("pandan", 2, False), ("ube", 2, False), ("mochi toppings", None, False)],
                         terms=["pandan", "ube", "mochi"],
                         why="'I really like the flavors... my favorite is the pandan and ube... the owner is quite nice'")], "")
L[A + "t1_o3l2skt"] = ([], "'need to get into ube' — about the flavor in general.")
L[A + "t1_o3l32gu"] = ([N(service=1, alt={"service": [None]}, dishes=["blueberry pie", "olive oil", "carrot cake"],
                         why="'She let me suggest some flavors for the spring too!'")], "")
L[A + "t1_o3l1pm2"] = ([N(named_in="comment", food=2, why="'Love this place. Great flavor combinations!'")], "")
L[A + "t1_o3l27ui"] = ([N(food=1, first=False, dishes=[("passionfruit", 1, False)], terms=["passionfruit ice cream"],
                         why="'passionfruit ice cream sounds FIRE'")], "")
L[A + "t1_o3l32yp"] = ([N(food=1, first=False, alt={"food": [None]}, why="'looks so yummy! How much was your cup??'")], "")
L[A + "t1_o3l3uo7"] = ([N(named_in="ancestor", exp=0, alt={"expensiveness": [-1, None]},
                         why="'around $8 (this includes a topping and drizzle)': price info")], "")
L[A + "t1_o3l38qd"] = ([N(food=1, service=-1, alt={"service": [-2]},
                         why="'My ice cream was pretty good but they gotta work on showing up on time'")], "")
L[A + "t1_o3lbclv"] = ([], "Defends the small business; no opinion of the place.")
L[A + "t1_o3ltycs"] = ([N(service=-1, alt={"service": [-2]}, why="'should be open when they say they are'")], "")
L[A + "t1_o3l38uq"] = ([N(named_in="comment", food=2, first=True, why="'This looks so good! I love Noona's'")], "")
L[A + "t1_o3l7buy"] = ([N(food=1, first=False, dishes=[("lotus flavor", 1, False)], why="'that lotus flavor looks incredible'")], "")
L[A + "t1_o3leq0o"] = ([N(food=2, dishes=[("banana pudding mochi", 2, False)], terms=["banana pudding mochi"],
                         why="'Their banana pudding mochi flavor is so frickin good'")], "")
L[A + "t1_o3lkoy9"] = ([], "Raw buffalo-milk ice cream (Uddermilk, online) as a product comparison; no place.")
L[A + "t1_o3p6axy"] = ([], "Question.")
L[A + "t1_o430eg1"] = ([M("Uddermilk", oos=True, why="online order, not a place")], "")
L[A + "t1_o3m9fu3"] = ([N(food=1, first=False, alt={"food": [None]}, why="'whats the flavour... looks delicious'")], "")
L[A + "t1_o3mb99h"] = ([N(amb=True, dishes=["banana pudding mochi w/ strawberry jam drizzle"], why="OP names their order; nameless, no opinion")], "")
L[A + "t1_o3n7uyu"] = ([N(food=2, why="'I've been following her since she did mail order pints... She does amazing flavors!'")], "")
L[A + "t1_o3nc7xi"] = ([N(food=1, alt={"food": [2]}, first=None, terms=["korean"],
                         why="'the flavors that she makes truly showcase her Korean heritage'")], "")
L[A + "t1_o3p6do4"] = ([N(amb=True, hood="east village", why="'they're located in the east village' — location only")], "")
L[A + "t1_o3r5jyp"] = ([N(food=2, dishes=[("toasted rice", 2, False)], terms=["toasted rice"],
                         why="'Highly recommend the toasted rice flavor... truly unique'")], "")

B = "t003/"
PG = dict(type="grocery_market", oos=True)
L[B + "t1_orndi7d"] = ([M("Liebmans", "Liebman's Deli", food=1, why="'Otherwise I go to Liebmans'"),
                        M("Jacob’s Pickles", "Jacob's Pickles", food=-1, value=-1, vc=True, neg=True, neg_ok=True,
                          dishes=[("pickles", -1, False)], why="'their pickles are mid and not worth the time or money'"),
                        M("The Pickle Guys", "The Pickle Guys", **PG, why="retail pickle shop; 'mid and not worth it'")],
                       "Unnamed closed neighborhood deli; Grillo's is a jarred brand.")
L[B + "t1_orne7q0"] = ([], "")
L[B + "t1_ornphy1"] = ([M("pickle guys", "The Pickle Guys", **PG, why="retail: 'I like pickle guys fruit... average in a nice atmosphere'")], "")
L[B + "t1_ornssi9"] = ([M("Jacob’s", "Jacob's Pickles", food=-1, alt={"food": [-2]}, dishes=[("pickles", -1, False)],
                          terms=["half-sours", "new pickles"],
                          why="'needs snacking/crunching pickles... Everything on the menu is way over the top'")], "")
L[B + "t1_oro17m1"] = ([M("The Pickle Guys", **PG, why="retail: 'pickled pineapple. Goddamn that was good'")], "")
L[B + "t1_orom5pn"] = ([M("pickle guys", "The Pickle Guys", named_in="parent", **PG, amb=True,
                          why="'I LOVE their pickled mango' — 'their' is Jacob's (parent) or Pickle Guys (sibling)")], "")
L[B + "t1_ornh0jb"] = ([M("Simply Nova", food=2, hood="Williamsburg", dishes=[("sours", 2, False)], terms=["sours", "pickles"],
                          conf="medium", why="'has some tasty sours!'")], "")
L[B + "t1_ornhp4u"] = ([M("Hormans pickles", "Horman's Pickles", type="stall_vendor", food=1, alt={"food": [None]},
                          hood="mcgolrick farmers market", terms=["pickles"], why="'Worth it to check out' at the farmers market"),
                        M("Sweet Pickle Books", type="other", oos=True, why="bookstore")], "Polish delis generic.")
L[B + "t1_ornj05g"] = ([M("mason pickel", "Mason Pickle", food=1, dishes=[("pickle cake", 1, False)], conf="low",
                          why="'I have enjoyed the picked cake at mason pickel'")], "")
L[B + "t1_ornmvyh"] = ([M("2nd avenue deli", "2nd Ave Deli", food=1, why="list answer"),
                        M("PJ Bernstein’s", "P.J. Bernstein", food=1, why="list answer")], "")
L[B + "t1_orpy4cu"] = ([M("2nd Ave", "2nd Ave Deli", food=-2, dishes=[("pickles", -2, False)],
                          why="'2nd Ave pickles have sucked for years... limp and crunchless'")], "")
L[B + "t1_ornog7a"] = ([M("Tashkent Market", **PG, why="supermarket")], "")
L[B + "t1_orns9uo"] = ([M("Zabar’s", "Zabar's", **PG, why="grocery")], "")
L[B + "t1_oro51m1"] = ([M("grillos pickles pop up", "Grillo's Pickles", amb=True, type="stall_vendor",
                          why="links a brand pop-up event; no opinion")], "")
L[B + "t1_oro9mqv"] = ([M("Grillos", "Grillo's Pickles", oos=True, why="jarred brand")], "")
L[B + "t1_orojyyr"] = ([M("Eddies", "Eddie's Pickles", hood="Maspeth", **PG, why="wholesale/retail pickles")], "")
L[B + "t1_orsb2c2"] = ([M("Eddies", "Eddie's Pickles", named_in="parent", **PG, why="retail; 'my favorite pickles'")], "")
L[B + "t1_orsqiae"] = ([], "")
L[B + "t1_oroqqdi"] = ([M("The Pickle Guy", "The Pickle Guys", **PG, why="retail"),
                        M("Schaller & Weber", **PG, why="butcher/grocery"),
                        M("Bi-Tampte", oos=True, why="brand"),
                        M("Zabar’s", "Zabar's", **PG, why="grocery"),
                        M("Tashkent Supermarket", "Tashkent Market", **PG, why="supermarket"),
                        M("Parrot Coffee", **PG, why="market"),
                        M("Katz’s Deli", "Katz's Delicatessen", food=1, alt={"food": [None]}, dishes=["pickles"],
                          why="'you can get Katz's Deli pickles by weight'")], "")
L[B + "t1_orp1myy"] = ([M("Pickle Guys", "The Pickle Guys", **PG, why="retail"),
                        M("Kossar’s Bialys", "Kossar's Bagels & Bialys", type="cafe_bakery_dessert", first=None, why="landmark reference"),
                        M("Doughnut Plant", type="cafe_bakery_dessert", first=None, why="landmark reference"),
                        M("Katz’s", "Katz's Delicatessen", first=None, why="landmark reference"),
                        M("Russ and Daughter", "Russ & Daughters", first=None, why="landmark reference")], "")
L[B + "t1_orpu53d"] = ([M("zabars", "Zabar's", **PG, why="grocery deli pickles")], "")
L[B + "t1_orq46y7"] = ([M("sweet pickles", "Sweet Pickle Books", type="other", oos=True, why="bookstore")], "")
L[B + "t1_orqe0gm"] = ([M("big nicks", "Big Nick's", closed=True, why="'miss that joint': closed")], "")
L[B + "t1_orqozk2"] = ([M("Stuytown market", "Stuytown Market", food=2, alt={"food": [1]}, hood="Gramercy", conf="medium",
                          why="'Stuytown market!!!' as the answer (deli counter)")], "")
L[B + "t1_orqp608"] = ([M("Stuytown market", "Stuytown Market", named_in="parent", food=3, dishes=[("chicken caesar wrap", 3, False)],
                          terms=["chicken caesar wrap"], conf="medium", why="'Also has the best Chicken Caesar Wrap omg'")], "")
L[B + "t1_ors3no0"] = ([M("Pickle guy", "The Pickle Guys", hood="Grand St", **PG, why="retail")], "")
L[B + "t1_orsb469"] = ([M("Pickle Me Pete", type="stall_vendor", food=2, hood="Bryant park", terms=["pickles", "street fairs"],
                          why="'I'm a big fan of Pickle Me Pete'")], "")
L[B + "t1_orsydim"] = ([M("HMart", "H Mart", **PG, why="grocery"), M("Katagiri", **PG, why="Japanese grocery")], "")
