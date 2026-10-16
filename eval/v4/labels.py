"""Check and convert Claude's v5 labels. No database, no model.

    python eval/v4/labels.py check  --pass same_input                 # the whole pass
    python eval/v4/labels.py check  --pass same_input --batch b007    # one labeler's file
    python eval/v4/labels.py export --pass full_context               # -> labels/<pass>.run.jsonl and .gold.jsonl
    python eval/v4/labels.py export --pass same_input --dir eval/v4/round2

LABEL FORMAT (the full brief is eval/v4/LABELING.md). One file per batch,
labels/<pass>/bNNN.jsonl, one line per packet:

    {"packet_id": "3f9a2c1b", "output": {"mentions": [ ... ]}}

Each mention is a v5 contract mention (eval/docs/schema_v5.md: the keys the
v5 prompt asks for, "id" first in thread packets) plus the label metadata
the scorer needs, so a label can be both a model-shaped output and gold:

  required   canonical_name   the place's usual full name, so other spellings match
             rationale        one short sentence on why the mention reads this way
  optional   accept_names     other names that should also match ([])
             entity_type      restaurant | chain | bar | cafe_bakery_dessert | food_hall |
                              food_truck | stall_vendor | grocery_market | other (restaurant)
             out_of_scope     not a food place a ranking should hold (false)
             ambiguous        a mention a model is neither rewarded nor penalised for (false)
             confidence       high | medium | low (high)
             named_in         where the name was typed: comment | parent | ancestor |
                              title | selftext (comment)
             aspect_alternatives  {aspect or "price": [other acceptable values, null allowed]} ({})
             judgment_question    a bare name scored with the request's own judgment (false)
             uncertain_fields     any of reference_only, is_negated, experience: not scored ([])
             value_complaint      the comment complains about value (value at meh or below)
             needs_context        full_context pass only: the mention cannot be read from
                                  the model's own input (false)

check and export validate every mention against contract v5 and its
conventions, and fail loudly: unknown or missing keys, values outside the
enums, a dish in two lists, a reference with an opinion, an avoid with a
positive or no aspect that is not a non-quality avoid, a closed place that is
not a reference, a judgment question on a reference, a thread id that is not
a bracket number, a comment-packet mention with an id, the same place twice
in one comment.

EXPORT also refuses, exiting nonzero and writing nothing, if any line is bad
JSON, names a packet outside its batch, labels a packet twice, or if any
packet is unlabeled (--allow-missing exports a partial pass). It writes:

  labels/<pass>.run.jsonl    run.py's record format holding the contract
                             mentions only (rep 0 = primary copy, rep 1 = the
                             self-consistency duplicates), so the labels can be
                             scored as if they were a model
  labels/<pass>.gold.jsonl   v5 gold (label_version 3, the format of
                             eval/v1/gold_v5.jsonl) from the primary copy,
                             checked with the v5 gold validator before it is
                             kept. Every comment in a labeled chunk gets a
                             line, with or without mentions.

canonical_key and accept_keys are extract.normalize_entity of canonical_name,
restaurant_raw and accept_names with alias_overrides applied, the keying a
model mention gets. A key in excluded_entities is out of scope. A non-quality
avoid (is_negated, every aspect null, no dish verdict) is tagged
c2_nonquality, as in the v1/v2 gold.
"""

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
sys.path.insert(0, os.path.join(EVAL, "gold_v5"))
import _paths  # noqa: E402,F401  (puts eval/lib on sys.path)
import score as S  # noqa: E402
import schema_v5 as V  # noqa: E402
import convert_gold_v5 as G  # noqa: E402  (the v5 gold validator, reused as is)

ASPECTS = V.ASPECTS
LEVELS = set(V.LEVELS)
PRICES = set(V.PRICES)
EXPERIENCES = set(V.EXPERIENCES)
NEGATIVE = {"meh", "bad", "awful"}
PASSES = ("same_input", "full_context")
CONTRACT = ["restaurant_raw", "neighborhood_hint", "reference_only", "aspects", "is_negated", "price",
            "experience", "dishes_liked", "dishes_disliked", "dishes_mentioned", "descriptors"]
