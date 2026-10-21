"""Check and aggregate the Opus judgments of Haiku's round-3 output. No database, no model.

    python eval/review_v6/judgments.py check               # every packet item judged once, valid
    python eval/review_v6/judgments.py aggregate           # -> report.json, report.md
    python eval/review_v6/judgments.py self-test           # synthetic judges, temp dir

A judgment line (RUBRIC.md):
  {item_id, comment_id, own_read:[{name, overall, aspects, experience, opinion, avoid, dishes}],
   compare:[{name, field, haiku, own, final, right, reason}], missed:[v6 mentions],
   notes_grade:[{name, notes, tags, location, note}], rule_questions:[...], overall_item_ok}

The aggregator diffs own_read against the output shown in the packet itself. Every
difference must have a compare entry (the checker enforces it). Where the two
agree, that value is final. Where they differ, the compare entry's final is. Haiku
is scored against the final values on the items that showed its real round-3
output. The judge's first read is scored against the same finals (judge
self-consistency). Planted items are scored only for whether the judge caught the
change, using the sealed key.
"""

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
sys.path.insert(0, os.path.dirname(EVAL))
import score as S  # noqa: E402
from extract import normalize_entity  # noqa: E402

PACKETS = os.path.join(HERE, "packets")
JUDGMENTS = os.path.join(HERE, "judgments")
KEY = os.path.join(HERE, ".sealed", "key.json")
LEVELS = ("very_positive", "positive", "neutral", "negative", "very_negative", None)
ASPECTS = ("taste", "value", "service", "atmosphere", "wait")
SCORED = ["overall"] + [f"aspects.{a}" for a in ASPECTS] + ["experience", "opinion", "avoid"]
EXTRA = ("price", "timeframe", "trend", "status")
ENUMS = {"overall": LEVELS, **{f"aspects.{a}": LEVELS for a in ASPECTS},
         "experience": ("firsthand", "secondhand", "none"), "opinion": ("none", "endorse", "stated"),
         "avoid": (True, False), "_mention": ("present", None),
         "price": ("very_cheap", "cheap", "moderate", "expensive", "very_expensive", None),
         "timeframe": ("current", "past"), "trend": ("declined", "improved", None),
         "status": ("closed", "moved", "opened", None)}
RIGHT = ("haiku", "judge", "neither")
GRADES = ("ok", "wrong", "missing")
_alias = None


def k(name):
    global _alias
    if _alias is None:
        _alias = S.load_map("alias_overrides.json")
    x = S.street_norm(normalize_entity(name or ""))
    return _alias.get(x, x)


def same(a, b):
    ka, kb = k(a), k(b)
    return bool(ka) and (ka == kb or S.fuzzy(ka, kb))


def get(m, field):
    if field.startswith("aspects."):
        return (m.get("aspects") or {}).get(field.split(".", 1)[1])
    return m.get(field)


def pair(own, shown):
    """[(own mention or None, shown mention or None)], places matched by name."""
    out, used = [], set()
    for o in own:
        j = next((i for i, s in enumerate(shown) if i not in used and same(o.get("name"), s.get("name"))), None)
        if j is None:
            out.append((o, None))
        else:
            used.add(j)
            out.append((o, shown[j]))
    out += [(None, s) for i, s in enumerate(shown) if i not in used]
    return out


def dish_pairs(a, b):
    a, b = a or [], b or []
    out, used = [], set()
    for x in a:
        j = next((i for i, y in enumerate(b) if i not in used and S.lenient_same(x.get("dish"), y.get("dish"))), None)
        out.append((x, b[j] if j is not None else None))
        if j is not None:
            used.add(j)
    out += [(None, y) for i, y in enumerate(b) if i not in used]
    return out


def dval(d):
    return None if d is None else {"level": d.get("level"), "avoid": bool(d.get("avoid"))}


