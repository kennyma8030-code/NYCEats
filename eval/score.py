"""Score run files against eval/gold.jsonl.

    python eval/score.py eval/runs/<model>__<hash>__<mode>.jsonl [more runs ...]
    python eval/score.py eval/runs/production__stored__all.jsonl --drop-chains
    python eval/score.py --self-test             # gold scored against itself
    python eval/score.py RUN --gold eval/v2/gold.jsonl --items eval/v2/items.jsonl   # v2 diagnostic set

Writes eval/results/<date>__<run>.md and .csv. Full definitions are in
eval/README.md ("Scoring"). The HEADLINE follows the owner's priorities, in
this order:

  a. comment drop rate          gold has >=1 required mention, model returned none
  b. mention recall             people-talking volume (required gold mentions found)
  c. negative-mention recall    gold mention with any aspect <= -1 whose match carries a
                                negative (any aspect level < 0, or is_negated)
  d. value-complaint recall     gold value_complaint; model value_complaint if the prompt
                                emits it, else aspects.value < 0
  e. dish-negative recall       gold dish level <= -1 or avoid; model dish_sentiment level < 0
                                or avoid, dish names matched leniently. n/a when the run
                                never emits dish_sentiment (production prompts)
  f. sign accuracy + levels used

Model mentions are keyed normalize_entity -> alias_overrides (production's
1,901). A key in excluded_entities.json, or a match to a gold out_of_scope or
ambiguous mention, is neither rewarded nor penalised.
"""

import argparse
import collections
import csv
import datetime
import json
import math
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from extract import CHAINS, normalize_entity  # noqa: E402
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import v6_adapter  # noqa: E402

ASPECTS = ("food", "value", "service", "atmosphere", "wait")
PROD_MODE = {"ca5439be83b3": "thread", "5b02ac883c80": "thread",
             "1d5bac550078": "comment", "0d75b20b5f83": "comment"}
STOP = {"the", "a", "an", "and", "of", "with", "w", "on", "in", "at", "their", "to", "for"}


# ---------------------------------------------------------------- helpers
def bucket(v):
    """Model float (-1..1) -> 7-point level. 0.3/0.33 -> 1, 0.5/0.6/0.67 -> 2, 0.85/1 -> 3."""
    if v is None or isinstance(v, bool):
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    v = max(-1.0, min(1.0, v))
    lvl = math.floor(abs(v) * 3 + 0.5)
    return int(math.copysign(lvl, v)) if lvl else 0


def fnum(v):
    try:
        return None if v is None or isinstance(v, bool) else float(v)
    except (TypeError, ValueError):
        return None


def sign(x):
    return (x > 0) - (x < 0)


def tokens(s):
    s = normalize_entity(s or "")
    return {t[:-1] if t.endswith("s") and len(t) > 3 else t for t in s.split() if t not in STOP}


def lenient_same(a, b):
    """Dish / term match: normalized substring either way, or token overlap >= half of the shorter."""
    na, nb = normalize_entity(a or ""), normalize_entity(b or "")
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) >= max(1, math.ceil(min(len(ta), len(tb)) / 2))


def spearman(xs, ys):
    if len(xs) < 3:
        return None
    def ranks(a):
        order = sorted(range(len(a)), key=lambda i: a[i])
        r = [0.0] * len(a)
        i = 0
        while i < len(a):
            j = i
            while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def ratio(a, b):
    return a / b if b else None