LISTS = ("dishes_liked", "dishes_disliked", "dishes_mentioned", "descriptors")
REQUIRED_META = ("canonical_name", "rationale")
OPTIONAL_META = {
    "accept_names": [], "entity_type": "restaurant", "out_of_scope": False, "ambiguous": False,
    "confidence": "high", "named_in": "comment", "aspect_alternatives": {}, "judgment_question": False,
    "uncertain_fields": [], "value_complaint": None, "needs_context": False,
}
ENTITY_TYPES = {"restaurant", "chain", "bar", "cafe_bakery_dessert", "food_hall", "food_truck",
                "stall_vendor", "grocery_market", "other"}
CONFIDENCE = {"high", "medium", "low"}
NAMED_IN = {"comment", "parent", "ancestor", "title", "selftext"}
UNCERTAIN = {"reference_only", "is_negated", "experience"}


def _strs(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def problems(m, mode, short_ids, pass_name):
    """Every way one label mention breaks contract v5 or the label format."""
    if not isinstance(m, dict):
        return ["mention is not an object"]
    out = []
    allowed = set(CONTRACT) | set(REQUIRED_META) | set(OPTIONAL_META) | ({"id"} if mode == "thread" else set())
    extra = sorted(set(m) - allowed)
    if extra:
        out.append(f"unknown key(s) {extra}" + (" (a comment packet's mention has no id)" if "id" in extra else ""))
    missing = [k for k in CONTRACT + list(REQUIRED_META) + (["id"] if mode == "thread" else []) if k not in m]
    if missing:
        return out + [f"missing {missing}"]

    if mode == "thread" and (isinstance(m["id"], bool) or str(m["id"]) not in short_ids):
        out.append(f"id {m['id']!r} is not a bracket number in this packet")
    for k in ("restaurant_raw", "canonical_name"):
        if not isinstance(m[k], str) or not m[k].strip():
            out.append(f"{k} must be a non-empty string")
    if not isinstance(m["rationale"], str):
        out.append("rationale must be a string")
    if m["neighborhood_hint"] is not None and not isinstance(m["neighborhood_hint"], str):
        out.append("neighborhood_hint must be a string or null")
    for k in ("reference_only", "is_negated"):
        if not isinstance(m[k], bool):
            out.append(f"{k} must be true or false")
    a = m["aspects"]
    if not isinstance(a, dict) or set(a) != set(ASPECTS):
        return out + [f"aspects must have exactly {list(ASPECTS)}"]
    bad = {k: v for k, v in a.items() if v is not None and v not in LEVELS}
    if bad:
        out.append(f"aspect values outside the seven levels: {bad}")
    if m["price"] is not None and m["price"] not in PRICES:
        out.append(f"price {m['price']!r}")
    if m["experience"] not in EXPERIENCES:
        out.append(f"experience {m['experience']!r}")
    for k in LISTS:
        if not _strs(m[k]):
            return out + [f"{k} must be a list of strings"]
    dishes = [d.strip().lower() for k in LISTS[:3] for d in m[k]]
    if len(dishes) != len(set(dishes)):
        out.append("a dish is in more than one list")

    judged = [v for v in a.values() if v is not None]
    verdict = bool(m["dishes_liked"] or m["dishes_disliked"])
    if m["reference_only"] is True:
        if judged:
            out.append("reference_only with an aspect set")
        if m["is_negated"]:
            out.append("reference_only with is_negated")
        if verdict:
            out.append("reference_only with a liked or disliked dish")
    if m["is_negated"] is True and not any(v in NEGATIVE for v in judged) and (judged or verdict):
        out.append("an avoid needs a negative aspect (food bad when no reason is given), or, for a "
                   "reason unrelated to quality, every aspect null and no dish verdict")
    if verdict and a["food"] is None and m["reference_only"] is not True:
        out.append("c1: a liked or disliked dish sets food when no overall food verdict is given")
    if any(d.strip().lower() == "closed" for d in m["descriptors"]) and m["reference_only"] is not True:
        out.append("a closed place must be reference_only")

    get = lambda k: m.get(k, OPTIONAL_META[k])  # noqa: E731
    if not _strs(get("accept_names")):
        out.append("accept_names must be a list of strings")
    if get("entity_type") not in ENTITY_TYPES:
        out.append(f"entity_type {get('entity_type')!r} (one of {sorted(ENTITY_TYPES)})")
    if get("confidence") not in CONFIDENCE:
        out.append(f"confidence {get('confidence')!r}")
    if get("named_in") not in NAMED_IN:
        out.append(f"named_in {get('named_in')!r} (one of {sorted(NAMED_IN)})")
    for k in ("out_of_scope", "ambiguous", "judgment_question", "needs_context"):
        if not isinstance(get(k), bool):
            out.append(f"{k} must be true or false")
    if get("value_complaint") is not None and not isinstance(get("value_complaint"), bool):
        out.append("value_complaint must be true, false or absent")
    uf = get("uncertain_fields")
    if not _strs(uf) or set(uf) - UNCERTAIN:
        out.append(f"uncertain_fields may only list {sorted(UNCERTAIN)}")
    alts = get("aspect_alternatives")
    if not isinstance(alts, dict):
        out.append("aspect_alternatives must be an object")
    else:
        for k, vs in alts.items():
            ok = LEVELS if k in ASPECTS else PRICES if k == "price" else None
            if ok is None:
                out.append(f"aspect_alternatives key {k!r} (an aspect or price)")
            elif not isinstance(vs, list) or any(v is not None and v not in ok for v in vs):
                out.append(f"aspect_alternatives[{k}] must list allowed values or null: {vs!r}")
    if get("judgment_question") is True and (m["reference_only"] or not judged):
        out.append("judgment_question needs an opinion: reference_only false and the judged aspect set")
    if get("needs_context") is True and pass_name != "full_context":
        out.append("needs_context belongs to the full_context pass only")
    return out


class LabelError(SystemExit):
    """Raised by export when any label is invalid: nothing is written."""


def read_pass(d, pass_name, batch=None, alias=None):
    """(key, {packet_id: mentions}, errors, missing).

    errors are hard failures: bad JSON, a packet id not in its batch, a
    packet labeled twice, a missing mentions list, a mention that fails the
    format, or one place twice in one comment. A packet labeled twice is kept
    neither way. missing lists the packets with no label yet (only the given
    batch's, when batch is set)."""
    alias = S.load_map("alias_overrides.json") if alias is None else alias
    with open(os.path.join(d, "keys", pass_name + ".json"), encoding="utf-8") as f:
        key = json.load(f)
    batches = sorted({v["batch"] for v in key.values()})
    if batch is not None:
        if batch not in batches:
            raise SystemExit(f"no batch {batch!r} in {pass_name} (have {batches[0]}..{batches[-1]})")
        batches = [batch]
    got, errors, twice = {}, [], set()
    ldir = os.path.join(d, "labels", pass_name)
    for b in batches:
        path = os.path.join(ldir, b + ".jsonl")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            lines = list(f)
        for n, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"{b}:{n}: bad JSON ({e})")
                continue
            pid = rec.get("packet_id") if isinstance(rec, dict) else None
            if pid not in key or key[pid]["batch"] != b:
                errors.append(f"{b}:{n}: packet {pid!r} is not in this batch")
                continue
            if pid in got or pid in twice:
                errors.append(f"{b}:{n}: packet {pid} labeled more than once")
                got.pop(pid, None)
                twice.add(pid)
                continue
            out = rec.get("output")
            ms = out.get("mentions") if isinstance(out, dict) else None
            if not isinstance(ms, list) or set(out) != {"mentions"}:
                errors.append(f"{b}:{n}: output must be exactly {{\"mentions\": [...]}}")
                continue
            k = key[pid]
            bad = [f"{b}:{n} {pid} mention {i} {m.get('restaurant_raw') if isinstance(m, dict) else ''!r}: {p}"
                   for i, m in enumerate(ms) for p in problems(m, k["mode"], k.get("short_ids", {}), pass_name)]
            if not bad:
                seen = set()
                for m in ms:
                    where = (m.get("id"), S.model_key({"restaurant_raw": m["canonical_name"]}, alias))
                    if where in seen:
                        bad.append(f"{b}:{n} {pid}: {m['canonical_name']!r} labeled twice in one comment "
                                   "(the same place named twice in a comment is ONE mention)")
                    seen.add(where)
            errors += bad
            if not bad:
                got[pid] = ms
    missing = [pid for pid, v in key.items() if v["batch"] in batches and pid not in got and pid not in twice]
    return key, got, errors, missing


