"""Check and convert Claude's labels. No database, no model.

    python eval/v4/labels.py init   --pass same_input --commit <rev>   # before labeling a v6 pass
    python eval/v4/labels.py check  --pass same_input        # every packet labeled, schema valid
    python eval/v4/labels.py check  --pass same_input --batch b007   # one labeler's file
    python eval/v4/labels.py export --pass full_context      # -> labels/<pass>.run.jsonl and .gold.jsonl
    python eval/v4/labels.py export --pass same_input --dir eval/v4/round2

LABEL FORMAT. One file per batch, labels/<pass>/bNNN.jsonl, one line per packet:

    {"packet_id": "3f9a2c1b", "output": {"mentions": [ ... ]}}

"output" is exactly what production's extraction prompt returns
(prompt.py / prompt_thread.py), so labels, production's stored rows and any
model's output are scored by the same code:

    restaurant_raw     string, the name as typed
    neighborhood_hint  string or null
    dishes             [string]
    descriptors        [string]   ("closed" marks a closed place)
    aspects            {food, value, service, atmosphere, wait}: number in -1..1 or null
    expensiveness      number in -1..1 or null
    is_firsthand       boolean
    is_negated         boolean
    id                 thread packets only: the bracket number of the comment

Optional fields, used by score.py when present: value_complaint (boolean),
dish_sentiment ([{dish, level -1..1 or null, avoid}]), ambiguous (boolean,
mention neither required nor penalised), out_of_scope (boolean). Any other
extra key is allowed and ignored. If the user's labeling prompt returns a
different schema, write a mapping into this shape before export. Output in
the v6 schema (eval/prompts/v6_schema.json) is mapped automatically by
eval/v6_adapter.py.

EXPORT refuses, exiting nonzero and writing nothing, if any line is bad JSON,
names a packet outside its batch, labels a packet twice, or has a mention
that fails the schema (a thread id that is not a bracket number included),
or if any packet is unlabeled (--allow-missing exports a partial pass).
Nothing is ever silently dropped or overwritten.

V6 LABELS. `labels.py init --pass P` (run once batches.py has written the
key) records in labels/manifest.json what the pass is labeled against:

    {"same_input": {"schema": "v6",
                    "prompts": {"comment": {"file": "eval/prompts/v6_comment.py",
                                            "prompt_hash": "a15cfb978cce", "sha256": "...",
                                            "commit": "d61c91a"}, "thread": {...}},
                    "inputs": {"thread_renderer": {...}, "comment_builder": {...}, "schema": {...}},
                    "key": {"renderer": "v6", "short_ids_sha256": "..."},
                    "reruns": [...]}, "full_context": {...}}

For a pass whose schema is "v6", every packet's whole output must validate
strictly against v6_schema.json (comment packets) or its thread form with
"id" (thread packets): a missing or extra key, or an unknown level, is an
error like any other, so export refuses. So is a key that is not the one
recorded (another renderer, or other bracket numbers): the labels' ids would
land on the wrong comments. The mentions are then mapped with
eval/v6_adapter.py, as for a v6 model run, and the untranslated v6 mention
is kept under "v6" in both the run and the gold file. A prompt, input
builder or schema that has changed since labeling is reported, not refused:
the labels stay the reference for the version they were made with.

Otherwise it writes two files per pass:

  labels/<pass>.run.jsonl    run.py's record format (rep 0 = primary copy,
                             rep 1 = the self-consistency duplicates), so the
                             labels can be scored as if they were a model
  labels/<pass>.gold.jsonl   score.py's gold format built from the primary
                             copy, so the labels can be the reference. Every
                             comment in a labeled chunk gets a line, with or
                             without mentions.

Converting a label into gold: canonical_key is extract.normalize_entity of
restaurant_raw with alias_overrides applied (the same keying score.py gives a
model), aspects and expensiveness become 7-point levels with score.bucket
(0.3 -> +1, 0.6 -> +2, 1 -> +3), value_complaint defaults to "value < 0",
closed comes from a "closed" descriptor, and a key in excluded_entities is
out of scope. There are no accept_keys or aspect alternatives: matching
leans on score.py's fuzzy key rule (extra trailing words, a possessive s).
"""

import argparse
import collections
import hashlib
import inspect
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
import score as S  # noqa: E402
import prompt_modules as PM  # noqa: E402

