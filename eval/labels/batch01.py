"""Batch 1 labels (items c0001-c0050), written by reading each comment blind.
Emits eval/gold.jsonl. Aspects use the 7-point scale (-3..3, None = not mentioned)."""
import json, os, sys
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from extract import normalize_entity  # noqa

ALIAS = {"cote": "cote", "republic": "republic", "otto": "otto"}  # alias_overrides snapshot
ASPECTS = ("food", "value", "service", "atmosphere", "wait")


def M(raw, canon=None, *, also=(), type="restaurant", food=None, value=None, service=None,
      atmosphere=None, wait=None, alt=None, neg=False, first=True, dishes=(), hood=None,
      closed=False, rc=True, rt=True, conf="high", amb=False, unc=(), named_in="comment",
      why=""):
    canon = canon or raw
    key = normalize_entity(canon)
    key = ALIAS.get(key, key)
    accept = sorted({normalize_entity(x) for x in (raw, canon, *also)} - {key})
    return {
        "restaurant_raw": raw, "canonical_name": canon, "canonical_key": key,
        "accept_keys": accept, "entity_type": type,
        "aspects": {"food": food, "value": value, "service": service,
                    "atmosphere": atmosphere, "wait": wait},
        "aspect_alternatives": alt or {},
        "is_negated": neg, "is_firsthand": first, "dishes": list(dishes),
        "neighborhood_hint": hood, "closed": closed, "named_in": named_in,
        "resolvable_comment_mode": rc, "resolvable_thread_mode": rt,
        "confidence": conf, "ambiguous": amb, "uncertain_fields": list(unc),
        "rationale": why,
    }


L = {}
L["c0001"] = ([M("Beets Cafe", named_in="parent", food=1, conf="low", amb=True,
                 alt={"food": [None]},
                 why="'Haitian food is seriously underrated' praises the cuisine; can be read as seconding the parent's Beets Cafe rec, or as cuisine-only")],
              "Cuisine-level remark under a named rec; only defensible mention is the parent's place, scored leniently.")
L["c0002"] = ([], "Defends diner food in general; does not judge Washington Square Diner or any named place.")
L["c0003"] = ([M("Shake Shack", type="chain", food=-2, value=-2, dishes=["cheeseburger", "fries", "milkshake"],
                 alt={"food": [-3], "value": [-3]},
                 why="'burger is just awful, overpriced, overhyped'; milkshakes 'not too bad' keeps food at -2 not -3; 'expensive for no reason' is value; a bad review, not an avoid instruction")],
              "")
L["c0004"] = ([M("Tony’s di Napoli", "Tony's Di Napoli", food=2, service=2, hood="Times Square",
                 alt={"food": [3], "service": [3]},
                 why="'the real deal. One of the best meals we've had lately' (+2, 'lately' hedges the superlative); 'service is top notch' +2")], "")
L["c0005"] = ([M(r, c, also=a, food=1, why="bare list answering the walk-in question: named as an answer, food +1")
               for r, c, a in [("Raouls", "Raoul's", ()), ("Via carota", "Via Carota", ()),
                               ("Minetta tavern", "Minetta Tavern", ()), ("Cervos", "Cervo's", ()),
                               ("Penny", None, ()), ("L Artusi", "L'Artusi", ()),
                               ("Semma", None, ()), ("Torrisi", None, ())]], "Bare 8-name list.")
L["c0006"] = ([
    M("Via Carota", wait=1, alt={"wait": [None], "food": [1]},
      why="'they'd give a table for 4 for walk ins for early dinners' = reservation/walk-in ease (wait +1); food not judged"),
    M("l’artusi", "L'Artusi", wait=1, alt={"wait": [None], "food": [1]}, why="'same with l'artusi' = same walk-in ease"),
    M("Shmone wine bar", "Shmoné Wine Bar", type="bar", food=1, alt={"food": [None]},
      why="suggested as an option; 'smaller plates but still some of the same dishes from the restaurant next door with a star' is a mild food endorsement; 'walk ins only' is a fact"),
    M("Bad Roman", wait=1, alt={"wait": [None], "food": [1]},
      why="'looks like they have an opening' = availability (wait +1), food not judged; not firsthand",
      first=False, unc=["is_firsthand"]),
], "Beli/ResX are apps; Gramercy Tavern only in the post body.")
L["c0007"] = ([
    *[M(r, c, also=a, type=t, first=None, conf="medium", alt={"food": [1]},
        why="named as an EXAMPLE of a common category (Asian bowls/sandwiches), not recommended; no opinion")
      for r, c, a, t in [("Xi’an", "Xi'an Famous Foods", ("xian",), "chain"), ("Ippudo", None, (), "restaurant"),
                         ("GAI", None, (), "restaurant"), ("Mr Bao", None, (), "restaurant"),
                         ("pokeworks", "Pokeworks", (), "chain"), ("wagamama", "Wagamama", (), "chain")]],
    M("num pang", "Num Pang", food=1, alt={"food": [2]}, conf="medium",
      why="'damn I really miss num pang now' = fond, mild positive; unclear if it is closed"),
], "'any banh mi shop, kati roll places' are categories, not names.")
L["c0008"] = ([M("DCP", "Double Chicken Please", also=("the coop at dcp", "coop"), type="bar", first=False, amb=True,
                 conf="medium", why="asks what to order at DCP: names the place, no opinion; reference-only mention is optional")],
              "Question-only mention.")
