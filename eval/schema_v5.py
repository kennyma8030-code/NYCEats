"""The v5 extraction schema as code: label maps, the normalizer, and the adapter.

Everything that turns a model's raw output into the v5 contract lives here, so
the scorer, the bench and the self-tests all read output the same way. The
written contract is eval/schema_v5.md; this file must agree with it.

Two entry points:

    normalize_v5(m)   a mention a model emitted under a v5 prompt -> the
                      contract, with every repair counted. Models drift (a
                      string "false", a float where a label belongs, a dish in
                      two lists), and the counts are reported per run because
                      a prompt that needs many repairs is itself a finding.
    adapt_old(m)      a mention in the OLD schema (production's prompts, the
                      current prompt, rubric_v1) -> the contract, so baselines
                      score on the same scorer without new API calls.

to_v5(m) picks between them per mention.
"""

import collections
import math

ASPECTS = ("food", "value", "service", "atmosphere", "wait")

# Sentiment labels and their 7-point levels. The floats are what production's
# -1..1 columns would store, so v5 output can be written into today's schema.
LEVELS = {"rave": 3, "good": 2, "decent": 1, "mixed": 0, "meh": -1, "bad": -2, "awful": -3}
LABEL_OF_LEVEL = {v: k for k, v in LEVELS.items()}
FLOATS = {"rave": 1.0, "good": 0.6, "decent": 0.3, "mixed": 0.0, "meh": -0.3, "bad": -0.6, "awful": -1.0}

# Price is an ordered fact with no valence; the rank only serves within-one
# agreement.
PRICES = ("cheap", "moderate", "pricey", "very_pricey")
PRICE_RANK = {p: i for i, p in enumerate(PRICES)}

EXPERIENCES = ("ate_there", "secondhand", "unclear")

DISH_LISTS = ("dishes_liked", "dishes_disliked", "dishes_mentioned")
V5_KEYS = ("restaurant_raw", "neighborhood_hint", "reference_only", "aspects", "is_negated",
           "price", "experience", "dishes_liked", "dishes_disliked", "dishes_mentioned",
           "descriptors")
# Keys that only a v5 output carries; any one of them marks a mention as v5.
V5_ONLY = {"reference_only", "experience", "price", "dishes_liked", "dishes_disliked",
           "dishes_mentioned"}


# ---------------------------------------------------------------- small coercions
def level_of_float(v):
    """Old -1..1 float -> 7-point level, the same cut points as score.bucket."""
    v = max(-1.0, min(1.0, float(v)))
    lvl = math.floor(abs(v) * 3 + 0.5)
    return int(math.copysign(lvl, v)) if lvl else 0


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _bool(v, field, fixes, default=False):
    """Strict boolean. bool("false") is True, which is how a string slips
    through as an avoid instruction, so strings are read for their words."""
    if isinstance(v, bool):
        return v
    if v is None:
        fixes[f"{field}_missing"] += 1
        return default
    if isinstance(v, str) and v.strip().lower() in ("true", "false"):
        fixes[f"{field}_string"] += 1
        return v.strip().lower() == "true"
    if isinstance(v, (int, float)) and v in (0, 1):
        fixes[f"{field}_number"] += 1
        return bool(v)
    fixes[f"{field}_invalid"] += 1
    return default


def _str_list(v, field, fixes):
    if v is None:
        fixes[f"{field}_missing"] += 1
        return []
    if isinstance(v, str):
        fixes[f"{field}_string"] += 1
        v = [v]
    if not isinstance(v, list):
        fixes[f"{field}_invalid"] += 1
        return []
    out, seen = [], set()
    for x in v:
        if not isinstance(x, str):
            fixes[f"{field}_non_string"] += 1
            continue
        x = x.strip()
        if x and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


def _label(v, fixes, field):
    """An aspect value -> a label or None.

    A v5 model that drifts into numbers almost always writes the 7-point
    levels it was shown (-3..3), so whole numbers, as ints, int-like strings
    or floats like 2.0, are read as levels: 1 is decent, not rave. Only a
    fractional number (0.6, -0.33) is read on the old -1..1 scale."""
    if v is None:
        return None
    if isinstance(v, bool):
        fixes[f"{field}_bad_label"] += 1
        return None
    if isinstance(v, str):
        s = v.strip().lower()
        if s in LEVELS:
            if s != v:
                fixes[f"{field}_label_case"] += 1
            return s
        if s in ("", "null", "none"):
            fixes[f"{field}_null_string"] += 1
            return None
        n = _num(s.removeprefix("+"))
        if n is None:
            fixes[f"{field}_bad_label"] += 1
            return None
        v = n
    n = _num(v)
    if n is None:
        fixes[f"{field}_bad_label"] += 1
        return None
    if float(n).is_integer():
        fixes[f"{field}_numeric_level"] += 1
        return LABEL_OF_LEVEL[max(-3, min(3, int(n)))]
    fixes[f"{field}_numeric_float"] += 1
    return LABEL_OF_LEVEL[level_of_float(n)]


