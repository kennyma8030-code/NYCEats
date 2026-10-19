"""Offline checks for the v6 prompt, schema and adapter. No database, no model.

    python eval/v6_selftest.py

1. The schema obeys strict structured-output rules (every object closed, every
   property required, nullable enums list null) and the prompt modules load.
2. No eval comment leaks into either prompt.
3. Hand-written v6 outputs for 14 real v1 gold comments are schema-valid and,
   through v6_adapter and score.score_comment, score the way the design says
   they should. The outputs were written by reading each comment under the v6
   rules, not by copying the gold; where v6 and the gold deliberately disagree
   (price from a dollar figure, five levels against seven) the expected
   result says so.
4. The same outputs pass v4/labels.py's label check and convert to gold, in
   comment and thread mode, and a production-shaped mention passes through
   the adapter unchanged.
5. Round 4: the fixtures are written in the owner's level names and converted
   to round 4's schema form (level labels, kind, notes without level or dish)
   before they are validated and adapted, so the adapter's label mapping is
   exercised on every case. The frozen rounds keep their hashes and their
   schema, the round-4 schema stays within the strict-mode union limit, every
   comment_rows sidecar renders with build_user_message, and excluded kinds
   drop out of the counts.
"""

import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "v4"))
import score as S  # noqa: E402
import labels as L  # noqa: E402
import v6_adapter as A  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, "prompts", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------ schema checks
def lint_strict(node, path="$", defs=None):
    """Strict-mode rules shared by OpenAI and Anthropic structured outputs."""
    errs = []
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            if node.get("additionalProperties") is not False:
                errs.append(f"{path}: additionalProperties must be false")
            if set(node.get("required", [])) != set(node.get("properties", {})):
                errs.append(f"{path}: every property must be required")
        t = node.get("type")
        if "enum" in node and isinstance(t, list) and "null" in t and None not in node["enum"]:
            errs.append(f"{path}: nullable enum must list null")
        for bad in ("minimum", "maximum", "minLength", "maxLength", "pattern", "minItems", "maxItems"):
            if bad in node:
                errs.append(f"{path}: {bad} is not supported")
        for k, v in node.items():
            errs += lint_strict(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            errs += lint_strict(v, f"{path}[{i}]")
    return errs


def validate(value, node, root, path="$"):
    """A minimal JSON Schema validator for the subset the v6 schema uses."""
    if "$ref" in node:
        return validate(value, root["$defs"][node["$ref"].split("/")[-1]], root, path)
    errs = []
    types = node.get("type")
    types = types if isinstance(types, list) else [types] if types else []
    pytype = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
    ok = not types or any(
        (t == "integer" and isinstance(value, int) and not isinstance(value, bool)) or
        (t in pytype and isinstance(value, pytype[t])) for t in types)
    if not ok:
        return [f"{path}: {value!r} is not {types}"]
    if "enum" in node and value not in node["enum"]:
        errs.append(f"{path}: {value!r} not in enum")
    if isinstance(value, dict):
        props = node.get("properties", {})
        for k in node.get("required", []):
            if k not in value:
                errs.append(f"{path}: missing {k}")
        for k, v in value.items():
            if k not in props:
                errs.append(f"{path}: extra key {k}")
            else:
                errs += validate(v, props[k], root, f"{path}.{k}")
    if isinstance(value, list) and "items" in node:
        for i, v in enumerate(value):
            errs += validate(v, node["items"], root, f"{path}[{i}]")
    return errs


# ------------------------------------------------------------ fixtures
TO_LABEL = {v: k for k, v in A.LEVEL_MAP.items()}


def M(name, opinion, overall=None, *, named_in="comment", experience="firsthand", taste=None,
      value=None, service=None, atmosphere=None, wait=None, avoid=False,
      dishes=(), price=None, timeframe="current", trend=None, status=None, tags=(), notes=(),
      location=None, kind="restaurant"):
    """A mention in the owner's level names; r4() turns it into round 4's schema form."""
    return {"name": name, "named_in": named_in, "kind": kind, "location": location, "experience": experience,
            "opinion": opinion, "overall": overall,
            "aspects": {"taste": taste, "value": value, "service": service,
                        "atmosphere": atmosphere, "wait": wait},
            "avoid": avoid, "dishes": list(dishes), "price": price,
            "timeframe": timeframe, "trend": trend, "status": status, "tags": list(tags),
            "notes": list(notes)}


def r4(m):
    """Round 4's output form of a fixture: level labels, notes with only about and text."""
    lab = lambda v: TO_LABEL.get(v, v)  # noqa: E731
    out = dict(m, overall=lab(m["overall"]), aspects={k: lab(v) for k, v in m["aspects"].items()},
               dishes=[dict(d, level=lab(d["level"])) for d in m["dishes"]],
               notes=[{"about": n["about"], "text": n["text"]} for n in m["notes"]])
    return out


def R4(ms):
    return [r4(m) for m in ms]


def D(dish, level, avoid=False):
    return {"dish": dish, "level": level, "avoid": avoid}


def N(about, text, level=None, dish=None):
    return {"about": about, "text": text, "level": level, "dish": dish}


# item_id -> v6 output, with the comment it answers in a comment.
CASES = {
    # "Raouls Via carota Minetta tavern ..." under "easiest upper level places to walk in"
    "c0005": [M(n, "endorse", "positive") for n in
              ("Raouls", "Via carota", "Minetta tavern", "Cervos", "Penny", "L Artusi", "Semma", "Torrisi")],
    # "Thank you! Any specific drinks you recommend at DCP?"
    "c0008": [M("DCP", "none", experience="none", tags=["cocktails"])],
    # "i knew how good we had it i was there weekly and i miss it so much. should have never
    #  leaned in to the delivery food stuff" (Mekelburg's closed, per the post)
    "c0009": [M("Mekelburg's", "stated", "positive", named_in="context", status="closed", timeframe="past",
                notes=[N("why it closed", "leaned too far into delivery", "negative")])],
    # "You can order Salt Hank for pickup on GrubHub now and skip the line!"
    "c0014": [M("Salt Hank", "none", experience="none",
                notes=[N("ordering", "order pickup on GrubHub to skip the line")])],
    # "if you go around 4/4:40ish there always one or two free tables" (Fish Cheeks, from the title)
    "c0029": [M("Fish Cheeks", "stated", named_in="context", wait="positive",
                notes=[N("best time to go", "around 4-4:40pm there are always free tables", "positive")])],
    # "... I was never able to get a reservation to Monkey Bar, but I ate so much great food ..."
    "c0038": [M("Monkey Bar", "stated", experience="none", wait="negative")],
    # "If Rubirosa is just like that, I'd rather skip it"
    "c0044": [M("Rubirosa", "stated", "negative", experience="secondhand")],
    # "Second this. Came here to write Serafina." in "poor quality yet expensive restaurant for an enemy"
    "c0045": [M("Serafina", "stated", "negative", taste="negative", value="negative", price="expensive")],
    # "the grapefruit and yogurt at jacks wife freda is really good, although at 15$ it's highway robbery"
    "c0049": [M("jacks wife freda", "stated", "neutral", taste="positive", value="negative",
                dishes=[D("grapefruit and yogurt", "positive")],
                notes=[N("price", "$15 for the grapefruit and yogurt", "negative", "grapefruit and yogurt")])],
    # "So hard it was inedible" (Luigi's, two levels up: thread-mode context)
    "c0053": [M("Luigi’s", "stated", "very_negative", named_in="context", taste="very_negative",
                dishes=[D("pizza", "very_negative")])],
    # "Service is horrible. Def not worth it" (Chef's Table at Brooklyn Fare, from the parent)
    "c0064": [M("Chef’s Table at Brooklyn Fare", "stated", "negative", named_in="context",
                service="negative", value="negative", avoid=True)],
    # "jeeze skip lenwich"
    "c0074": [M("lenwich", "stated", "negative", avoid=True)],
    # "I wouldn't say it's worth 34 dollars for a sandwich. It was good, but not worth that much" (Salt Hank)
    "c0084": [M("Salt Hank", "stated", "neutral", named_in="context", taste="positive", value="negative",
                dishes=[D("sandwich", "positive")],
                notes=[N("price", "$34 for a sandwich", "negative", "sandwich")])],
    # "... Super Burrito. It fucking sucks. There's certainly better burritos in NY (even Chipotle ffs) &
    #  it's extremely expensive ... No one ... should pay $20+ for that shitty ass burrito."
    "c0205": [M("Super Burrito", "stated", "negative", taste="negative", value="very_negative", avoid=True,
                price="very_expensive", location="WV",
                dishes=[D("burrito", "negative")],
                notes=[N("price", "$20+ for a burrito", "negative", "burrito")]),
              M("Chipotle", "stated", notes=[N("comparison", "a better burrito than Super Burrito")])],
    # Benchmark miss (v5 filed it reference-only): "Buy their canned chili and make it yourself. They
    # aren't making it in store." under "Cincinnati Night at Edward's". Skyline (Cincinnati) is out of scope.
    "c0185": [M("Edward's", "stated", "negative", named_in="context", taste="negative",
                dishes=[D("chili", "negative")],
                notes=[N("not made in house", "the chili is canned, not made in store", "negative", "chili")])],
    # Benchmark miss ("not bad" read as praise): "Straight up. 80% normal bagel size too. They're not bad.
    # But Tal is a million times better" in a "Pop up bagels" thread.
    "c0155": [M("Pop up bagels", "stated", "negative", named_in="context", taste="negative",
                notes=[N("portion size", "bagels are 80% of normal size", "negative")]),
              M("Tal", "stated", "positive", taste="positive",
                notes=[N("comparison", "a million times better than Pop Up Bagels", "positive")])],
}

# v2 gold, keyed by v2 item id: the remaining benchmark failure quotes and the
# "scored positive" pattern (v2 weakness negative_softened_to_positive).
CASES_V2 = {
    # "...some of the best places are: 1. Extremely hard to get a reservation to, so tie with Sho post 3*
    #  2. Cost somewhere $300-$400, which is the same as the base cost of Sho roughly ... similar to
    #  Yoshino and Sho." v5 filed Sho reference-only; the trait is shared with Sho (RULES 5).
    "v0065": [M("Sho", "stated", wait="negative",
                notes=[N("price", "base cost about $300-$400")]),
              M("Yoshino", "none")],
    # "I agree with you on Semma. The dosa was amazing, but definitely not leagues ahead ... Other
    #  dishes lacked the depth and complexity I expected" (the original model scored it positive)
    "v0119": [M("Semma", "stated", "negative", taste="negative", dishes=[D("dosa", "positive")],
                notes=[N("other dishes", "other dishes lacked depth and complexity", "negative")])],
    # "I feel like moms isn't as good as it used to be ... the last time I went it was meh. Maybe swap
    #  it for Thai dinner or golden dinner?"
    "v0364": [M("moms", "stated", "negative", taste="negative", trend="declined",
                dishes=[D("mac and cheese pancake", "negative")]),
              M("Thai dinner", "endorse", "positive"), M("golden dinner", "endorse", "positive")],
    # "...The pizza is definitely not worth the wait. A good slice but only a slight step above every
    #  other NYC slice"
    "v0373": [M("Lindustrie", "stated", "negative", taste="positive", wait="negative",
                notes=[N("compared to other slices", "only a slight step above other NYC slices")])],
    # Owner decision, comparison losers get a level: "I think I actually prefer Tatiana to Kabawa, and I
    # don't rate Tatiana too highly anyway. The dishes are just not inventive ... enough to justify the
    # price. Duck sausage and goat where just nice. Matrimony as dessert was just ridiculous ... The
    # starters were the best part."
    "v0427": [M("Kabawa", "stated", "negative", taste="negative", value="negative",
                dishes=[D("duck sausage", "negative"), D("goat", "negative"), D("Matrimony", "very_negative"),
                        D("starters", "positive")],
                notes=[N("comparison", "prefers Tatiana to it", "negative")]),
              M("Tatiana", "stated", "negative", notes=[N("comparison", "preferred to Kabawa, but not rated highly")])],
    # "... bCD tofu house is fun ... Prefer Saperavi over Chama Mama ..."
    "v0476": [M("bCD tofu house", "stated", "positive"),
              M("Saperavi", "stated", "positive", notes=[N("comparison", "preferred to Chama Mama", "positive")]),
              M("Chama Mama", "stated", "negative", notes=[N("comparison", "Saperavi preferred", "negative")])],
}

# Thread comments scored in comment mode by their v1 gold line: line and timing tips are wait negative.
CASES_BY_COMMENT = {
    # "Went a few sundays ago, the line started around 4:15 I think" (Red Hook Tavern, from the title)
    "t1_obkhwb2": [M("Red Hook Tavern", "stated", named_in="context", wait="negative",
                     notes=[N("best time to go", "the line started around 4:15 on a Sunday", "negative")])],
    # "Be there at 11:30"
    "t1_obpxgdx": [M("Red Hook Tavern", "stated", named_in="context", wait="negative",
                     notes=[N("best time to go", "be there at 11:30", "negative")])],
}

# Cases where a sign disagreement with the gold is expected under the new conventions
# (eval/CONVENTIONS.md). Empty: Tatiana's "I don't rate Tatiana too highly" reads as a
# knock, and the v2 gold already accepts food -1 there.
EXPECT_SIGN_DISAGREE = set()

# Thread mode, rendered by v6_thread.render_chunk from the read-only sidecar.
# Keys: (items file, item id, chunk index); values: {new bracket number:
# (expected comment id, v6 mentions)}. t003/0 holds the misordered replies
# (production drew "I LOVE their pickled mango" under Jacob's; it answers the
# Pickle Guys comment). t001/0 [25] answers a 14-character parent ("Tell me
# more...") that production never renders.
THREAD_CASES = {
    ("items.jsonl", "t003", 0): {
        3: ("t1_ornphy1", [M("pickle guys", "stated", "neutral", taste="neutral", atmosphere="positive",
                             dishes=[D("fruit", "positive")])]),
        4: ("t1_oro17m1", [M("The Pickle Guys", "stated", "positive", taste="positive",
                             dishes=[D("pickled pineapple", "positive")])]),
        5: ("t1_orom5pn", [M("pickle guys", "stated", "positive", named_in="context", taste="positive",
                             dishes=[D("pickled mango", "very_positive")])]),
        6: ("t1_ornssi9", [M("Jacob’s", "stated", "negative", taste="negative",
                             dishes=[D("pickles", "negative")],
                             notes=[N("menu", "everything on the menu is over the top", "negative")])]),
    },
    ("items.jsonl", "t001", 0): {
        25: ("t1_owlz2bg", [M("Pressed", "stated", "negative", named_in="context", value="negative",
                              notes=[N("price", "overpriced produce in liquid form", "negative")])]),
    },
}

# An invented chunk in production order: [b] and [c] both answer [a], and [d]
# answers [b] but was posted after [c], so production draws it under [c].
# [e] answers a comment in another chunk, [f] a deleted one, [g] one missing
# from the database.
SYNTH_ROWS = [
    {"comment_id": "a", "parent_comment_id": None, "author": "ann", "body": "Golden Lotus is the move"},
    {"comment_id": "b", "parent_comment_id": "a", "author": "bob", "body": "their noodles are mid"},
    {"comment_id": "c", "parent_comment_id": "a", "author": "cal", "body": "second this"},
    {"comment_id": "d", "parent_comment_id": "b", "author": "dee", "body": "hard disagree"},
    {"comment_id": "e", "parent_comment_id": "x", "author": "eve", "body": "overrated"},
    {"comment_id": "f", "parent_comment_id": "y", "author": "fay", "body": "so good"},
    {"comment_id": "g", "parent_comment_id": "z", "author": "gus", "body": "agreed"},
]
SYNTH_OUTSIDE = {"x": {"author": "zed", "body": "Pepper  House"}, "y": {"author": "yul", "body": "[deleted]"}}
SYNTH_EXPECTED = """POST: Best noodles in Queens?

[1] u/ann: Golden Lotus is the move
  [2] u/bob (reply to [1]): their noodles are mid
    [3] u/dee (reply to [2]): hard disagree
  [4] u/cal (reply to [1]): second this
[5] u/eve (reply to u/zed, not in this chunk: "Pepper House"): overrated
[6] u/fay (reply to a deleted comment): so good
[7] u/gus (reply to a comment not shown): agreed"""

# What the design expects when the cases are scored against the gold: every
# required mention matched with no false positive, every gold negative,
# value complaint and dish negative caught, and no sign error. Deliberate
# disagreements with the gold are listed here, not hidden:
EXPECT_MISSES = {
    # v6 never turns a bare dollar figure into a price level, and does not
    # read "overpriced" as one; the gold does both.
    "expensiveness": {"c0049", "c0084", "v0065"},
    # Owner's rule: a portion complaint that doesn't mention price is a note,
    # not value. The v1 gold reads "80% normal bagel size" as a value complaint.
    "value_complaint": {"c0155"},
}


def main():
    errs = []
    common, pc, pt = load("v6_common"), load("v6_comment"), load("v6_thread")

    # 1. schema
    for name, sch in (("comment", common.SCHEMA_COMMENT), ("thread", common.SCHEMA_THREAD)):
        errs += [f"{name} schema: {e}" for e in lint_strict(sch)]
    assert pc.RESPONSE_FORMAT["json_schema"]["strict"] is True
    assert pt.SCHEMA["$defs"]["mention"]["required"][0] == "id"
    assert "id" not in common.SCHEMA_COMMENT["$defs"]["mention"]["properties"], "comment schema was mutated"
    for mod in (pc, pt):
        for key in ("SYSTEM_PROMPT", "PROMPT_HASH", "RESPONSE_FORMAT", "ANTHROPIC_OUTPUT_FORMAT"):
            assert getattr(mod, key), key
        # every level label and kind the prompt teaches is one the schema accepts, and back
        for lab in common.LEVELS:
            assert lab in mod.SYSTEM_PROMPT, lab
        for word in re.findall(r"\b(superlative_praise|praise|mixed|knock|extreme_knock)\b", mod.SYSTEM_PROMPT):
            assert word in common.LEVELS
    lv = common.SCHEMA_COMMENT["$defs"]["level"]["enum"]
    assert set(lv) - {None} == set(common.LEVELS) == set(A.LEVEL_MAP), "labels, schema and adapter disagree"
    kinds = common.SCHEMA_COMMENT["$defs"]["mention"]["properties"]["kind"]["enum"]
    assert set(kinds) == set(common.KINDS_COUNTED) | set(common.KINDS_EXCLUDED)
    assert set(common.KINDS_EXCLUDED) == set(A.EXCLUDED_KINDS)
    # strict structured outputs allow at most 16 parameters with a type union (anyOf)
    import anthropic_backend as AB
    defs = common.SCHEMA_THREAD["$defs"]
    unions = json.dumps(AB.strict_schema(common.SCHEMA_THREAD)).count('"anyOf"')
    refs = sum(json.dumps(defs[d]).count('"#/$defs/level"') for d in defs if d != "level")
    n_union = unions - 1 + refs                    # the level def is one anyOf, used at each $ref
    if n_union > 16:
        errs.append(f"{n_union} union-typed parameters; strict mode allows 16")
    print(f"round-4 schema: {n_union} union-typed parameters (limit 16)")
    # the frozen rounds keep their hashes and the schema of rounds 1 to 3
    for name, want in (("v6r1_comment", "a15cfb978cce"), ("v6r1_thread", "44e1a49c7781"),
                       ("v6r2_comment", "1cb01c0721f4"), ("v6r2_thread", "54d4ad44db68"),
                       ("v6r3_comment", "6b046d8ed65d"), ("v6r3_thread", "1b87239a557f")):
        mod = load(name)
        if mod.PROMPT_HASH != want:
            errs.append(f"{name} hash {mod.PROMPT_HASH}, frozen at {want}")
        if mod.SCHEMA["$defs"]["level"]["enum"][0] != "very_positive":
            errs.append(f"{name} lost the round 1-3 schema")
    assert load("v6r3_comment").PROMPT_HASH_POST == "1b0a9d4098e3"
    assert not hasattr(load("v6r3_comment"), "build_user_message"), "round 3 must keep production's rendering"

    # 2. no eval comment in a prompt: neither a whole body nor any 7-word run of one
    prompts = " ".join(" ".join(m.SYSTEM_PROMPT.lower().split()) for m in (pc, pt))
    shingles = {" ".join(w[i:i + 7]) for w in [prompts.split()] for i in range(len(w) - 6)}
    leaks = 0
    for path in ("items.jsonl", "v2/items.jsonl", "v2/topup_items.jsonl", "v4/items.jsonl",
                 "hard/items.jsonl", "fresh/items.jsonl"):
        for line in open(os.path.join(HERE, path), encoding="utf-8"):
            for body in re.findall(r'"body": "((?:[^"\\]|\\.){25,}?)"', line):
                w = " ".join(json.loads(f'"{body}"').lower().split()).split()
                if any(" ".join(w[i:i + 7]) in shingles for i in range(len(w) - 6)):
                    leaks += 1
    if leaks:
        errs.append(f"{leaks} eval comment(s) share a 7-word run with a prompt")

    # 3. hand-written outputs vs the v1 and v2 gold (comment mode), and the
    #    rendered thread chunks vs the v1 gold (thread mode)
    alias, excluded = S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json")
    lines_v1 = S.load_jsonl(os.path.join(HERE, "gold.jsonl"))
    gold_v1 = {g["item_id"]: g for g in lines_v1 if not g["item_id"].startswith("t")}
    gold_v2 = {g["item_id"]: g for g in S.load_jsonl(os.path.join(HERE, "v2", "gold.jsonl"))}
    by_cid = {g["comment_id"]: g for g in lines_v1}    # thread lines share their item id
    scored = []                                   # (label, gold line, v6 mentions, mode, schema)
    for gold, cases in ((gold_v1, CASES), (gold_v2, CASES_V2)):
        for iid, ms in cases.items():
            scored.append((iid, gold[iid], ms, "comment", common.SCHEMA_COMMENT))
    for cid, ms in CASES_BY_COMMENT.items():
        scored.append((cid, by_cid[cid], ms, "comment", common.SCHEMA_COMMENT))
    for (path, iid, ci), outs in THREAD_CASES.items():
        it = next(json.loads(l) for l in open(os.path.join(HERE, path), encoding="utf-8")
                  if json.loads(l)["item_id"] == iid)
        side = os.path.join(HERE, os.path.splitext(path)[0] + ".thread_rows.jsonl")
        rec = next(r for r in map(json.loads, open(side, encoding="utf-8"))
                   if r["call_key"] == f"thread:{it['thread_id']}:{ci}")
        _, id_map = pt.render_chunk(rec["title"], rec["selftext"], rec["rows"], rec["outside"])
        for n, (cid, ms) in outs.items():
            if id_map.get(n) != cid:
                errs.append(f"{iid}/{ci} [{n}] renders as {id_map.get(n)}, expected {cid}")
            ms = [dict(m, id=n) for m in ms]
            scored.append((f"{iid}/{ci}[{n}]", by_cid[cid], ms, "thread", common.SCHEMA_THREAD))

    total, rows = S.Acc(), []
    misses = {"expensiveness": set(), "value_complaint": set()}
    for label, g, ms, mode, schema in scored:
        ms = R4(ms)
        errs += [f"{label}: {e}" for e in validate({"mentions": ms}, schema, schema)]
        a = S.score_comment(g, A.adapt_all(ms), mode, alias, excluded, False)
        total.add(a)
        c = a.c
        if c["pres_fn_expensiveness"]:
            misses["expensiveness"].add(label)
        if c["vc_hit"] != c["vc_n"]:
            misses["value_complaint"].add(label)
        for what, ok in (("matching", not c["fn"] and not c["fp"]),
                         ("negative", c["neg_mention_hit"] == c["neg_mention_n"]),
                         ("dish negative", c["dishneg_hit"] == c["dishneg_n"]),
                         ("sign", c["sign_ok"] == c["sign_n"] or label in EXPECT_SIGN_DISAGREE)):
            if not ok:
                errs.append(f"{label}: {what} disagrees with the gold")
        rows.append(f"  {label:16s} tp {c['tp']} fn {c['fn']} fp {c['fp']}  neg {c['neg_mention_hit']}/{c['neg_mention_n']}"
                    f"  vc {c['vc_hit']}/{c['vc_n']}  dishneg {c['dishneg_hit']}/{c['dishneg_n']}"
                    f"  sign {c['sign_ok']}/{c['sign_n']}  negated {c['neg_ok']}/{c['neg_n']}"
                    f"  firsthand {c['first_ok']}/{c['first_n']}")
    o = S.summarize(total, True)
    print("per comment (v6 output -> adapter -> score.score_comment vs gold):")
    print("\n".join(rows))
    print(json.dumps({k: o[k] for k in ("drop_rate", "mention_recall", "mention_precision",
                                        "negative_mention_recall", "value_complaint_recall",
                                        "dish_negative_recall", "sign_accuracy", "is_negated_acc",
                                        "is_firsthand_acc", "food_exact_acc", "food_within1_acc",
                                        "expensiveness_presence_f1", "level_histogram")}, indent=1))
    for k, want in EXPECT_MISSES.items():
        if misses[k] != want:
            errs.append(f"{k} misses {sorted(misses[k])}, expected exactly {sorted(want)}")

    # 4. thread rendering, offline
    text, id_map = pt.render_chunk("Best noodles in Queens?", "", SYNTH_ROWS, SYNTH_OUTSIDE)
    if text != SYNTH_EXPECTED:
        errs.append("synthetic chunk renders differently:\n" + text)
    if id_map != {1: "a", 2: "b", 3: "d", 4: "c", 5: "e", 6: "f", 7: "g"}:
        errs.append(f"synthetic id map {id_map}")
    # Every chunk in every sidecar: same membership as production, every reply's
    # marker names its real parent, and a parent always comes before its replies.
    n_chunks = n_markers = 0
    for side in ("items", "v2/items", "v4/items_single", "v4/items_thread"):
        for rec in map(json.loads, open(os.path.join(HERE, side + ".thread_rows.jsonl"), encoding="utf-8")):
            text, id_map = pt.render_chunk(rec["title"], rec["selftext"], rec["rows"], rec["outside"])
            n_chunks += 1
            if sorted(id_map.values()) != sorted(rec["short_ids"].values()):
                errs.append(f"{side} {rec['call_key']}: chunk membership changed")
            num = {cid: n for n, cid in id_map.items()}
            for r in rec["rows"]:
                line = next(l for l in text.splitlines() if l.lstrip().startswith(f"[{num[r['comment_id']]}] "))
                m = re.match(r"\s*\[\d+\] u/\S* \(reply to \[(\d+)\]\)", line)
                p = r["parent_comment_id"]
                if p in num:
                    n_markers += 1
                    if not m or id_map[int(m.group(1))] != p or num[p] >= num[r["comment_id"]]:
                        errs.append(f"{side} {rec['call_key']}: reply {r['comment_id']} not marked under its parent")
                elif m:
                    errs.append(f"{side} {rec['call_key']}: {r['comment_id']} marked with an in-chunk parent it lacks")
    print(f"rendering: {n_chunks} real chunks, {n_markers} in-chunk reply markers all point at the true parent")

    # 5. v4 label path and passthrough
    for iid, ms in CASES.items():
        for m in A.adapt_all(ms):
            errs += [f"{iid} labels.problems: {p}" for p in L.problems(m, "comment", {})]
    t = dict(CASES["c0064"][0], id=7)
    lt = A.adapt(t)
    assert lt["id"] == 7 and not L.problems(lt, "thread", {"7": "t1_x"}), L.problems(lt, "thread", {"7": "t1_x"})
    assert L.problems(A.adapt(dict(t, id=8)), "thread", {"7": "t1_x"}), "a bad thread id must fail"
    g = L.as_gold_mention(lt, alias, excluded)
    assert g["aspects"] == {"food": -2, "value": -2, "service": -2, "atmosphere": None, "wait": None}, g["aspects"]
    assert g["is_negated"] and g["value_complaint"] and g["is_firsthand"] is True
    g = L.as_gold_mention(A.adapt(CASES["c0205"][0]), alias, excluded)
    assert g["dish_sentiment"] == [{"dish": "burrito", "level": -2, "avoid": False}], g["dish_sentiment"]
    assert g["expensiveness"] == 3 and g["aspects"]["value"] == -3
    g = L.as_gold_mention(A.adapt(CASES["c0009"][0]), alias, excluded)
    assert g["closed"] and all(v is None for v in g["aspects"].values())
    endorse = A.adapt(CASES["c0005"][0])
    assert endorse["aspects"]["food"] == 0.33 and S.bucket(endorse["aspects"]["food"]) == 1
    legacy = {"restaurant_raw": "X", "aspects": {"food": 0.3}, "is_negated": False}
    assert A.adapt(legacy) is legacy

    # 6. scorer fixes: on by default, fixes=False reproduces the old scorer
    over = A.adapt(M("Lucali", "stated", "negative", taste="positive"))
    assert S.model_negative(over) and not S.model_negative(over, fixes=False), "overall-negative fix"
    g = {"canonical_key": "2nd ave deli", "accept_keys": [], "ambiguous": False}
    mm = [dict(A.adapt(M("2nd avenue deli", "stated", "negative")), _key="2nd avenue deli")]
    assert S.match([g], mm)[0] and not S.match([g], mm, fixes=False)[0], "street-word fix"
    ref = dict(A.adapt(M("Pepper House", "none", named_in="context", experience="none")), id=2)
    line = {"mentions": [], "comment_id": "x"}
    landmark = A.adapt(M("Doughnut Plant", "none", experience="none"))      # named in the comment, no opinion
    for mode in ("thread", "comment"):
        for fixes, fp in ((False, 2), (True, 0)):
            a = S.score_comment(line, [ref, landmark], mode, alias, excluded, False, fixes)
            assert a.c["fp"] == fp, ("reference-mention fix", mode, fixes, a.c["fp"])
            assert a.c["ref_unmatched"] == (2 if fixes else 0)

    # 7. five-level metrics: gold +2 food against very_positive is a miss, +1 against an
    #    endorsement agrees, and a lone +1 food leaves the opinion type undecided
    gl = {"comment_id": "y", "mentions": [{"restaurant_raw": "X", "canonical_key": "x", "accept_keys": [],
          "ambiguous": False, "out_of_scope": False, "aspects": {"food": 2, "value": None, "service": None,
          "atmosphere": None, "wait": None}, "aspect_alternatives": {}, "expensiveness": None,
          "value_complaint": False, "dish_sentiment": [], "search_terms": [], "closed": False,
          "is_negated": False, "is_firsthand": True, "uncertain_fields": []}]}
    a = S.score_comment(gl, A.adapt_all([M("X", "stated", "very_positive", taste="very_positive")]),
                        "comment", alias, excluded, False)
    assert a.c["l5_n_food"] == 1 and a.c["l5_ok_food"] == 0 and a.c["ov_ok5"] == 0 and a.c["ov_sign"] == 1
    assert a.food_conf[("positive", "very_positive")] == 1 and a.c["op_stated_ok"] == 1
    gl["mentions"][0]["aspects"]["food"] = 1
    a = S.score_comment(gl, A.adapt_all([M("X", "endorse", "positive")]), "comment", alias, excluded, False)
    assert a.c["l5_ok_food"] == 1 and a.c["ov_ok5"] == 1 and not a.c["op_stated_n"] and not a.c["op_none_n"]

    # 8. round 4: labels map back, excluded kinds drop out, and every comment renders
    out = A.adapt_all(R4([M("Golden Lotus", "stated", "very_negative", taste="negative",
                            dishes=[D("noodles", "very_positive")]),
                          M("Hilltop Market", "stated", "positive", kind="grocery")]))
    assert len(out) == 1 and out[0]["v6"]["overall"] == "very_negative", out
    assert out[0]["v6"]["aspects"]["taste"] == "negative" and out[0]["v6"]["dishes"][0]["level"] == "very_positive"
    assert out[0]["aspects"]["food"] == -0.67 and out[0]["dish_sentiment"][0]["level"] == 1.0
    synth = {"author": "me", "thread_author": "me", "title": "Best  noodles?", "selftext": "x" * 1300,
             "body": "> Golden Lotus is great\n> really\nhard disagree", "ancestors_total": 7,
             "ancestors": [{"author": "op", "body": "a", "state": "ok"}, {"author": None, "body": None,
                           "state": "deleted"}, {"author": "me", "body": "b " * 400, "state": "ok"},
                           {"author": "zed", "body": "c " * 300, "state": "ok"},
                           {"author": "yul", "body": "d", "state": "ok"},
                           {"author": "me", "body": "e " * 900, "state": "ok"}]}
    msg = pc.build_user_message(synth)
    want_bits = ['<post_title author="you">Best noodles?</post_title>', "(2 earlier comments not shown)",
                 "[2] you, earlier: " + ("b " * 150).strip() + " ...", "[1] (a deleted comment)",
                 "<quote>Golden Lotus is great really</quote>\nhard disagree", "[5] you, earlier: e e"]
    for bit in want_bits:
        if bit not in msg:
            errs.append(f"build_user_message: missing {bit!r}\n{msg}")
    if len(msg.split("<post_body")[1].split("</post_body>")[0]) > pc.POST_BODY_CHARS + 20:
        errs.append("post body not cut")
    if len(msg.split("[5] you, earlier: ")[1].split("\n")[0]) > pc.PARENT_CHARS + 4:
        errs.append("parent not cut")
    n_rendered = 0
    for side in ("items", "v2/items", "hard/items", "fresh/items"):
        for rec in map(json.loads, open(os.path.join(HERE, side + ".comment_rows.jsonl"), encoding="utf-8")):
            m = pc.build_user_message(rec)
            n_rendered += 1
            if not m.rstrip().endswith("</comment_to_extract>") or "<comment_to_extract>" not in m:
                errs.append(f"{side} {rec['call_key']}: bad rendering")
    print(f"comment rendering: {n_rendered} sidecar rows render")

    if errs:
        print("FAILED")
        for e in errs:
            print("  " + e)
        sys.exit(1)
    print("v6 self-test ok")


if __name__ == "__main__":
    main()
