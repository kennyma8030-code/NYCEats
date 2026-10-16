"""Validate every worked example in the v5 prompts against schema contract v5.

    python eval/prompts/check_v5.py

Models copy examples more faithfully than they follow rules, so an example that
breaks a rule teaches the break. Production's thread prompt did exactly that
(a bare name at food 0.6 under a rule saying 0.3). This check fails loudly on:
- any key, enum or consistency violation;
- a name, dish or descriptor not typed where the mention may draw it from
  (the comment's own input, or in thread mode that comment, its ancestors and
  the post);
- an example input not laid out exactly as production renders it;
- a level, the secondhand case, or the empty-output case that no example shows;
- any float left in the prompt text.
"""

import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
ROOT = os.path.dirname(EVAL)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


common = _load("v5_common", os.path.join(HERE, "v5_common.py"))
run = _load("eval_run", os.path.join(EVAL, "run.py"))  # the loader the benchmark itself uses
prod_comment = _load("prompt", os.path.join(ROOT, "prompt.py"))
prod_thread = _load("prompt_thread", os.path.join(ROOT, "prompt_thread.py"))

LEVELS, ASPECTS = common.LEVELS, common.ASPECTS
PRICES, EXPERIENCES = common.PRICES, common.EXPERIENCES
NEGATIVE = ("meh", "bad", "awful")
PROMPTS = {"comment": os.path.join(HERE, "v5_comment.py"),
           "thread": os.path.join(HERE, "v5_thread.py")}
KEYS = ["restaurant_raw", "neighborhood_hint", "reference_only", "aspects", "is_negated",
        "price", "experience", "dishes_liked", "dishes_disliked", "dishes_mentioned",
        "descriptors"]
LISTS = ("dishes_liked", "dishes_disliked", "dishes_mentioned", "descriptors")
SHARED = ["KINDS", "LEVEL_TABLE", "OTHER_FIELDS", "RULES"]
TREE_LINE = re.compile(r"^( *)\[(\d+)\] u/([^:]*): (.*)$")


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
        out.append((seg[m.start():].strip("\n"), obj))
        pos = end


# ---------------------------------------------------------------- input layout
def comment_layout_error(text):
    """None if text is exactly what production's build_user_message renders."""
    parts = {}
    for block in text.split("\n\n"):
        for label in ("POST TITLE", "POST BODY", "PARENT COMMENT", "COMMENT"):
            if block.startswith(label + ": "):
                parts[label] = block[len(label) + 2:]
                break
        else:
            return f"block {block[:40]!r} has no production label"
    want = prod_comment.build_user_message(parts.get("COMMENT"), parts.get("POST TITLE"),
                                           parts.get("POST BODY"), parts.get("PARENT COMMENT"))
    return None if want == text else "differs from prompt.build_user_message"


def parse_thread(text):
    """(post_text, {id: (depth, line)}, {id: parent id or None}, layout error or None)."""
    lines = text.split("\n")
    first = next((i for i, l in enumerate(lines) if TREE_LINE.match(l)), len(lines))
    post = "\n".join(lines[:first])
    nodes, parents, stack, rows = {}, {}, [], []
    for l in lines[first:]:
        m = TREE_LINE.match(l)
        if not m:
            return post, nodes, parents, f"line {l[:40]!r} is not a comment line"
        depth, sid = len(m.group(1)) // 2, int(m.group(2))
        while stack and stack[-1][0] >= depth:
            stack.pop()
        parents[sid] = stack[-1][1] if stack else None
        nodes[sid] = (depth, l)
        stack.append((depth, sid))
        rows.append((sid, depth, m.group(3), m.group(4)))
    title = lines[0][len("POST: "):] if lines and lines[0].startswith("POST: ") else None
    selftext = "\n".join(lines[1:first]).strip() or None
    want = prod_thread.build_message(title, selftext, rows)
    return post, nodes, parents, None if want == text else "differs from prompt_thread.build_message"


def thread_context(sid, post, nodes, parents):
    """What a mention under bracket sid may draw from: the post, sid, its ancestors."""
    seen, parts = set(), [post]
    while sid is not None and sid in nodes and sid not in seen:
        seen.add(sid)
        parts.append(nodes[sid][1])
        sid = parents.get(sid)
    return "\n".join(parts)