def price_of_float(v):
    """Old expensiveness float -> price label. By level: -1 or below is cheap,
    0 moderate, +1 and +2 pricey, +3 very_pricey. The old scale had no single
    'moderate' anchor (0 meant middling), so this is the nearest reading."""
    lvl = level_of_float(v)
    if lvl <= -1:
        return "cheap"
    if lvl == 0:
        return "moderate"
    return "very_pricey" if lvl >= 3 else "pricey"


def _price(v, fixes):
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().lower().replace(" ", "_").replace("-", "_")
        if s in PRICE_RANK:
            return s
        if s in ("", "null", "none"):
            fixes["price_null_string"] += 1
            return None
        fixes["price_bad_label"] += 1
        return None
    n = _num(v)
    if n is None:
        fixes["price_bad_label"] += 1
        return None
    fixes["price_numeric"] += 1
    if float(n).is_integer():           # a level, as for aspects
        lvl = max(-3, min(3, int(n)))
        return "cheap" if lvl <= -1 else "moderate" if lvl == 0 else "very_pricey" if lvl >= 3 else "pricey"
    return price_of_float(n)


def _experience(v, fixes):
    if isinstance(v, str) and v.strip().lower() in EXPERIENCES:
        return v.strip().lower()
    if isinstance(v, bool):
        fixes["experience_bool"] += 1
        return "ate_there" if v else "secondhand"
    if v is None:
        fixes["experience_missing"] += 1
    else:
        fixes["experience_bad_label"] += 1
    return "unclear"


# ---------------------------------------------------------------- the normalizer
def normalize_v5(m, fixes=None):
    """A raw v5 mention -> (mention in the contract, or None to drop it).

    `fixes` is a Counter that collects one entry per repair. The consistency
    rules (contract rule 9) are enforced here rather than trusted: evidence of
    an opinion beats the reference_only flag, so set aspects, an avoid
    instruction, or a liked/disliked dish each clear it. The contract states
    the aspect case outright; the other two follow the same reading, because
    each is an opinion the commenter stated, and dropping it would lose
    exactly the negative evidence the eval exists to catch."""
    fixes = fixes if fixes is not None else collections.Counter()
    if not isinstance(m, dict):
        fixes["not_object"] += 1
        return None
    name = m.get("restaurant_raw")
    if not isinstance(name, str) or not name.strip():
        fixes["no_name"] += 1
        return None
    for k in m:
        if k not in V5_KEYS and k != "id":
            fixes["extra_key"] += 1

    asp_in = m.get("aspects")
    if not isinstance(asp_in, dict):
        fixes["aspects_missing" if asp_in is None else "aspects_invalid"] += 1
        asp_in = {}
    aspects = {}
    for a in ASPECTS:
        if a not in asp_in:
            fixes["aspect_missing_key"] += 1
        aspects[a] = _label(asp_in.get(a), fixes, "aspect")
    if any(k not in ASPECTS for k in asp_in):
        fixes["aspect_extra_key"] += 1

    hood = m.get("neighborhood_hint")
    if hood is not None and not isinstance(hood, str):
        fixes["neighborhood_invalid"] += 1
        hood = None
    hood = (hood or "").strip() or None

    out = {
        "restaurant_raw": name.strip(),
        "neighborhood_hint": hood,
        "reference_only": _bool(m.get("reference_only"), "reference_only", fixes),
        "aspects": aspects,
        "is_negated": _bool(m.get("is_negated"), "is_negated", fixes),
        "price": _price(m.get("price"), fixes),
        "experience": _experience(m.get("experience"), fixes),
        "descriptors": _str_list(m.get("descriptors"), "descriptors", fixes),
    }
    for k in DISH_LISTS:
        out[k] = _str_list(m.get(k), k, fixes)
    if "id" in m:
        out["id"] = m["id"]

    # A dish belongs to one list. Disliked wins, then liked: a verdict is the
    # stronger statement, and a negative is the one the owner reads for.
    seen = set()
    for k in ("dishes_disliked", "dishes_liked", "dishes_mentioned"):
        keep = []
        for d in out[k]:
            if d.lower() in seen:
                fixes["dish_in_two_lists"] += 1
                continue
            seen.add(d.lower())
            keep.append(d)
        out[k] = keep

    if out["reference_only"]:
        if any(v is not None for v in aspects.values()):
            fixes["reference_with_aspects"] += 1
            out["reference_only"] = False
        if out["is_negated"]:
            fixes["reference_with_negated"] += 1
            out["reference_only"] = False
        if out["dishes_liked"] or out["dishes_disliked"]:
            fixes["reference_with_dish_verdict"] += 1
            out["reference_only"] = False
    return out