def prf(tp, fp, fn):
    p, r = ratio(tp, tp + fp), ratio(tp, tp + fn)
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return p, r, f


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_map(name):
    path = os.path.join(HERE, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------------- matching
def model_key(m, alias):
    k = normalize_entity(m.get("restaurant_raw") or "")
    return alias.get(k, k)


def fuzzy(a, b):
    """Extra trailing words ('lindustrie' / 'lindustrie pizzeria') or a possessive s ('mangias' / 'mangia')."""
    return a.startswith(b + " ") or b.startswith(a + " ") or a == b + "s" or b == a + "s"


# Scorer fixes (eval/bench_v6/DIAGNOSIS.md, eval/CONVENTIONS.md), on by default.
# `fixes=False` (score.py --legacy-scorer) reproduces the numbers scored before them.
# The three fixes:
#   * street words match their short forms ("2nd avenue deli" = "2nd ave deli");
#   * a v6 mention whose overall verdict is negative counts as a negative
#     mention even when no aspect is ("most overrated restaurant… good pizza");
#   * an unmatched v6 mention named from context with no opinion (a reply that
#     only asks about a place, or names it in passing) is not a false positive.
#     The owner counts these as mentions; the v1/v2 gold mostly lacks them
#     (CONVENTIONS.md lists the gold patches that would add them).
STREET_WORDS = {"avenue": "ave", "street": "st", "road": "rd", "boulevard": "blvd", "place": "pl",
                "parkway": "pkwy", "square": "sq"}
NEGATIVE_LEVELS = ("negative", "very_negative")


def street_norm(key):
    return " ".join(STREET_WORDS.get(t, t) for t in key.split())


def match(gold_ms, model_ms, fixes=True):
    """Greedy one-to-one matching. Returns [(g, m, how)], unmatched model mentions."""
    nk = street_norm if fixes else (lambda k: k)
    pairs, used, taken = [], set(), set()
    order = sorted(range(len(gold_ms)), key=lambda i: (gold_ms[i]["ambiguous"] or gold_ms[i].get("out_of_scope", False)))
    for how in ("exact", "fuzzy"):
        for gi in order:
            if gi in taken:
                continue
            g = gold_ms[gi]
            keys = {nk(x) for x in (g["canonical_key"], *g["accept_keys"])}
            for mi, m in enumerate(model_ms):
                if mi in used:
                    continue
                k = nk(m["_key"])
                if (how == "exact" and k in keys) or (how == "fuzzy" and any(fuzzy(k, x) for x in keys)):
                    pairs.append((g, m, how))
                    used.add(mi)
                    taken.add(gi)
                    break
    return pairs, [m for i, m in enumerate(model_ms) if i not in used]


def is_required(g):
    return not g["ambiguous"] and not g.get("out_of_scope", False)


def gold_negative(g):
    return any(v is not None and v <= -1 for v in g["aspects"].values())


def model_negative(m, fixes=True):
    asp = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
    if any((bucket(asp.get(a)) or 0) < 0 for a in ASPECTS):
        return True
    if fixes and ((m.get("v6") or {}).get("overall") in NEGATIVE_LEVELS):
        return True
    return bool(m.get("is_negated"))


def context_reference(m):
    """A v6 mention named from context with no opinion: a question or aside in a reply."""
    v = m.get("v6") or {}
    return v.get("named_in") == "context" and v.get("opinion") == "none"


def model_value_complaint(m):
    if "value_complaint" in m:
        return bool(m.get("value_complaint"))
    asp = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
    return (bucket(asp.get("value")) or 0) < 0


def model_dish_entries(m):
    ds = m.get("dish_sentiment")
    return ds if isinstance(ds, list) else None


# ---------------------------------------------------------------- scoring
# Five-level views (the owner's scale): gold's 7 points collapse to 5, with
# +-3 -> very, +-1/+-2 -> positive/negative, 0 -> neutral. A model float is
# bucketed to 7 points first, so v6's levels and the old prompts' floats
# collapse the same way.
FIVE = {3: "very_positive", 2: "positive", 1: "positive", 0: "neutral",
        -1: "negative", -2: "negative", -3: "very_negative"}
V6_LEVEL = {"very_positive": 3, "positive": 2, "neutral": 0, "negative": -2, "very_negative": -3}


def five(level7):
    return None if level7 is None else FIVE[level7]


def verdict7(aspects):
    """A 7-point verdict from aspect levels: food when set (the old convention puts
    generic verdicts there), else the strongest other aspect, negative on a tie."""
    if aspects.get("food") is not None:
        return aspects["food"]
    vals = [v for v in aspects.values() if v is not None]
    return min(vals, key=lambda v: (-abs(v), v)) if vals else None


def model_verdict7(m):
    v6 = m.get("v6")
    if v6 is not None:
        return V6_LEVEL.get(v6.get("overall"))
    asp = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
    return verdict7({a: bucket(asp.get(a)) for a in ASPECTS})


def gold_opinion(g):
    """'none' (nothing judged), 'stated' (anything beyond a lone +1 food), or None
    where the gold can't tell an endorsement from mild praise (a lone +1 food)."""
    asp = g["aspects"]
    if all(v is None for v in asp.values()) and not any(d["level"] is not None for d in g.get("dish_sentiment", [])):
        return "none"
    if asp.get("food") == 1 and all(v is None for k, v in asp.items() if k != "food"):
        return None
    return "stated"


def model_opinion(m):
    v6 = m.get("v6")
    if v6 is not None:
        return v6.get("opinion")
    asp = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
    lv = {a: bucket(asp.get(a)) for a in ASPECTS}
    if all(v is None for v in lv.values()):
        return "none"
    if lv["food"] == 1 and all(v is None for k, v in lv.items() if k != "food"):
        return "endorse"
    return "stated"


class Acc:
    def __init__(self):
        self.c = collections.Counter()
        self.food_pairs = []
        self.raw_food = collections.Counter()
        self.levels = collections.Counter()
        self.food_conf = collections.Counter()

    def add(self, o, w=1):
        for k, v in o.c.items():
            self.c[k] += v if w == 1 else v * w
        if w == 1:
            self.food_pairs += o.food_pairs
            self.raw_food.update(o.raw_food)
            self.levels.update(o.levels)
            self.food_conf.update(o.food_conf)


def model_mentions(preds, alias, drop_chains):
    """A model's mentions for one comment, keyed (copied with _key), with
    nameless entries and repeats of a key dropped, and chains too if asked."""
    ms, seen = [], set()
    for m in preds or []:
        if not isinstance(m, dict) or not (m.get("restaurant_raw") or "").strip():
            continue
        m = dict(m, _key=model_key(m, alias))
        if not m["_key"] or m["_key"] in seen:
            continue
        if drop_chains and m["_key"] in CHAINS:
            continue
        seen.add(m["_key"])
        ms.append(m)
    return ms


def score_comment(gold, preds, mode, alias, excluded, drop_chains, fixes=True):
    a = Acc()
    ms = model_mentions(preds, alias, drop_chains)
    emits_dishes = any(model_dish_entries(m) is not None for m in ms)
    gms = [g for g in gold["mentions"] if not (drop_chains and g["canonical_key"] in CHAINS)]
    required = [g for g in gms if is_required(g)]
    pairs, fps = match(gms, ms, fixes)
    fps = [m for m in fps if m["_key"] not in excluded
           and not (fixes and context_reference(m))]
    rk = f"resolvable_{mode}_mode"
    matched = {id(g): m for g, m, _ in pairs}

    a.c["comments"] += 1
    if required:
        a.c["comments_with_gold"] += 1
        if not [m for m in ms if m["_key"] not in excluded]:
            a.c["dropped_comments"] += 1
    elif fps:
        a.c["false_alarm_comments"] += 1
    a.c["emits_dishes"] += emits_dishes

    for g in required:
        gap = g.get(rk) is False
        m = matched.get(id(g))
        a.c["tp" if m else "fn"] += 1
        if not m:
            a.c["fn_context_gap" if gap else "fn_model_error"] += 1
        if g["closed"]:
            a.c["closed_n"] += 1
            a.c["closed_hit"] += bool(m)
        if not any(v is not None for v in g["aspects"].values()):
            a.c["reference_n"] += 1
            a.c["reference_hit"] += bool(m)
        if gold_negative(g):
            a.c["neg_mention_n"] += 1
            hit = bool(m) and model_negative(m, fixes)
            a.c["neg_mention_hit"] += hit
            if not hit:
                a.c["neg_miss_context_gap" if gap else "neg_miss_model_error"] += 1
            if m and not model_negative(m, fixes):
                asp = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
                if any((bucket(asp.get(x)) or 0) > 0 for x in ASPECTS):
                    a.c["neg_to_positive"] += 1
        if g.get("value_complaint"):
            a.c["vc_n"] += 1
            a.c["vc_hit"] += bool(m) and model_value_complaint(m)
        for d in g.get("dish_sentiment", []):
            if (d["level"] is not None and d["level"] <= -1) or d["avoid"]:
                a.c["dishneg_n"] += 1
                ents = model_dish_entries(m) if m else None
                if ents:
                    ok = any(isinstance(e, dict) and lenient_same(e.get("dish"), d["dish"]) and
                             (((bucket(e.get("level")) or 0) < 0) or bool(e.get("avoid"))) for e in ents)
                    a.c["dishneg_hit"] += ok
        terms = g.get("search_terms") or []
        if terms:
            pool = []
            if m:
                pool = [str(x) for x in (m.get("descriptors") or []) + (m.get("dishes") or [])]
                pool += [str(e.get("dish")) for e in (model_dish_entries(m) or []) if isinstance(e, dict)]
            for t in terms:
                a.c["terms_n"] += 1
                a.c["terms_hit"] += any(lenient_same(t, p) for p in pool)
    a.c["fp"] += len(fps)
    a.c["fuzzy_matches"] += sum(1 for _, _, how in pairs if how == "fuzzy")

    for g, m, _ in pairs:
        if not is_required(g):
            continue
        gap = g.get(rk) is False
        asp = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
        for name in ASPECTS + ("expensiveness",):
            gv = g["expensiveness"] if name == "expensiveness" else g["aspects"].get(name)
            ok = {gv, *g["aspect_alternatives"].get(name, [])}
            raw = fnum(m.get("expensiveness")) if name == "expensiveness" else fnum(asp.get(name))
            mv = bucket(raw)
            if name == "food" and raw is not None:
                a.raw_food[round(raw, 2)] += 1
            if mv is not None and name != "expensiveness":
                a.levels[mv] += 1
            g_present, m_present = gv is not None, mv is not None
            if m_present != g_present and ((None in ok) if not m_present else any(x is not None for x in ok)):
                g_present = m_present
            a.c[f"pres_tp_{name}"] += g_present and m_present
            a.c[f"pres_fp_{name}"] += (not g_present) and m_present
            a.c[f"pres_fn_{name}"] += g_present and not m_present
            vals = [x for x in ok if x is not None]
            if m_present and vals:
                near = min(vals, key=lambda x: abs(raw * 3 - x))
                a.c[f"n_{name}"] += 1
                a.c[f"exact_{name}"] += mv in vals
                a.c[f"within1_{name}"] += min(abs(mv - x) for x in vals) <= 1
                a.c[f"sign_{name}"] += sign(mv) == sign(near)
                a.c[f"abserr_{name}"] += min(abs(raw * 3 - x) for x in vals)
                if name != "expensiveness":
                    a.c["sign_n"] += 1
                    a.c["sign_ok"] += sign(mv) == sign(near)
                    if sign(mv) != sign(near):
                        a.c["sign_err_context_gap" if gap else "sign_err_model_error"] += 1
                    if near < 0:
                        a.c["softened_n"] += 1
                        a.c["softened"] += mv > near
                if name == "food":
                    a.food_pairs.append((raw, gv if gv is not None else near))
        # five-level agreement per aspect, the food confusion table, the overall verdict,
        # and the opinion type where the gold can tell
        for name in ASPECTS:
            gv = g["aspects"].get(name)
            mv = bucket(asp.get(name))
            if name == "food":
                a.food_conf[(five(gv) or "null", five(mv) or "null")] += 1
            if gv is not None and mv is not None:
                ok5 = {five(x) for x in (gv, *g["aspect_alternatives"].get(name, [])) if x is not None}
                a.c[f"l5_n_{name}"] += 1
                a.c[f"l5_ok_{name}"] += five(mv) in ok5
        gvd, mvd = verdict7(g["aspects"]), model_verdict7(m)
        if gvd is not None and mvd is not None:
            a.c["ov_n"] += 1
            a.c["ov_ok5"] += five(gvd) == five(mvd)
            a.c["ov_sign"] += sign(gvd) == sign(mvd)
        go, mo = gold_opinion(g), model_opinion(m)
        if go is not None and mo is not None:
            a.c[f"op_{go}_n"] += 1
            a.c[f"op_{go}_ok"] += mo == go
        if "is_negated" not in g["uncertain_fields"]:
            a.c["neg_n"] += 1
            a.c["neg_ok"] += bool(m.get("is_negated")) == bool(g["is_negated"])
            if g["is_negated"]:
                a.c["neg_pos_n"] += 1
                a.c["neg_pos_hit"] += bool(m.get("is_negated"))
        if g["is_firsthand"] is not None and "is_firsthand" not in g["uncertain_fields"]:
            a.c["first_n"] += 1
            a.c["first_ok"] += bool(m.get("is_firsthand")) == bool(g["is_firsthand"])
    return a


def summarize(a, dish_capable):
    c = a.c
    p, r, f = prf(c["tp"], c["fp"], c["fn"])
    out = {
        "comments": c["comments"],
        "drop_rate": ratio(c["dropped_comments"], c["comments_with_gold"]),
        "mention_recall": r,
        "negative_mention_recall": ratio(c["neg_mention_hit"], c["neg_mention_n"]),
        "value_complaint_recall": ratio(c["vc_hit"], c["vc_n"]),
        "dish_negative_recall": ratio(c["dishneg_hit"], c["dishneg_n"]) if dish_capable else "n/a",
        "sign_accuracy": ratio(c["sign_ok"], c["sign_n"]),
        "levels_used": len(a.levels) or None,
        # --- everything else
        "mention_precision": p, "mention_f1": f,
        "tp": c["tp"], "fp": c["fp"], "fn": c["fn"],
        "fn_model_error": c["fn_model_error"], "fn_context_gap": c["fn_context_gap"],
        "neg_miss_model_error": c["neg_miss_model_error"], "neg_miss_context_gap": c["neg_miss_context_gap"],
        "negative_to_positive_rate": ratio(c["neg_to_positive"], c["neg_mention_n"]),
        "negative_softened_rate": ratio(c["softened"], c["softened_n"]),
        "reference_mention_recall": ratio(c["reference_hit"], c["reference_n"]),
        "closed_mention_recall": ratio(c["closed_hit"], c["closed_n"]),
        "search_terms_recall": ratio(c["terms_hit"], c["terms_n"]),
        "neg_mention_n": c["neg_mention_n"], "vc_n": c["vc_n"], "dishneg_n": c["dishneg_n"],
        "false_alarm_comments": c["false_alarm_comments"], "fuzzy_matches": c["fuzzy_matches"],
        "sign_err_model_error": c["sign_err_model_error"], "sign_err_context_gap": c["sign_err_context_gap"],
        "is_negated_acc": ratio(c["neg_ok"], c["neg_n"]),
        "is_negated_recall": ratio(c["neg_pos_hit"], c["neg_pos_n"]),
        "is_firsthand_acc": ratio(c["first_ok"], c["first_n"]),
    }
    for name in ASPECTS + ("expensiveness",):
        _, _, pf = prf(c[f"pres_tp_{name}"], c[f"pres_fp_{name}"], c[f"pres_fn_{name}"])
        n = c[f"n_{name}"]
        out[f"{name}_presence_f1"] = pf
        out[f"{name}_n"] = n
        out[f"{name}_sign_acc"] = ratio(c[f"sign_{name}"], n)
        out[f"{name}_exact_acc"] = ratio(c[f"exact_{name}"], n)
        out[f"{name}_within1_acc"] = ratio(c[f"within1_{name}"], n)
        out[f"{name}_mae_levels"] = ratio(c[f"abserr_{name}"], n)
    if a.food_pairs:
        out["food_spearman"] = spearman([x for x, _ in a.food_pairs], [y for _, y in a.food_pairs])
    tot = sum(a.raw_food.values())
    out["food_distinct_values"] = len(a.raw_food) or None
    out["food_share_0.3_or_0.6"] = ratio(sum(n for v, n in a.raw_food.items() if v in (0.3, 0.6)), tot)
    out["food_top_values"] = ", ".join(f"{v}:{n}" for v, n in a.raw_food.most_common(6))
    out["level_histogram"] = " ".join(f"{k:+d}:{a.levels[k]}" for k in sorted(a.levels))
    for name in ASPECTS:
        out[f"{name}_5level_acc"] = ratio(c[f"l5_ok_{name}"], c[f"l5_n_{name}"])
    out["overall_5level_agree"] = ratio(c["ov_ok5"], c["ov_n"])
    out["overall_sign_agree"] = ratio(c["ov_sign"], c["ov_n"])
    out["opinion_type_acc"] = ratio(c["op_none_ok"] + c["op_stated_ok"], c["op_none_n"] + c["op_stated_n"])
    out["opinion_none_acc"] = ratio(c["op_none_ok"], c["op_none_n"])
    out["opinion_stated_acc"] = ratio(c["op_stated_ok"], c["op_stated_n"])
    out["food_confusion"] = {f"{g}->{m}": n for (g, m), n in sorted(a.food_conf.items())}
    return out


# ---------------------------------------------------------------- runs
def load_run(path, items):
    recs = load_jsonl(path)
    reps = collections.defaultdict(dict)
    covered = collections.defaultdict(set)
    stats = {"calls": 0, "errors": 0, "json_bad": 0, "cost": 0.0, "latency": [],
             "prompt_tokens": 0, "completion_tokens": 0}
    modes = collections.Counter()
    chunk_cover = {}
    for it in items:
        if it["kind"] == "comment":
            t = it["inputs"]["thread"]
            chunk_cover[f"thread:{it['thread_id']}:{t['chunk_index']}"] = set(t["short_ids"].values())
        else:
            for ch in it["thread_chunks"]:
                chunk_cover[f"thread:{it['thread_id']}:{ch['chunk_index']}"] = set(ch["short_ids"].values())
    for r in recs:
        stats["calls"] += 1
        modes[r.get("mode")] += 1
        if r.get("error"):
            stats["errors"] += 1
            continue
        if not r.get("json_ok"):
            stats["json_bad"] += 1
        u = r.get("usage") or {}
        stats["cost"] += float(u.get("cost") or 0)
        stats["prompt_tokens"] += u.get("prompt_tokens") or 0
        stats["completion_tokens"] += u.get("completion_tokens") or 0
        if r.get("latency_s") is not None:
            stats["latency"].append(r["latency_s"])
        for cid, ms in (r.get("mentions_by_comment") or {}).items():
            # v6 output is translated to the gold's shape here, once, so every
            # scorer downstream (this file, compare_v4, next_round) reads it.
            reps[r["rep"]].setdefault(cid, []).extend(v6_adapter.adapt_all(ms))
        key = r["call_key"]
        if key.startswith(("comment:", "stored:")):
            covered[r["rep"]].add(key.split(":", 1)[1])
        elif key.startswith("thread:"):
            covered[r["rep"]].update(chunk_cover.get(key, ()))
    return reps, covered, stats, modes.most_common(1)[0][0] if modes else None


def evaluate(gold, items, run, alias, excluded, drop_chains, stats_path, fixes=True):
    by_item = {it["item_id"]: it for it in items}
    strata_pop = {}
    if stats_path and os.path.exists(stats_path):
        with open(stats_path, encoding="utf-8") as f:
            strata_pop = json.load(f).get("strata_population", {})
    reps, covered, cstats, mode = run
    per_rep = []
    for rep in sorted(reps) or [0]:
        preds = reps.get(rep, {})
        dish_capable = any(isinstance(m, dict) and isinstance(m.get("dish_sentiment"), list)
                           for ms in preds.values() for m in ms)
        scopes = collections.defaultdict(Acc)
        strata = collections.defaultdict(Acc)
        strata_n = collections.Counter()
        missing = 0
        for g in gold:
            it = by_item.get(g["item_id"])
            cid = g["comment_id"]
            if it is None or cid not in covered.get(rep, set()):
                missing += 1
                continue
            m = mode
            if mode == "stored":
                ph = next((x.get("prompt_hash") for x in preds.get(cid, []) if isinstance(x, dict)), None)
                prod = it.get("production") or next((c["production"] for c in it.get("comments", [])
                                                     if c["comment_id"] == cid), {})
                m = PROD_MODE.get(ph) or prod.get("mode") or "thread"
            a = score_comment(g, preds.get(cid, []), m, alias, excluded, drop_chains, fixes)
            groups = list(it.get("risk_groups", [])) + list(it.get("weaknesses", []))
            if it.get("split"):
                groups.append(f"split_{it['split']}")
            for scope in ["overall", *groups]:
                scopes[scope].add(a)
            if it["kind"] == "comment":
                scopes["single_comments"].add(a)
                st = it.get("stratum", "none")
                strata[st].add(a)
                strata_n[st] += 1
        rw, covered_pop = Acc(), 0
        for st, acc in strata.items():
            n_pop = strata_pop.get(st)
            if n_pop:
                rw.add(acc, n_pop / strata_n[st])
                covered_pop += n_pop
        res = {k: summarize(v, dish_capable) for k, v in scopes.items()}
        if strata_pop:
            res["reweighted"] = summarize(rw, dish_capable)
            res["reweighted"]["population_share_covered"] = ratio(covered_pop, sum(strata_pop.values()))
        res["_missing"] = missing
        per_rep.append(res)

    flips = None
    if len(reps) > 1:
        status = collections.defaultdict(set)
        for rep, preds in reps.items():
            for g in gold:
                ms = [dict(m, _key=model_key(m, alias)) for m in preds.get(g["comment_id"], []) if isinstance(m, dict)]
                pairs, _ = match(g["mentions"], ms)
                got = {id(x) for x, _, _ in pairs}
                for i, gm in enumerate(g["mentions"]):
                    if is_required(gm):
                        status[(g["comment_id"], i)].add(id(gm) in got)
        flips = ratio(sum(len(v) > 1 for v in status.values()), len(status))
    return per_rep, cstats, flips, mode


# ---------------------------------------------------------------- report
HEADLINE = ["drop_rate", "mention_recall", "negative_mention_recall", "value_complaint_recall",
            "dish_negative_recall", "sign_accuracy", "levels_used"]
SECONDARY = ["comments", "mention_precision", "mention_f1", "fn_model_error", "fn_context_gap",
             "neg_miss_model_error", "neg_miss_context_gap", "negative_to_positive_rate",
             "negative_softened_rate", "reference_mention_recall", "closed_mention_recall",
             "search_terms_recall", "expensiveness_presence_f1", "expensiveness_exact_acc",
             "expensiveness_within1_acc", "food_presence_f1", "food_exact_acc", "food_mae_levels",
             "food_spearman", "food_distinct_values", "food_share_0.3_or_0.6", "is_negated_acc",
             "is_negated_recall", "is_firsthand_acc", "sign_err_model_error", "sign_err_context_gap",
             "neg_mention_n", "vc_n", "dishneg_n"]


def fmt(v):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.3f}" if not v.is_integer() or abs(v) < 1 else f"{v:.1f}"
    return str(v)


