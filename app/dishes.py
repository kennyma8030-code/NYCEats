"""What a place is known for ordering, from the dish names the extractor wrote.

The extractor writes whatever people typed, so one dish arrives as "pastrami",
"pastrami sandwich", "pastrami on rye" and "sandwiches", and filler like
"sandwich" or "bread" takes a slot of its own. Two layers clean that up.

A file per city beside this module (dish_groups_<subreddit>.json) holds
curated per-place decisions: which of a place's names are one dish, and which
are filler. They were written by reading each place's dish names, so they are
judgement kept in the repo, like alias_overrides are curated identity
decisions; they cannot be rebuilt from mentions.dishes, which is never
touched. A place missing from its file (new, or renamed by resolve) is not an
error: its names fall back to plural folding alone, as do names the file does
not mention, and new ones arrive daily.

A file entry is keyed by the place's resolved key:
    {"katzs delicatessen": {"groups": [{"label": "Pastrami sandwich",
                                        "names": ["pastrami", "pastrami on rye"]}],
                            "drop": ["sandwich", "bread"]}}
Everything, the file's names, drops and labels and the names mentioned, is
matched on one key, the lowercased name with a plural on its last word folded,
so a new "spare rib" meets the group that lists "spare ribs" and "bagel" is
dropped where "bagels" is.

Counting is by mention, not by string: one comment that names both "pastrami"
and "pastrami sandwich" is one vote for the dish, so merging names can never
inflate it.
"""

import logging
import os
import threading
from collections import Counter

from . import jsonfile

log = logging.getLogger("uvicorn.error")

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
# A dish named by fewer mentions than this is one person's order, not what the place is known for.
MIN_MENTIONS = 3

# {subreddit: {place key: (labels, dropped)}}, each city built once, on first use.
_PLACES = {}
_LOCK = threading.Lock()


def _path(sub):
    return os.path.join(DATA, f"dish_groups_{sub}.json")


def clean(name):
    """The name with runs of whitespace collapsed and the ends trimmed."""
    return " ".join(name.split())


def fold(name):
    """The key a name is matched on: lowercased, with the plural of its last
    word folded so "burritos" and "burrito" are one dish. Only the key is
    folded; it is never shown. The folds are chosen so that a word and its
    plural meet, not to be good English: "quiche" and "quiches" both become
    "quich", "cookie" and "cookies" both "cooky". Left alone are "fries",
    words ending "ss", "us" or "is" (hummus, couscous), and anything of three
    letters or fewer."""
    head, _, last = clean(name).lower().rpartition(" ")
    if len(last) > 3 and last != "fries":
        if last.endswith("ies"):
            last = last[:-3] + "y" if len(last) > 4 else last[:-1]
        elif last.endswith("ie"):
            last = last[:-2] + "y"
        elif last.endswith(("ches", "shes", "xes", "oes")):
            last = last[:-2]
        elif last.endswith("che"):
            last = last[:-1]
        elif last.endswith("s") and not last.endswith(("ss", "us", "is")):
            last = last[:-1]
    return f"{head} {last}" if head else last


def _strings(value):
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _place(key, entry):
    """One entry as (labels, dropped): {folded name: label} and {folded name},
    or None, with a warning, if it is not the shape the file promises."""
    try:
        groups, drop = entry.get("groups", []), entry.get("drop", [])
        if not isinstance(groups, list) or not _strings(drop):
            raise ValueError("groups and drop must be lists")
        labels = {}
        for g in groups:
            if not (isinstance(g, dict) and isinstance(g.get("label"), str) and g["label"].strip()
                    and _strings(g.get("names"))):
                log.warning("dish group of %s skipped: needs a label and a list of names: %r", key, g)
                continue
            label = clean(g["label"])
            for name in [label, *g["names"]]:
                labels[fold(name)] = label
    except (AttributeError, ValueError) as e:
        log.warning("dish groups of %s skipped: %s", key, e)
        return None
    return labels, {fold(n) for n in drop}


def _build(path):
    data = jsonfile.load(path, "dish groups")
    if not isinstance(data, dict):
        log.warning("no dish groups loaded from %s: not an object", path)
        return {}
    places = {}
    for key, entry in data.items():
        place = _place(key, entry)
        if place:
            places[key] = place
    return places


def groups(sub, entity_key):
    """The place's lookup as ({folded name: label}, {folded dropped names}),
    empty for a place the file does not mention."""
    if sub not in _PLACES:
        with _LOCK:
            if sub not in _PLACES:
                _PLACES[sub] = _build(_path(sub))
    return _PLACES[sub].get(entity_key, ({}, set()))


def top(rows, sub, entity_key, limit=15):
    """The dishes of a place as [{"name", "n"}], most-mentioned first, where n
    is the number of distinct mentions. rows holds one dish array per mention."""
    labels, dropped = groups(sub, entity_key)
    counts = Counter()
    shown = {}  # key -> the file's label
    forms = {}  # key -> Counter of the spellings typed, for names the file does not cover
    for dishes in rows:
        keys = set()
        for raw in dishes:
            if not isinstance(raw, str) or not raw.strip():
                continue
            key = fold(raw)
            if key in dropped:
                continue
            if key in labels:
                shown[fold(labels[key])] = labels[key]
                key = fold(labels[key])
            else:
                forms.setdefault(key, Counter())[clean(raw)] += 1
            keys.add(key)
        counts.update(keys)
    out = []
    for key, n in counts.items():
        if n < MIN_MENTIONS:
            continue
        # A label wins over the spellings typed: the file named the dish.
        name = shown[key] if key in shown else min(forms[key].items(), key=lambda f: (-f[1], f[0]))[0]
        out.append((-n, key, name))
    out.sort()
    return [{"name": name, "n": -neg} for neg, _, name in out[:limit]]
