"""Judge-against-judge agreement: the second review (B, here) against the first (A, review_v6r4).

    python eval/review_v6r4_rejudge/agree.py check       # every r2 packet item judged once, valid
    python eval/review_v6r4_rejudge/agree.py report      # -> agreement.json, agreement.md
    python eval/review_v6r4_rejudge/agree.py self-test   # synthetic second judges, temp dir

Each of the 150 items maps back to the first review by comment id: the fresh-med item A
judged, or, where fresh-med's output equalled fresh-low's and inherited its grades, the
fresh-low item. Both reviews' final values come from the same code (review_v6r4/judgments.py
final_places). Fields a planted change touched, in either review, are left out of every
comparison, and so is the item for the item-level verdict.

Reported:
  1. per-field agreement of A's and B's final values: mention presence, overall, each
     aspect, experience, opinion, avoid, timeframe, trend, status, price, dishes;
  2. item-level agreement on overall_item_ok;
  3. Haiku's accuracy on the same 150 under A's finals and under B's: the error bar;
  4. the planted catch rate in B;
  5. every disagreement, grouped by the rule it most likely turns on, with the comment.
"""

import collections
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_packets as MP  # noqa: E402

J4, B4 = MP.J4, MP.B4
J3 = B4.J3
FIELDS = B4.FIELDS                      # overall, five aspects, experience, opinion, avoid, timeframe, trend, status, price
ACC_FIELDS = ("overall", "aspects.taste", "dishes", "experience", "opinion")
A_DIR = MP.R4


# ---------------------------------------------------------------- the two reviews
def review_a(key_a_path=None):
    """{comment_id: (finals, judgment, shown, planted or None, A item id)} for fresh-med."""
    key = json.load(open(key_a_path or os.path.join(A_DIR, ".sealed", "key.json"), encoding="utf-8"))
    paths = B4.Paths(A_DIR)
    got, _, items = J4.read(paths)
    by = {}
    for iid, meta in key["items"].items():
        if meta["source"] in ("fresh-med", "fresh-low") and iid in got:
            by[(meta["source"], meta["comment_id"])] = iid
    out = {}
    cids = {meta["comment_id"] for meta in key["items"].values() if meta["source"] == "fresh-low"}
    same = {a["comment_id"] for a in key["auto"] if a["source"] == "fresh-med" and a.get("same_as") == "fresh-low"}
    for cid in cids:
        src = "fresh-low" if cid in same else "fresh-med"
        iid = by.get((src, cid))
        if iid is None:
            continue
        j = got[iid]
        out[cid] = (J4.final_places(j, items[iid]["shown"]), j, items[iid]["shown"],
                    key["items"][iid].get("planted"), iid)
    return out


def review_b(paths):
    key = json.load(open(paths.key, encoding="utf-8"))
    got, problems, items = J4.read(paths)
    out = {}
    for iid, meta in key["items"].items():
        if iid in got:
            out[meta["comment_id"]] = (J4.final_places(got[iid], items[iid]["shown"]), got[iid], items[iid]["shown"],
                                       meta.get("planted"), iid)
    return out, problems, key, items


# ---------------------------------------------------------------- comparisons
def _skip(planted):
    return {(planted["mention"], planted["field"])} if planted else set()


def _skipped(skip, name, field):
    for n, f in skip:
        if J3.same(n, name) and (f == field or f == "_mention" or
                                 (f.startswith("dish:") and field.startswith("dish:") and J3.S.lenient_same(f[5:], field[5:]))):
            return True
    return False


def pair_places(fa, fb):
    """[(name, A fields or None, B fields or None)], places matched by name."""
    out, used = [], set()
    for na, a in fa:
        j = next((i for i, (nb, _) in enumerate(fb) if i not in used and J3.same(na, nb)), None)
        if j is None:
            out.append((na, a, None))
        else:
            used.add(j)
            out.append((na, a, fb[j][1]))
    out += [(nb, None, b) for i, (nb, b) in enumerate(fb) if i not in used]
    return out