# ---------------------------------------------------------------- one mention
def check_mention(m, text, mode, where, errs, tree=None):
    if not isinstance(m, dict):
        errs.append(f"{where}: mention is not an object: {m!r}")
        return

    def err(msg):
        errs.append(f"{where} {m.get('restaurant_raw')!r}: {msg}")

    want = (["id"] if mode == "thread" else []) + KEYS
    if list(m) != want:
        err(f"keys {list(m)} != {want}")
        return
    if mode == "thread":
        post, nodes, parents = tree
        if not isinstance(m["id"], int) or isinstance(m["id"], bool) or m["id"] not in nodes:
            err(f"id {m['id']!r} not among bracket ids {sorted(nodes)}")
            return
        text = thread_context(m["id"], post, nodes, parents)
    if not isinstance(m["restaurant_raw"], str) or not m["restaurant_raw"]:
        err("restaurant_raw must be a non-empty string")
    elif m["restaurant_raw"] not in text:
        err("restaurant_raw is not typed verbatim where this mention may draw it from")
    hood = m["neighborhood_hint"]
    if hood is not None and (not isinstance(hood, str) or hood.lower() not in text.lower()):
        err(f"neighborhood_hint {hood!r} not in the input")
    for k in ("reference_only", "is_negated"):
        if not isinstance(m[k], bool):
            err(f"{k} must be a bool")
    asp = m["aspects"]
    if not isinstance(asp, dict) or sorted(asp) != sorted(ASPECTS):
        err(f"aspects must be an object with keys {ASPECTS}")
        return
    bad = {k: v for k, v in asp.items() if v is not None and v not in LEVELS}
    if bad:
        err(f"aspect values outside the seven levels: {bad}")
    if m["price"] is not None and m["price"] not in PRICES:
        err(f"price {m['price']!r}")
    if m["experience"] not in EXPERIENCES:
        err(f"experience {m['experience']!r}")
    for k in LISTS:
        if not isinstance(m[k], list) or not all(isinstance(x, str) for x in m[k]):
            err(f"{k} must be a list of strings")
            return
        for x in m[k]:
            if x.lower() not in text.lower():
                err(f"{k} entry {x!r} is not where this mention may draw it from")
    dishes = [d.lower() for k in LISTS[:3] for d in m[k]]
    if len(dishes) != len(set(dishes)):
        err("a dish appears in more than one list")

    judged = [v for v in asp.values() if v is not None]
    if m["reference_only"] is True:
        if judged:
            err("reference_only with aspects set")
        if m["is_negated"]:
            err("reference_only with is_negated")
        if m["dishes_liked"] or m["dishes_disliked"]:
            err("reference_only with liked or disliked dishes")
    if m["is_negated"] is True and not any(v in NEGATIVE for v in judged):
        err("is_negated with no negative aspect (an avoid with no reason is food bad)")
    if "closed" in [d.lower() for d in m["descriptors"]] and m["reference_only"] is not True:
        err("a closed place must be reference_only")


# ---------------------------------------------------------------- one prompt
def check(mode, path):
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

    used = {"levels": set(), "ref": 0, "neg": 0, "secondhand": 0, "price": 0,
            "liked": 0, "disliked": 0, "mentioned": 0, "empty": 0}
    exs = examples(p)
    for n, (text, obj) in enumerate(exs, 1):
        where = f"{mode} example {n}"
        tree = None
        if mode == "comment":
            layout = comment_layout_error(text)
        else:
            post, nodes, parents, layout = parse_thread(text)
            tree = (post, nodes, parents)
        if layout:
            errs.append(f"{where}: input {layout}")
        if not isinstance(obj, dict) or list(obj) != ["mentions"] or not isinstance(obj["mentions"], list):
            errs.append(f"{where}: top level must be exactly {{\"mentions\": [...]}}")
            continue
        if not obj["mentions"]:
            used["empty"] += 1
        seen = set()
        for m in obj["mentions"]:
            try:
                check_mention(m, text, mode, where, errs, tree)
            except Exception as e:  # a malformed example is a finding, never a crash
                errs.append(f"{where}: malformed mention {m!r}: {type(e).__name__}: {e}")
            if not isinstance(m, dict):
                continue
            key = (m.get("id"), str(m.get("restaurant_raw", "")).lower())
            if key in seen:
                errs.append(f"{where}: {key} emitted twice from one comment")
            seen.add(key)
            a = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
            used["levels"] |= {v for v in a.values() if isinstance(v, str)}
            used["ref"] += m.get("reference_only") is True
            used["neg"] += m.get("is_negated") is True
            used["secondhand"] += m.get("experience") == "secondhand"
            used["price"] += m.get("price") is not None
            for k in ("liked", "disliked", "mentioned"):
                used[k] += bool(m.get("dishes_" + k))

    missing = [w for w in LEVELS if w not in used["levels"]]
    if missing:
        errs.append(f"{mode}: no example uses level(s) {missing}")
    if not used["empty"]:
        errs.append(f"{mode}: no example shows the empty output")
    if mode == "thread" and not used["secondhand"]:
        errs.append("thread: no example shows a secondhand mention")
    return errs, len(exs), used, len(p)


def main():
    all_errs = []
    for mode, path in PROMPTS.items():
        errs, n, used, chars = check(mode, path)
        all_errs += errs
        lv = used.pop("levels")
        levels = ", ".join(w for w in LEVELS if w in lv)
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
