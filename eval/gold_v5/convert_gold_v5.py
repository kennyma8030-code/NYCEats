"""Convert the v1 and v2 gold to the v5 schema.

    python eval/gold_v5/convert_gold_v5.py    # writes eval/v1/gold_v5.jsonl and eval/v2/gold_v5.jsonl
    python eval/gold_v5/convert_gold_v5.py --check    # validate the written files only

The blind v1/v2 labels are never edited. This script maps them to v5 with the
fixed rules below, then applies the hand decisions in gold_v5/overrides.py
then applies the provisional conventions. gold_v5/threads.py records how
each judgment-carrying thread was classified; its per-mention results are
entries in overrides.py. Every
output mention records which convention decided a field and what the field
would be without it, so a convention can be reversed with a query.

Mechanical rules
----------------
- Aspects: level -3..3 becomes awful, bad, meh, mixed, decent, good, rave.
  Alternatives map the same way; null stays null.
- Bare endorsement: an old food +1 with no other aspect is a name given as an
  answer with nothing said ("named as an answer means food +1" in the v1
  rules). It becomes food null, reference_only false, experience unclear.
  A food +1 that came with a dish verdict is not bare: the review decided
  each one.
  Old food +1 was also used for mild judgments ("solid", "looks good"); the
  review re-read every one and overrides.py restores those to "decent".
  "decent" is dropped from a bare mention's food alternatives, because v5
  never invents a food score for a bare name.
- Old rule 2 listed food +1 as an accepted alternative when another aspect
  was scored; that alternative is dropped for the same reason.
- reference_only: true for a closed place, and for a mention with every
  aspect null, no dish verdict and no avoid (the v1 rules gave every bare
  answer +1, so an all-null mention was a reference). The review checked these.
- experience: is_firsthand true is ate_there, false is secondhand, null is
  unclear. A bare endorsement is unclear (v1 defaulted bare recs to true).
- Dishes: a dish level above 0 is liked; below 0, or marked avoid, is
  disliked; null or 0 is mentioned (v5 has no mixed-dish list). On a
  reference-only mention every dish is mentioned.
- price, from the 7-point expensiveness: -3 and -2 are cheap, -1 is cheap
  (moderate accepted), 0 is moderate, +1 is pricey (moderate accepted), +2 is
  pricey (very_pricey accepted), +3 is very_pricey. The review nulls a price
  that came only from a dollar figure (convention 7).
- descriptors: the old descriptors plus the old search_terms that are not
  part of a dish name. Gold descriptors are a recall target for lenient
  matching, not an exhaustive list, so descriptor precision is not scorable.

Provisional conventions (relayed by the orchestrator from the prompt worker,
not yet confirmed with the user). Each sets `conventions[id]` to the values
the fields would have without it:
- c1: when a comment gives no overall food verdict, food takes the dishes'
  own level, or "mixed" when liked and disliked dishes disagree. A disliked
  dish counts as at most meh. A liked dish with no v1 level is taken as good
  and also tagged c1_assumed. Other aspects (value, the wait) do not stop it.
- c2: an avoid with no negative aspect gets food "bad". Avoids for a reason
  that is not about quality (politics, the asker's diet) are also tagged
  c2_nonquality, so they can be flipped on their own.
- c3: a verdict in the commenter's own voice is ate_there unless they say
  they haven't been. Bare names, questions and facts stay unclear.
- c4: bare "not worth it" given as advice is an avoid (is_negated true);
  "not worth the price / the line / the hype" names what fails (value bad,
  wait bad, food meh) and is not an avoid. Applied by hand in overrides.py;
  the tag records the opposite is_negated reading.

Convention 4 as first relayed (a judgment-carrying question applied at a
"plain level") was corrected: the question is scored at the level its own
words carry ("worst service" is service awful, "most overrated" food meh,
"biggest letdown" food bad). It is not tagged; rule 2 decides it.

Kept metadata beyond the v5 fields: search_terms and closed, so the old
search-terms and closed-place recalls stay computable.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
import overrides as ov  # noqa: E402

LEVEL = {3: "rave", 2: "good", 1: "decent", 0: "mixed", -1: "meh", -2: "bad", -3: "awful"}
LABELS = set(LEVEL.values())
NEGATIVE = {"meh", "bad", "awful"}
ASPECTS = ("food", "value", "service", "atmosphere", "wait")
PRICES = ("cheap", "moderate", "pricey", "very_pricey")
PRICE = {-3: ("cheap", []), -2: ("cheap", []), -1: ("cheap", ["moderate"]), 0: ("moderate", []),
         1: ("pricey", ["moderate"]), 2: ("pricey", ["very_pricey"]), 3: ("very_pricey", [])}
EXPERIENCE = ("ate_there", "secondhand", "unclear")
FIRSTHAND = {True: "ate_there", False: "secondhand", None: "unclear"}
CONVENTIONS = ("c1", "c1_assumed", "c2", "c2_nonquality", "c3", "c4")

META_KEYS = ["canonical_name", "canonical_key", "accept_keys", "entity_type", "out_of_scope", "ambiguous",
             "confidence", "named_in", "resolvable_comment_mode", "resolvable_thread_mode", "uncertain_fields",
             "rationale", "value_complaint", "search_terms", "closed"]
V5_KEYS = ["restaurant_raw", "neighborhood_hint", "reference_only", "aspects", "is_negated", "price",
           "experience", "dishes_liked", "dishes_disliked", "dishes_mentioned", "descriptors",
           "aspect_alternatives", "judgment_question", "conventions"]
MENTION_KEYS = set(META_KEYS) | set(V5_KEYS)
SETTABLE = set(ASPECTS) | {"reference_only", "is_negated", "price", "experience", "judgment_question",
                           "neighborhood_hint", "descriptors", "dishes_liked", "dishes_disliked",
                           "dishes_mentioned", "restaurant_raw"}


def lab(v):
    return None if v is None else LEVEL[v]


def lab_list(vs):
    return [lab(v) for v in vs]


def price_of(v):
    return (None, []) if v is None else PRICE[v]


def dish_verdict(d):
    """'liked', 'disliked' or 'mentioned' for one v1 dish_sentiment entry."""
    if d["avoid"] or (d["level"] is not None and d["level"] < 0):
        return "disliked"
    if d["level"] is not None and d["level"] > 0:
        return "liked"
    return "mentioned"


def is_bare(m):
    """v1's 'named as an answer': food +1, nothing else scored, no dish verdict, not closed.

    A dish verdict is a judgment, so food +1 with a liked or disliked dish is
    not bare; the review decides whether that +1 was an overall verdict.
    """
    a = m["aspects"]
    return (a.get("food") == 1 and all(a[k] is None for k in ASPECTS if k != "food") and not m["closed"]
            and not any(dish_verdict(d) != "mentioned" for d in m["dish_sentiment"]))


def mention_keys(g):
    """Override key per mention: canonical_name, or name#n when a name repeats in the comment."""
    names = [m["canonical_name"] for m in g["mentions"]]
    keys = []
    for i, name in enumerate(names):
        if names.count(name) > 1:
            keys.append((g["comment_id"], f"{name}#{names[:i].count(name)}"))
        else:
            keys.append((g["comment_id"], name))
    return keys