ASPECTS = ("food", "value", "service", "atmosphere", "wait")
REQUIRED = ("restaurant_raw", "neighborhood_hint", "dishes", "descriptors", "aspects",
            "expensiveness", "is_firsthand", "is_negated")
PASSES = ("same_input", "full_context")
MANIFEST = "manifest.json"


def sha256(text):
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def manifest(d):
    """labels/manifest.json, or {} for a round labeled before v6."""
    path = os.path.join(d, "labels", MANIFEST)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def v6_schemas():
    c = PM.load("v6_common")
    return {"comment": c.SCHEMA_COMMENT, "thread": c.SCHEMA_THREAD}


# ---------------------------------------------------------------- fingerprints
# What a v6 label depends on, besides the packet text: the two system
# prompts, the code that draws a candidate's input (v6's thread renderer, and
# a comment-mode message builder if v6_comment ever defines one; today it
# sends production's stored message), and the output schema. labels.py init
# records them when a pass is labeled; check and export warn when any has
# changed since, because the labels then answer an older prompt.

def prompt_fingerprints():
    out = {}
    for mode in ("comment", "thread"):
        mod = PM.load("v6_" + mode)
        out[mode] = {"file": f"eval/prompts/v6_{mode}.py", "prompt_hash": mod.PROMPT_HASH,
                     "sha256": sha256(mod.SYSTEM_PROMPT)}
    return out


def input_fingerprints():
    pt, pc = PM.load("v6_thread"), PM.load("v6_comment")
    renderer = "\n".join(inspect.getsource(f) for f in (pt.render_chunk, pt.depth_first, pt._flat, pt._cut))
    renderer += json.dumps({k: getattr(pt, k) for k in ("SELFTEXT_LIMIT", "MAX_COMMENT_CHARS",
                                                        "STUB_CHARS", "MAX_INDENT")}, sort_keys=True)
    builder = (inspect.getsource(pc.build_user_message) if hasattr(pc, "build_user_message")
               else "none: production's stored comment-mode message")
    with open(os.path.join(PM.PROMPTS, "v6_schema.json"), "rb") as f:
        schema = f.read()
    return {"thread_renderer": {"file": "eval/prompts/v6_thread.py",
                                "what": "render_chunk, depth_first, _flat, _cut and the cut limits",
                                "sha256": sha256(renderer)},
            "comment_builder": {"file": "eval/prompts/v6_comment.py", "what": "build_user_message",
                                "defined": hasattr(pc, "build_user_message"), "sha256": sha256(builder)},
            "schema": {"file": "eval/prompts/v6_schema.json", "sha256": sha256(schema)}}


def key_fingerprint(key):
    """sha256 of every thread packet's bracket-number map, the part of a key
    that turns a label's id into a comment id."""
    return sha256(json.dumps({pid: v["short_ids"] for pid, v in key.items() if "short_ids" in v},
                             sort_keys=True))


def key_meta(d, pass_name):
    """keys/<pass>.meta.json, written by batches.py: the renderer the pass's
    packets were drawn with and the key's fingerprint. None if absent."""
    path = os.path.join(d, "keys", pass_name + ".meta.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def drift(spec):
    """Warnings for each recorded prompt, input builder or schema that has
    changed since the pass was labeled."""
    out = []
    now_p = prompt_fingerprints()
    for mode, p in (spec.get("prompts") or {}).items():
        if now_p.get(mode, {}).get("sha256") != p["sha256"]:
            out.append(f"{mode} prompt ({p['file']}) has changed since labeling; the labels follow prompt "
                       f"{p['prompt_hash']} (commit {p.get('commit')})")
    now_i = input_fingerprints()
    for name, rec in (spec.get("inputs") or {}).items():
        if now_i.get(name, {}).get("sha256") != rec["sha256"]:
            out.append(f"{name} ({rec['file']}) has changed since labeling; candidate inputs or outputs "
                       "may no longer match what the labelers saw")
    return out


def default_fixes(dirs, ref):
    """Score with score.py's fixes when the reference pass was labeled with v6:
    a negative v6 overall is then a negative on both sides. compare_v4 and
    next_round both use this, so reporting and round sampling agree."""
    return any(manifest(d).get(ref, {}).get("schema") == "v6" for d in dirs)


def num_ok(v):
    return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool) and -1 <= v <= 1)