def contract(m):
    """The model-shaped part of a label: the v5 contract keys, in order."""
    return {k: m[k] for k in CONTRACT}


def keyed(name, alias):
    return S.model_key({"restaurant_raw": name or ""}, alias)


def as_gold_mention(m, alias, excluded, item_mode):
    """A label mention (or any contract mention) -> one v5 gold mention with
    exactly the keys convert_gold_v5 writes and validates."""
    get = lambda k: m.get(k, OPTIONAL_META[k])  # noqa: E731
    canon = (m.get("canonical_name") or m["restaurant_raw"]).strip()
    ck = keyed(canon, alias)
    accept = [ck]
    for name in [m["restaurant_raw"], *get("accept_names")]:
        k = keyed(name, alias)
        if k and k not in accept:
            accept.append(k)
    asp = dict(m["aspects"])
    alts = {}
    for k, vs in (get("aspect_alternatives") or {}).items():
        primary = m["price"] if k == "price" else asp.get(k)
        keep = []
        for v in vs:
            if v != primary and v not in keep:
                keep.append(v)
        if keep:
            alts[k] = keep
    vc = get("value_complaint")
    if vc is None:
        vc = (V.level(asp["value"]) or 0) < 0
    judged = any(v is not None for v in asp.values())
    conventions = {}
    if m["is_negated"] and not judged and not (m["dishes_liked"] or m["dishes_disliked"]):
        conventions["c2_nonquality"] = {"food": "bad"}
    resolvable = {"comment": True, "thread": True}
    if get("needs_context"):
        resolvable[item_mode] = False
    g = {
        "canonical_name": canon, "canonical_key": ck, "accept_keys": accept,
        "entity_type": get("entity_type"), "out_of_scope": bool(get("out_of_scope")) or ck in excluded,
        "ambiguous": bool(get("ambiguous")), "confidence": get("confidence"), "named_in": get("named_in"),
        "resolvable_comment_mode": resolvable["comment"], "resolvable_thread_mode": resolvable["thread"],
        "uncertain_fields": list(get("uncertain_fields")), "rationale": m.get("rationale", ""),
        "value_complaint": bool(vc), "search_terms": [],
        "closed": any(d.strip().lower() == "closed" for d in m["descriptors"]),
    }
    g.update(contract(m))
    g["aspects"] = asp
    g.update(aspect_alternatives=alts, judgment_question=bool(get("judgment_question")), conventions=conventions)
    return g


