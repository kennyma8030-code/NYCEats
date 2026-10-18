"""Map a v6 mention onto the shape score.py and v4/labels.py already read.

The gold sets (v1, v2, and v4's label export) are written in production's
schema: food/value/service/atmosphere/wait as -1..1 numbers, expensiveness,
is_firsthand, is_negated, and the rubric extras value_complaint and
dish_sentiment. v6 says the same things in five named levels and a few new
fields, so scoring v6 is a translation, done once here. score.load_run and
labels.read_pass call adapt() on every mention; anything that is not a v6
mention passes through untouched, so old run files score exactly as before.

The translation keeps v6's meaning and only bends where the old gold has a
convention v6 deliberately dropped:

  * food is v6's taste. When taste is null the old prompts put a generic
    verdict in food, so food falls back to 0.33 for an endorsement (the old
    "named as an answer" default) and otherwise to overall.
  * Five levels land on the 7-point grid at +-1 and +-0.67; neutral is 0.
    The gold's mild knock (-1, e.g. "mid") therefore reads as -2 after
    bucketing: the sign agrees, the exact level cannot.
  * A closed place gets every aspect null, which is how the gold labels it.
    v6 keeps the remembered verdict with timeframe "past"; that survives
    under the "v6" key.
  * value_complaint is a negative value level. v6 has no complaint list;
    a price complaint is value by definition.

The untranslated mention stays available under "v6", so a v6-aware scorer
never has to re-parse the run file.
"""

LEVEL_NUM = {"very_positive": 1.0, "positive": 0.67, "neutral": 0.0,
             "negative": -0.67, "very_negative": -1.0}
PRICE_NUM = {"very_cheap": -1.0, "cheap": -0.67, "moderate": 0.0,
             "expensive": 0.67, "very_expensive": 1.0}
ENDORSE_FOOD = 0.33
OTHER_ASPECTS = ("value", "service", "atmosphere", "wait")


def is_v6(m):
    return isinstance(m, dict) and "opinion" in m and "name" in m and "restaurant_raw" not in m


def num(level):
    return LEVEL_NUM.get(level) if isinstance(level, str) else None


def to_legacy(m):
    """One v6 mention -> production/rubric shape (plus the original under "v6")."""
    asp = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
    closed = m.get("status") == "closed"
    food = num(asp.get("taste"))
    if food is None:
        food = ENDORSE_FOOD if m.get("opinion") == "endorse" else num(m.get("overall"))
    aspects = {"food": food, **{a: num(asp.get(a)) for a in OTHER_ASPECTS}}
    if closed:
        aspects = {k: None for k in aspects}
    dishes = [d for d in (m.get("dishes") or []) if isinstance(d, dict) and d.get("dish")]
    tags = [str(t) for t in (m.get("tags") or [])]
    out = {
        "restaurant_raw": m.get("name"),
        "neighborhood_hint": m.get("location"),
        "dishes": [d["dish"] for d in dishes],
        "dish_sentiment": [{"dish": d["dish"], "level": num(d.get("level")),
                            "avoid": bool(d.get("avoid"))} for d in dishes],
        "descriptors": tags + (["closed"] if closed and "closed" not in tags else []),
        "aspects": aspects,
        "expensiveness": PRICE_NUM.get(m.get("price")),
        "value_complaint": (aspects["value"] or 0) < 0,
        "is_firsthand": m.get("experience") == "firsthand",
        "is_negated": bool(m.get("avoid")),
        "v6": m,
    }
    if "id" in m:
        out["id"] = m["id"]
    return out


def adapt(m):
    return to_legacy(m) if is_v6(m) else m


def adapt_all(mentions):
    return [adapt(m) for m in mentions] if isinstance(mentions, list) else mentions


SCHEMA_KEYWORDS = {"$ref", "type", "enum", "properties", "required", "additionalProperties", "items"}
SCHEMA_ANNOTATIONS = {"$schema", "$id", "$defs", "title", "description"}


class UnsupportedSchema(ValueError):
    """The schema uses a keyword schema_errors does not implement."""


def schema_errors(value, node, root=None, path="$"):
    """Errors for value against the v6 schema (v6_common.SCHEMA_COMMENT or
    SCHEMA_THREAD), [] when it is valid. A minimal JSON Schema validator for
    the subset the v6 schema uses ($ref, type unions, enum, properties,
    required, additionalProperties, items), so checking labels needs no extra
    package. A keyword outside that subset raises UnsupportedSchema rather
    than being skipped: a validator that ignores a constraint would pass
    labels the schema forbids. additionalProperties is read as JSON Schema
    defines it: false forbids extra keys, a schema validates them, and true or
    absent allows them (the v6 schema closes every object)."""
    root = root if root is not None else node
    unknown = set(node) - SCHEMA_KEYWORDS - SCHEMA_ANNOTATIONS
    if unknown:
        raise UnsupportedSchema(f"{path}: schema keyword(s) {sorted(unknown)} are not implemented")
    if "$ref" in node:
        ref = node["$ref"]
        if not ref.startswith("#/$defs/"):
            raise UnsupportedSchema(f"{path}: only local #/$defs/ references are implemented, not {ref}")
        return schema_errors(value, root["$defs"][ref.split("/")[-1]], root, path)
    types = node.get("type")
    types = types if isinstance(types, list) else [types] if types else []
    pytype = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
    if types and not any((t == "integer" and isinstance(value, int) and not isinstance(value, bool))
                         or (t in pytype and isinstance(value, pytype[t])) for t in types):
        return [f"{path}: {value!r} is not {types}"]
    errs = []
    if "enum" in node and value not in node["enum"]:
        errs.append(f"{path}: {value!r} not in enum")
    if isinstance(value, dict):
        props = node.get("properties", {})
        extra = node.get("additionalProperties", True)
        errs += [f"{path}: missing {k}" for k in node.get("required", []) if k not in value]
        for k, v in value.items():
            if k in props:
                errs += schema_errors(v, props[k], root, f"{path}.{k}")
            elif extra is False:
                errs.append(f"{path}: extra key {k}")
            elif isinstance(extra, dict):
                errs += schema_errors(v, extra, root, f"{path}.{k}")
    if isinstance(value, list) and "items" in node:
        for i, v in enumerate(value):
            errs += schema_errors(v, node["items"], root, f"{path}[{i}]")
    return errs
