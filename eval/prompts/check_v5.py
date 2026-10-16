"""Validate every worked example in the v5 prompts against schema contract v5.

    python eval/prompts/check_v5.py

Models copy examples more faithfully than they follow rules, so an example that
breaks a rule teaches the break. Production's thread prompt did exactly that
(a bare name at food 0.6 under a rule saying 0.3). This check fails loudly on
any key, enum or consistency violation, on a name or dish that is not typed in
the example's own input, and on any float left in the prompt text.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import run  # noqa: E402  (eval/run.py: the loader the benchmark itself uses)

PROMPTS = {"comment": os.path.join(HERE, "v5_comment.py"),
           "thread": os.path.join(HERE, "v5_thread.py")}

LEVELS = {"rave", "good", "decent", "mixed", "meh", "bad", "awful"}
NEGATIVE = {"meh", "bad", "awful"}
ASPECTS = {"food", "value", "service", "atmosphere", "wait"}
PRICES = {"cheap", "moderate", "pricey", "very_pricey"}
EXPERIENCES = {"ate_there", "secondhand", "unclear"}
KEYS = ["restaurant_raw", "neighborhood_hint", "reference_only", "aspects", "is_negated",
        "price", "experience", "dishes_liked", "dishes_disliked", "dishes_mentioned",
        "descriptors"]
SHARED = ["KINDS", "LEVEL_TABLE", "OTHER_FIELDS", "RULES"]


def examples(prompt):
    """(input_text, parsed_output) for every JSON example after the EXAMPLES header."""
    start = prompt.index("EXAMPLES (invented places)")
    dec = json.JSONDecoder()
    out, pos = [], start
    while True:
        i = prompt.find('{"mentions":', pos)
        if i < 0:
            return out
        seg = prompt[pos:i]
        m = re.search(r"^POST", seg, re.M)
        if not m:
            raise AssertionError(f"example at char {i} has no POST input above it")
        obj, end = dec.raw_decode(prompt, i)
        out.append((seg[m.start():], obj))
        pos = end


def check_mention(m, text, mode, where, errs):
    def err(msg):
        errs.append(f"{where} {m.get('restaurant_raw')!r}: {msg}")

    want = (["id"] if mode == "thread" else []) + KEYS
    if list(m) != want:
        err(f"keys {list(m)} != {want}")
        return
    if mode == "thread":
        ids = {int(x) for x in re.findall(r"^\s*\[(\d+)\]", text, re.M)}
        if not isinstance(m["id"], int) or m["id"] not in ids:
            err(f"id {m['id']!r} not among bracket ids {sorted(ids)}")
    if not isinstance(m["restaurant_raw"], str) or m["restaurant_raw"] not in text:
        err("restaurant_raw is not typed verbatim in the example input")
    hood = m["neighborhood_hint"]
    if hood is not None and (not isinstance(hood, str) or hood.lower() not in text.lower()):
        err(f"neighborhood_hint {hood!r} not in the input")
    for k in ("reference_only", "is_negated"):
        if not isinstance(m[k], bool):
            err(f"{k} must be a bool")
    asp = m["aspects"]
    if not isinstance(asp, dict) or set(asp) != ASPECTS:
        err(f"aspects keys {sorted(asp) if isinstance(asp, dict) else asp}")
        return
    bad = {k: v for k, v in asp.items() if v is not None and v not in LEVELS}
    if bad:
        err(f"aspect values outside the seven levels: {bad}")
    if m["price"] is not None and m["price"] not in PRICES:
        err(f"price {m['price']!r}")
    if m["experience"] not in EXPERIENCES:
        err(f"experience {m['experience']!r}")
    lists = ("dishes_liked", "dishes_disliked", "dishes_mentioned", "descriptors")
    for k in lists:
        if not isinstance(m[k], list) or not all(isinstance(x, str) for x in m[k]):
            err(f"{k} must be a list of strings")
            return
        for x in m[k]:
            if x.lower() not in text.lower():
                err(f"{k} entry {x!r} is not in the input")
    dishes = [d.lower() for k in lists[:3] for d in m[k]]
    if len(dishes) != len(set(dishes)):
        err("a dish appears in more than one list")

    judged = [v for v in asp.values() if v is not None]
    if m["reference_only"]:
        if judged:
            err("reference_only with aspects set")
        if m["is_negated"]:
            err("reference_only with is_negated")
        if m["dishes_liked"] or m["dishes_disliked"]:
            err("reference_only with liked or disliked dishes")
    if m["is_negated"] and not any(v in NEGATIVE for v in judged):
        err("is_negated with no negative aspect (an avoid with no reason is food bad)")
    if "closed" in [d.lower() for d in m["descriptors"]] and not m["reference_only"]:
        err("a closed place must be reference_only")


def check(mode, path, common):
    errs = []
    pmod, _ = run.load_prompt("file:" + path, mode)
    p = pmod.SYSTEM_PROMPT
    if pmod.PROMPT_HASH != run.prompt_hash(p):
        errs.append(f"{mode}: PROMPT_HASH does not match run.prompt_hash")
    if hasattr(pmod, "build_user_message") or hasattr(pmod, "build_message"):
        errs.append(f"{mode}: defines a builder; v5 must use the stored production renderings")
    floats = re.findall(r"(?<![\w$.])-?\d+\.\d+", p)
    if floats:
        errs.append(f"{mode}: floats left in the prompt: {floats}")
    for name in SHARED:
        if getattr(common, name) not in p:
            errs.append(f"{mode}: shared block {name} is not in the prompt verbatim")
    for w in LEVELS:
        if f'"{w}"' not in p:
            errs.append(f"{mode}: level {w!r} is never defined")

    exs = examples(p)
    used = {"levels": set(), "ref": 0, "neg": 0, "secondhand": 0, "price": 0,
            "liked": 0, "disliked": 0, "mentioned": 0, "empty": 0}
    for n, (text, obj) in enumerate(exs, 1):
        where = f"{mode} example {n}"
        if list(obj) != ["mentions"] or not isinstance(obj["mentions"], list):
            errs.append(f"{where}: top level must be exactly {{\"mentions\": [...]}}")
            continue
        if not obj["mentions"]:
            used["empty"] += 1
        seen = set()
        for m in obj["mentions"]:
            check_mention(m, text, mode, where, errs)
            key = (m.get("id"), str(m.get("restaurant_raw", "")).lower())
            if key in seen:
                errs.append(f"{where}: {key} emitted twice from one comment")
            seen.add(key)
            a = m.get("aspects") or {}
            used["levels"] |= {v for v in a.values() if v}
            used["ref"] += bool(m.get("reference_only"))
            used["neg"] += bool(m.get("is_negated"))
            used["secondhand"] += m.get("experience") == "secondhand"
            used["price"] += m.get("price") is not None
            for k in ("liked", "disliked", "mentioned"):
                used[k] += bool(m.get("dishes_" + k))
    return errs, len(exs), used, len(p)


def main():
    spec = run.importlib.util.spec_from_file_location("v5_common", os.path.join(HERE, "v5_common.py"))
    common = run.importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    all_errs = []
    for mode, path in PROMPTS.items():
        errs, n, used, chars = check(mode, path, common)
        all_errs += errs
        levels = ", ".join(sorted(used.pop("levels")))
        print(f"{mode}: {n} examples, {chars} chars; levels used: {levels}; "
              + ", ".join(f"{k} {v}" for k, v in used.items()))
    if all_errs:
        print(f"\nFAIL: {len(all_errs)} problem(s)")
        for e in all_errs:
            print("  " + e)
        sys.exit(1)
    print("OK: every example obeys contract v5")


if __name__ == "__main__":
    main()