def problems(m, mode, short_ids):
    out = []
    if not isinstance(m, dict):
        return ["mention is not an object"]
    for k in REQUIRED:
        if k not in m:
            out.append(f"missing {k}")
    if not isinstance(m.get("restaurant_raw"), str) or not m.get("restaurant_raw", "").strip():
        out.append("restaurant_raw empty")
    for k in ("dishes", "descriptors"):
        if k in m and not isinstance(m[k], list):
            out.append(f"{k} not a list")
    a = m.get("aspects")
    if not isinstance(a, dict) or set(a) != set(ASPECTS):
        out.append("aspects must have exactly food, value, service, atmosphere, wait")
    elif not all(num_ok(v) for v in a.values()):
        out.append("aspect outside -1..1")
    if not num_ok(m.get("expensiveness")):
        out.append("expensiveness outside -1..1")
    for k in ("is_firsthand", "is_negated"):
        if k in m and not isinstance(m[k], bool):
            out.append(f"{k} not boolean")
    if mode == "thread":
        if str(m.get("id")) not in short_ids:
            out.append(f"id {m.get('id')!r} not a bracket number in this packet")
    return out


class LabelError(SystemExit):
    """Raised by export when any label is invalid: nothing is written."""


def key_errors(d, pass_name, key, spec):
    rec = spec.get("key")
    if not rec:
        return [f"{pass_name}: the manifest records no key for this v6 pass; run labels.py init"]
    meta = key_meta(d, pass_name)
    fp = key_fingerprint(key)
    out = []
    if meta is None:
        out.append(f"{pass_name}: keys/{pass_name}.meta.json is missing; rebuild with batches.py")
    else:
        if meta.get("renderer") != rec["renderer"]:
            out.append(f"{pass_name}: the key was built with renderer {meta.get('renderer')!r}, but the labels "
                       f"were made against {rec['renderer']!r}; rebuild packets with that renderer")
        if meta.get("short_ids_sha256") != fp:
            out.append(f"{pass_name}: keys/{pass_name}.json does not match its meta file")
    if fp != rec["short_ids_sha256"]:
        out.append(f"{pass_name}: the key's bracket numbers differ from the ones the labels were made against")
    return out


def read_pass(d, pass_name):
    """(key, {packet_id: mentions}, errors, missing).

    errors are hard failures: bad JSON, a packet id not in its batch, a
    packet labeled twice, a missing mentions list, or a mention that fails
    the schema (including a thread id that is not a bracket number in the
    packet). A packet labeled twice is kept neither way. missing lists the
    packets with no label yet.

    For a v6 pass the key must also be the one the labels were made against:
    the renderer and bracket-number fingerprint the manifest recorded must
    match keys/<pass>.meta.json and the key itself. Rebuilding packets with
    another renderer renumbers thread chunks, and the labels' ids would then
    land on the wrong comments, so any mismatch is a hard error."""
    with open(os.path.join(d, "keys", pass_name + ".json"), encoding="utf-8") as f:
        key = json.load(f)
    spec = manifest(d).get(pass_name, {})
    v6 = spec.get("schema") == "v6"
    schemas = v6_schemas() if v6 else None
    got, errors, twice = {}, [], set()
    if v6:
        errors += key_errors(d, pass_name, key, spec)
    ldir = os.path.join(d, "labels", pass_name)
    for b in sorted({v["batch"] for v in key.values()}):
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
            if not isinstance(ms, list):
                errors.append(f"{b}:{n}: output has no mentions list")
                continue
            if v6:
                bad = [f"{b}:{n} {pid} v6 schema: {e}"
                       for e in S.v6_adapter.schema_errors(out, schemas[key[pid]["mode"]])]
                if bad:
                    errors += bad
                    continue
            # Labels written with the v6 prompt are mapped into this file's
            # schema first, the same mapping score.py applies to v6 runs.
            ms = S.v6_adapter.adapt_all(ms)
            bad = [f"{b}:{n} {pid} mention {i}: {p}" for i, m in enumerate(ms)
                   for p in problems(m, key[pid]["mode"], key[pid].get("short_ids", {}))]
            errors += bad
            if not bad:
                got[pid] = ms
    missing = [pid for pid in key if pid not in got and pid not in twice]
    return key, got, errors, missing


