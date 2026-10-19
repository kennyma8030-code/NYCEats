"""Check and aggregate the Opus judgments of Haiku's round-4 output. No database, no model.

    python eval/review_v6r4/judgments.py check        # every packet item judged once, valid
    python eval/review_v6r4/judgments.py aggregate    # -> report.json, report.md
    python eval/review_v6r4/judgments.py self-test    # build + synthetic judges in a temp dir

The judgment line is round 3's (eval/review_v6/RUBRIC.md), with timeframe, trend and
status compared like the other blind fields and a kind grade in notes_grade.

Final values come from three places. A judged item's finals are its judge's (own read
where it agrees with the output shown, the compare entry's final where it doesn't, plus
missed places). An auto-resolved output (build.py) takes the round-3 finals it equalled,
or, for a medium output identical to low's, low's finals. Haiku's real output is then
scored against the finals of its comment, per source: round 3's 600, the hard cases, the
fresh held-out set, low and medium effort. Each is reported without and with the
validators (eval/v6_validate.py, DEFAULT), and round 3's output on the same 600 is
scored against the same finals, so round 3 and round 4 compare on one answer key.

Planted items are scored too, since a blind own read gives finals for every field,
except the planted field (or dropped mention, or dropped dish) itself. The planted
catch rate, the judges' first-read accuracy and how often a judge was overturned by
their own re-read are reported as in round 3.
"""

import collections
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, EVAL)
import build as B  # noqa: E402
import v6_validate as V  # noqa: E402

J3 = B.J3
BLIND = [f for f in B.FIELDS if f != "price"]
ENUMS = dict(J3.ENUMS, timeframe=("current", "past"))
GRADED = ("notes", "tags", "location", "kind")
NEGATIVE = ("negative", "very_negative")


# ---------------------------------------------------------------- reading
def packets(paths):
    out = {}
    for fn in sorted(os.listdir(paths.packets)):
        if fn.endswith(".json"):
            d = json.load(open(os.path.join(paths.packets, fn), encoding="utf-8"))
            out[d["packet"]] = d["items"]
    return out


def diffs(own, shown):
    """[(place, field, haiku value, own value)] wherever the blind read and the output differ."""
    out = []
    for o, s in J3.pair(own, shown):
        name = (o or s).get("name")
        if o is None or s is None:
            out.append((name, "_mention", "present" if s else None, "present" if o else None))
            continue
        for f in BLIND:
            if J3.get(o, f) != J3.get(s, f):
                out.append((name, f, J3.get(s, f), J3.get(o, f)))
        for do, ds in J3.dish_pairs(o.get("dishes"), s.get("dishes")):
            if J3.dval(do) != J3.dval(ds):
                out.append((name, "dish:" + (do or ds)["dish"], J3.dval(ds), J3.dval(do)))
    return out


def validate(j, shown):
    p = []
    for key in ("item_id", "comment_id", "own_read", "compare", "missed", "notes_grade", "rule_questions",
                "overall_item_ok"):
        if key not in j:
            p.append(f"missing {key}")
    for m in j.get("own_read") or []:
        for f in BLIND:
            if J3.get(m, f) not in ENUMS[f]:
                p.append(f"own_read {m.get('name')!r}: {f} = {J3.get(m, f)!r}")
        for d in m.get("dishes") or []:
            if not d.get("dish") or d.get("level") not in J3.LEVELS:
                p.append(f"own_read {m.get('name')!r}: bad dish {d!r}")
    for c in j.get("compare") or []:
        f = c.get("field") or ""
        if c.get("right") not in J3.RIGHT:
            p.append(f"compare {c.get('name')!r} {f}: right must be one of {J3.RIGHT}")
        if f in ENUMS and c.get("final") not in ENUMS[f]:
            p.append(f"compare {c.get('name')!r} {f}: final {c.get('final')!r}")
        elif not (f in ENUMS or f.startswith("dish:")):
            p.append(f"compare: unknown field {f!r}")
    for name, f, hv, ov in diffs(j.get("own_read") or [], shown):
        if J3.find_compare(j, name, f) is None:
            p.append(f"no compare entry for {name!r} {f} (Haiku {hv!r}, own {ov!r})")
    for g in j.get("notes_grade") or []:
        for f in GRADED:
            if g.get(f, "ok") not in J3.GRADES:
                p.append(f"notes_grade {g.get('name')!r}: {f} must be one of {J3.GRADES}")
    return p