L["c0009"] = ([M("Mekelburg's", "Mekelburg's", named_in="selftext", closed=True, alt={"food": [2]},
                 why="closed place (post says it closed); 'i was there weekly and i miss it so much' is remembered praise: aspects null under the closed rule, +2 accepted")], "")
L["c0010"] = ([M("Portale", named_in="title", food=1, dishes=["insalata", "pappardelle", "duck breast", "olive cake"],
                 alt={"food": [2]}, why="answers 'what should I order at Portale' with dishes; implicit endorsement +1")], "")
L["c0011"] = ([M("Cho Dang Gol", named_in="parent", food=3, dishes=["kimchi biji jigae"],
                 why="'This is the answer' + 'even better than anything I've had in Korea' = superlative")], "")
L["c0012"] = ([M("shukette", "Shukette", food=3, why="'one of the best restaurants in New York' = city-level superlative")], "")
L["c0013"] = ([], "Houston vs NYC generalization; no named place.")
L["c0014"] = ([M("Salt Hank", first=False, alt={"wait": [-1], "food": [1]}, unc=["is_firsthand"], conf="medium",
                 why="logistics tip: order on GrubHub to skip the line; no opinion of the food; the line is implied long but bypassable")], "")
L["c0015"] = ([M("Sam’s", "Sam's Restaurant", also=("sams",), food=1, hood="Cobble Hill",
                 alt={"food": [None]}, unc=["is_firsthand"],
                 why="'Also, Sam's in Cobble Hill just reopened' offered as a dinner suggestion")], "")
L["c0016"] = ([M("Katz", "Katz's Delicatessen", also=("katzs", "katz deli", "katzs deli"), named_in="title",
                 atmosphere=-2, alt={"atmosphere": [-1], "food": [-1]}, hood="Brooklyn", amb=True, conf="low",
                 why="'That food hall sucks' about Katz's Brooklyn outpost (DeKalb food hall); target is the hall as much as Katz's")],
              "Target ambiguous: food hall (unnamed) vs Katz's Brooklyn location.")
L["c0017"] = ([M(r, c, also=a, food=1, why="bare list of steakhouse alternatives to Luger: named as an answer")
               for r, c, a in [("Le TetE D’Or", "Le Tête d'Or", ()), ("Salt + Charcoal", None, ()),
                               ("Dolmenicos", "Delmonico's", ()), ("Porterhouse Steakhouse", "Porter House Bar and Grill", ("porterhouse",)),
                               ("Quality Italian", None, ())]], "Misspelling 'Dolmenicos' = Delmonico's.")
L["c0018"] = ([], "Generic ordering rule of thumb; no opinion of Pies n Thighs.")
L["c0019"] = ([], "Unnamed street vendor ('guy' at a corner); no name to extract.")
L["c0020"] = ([], "Chopped cheese history; no place.")
L["c0021"] = ([M("Lovely's Old Fashioned", named_in="parent", food=2, dishes=["burger"],
                 why="'Great burger too' replying to the Lovely's rec")], "")
L["c0022"] = ([], "Asks whether tile makes rooms loud; question about acoustics, no judgment.")
L["c0023"] = ([M("the Grill", "The Grill", food=1, alt={"food": [2]},
                 why="'walk to the Grill in 20 mins and eat at the bar' as the answer; 'plenty of good food' is general")],
              "Rest is a generic Midtown rant.")