def diffs(own, shown):
    """[(place name, field, haiku value, own value)] where own_read and the output differ."""
    out = []
    for o, s in pair(own, shown):
        name = (o or s).get("name")
        if o is None or s is None:
            out.append((name, "_mention", "present" if s else None, "present" if o else None))
            continue
        for f in SCORED:
            if get(o, f) != get(s, f):
                out.append((name, f, get(s, f), get(o, f)))
        for do, ds in dish_pairs(o.get("dishes"), s.get("dishes")):
            if dval(do) != dval(ds):
                out.append((name, "dish:" + (do or ds)["dish"], dval(ds), dval(do)))
    return out


def find_compare(j, name, field):
    for c in j.get("compare") or []:
        if not same(c.get("name"), name):
            continue
        cf = c.get("field") or ""
        if cf == field or (cf.startswith("dish:") and field.startswith("dish:")
                           and S.lenient_same(cf[5:], field[5:])):
            return c
    return None


# ---------------------------------------------------------------- loading
def packets():
    out = {}
    for fn in sorted(os.listdir(PACKETS)):
        if fn.endswith(".json"):
            d = json.load(open(os.path.join(PACKETS, fn), encoding="utf-8"))
            out[d["packet"]] = d["items"]
    return out


def read(jdir=JUDGMENTS):
    """({item_id: judgment}, problems, {item_id: shown mentions})."""
    got, problems, shown = {}, [], {}
    for name, items in packets().items():
        allowed = {it["item_id"]: it for it in items}
        for it in items:
            shown[it["item_id"]] = it["shown"]
        path = os.path.join(jdir, name + ".jsonl")
        if not os.path.exists(path):
            continue
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            if not line.strip():
                continue
            try:
                j = json.loads(line)
            except json.JSONDecodeError as e:
                problems.append(f"{name}:{n}: bad JSON ({e})")
                continue
            iid = j.get("item_id")
            if iid not in allowed:
                problems.append(f"{name}:{n}: {iid!r} is not in this packet")
                continue
            if iid in got:
                problems.append(f"{name}:{n}: {iid} judged twice")
                continue
            problems += [f"{name}:{n}: {iid}: {p}" for p in validate(j, allowed[iid]["shown"])]
            got[iid] = j
    return got, problems, shown


def validate(j, shown):
    p = []
    for key in ("item_id", "comment_id", "own_read", "compare", "missed", "notes_grade", "rule_questions",
                "overall_item_ok"):
        if key not in j:
            p.append(f"missing {key}")
    for m in j.get("own_read") or []:
        for f in SCORED:
            if get(m, f) not in ENUMS[f]:
                p.append(f"own_read {m.get('name')!r}: {f} = {get(m, f)!r}")
        for d in m.get("dishes") or []:
            if not d.get("dish") or d.get("level") not in LEVELS:
                p.append(f"own_read {m.get('name')!r}: bad dish {d!r}")
    for c in j.get("compare") or []:
        f = c.get("field") or ""
        if c.get("right") not in RIGHT:
            p.append(f"compare {c.get('name')!r} {f}: right must be one of {RIGHT}")
        if f in ENUMS and c.get("final") not in ENUMS[f]:
            p.append(f"compare {c.get('name')!r} {f}: final {c.get('final')!r}")
        elif not (f in ENUMS or f.startswith("dish:")):
            p.append(f"compare: unknown field {f!r}")
    for name, f, hv, ov in diffs(j.get("own_read") or [], shown):
        if find_compare(j, name, f) is None:
            p.append(f"no compare entry for {name!r} {f} (Haiku {hv!r}, own {ov!r})")
    for g in j.get("notes_grade") or []:
        for f in ("notes", "tags", "location"):
            if g.get(f) not in GRADES:
                p.append(f"notes_grade {g.get('name')!r}: {f} must be one of {GRADES}")
    return p