def read(paths):
    """({item_id: judgment}, problems, {item_id: packet item})."""
    got, problems, items = {}, [], {}
    for name, its in packets(paths).items():
        allowed = {it["item_id"]: it for it in its}
        items.update(allowed)
        path = os.path.join(paths.judgments, name + ".jsonl")
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
    return got, problems, items


def final_places(j, shown):
    """[(name, fields)] for every place whose final status is present, missed places included."""
    out = []
    for o, s in J3.pair(j.get("own_read") or [], shown):
        name = (o or s).get("name")
        if o is None or s is None:
            c = J3.find_compare(j, name, "_mention")
            if not c or c.get("final") != "present":
                continue
        fin = {}
        for f in B.FIELDS:
            c = J3.find_compare(j, name, f)
            if c is not None:
                fin[f] = c.get("final")
            elif f == "price":
                fin[f] = J3.get(s, f) if s else None
            else:
                fin[f] = J3.get(o if o is not None else s, f)
        dishes = {}
        for do, ds in J3.dish_pairs((o or {}).get("dishes"), (s or {}).get("dishes")):
            dn = (do or ds)["dish"]
            c = J3.find_compare(j, name, "dish:" + dn)
            dishes[dn] = c.get("final") if c is not None else J3.dval(do if o is not None else ds)
        fin["dishes"] = {d: v for d, v in dishes.items() if v is not None}
        out.append((name, fin))
    for m in j.get("missed") or []:
        if not any(J3.same(m.get("name"), n) for n, _ in out):
            fin = {f: J3.get(m, f) for f in B.FIELDS}
            fin["dishes"] = {d["dish"]: J3.dval(d) for d in m.get("dishes") or []}
            out.append((m.get("name"), fin))
    return out


# ---------------------------------------------------------------- scoring
def negative(fields):
    return fields.get("overall") in NEGATIVE or bool(fields.get("avoid")) or any(
        fields.get(f"aspects.{a}") in NEGATIVE for a in B.ASPECTS)


def score(ms, finals, skip=None, acc=None):
    """Add one output's agreement with its finals to acc. skip: (name, field) pairs left out
    (a planted change); field "_mention" leaves the whole place out."""
    acc = acc if acc is not None else collections.Counter()
    skip = skip or set()
    gone = {n for n, f in skip if f == "_mention"}
    finals = [(n, f) for n, f in finals if not any(J3.same(n, g) for g in gone)]
    ms = [m for m in ms if not any(J3.same(m.get("name"), g) for g in gone)]
    used = set()
    for name, fin in finals:
        acc["final_mentions"] += 1
        acc["final_negative"] += negative(fin)
        j = next((i for i, m in enumerate(ms) if i not in used and J3.same(m.get("name"), name)), None)
        if j is None:
            continue
        used.add(j)
        m = ms[j]
        acc["found"] += 1
        mine = B.place_fields(m)
        acc["negative_caught"] += negative(fin) and negative(mine)
        for f in B.FIELDS:
            if any(J3.same(name, n) and f == sf for n, sf in skip):
                continue
            acc[f"n|{f}"] += 1
            acc[f"ok|{f}"] += mine[f] == fin.get(f)
        for dn, v in fin["dishes"].items():
            if any(J3.same(name, n) and sf.startswith("dish:") and J3.S.lenient_same(sf[5:], dn) for n, sf in skip):
                continue
            hv = next((x for d, x in mine["dishes"].items() if J3.S.lenient_same(d, dn)), None)
            acc["n|dishes"] += 1
            acc["ok|dishes"] += hv == v
    acc["output_mentions"] += len(ms)
    acc["output_kept"] += len(used)
    acc["items"] += 1
    acc["items_ok"] += B.equal_to_finals(ms, finals) if not skip else 0
    acc["items_ok_n"] += 0 if skip else 1
    return acc