L["c0024"] = ([], "Cuisine/country comparison; 'Greek food in Astoria' is a neighborhood+cuisine, no named place.")
L["c0025"] = ([M("The modern", "The Modern", food=1, alt={"food": [None]}, unc=["is_firsthand"],
                 why="answers 'which 2-3 star place' (sells gift cards): named as an answer"),
               M("per se", "Per Se", food=1, alt={"food": [None]}, unc=["is_firsthand"],
                 why="same")], "")
L["c0026"] = ([M("zabars", "Zabar's", type="grocery_market", food=1, hood="upper west",
                 why="'try zabars in the upper west' for smoked fish: named as an answer"),
               M("acmesmokedfish", "Acme Smoked Fish", type="grocery_market", food=1, hood="brooklyn",
                 amb=True, conf="medium", alt={"food": [None]},
                 why="named only via URL; recommended Fish Friday trip"),
               M("costco", "Costco", type="grocery_market", amb=True, unc=["is_firsthand"],
                 why="reference only: where Acme product is sold")], "")
L["c0027"] = ([M(r, c, food=f, alt={"food": [1]} if f == 2 else {"food": [3]},
                 why=w)
               for r, c, f, w in [
                   ("Mariscos El Submarino", None, 2, "'Personal favs' + 'definitely Mariscos El Submarino'"),
                   ("East Harbor Seafood", "East Harbor Seafood Palace", 2, "listed under 'Personal favs'"),
                   ("Wu’s Wonton King", "Wu's Wonton King", 2, "listed under 'Personal favs'"),
                   ("Abuqir", None, 2, "listed under 'Personal favs'"),
                   ("Hamido Seafood", "Hamido", 2, "listed under 'Personal favs'"),
                   ("Astoria Seafood", None, 2, "listed under 'Personal favs' (also in post)"),
                   ("Chuan Tian Xia", None, 2, "listed under 'Personal favs'"),
                   ("Hug Esan", None, 2, "listed under 'Personal favs'"),
                   ("Zaab Zaab", None, 2, "listed under 'Personal favs'")]],
              "Header 'Personal favs' makes every list item +2 (favorite), +1 accepted.")
L["c0028"] = ([], "Drink brands (Arizona, Dr Browns, Snapple...), not places.")
L["c0029"] = ([M("Fish Cheeks", named_in="title", wait=1, alt={"wait": [None]},
                 why="answers the walk-in question: 'around 4/4:40 there's always one or two free tables' = easy walk-in")], "")
L["c0030"] = ([M("Cannelle Patisserie", type="cafe_bakery_dessert", food=1, dishes=["chocolate mousse cake"],
                 why="named as an answer with a dish, no adjective")], "")
L["c0031"] = ([M("S&P", named_in="parent", food=1, first=False, alt={"food": [None]}, conf="medium",
                 why="'Marked, looks so nice' = mild positive from looking at it, has not been")], "")
L["c0032"] = ([], "Asks which panettone product; no place judged.")
L["c0033"] = ([], "Mod removal notice.")
L["c0034"] = ([], "'Fancy food is boring... Skip it' targets fancy food as a category, not the post's named places.")
L["c0035"] = ([M("John’s", "John's of Bleecker Street", also=("johns of bleecker", "johns of bleeker st", "johns of bleecker st"),
                 food=1, alt={"food": [2]},
                 why="picks John's in the comparison ('out of spite, plus they got a coal oven')"),
               M("L’industrie", "L'Industrie Pizzeria", also=("lindustrie",), named_in="title", food=-1, amb=True,
                 conf="low", alt={"food": [None]},
                 why="loses the comparison 'out of spite'; not named in the comment and not judged on food")], "")
L["c0036"] = ([M("Arbys", "Arby's", type="chain", food=1, amb=True, conf="low", first=None, alt={"food": [None]},
                 why="joke: buy frozen Arby's curly fries at the supermarket; product, not a visit")],
              "Says NYC isn't a curly-fry town; no NYC place.")
L["c0037"] = ([M(r, c, type="bar", food=1, why="bare list answering a bar-crawl request: named as an answer")
               for r, c in [("Wilfie", "Wilfie & Nell"), ("Grove street social", "Grove Street Social"),
                            ("Spaniard", "The Spaniard"), ("Parkgate", None),
                            ("Barrow Street ale house", "Barrow Street Ale House"),
                            ("Bayard’s ale house", "Bayard's Ale House"), ("White horse", "White Horse Tavern")]],
              "All bars (out_of_scope?), Knicks remark irrelevant.")