def cell(per_rep, scope, metric):
    vals = [r[scope].get(metric) for r in per_rep if scope in r]
    vals = [v for v in vals if v is not None]
    if not vals:
        return "–"
    if len(vals) > 1 and all(isinstance(v, (int, float)) for v in vals):
        return f"{statistics.fmean(vals):.3f}±{statistics.pstdev(vals):.3f}"
    return fmt(vals[0])


def report(run_path, per_rep, cstats, flips, mode, out_dir, tag=""):
    name = os.path.basename(run_path).removesuffix(".jsonl") + tag
    date = datetime.date.today().isoformat()
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"{date}__{name}.md")
    csv_path = os.path.join(out_dir, f"{date}__{name}.csv")
    r0 = per_rep[0]
    lat = sorted(cstats["latency"]) or [0]
    main = [s for s in ("overall", "reweighted", "single_comments", "random", "threads") if s in r0]
    groups = sorted(k for k in r0 if k not in main and not k.startswith("_"))
    lines = [f"# {name}", "",
             f"mode: {mode}; reps: {len(per_rep)}; labeled comments not in run: {r0['_missing']}",
             f"calls {cstats['calls']}, errors {cstats['errors']}, invalid JSON {cstats['json_bad']}, "
             f"cost ${cstats['cost']:.4f}, tokens {cstats['prompt_tokens']:,} in / {cstats['completion_tokens']:,} out, "
             f"latency p50 {lat[len(lat)//2]:.1f}s p90 {lat[int(len(lat)*0.9)]:.1f}s"]
    if flips is not None:
        lines.append(f"required-mention match status flips across reps: {flips:.3f}")
    lines += ["", "## Headline (owner priorities, in order)", "",
              "| metric | " + " | ".join(main) + " |", "|---" * (len(main) + 1) + "|"]
    labels = {"drop_rate": "a. comment drop rate (lower is better)", "mention_recall": "b. mention recall",
              "negative_mention_recall": "c. negative-mention recall", "value_complaint_recall": "d. value-complaint recall",
              "dish_negative_recall": "e. dish-negative recall", "sign_accuracy": "f. sign accuracy",
              "levels_used": "f. aspect levels used (of 7)"}
    for m in HEADLINE:
        lines.append(f"| {labels[m]} | " + " | ".join(cell(per_rep, s, m) for s in main) + " |")
    lines += ["", "## Everything else", "", "| metric | " + " | ".join(main) + " |", "|---" * (len(main) + 1) + "|"]
    for m in SECONDARY:
        lines.append(f"| {m} | " + " | ".join(cell(per_rep, s, m) for s in main) + " |")
    lines += ["", f"food values (rep 0, overall): {r0['overall'].get('food_top_values') or '–'}",
              f"aspect level histogram (rep 0, overall): {r0['overall'].get('level_histogram') or '–'}", "",
              "## By group", "", "| metric | " + " | ".join(groups) + " |", "|---" * (len(groups) + 1) + "|"]
    for m in HEADLINE + ["comments", "mention_precision", "fn_model_error", "fn_context_gap"]:
        lines.append(f"| {m} | " + " | ".join(cell(per_rep, s, m) for s in groups) + " |")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["run", "rep", "scope", "metric", "value"])
        for rep, r in enumerate(per_rep):
            for s, d in r.items():
                if isinstance(d, dict):
                    for k, v in d.items():
                        w.writerow([name, rep, s, k, v])
    return md_path, csv_path


