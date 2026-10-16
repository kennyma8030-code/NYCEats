"""Post-adjudication gold corrections, applied by build_gold.py on top of the blind batches.

Each was found while re-reading a disagreement between gold and the ORIGINAL
production extraction (eval/baseline/disagreements.jsonl). The blind labels are
left untouched in batchNN.py so the change is auditable; gold_changes.md
explains each one. Actions:
  alt    add accepted alternative values: data = {field: [values]}
  set    set mention fields: data = {field: value}
  add    append a new mention: data = M(...) result
  unc    add a field to uncertain_fields: data = field name
"""
from common import M

PATCHES = [
    ("c0014", "alt", "salt hanks", {"wait": [1, 2]}, "'order for pickup and skip the line' can be read as easy wait"),
    ("c0065", "alt", "cote", {"atmosphere": [1]}, "'in a modern environment. It works.' is a mild room positive"),
    ("c0067", "add", None, M("Great Nosh", "The Great Nosh", type="food_hall", amb=True, alt={"food": [1], "value": [-2]},
                             why="food festival with vendor booths; '$40 is waaay overpriced' about its tickets"),
     "multi-vendor food event: in-scope reading (like Smorgasburg) is defensible"),
    ("c0094", "alt", "oven slice", {"value": [-1, -2]}, "'not worth anything other than being closest' is a value knock"),
    ("c0094", "alt", "johnnys pizzeria", {"value": [1]}, "'much better slice for 1.50 more' is a value judgment"),
    ("c0114", "alt", "4 charles prime rib", {"value": [-2]}, "'not worth all that' can be a strong value knock"),
    ("c0125", "add", None, M("the Kitchen Table", "The Modern Kitchen Table", amb=True, first=False,
                             why="The Modern's chef's-table experience named separately"),
     "a named sub-venue of The Modern"),
    ("c0176", "alt", "mongolian momo king", {"food": [1]}, "offered as a lead in answer to the question: rule 2 (named as an answer)"),
    ("c0206", "alt", "dunkin", {"food": [1]}, "chosen 'if i want caffeine' is a mild positive"),
    ("c0206", "alt", "mcdonalds", {"food": [1]}, "same"),
    ("c0242", "alt", "amandas good morning cafe", {"value": [1, 2]}, "'don't want to break the bank' reads as good value"),
    ("c0282", "alt", "katzs delicatessen", {"food": [-1]}, "'a measly sandwich' judges the food"),
    ("c0345", "alt", "brooklyn dop", {"atmosphere": [1]}, "'Looked quite clean' is a room positive"),
    ("c0353", "unc", "cesar", "is_negated", "'I'd dump Cesar' (from the list) can be read as an avoid"),
    ("c0363", "add", None, M("Carbone", first=None, why="'I worked for Mario at Carbone for a year': named reference"),
     "missed in blind labeling: a named reference is a required mention under the owner's rules"),
    ("c0365", "alt", "bar goto niban", {"atmosphere": [2, 3]}, "'perfect for this' (a romantic quiet date) is about the room"),
    ("c0368", "alt", "hillstone manhattan", {"atmosphere": [1, 2]}, "'nice view' read literally rather than as sarcasm"),
    ("t004/t1_p6732eo", "set", "lindustrie pizzeria", {"ambiguous": True},
     "'I don't like their pizza like lindustry' also reads as 'not the way I like L'industrie'"),
    ("t001/t1_owksvvi", "add", None, M("Pressed", "Pressed Juicery", also=("pressed",), named_in="title", type="chain", amb=True,
                                       why="'People are just doing it themselves more' about Pressed's decline; nameless"),
     "nameless remark about the post's subject"),
    ("t001/t1_owp4j06", "add", None, M("Pressed", "Pressed Juicery", also=("pressed",), named_in="title", type="chain", amb=True,
                                       why="'they were such a force' — juice shops incl. Pressed; nameless"),
     "nameless remark about the post's subject"),
    ("t005/t1_o2c1yf4", "alt", "mangia", {"value": [1, 2]}, "'not cheap, but the quality is very good' reads as fair value"),
    ("t010/t1_ozsqh90", "add", None, M("Mama’s Too", "Mama's Too", also=("mamas too",), named_in="title", amb=True,
                                       why="'just these 2 places' — nameless reference"), "nameless reference to the title places"),
    ("t010/t1_ozsqh90", "add", None, M("Red Gate Bakery", named_in="title", type="cafe_bakery_dessert", amb=True,
                                       why="'just these 2 places' — nameless reference"), "same"),
]


def apply(labels):
    """labels: {label_id: (mentions, note)}; returns the number of patches applied."""
    n = 0
    for lid, action, key, data, _why in PATCHES:
        ms, note = labels[lid]
        if action == "add":
            ms.append(data)
            n += 1
            continue
        target = [m for m in ms if m["canonical_key"] == key]
        assert len(target) == 1, (lid, key, [m["canonical_key"] for m in ms])
        m = target[0]
        if action == "alt":
            for field, vals in data.items():
                cur = m["aspect_alternatives"].setdefault(field, [])
                cur.extend(v for v in vals if v not in cur)
        elif action == "set":
            m.update(data)
        elif action == "unc":
            if data not in m["uncertain_fields"]:
                m["uncertain_fields"].append(data)
        n += 1
    return n