def dish_part_of(term, dishes):
    t = term.lower()
    return any(t in d.lower() or d.lower() in t for d in dishes)


def merged_overrides():
    """(comment_id, name) -> merged fields; later entries win per key."""
    out = {}
    for e in ov.OVERRIDES:
        k = (e["comment_id"], e["name"])
        cur = out.setdefault(k, dict(fields={}, alts={}, uncertain=[], conv={}, add_desc=[], drop_desc=[], why=[]))
        f = dict(e["fields"])
        cur["alts"].update(f.pop("alts", {}))
        cur["uncertain"] += f.pop("uncertain", [])
        cur["conv"].update(f.pop("conv", {}))
        cur["add_desc"] += f.pop("add_desc", [])
        cur["drop_desc"] += f.pop("drop_desc", [])
        if "ambiguous" in f:
            cur["fields"]["ambiguous"] = f.pop("ambiguous")
        if "no_c3" in f:
            cur["fields"]["no_c3"] = f.pop("no_c3")
        bad = set(f) - SETTABLE
        if bad:
            raise SystemExit(f"override {k} sets unknown fields {bad}")
        cur["fields"].update(f)
        cur["why"].append(e["why"])
    return out


def convert_mention(m, o):
    a_old = m["aspects"]
    alts_old = m["aspect_alternatives"]
    bare = is_bare(m)
    aspects = {k: lab(a_old[k]) for k in ASPECTS}
    alts = {}
    for k, vs in alts_old.items():
        if k == "expensiveness":
            continue
        alts[k] = lab_list(vs)
    if bare:
        aspects["food"] = None
        alts["food"] = [x for x in alts.get("food", []) if x not in ("decent", None)]
        if not alts["food"]:
            del alts["food"]
    all_null_old = all(v is None for v in a_old.values())
    endorse_alt = all_null_old and 1 in (alts_old.get("food") or [])
    for k in list(alts):
        if aspects[k] is None and "decent" in alts[k] and k == "food":
            alts[k] = [x for x in alts[k] if x != "decent"] or None
            if alts[k] is None:
                del alts[k]
    price, price_alts = price_of(m["expensiveness"])
    if "expensiveness" in alts_old:
        price_alts = sorted(set(price_alts) | {price_of(v)[0] for v in alts_old["expensiveness"] if v is not None}
                            - {price}) + ([None] if None in alts_old["expensiveness"] else [])
    if price_alts:
        alts["price"] = price_alts
    liked, disliked, mentioned = [], [], []
    levels = {}
    for d in m["dish_sentiment"]:
        {"liked": liked, "disliked": disliked, "mentioned": mentioned}[dish_verdict(d)].append(d["dish"])
        levels[d["dish"]] = d["level"]
    has_verdict = bool(liked or disliked)
    all_null = all(v is None for v in a_old.values())
    reference_only = bool(m["closed"] or (all_null and not has_verdict and not m["is_negated"]))
    fh = m["is_firsthand"]
    experience = FIRSTHAND[fh]
    if bare and fh is not False:
        experience = "unclear"
    dish_names = [d["dish"] for d in m["dish_sentiment"]]
    descriptors = list(m["descriptors"])
    for t in m["search_terms"]:
        if not dish_part_of(t, dish_names) and t not in descriptors:
            descriptors.append(t)
    out = {k: m[k] for k in META_KEYS}
    out["uncertain_fields"] = list(m["uncertain_fields"])
    # v1 accepted food +1 on an all-null mention as "named as an answer";
    # in v5 that reading is a bare endorsement, i.e. reference_only either way.
    if endorse_alt and "reference_only" not in out["uncertain_fields"]:
        out["uncertain_fields"].append("reference_only")
    out.update(restaurant_raw=m["restaurant_raw"], neighborhood_hint=m["neighborhood_hint"],
               reference_only=reference_only, aspects=aspects, is_negated=m["is_negated"], price=price,
               experience=experience, dishes_liked=liked, dishes_disliked=disliked, dishes_mentioned=mentioned,
               descriptors=descriptors, aspect_alternatives=alts, judgment_question=False, conventions={})
    no_c3 = False
    exp_set = False
    for src in (o,):
        if not src:
            continue
        f = dict(src["fields"])
        if "ambiguous" in f:
            out["ambiguous"] = f.pop("ambiguous")
        no_c3 = f.pop("no_c3", no_c3)
        exp_set = exp_set or "experience" in f
        for k, v in f.items():
            if k in ASPECTS:
                out["aspects"][k] = v
            else:
                out[k] = v
        for k, v in src["alts"].items():
            if v is None:
                out["aspect_alternatives"].pop(k, None)
            else:
                out["aspect_alternatives"][k] = v
        out["uncertain_fields"] += [u for u in src["uncertain"] if u not in out["uncertain_fields"]]
        out["conventions"].update(src["conv"])
        out["descriptors"] = [d for d in out["descriptors"] if d not in src["drop_desc"]]
        out["descriptors"] += [d for d in src["add_desc"] if d not in out["descriptors"]]
    asp = out["aspects"]
    # A reference with an accepted aspect value also accepts the opinion reading.
    if out["reference_only"] and any(any(v is not None for v in vs) for k, vs in out["aspect_alternatives"].items()
                                     if k in ASPECTS) and "reference_only" not in out["uncertain_fields"]:
        out["uncertain_fields"].append("reference_only")
    if out["reference_only"]:
        out["dishes_mentioned"] += [d for d in out["dishes_liked"] + out["dishes_disliked"]
                                    if d not in out["dishes_mentioned"]]
        out["dishes_liked"], out["dishes_disliked"] = [], []
    # c1: food from the dishes when the food overall is not judged.
    if (not out["reference_only"] and asp["food"] is None and "c1" not in out["conventions"]
            and (out["dishes_liked"] or out["dishes_disliked"])):
        assumed = False
        if out["dishes_liked"] and out["dishes_disliked"]:
            food = "mixed"
        elif out["dishes_liked"]:
            # The dishes' own level; a dish with no v1 level (added by the
            # review) is taken as good and tagged so it can be audited.
            known = [levels[d] for d in out["dishes_liked"] if (levels.get(d) or 0) > 0]
            assumed = len(known) < len(out["dishes_liked"])
            food = LEVEL[min(max(known + ([2] if assumed else [])), 3)]
        else:
            # A disliked dish is at most meh, whatever its stale v1 level; an
            # avoid with no level is bad.
            worst = min(min(levels[d], -1) if levels.get(d) is not None else -2 for d in out["dishes_disliked"])
            food = LEVEL[max(worst, -3)]
        asp["food"] = food
        out["conventions"]["c1"] = {"food": None}
        if assumed:
            out["conventions"]["c1_assumed"] = {"food": None}
    # c2: an avoid always carries a negative aspect.
    if out["is_negated"] and not any(v in NEGATIVE for v in asp.values()):
        if asp["food"] is not None:
            raise SystemExit(f"avoid with positive food: {m['canonical_name']}")
        asp["food"] = "bad"
        out["conventions"]["c2"] = {"food": None}
    # c3: a verdict in their own voice means they went.
    judged = any(v is not None for v in asp.values()) or out["dishes_liked"] or out["dishes_disliked"]
    if not out["reference_only"] and judged and out["experience"] == "unclear" and not exp_set and not no_c3:
        out["experience"] = "ate_there"
        out["conventions"]["c3"] = {"experience": "unclear"}
    # c3, other direction: a reference (a fact, a question, a passing name) is
    # unclear unless the review saw a visit; v1 marked many of these firsthand.
    if out["reference_only"] and out["experience"] == "ate_there" and not exp_set and not no_c3:
        out["experience"] = "unclear"
        out["conventions"]["c3"] = {"experience": "ate_there"}
    # An alternative equal to the label itself says nothing.
    for k in list(out["aspect_alternatives"]):
        primary = out["price"] if k == "price" else out["aspects"][k]
        vs = []
        for v in out["aspect_alternatives"][k]:
            if v != primary and v not in vs:
                vs.append(v)
        if vs:
            out["aspect_alternatives"][k] = vs
        else:
            del out["aspect_alternatives"][k]
    return out


