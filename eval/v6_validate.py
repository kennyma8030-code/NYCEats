"""Deterministic checks applied to v6 output after extraction, and their measurement.

    python eval/v6_validate.py measure      # each rule on round 3's output vs the Opus finals
                                            # -> eval/review_v6/validators.json

What code can enforce, code should, rather than hoping a small model at low effort
follows a rule every time. Each rule rewrites one field of one mention from evidence
in the mention and the comment's own words, or only flags it; nothing here invents a
place. Stored output is never touched: apply() returns new mention dicts, so run files
keep the model's raw answer and a result can always be reported with and without
validators.

Every rule was measured on the 542 real items of the round-3 review (eval/review_v6),
against the judges' final values, before it was allowed into DEFAULT: a rule is kept
only when the fields it fixes clearly outnumber the fields it breaks. The table, from
`measure`, is in eval/review_v6/validators.json; the reasons are next to each rule.
Measured on round 3, scored fields the rule fixed / broke (dish entries counted apart):

  rule                     what it does                                          fixed broken
  endorse_positive         endorse -> overall positive (owner rule)                  1      0  kept
  very_needs_word          very_* with no superlative or extreme word in the        40     13  kept
                           comment -> one step down (+7 dish levels)
  none_to_firsthand        experience none on a stated or endorse mention ->        28      7  kept
                           firsthand, unless the comment has untried words
  secondhand_needs_credit  secondhand with no credit word -> firsthand              22      4  kept
  closed_past              status closed -> timeframe past                           5      2  kept
  lone_aspect_overall      stated, overall null, one-signed non-wait aspects or     24      2  kept
                           dish levels -> overall (the owner's lone-verdict rule)
  note_dish                a dish only in a note -> a dish entry                     0      0  dropped: +2 dish
                           (round 4's notes have no dish slot anyway)                            entries, no field
  stated_all_null_none     stated with nothing leveled -> opinion none               3      2  dropped: no clear gain
  avoid_positive           avoid true with overall positive                      flag only (1 flagged, 1 real)
  kind_excluded            kind grocery, brand, venue, company, other -> out     round 4 only (round 3 has no kind)

All six kept together: 120 fields fixed, 28 broken, 99 more right fields (overall +37,
experience +39). Most of very_needs_word's "breaks" are knocks the round-3 judges
called very_negative under the old calibration ("terrible", "sucks"), which the owner's
round-4 decision makes negative; under the new rubric the rule is better than measured.
"""

import collections
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v6_adapter as A  # noqa: E402

POS, NEG = ("very_positive", "positive"), ("very_negative", "negative")
ASPECTS = ("taste", "value", "service", "atmosphere", "wait")

# Words that let a very_* level stand. The owner's tests: a superlative against the
# whole city or wider, or an extreme (worst, inedible, disgusting, got sick, avoid at
# all costs). The check is deliberately loose (any such word anywhere in the comment):
# it only removes very_* levels that have no basis at all.
SUPERLATIVE = re.compile(r"\b(best|greatest|favou?rites?( \w+){0,3} (in|of)|number one|#1|top (spot|pick) in|of my life|"
                         r"ever (had|eaten|tasted)|i'?ve ever|nothing (else )?(in \w+ )?(comes close|compares)|"
                         r"no(where| one) (else )?(comes close|compares|does it better)|unmatched|unrivaled|"
                         r"goat|best of the best)\b", re.I)
EXTREME = re.compile(r"\b(worst|inedible|disgusting|vile|got sick|food poisoning|poison(ed|ing)?|threw up|"
                     r"vomit\w*|avoid (it )?at all costs|stay away|roach(es)?|rats?|mice|bugs? in|hair in|"
                     r"inexcusable|abomination)\b", re.I)
UNTRIED = re.compile(r"(never been|haven'?t (ever |even )?(been|tried|eaten|gone)|have not been|never tried|not tried|"
                     r"\blooks?\b|\blooked\b|\bsounds?\b|bucket list|never go|"
                     r"(want|wanna|gonna|going|need|have|got) to (try|go|check)|wanna try|gotta try|will (try|check)|"
                     r"can'?t wait|saved|bookmark|on my list|"
                     r"been meaning|thanks|thank you|planning|plan to|next time i'?m|added to)", re.I)
CREDIT = re.compile(r"\b(friends?|heard|hear|people|apparently|reviews?|say|says|said|told|according|supposedly|"
                    r"word is|reddit(ors)?|they say|my (wife|husband|partner|bf|gf|boyfriend|girlfriend|sister|"
                    r"brother|mom|mother|dad|father|coworkers?|colleagues?|family|roommates?|cousin|son|daughter|"
                    r"kids?)|rumou?r)\b", re.I)


def _very(level, text):
    if level == "very_positive" and not SUPERLATIVE.search(text):
        return "positive"
    if level == "very_negative" and not EXTREME.search(text):
        return "negative"
    return level