# ---------------------------------------------------------------- aggregate
def final_places(j, shown):
    """[(final mention fields dict, shown mention or None, own mention or None)] for every
    place whose final status is present, plus the missed list's places."""
    out = []
    for o, s in pair(j.get("own_read") or [], shown):
        name = (o or s).get("name")
        if o is None or s is None:
            c = find_compare(j, name, "_mention")
            if not c or c.get("final") != "present":
                continue
        fin = {}
        for f in SCORED + list(EXTRA):
            c = find_compare(j, name, f)
            if c is not None:
                fin[f] = c.get("final")
            elif f in EXTRA:
                fin[f] = get(s, f) if s else None
            elif o is not None and s is not None:
                fin[f] = get(o, f)
            else:
                fin[f] = get(o or s, f)
        dishes = {}
        for do, ds in dish_pairs((o or {}).get("dishes"), (s or {}).get("dishes")):
            dn = (do or ds)["dish"]
            c = find_compare(j, name, "dish:" + dn)
            dishes[dn] = c.get("final") if c is not None else dval(do if o is not None else ds)
        fin["dishes"] = {d: v for d, v in dishes.items() if v is not None}
        out.append((name, fin, s, o))
    for m in j.get("missed") or []:
        if not any(same(m.get("name"), n) for n, _, _, _ in out):
            fin = {f: get(m, f) for f in SCORED + list(EXTRA)}
            fin["dishes"] = {d["dish"]: dval(d) for d in m.get("dishes") or []}
            out.append((m.get("name"), fin, None, None))
    return out


def negative(fin):
    return fin.get("overall") in ("negative", "very_negative") or any(
        fin.get(f"aspects.{a}") in ("negative", "very_negative") for a in ASPECTS) or fin.get("avoid")