def compare_finals(fa, fb, skip):
    """[(place, field, A value, B value, agree)] for one comment."""
    rows = []
    for name, a, b in pair_places(fa, fb):
        if _skipped(skip, name, "_mention"):
            continue
        rows.append((name, "_mention", "present" if a else None, "present" if b else None, bool(a) == bool(b)))
        if not (a and b):
            continue
        for f in FIELDS:
            if not _skipped(skip, name, f):
                rows.append((name, f, a.get(f), b.get(f), a.get(f) == b.get(f)))
        dishes = list(a["dishes"])
        dishes += [d for d in b["dishes"] if not any(J3.S.lenient_same(d, x) for x in dishes)]
        for d in dishes:
            if _skipped(skip, name, "dish:" + d):
                continue
            va = a["dishes"].get(d, next((v for x, v in a["dishes"].items() if J3.S.lenient_same(x, d)), None))
            vb = b["dishes"].get(d, next((v for x, v in b["dishes"].items() if J3.S.lenient_same(x, d)), None))
            rows.append((name, "dish:" + d, va, vb, va == vb))
    return rows


# ---------------------------------------------------------------- causes
BEST = re.compile(r"\b(best|greatest|top|favou?rite|#1|number one)\b", re.I)
WORST = re.compile(r"\b(worst|terrible|awful|disgusting|inedible|gross|sick)\b", re.I)
UNTRIED = re.compile(r"(never been|haven'?t (been|tried)|want to try|wanna try|gonna try|looks? (so |really )?\w+|"
                     r"sounds? \w+|can'?t wait|saved|bookmark|on my list|thanks?|thank you)", re.I)
PRONOUN = re.compile(r"\b(it|they|their|them|this place|that place|there)\b", re.I)
WAIT = re.compile(r"\b(line|wait|walk[- ]?in|reservation|book|resy|crowd|packed|sold out)\b", re.I)


def cause(field, va, vb, text, title, named_in):
    t = (text or "").replace("’", "'")
    levels = {v for v in (va, vb) if not isinstance(v, (dict, list))}
    if field.startswith("dish:"):
        return "dish naming and dish levels"
    if field == "_mention":
        if named_in == "context" or PRONOUN.search(t):
            return "it/they references and context places"
        return "whether a name counts (kind, passing names, non-places)"
    if field == "experience":
        return "untried reactions" if UNTRIED.search(t) else "experience voice (firsthand / secondhand / none)"
    if levels & {"very_positive"} and BEST.search(t):
        return "superlatives: is 'the best' city-wide?"
    if levels & {"very_negative"}:
        return "extremes: very_negative or negative"
    if field == "opinion" or (field == "overall" and None in levels):
        if UNTRIED.search(t):
            return "untried reactions"
        if len(t) < 80 and "?" in (title or ""):
            return "rule 6: bare answers and question framing"
        return "opinion type and null overall (fact, pick or verdict)"
    if field == "aspects.wait" or (field == "overall" and WAIT.search(t)):
        return "wait and overall"
    if levels & {"neutral"}:
        return "mixed versus a bottom line"
    if field in ("timeframe", "trend", "status"):
        return "time, trend and closure"
    if field in ("price", "aspects.value"):
        return "price and value"
    if field == "avoid":
        return "avoid"
    if levels & {"positive", "very_positive"} and levels & {"negative", "very_negative"}:
        return "polarity: praise or knock"
    return "levels: other"


