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
Measured on round 3, scored fields the rule fixed / broke against the round-3 judges'
finals (dish entries counted apart). Patterns are matched only around the place's name
(150 characters before, 350 after; the whole comment for a context-named place), plus the
parent for an agreement reply, and the superlative and extreme lists are the prompt's own.

  rule                          what it does                                     fixed broken
  endorse_positive              endorse with overall null -> positive (owner rule;   1      0  kept
                                never overrides a set overall)
  very_needs_word               very_* with no superlative or extreme word near     49     24  kept
                                the name -> one step down (+5 dish levels)
  none_to_firsthand             experience none on a stated or endorse mention ->   31      9  kept
                                firsthand, unless untried words are near the name
  secondhand_needs_credit       secondhand with no credit word -> firsthand (none   24      4  kept
                                when opinion is none)
  lone_aspect_overall           stated, overall null, one non-wait aspect (and its  20      2  kept
                                dishes), one sign, no untried words -> overall
  opinion_none_experience_none  opinion none -> experience none (the prompt's rule)   4      7  dropped
  closed_past                   status closed, no branch location -> past            1      2  dropped
  note_dish                     a dish only in a note -> a dish entry                0      0  dropped
  stated_all_null_none          stated with nothing leveled -> opinion none          3      2  dropped
  avoid_positive                avoid true with overall positive                 flag only (1 flagged, 1 real)
  kind_excluded                 kind grocery, brand, venue, company, other -> out   round 4 only

The five kept together: 125 fields fixed, 39 broken, 91 more right fields (overall +31,
experience +42). The finals are the old rubric's: 16 of very_needs_word's 24 "breaks" are
levels the owner's round-4 calibration moves to the validator's answer ("terrible", "sucks",
"an abomination", "best on the UES", the asker's "best"), so under the new rubric it does
better than measured. The two dropped rules that follow round-4 rules (experience none for
no opinion, closed means past) lose against the old finals; re-measure them on round 4's.
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

# The words that let a very_* level stand: the prompt's own lists (v6_common.SCALE),
# superlative_praise and extreme_knock, written as patterns. Nothing beyond them: the
# prompt calls "vile", "stay away" or "an abomination" a knock, so they don't count.
BROAD = r"(the )?(city|nyc|ny|new york|town|the world|the country|the us|america|the states)"
SUPERLATIVE = re.compile(
    r"\b(best|greatest|top)\b[^.!?\n]{0,40}\b(in|of) " + BROAD + r"\b|"
    r"\b(nyc|new york|the city)'?s? (best|greatest|top)\b|"
    r"\b(best|greatest)\b[^.!?\n]{0,40}\b(i'?ve|i have|i) ever\b|\bever (had|eaten|tasted)\b|"
    r"\bfavou?rite\b[^.!?\n]{0,30}\bin " + BROAD + r"\b|"
    r"\bof my life\b|\bbest [^.!?\n]{0,30}anywhere\b|"
    r"\bnothing (else )?(in \w+ )?(comes close|compares)\b|"
    r"\bno(where| one) (else )?(in \w+ )?(comes close|compares|does it better)\b", re.I)
# "worst" against anything ("some of the worst ribs") is the prompt's worst-I've-had; "the
# worst part is" is not a verdict.
EXTREME = re.compile(
    r"\bworst\b(?! (part|thing about|case|time to))|"
    r"\binedible\b|\bdisgusting\b|\bgot (really |so )?sick\b|\bfood poisoning\b|\bavoid (it |this place )?at all costs\b", re.I)
UNTRIED = re.compile(
    r"never been|haven't (ever |even )?(been|tried|eaten)(?! in a while| lately| in)|have not been|never tried|"
    r"\blook(s|ed)?\b(?! like)|\bsounds?\b|bucket list|never go\b|"
    r"(want|wanna|gonna|going|have|got) to (try|check)|wanna try|gotta try|will (try|check)|can't wait|"
    r"\bsaved\b|bookmark|on my list|been meaning|first time (going|trying)|\bthanks?\b|thank you", re.I)
CREDIT = re.compile(r"\b(friends?|heard|hear|people|apparently|reviews?|say|says|said|told|according|supposedly|"
                    r"word is|reddit(ors)?|they say|my (wife|husband|partner|bf|gf|boyfriend|girlfriend|sister|"
                    r"brother|mom|mother|dad|father|coworkers?|colleagues?|family|roommates?|cousin|son|daughter|"
                    r"kids?)|rumou?r)\b", re.I)
AGREE = re.compile(r"^\W*(this|\+1|agreed?|same|exactly|seconded|second(ed)? this|so true|yes+|100%|facts|truth|"
                   r"this is the (way|answer)|came here to say)\b", re.I)
SENT = re.compile(r"(?<=[.!?\n])\s+")
SHORT_NAME_WORDS = {"the", "a", "an", "and", "of", "on", "in", "at", "nyc", "cafe", "bar", "pizza", "deli", "bakery",
                    "restaurant", "house", "kitchen", "place", "shop", "grill"}


class Ctx:
    """What a rule may look at: the comment, the parent (for agreement replies), and for
    each mention the part of the comment that is about it."""

    def __init__(self, comment, parent=None):
        # curly apostrophes (Reddit's mobile keyboards) would hide "haven't" from the patterns
        self.comment = (comment or "").replace("\u2019", "'").replace("\u2018", "'")
        self.parent = (parent or "").replace("\u2019", "'").replace("\u2018", "'")
        self.agreement = bool(AGREE.search(self.comment)) and len(self.comment) < 120
        self.sentences = [s for s in SENT.split(self.comment) if s.strip()]

    def scope(self, m):
        """The comment around each place the mention's name appears (150 characters before,
        350 after), else the whole comment (a context-named place, or a name the comment
        spells differently); plus the parent for an agreement reply, which takes the parent's
        verdict."""
        words = [w for w in re.findall(r"[a-z0-9']+", (m.get("name") or "").lower())
                 if len(w) >= 3 and w not in SHORT_NAME_WORDS]
        low = self.comment.lower()
        spans = [(max(0, x.start() - 150), x.end() + 350) for w in words for x in re.finditer(re.escape(w), low)]
        if spans and m.get("named_in") != "context":
            text = " ... ".join(self.comment[a:b] for a, b in sorted(spans))
        else:
            text = self.comment
        return text + ("\n" + self.parent if self.agreement else "")


def _very(level, text):
    if level == "very_positive" and not SUPERLATIVE.search(text):
        return "positive"
    if level == "very_negative" and not EXTREME.search(text):
        return "negative"
    return level


def r_endorse_positive(m, ctx):
    """Owner rule: an endorsement is praise. Only fills a missing overall; never overrides one."""
    if m.get("opinion") == "endorse" and m.get("overall") is None:
        return {"overall": "positive"}


def r_very_needs_word(m, ctx):
    text = ctx.scope(m)
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


def r_none_to_firsthand(m, ctx):
    if m.get("experience") == "none" and m.get("opinion") in ("stated", "endorse") \
            and not UNTRIED.search(ctx.scope(m)):
        return {"experience": "firsthand"}


def r_secondhand_needs_credit(m, ctx):
    if m.get("experience") == "secondhand" and not CREDIT.search(ctx.comment):
        return {"experience": "none" if m.get("opinion") == "none" else "firsthand"}


def r_opinion_none_experience_none(m, ctx):
    """The prompt's rule: a mention with no opinion has experience none."""
    if m.get("opinion") == "none" and m.get("experience") != "none":
        return {"experience": "none"}


def r_closed_past(m, ctx):
    """Closed means the whole place; a status with a branch location is a branch closing,
    which the prompt says leaves status null, so it doesn't move timeframe."""
    if m.get("status") == "closed" and m.get("timeframe") != "past" and not m.get("location"):
        return {"timeframe": "past"}


def r_note_dish(m, ctx):
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


def r_stated_all_null_none(m, ctx):
    if m.get("opinion") == "stated" and not m.get("overall") and not _levels(m):
        return {"opinion": "none"}


STRENGTH = {"very_positive": 2, "positive": 1, "neutral": 0, "negative": -1, "very_negative": -2}


def r_lone_aspect_overall(m, ctx):
    """The owner's rule: a lone taste, value, service or atmosphere verdict (a dish verdict is
    taste) sets overall; the wait never does. Only a truly lone verdict: one non-wait aspect
    (with the dishes behind it, if any), all one sign, and no untried words near the name, so
    a reaction to a photo or a second misread aspect is never lifted into overall."""
    if m.get("opinion") != "stated" or m.get("overall") or UNTRIED.search(ctx.scope(m)):
        return None
    asp = {a: v for a, v in (m.get("aspects") or {}).items() if v and a != "wait"}
    dish = [d.get("level") for d in m.get("dishes") or [] if d.get("level")]
    if len(asp) > 1 or (dish and set(asp) - {"taste"}):
        return None
    vals = list(asp.values()) + dish
    if not vals:
        return None
    signs = {(STRENGTH[v] > 0) - (STRENGTH[v] < 0) for v in vals}
    if len(signs) != 1 or 0 in signs:
        return None
    best = max(vals, key=lambda v: abs(STRENGTH[v]))
    return {"overall": {"very_positive": "positive", "very_negative": "negative"}.get(best, best)}


def f_avoid_positive(m, ctx):
    return bool(m.get("avoid")) and m.get("overall") in POS


RULES = {"endorse_positive": r_endorse_positive, "very_needs_word": r_very_needs_word,
         "none_to_firsthand": r_none_to_firsthand, "secondhand_needs_credit": r_secondhand_needs_credit,
         "opinion_none_experience_none": r_opinion_none_experience_none,
         "closed_past": r_closed_past, "note_dish": r_note_dish, "stated_all_null_none": r_stated_all_null_none,
         "lone_aspect_overall": r_lone_aspect_overall}
FLAGS = {"avoid_positive": f_avoid_positive}
# Kept after measurement on round 3 (see the docstring and eval/review_v6/validators.json).
DEFAULT = ("endorse_positive", "very_needs_word", "none_to_firsthand", "secondhand_needs_credit",
           "lone_aspect_overall")


def _set(m, field, value):
    if field.startswith("aspects."):
        m["aspects"] = dict(m.get("aspects") or {}, **{field.split(".", 1)[1]: value})
    else:
        m[field] = value


def apply(mentions, comment_text, rules=DEFAULT, drop_excluded=True, parent_text=None):
    """(new mentions, {rule: [(mention name, field, old, new)]}, flags) for one comment's output.
    Mentions are normalized to the owner's level names first (v6_adapter.normalize).
    parent_text is the parent comment, read only for an agreement reply ("+1", "this")."""
    ctx = Ctx(comment_text, parent_text)
    out, changes, flags = [], collections.defaultdict(list), collections.defaultdict(list)
    for m in mentions or []:
        if not isinstance(m, dict):
            continue
        m = copy.deepcopy(A.normalize(m))
        if drop_excluded and not A.counted(m):
            changes["kind_excluded"].append((m.get("name"), "_mention", "present", None))
            continue
        for name in rules:
            ch = RULES[name](m, ctx) or {}
            for field, value in ch.items():
                old = m.get(field) if not field.startswith("aspects.") else (m.get("aspects") or {}).get(field[8:])
                changes[name].append((m.get("name"), field, old, value))
                _set(m, field, value)
        for name, f in FLAGS.items():
            if f(m, ctx):
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

    def parent_of(it):
        anc = (it["context"] or {}).get("ancestors") or []
        return (anc[-1].get("body") or "") if anc else ""

    cases = []
    for iid, j in got.items():
        if iid in key:
            continue
        cases.append((items[iid], J.final_places(j, shown[iid]), shown[iid]))

    def total(rules):
        acc = collections.defaultdict(lambda: [0, 0])
        changed = 0
        for it, finals, ms in cases:
            new, ch, _ = apply(ms, text_of(it), rules, drop_excluded=False, parent_text=parent_of(it))
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
            new, ch, _ = apply(ms, text_of(it), rules, drop_excluded=False, parent_text=parent_of(it))
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
        _, _, fl = apply(ms, text_of(it), (), drop_excluded=False, parent_text=parent_of(it))
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