# ---------------------------------------------------------------- the adapter
def adapt_old(m, fixes=None):
    """An OLD-schema mention -> the contract.

    - Floats bucket to levels (score.bucket's cut points), then to labels.
    - Food at level 1 with every other aspect null and no avoid is the old
      prompts' bare endorsement (0.3, or 0.33 for rubric_v1): it becomes
      aspects null, reference_only false. A genuine "X is solid" also lands
      at level 1 in the old schema; the two cannot be told apart here.
    - reference_only is derived: every aspect null and no avoid. The old
      prompts gave every bare name food 0.3, so an all-null mention is one
      where the model recorded no judgment at all (a closed place, a
      question, hearsay it chose not to score). It is a derived reading, and
      the bench marks reference_only metrics for adapted runs as such.
    - expensiveness -> price by price_of_float.
    - dishes -> dishes_mentioned; rubric_v1's dish_sentiment entries move to
      liked (level > 0) or disliked (level < 0, or avoid).
    - is_firsthand true/false/null -> ate_there/secondhand/unclear.
    """
    fixes = fixes if fixes is not None else collections.Counter()
    if not isinstance(m, dict):
        fixes["not_object"] += 1
        return None
    name = m.get("restaurant_raw")
    if not isinstance(name, str) or not name.strip():
        fixes["no_name"] += 1
        return None
    asp_in = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
    levels = {}
    for a in ASPECTS:
        n = _num(asp_in.get(a))
        levels[a] = None if n is None else level_of_float(n)
    negated = _bool(m.get("is_negated"), "is_negated", fixes) if "is_negated" in m else False
    others_null = all(levels[a] is None for a in ASPECTS if a != "food")
    bare = levels["food"] == 1 and others_null and not negated
    aspects = {a: (None if bare or levels[a] is None else LABEL_OF_LEVEL[levels[a]]) for a in ASPECTS}

    liked, disliked, mentioned = [], [], []
    ds = m.get("dish_sentiment")
    for d in ds if isinstance(ds, list) else []:
        if not isinstance(d, dict) or not isinstance(d.get("dish"), str):
            continue
        n = _num(d.get("level"))
        if d.get("avoid") is True or (n is not None and level_of_float(n) < 0):
            disliked.append(d["dish"])
        elif n is not None and level_of_float(n) > 0:
            liked.append(d["dish"])
        else:
            mentioned.append(d["dish"])
    judged = {x.lower() for x in liked + disliked + mentioned}
    for d in m.get("dishes") or []:
        if isinstance(d, str) and d.lower() not in judged:
            judged.add(d.lower())
            mentioned.append(d)

    fh = m.get("is_firsthand")
    exp = m.get("expensiveness")
    out = {
        "restaurant_raw": name.strip(),
        "neighborhood_hint": m.get("neighborhood_hint") if isinstance(m.get("neighborhood_hint"), str) else None,
        "reference_only": all(v is None for v in levels.values()) and not negated,
        "aspects": aspects,
        "is_negated": negated,
        "price": None if _num(exp) is None else price_of_float(_num(exp)),
        "experience": "ate_there" if fh is True else "secondhand" if fh is False else "unclear",
        "dishes_liked": liked, "dishes_disliked": disliked, "dishes_mentioned": mentioned,
        "descriptors": [x for x in (m.get("descriptors") or []) if isinstance(x, str)],
        "_adapted": True,
        "_dish_capable": isinstance(ds, list),
    }
    if "value_complaint" in m:
        out["_value_complaint"] = m.get("value_complaint") is True
    if "id" in m:
        out["id"] = m["id"]
    return out


def is_v5(m):
    """Whether a raw mention was written in the v5 schema."""
    if not isinstance(m, dict):
        return False
    if V5_ONLY & set(m):
        return True
    asp = m.get("aspects")
    return isinstance(asp, dict) and any(isinstance(v, str) for v in asp.values())


def run_schema(mentions):
    """'v5' or 'old' for a whole run, by majority of its mentions (ties go to
    v5). Deciding per run rather than per mention matters: a v5 mention that
    drifted (numeric aspects, missing v5 keys) must still go through the
    normalizer, where its repairs are counted, not be quietly adapted."""
    v5 = old = 0
    for m in mentions:
        if isinstance(m, dict):
            v5 += is_v5(m)
            old += not is_v5(m)
    return "v5" if v5 >= old else "old"


def to_v5(m, fixes=None, schema=None):
    """A raw mention -> the contract: the normalizer for a v5 run, the
    adapter for an old one. Without a run's schema, the mention decides."""
    schema = schema or ("v5" if is_v5(m) else "old")
    return normalize_v5(m, fixes) if schema == "v5" else adapt_old(m, fixes)


def level(label):
    return None if label is None else LEVELS.get(label)


def to_production_floats(m):
    """A contract mention -> today's mentions columns. A bare endorsement
    (not reference_only, every aspect null) becomes food 0.3 exactly, which
    is what scoring_v2's bare-name test looks for."""
    asp = {a: (None if m["aspects"][a] is None else FLOATS[m["aspects"][a]]) for a in ASPECTS}
    if not m["reference_only"] and all(v is None for v in asp.values()) and not m["is_negated"]:
        asp["food"] = 0.3
    return asp