# ---------------------------------------------------------------- report
def report(paths=MP.Paths(), key_a_path=None, write=True):
    a = review_a(key_a_path)
    b, problems, key_b, items_b = review_b(paths)
    raw = J4.raw_outputs(key_b["runs_path"])
    rows_ctx = B4.rows_and_contexts()[0]
    per_field = collections.defaultdict(lambda: [0, 0])
    item_ok = collections.Counter()
    acc_a, acc_b = collections.Counter(), collections.Counter()
    groups = collections.defaultdict(list)
    catch = collections.defaultdict(lambda: [0, 0])
    unmatched = 0
    for cid, (fb, jb, shown_b, plant_b, iid_b) in sorted(b.items()):
        if cid not in a:
            unmatched += 1
            continue
        fa, ja, shown_a, plant_a, iid_a = a[cid]
        skip = _skip(plant_a) | _skip(plant_b)
        for name, field, va, vb, ok in compare_finals(fa, fb, skip):
            key = "dishes" if field.startswith("dish:") else field
            per_field[key][0] += ok
            per_field[key][1] += 1
            if not ok:
                it = items_b[iid_b]
                ra = next((c for c in ja.get("compare") or [] if J3.same(c.get("name"), name) and c.get("field") == field), {})
                rb = next((c for c in jb.get("compare") or [] if J3.same(c.get("name"), name) and c.get("field") == field), {})
                named_in = next((m.get("named_in") for m in shown_b if J3.same(m.get("name"), name)), None)
                groups[cause(field, va, vb, it["context"]["body"], it["context"]["title"], named_in)].append({
                    "item": iid_b, "first_review_item": iid_a, "comment_id": cid, "place": name, "field": field,
                    "A": va, "B": vb, "A_reason": ra.get("reason"), "B_reason": rb.get("reason"),
                    "title": it["context"]["title"], "comment": " ".join((it["context"]["body"] or "").split())[:300]})
        if not plant_a and not plant_b:
            item_ok["n"] += 1
            item_ok["agree"] += bool(ja.get("overall_item_ok")) == bool(jb.get("overall_item_ok"))
            item_ok["A_ok"] += bool(ja.get("overall_item_ok"))
            item_ok["B_ok"] += bool(jb.get("overall_item_ok"))
        out = B4.shown_form(raw.get(cid) or [])
        J4.score(out, fa, skip, acc_a)
        J4.score(out, fb, skip, acc_b)
        if plant_b:
            kind = plant_b["kind"]
            if kind == "drop_mention":
                hit = any(J3.same(n, plant_b["mention"]) for n, _ in fb)
            elif kind == "drop_dish":
                sm = next((m for m in shown_b if J3.same(m.get("name"), plant_b["mention"])), {})
                like = lambda ds: sum(J3.S.lenient_same(d, plant_b["field"][5:]) for d in ds)  # noqa: E731
                hit = any(J3.same(n, plant_b["mention"]) and like(f["dishes"]) > like([d["dish"] for d in sm.get("dishes") or []])
                          for n, f in fb)
            else:
                hit = any(J3.same(n, plant_b["mention"]) and f.get(plant_b["field"]) != plant_b["shown"] for n, f in fb)
            catch[kind][0] += hit
            catch[kind][1] += 1
    sa, sb = J4.summary(acc_a), J4.summary(acc_b)

    def pick(s):
        out = {k: s[k] for k in ("item_ok_rate", "mention_recall", "mention_precision", "negative_recall")}
        out.update({f: s["field_accuracy"][f]["acc"] for f in ACC_FIELDS})
        return out
    ha, hb = pick(sa), pick(sb)
    rep = {"items_compared": sum(1 for c in b if c in a), "items_in_b": len(b), "not_in_a": unmatched,
           "problems": problems[:100],
           "field_agreement": {f: {"agree": v[0], "n": v[1], "rate": round(v[0] / v[1], 3) if v[1] else None}
                               for f, v in sorted(per_field.items())},
           "item_ok_agreement": {"n": item_ok["n"], "agree": item_ok["agree"],
                                 "rate": round(item_ok["agree"] / item_ok["n"], 3) if item_ok["n"] else None,
                                 "A_ok": item_ok["A_ok"], "B_ok": item_ok["B_ok"]},
           "haiku_under_A": ha, "haiku_under_B": hb,
           "haiku_difference_B_minus_A": {k: (round(hb[k] - ha[k], 3) if ha[k] is not None and hb[k] is not None else None)
                                          for k in ha},
           "planted_catch_rate_B": {k: {"caught": v[0], "n": v[1]} for k, v in sorted(catch.items())},
           "planted_catch_rate_B_all": round(sum(v[0] for v in catch.values()) / sum(v[1] for v in catch.values()), 3)
           if catch else None,
           "disagreements_by_cause": {k: v for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))}}
    if write:
        with open(os.path.join(paths.base, "agreement.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        with open(os.path.join(paths.base, "agreement.md"), "w", encoding="utf-8") as f:
            f.write(markdown(rep))
    return rep


def markdown(rep):
    L = ["# Judge agreement: a second review of 150 fresh comments (round 4, medium)", "",
         f"Items compared: {rep['items_compared']} of {rep['items_in_b']} judged in the second review.", "",
         "## 1. Field agreement (final values, A against B)", "", "| field | agree | n | rate |", "|---|---:|---:|---:|"]
    L += [f"| {f} | {v['agree']} | {v['n']} | {v['rate']} |" for f, v in rep["field_agreement"].items()]
    io = rep["item_ok_agreement"]
    L += ["", "## 2. Item verdict (overall_item_ok)", "",
          f"Agree on {io['agree']} of {io['n']} unplanted items ({io['rate']}); A called {io['A_ok']} fully right, "
          f"B {io['B_ok']}.", "",
          "## 3. Haiku's accuracy under each review (the error bar)", "", "| metric | under A | under B | B − A |",
          "|---|---:|---:|---:|"]
    L += [f"| {k} | {rep['haiku_under_A'][k]} | {rep['haiku_under_B'][k]} | {rep['haiku_difference_B_minus_A'][k]} |"
          for k in rep["haiku_under_A"]]
    L += ["", f"## 4. Planted changes caught by B: {rep['planted_catch_rate_B_all']} "
          f"{json.dumps(rep['planted_catch_rate_B'])}", "", "## 5. Disagreements by cause", ""]
    for c, lst in rep["disagreements_by_cause"].items():
        L += [f"### {c} ({len(lst)})", ""]
        for d in lst:
            L.append(f"- {d['item']} / {d['first_review_item']} **{d['place']}** `{d['field']}`: A {json.dumps(d['A'])}, "
                     f"B {json.dumps(d['B'])}. Title: {d['title']!r}. Comment: \"{d['comment']}\"")
            if d["A_reason"] or d["B_reason"]:
                L.append(f"  - A: {d['A_reason'] or '(agreed with Haiku)'}; B: {d['B_reason'] or '(agreed with Haiku)'}")
        L.append("")
    if rep["problems"]:
        L += ["## Checker problems", ""] + [f"- {p}" for p in rep["problems"]]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- self-test
def judgment_with(finals, it):
    """A valid judgment whose final values are exactly `finals` for the item's shown output."""
    shown = it["shown"]
    own, compare, missed = [], [], []
    for name, f in finals:
        m = {"name": name, "overall": f["overall"],
             "aspects": {x: f[f"aspects.{x}"] for x in B4.ASPECTS}, "experience": f["experience"],
             "opinion": f["opinion"], "avoid": f["avoid"], "timeframe": f["timeframe"], "trend": f["trend"],
             "status": f["status"], "dishes": [{"dish": d, **v} for d, v in f["dishes"].items()]}
        own.append(m)
        s = next((x for x in shown if J3.same(x.get("name"), name)), None)
        if s is None:
            compare.append({"name": name, "field": "_mention", "haiku": None, "own": "present", "final": "present",
                            "right": "judge", "reason": "t"})
            missed.append(m)
            continue
        if J3.get(s, "price") != f["price"]:
            compare.append({"name": name, "field": "price", "haiku": J3.get(s, "price"), "own": None,
                            "final": f["price"], "right": "judge", "reason": "t"})
    for name, fld, hv, ov in J4.diffs(own, shown):
        if fld == "_mention" and ov is None:
            compare.append({"name": name, "field": "_mention", "haiku": "present", "own": None, "final": None,
                            "right": "judge", "reason": "t"})
        elif fld != "_mention":
            compare.append({"name": name, "field": fld, "haiku": hv, "own": ov, "final": ov, "right": "judge",
                            "reason": "t"})
    ok = not compare
    return {"item_id": it["item_id"], "comment_id": it["comment_id"], "own_read": own, "compare": compare,
            "missed": missed, "notes_grade": [], "rule_questions": [], "overall_item_ok": ok}


def self_test():
    """Build the packets into a temp dir from the real first review, then judge them twice:
    a clone of review A (agreement must be 1.0 on every field, the error bar 0, and every
    plant caught where A's final differs from the planted value), and a judge that copies
    Haiku's output (catches no plant). Both must pass review_v6r4's checker."""
    tmp = tempfile.mkdtemp()
    try:
        paths = MP.Paths(tmp)
        s = MP.build(paths, quiet=True)
        assert s["items"] == 150 and len(s["packets"]) == 6 and s["planted"] == 9, s
        assert all(n.startswith("r2_") for n in s["packets"])
        src = open(os.path.join(A_DIR, "RUBRIC.md"), encoding="utf-8").read()
        new = open(paths.rubric, encoding="utf-8").read()
        rules = src.index("## The rules are the prompt's")
        assert new.endswith(src[rules:].replace("`eval/review_v6r4/judgments/pNNN.jsonl`",
                                                "`eval/review_v6r4_rejudge/judgments/r2_NNN.jsonl`")), "rubric drifted"
        a = review_a()
        key_b = json.load(open(paths.key))
        ids_a = {v[4] for v in a.values()}
        assert not ids_a & set(key_b["items"]), "item ids must not map to the first review"
        for mode in ("clone_of_A", "copies_haiku"):
            paths.judgments = os.path.join(tmp, "j_" + mode)
            os.makedirs(paths.judgments)
            for name, its in J4.packets(paths).items():
                with open(os.path.join(paths.judgments, name + ".jsonl"), "w") as f:
                    for it in its:
                        fin = a[it["comment_id"]][0] if mode == "clone_of_A" else \
                            [(m["name"], B4.place_fields(m)) for m in it["shown"]]
                        f.write(json.dumps(judgment_with(fin, it)) + "\n")
            rep = report(paths, write=False)
            assert not rep["problems"], rep["problems"][:5]
            assert rep["items_compared"] == 150, rep["items_compared"]
            if mode == "clone_of_A":
                bad = {f: v for f, v in rep["field_agreement"].items() if v["rate"] != 1.0}
                assert not bad, bad
                assert all(v in (0, 0.0, None) for v in rep["haiku_difference_B_minus_A"].values()), rep["haiku_difference_B_minus_A"]
                assert not rep["disagreements_by_cause"]
            else:
                assert rep["planted_catch_rate_B_all"] == 0.0, rep["planted_catch_rate_B"]
                assert rep["haiku_under_B"]["item_ok_rate"] == 1.0
                assert sum(len(v) for v in rep["disagreements_by_cause"].values()) > 0
            print(f"self-test {mode}: catch {rep['planted_catch_rate_B_all']}, item_ok agreement "
                  f"{rep['item_ok_agreement']['rate']}, disagreements "
                  f"{sum(len(v) for v in rep['disagreements_by_cause'].values())} in "
                  f"{len(rep['disagreements_by_cause'])} causes")
        print("rejudge self-test ok")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    paths = MP.Paths()
    if cmd == "self-test":
        return self_test()
    if cmd == "check":
        got, problems, items = J4.read(paths)
        print(f"{len(got)} of {len(items)} items judged, {len(problems)} problem(s)")
        for p in problems[:100]:
            print("  " + p)
        sys.exit(1 if problems or len(got) < len(items) else 0)
    if cmd == "report":
        rep = report(paths)
        print(json.dumps({k: rep[k] for k in ("items_compared", "item_ok_agreement", "planted_catch_rate_B_all")}))


if __name__ == "__main__":
    main()
