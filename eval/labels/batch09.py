"""Batch 9: c0226-c0250."""
from common import M

L = {}
L["c0226"] = ([], "Bodega cat debate.")
L["c0227"] = ([M("Black Fox", "Black Fox Coffee", type="cafe_bakery_dessert", food=2, alt={"food": [3]}, terms=["coffee"],
                 why="'Best coffee: Black Fox'"),
               M("Suited", type="cafe_bakery_dessert", food=1, terms=["coffee"], why="'Runners up'"),
               M("Simpl", type="cafe_bakery_dessert", food=1, terms=["coffee"], why="'Runners up'"),
               M("La Parisienne", food=2, terms=["sit-down lunch"], why="'try La Parisienne! Delicious.'"),
               M("Kuu", food=1, terms=["ramen", "japanese curry"], why="'Kuu for ramen or japenese curry'"),
               M("Pho Maiden Lane", food=1, terms=["pho", "banh mi"], why="'for pho or bahn mi'")], "")
L["c0228"] = ([M("Tabetomo", named_in="title", alt={"food": [1]}, terms=["japanese", "ramen"], first=None,
                 why="defends its authenticity (Japanese-trained chef); no direct opinion of the food here")], "")
L["c0229"] = ([], "Generic double-tortilla taste.")
L["c0230"] = ([M("Hanis", "Hani's Bakery", named_in="title", food=-1, alt={"food": [0, None]},
                 dishes=[("smoked salmon foccacia", 2, False)], terms=["smoked salmon focaccia"],
                 why="'The smoked salmon foccacia is my favorite... I agree with your takes on everything you had' (OP was disappointed)")], "")
L["c0231"] = ([M("Saigon Shack", named_in="parent", food=1, first=False, alt={"food": [None]}, why="'looks great thanks!'")], "")
L["c0232"] = ([], "Bay Area Thai vs NYC.")
L["c0233"] = ([], "Unnamed Italian deli; bodegas generic.")
L["c0234"] = ([], "Polish food in general.")
L["c0235"] = ([M("Gramercy", "Gramercy Tavern", food=1, alt={"food": [2, None]}, dishes=[("additional milk", 2, False)],
                 terms=["chocolate chip cookie"], why="'The additional milk at Gramercy is so fun' (with the cookie)")], "")
L["c0236"] = ([M("Essex Market", type="food_hall", amb=True, first=None,
                 why="'Maybe Essex Market?' for buying huitlacoche: retail use of a market hall, scope unclear")], "")
L["c0237"] = ([M(r, c, also=a, food=1, why="list answer")
               for r, c, a in [("Angel", "Angel Indian Restaurant", ("angel",)), ("Temple Canteen", None, ()),
                               ("Curry Corner", None, ()), ("Dosa Delight", None, ())]], "")
L["c0238"] = ([], "")
L["c0239"] = ([], "Scott's Pizza Tours is a tour company.")
L["c0240"] = ([M("Lillo", food=3, hood="Henry Street, cobble hill", dishes=[("carciofi", 3, False)],
                 terms=["carciofi", "artichoke", "cash only"], desc=["cash only"],
                 why="'Best artichoke dish of any origin I've eaten anywhere'")], "")
L["c0241"] = ([M("Bangkok center grocery", "Bangkok Center Grocery", named_in="parent", type="grocery_market", oos=True,
                 why="retail")], "")
L["c0242"] = ([M("Hani's", "Hani's Bakery", named_in="ancestor", food=0, alt={"food": [-1, 1]}, rc=False, rt=True,
                 why="'only stop in if you happen to walk by... tastes better first thing in the morning'"),
               M("Campbell & Co", type="cafe_bakery_dessert", food=2, dishes=[("rice krispies treat", 2, False)],
                 terms=["rice krispies treat"], why="'makes a really good classic rice Krispies treat'"),
               M("Amanda's Good Morning Cafe", type="cafe_bakery_dessert", food=2, exp=-1, hood="Fort Greene",
                 alt={"expensiveness": [None]}, dishes=[("beignets", 1, False), ("cinnamon roll", 2, False)],
                 terms=["beignets", "cinnamon roll"], why="'beignets and a damn good cinnamon roll and don't want to break the bank'")], "")