def r_endorse_positive(m, text):
    if m.get("opinion") == "endorse" and m.get("overall") != "positive":
        return {"overall": "positive"}


def r_very_needs_word(m, text):
    ch = {}
    if _very(m.get("overall"), text) != m.get("overall"):
        ch["overall"] = _very(m["overall"], text)
    for a in ASPECTS:
        v = (m.get("aspects") or {}).get(a)
        if _very(v, text) != v:
            ch[f"aspects.{a}"] = _very(v, text)
    dishes = m.get("dishes") or []
    if any(_very(d.get("level"), text) != d.get("level") for d in dishes):
        ch["dishes"] = [dict(d, level=_very(d.get("level"), text)) for d in dishes]
    return ch


def r_none_to_firsthand(m, text):
    if m.get("experience") == "none" and m.get("opinion") in ("stated", "endorse") and not UNTRIED.search(text):
        return {"experience": "firsthand"}


def r_secondhand_needs_credit(m, text):
    if m.get("experience") == "secondhand" and not CREDIT.search(text):
        return {"experience": "firsthand"}


def r_closed_past(m, text):
    if m.get("status") == "closed" and m.get("timeframe") != "past":
        return {"timeframe": "past"}


def r_note_dish(m, text):
    have = {(d.get("dish") or "").lower() for d in m.get("dishes") or []}
    add = []
    for n in m.get("notes") or []:
        dish = n.get("dish") if isinstance(n, dict) else None
        if dish and dish.lower() not in have and not any(dish.lower() in h or h in dish.lower() for h in have if h):
            add.append({"dish": dish, "level": n.get("level"), "avoid": False})
            have.add(dish.lower())
    if add:
        return {"dishes": (m.get("dishes") or []) + add}


def _levels(m):
    return [v for v in (m.get("aspects") or {}).values() if v] + [d.get("level") for d in m.get("dishes") or [] if d.get("level")]


def r_stated_all_null_none(m, text):
    if m.get("opinion") == "stated" and not m.get("overall") and not _levels(m):
        return {"opinion": "none"}


STRENGTH = {"very_positive": 2, "positive": 1, "neutral": 0, "negative": -1, "very_negative": -2}


def r_lone_aspect_overall(m, text):
    """The owner's rule: a lone taste, value, service or atmosphere verdict (a dish verdict is
    taste) sets overall; a wait-only remark does not."""
    if m.get("opinion") != "stated" or m.get("overall"):
        return None
    vals = [v for a, v in (m.get("aspects") or {}).items() if v and a != "wait"]
    vals += [d.get("level") for d in m.get("dishes") or [] if d.get("level")]
    if not vals:
        return None
    signs = {(STRENGTH[v] > 0) - (STRENGTH[v] < 0) for v in vals}
    if len(signs) != 1 or 0 in signs:
        return None
    # the strongest of them, but never an extreme for overall from one dish
    best = max(vals, key=lambda v: abs(STRENGTH[v]))
    return {"overall": {"very_positive": "positive", "very_negative": "negative"}.get(best, best)}


def f_avoid_positive(m, text):
    return bool(m.get("avoid")) and m.get("overall") in POS


RULES = {"endorse_positive": r_endorse_positive, "very_needs_word": r_very_needs_word,
         "none_to_firsthand": r_none_to_firsthand, "secondhand_needs_credit": r_secondhand_needs_credit,
         "closed_past": r_closed_past, "note_dish": r_note_dish, "stated_all_null_none": r_stated_all_null_none,
         "lone_aspect_overall": r_lone_aspect_overall}
FLAGS = {"avoid_positive": f_avoid_positive}
# Kept after measurement on round 3 (see the docstring and eval/review_v6/validators.json).
DEFAULT = ("endorse_positive", "very_needs_word", "none_to_firsthand", "secondhand_needs_credit",
           "closed_past", "lone_aspect_overall")


def _set(m, field, value):
    if field.startswith("aspects."):
        m["aspects"] = dict(m.get("aspects") or {}, **{field.split(".", 1)[1]: value})
    else:
        m[field] = value


def apply(mentions, comment_text, rules=DEFAULT, drop_excluded=True):
    """(new mentions, {rule: [(mention name, field, old, new)]}, flags) for one comment's output.
    Mentions are normalized to the owner's level names first (v6_adapter.normalize)."""
    out, changes, flags = [], collections.defaultdict(list), collections.defaultdict(list)
    for m in mentions or []:
        if not isinstance(m, dict):
            continue
        m = copy.deepcopy(A.normalize(m))
        if drop_excluded and not A.counted(m):
            changes["kind_excluded"].append((m.get("name"), "_mention", "present", None))
            continue
        for name in rules:
            ch = RULES[name](m, comment_text or "") or {}
            for field, value in ch.items():
                old = m.get(field) if not field.startswith("aspects.") else (m.get("aspects") or {}).get(field[8:])
                changes[name].append((m.get("name"), field, old, value))
                _set(m, field, value)
        for name, f in FLAGS.items():
            if f(m, comment_text or ""):
                flags[name].append(m.get("name"))
        out.append(m)
    return out, dict(changes), dict(flags)


