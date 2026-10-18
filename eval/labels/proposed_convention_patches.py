"""PROPOSED gold patches for the new extraction conventions (eval/CONVENTIONS.md).

NOT APPLIED and not imported by build_gold.py. Every entry is a candidate found by a
heuristic scan or from v6's benchmark output, and needs a human read before it moves
into labels/adjudication.py (same tuple format: label id, action, canonical key, data,
reason). Entries under V2_TOPUP target v2 top-up items, which have no patch hook yet:
eval/v2/build_v2.py would need one that applies them by v2 item id.

Counts: {'line tip': 46, 'question reply marked ambiguous': 13, 'reference v6 found, gold lacks': 47, 'lukewarm': 1}
"""
from common import M  # noqa: F401  (used by the "add" entries)

PROPOSED = [
    # [line tip]
    ('c0006', "alt", 'shmone wine bar', {"wait": [-1]}, 'line/timing tip: wait in | You could go wait in line at Via Carota they’d give a table for 4 for walk ins f'),
    # [line tip]
    ('c0117', "alt", 'peter luger steakhouse', {"wait": [-1]}, 'line/timing tip: wait in | As a defender and lover of this burger and establishment, I will say first of al'),
    # [line tip]
    ('c0117', "alt", 'minetta tavern', {"wait": [-1]}, 'line/timing tip: wait in | As a defender and lover of this burger and establishment, I will say first of al'),
    # [line tip]
    ('c0117', "alt", 'jg melon', {"wait": [-1]}, 'line/timing tip: wait in | As a defender and lover of this burger and establishment, I will say first of al'),
    # [line tip]
    ('c0262', "alt", 'quality meats', {"wait": [-1]}, 'line/timing tip: busy | Sat in the main dining room, busy night as it was Friday pre Valentine’s Day. The a'),
    # [line tip]
    ('c0344', "alt", 'fu zhou wei zhong wei ju xiang feng wei', {"wait": [-1]}, 'line/timing tip: busy | Yes - these dumplings are best in the city (actually, I’m a gatekeeping asshole and'),
    # [line tip]
    ('t004/t1_p6puvov', "alt", 'mamas too', {"wait": [-1]}, 'line/timing tip: a line | Mamas too is pretty good, but Village Square is only a couple blocks away, cheape'),
    # [line tip]
    ('t014/t1_olcw9wi', "alt", 'utopia bagels', {"wait": [-1]}, 'line/timing tip: waiting for | Do it! I’m waiting for their new location to open by me in midtown.'),
    # [question reply marked ambiguous]
    ('c0042', "set", 'wonder', {"ambiguous": False}, 'question reply counts as a mention: Didn’t they purchase GrubHub? Guess it’s not a “third-party delivery service” if'),
    # [question reply marked ambiguous]
    ('c0061', "set", 'two doors down', {"ambiguous": False}, 'question reply counts as a mention: Is that everyday or just weekdays?'),
    # [question reply marked ambiguous]
    ('c0178', "set", 'five iron golf', {"ambiguous": False}, "question reply counts as a mention: Try spamming this one more time, guys. Last time wasn't it specially for the sta"),
    # [question reply marked ambiguous]
    ('c0209', "set", 'traif', {"ambiguous": False}, 'question reply counts as a mention: have you gone recently? wondering if quality has changed it’s on my list but a l'),
    # [question reply marked ambiguous]
    ('c0216', "set", 'shake shack', {"ambiguous": False}, 'question reply counts as a mention: They don’t use that blend any more??!! That blend was shake shacks calling card '),
    # [question reply marked ambiguous]
    ('c0236', "set", 'essex market', {"ambiguous": False}, 'question reply counts as a mention: Maybe Essex Market?'),
    # [question reply marked ambiguous]
    ('c0280', "set", 'taco bell', {"ambiguous": False}, 'question reply counts as a mention: If im going to lick a chalupa im not paying for it, kapeesh? 🤌'),
    # [question reply marked ambiguous]
    ('c0294', "set", 'johnnys bar', {"ambiguous": False}, 'question reply counts as a mention: Is this the tiny place in Greenwich Ave I can never find?'),
    # [question reply marked ambiguous]
    ('c0357', "set", 'fish market', {"ambiguous": False}, 'question reply counts as a mention: What’s your fave thing to get there? It’s on my list'),
    # [question reply marked ambiguous]
    ('t001/t1_oxitb7w', "set", 'pressed juicery', {"ambiguous": False}, 'question reply counts as a mention: What??? Nooooo. I just went there last week!!!'),
    # [question reply marked ambiguous]
    ('t002/t1_o3kxbbu', "set", 'noonas ice cream', {"ambiguous": False}, 'question reply counts as a mention: Let me guess… $16 each?'),
    # [question reply marked ambiguous]
    ('t004/t1_p64hx5p', "set", 'paulie gees slice shop', {"ambiguous": False}, 'question reply counts as a mention: Do they still have a C health rating?'),
    # [question reply marked ambiguous]
    ('t011/t1_obk6ris', "set", 'red hook tavern', {"ambiguous": False}, 'question reply counts as a mention: what’s the draw?'),
    # [reference v6 found, gold lacks]
    ('c0047', "add", None, M('Shuko', named_in='parent', first=None, why='reference only: Yeah I was no longer regular, after Masato left, so I started going to'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('c0118', "add", None, M('Deep Queens', named_in='parent', first=None, why='reference only: I don’t remember but I’m pretty sure it wasn’t even a place. Just a *w'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('c0259', "add", None, M('Ulysses Bar', named_in='parent', first=None, why='reference only: dunno. i would guess they buy lobsters from restaurants that don’t sel'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('c0315', "add", None, M('Los Tacos', named_in='parent', first=None, why="reference only: I gotta try their truck spot, I've only ever had at the restaurant"), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('c0361', "add", None, M('Lucky Charlie', named_in='parent', first=None, why='reference only: They do huge late night volume with it being on top of the LIRR stop, '), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('c0376', "add", None, M('888 Hudson Thai', named_in='parent', first=None, why='reference only: I did. They said they cannot investigate for up to 36 days. I’m unsure'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t001/t1_owlhmv1', "add", None, M('Pressed Juicery', named_in='parent', first=None, why='reference only: Killed by proteinmaxing'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t001/t1_owx1azt', "add", None, M('Pressed Juicery', named_in='parent', first=None, why='reference only: It’s partially bc the markup on juices and the profit margins are the '), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t001/t1_owtdezk', "add", None, M('Pressed Juicery', named_in='parent', first=None, why='reference only: That rent too high'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t001/t1_ox41sx2', "add", None, M('Pressed Juicery', named_in='parent', first=None, why='reference only: Where is this at .. upper east side?'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t001/t1_oxci02s', "add", None, M('Pressed Juicery', named_in='parent', first=None, why='reference only: Thanks.. wow .. UES also closed and so did a few other locations in CT'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t002/t1_o430eg1', "add", None, M("Noona's Ice Cream", named_in='parent', first=None, why='reference only: Online order via Uddermilk'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t004/t1_p64he5x', "add", None, M('Mama’s Too', named_in='parent', first=None, why='reference only: Where is it located?'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t004/t1_p64hx5p', "add", None, M('Mama’s Too', named_in='parent', first=None, why='reference only: Do they still have a C health rating?'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t004/t1_p69bw81', "add", None, M('Mama’s Too', named_in='parent', first=None, why='reference only: which ones sound weird?'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t004/t1_p69u9at', "add", None, M("Mama's Too", named_in='parent', first=None, why='reference only: The one with pears'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t006/t1_p2ym4d8', "add", None, M('Eleven Madison Park', named_in='parent', first=None, why='reference only: This was matching flavors of chocolate bars. I was amazingly 0 for 4.'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t006/t1_p31z3t5', "add", None, M('Eleven Madison Park', named_in='parent', first=None, why="reference only: Were they not 'trying' in the past? or is that just a dig at their cha"), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t011/t1_obj5hsr', "add", None, M('red hook tavern', named_in='parent', first=None, why='reference only: Was it worth the wait?'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t011/t1_oboxx5i', "add", None, M('red hook tavern', named_in='parent', first=None, why='reference only: What would a Sunday lunch for 4 look like without reservations?'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t017/t1_oon31k0', "add", None, M('Java', named_in='parent', first=None, why='reference only: Looks like we will have to make a Queens trip 😂'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t017/t1_oonvqx1', "add", None, M('Kopitiam', named_in='parent', first=None, why='reference only: And only one stop from Brooklyn on the F'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('c0343', "add", None, M('TV Eye', named_in='parent', first=None, why='reference only: This is so cool, can’t wait to try and see your ascension'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t001/t1_owp7pum', "add", None, M('Pressed Juicery', named_in='parent', first=None, why="reference only: Whoa — I've always preferred smoothies but I didn't even clock that ju"), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('c0018', "add", None, M('Pies n Thighs', named_in='parent', first=None, why='reference only: My rule of thumb is when trying some new or hole-in-the-wall place, I '), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('c0098', "add", None, M('888 Hudson Thai', named_in='parent', first=None, why='reference only: You can try reposting the 2 star review again with a different Google '), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('c0151', "add", None, M("Katz's", named_in='parent', first=None, why="reference only: Yes, don't need kosher. Just need a delicious beef brisket for 22 peop"), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('c0160', "add", None, M('Tomi Jazz', named_in='parent', first=None, why='reference only: Where should I go next weekend? First time in NYC in many years. Prefe'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t001/t1_owm349b', "add", None, M('Pressed Juicery', named_in='parent', first=None, why='reference only: Just remove the healthy fiber first'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t004/t1_p64l1oi', "add", None, M('Mama’s Too', named_in='parent', first=None, why='reference only: They have a slice shop in east village now that I think is rated bette'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t009/t1_p7lwbu7', "add", None, M('4 Charles', named_in='parent', first=None, why='reference only: you must have an appetite like John Cena to be able to eat all that!'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t009/t1_p7lxsg4', "add", None, M('4 Charles', named_in='parent', first=None, why='reference only: Most people don’t eat everything that you did…'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t013/t1_oh36mnz', "add", None, M('Market Basket', named_in='parent', first=None, why='reference only: Next time I go I’m bringing back a suitcase full of tinned seafood'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t001/t1_owsdb8z', "add", None, M('Juice Press', named_in='parent', first=None, why='reference only: oh wow i want to know more about this! 🍿'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t002/t1_o3l2skt', "add", None, M("Noona's Ice Cream", named_in='parent', first=None, why='reference only: need to get into ube im so srs'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t002/t1_o3lbclv', "add", None, M("Noona's Ice Cream", named_in='parent', first=None, why='reference only: It’s a small business get a grip literally one person doing everything'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t004/t1_p64he5x', "add", None, M('Paulie Gee’s', named_in='parent', first=None, why='reference only: Where is it located?'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t006/t1_p2ym7g6', "add", None, M('Eleven Madison Park', named_in='parent', first=None, why='reference only: I Almost stayed inside the lines!'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t011/t1_obhgoy5', "add", None, M('Red Hook Tavern', named_in='parent', first=None, why='reference only: Good luck, lemme know how it goes'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t015/t1_nl1njov', "add", None, M('Rudy’s', named_in='parent', first=None, why='reference only: *Yooooou* were high It was a cryin’ disgrace'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('t014/t1_olbm9d1', "add", None, M('Choice', named_in='comment', first=None, why='reference only: I love the chicken salad sandwich from Choice Brooklyn. I can’t vouch '), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('c0167', "add", None, M('Chino Latino', named_in='comment', first=None, why='reference only: Bagels: go get you a bagel and lox at Russ and Daughters, Barney Green'), "candidate from v6 output; check it is a real NYC place"),
]

V2_TOPUP = [
    # [line tip]
    ('v0251', "alt", 'carnitas ramirez', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0251', "alt", 'tacos el bronco', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0251', "alt", 'joes pizza', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0251', "alt", 'prince street pizza', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0251', "alt", 'village square pizza', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0251', "alt", 'bleecker street pizza', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0251', "alt", 'slicehaus pizzeria', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0251', "alt", 'scarrs pizza', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0251', "alt", 'upside pizza', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0251', "alt", 'grand street pizza', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0251', "alt", 'cellos pizzeria', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0251', "alt", 'new york pizza suprema', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0251', "alt", 'unregular pizza', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0251', "alt", 'marinara pizza', {"wait": [-1]}, 'line/timing tip: a line | Taqueria Ramirez: very good al pastor tacos. There might be a line and there’s ba'),
    # [line tip]
    ('v0274', "alt", 'cipriani', {"wait": [-1]}, "line/timing tip: busy | The merengue cake at cipriani is fantastic! If you're dressed warm you can sit outs"),
    # [line tip]
    ('v0274', "alt", 'lucia pizza', {"wait": [-1]}, "line/timing tip: busy | The merengue cake at cipriani is fantastic! If you're dressed warm you can sit outs"),
    # [line tip]
    ('v0274', "alt", 'prince street pizza', {"wait": [-1]}, "line/timing tip: busy | The merengue cake at cipriani is fantastic! If you're dressed warm you can sit outs"),
    # [line tip]
    ('v0274', "alt", 'la esquina', {"wait": [-1]}, "line/timing tip: busy | The merengue cake at cipriani is fantastic! If you're dressed warm you can sit outs"),
    # [line tip]
    ('v0274', "alt", '12 chairs cafe', {"wait": [-1]}, "line/timing tip: busy | The merengue cake at cipriani is fantastic! If you're dressed warm you can sit outs"),
    # [line tip]
    ('v0274', "alt", 'shuka', {"wait": [-1]}, "line/timing tip: busy | The merengue cake at cipriani is fantastic! If you're dressed warm you can sit outs"),
    # [line tip]
    ('v0274', "alt", 'cleveland', {"wait": [-1]}, "line/timing tip: busy | The merengue cake at cipriani is fantastic! If you're dressed warm you can sit outs"),
    # [line tip]
    ('v0274', "alt", 'rubirosa', {"wait": [-1]}, "line/timing tip: busy | The merengue cake at cipriani is fantastic! If you're dressed warm you can sit outs"),
    # [line tip]
    ('v0274', "alt", 'parm', {"wait": [-1]}, "line/timing tip: busy | The merengue cake at cipriani is fantastic! If you're dressed warm you can sit outs"),
    # [line tip]
    ('v0274', "alt", 'dominique ansel bakery', {"wait": [-1]}, "line/timing tip: busy | The merengue cake at cipriani is fantastic! If you're dressed warm you can sit outs"),
    # [line tip]
    ('v0274', "alt", 'black seed bagels', {"wait": [-1]}, "line/timing tip: busy | The merengue cake at cipriani is fantastic! If you're dressed warm you can sit outs"),
    # [line tip]
    ('v0274', "alt", 'russ daughters cafe', {"wait": [-1]}, "line/timing tip: busy | The merengue cake at cipriani is fantastic! If you're dressed warm you can sit outs"),
    # [line tip]
    ('v0295', "alt", 'zibetto espresso bar', {"wait": [-1]}, 'line/timing tip: go early | Zibetto is the best in NY. Original location for that old school vibe. Its wher'),
    # [line tip]
    ('v0346', "alt", 'raouls', {"wait": [-1]}, 'line/timing tip: packed | Raoul’s specializes in steak frites with a famous au poivre sauce. Either that or'),
    # [line tip]
    ('v0346', "alt", 'minetta tavern', {"wait": [-1]}, 'line/timing tip: packed | Raoul’s specializes in steak frites with a famous au poivre sauce. Either that or'),
    # [line tip]
    ('v0362', "alt", '2nd ave deli', {"wait": [-1]}, 'line/timing tip: the line | The other big two delis are second ave deli and pastrami queen. Katz’s is my fa'),
    # [line tip]
    ('v0362', "alt", 'pastrami queen', {"wait": [-1]}, 'line/timing tip: the line | The other big two delis are second ave deli and pastrami queen. Katz’s is my fa'),
    # [line tip]
    ('v0396', "alt", 'carbone', {"wait": [-1]}, 'line/timing tip: a line | It feels like every new opening is going for the tiktok crowd now, it’s awful. Ev'),
    # [line tip]
    ('v0396', "alt", 'don angie', {"wait": [-1]}, 'line/timing tip: a line | It feels like every new opening is going for the tiktok crowd now, it’s awful. Ev'),
    # [line tip]
    ('v0415', "alt", 'grand street pizza', {"wait": [-1]}, 'line/timing tip: wait in | My pick for pizza in the area would be [Grand St. Pizza](https://maps.app.goo.gl'),
    # [line tip]
    ('v0416', "alt", 'soothr', {"wait": [-1]}, 'line/timing tip: the line | What do you like? A bungalow res is basically impossible. "must eats" are mostl'),
    # [line tip]
    ('v0430', "alt", 'rose bar', {"wait": [-1]}, 'line/timing tip: crowded | The old Rose Bar in the Gramercy Park Hotel used to be notorious for this. **I b'),
    # [line tip]
    ('v0430', "alt", 'spin', {"wait": [-1]}, 'line/timing tip: crowded | The old Rose Bar in the Gramercy Park Hotel used to be notorious for this. **I b'),
    # [line tip]
    ('v0466', "alt", '787 coffee', {"wait": [-1]}, 'line/timing tip: packed | The 787 in Tribeca is always hopping, for some reason. It’s small but lots of sea'),
    # [reference v6 found, gold lacks]
    ('v0433', "add", None, M('888 Hudson Thai', named_in='parent', first=None, why='reference only: I did. They closed it within 24 hours and said it was an “isolated inc'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('v0460', "add", None, M('El Califa de Leon', named_in='parent', first=None, why='reference only: It is tho. Thats how it works.'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('v0288', "add", None, M("Carmine's", named_in='parent', first=None, why='reference only: It\'s colloquially called a "Sunday salad" and you can find it at a var'), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('v0344', "add", None, M('Sugarfish', named_in='parent', first=None, why='reference only: For what it’s worth a lot of my Japanese friends are pretty aghast at '), "candidate from v6 output; check it is a real NYC place"),
    # [reference v6 found, gold lacks]
    ('v0458', "add", None, M('Lisbonata', named_in='parent', first=None, why='reference only: The macau style ones are the most similar to the portuguese ones thoug'), "candidate from v6 output; check it is a real NYC place"),
    # [lukewarm]
    ('v0372', "alt", 'russ daughters cafe', {"food": [-1]}, 'lukewarm is negative: their bagels are very meh'),
]