def as_gold_mention(m, alias, excluded):
    key = S.model_key(m, alias)
    asp = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
    levels = {a: S.bucket(asp.get(a)) for a in ASPECTS}
    vc = m.get("value_complaint")
    if vc is None:
        vc = (levels["value"] or 0) < 0
    dish = []
    for d in m.get("dish_sentiment") or []:
        if isinstance(d, dict) and d.get("dish"):
            dish.append({"dish": d["dish"], "level": S.bucket(d.get("level")), "avoid": bool(d.get("avoid"))})
    desc = [str(x) for x in (m.get("descriptors") or [])]
    first = m.get("is_firsthand")
    return {
        "restaurant_raw": m.get("restaurant_raw"), "canonical_key": key, "accept_keys": [],
        "out_of_scope": bool(m.get("out_of_scope")) or key in excluded,
        "ambiguous": bool(m.get("ambiguous")),
        "aspects": levels, "aspect_alternatives": {},
        "expensiveness": S.bucket(m.get("expensiveness")),
        "value_complaint": bool(vc), "dish_sentiment": dish,
        "dishes": [str(x) for x in (m.get("dishes") or [])],
        "search_terms": [str(x) for x in (m.get("search_terms") or [])],
        "descriptors": desc, "closed": any(x.strip().lower() == "closed" for x in desc),
        "is_negated": bool(m.get("is_negated")),
        "is_firsthand": first if isinstance(first, bool) else None,
        "uncertain_fields": [], "neighborhood_hint": m.get("neighborhood_hint"),
        # A v6 label keeps its own words (overall, opinion, named_in, notes),
        # which the 7-point gold shape cannot hold.
        **({"v6": m["v6"]} if isinstance(m.get("v6"), dict) else {}),
    }