def aggregate(jdir=JUDGMENTS, key_path=KEY, out_dir=HERE):
    got, problems, shown = read(jdir)
    key = json.load(open(key_path)) if os.path.exists(key_path) else {}
    acc = collections.defaultdict(lambda: [0, 0])          # field -> [haiku right, n]
    judge = collections.defaultdict(lambda: [0, 0])        # field -> [first read right, n]
    rights = collections.Counter()
    ment = collections.Counter()
    neg = collections.Counter()
    notes = collections.Counter()
    rq, items_ok = [], [0, 0]
    catch = collections.defaultdict(lambda: [0, 0])
    for iid, j in got.items():
        sh = shown[iid]
        for c in j.get("compare") or []:
            rights[c.get("right")] += 1
        for q in j.get("rule_questions") or []:
            rq.append({"item_id": iid, "question": q})
        places = final_places(j, sh)
        if iid in key:
            kk = key[iid]
            kind = kk["kind"]
            if kind == "r1_substitute":
                hit = not j.get("overall_item_ok", True)
            elif kind == "drop_mention":
                hit = any(same(n, kk["mention"]) for n, _, _, _ in places)
            elif kind == "drop_dish":
                # Lenient dish matching can pair the dropped dish with a similar one
                # still shown ("Chicken Over Rice" for "Braised Pork over rice"), so
                # count: caught only if the final list has more such dishes than shown.
                like = lambda ds: sum(S.lenient_same(d, kk["field"][5:]) for d in ds)  # noqa: E731
                hit = any(same(n, kk["mention"]) and s is not None
                          and like(fin["dishes"]) > like([d["dish"] for d in s.get("dishes") or []])
                          for n, fin, s, _ in places)
            else:
                hit = any(same(n, kk["mention"]) and fin.get(kk["field"]) != kk["shown"]
                          for n, fin, _, _ in places)
            catch[kind][0] += hit
            catch[kind][1] += 1
            continue
        items_ok[0] += bool(j.get("overall_item_ok"))
        items_ok[1] += 1
        haiku_names = [s.get("name") for s in sh]
        ment["haiku"] += len(sh)
        for name, fin, s, o in places:
            ment["final"] += 1
            ment["haiku_found"] += s is not None
            if negative(fin):
                neg["final_negative"] += 1
                neg["haiku_caught"] += s is not None and negative({f: get(s, f) for f in SCORED})
            if s is not None:
                for f in SCORED + list(EXTRA):
                    acc[f][0] += get(s, f) == fin.get(f)
                    acc[f][1] += 1
                sd = {d["dish"]: dval(d) for d in s.get("dishes") or []}
                for dn, v in fin["dishes"].items():
                    hv = next((x for d, x in sd.items() if S.lenient_same(d, dn)), None)
                    acc["dishes"][0] += hv == v
                    acc["dishes"][1] += 1
            if o is not None:
                for f in SCORED:
                    judge[f][0] += get(o, f) == fin.get(f)
                    judge[f][1] += 1
        ment["haiku_kept"] += sum(1 for n in haiku_names if any(same(n, x) for x, _, _, _ in places))
        for g in j.get("notes_grade") or []:
            for f in ("notes", "tags", "location"):
                notes[(f, g.get(f))] += 1
    r = lambda a: round(a[0] / a[1], 3) if a[1] else None  # noqa: E731
    report = {
        "items_judged": len(got), "problems": problems[:200], "items_with_real_output": items_ok[1],
        "haiku_item_ok_rate": r(items_ok),
        "haiku_field_accuracy": {f: {"acc": r(v), "n": v[1]} for f, v in sorted(acc.items())},
        "mention_recall": round(ment["haiku_found"] / ment["final"], 3) if ment["final"] else None,
        "mention_precision": round(ment["haiku_kept"] / ment["haiku"], 3) if ment["haiku"] else None,
        "missed_negatives": {"final_negative_mentions": neg["final_negative"],
                             "haiku_caught": neg["haiku_caught"],
                             "recall": round(neg["haiku_caught"] / neg["final_negative"], 3) if neg["final_negative"] else None},
        "notes_grades": {f"{f}:{g}": n for (f, g), n in sorted(notes.items(), key=str)},
        "judge_first_read_accuracy": {f: {"acc": r(v), "n": v[1]} for f, v in sorted(judge.items())},
        "disagreement_resolution": dict(rights),
        "judge_overturned_share": round(rights["haiku"] / sum(rights.values()), 3) if rights else None,
        "planted_catch_rate": {kind: {"caught": v[0], "n": v[1], "rate": r(v)} for kind, v in sorted(catch.items())},
        "planted_catch_rate_all": r([sum(v[0] for v in catch.values()), sum(v[1] for v in catch.values())]),
        "rule_questions": rq,
    }
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    lines = ["# Opus review of Haiku round 3", "",
             f"Items judged: {len(got)} (real round-3 output on {items_ok[1]}; the rest were planted checks).", "",
             f"- Haiku items fully right: {report['haiku_item_ok_rate']}",
             f"- Mention recall / precision (judge's final view): {report['mention_recall']} / {report['mention_precision']}",
             f"- Negative mentions caught: {report['missed_negatives']}",
             f"- Planted errors caught: {report['planted_catch_rate_all']} {json.dumps(report['planted_catch_rate'])}",
             f"- Judge first read overturned by its own re-read: {report['judge_overturned_share']} "
             f"(resolution {report['disagreement_resolution']})", "",
             "## Haiku field accuracy (against final values)", "", "| field | accuracy | n |", "|---|---:|---:|"]
    lines += [f"| {f} | {v['acc']} | {v['n']} |" for f, v in report["haiku_field_accuracy"].items()]
    lines += ["", "## Judge first-read accuracy", "", "| field | accuracy | n |", "|---|---:|---:|"]
    lines += [f"| {f} | {v['acc']} | {v['n']} |" for f, v in report["judge_first_read_accuracy"].items()]
    lines += ["", "## Notes, tags, location", "", json.dumps(report["notes_grades"]), "",
              f"## Rule questions ({len(rq)})", ""]
    lines += [f"- {q['item_id']}: {q['question']}" for q in rq]
    if problems:
        lines += ["", f"## Checker problems ({len(problems)})", ""] + [f"- {p}" for p in problems[:50]]
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return report


