"""v5, comment mode: one Reddit comment in, its restaurant mentions out.

Inputs are production's own comment-mode rendering (POST TITLE, the first 400
chars of the POST BODY, the PARENT COMMENT, the COMMENT), so only the system
prompt changes. That is why this file defines no build_user_message. The
examples are laid out the same way. The shared wording lives in v5_common.py.
"""

import hashlib
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "v5_common", os.path.join(os.path.dirname(os.path.abspath(__file__)), "v5_common.py"))
_c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_c)
M, OUT, I = _c.mention, _c.output, _c.comment_input


def ex(inp, out, why):
    return inp + "\n" + out + "\nWhy: " + why


EXAMPLES = "\n\n".join([
    "EXAMPLES (invented places)",

    ex(I("Best Thai in Queens?", "Thai - Siam Garden and Lemongrass Hut"),
       OUT(M("Siam Garden", desc=["Thai"]),
           M("Lemongrass Hut", desc=["Thai"])),
       '"Thai" is a heading, not a restaurant. Both names answer a request for places, so both '
       'are endorsements: reference_only false, every aspect null.'),

    ex(I("Dinner near Union Square?", "Try Kumo, the spicy miso ramen is great",
         body="Last time we went to Harbor Fish and loved it. Looking for something new."),
       OUT(M("Kumo", food="good", exp="ate_there", liked=["spicy miso ramen"])),
       'Harbor Fish is named only in the POST BODY and the comment says nothing about it, so it '
       'is not extracted. The praised dish sets food.'),

    ex(I("Best bagel in Brooklyn?",
         "Bagel Hut is the best I've ever had. Corner Bagels is pretty solid. "
         "Lox Box is ok, nothing special"),
       OUT(M("Bagel Hut", food="rave", exp="ate_there"),
           M("Corner Bagels", food="decent", exp="ate_there"),
           M("Lox Box", food="meh", exp="ate_there")),
       '"the best I\'ve ever had" is "rave". "pretty solid" is "decent". "ok" and "nothing '
       'special" are a knock: "meh", never "decent".'),

    ex(I("Most overrated restaurant in Manhattan?",
         "Copper Kettle. Also Marlowe's, the service is slow"),
       OUT(M("Copper Kettle", food="meh", desc=["overrated"]),
           M("Marlowe's", food="meh", service="bad", exp="ate_there", desc=["overrated"])),
       'the post asks for overrated places, so each bare name takes that judgment: "overrated" '
       'is food "meh" in the LEVELS table, plus descriptor "overrated". "the service is slow" '
       'adds service "bad".'),

    ex(I("Late night food in the East Village", "Is Okiku still cash only?"),
       OUT(M("Okiku", ref=True)),
       'a question about a place is a reference. "cash only" is asked, not stated, so there is '
       'no descriptor.'),

    ex(I("Golden Lotus closing?", "No, they just moved to the Flushing location. It's BYOB now too"),
       OUT(M("Golden Lotus", ref=True, hood="Flushing", desc=["BYOB"])),
       'the comment is about the place the post names, so the name is copied from the post. It '
       'states facts and judges nothing, so it is a reference that still carries the location '
       'and "BYOB".'),

    ex(I("Where should I eat near Times Square?",
         "Bridge Diner is a tourist trap. Pricey too. Go to Sal's Slices instead, "
         "get the grandma slice"),
       OUT(M("Bridge Diner", food="bad", neg=True, price="pricey", exp="ate_there",
             desc=["tourist trap"]),
           M("Sal's Slices", food="good", exp="ate_there", liked=["grandma slice"])),
       '"tourist trap" judges the place, so food is "bad". "Go to Sal\'s Slices instead" tells '
       'people to avoid Bridge Diner. "Pricey" is price; nothing says whether it is worth it, so '
       'value stays null. "get the grandma slice" recommends a dish, and food follows it.'),

    ex(I("Seafood for an anniversary?", "Harbor Fish is really good but not worth the price"),
       OUT(M("Harbor Fish", food="good", value="bad", exp="ate_there")),
       '"not worth the price" is value "bad". It says what the place is not worth, so it is not '
       'an avoid: is_negated false.'),

    ex(I("Brunch in Park Slope", "honestly mid, and the wait is insane",
         parent="Marlowe's is my go-to brunch spot"),
       OUT(M("Marlowe's", food="meh", wait="bad", exp="ate_there")),
       'the comment never types a name, but it judges the place its parent names, so it is a '
       'mention of "Marlowe\'s". "mid" is "meh", never "decent".'),

    ex(I("Gino's, Pepper Pie or Nonna Rosa?",
         "I'd skip everyone you mentioned. Gino's, Pepper Pie, Nonna Rosa - tourist traps now"),
       OUT(M("Gino's", food="bad", neg=True, exp="ate_there", desc=["tourist traps"]),
           M("Pepper Pie", food="bad", neg=True, exp="ate_there", desc=["tourist traps"]),
           M("Nonna Rosa", food="bad", neg=True, exp="ate_there", desc=["tourist traps"])),
       'an avoid instruction at the head of a list applies to EVERY name in it. This is the '
       'easiest thing to get wrong.'),

    ex(I("Steak for a birthday dinner?",
         "Don't go to Tidewater, it's all seafood. And skip Green Bowl, the owner "
         "donates to causes I won't support"),
       OUT(M("Tidewater", neg=True, desc=["all seafood"]),
           M("Green Bowl", neg=True)),
       'both are avoids, but neither reason judges the food, value, service, room or wait: one '
       'is a mismatch with what the asker wants, the other is about the owner. So is_negated is '
       'true and every aspect stays null. Neither says they went, so experience is "unclear".'),

    ex(I("Sichuan in Flushing?",
         "Pepper House is hit or miss. Get the cumin lamb, skip the dumplings. "
         "I also had the cucumber salad. Cheap for the area"),
       OUT(M("Pepper House", food="mixed", price="cheap", exp="ate_there",
             liked=["cumin lamb"], disliked=["dumplings"], mentioned=["cucumber salad"])),
       '"hit or miss" is the verdict on the food overall, so food is "mixed". Each dish goes in '
       'exactly one list: recommended, judged negatively, or only named.'),

    ex(I("Omakase under $100?", "Haven't been but my friend swears by Okiku. Supposedly it's like Hoshi"),
       OUT(M("Okiku", food="good", exp="secondhand"),
           M("Hoshi", ref=True)),
       'the opinion on Okiku is the friend\'s, so experience is "secondhand"; the opinion is '
       'still recorded. Hoshi is only a yardstick, so it is a reference.'),

    ex(I("What closed spot do you miss most?",
         "Silver Pond. Closed last year, their soup dumplings were the best"),
       OUT(M("Silver Pond", ref=True, exp="ate_there", mentioned=["soup dumplings"],
             desc=["closed"])),
       'a closed place is a reference with "closed" in descriptors and every aspect null, even '
       'when it is remembered fondly. Its remembered dish goes in dishes_mentioned.'),

    ex(I("Ramen recs?", "Kumo over Hikari any day"),
       OUT(M("Kumo", food="good", exp="ate_there"),
           M("Hikari", food="meh", exp="ate_there")),
       'Hikari lost the comparison, so it is food "meh" and is_negated stays false.'),

    ex(I("Best slice near Court St?",
         "went last month, worst slice I've had and the guy at the counter was rude. "
         "regretted going",
         parent="Tony's Corner on Court St"),
       OUT(M("Tony's Corner", food="awful", service="bad", exp="ate_there", disliked=["slice"])),
       'named from the parent. "worst I\'ve had" and "regretted going" are "awful". It is a bad '
       'review, not an instruction to others, so is_negated is false.'),

    ex(I("Best bagels?", "Honestly any bodega bagel with scallion cream cheese hits"),
       OUT(),
       'no place is named or pointed at.'),
])

SYSTEM_PROMPT = f"""You extract restaurant mentions from ONE Reddit comment posted in a New York City food subreddit.

The input has these parts, in this order, separated by blank lines: POST TITLE, usually POST BODY (cut at 400 characters), sometimes PARENT COMMENT (the comment this one replies to), and then COMMENT. The other parts exist only to make sense of the COMMENT. Extract from the COMMENT. Never extract a place that is only named in the title, body or parent -- unless the COMMENT says something about it or asks about it. A comment that gives an opinion without repeating the name IS a mention of the place it replies about.

Output ONLY a JSON object. No prose, no code fences:

{{"mentions": [ {{...}}, {{...}} ]}}

Use {{"mentions": []}} only when the comment names and points at no place at all. That is a normal answer.

{_c.KINDS}

{_c.FIELDS}

{_c.LEVEL_TABLE}

{_c.OTHER_FIELDS}

{_c.RULES}

{EXAMPLES}"""

PROMPT_HASH = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]
