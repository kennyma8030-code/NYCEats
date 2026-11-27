"""What a place is known for ordering, from the dish names the extractor wrote.

The extractor writes whatever people typed, so one dish arrives as "pastrami",
"pastrami sandwich", "pastrami on rye" and "sandwiches", and filler like
"sandwich" or "bread" takes a slot of its own. Two layers clean that up. A file
per city beside this module (dish_groups_<subreddit>.json, written offline)
says which names of a place are one dish and which are filler; it is a
rebuildable cache over mentions.dishes, which is never touched. Names the file
does not cover, and new ones arrive daily, fall back to a plain normalisation.

A file entry is keyed by the place's resolved key:
    {"katzs delicatessen": {"groups": [{"label": "Pastrami sandwich",
                                        "names": ["pastrami", "pastrami on rye"]}],
                            "drop": ["sandwich", "bread"]}}
A city whose file is missing is served by the fallback alone.

Counting is by mention, not by string: one comment that names both "pastrami"
and "pastrami sandwich" is one vote for the dish, so merging names can never
inflate it.
"""

import json
import logging
import os
from collections import Counter

log = logging.getLogger("uvicorn.error")

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
# A dish named by fewer mentions than this is one person's order, not what the place is known for.
MIN_MENTIONS = 3

# {subreddit: {place key: entry}}, filled the first time a city is asked for.
_GROUPS = {}


def _path(sub):
    return os.path.join(DATA, f"dish_groups_{sub}.json")


def _load(path):
    """One file as {place key: entry}. A missing or broken file is a warning
    and an empty lookup: the list works on the fallback alone, and the API
    should not fail over a cleanup file."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        log.warning("no dish groups loaded from %s: %s", path, e)
        return {}


def clean(name):
    """Lowercased with runs of whitespace collapsed, the form the files use."""
    return " ".join(name.lower().split())


def groups(sub, entity_key):
    """The place's lookup as ({name: label}, {dropped names}), read from its
    city's file the first time that city is asked for."""
    if sub not in _GROUPS:
        _GROUPS[sub] = _load(_path(sub))
    entry = _GROUPS[sub].get(entity_key) or {}
    labels = {}
    for g in entry.get("groups", ()):
        for name in g.get("names", ()):
            labels[clean(name)] = g["label"]
    return labels, {clean(n) for n in entry.get("drop", ())}


def fold(name):
    """The name with a simple plural on its last word removed, so "burritos"
    and "burrito" are one dish. Words that merely end in s are left alone:
    "fries", "ss" words, "us"/"is" words (hummus), and anything too short to
    be a plural of something."""
    head, _, last = name.rpartition(" ")
    if len(last) > 3 and last.endswith("s") and not last.endswith(("ss", "us", "is", "ies")):
        last = last[:-2] if last.endswith(("ches", "shes", "xes")) else last[:-1]
    return f"{head} {last}" if head else last


def top(rows, sub, entity_key, limit=15):
    """The dishes of a place as [{"name", "n"}], most-mentioned first, where n
    is the number of distinct mentions. rows holds one dish array per mention."""
    labels, dropped = groups(sub, entity_key)
    counts = Counter()
    shown = {}  # key -> the file's label
    forms = {}  # key -> Counter of original spellings, for names the file does not cover
    for dishes in rows:
        keys = set()
        for raw in dishes:
            if not isinstance(raw, str):
                continue
            name = clean(raw)
            if not name or name in dropped:
                continue
            if name in labels:
                key = labels[name].lower()
                shown[key] = labels[name]
            else:
                key = fold(name)
                forms.setdefault(key, Counter())[name] += 1
            keys.add(key)
        counts.update(keys)
    out = [{"name": shown.get(k) or forms[k].most_common(1)[0][0], "n": n}
           for k, n in counts.items() if n >= MIN_MENTIONS]
    out.sort(key=lambda d: (-d["n"], d["name"]))
    return out[:limit]