def gold_lines(items, by_comment, alias, excluded, source):
    """One v5 gold line per labeled comment. by_comment: {comment_id: [mentions]}
    for every comment a label covered (an empty list is a real 'nothing')."""
    out = []
    for it in items:
        cids = [it["comment_id"]] if it["kind"] == "comment" else [c["comment_id"] for c in it["comments"]]
        for cid in cids:
            if cid not in by_comment:
                continue
            ms, seen = [], set()
            for m in by_comment[cid]:
                if not isinstance(m, dict) or not (m.get("restaurant_raw") or "").strip():
                    continue
                g = as_gold_mention(m, alias, excluded, it["mode"])
                if not g["canonical_key"] or g["canonical_key"] in seen:
                    continue          # the same place twice in one comment is one mention
                seen.add(g["canonical_key"])
                ms.append(g)
            # Chains are dropped on both sides when scoring (production drops
            # them at write time), so they are never a required mention.
            out.append({"item_id": it["item_id"], "comment_id": cid, "thread_id": it["thread_id"],
                        "label_version": 3, "source": source, "note": "", "mentions": ms,
                        "has_mention": any(S.is_required(g) and g["canonical_key"] not in S.CHAINS
                                           for g in ms)})
    return out


def prompt_record(d, pass_name):
    path = os.path.join(d, "keys", pass_name + ".prompt.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def export(d, pass_name, allow_missing=False):
    """Write the run and gold files, or raise LabelError and write nothing."""
    alias, excluded = S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json")
    key, got, errors, missing = read_pass(d, pass_name, alias=alias)
    problems_found = list(errors)
    if missing and not allow_missing:
        problems_found.append(f"{len(missing)} packet(s) unlabeled, e.g. {missing[:5]} "
                              "(--allow-missing exports the rest)")
    if problems_found:
        raise LabelError("\n".join([f"{pass_name}: not exported, {len(problems_found)} problem(s):"]
                                   + ["  " + p for p in problems_found[:200]]))
    prompts = prompt_record(d, pass_name)
    items = {it["item_id"]: it for it in S.load_jsonl(os.path.join(d, "items.jsonl"))}
    records, primary = [], {}
    for pid in sorted(got):
        ms, k = got[pid], key[pid]
        it = items[k["item_id"]]
        by = collections.defaultdict(list)
        if it["kind"] == "comment":
            call = f"comment:{it['comment_id']}"
            by[it["comment_id"]] = list(ms)
        else:
            call = f"thread:{it['thread_id']}:{it['chunk_index']}"
            for c in it["comments"]:
                by[c["comment_id"]]
            for m in ms:
                by[k["short_ids"][str(m["id"])]].append(m)   # ids validated in read_pass
        records.append({"call_key": call, "rep": k["copy"], "item_ids": [it["item_id"]],
                        "packet_id": pid, "model": f"claude-labels/{pass_name}",
                        "prompt_hash": prompts.get(it["mode"], pass_name),
                        "mode": it["mode"], "json_ok": True, "error": None,
                        "mentions_by_comment": {c: [contract(m) for m in v] for c, v in by.items()}})
        if k["copy"] == 0:
            primary.update(by)
    gold = gold_lines(list(items.values()), primary, alias, excluded, pass_name)

    ldir = os.path.join(d, "labels")
    os.makedirs(ldir, exist_ok=True)
    run_path, gold_path = (os.path.join(ldir, pass_name + s) for s in (".run.jsonl", ".gold.jsonl"))
    tmp_run, tmp_gold = run_path + ".tmp", gold_path + ".tmp"
    try:
        with open(tmp_run, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with open(tmp_gold, "w", encoding="utf-8") as f:
            for g in gold:
                f.write(json.dumps(g, ensure_ascii=False) + "\n")
        try:
            G.validate(tmp_gold)         # the same validator the v1/v2 v5 gold passes
        except SystemExit as e:
            raise LabelError(f"{pass_name}: exported gold failed the v5 gold check, nothing written\n{e}")
        os.replace(tmp_run, run_path)
        os.replace(tmp_gold, gold_path)
    finally:
        for p in (tmp_run, tmp_gold):
            if os.path.exists(p):
                os.remove(p)
    print(f"{pass_name}: {len(records)} labeled packets -> {len(gold)} gold comments "
          f"({sum(g['has_mention'] for g in gold)} with a required mention)")


def complete(d, pass_name):
    """True when every packet of the pass has exactly one valid label."""
    if not os.path.exists(os.path.join(d, "keys", pass_name + ".json")):
        return False
    _, _, errors, missing = read_pass(d, pass_name)
    return not errors and not missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("check", "export"))
    ap.add_argument("--pass", dest="pass_name", choices=PASSES, required=True)
    ap.add_argument("--batch", help="check one batch only, e.g. b007 (what a labeler runs on its own file)")
    ap.add_argument("--dir", default=HERE)
    ap.add_argument("--allow-missing", action="store_true", help="export even if some packets are unlabeled")
    args = ap.parse_args()
    if args.cmd == "export":
        if args.batch:
            raise SystemExit("export takes a whole pass; --batch is for check")
        export(args.dir, args.pass_name, args.allow_missing)    # LabelError exits nonzero
        return
    _, got, errors, missing = read_pass(args.dir, args.pass_name, args.batch)
    scope = f"batch {args.batch}" if args.batch else f"pass {args.pass_name}"
    print(f"{scope}: {len(got)} packets validly labeled, {len(missing)} unlabeled, {len(errors)} error(s)")
    for e in errors[:200]:
        print("  " + e)
    if missing and args.batch:
        print("  unlabeled: " + ", ".join(missing))
    if errors or missing:
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