L["c0243"] = ([M("Blank street", "Blank Street Coffee", type="chain", food=-3, alt={"food": [-2]}, first=None,
                 why="'Blank street is the WORST'")], "")
L["c0244"] = ([M("Carbone", named_in="title", food=-1, first=None, why="'Both are mid and overhyped.'"),
               M("Din Tai Fung", named_in="title", type="chain", food=-1, first=None, why="same")], "")
L["c0245"] = ([M("Village squares", "Village Square Pizza", food=2, dishes=[("plain pie", 2, False)], terms=["pizza", "plain pie"],
                 hood="UES", why="'plain pie is great'"),
               M("Lucia", "Lucia Pizza", food=3, exp=1, alt={"food": [2]}, hood="UES", terms=["pizza"],
                 why="'pricier but probably the best on the UES'")], "")
L["c0246"] = ([M("Beer Street South", type="bar", food=1, alt={"food": [None]}, terms=["pop-up"],
                 why="answer: bar that hosts pop-ups"),
               M("Chaat Dog", type="stall_vendor", first=None, why="reference: moved to Time Out Market"),
               M("time out market", "Time Out Market", type="food_hall", first=None, why="reference")], "")
L["c0247"] = ([
    M("Chinatown Ice Cream Factory", type="cafe_bakery_dessert", food=2, dishes=[("zen butter", 2, False)],
      terms=["ice cream", "zen butter"], why="'An institution... I highly recommend their Zen Butter flavor'"),
    M("Hop Kee", food=2, atmosphere=1, alt={"food": [1]}, dishes=[("periwinkle snails", None, False), ("pan-fried flounder", 1, False)],
      terms=["cantonese", "periwinkle snails", "pan-fried flounder"], why="favorites list; 'oozes history'"),
    M("Tao Hong", type="cafe_bakery_dessert", food=3, alt={"food": [2]}, dishes=[("egg tart", 3, False), ("cantonese buns", 2, False)],
      terms=["egg tart", "cantonese buns"], why="egg-tart tour favorite: 'Incredibly flaky crust... buns are excellent'"),
    M("Double Crispy", type="cafe_bakery_dessert", food=2, dishes=[("egg tart", 2, False)], terms=["egg tart", "cantonese bakery"],
      why="'Iconic Cantonese bakery... egg tart is no slouch'"),
    M("Spongies", type="cafe_bakery_dessert", food=2, exp=-2, alt={"food": [1]}, dishes=[("sponge cakes", None, False)],
      terms=["sponge cakes", "coffee"], why="'$1.50 sponge cakes... Good coffee too'"),
    M("Kong Sihk Tong", food=2, alt={"food": [1]}, terms=["cha chaan tang", "budget eats", "brunch"], why="favorites list"),
    M("Phoenix Palace", food=2, alt={"food": [1]}, terms=["cantonese"], why="'Trendy, but still authentic'"),
    M("Potluck Club", food=2, alt={"food": [1]}, terms=["cantonese"], why="same"),
    M("Uncle Lous", "Uncle Lou", food=2, atmosphere=1, alt={"food": [1]}, terms=["cantonese banquet"], why="'leans much more traditional'"),
    M("Pings", "Ping's", food=2, terms=["dim sum"], why="'the quality of the dim sum makes up for it'"),
    M("Nom Wah", "Nom Wah Tea Parlor", food=0, atmosphere=2, alt={"food": [-1, 1], "atmosphere": [1]}, terms=["dim sum"],
      why="'Is it the best Dim Sum in CT? No'; 'worth walking by for the ambience'"),
    M("Yu & Me Books", type="other", oos=True, why="bookstore"),
    M("Kono", food=2, alt={"food": [3]}, terms=["omakase", "chicken"], why="'My favorite atypical omakase experience in NYC'"),
], "Header 'these are my current favorites' => +2 unless qualified.")
L["c0248"] = ([], "Neighborhood advice.")
L["c0249"] = ([M("uva next door", "Uva Next Door", food=2, terms=["gluten free", "celiac safe", "gluten free pizza", "pasta"],
                 why="'can do almost anything gluten free celiac safe... bomb af'")], "")
L["c0250"] = ([M("Biriyani Bol", named_in="title", food=1, first=False, why="'I was skeptical, but it looks tasty'")], "")