def summary(acc):
    r = lambda a, b: round(acc[a] / acc[b], 3) if acc[b] else None  # noqa: E731
    out = {"items": acc["items"], "item_ok_rate": r("items_ok", "items_ok_n"),
           "mention_recall": r("found", "final_mentions"), "mention_precision": r("output_kept", "output_mentions"),
           "negative_recall": r("negative_caught", "final_negative"),
           "final_mentions": acc["final_mentions"], "final_negative_mentions": acc["final_negative"]}
    out["field_accuracy"] = {f: {"acc": r(f"ok|{f}", f"n|{f}"), "n": acc[f"n|{f}"]} for f in B.FIELDS + ["dishes"]}
    return out


def raw_outputs(path):
    """{comment_id: raw mention list} from a run file (no normalizing; the validators do it)."""
    if not path or not os.path.exists(path):
        return {}
    return {cid: B.B3.mentions_of(r) for cid, r in B.B3.run_records(path).items() if r.get("raw") is not None}


def aggregate(paths=B.Paths(), r3_run=None, write=True):
    key = json.load(open(paths.key, encoding="utf-8"))
    got, problems, items = read(paths)
    rows, _ = B.rows_and_contexts()
    runs = {"low": raw_outputs(key["runs_path"]["low"]), "med": raw_outputs(key["runs_path"]["medium"])}
    old = B.old_finals()
    # finals per (source, comment)
    finals, judged_source = {}, {}
    for iid, meta in key["items"].items():
        if iid in got:
            finals[(meta["source"], meta["comment_id"])] = final_places(got[iid], items[iid]["shown"])
            judged_source[iid] = meta
    for a in key["auto"]:
        if "reused" in a:
            finals[(a["source"], a["comment_id"])] = old[a["comment_id"]][0]
    for a in key["auto"]:
        if "same_as" in a and (a["same_as"], a["comment_id"]) in finals:
            finals[(a["source"], a["comment_id"])] = finals[(a["same_as"], a["comment_id"])]
    skips = collections.defaultdict(set)
    for iid, meta in key["items"].items():
        p = meta.get("planted")
        if p:
            skips[(meta["source"], meta["comment_id"])].add((p["mention"], p["field"]))
    by_source = collections.defaultdict(collections.Counter)
    by_source_v = collections.defaultdict(collections.Counter)
    for (src, cid), fin in finals.items():
        raw = runs["low" if src.endswith("-low") else "med"].get(cid)
        if raw is None:
            continue
        text = rows[cid]["body"] if cid in rows else ""
        score(B.shown_form(raw), fin, skips.get((src, cid)), by_source[src])
        validated, _, _ = V.apply(raw, text)
        score(validated, fin, skips.get((src, cid)), by_source_v[src])
    report = {"judged_items": len(got), "judged_expected": len(key["items"]), "problems": problems[:200],
              "auto_resolved": collections.Counter(a["source"] for a in key["auto"]),
              "missing_outputs": len(key.get("missing_outputs", [])),
              "by_source": {s: summary(a) for s, a in sorted(by_source.items())},
              "by_source_with_validators": {s: summary(a) for s, a in sorted(by_source_v.items())}}
    # round 3 on the same 600, against the same finals
    if r3_run:
        r3 = raw_outputs(r3_run)
        acc3, acc3v = collections.Counter(), collections.Counter()
        for (src, cid), fin in finals.items():
            if src == "r600-low" and cid in r3:
                sk = skips.get((src, cid))           # the same exclusions as round 4's low output
                score(B.shown_form(r3[cid]), fin, sk, acc3)
                score(V.apply(r3[cid], rows[cid]["body"] if cid in rows else "")[0], fin, sk, acc3v)
        report["round3_on_same_finals"] = summary(acc3)
        report["round3_on_same_finals_with_validators"] = summary(acc3v)
    # judges: first-read accuracy, overturned share, planted catch rate, rule questions
    rights, first = collections.Counter(), collections.Counter()
    catch = collections.defaultdict(lambda: [0, 0])
    rq = []
    for iid, j in got.items():
        meta = key["items"][iid]
        fin = final_places(j, items[iid]["shown"])
        for c in j.get("compare") or []:
            rights[c.get("right")] += 1
        for q in j.get("rule_questions") or []:
            rq.append({"item_id": iid, "source": meta["source"], "question": q})
        for o in j.get("own_read") or []:
            f = next((fv for n, fv in fin if J3.same(n, o.get("name"))), None)
            if f is None:
                continue
            for fld in BLIND:
                first[f"n|{fld}"] += 1
                first[f"ok|{fld}"] += J3.get(o, fld) == f.get(fld)
        p = meta.get("planted")
        if p:
            kind = p["kind"]
            if kind == "drop_mention":
                hit = any(J3.same(n, p["mention"]) for n, _ in fin)
            elif kind == "drop_dish":
                shown_m = next((m for m in items[iid]["shown"] if J3.same(m.get("name"), p["mention"])), {})
                like = lambda ds: sum(J3.S.lenient_same(d, p["field"][5:]) for d in ds)  # noqa: E731
                hit = any(J3.same(n, p["mention"]) and like(f["dishes"]) > like([d["dish"] for d in shown_m.get("dishes") or []])
                          for n, f in fin)
            else:
                hit = any(J3.same(n, p["mention"]) and f.get(p["field"]) != p["shown"] for n, f in fin)
            catch[kind][0] += hit
            catch[kind][1] += 1
    report["judge_first_read_accuracy"] = {f: round(first[f"ok|{f}"] / first[f"n|{f}"], 3) if first[f"n|{f}"] else None
                                           for f in BLIND}
    report["disagreement_resolution"] = dict(rights)
    report["judge_overturned_share"] = round(rights["haiku"] / sum(rights.values()), 3) if rights else None
    report["planted_catch_rate"] = {k: {"caught": v[0], "n": v[1]} for k, v in sorted(catch.items())}
    tot = [sum(v[0] for v in catch.values()), sum(v[1] for v in catch.values())]
    report["planted_catch_rate_all"] = round(tot[0] / tot[1], 3) if tot[1] else None
    report["rule_questions"] = rq
    if write:
        with open(os.path.join(paths.base, "report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        with open(os.path.join(paths.base, "report.md"), "w", encoding="utf-8") as f:
            f.write(markdown(report))
    return report


def markdown(rep):
    lines = ["# Opus review of Haiku round 4", "",
             f"Judged items: {rep['judged_items']} of {rep['judged_expected']}; auto-resolved outputs: "
             f"{dict(rep['auto_resolved'])}.", "",
             f"- Planted errors caught: {rep['planted_catch_rate_all']} {json.dumps(rep['planted_catch_rate'])}",
             f"- Judge first read overturned by its own re-read: {rep['judge_overturned_share']} "
             f"({rep['disagreement_resolution']})", ""]
    views = [("raw output", rep["by_source"]), ("with validators", rep["by_source_with_validators"])]
    if "round3_on_same_finals" in rep:
        views.append(("round 3 on the 600, same finals",
                      {"r600-low (r3)": rep["round3_on_same_finals"],
                       "r600-low (r3, validators)": rep["round3_on_same_finals_with_validators"]}))
    for title, by in views:
        if not by:
            continue
        srcs = list(by)
        lines += [f"## {title}", "", "| | " + " | ".join(srcs) + " |", "|---|" + "---:|" * len(srcs)]
        for k in ("items", "item_ok_rate", "mention_recall", "mention_precision", "negative_recall"):
            lines.append(f"| {k} | " + " | ".join(str(by[s][k]) for s in srcs) + " |")
        for f in B.FIELDS + ["dishes"]:
            lines.append(f"| {f} | " + " | ".join(str(by[s]["field_accuracy"][f]["acc"]) for s in srcs) + " |")
        lines.append("")
    lines += [f"## Rule questions ({len(rep['rule_questions'])})", ""]
    lines += [f"- {q['item_id']}: {q['question']}" for q in rep["rule_questions"]]
    if rep["problems"]:
        lines += ["", f"## Checker problems ({len(rep['problems'])})", ""] + [f"- {p}" for p in rep["problems"][:50]]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- self-test
def self_test():
    """Build packets from stand-in outputs (round 3's low run as round 4 low, round 1's
    medium run as medium, empty outputs for the hard and fresh sets) in a temp dir, then
    judge them with two synthetic judges: one that copies the output (catches nothing)
    and one that knows the planted changes (catches all). Both must pass the checker."""
    import copy
    tmp = tempfile.mkdtemp()
    try:
        r3 = os.path.join(EVAL, "runs", "claude-haiku-5-5__6b046d8ed65d__comment__bench6-low-r3_schema.jsonl")
        r1m = os.path.join(EVAL, "runs", "claude-haiku-5-5__a15cfb978cce__comment__bench6-med_schema.jsonl")
        sets = B.comment_sets()
        low_path, med_path = os.path.join(tmp, "low.jsonl"), os.path.join(tmp, "med.jsonl")
        for src, extra, out in ((r3, sets["hard"] + sets["fresh"], low_path), (r1m, sets["hard"], med_path)):
            keep = {f"comment:{c}" for c in sets["r600"]}
            with open(out, "w", encoding="utf-8") as f:
                for line in open(src, encoding="utf-8"):
                    r = json.loads(line)
                    if r["call_key"] in keep and r.get("rep", 0) == 0:
                        f.write(line)
                for c in extra:
                    f.write(json.dumps({"call_key": f"comment:{c}", "rep": 0, "raw": '{"mentions": []}'}) + "\n")
        paths = B.Paths(tmp)
        s = B.build(low_path, med_path, paths, quiet=True)
        key = json.load(open(paths.key))
        assert s["judged_items"] > 0 and s["planted"] > 0, s
        assert s["auto_resolved_by_source"].get("r600-low", 0) > 0, "round 3's output must equal many old finals"
        # round 3's own output equals its finals exactly where the old judge found it fully right
        n_auto = s["auto_resolved_by_source"]["r600-low"]
        old = B.old_finals()
        assert all(a["reused"] in {v[2] for v in old.values()} for a in key["auto"] if "reused" in a)
        for mode in ("rubber_stamp", "oracle"):
            jdir = paths.judgments = os.path.join(tmp, "judgments_" + mode)
            os.makedirs(jdir)
            for name, its in packets(paths).items():
                with open(os.path.join(jdir, name + ".jsonl"), "w") as f:
                    for it in its:
                        own = [{k: m.get(k) for k in ("name", "overall", "aspects", "experience", "opinion", "avoid",
                                                      "dishes", "timeframe", "trend", "status")}
                               for m in copy.deepcopy(it["shown"])]
                        compare, ok, p = [], True, key["items"][it["item_id"]].get("planted")
                        if mode == "oracle" and p:
                            ok = False
                            if p["kind"] == "drop_mention":
                                own.append({"name": p["mention"], "overall": None,
                                            "aspects": {a: None for a in B.ASPECTS}, "experience": "firsthand",
                                            "opinion": "none", "avoid": False, "dishes": [], "timeframe": "current",
                                            "trend": None, "status": None})
                                compare.append({"name": p["mention"], "field": "_mention", "haiku": None,
                                                "own": "present", "final": "present", "right": "judge", "reason": "t"})
                            elif p["kind"] == "drop_dish":
                                m = next(o for o in own if J3.same(o["name"], p["mention"]))
                                m["dishes"] = (m.get("dishes") or []) + [p["original"]]
                                compare.append({"name": p["mention"], "field": p["field"], "haiku": None,
                                                "own": J3.dval(p["original"]), "final": J3.dval(p["original"]),
                                                "right": "judge", "reason": "t"})
                            else:
                                m = next(o for o in own if J3.same(o["name"], p["mention"]))
                                fld = p["field"]
                                if fld.startswith("aspects."):
                                    m["aspects"] = dict(m["aspects"], **{fld[8:]: p["original"]})
                                else:
                                    m[fld] = p["original"]
                                compare.append({"name": p["mention"], "field": fld, "haiku": p["shown"],
                                                "own": p["original"], "final": p["original"], "right": "judge",
                                                "reason": "t"})
                        grades = [{"name": m["name"], "notes": "ok", "tags": "ok", "location": "ok", "kind": "ok",
                                   "note": ""} for m in it["shown"]]
                        f.write(json.dumps({"item_id": it["item_id"], "comment_id": it["comment_id"], "own_read": own,
                                            "compare": compare, "missed": [], "notes_grade": grades,
                                            "rule_questions": [], "overall_item_ok": ok}) + "\n")
            rep = aggregate(paths, r3_run=r3, write=False)
            assert not rep["problems"], rep["problems"][:5]
            assert rep["judged_items"] == rep["judged_expected"] == s["judged_items"]
            rate = rep["planted_catch_rate_all"]
            assert rate == (0.0 if mode == "rubber_stamp" else 1.0), (mode, rep["planted_catch_rate"])
            low = rep["by_source"]["r600-low"]
            # the stand-in low output is round 3's: on its own finals it scores like round 3
            assert low["items"] == len(sets["r600"]), low["items"]
            assert rep["round3_on_same_finals"]["field_accuracy"]["overall"] == low["field_accuracy"]["overall"]
            print(f"self-test {mode}: {rep['judged_items']} judged, {n_auto} auto-resolved low outputs, "
                  f"catch rate {rate}, r600-low overall acc {low['field_accuracy']['overall']['acc']}, "
                  f"with validators {rep['by_source_with_validators']['r600-low']['field_accuracy']['overall']['acc']}")
        # an own read that differs from the output with no compare entry must be reported
        it = next(i for its in packets(paths).values() for i in its if i["shown"])
        bad = {"item_id": it["item_id"], "comment_id": it["comment_id"], "own_read": [], "compare": [], "missed": [],
               "notes_grade": [], "rule_questions": [], "overall_item_ok": True}
        assert validate(bad, it["shown"]), "missing compare entries must be reported"
        print(f"packets: {s['packets']}, judged by source {s['judged_by_source']}, auto {s['auto_resolved_by_source']}")
        print("review_v6r4 self-test ok")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    paths = B.Paths()
    if cmd == "self-test":
        return self_test()
    if cmd == "check":
        got, problems, items = read(paths)
        print(f"{len(got)} of {len(items)} items judged, {len(problems)} problem(s)")
        for p in problems[:100]:
            print("  " + p)
        sys.exit(1 if problems or len(got) < len(items) else 0)
    if cmd == "aggregate":
        r3 = os.path.join(EVAL, "runs", "claude-haiku-5-5__6b046d8ed65d__comment__bench6-low-r3_schema.jsonl")
        rep = aggregate(paths, r3_run=r3)
        print(json.dumps({k: rep[k] for k in ("judged_items", "planted_catch_rate_all", "judge_overturned_share")}))


if __name__ == "__main__":
    main()