# ---------------------------------------------------------------- measurement
def measure():
    """Each rule alone, then DEFAULT together, on round 3's real (unplanted) review items:
    for every place both the output and the judges' final have, count scored fields the
    rule turns right and fields it turns wrong."""
    sys.path.insert(0, os.path.join(HERE, "review_v6"))
    import judgments as J
    got, problems, shown = J.read()
    key = json.load(open(J.KEY)) if os.path.exists(J.KEY) else {}
    items = {it["item_id"]: it for v in J.packets().values() for it in v}
    fields = J.SCORED + ["timeframe"]

    def score(ms, finals):
        """{field: [right, n]} over places matched to a final, plus dish entries."""
        acc = collections.defaultdict(lambda: [0, 0])
        for name, fin, s, o in finals:
            m = next((x for x in ms if J.same(x.get("name"), name)), None)
            if m is None:
                continue
            for f in fields:
                acc[f][0] += J.get(m, f) == fin.get(f)
                acc[f][1] += 1
            md = {d["dish"]: J.dval(d) for d in m.get("dishes") or []}
            for dn, v in fin["dishes"].items():
                hv = next((x for d, x in md.items() if J.S.lenient_same(d, dn)), None)
                acc["dishes"][0] += hv == v
                acc["dishes"][1] += 1
        return acc

    def text_of(it):
        return (it["context"] or {}).get("body") or ""

    cases = []
    for iid, j in got.items():
        if iid in key:
            continue
        cases.append((items[iid], J.final_places(j, shown[iid]), shown[iid]))

    def total(rules):
        acc = collections.defaultdict(lambda: [0, 0])
        changed = 0
        for it, finals, ms in cases:
            new, ch, _ = apply(ms, text_of(it), rules, drop_excluded=False)
            changed += sum(len(v) for v in ch.values())
            for f, (a, n) in score(new, finals).items():
                acc[f][0] += a
                acc[f][1] += n
        return acc, changed

    base, _ = total(())
    report = {"items": len(cases), "baseline": {f: round(a / n, 4) for f, (a, n) in sorted(base.items()) if n}, "rules": {}}
    for name in list(RULES) + ["DEFAULT"]:
        rules = DEFAULT if name == "DEFAULT" else (name,)
        acc, changed = total(rules)
        delta = {f: acc[f][0] - base[f][0] for f in base if acc[f][0] != base[f][0]}
        # fixed / broken, counted per field change
        fixed = broken = 0
        for it, finals, ms in cases:
            new, ch, _ = apply(ms, text_of(it), rules, drop_excluded=False)
            for mname, field, old, value in [c for v in ch.values() for c in v]:
                fin = next((fn for n, fn, _, _ in finals if J.same(n, mname)), None)
                if fin is None:
                    continue
                if field == "dishes":
                    continue
                want = fin.get(field)
                fixed += old != want and value == want
                broken += old == want and value != want
        report["rules"][name] = {"field_changes": changed, "fixed": fixed, "broken": broken,
                                 "net_right_fields": sum(delta.values()), "delta_by_field": delta,
                                 "accuracy_after": {f: round(acc[f][0] / acc[f][1], 4) for f in sorted(acc) if acc[f][1]}}
    flags = collections.Counter()
    flag_right = collections.Counter()
    for it, finals, ms in cases:
        _, _, fl = apply(ms, text_of(it), (), drop_excluded=False)
        for name, names in fl.items():
            for mname in names:
                flags[name] += 1
                fin = next((fn for n, fn, _, _ in finals if J.same(n, mname)), None)
                flag_right[name] += bool(fin) and not (fin.get("avoid") and fin.get("overall") in POS)
    report["flags"] = {k: {"flagged": flags[k], "flag_was_a_real_error": flag_right[k]} for k in flags}
    report["note"] = ("Finals are the round-3 judges' (the rubric before the owner's round-4 decisions). Rules "
                      "that follow a round-4 decision the old finals don't (lone_aspect_overall's wait exception) "
                      "are measured against the old rubric, so their gain is a floor. kind_excluded can't be "
                      "measured on round 3: its output has no kind.")
    path = os.path.join(HERE, "review_v6", "validators.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(f"{report['items']} items; written {path}")
    print(f"{'rule':26s} {'changes':>7s} {'fixed':>6s} {'broken':>6s} {'net':>5s}")
    for name, r in report["rules"].items():
        print(f"{name:26s} {r['field_changes']:7d} {r['fixed']:6d} {r['broken']:6d} {r['net_right_fields']:5d}  {r['delta_by_field']}")
    print("flags", report["flags"])
    return report


if __name__ == "__main__":
    if sys.argv[1:] == ["measure"]:
        measure()
    else:
        print(__doc__)
