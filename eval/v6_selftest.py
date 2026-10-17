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
def M(name, opinion, overall=None, *, named_in="comment", experience="firsthand", taste=None,
      value=None, service=None, atmosphere=None, wait=None, avoid=False,
      dishes=(), price=None, timeframe="current", trend=None, status=None, tags=(), notes=(),
      location=None):
    return {"name": name, "named_in": named_in, "location": location, "experience": experience,
            "opinion": opinion, "overall": overall,
            "aspects": {"taste": taste, "value": value, "service": service,
                        "atmosphere": atmosphere, "wait": wait},
            "avoid": avoid, "dishes": list(dishes), "price": price,
            "timeframe": timeframe, "trend": trend, "status": status, "tags": list(tags),
            "notes": list(notes)}


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
}

# What the design expects when each case is scored against the v1 gold.
# Deliberate disagreements with the gold are listed, not hidden:
EXPECT = {
    "matched_all": True,          # every required gold mention found, no false positives
    "neg_hit_all": True,          # every gold negative carried a negative
    "vc_hit_all": True,           # every gold value complaint caught
    "dishneg_hit_all": True,      # every gold dish negative caught
    "sign_errors": 0,
    # v6 never turns a bare dollar figure into a price level, and does not
    # read "overpriced" as one; the gold does both.
    "expensiveness_presence_misses": {"c0049", "c0084"},
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
        ex = re.findall(r'\{"mentions":\[.*\]\}', mod.SYSTEM_PROMPT)
        for e in ex:
            errs += [f"prompt example: {x}" for x in validate(json.loads(e), common.SCHEMA_COMMENT,
                                                            common.SCHEMA_COMMENT)]
    line3 = next(l for l in pt.SYSTEM_PROMPT.splitlines() if l.startswith('{"id":3'))
    errs += [f"thread example: {x}" for x in validate({"mentions": [json.loads(line3)]},
                                                      common.SCHEMA_THREAD, common.SCHEMA_THREAD)]

    # 2. no eval comment in a prompt: neither a whole body nor any 7-word run of one
    prompts = " ".join(" ".join(m.SYSTEM_PROMPT.lower().split()) for m in (pc, pt))
    shingles = {" ".join(w[i:i + 7]) for w in [prompts.split()] for i in range(len(w) - 6)}
    leaks = 0
    for path in ("items.jsonl", "v2/items.jsonl", "v2/topup_items.jsonl", "v4/items.jsonl"):
        for line in open(os.path.join(HERE, path), encoding="utf-8"):
            for body in re.findall(r'"body": "((?:[^"\\]|\\.){25,}?)"', line):
                w = " ".join(json.loads(f'"{body}"').lower().split()).split()
                if any(" ".join(w[i:i + 7]) in shingles for i in range(len(w) - 6)):
                    leaks += 1
    if leaks:
        errs.append(f"{leaks} eval comment(s) share a 7-word run with a prompt")

    # 3. hand-written outputs vs v1 gold
    gold = {g["item_id"]: g for g in S.load_jsonl(os.path.join(HERE, "gold.jsonl"))}
    alias, excluded = S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json")
    total = S.Acc()
    exp_miss = set()
    rows = []
    for iid, ms in CASES.items():
        errs += [f"{iid}: {e}" for e in validate({"mentions": ms}, common.SCHEMA_COMMENT, common.SCHEMA_COMMENT)]
        a = S.score_comment(gold[iid], A.adapt_all(ms), "comment", alias, excluded, False)
        total.add(a)
        c = a.c
        if c["pres_fn_expensiveness"]:
            exp_miss.add(iid)
        rows.append(f"  {iid}: tp {c['tp']} fn {c['fn']} fp {c['fp']}  neg {c['neg_mention_hit']}/{c['neg_mention_n']}"
                    f"  vc {c['vc_hit']}/{c['vc_n']}  dishneg {c['dishneg_hit']}/{c['dishneg_n']}"
                    f"  sign {c['sign_ok']}/{c['sign_n']}  negated {c['neg_ok']}/{c['neg_n']}"
                    f"  firsthand {c['first_ok']}/{c['first_n']}")
    o = S.summarize(total, True)
    c = total.c
    print("per comment (v6 output -> adapter -> score.score_comment vs v1 gold):")
    print("\n".join(rows))
    print(json.dumps({k: o[k] for k in ("drop_rate", "mention_recall", "mention_precision",
                                        "negative_mention_recall", "value_complaint_recall",
                                        "dish_negative_recall", "sign_accuracy", "is_negated_acc",
                                        "is_firsthand_acc", "food_exact_acc", "food_within1_acc",
                                        "expensiveness_presence_f1", "level_histogram")}, indent=1))
    if EXPECT["matched_all"] and (c["fn"] or c["fp"]):
        errs.append(f"mention matching: fn {c['fn']} fp {c['fp']}")
    if EXPECT["neg_hit_all"] and c["neg_mention_hit"] != c["neg_mention_n"]:
        errs.append("a gold negative was missed")
    if EXPECT["vc_hit_all"] and c["vc_hit"] != c["vc_n"]:
        errs.append("a gold value complaint was missed")
    if EXPECT["dishneg_hit_all"] and c["dishneg_hit"] != c["dishneg_n"]:
        errs.append("a gold dish negative was missed")
    if c["sign_n"] - c["sign_ok"] != EXPECT["sign_errors"]:
        errs.append(f"sign errors: {c['sign_n'] - c['sign_ok']}")
    if exp_miss != EXPECT["expensiveness_presence_misses"]:
        errs.append(f"expensiveness presence misses {sorted(exp_miss)}")

    # 4. v4 label path and passthrough
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

    if errs:
        print("FAILED")
        for e in errs:
            print("  " + e)
        sys.exit(1)
    print("v6 self-test ok")


if __name__ == "__main__":
    main()
