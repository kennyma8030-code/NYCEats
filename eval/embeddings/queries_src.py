"""The frozen query set. Written before any retrieval was run against the corpus
and committed on its own, so no query could be tuned to favour a model.

Each query is what someone would type into the NYCEats search box. `intent`
is a one-line statement of what the searcher wants, written at the same time,
so the judges grade against the searcher's need rather than the literal words.
Running this file writes queries.jsonl with a deterministic ~20% holdout per
category.
"""

import json
import random

from common import HERE

Q = {
    "occasion_vibe": [
        ("date night", "a restaurant that works well for a romantic date"),
        ("romantic dinner for an anniversary", "a special, romantic place for an anniversary dinner"),
        ("first date spot that isn't too fancy", "a casual, relaxed place suited to a first date"),
        ("good for a big group", "a restaurant that can seat or suits a large group"),
        ("birthday dinner for 10 people", "a place that handles a ~10 person celebratory dinner"),
        ("solo dinner at the bar", "a place comfortable for eating alone, ideally at a bar or counter"),
        ("place to eat alone with a book", "a calm spot where dining solo is comfortable"),
        ("boozy brunch", "a brunch spot with drinks, e.g. bottomless or cocktails"),
        ("brunch without a crazy wait", "a brunch place where you can get seated without a long wait"),
        ("late night food after the bars", "food available late at night"),
        ("open past midnight", "a restaurant that serves food after midnight"),
        ("business lunch in midtown", "a midtown lunch place suitable for a work meal"),
        ("take my parents when they visit", "a crowd-pleasing restaurant to bring visiting parents"),
        ("kid friendly restaurant", "a place that welcomes children/families"),
        ("lively spot with a fun vibe", "an energetic, fun atmosphere"),
    ],
    "price": [
        ("cheap eats", "inexpensive, good food"),
        ("cheap tasting menu", "a tasting menu at a relatively low price"),
        ("worth the splurge", "an expensive place that is worth the money"),
        ("best meal under $20", "a very good meal for under about $20"),
        ("affordable omakase", "an omakase that is relatively inexpensive"),
        ("special occasion splurge dinner", "a high-end place for a special occasion"),
        ("good value prix fixe", "a prix fixe / set menu that is good value"),
        ("lunch special deals", "restaurants with good lunch specials"),
        ("cheap date", "an inexpensive place that works for a date"),
        ("dollar slice", "a cheap slice pizza place"),
        ("budget friendly sushi", "sushi that is affordable"),
        ("overpriced for what you get", "places where the price is too high for the quality (avoid intent)"),
    ],
    "dish": [
        ("best soup dumplings", "where to get great soup dumplings (xiao long bao)"),
        ("xiao long bao", "where to get great xiao long bao / soup dumplings"),
        ("good bagel", "a place with good bagels"),
        ("best pastrami sandwich", "where to get a great pastrami sandwich"),
        ("hand pulled noodles", "a place serving hand-pulled noodles"),
        ("birria tacos", "where to get birria tacos"),
        ("chopped cheese", "where to get a good chopped cheese"),
        ("flaky croissant", "a bakery with excellent croissants"),
        ("best burger in the city", "a top burger"),
        ("smash burger", "a place serving smash burgers"),
        ("pho", "a good pho / Vietnamese noodle soup spot"),
        ("ramen", "a good ramen shop"),
        ("dry aged steak", "a place known for dry-aged steak"),
        ("cacio e pepe", "a place with good cacio e pepe"),
        ("halal cart chicken over rice", "a good halal cart / chicken over rice"),
        ("oysters happy hour", "an oyster happy hour / discounted oysters"),
        ("hot pot", "a hot pot restaurant"),
        ("best fries", "a place with excellent french fries"),
    ],
    "cuisine_neighborhood": [
        ("sichuan in flushing", "a Sichuan restaurant in Flushing"),
        ("dim sum in chinatown", "a dim sum place in Manhattan or other Chinatown"),
        ("korean bbq in k-town", "Korean BBQ in Koreatown (Manhattan)"),
        ("italian in the west village", "an Italian restaurant in the West Village"),
        ("tacos in sunset park", "tacos in Sunset Park, Brooklyn"),
        ("thai in elmhurst", "Thai food in Elmhurst, Queens"),
        ("pizza in brooklyn", "pizza in Brooklyn"),
        ("jamaican food in flatbush", "Jamaican / Caribbean food in Flatbush"),
        ("ethiopian in harlem", "Ethiopian food in Harlem"),
        ("georgian food in brighton beach", "Georgian (country) food, ideally in south Brooklyn"),
        ("indian on curry hill", "Indian food on Lexington Ave in the 20s (Curry Hill)"),
        ("greek in astoria", "Greek food in Astoria"),
        ("ukrainian food in the east village", "Ukrainian/Eastern European food in the East Village"),
        ("dominican food in washington heights", "Dominican food in Washington Heights/Inwood"),
    ],
    "attribute": [
        ("no reservation needed", "walk-in friendly, no reservation required"),
        ("outdoor seating", "a place with outdoor seating, patio or backyard"),
        ("quiet enough to talk", "a restaurant quiet enough for conversation"),
        ("good cocktails with dinner", "a restaurant with good cocktails"),
        ("vegetarian friendly", "a place with good vegetarian options"),
        ("vegan options", "a place with vegan food"),
        ("gluten free", "a place that handles gluten free well"),
        ("chef's counter", "a restaurant with a chef's counter / counter seating experience"),
        ("byob", "a bring-your-own-bottle restaurant"),
        ("cash only", "a cash-only restaurant"),
        ("dog friendly patio", "a place where you can sit with a dog"),
        ("great service", "a restaurant with excellent service"),
        ("quick lunch near the office", "a fast, convenient lunch spot"),
        ("huge portions", "a place with big portions"),
        ("live music with dinner", "a restaurant with live music"),
    ],
    "avoid_negative": [
        ("overrated spots", "places people say are overrated (avoid intent)"),
        ("tourist traps", "places people call tourist traps (avoid intent)"),
        ("places that went downhill", "restaurants that used to be good and declined"),
        ("worst service", "restaurants with bad service (avoid intent)"),
        ("not worth the hype", "hyped places that disappoint (avoid intent)"),
        ("got food poisoning", "places people say made them sick (avoid intent)"),
        ("long line not worth it", "places where the wait isn't worth it (avoid intent)"),
        ("closed restaurants i miss", "restaurants that have closed and are missed"),
        ("disappointing michelin star", "Michelin-starred places that disappointed"),
    ],
    "paraphrase_slang": [
        ("spot that slaps", "a place whose food is excellent (slang)"),
        ("hidden gem", "a lesser-known but excellent place"),
        ("hole in the wall", "a small, unassuming but good place"),
        ("underrated", "a place better than its reputation"),
        ("bussin wings", "great chicken wings (slang)"),
        ("lowkey good dumpling spot", "an under-the-radar good dumpling place"),
        ("fire pizza", "excellent pizza (slang)"),
        ("no frills old school joint", "an old-school, unpretentious place"),
        ("legit authentic", "authentic, the real thing"),
        ("banger sandwich", "an excellent sandwich (slang)"),
        ("where locals actually eat", "a non-touristy place locals go to"),
        ("goated bakery", "an excellent bakery (slang)"),
    ],
    "hard_case": [
        ("quiet romantic spot, not loud", "a romantic place that is quiet; loud places do not qualify"),
        ("pizza that isn't a dollar slice", "quality pizza, not the cheap dollar-slice kind"),
        ("italian not in little italy", "good Italian food outside Little Italy"),
        ("chinese food that isn't americanized", "authentic Chinese food"),
        ("a steakhouse other than peter luger", "a recommended steakhouse that is not Peter Luger"),
        ("good food near penn station", "a good place to eat near Penn Station / Herald Sq"),
        ("restaurant with no wait", "a place where you get seated quickly"),
        ("sushi that isn't expensive", "affordable sushi"),
        ("brunch spot that takes reservations", "brunch place where you can reserve"),
        ("spicy food that actually has heat", "genuinely spicy food"),
        ("bar food that's actually good", "a bar with notably good food"),
        ("happy hour", "a happy hour with drink/food deals"),
        ("cold noodles", "a place serving cold noodle dishes"),
        ("jewish deli", "a classic Jewish deli"),
        ("not a chain", "an independent restaurant rather than a chain"),
    ],
}

SEED = 7
HOLDOUT_SHARE = 0.2


def main():
    rng = random.Random(SEED)
    rows = []
    n = 0
    for cat, qs in Q.items():
        k = max(1, round(len(qs) * HOLDOUT_SHARE))
        hold = set(rng.sample(range(len(qs)), k))
        for i, (text, intent) in enumerate(qs):
            n += 1
            rows.append({"qid": f"q{n:03d}", "text": text, "category": cat,
                         "intent": intent, "holdout": i in hold})
    with open(HERE / "queries.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(len(rows), "queries,", sum(r["holdout"] for r in rows), "holdout")


if __name__ == "__main__":
    main()
