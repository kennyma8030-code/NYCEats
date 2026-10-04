"""Shared label constructor for labels/batchNN.py. Schema: eval/README.md."""

import json
import os
import sys

EVAL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(EVAL))
from extract import normalize_entity  # noqa: E402

with open(os.path.join(EVAL, "alias_overrides.json"), encoding="utf-8") as f:
    ALIAS = json.load(f)
with open(os.path.join(EVAL, "excluded_entities.json"), encoding="utf-8") as f:
    EXCLUDED = json.load(f)

LEVELS = (None, -3, -2, -1, 0, 1, 2, 3)
ASPECTS = ("food", "value", "service", "atmosphere", "wait")
TYPES = ("restaurant", "bar", "cafe_bakery_dessert", "chain", "food_hall", "stall_vendor",
         "food_truck", "grocery_market", "other")


def key(name):
    k = normalize_entity(name)
    return ALIAS.get(k, k)


def M(raw, canon=None, *, also=(), type="restaurant", food=None, value=None, service=None,
      atmosphere=None, wait=None, exp=None, alt=None, neg=False, neg_ok=False, first=True,
      dishes=(), terms=(), desc=(), vc=False, hood=None, closed=False, oos=False,
      rc=True, rt=True, conf="high", amb=False, unc=(), named_in="comment", why=""):
    """dishes: (name, level|None, avoid) tuples or plain names (level None).
    neg_ok: accept is_negated either way (self-skip). oos: out of scope."""
    canon = canon or raw
    k = key(canon)
    accept = sorted({key(x) for x in (raw, canon, *also)} | {normalize_entity(x) for x in (raw, *also)}
                    - {k})
    ds = []
    for d in dishes:
        if isinstance(d, str):
            d = (d, None, False)
        name, lvl, avoid = (tuple(d) + (None, False))[:3]
        assert lvl in LEVELS, (raw, d)
        ds.append({"dish": name, "level": lvl, "avoid": bool(avoid)})
    descriptors = list(desc)
    if closed and "closed" not in descriptors:
        descriptors.append("closed")
    aspects = {"food": food, "value": value, "service": service,
               "atmosphere": atmosphere, "wait": wait}
    for a, v in list(aspects.items()) + [("expensiveness", exp)]:
        assert v in LEVELS, (raw, a, v)
    if closed:
        assert all(v is None for v in aspects.values()), (raw, "closed => aspects null")
    assert type in TYPES, type
    unc = list(unc)
    if neg_ok and "is_negated" not in unc:
        unc.append("is_negated")
    return {
        "restaurant_raw": raw, "canonical_name": canon, "canonical_key": k,
        "accept_keys": accept, "entity_type": type,
        "out_of_scope": bool(oos or k in EXCLUDED),
        "aspects": aspects, "aspect_alternatives": alt or {},
        "expensiveness": exp,
        "value_complaint": bool(vc),
        "dish_sentiment": ds, "dishes": [d["dish"] for d in ds],
        "search_terms": [t.lower() for t in terms],
        "descriptors": descriptors,
        "is_negated": neg, "is_firsthand": first,
        "neighborhood_hint": hood, "closed": closed, "named_in": named_in,
        "resolvable_comment_mode": rc, "resolvable_thread_mode": rt,
        "confidence": conf, "ambiguous": amb, "uncertain_fields": unc,
        "rationale": why,
    }