def convert(path_in, path_out, used):
    ovs = merged_overrides()
    lines = []
    for line in open(path_in, encoding="utf-8"):
        g = json.loads(line)
        new = []
        for m, key in zip(g["mentions"], mention_keys(g)):
            o = ovs.get(key)
            if o:
                used.add(key)
            new.append(convert_mention(m, o))
        g2 = {k: v for k, v in g.items() if k != "mentions"}
        g2["label_version"] = 3
        g2["v5_converted_by"] = "eval/gold_v5/convert_gold_v5.py"
        g2["mentions"] = new
        g2["has_mention"] = any(not x["ambiguous"] and not x["out_of_scope"] for x in new)
        lines.append(g2)
    with open(path_out, "w", encoding="utf-8") as f:
        for g in lines:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    return lines


def validate(path):
    errs = []
    n = 0
    for i, line in enumerate(open(path, encoding="utf-8")):
        g = json.loads(line)
        if g["label_version"] != 3:
            errs.append(f"{path}:{i} label_version")
        for m in g["mentions"]:
            n += 1
            where = f"{path}:{i} {g['comment_id']} {m.get('canonical_name')}"
            if set(m) != MENTION_KEYS:
                errs.append(f"{where} keys {set(m) ^ MENTION_KEYS}")
                continue
            if set(m["aspects"]) != set(ASPECTS):
                errs.append(f"{where} aspect keys")
            for k, v in m["aspects"].items():
                if v is not None and v not in LABELS:
                    errs.append(f"{where} aspect {k}={v!r}")
            for k, vs in m["aspect_alternatives"].items():
                ok = LABELS if k in ASPECTS else set(PRICES) if k == "price" else None
                if ok is None or not isinstance(vs, list) or any(v is not None and v not in ok for v in vs):
                    errs.append(f"{where} alternative {k}={vs!r}")
            if m["price"] is not None and m["price"] not in PRICES:
                errs.append(f"{where} price {m['price']!r}")
            if m["experience"] not in EXPERIENCE:
                errs.append(f"{where} experience {m['experience']!r}")
            for k in ("reference_only", "is_negated", "judgment_question"):
                if not isinstance(m[k], bool):
                    errs.append(f"{where} {k} not bool")
            for k in ("dishes_liked", "dishes_disliked", "dishes_mentioned", "descriptors"):
                if not isinstance(m[k], list) or not all(isinstance(x, str) for x in m[k]):
                    errs.append(f"{where} {k} not a list of strings")
            dl = [d.lower() for d in m["dishes_liked"] + m["dishes_disliked"] + m["dishes_mentioned"]]
            if len(dl) != len(set(dl)):
                errs.append(f"{where} a dish is in more than one list")
            if m["reference_only"]:
                if any(v is not None for v in m["aspects"].values()):
                    errs.append(f"{where} reference_only with aspects")
                if m["is_negated"]:
                    errs.append(f"{where} reference_only with is_negated")
                if m["dishes_liked"] or m["dishes_disliked"]:
                    errs.append(f"{where} reference_only with dish verdicts")
            if m["is_negated"] and not any(v in NEGATIVE for v in m["aspects"].values()):
                errs.append(f"{where} avoid without a negative aspect (c2)")
            for cid, rev in m["conventions"].items():
                if cid not in CONVENTIONS or not isinstance(rev, dict):
                    errs.append(f"{where} convention {cid}")
            if m["judgment_question"] and m["reference_only"]:
                errs.append(f"{where} judgment_question on a reference")
    if errs:
        raise SystemExit("v5 gold INVALID:\n  " + "\n  ".join(errs[:60]) + (f"\n  ... {len(errs)} errors" if len(errs) > 60 else ""))
    print(f"{path}: {n} mentions valid")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    outs = [(os.path.join(EVAL, "v1", "gold.jsonl"), os.path.join(EVAL, "v1", "gold_v5.jsonl")),
            (os.path.join(EVAL, "v2", "gold.jsonl"), os.path.join(EVAL, "v2", "gold_v5.jsonl"))]
    if not args.check:
        used = set()
        for src, dst in outs:
            convert(src, dst, used)
        unused = set(merged_overrides()) - used
        if unused:
            raise SystemExit(f"overrides matched no mention: {sorted(unused)}")
    for _, dst in outs:
        validate(dst)


if __name__ == "__main__":
    main()