def gold_as_run(gold):
    """A perfect run built from gold, in the rubric prompt's output shape."""
    preds, covered = {}, set()
    for g in gold:
        covered.add(g["comment_id"])
        preds[g["comment_id"]] = [{
            "restaurant_raw": m["restaurant_raw"],
            "aspects": {k: (None if v is None else v / 3) for k, v in m["aspects"].items()},
            "expensiveness": None if m["expensiveness"] is None else m["expensiveness"] / 3,
            "is_negated": m["is_negated"], "is_firsthand": bool(m["is_firsthand"]),
            "value_complaint": m["value_complaint"],
            "dish_sentiment": [{"dish": d["dish"], "level": None if d["level"] is None else d["level"] / 3,
                                "avoid": d["avoid"]} for d in m["dish_sentiment"]],
            "descriptors": m["search_terms"] + m["descriptors"], "dishes": m["dishes"],
        } for m in g["mentions"]]
    stats = {"calls": 0, "errors": 0, "json_bad": 0, "cost": 0.0, "latency": [], "prompt_tokens": 0, "completion_tokens": 0}
    return {0: preds}, {0: covered}, stats, "comment"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--gold", default=os.path.join(HERE, "gold.jsonl"))
    ap.add_argument("--items", default=os.path.join(HERE, "items.jsonl"))
    ap.add_argument("--stats", default=os.path.join(HERE, "sampling_stats.json"),
                    help="strata populations for reweighting ('' to skip)")
    ap.add_argument("--drop-chains", action="store_true", help="drop chains.txt keys on both sides, as production does")
    ap.add_argument("--legacy-scorer", action="store_true",
                    help="score without the scorer fixes, reproducing numbers from before them")
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    ap.add_argument("--tag", default="", help="suffix for result file names")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    gold = load_jsonl(args.gold)
    items = load_jsonl(args.items)
    alias, excluded = load_map("alias_overrides.json"), load_map("excluded_entities.json")
    if args.self_test:
        per_rep, _, _, _ = evaluate(gold, items, gold_as_run(gold), alias, excluded, False, args.stats)
        o = per_rep[0]["overall"]
        print(json.dumps({k: o[k] for k in HEADLINE + ["mention_precision", "food_exact_acc", "search_terms_recall",
                                                        "expensiveness_exact_acc"]}, indent=1))
        assert o["drop_rate"] == 0 and o["mention_recall"] == 1 and o["mention_precision"] == 1
        assert o["negative_mention_recall"] == 1 and o["value_complaint_recall"] == 1 and o["dish_negative_recall"] == 1
        assert o["sign_accuracy"] == 1 and o["food_exact_acc"] == 1 and o["search_terms_recall"] == 1
        print("self-test ok")
        return
    for path in args.runs:
        run = load_run(path, items)
        per_rep, cstats, flips, mode = evaluate(gold, items, run, alias, excluded, args.drop_chains, args.stats,
                                                fixes=not args.legacy_scorer)
        md, cs = report(path, per_rep, cstats, flips, mode, args.out, args.tag)
        print(f"{path}\n  -> {md}\n  -> {cs}")


if __name__ == "__main__":
    main()
