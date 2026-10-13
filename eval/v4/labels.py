"""Check and convert Claude's labels. No database, no model.

    python eval/v4/labels.py check  --pass same_input        # every packet labeled, schema valid
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
different schema, write a mapping into this shape before export.

EXPORT writes two files per pass:

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
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import score as S  # noqa: E402

ASPECTS = ("food", "value", "service", "atmosphere", "wait")
REQUIRED = ("restaurant_raw", "neighborhood_hint", "dishes", "descriptors", "aspects",
            "expensiveness", "is_firsthand", "is_negated")
PASSES = ("same_input", "full_context")


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


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


def read_pass(d, pass_name):
    """(key, {packet_id: output}, issues)."""
    with open(os.path.join(d, "keys", pass_name + ".json"), encoding="utf-8") as f:
        key = json.load(f)
    got, issues = {}, []
    ldir = os.path.join(d, "labels", pass_name)
    batches = sorted({v["batch"] for v in key.values()})
    for b in batches:
        path = os.path.join(ldir, b + ".jsonl")
        if not os.path.exists(path):
            issues.append(f"{b}: no label file")
            continue
        for n, line in enumerate(open(path, encoding="utf-8"), start=1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                issues.append(f"{b}:{n}: bad JSON ({e})")
                continue
            pid = rec.get("packet_id")
            if pid not in key or key[pid]["batch"] != b:
                issues.append(f"{b}:{n}: packet {pid!r} is not in this batch")
                continue
            if pid in got:
                issues.append(f"{b}:{n}: packet {pid} labeled twice")
            out = rec.get("output")
            ms = out.get("mentions") if isinstance(out, dict) else None
            if not isinstance(ms, list):
                issues.append(f"{b}:{n}: output has no mentions list")
                continue
            for i, m in enumerate(ms):
                for p in problems(m, key[pid]["mode"], key[pid].get("short_ids", {})):
                    issues.append(f"{b}:{n} {pid} mention {i}: {p}")
            got[pid] = ms
    missing = [pid for pid in key if pid not in got]
    if missing:
        issues.append(f"{len(missing)} packet(s) unlabeled, e.g. {missing[:5]}")
    return key, got, issues


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
            out.append({"item_id": it["item_id"], "comment_id": cid, "thread_id": it["thread_id"],
                        "source": source, "mentions": ms,
                        "has_mention": any(S.is_required(g) for g in ms)})
    return out


def export(d, pass_name):
    key, got, issues = read_pass(d, pass_name)
    items = {it["item_id"]: it for it in load_jsonl(os.path.join(d, "items.jsonl"))}
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
                cid = k["short_ids"].get(str(m.get("id")))
                if cid:
                    by[cid].append(m)
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
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("check", "export"))
    ap.add_argument("--pass", dest="pass_name", choices=PASSES, required=True)
    ap.add_argument("--dir", default=HERE)
    args = ap.parse_args()
    if args.cmd == "check":
        _, got, issues = read_pass(args.dir, args.pass_name)
        print(f"{len(got)} packets labeled")
    else:
        issues = export(args.dir, args.pass_name)
    for i in issues[:200]:
        print("  " + i)
    if issues:
        print(f"{len(issues)} issue(s)")
        sys.exit(1 if args.cmd == "check" else 0)


if __name__ == "__main__":
    main()