def gold_lines(items, by_comment, alias, excluded, source):
    """One gold line per labeled comment. by_comment: {comment_id: [mentions]}
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
                g = as_gold_mention(m, alias, excluded)
                if not g["canonical_key"] or g["canonical_key"] in seen:
                    continue          # the same place twice in one comment is one mention
                seen.add(g["canonical_key"])
                ms.append(g)
            # Chains are dropped on both sides when scoring (production drops
            # them at write time), so they are never a required mention.
            out.append({"item_id": it["item_id"], "comment_id": cid, "thread_id": it["thread_id"],
                        "source": source, "mentions": ms,
                        "has_mention": any(S.is_required(g) and g["canonical_key"] not in S.CHAINS
                                           for g in ms)})
    return out


def export(d, pass_name, allow_missing=False):
    """Write the run and gold files, or raise LabelError and write nothing."""
    key, got, errors, missing = read_pass(d, pass_name)
    for w in drift(manifest(d).get(pass_name, {})):
        print(f"note: {w}", file=sys.stderr)
    problems_found = list(errors)
    if missing and not allow_missing:
        problems_found.append(f"{len(missing)} packet(s) unlabeled, e.g. {missing[:5]} "
                              "(--allow-missing exports the rest)")
    if problems_found:
        raise LabelError("\n".join([f"{pass_name}: not exported, {len(problems_found)} problem(s):"]
                                   + ["  " + p for p in problems_found[:200]]))
    items = {it["item_id"]: it for it in S.load_jsonl(os.path.join(d, "items.jsonl"))}
    records, primary = [], {}
    for pid, ms in got.items():
        k = key[pid]
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
                by[k["short_ids"][str(m.get("id"))]].append(m)   # ids validated in read_pass
        records.append({"call_key": call, "rep": k["copy"], "item_ids": [it["item_id"]],
                        "packet_id": pid, "model": f"claude-labels/{pass_name}", "prompt_hash": pass_name,
                        "mode": it["mode"], "json_ok": True, "error": None,
                        "mentions_by_comment": dict(by)})
        if k["copy"] == 0:
            primary.update(by)
    ldir = os.path.join(d, "labels")
    with open(os.path.join(ldir, pass_name + ".run.jsonl"), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    gold = gold_lines(list(items.values()), primary, S.load_map("alias_overrides.json"),
                      S.load_map("excluded_entities.json"), pass_name)
    with open(os.path.join(ldir, pass_name + ".gold.jsonl"), "w", encoding="utf-8") as f:
        for g in gold:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    print(f"{pass_name}: {len(records)} labeled packets -> {len(gold)} gold comments "
          f"({sum(g['has_mention'] for g in gold)} with a required mention)")


def complete(d, pass_name):
    """True when every packet of the pass has exactly one valid label."""
    if not os.path.exists(os.path.join(d, "keys", pass_name + ".json")):
        return False
    _, _, errors, missing = read_pass(d, pass_name)
    return not errors and not missing


def init(d, pass_name, commit=None):
    """Record in labels/manifest.json what a v6 pass is labeled against: the
    two system prompts, the input builders and schema, and the key (its
    renderer and bracket-number fingerprint, from keys/<pass>.meta.json).
    Run it when labeling starts. Fields already recorded are kept, and a
    recorded value that no longer matches refuses, so init can never quietly
    move a labeled pass onto a new prompt or key."""
    meta = key_meta(d, pass_name)
    if meta is None:
        raise LabelError(f"{pass_name}: keys/{pass_name}.meta.json is missing; run batches.py first")
    with open(os.path.join(d, "keys", pass_name + ".json"), encoding="utf-8") as f:
        key = json.load(f)
    if meta.get("short_ids_sha256") != key_fingerprint(key):
        raise LabelError(f"{pass_name}: keys/{pass_name}.json does not match its meta file")
    prompts = prompt_fingerprints()
    if commit:
        for p in prompts.values():
            p["commit"] = commit
    now = {"schema": "v6", "prompts": prompts, "inputs": input_fingerprints(),
           "key": {"renderer": meta["renderer"], "short_ids_sha256": meta["short_ids_sha256"]}}
    man = manifest(d)
    entry = man.setdefault(pass_name, {})
    clash = []
    for field, value in now.items():
        if field not in entry:
            entry[field] = value
        elif field in ("prompts", "inputs"):
            old = entry[field]
            clash += [f"{field}.{n}" for n in value if n in old and old[n]["sha256"] != value[n]["sha256"]]
            for n in value:
                old.setdefault(n, value[n])
        elif entry[field] != value:
            clash.append(field)
    if clash:
        raise LabelError(f"{pass_name}: the manifest already records a different {', '.join(clash)}; "
                         "those labels belong to that version, so nothing was changed")
    os.makedirs(os.path.join(d, "labels", pass_name), exist_ok=True)
    with open(os.path.join(d, "labels", MANIFEST), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    print(f"{pass_name}: manifest records schema v6, prompts "
          f"{', '.join(p['prompt_hash'] for p in prompts.values())}, key renderer {meta['renderer']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("check", "export", "init"))
    ap.add_argument("--pass", dest="pass_name", choices=PASSES, required=True)
    ap.add_argument("--dir", default=HERE)
    ap.add_argument("--allow-missing", action="store_true", help="export even if some packets are unlabeled")
    ap.add_argument("--batch", help="check only: just this batch (bNNN)")
    ap.add_argument("--commit", help="init: the commit the prompts are frozen at")
    args = ap.parse_args()
    if args.batch and args.cmd != "check":
        ap.error("--batch works with check only; export always writes the whole pass")
    if args.cmd == "init":
        init(args.dir, args.pass_name, args.commit)              # LabelError exits nonzero
        return
    if args.cmd == "export":
        export(args.dir, args.pass_name, args.allow_missing)    # LabelError exits nonzero
        return
    key, got, errors, missing = read_pass(args.dir, args.pass_name)
    spec = manifest(args.dir).get(args.pass_name, {})
    for w in drift(spec):
        print(f"note: {w}")
    if args.batch:
        # One batch only: how a labeler's file is checked the moment it lands.
        # Pass-level errors (the key against the manifest) still count.
        if args.batch not in {v["batch"] for v in key.values()}:
            sys.exit(f"{args.pass_name}: no batch {args.batch!r} in keys/{args.pass_name}.json")
        errors = [e for e in errors if e.startswith((args.batch + ":", args.pass_name + ":"))]
        missing = [p for p in missing if key[p]["batch"] == args.batch]
        got = {p: v for p, v in got.items() if key[p]["batch"] == args.batch}
    print(f"{len(got)} packets validly labeled ({spec.get('schema', 'production')} schema), "
          f"{len(missing)} unlabeled, {len(errors)} error(s)")
    for e in errors[:200]:
        print("  " + e)
    if errors or missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
