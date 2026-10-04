"""Batch 10: c0251-c0275."""
from common import M

L = {}
L["c0251"] = ([M("Margons", "Margon", also=("margons",), named_in="parent", food=1, alt={"food": [2]},
                 why="'Shhh let's gate keep this' — implicit endorsement of the parent's rec")], "")
L["c0252"] = ([M("4 Charles", "4 Charles Prime Rib", named_in="title", amb=True,
                 why="walk up and tip the door; nameless, no opinion of the place")], "")
L["c0253"] = ([M("Don Angie", named_in="comment", food=-3, service=-2, neg=True, alt={"service": [-1, None]},
                 why="'the single worst dining experience Ive had in years and I would suggest to just stay away'; 'really pushy about turning over tables'")], "")
L["c0254"] = ([M("Los Tacos No1", "Los Tacos No. 1", named_in="title", amb=True, exp=-1, alt={"expensiveness": [None]},
                 why="expansion speculation, '$6 tacos'; nameless, no opinion")], "")
L["c0255"] = ([M("Joe’s Steam Rice Roll", "Joe's Steam Rice Roll", food=1, why="list answer for cheung fun"),
               M("East Harbor Seafood", "East Harbor Seafood Palace", food=1, why="list answer"),
               M("Park Asia", food=1, why="list answer"),
               M("New Double Fire", alt={"food": [1]}, first=False, why="reference to someone else's rec")],
              "'Cart on 61st and 8th ave' is unnamed.")
L["c0256"] = ([M("Wonder", named_in="title", type="food_hall", food=-1, neg_ok=True,
                 why="'First time was meh... second shot... also meh, so we never went back'")], "")
L["c0257"] = ([], "Joke.")
L["c0258"] = ([M("Magnolia", "Magnolia Bakery", type="chain", food=1, alt={"food": [2]}, dishes=[("banana pudding", 2, False)],
                 terms=["banana pudding"], why="'Magnolia's banana pudding still great though'")], "")
L["c0259"] = ([], "Lobster sourcing speculation; no opinion.")
L["c0260"] = ([], "")
L["c0261"] = ([
    M("mei lai wah", "Mei Lai Wah", food=-1, neg=True, alt={"food": [None]}, why="'I would suggest you skip mei lai wah'"),
    M("tao hong", "Tao Hong", type="cafe_bakery_dessert", food=2, value=2, exp=-1, alt={"value": [1], "expensiveness": [None]},
      dishes=[("buns", 2, False), ("egg tarts", 1, False)], terms=["buns", "egg tarts"],
      why="'better tasting, they are bigger and cheaper as well, i would also try their egg tarts'"),
    M("wah fung", "Wah Fung No. 1", first=None, why="reference: 'since you are going to wah fung'"),
    M("Great NY Noodle town", "Great NY Noodletown", food=1, dishes=[("soft shell crab", 1, False)], terms=["soft shell crab"],
      why="'for soft shell crab'"),
    M("Noodle village", "Noodle Village", food=1, dishes=[("soup dumplings", 1, False), ("curry oxtail", 1, False)],
      terms=["soup dumplings", "curry oxtail"], why="'for soup dumplings and curry oxtail'"),
    M("Banh mi saigon", "Banh Mi Saigon", food=1, dishes=[("#1 special", 1, False)], terms=["banh mi"], why="'for the #1 special'"),
    M("Banh Mi Co Ut", "Bánh Mì Cô Út", food=1, dishes=[("traditional sandwich", 1, False)], terms=["banh mi"],
      why="'for the more traditional sandwich'"),
], "'Malaysian jerky place on mott street' unnamed.")
L["c0262"] = ([M("Quality Meats", named_in="ancestor", food=3, alt={"food": [2]}, rc=False, rt=True,
                 dishes=[("caesar salad", 0, False), ("grilled bacon", 3, False), ("porterhouse", 2, False),
                         ("yorkshire creamed spinach", 2, False), ("parmesan waffle fries", 1, False),
                         ("corn creme brulee", 3, False), ("orange creamsicle pavlova", 3, False)],
                 terms=["steakhouse", "porterhouse", "grilled bacon", "corn creme brulee", "pavlova"],
                 why="dish-by-dish rave with *** must-haves; name only in their own d0 comment")], "")
L["c0263"] = ([M("Xi’an famous foods", "Xi'an Famous Foods", named_in="title", type="chain", food=-1, alt={"food": [-2]},
                 hood="LIC, Jackson Avenue", why="'disappointment that it seemed not to be as good as it used to be'")], "")
L["c0264"] = ([M("Radio Bakery", named_in="title", type="cafe_bakery_dessert", food=1, alt={"food": [None]},
                 dishes=[("tuna and lemon zest", None, False), ("turkey kale sandwich", None, False)],
                 terms=["sandwich", "tuna and lemon zest"], why="went for the tuna sandwich; will try the turkey next time")], "")
L["c0265"] = ([M("Felo Deli", named_in="parent", food=1, first=False, alt={"food": [None]}, dishes=["goat on rice"],
                 why="'that sounds amazing'")], "")
L["c0266"] = ([M("Wu's", "Wu's Wonton King", atmosphere=1, alt={"atmosphere": [None]}, terms=["lazy susan"],
                 why="'sit at a table with a lazy susan... Such a fun shot!'")], "")
L["c0267"] = ([], "BEC on a bagel in general.")
L["c0268"] = ([M("Peter Pan", "Peter Pan Donut & Pastry Shop", named_in="title", wait=1, alt={"wait": [None]},
                 terms=["donuts"], why="'call them ahead... you can skip the whole line'")], "")
L["c0269"] = ([], "App promo.")
L["c0270"] = ([M("Milano Market", named_in="title", food=1, alt={"food": [2]}, dishes=[("caesar wrap", 2, False)],
                 terms=["caesar wrap", "deli", "sandwich"],
                 why="'The Caesar wrap is great... a solid 7-8/10 - an ol' reliable'")], "")
L["c0271"] = ([M("queens night market", "Queens Night Market", type="food_hall", food=2, exp=-2, alt={"expensiveness": [-1]},
                 terms=["night market", "kid friendly"], why="'super kid friendly... huge variety... Everything is $6 or under'"),
               M("Burmese Bites", type="stall_vendor", food=2, alt={"food": [3]},
                 dishes=[("dry noodles", 2, False), ("ramen", None, False)], terms=["burmese", "noodles"],
                 why="'I highly recommend Burmese Bites — the noodles are amazing'")], "")
L["c0272"] = ([M("Naya", named_in="comment", food=2, why="'I could eat Naya every day'")], "")
L["c0273"] = ([], "Argues about 'not local'; no opinion of The Corner Store.")
L["c0274"] = ([M("888 Hudson Thai", named_in="title", food=-3, service=-2, first=False, neg_ok=True,
                 alt={"service": [-3]}, why="'Absolutely disgusting. How could they... not [give] you your money back?'")], "")
L["c0275"] = ([M("Lucali", food=-1, neg_ok=True, alt={"food": [0, -2]}, dishes=[("pizza", 1, False)], terms=["pizza"],
                 why="'the most overrated restaurant on the planet. They make a good pizza... not something special to go out of your way for'")], "")