# ---------------------------------------------------------------- self-test
def self_test():
    """Two synthetic judges over every packet: one that copies Haiku's output (it must
    catch nothing), and one that knows the truth from the key (it must catch all)."""
    import copy
    import tempfile
    key = json.load(open(KEY))
    with tempfile.TemporaryDirectory() as tmp:
        for mode in ("rubber_stamp", "oracle"):
            jdir = os.path.join(tmp, mode)
            os.makedirs(jdir)
            for name, items in packets().items():
                with open(os.path.join(jdir, name + ".jsonl"), "w") as f:
                    for it in items:
                        own = [{kk: m.get(kk) for kk in ("name", "overall", "aspects", "experience", "opinion", "avoid", "dishes")}
                               for m in copy.deepcopy(it["shown"])]
                        compare, ok = [], True
                        kk = key.get(it["item_id"])
                        if mode == "oracle" and kk:
                            ok = False
                            if kk["kind"] == "drop_mention":
                                own.append({"name": kk["mention"], "overall": None,
                                            "aspects": {a: None for a in ASPECTS}, "experience": "firsthand",
                                            "opinion": "none", "avoid": False, "dishes": []})
                                compare.append({"name": kk["mention"], "field": "_mention", "haiku": None,
                                                "own": "present", "final": "present", "right": "judge", "reason": "t"})
                            elif kk["kind"] == "drop_dish":
                                m = next(o for o in own if same(o["name"], kk["mention"]))
                                m["dishes"] = (m.get("dishes") or []) + [kk["original"]]
                                compare.append({"name": kk["mention"], "field": kk["field"], "haiku": None,
                                                "own": dval(kk["original"]), "final": dval(kk["original"]),
                                                "right": "judge", "reason": "t"})
                            elif kk["kind"] != "r1_substitute":
                                m = next(o for o in own if same(o["name"], kk["mention"]))
                                fld = kk["field"]
                                if fld.startswith("aspects."):
                                    m["aspects"][fld.split(".", 1)[1]] = kk["original"]
                                else:
                                    m[fld] = kk["original"]
                                compare.append({"name": kk["mention"], "field": fld, "haiku": kk["shown"],
                                                "own": kk["original"], "final": kk["original"], "right": "judge",
                                                "reason": "t"})
                        f.write(json.dumps({"item_id": it["item_id"], "comment_id": it["comment_id"], "own_read": own,
                                            "compare": compare, "missed": [], "notes_grade": [],
                                            "rule_questions": [], "overall_item_ok": ok}) + "\n")
            rep = aggregate(jdir, KEY, jdir)
            assert not rep["problems"], rep["problems"][:5]
            assert rep["items_judged"] == sum(len(v) for v in packets().values())
            rate = rep["planted_catch_rate_all"]
            assert (rate == 0.0) if mode == "rubber_stamp" else (rate == 1.0), (mode, rep["planted_catch_rate"])
            assert rep["haiku_field_accuracy"]["overall"]["acc"] == 1.0 and rep["mention_recall"] == 1.0
            print(f"self-test {mode}: catch rate {rate}, {rep['items_judged']} items, no checker problems")
        # a judge that disagrees without a compare entry must be flagged
        it = next(iter(packets().values()))[0]
        bad = {"item_id": it["item_id"], "comment_id": it["comment_id"], "own_read": [], "compare": [], "missed": [],
               "notes_grade": [], "rule_questions": [], "overall_item_ok": True}
        assert (not it["shown"]) or validate(bad, it["shown"]), "missing compare entries must be reported"
    print("judgments self-test ok")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        got, problems, shown = read()
        print(f"{len(got)} of {len(shown)} items judged, {len(problems)} problem(s)")
        for p in problems[:100]:
            print("  " + p)
        sys.exit(1 if problems or len(got) < len(shown) else 0)
    if cmd == "aggregate":
        rep = aggregate()
        print(json.dumps({k: rep[k] for k in ("items_judged", "haiku_item_ok_rate", "mention_recall",
                                              "mention_precision", "planted_catch_rate_all",
                                              "judge_overturned_share")}, indent=1))
        return
    if cmd == "self-test":
        self_test()


if __name__ == "__main__":
    main()