L["c0038"] = ([M("Monkey Bar", wait=-1, first=False, alt={"wait": [None]},
                 why="'never able to get a reservation' = hard to book; never went, food not judged")], "")
L["c0039"] = ([M("shopsins", "Shopsin's", named_in="ancestor", food=2, alt={"food": [3]}, rc=False, rt=True,
                 why="'100%, those breakfasts are insane' (praise); name is two levels up, absent from comment-mode input")], "")
L["c0040"] = ([M("Tommy Bahamas", "Tommy Bahama", type="chain", food=2, dishes=["coconut shrimp"],
                 why="'the restaurant at Tommy Bahamas is great and they serve a lovely coconut shrimp'")], "")
L["c0041"] = ([M("Verlain", named_in="parent", type="bar", amb=True, conf="low", alt={"food": [1]},
                 why="'Ahh the memories... or lack thereof' = fond joke about getting drunk on the lychee martinis; no real judgment")], "")
L["c0042"] = ([], "Corporate trivia about Wonder buying GrubHub; no judgment.")
L["c0043"] = ([], "Dogs-in-restaurants rant; does not judge Ceres Pizza itself.")
L["c0044"] = ([M("Rubirosa", food=-1, first=False, alt={"food": [None]}, unc=["is_negated"], conf="medium",
                 why="decides to skip Rubirosa on hearsay ('I'd rather skip it'); own plan, not an instruction to others")], "")
L["c0045"] = ([M("Serafina", food=-2, value=-2, neg=True, first=None,
                 alt={"food": [-1, -3], "value": [-1, -3]}, unc=["is_negated"], conf="medium",
                 why="'Second this. Came here to write Serafina.' in a thread asking for poor-quality, expensive places to send an enemy: polarity comes only from the title")],
              "Sarcasm thread: endorsement = negative.")
L["c0046"] = ([], "InKind payment app and a Costco deal; no place.")
L["c0047"] = ([
    M("15 East", closed=True, alt={"food": [-1]}, conf="medium",
      why="stopped going after the chef left ('never bothered'); since revived/renamed: closed, aspects null"),
    M("Jewel Bako", closed=True, alt={"food": [2]},
      why="'still great after Masato san left' but owners retired: closed, aspects null"),
    M("Sushi Ann", amb=True, first=None, why="reference only (where a chef went)"),
    M("Sushi Azabu", amb=True, first=None, why="reference only"),
    M("Sushi Aozora", amb=True, first=None, why="reference only (15 East's new name)"),
    M("Omakase by Mitsu", first=False, amb=True, why="'still havent visited': reference only"),
    M("Hasaki", food=2, value=1, alt={"value": [2, None]},
      why="'now pretty awesome and reasonably priced'"),
    M("Joji", amb=True, first=None, why="reference only (Yuba's chef runs it)"),
    M("Yuba", amb=True, first=None, why="reference only"),
], "Sushi-insider history; only Hasaki gets a live opinion.")
L["c0048"] = ([], "Self-promo for an app.")
L["c0049"] = ([M("jacks wife freda", "Jack's Wife Freda", food=2, value=-2, dishes=["grapefruit and yogurt"],
                 alt={"value": [-3]},
                 why="'really good' food; '$15 is highway robbery' = value complaint")], "")
L["c0050"] = ([], "Complains about subreddit title rules.")


def main():
    items = {json.loads(l)["item_id"]: json.loads(l)
             for l in open(os.path.join(REPO, "eval", "items.jsonl"))}
    out = []
    for iid in sorted(L):
        ms, note = L[iid]
        it = items[iid]
        for m in ms:
            for a in m["aspects"]:
                assert a in ASPECTS and m["aspects"][a] in (None, -3, -2, -1, 0, 1, 2, 3), (iid, m)
        out.append({
            "item_id": iid, "comment_id": it["comment_id"], "thread_id": it["thread_id"],
            "label_version": 1, "labeler": "claude-opus-5.5 (manual, blind)",
            "labeled_at": "2026-10-03",
            "has_mention": any(not m["ambiguous"] for m in ms),
            "mentions": ms, "note": note,
        })
    with open(os.path.join(REPO, "eval", "gold.jsonl"), "w", encoding="utf-8") as f:
        for g in out:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    print(len(out), "comments,", sum(len(g["mentions"]) for g in out), "mentions,",
          sum(g["has_mention"] for g in out), "with a required mention")


main()
