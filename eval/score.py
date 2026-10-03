"""Score run files against eval/gold.jsonl.

    python eval/score.py eval/runs/<model>__<hash>__<mode>.jsonl [more runs ...]
    python eval/score.py eval/runs/production__stored__all.jsonl --drop-chains
    python eval/score.py --self-test            # gold scored against itself

Writes eval/results/<date>__<run>.md and .csv (one per run file).
Definitions are in eval/README.md ("Scoring"). Summary:

- Model names are keyed with extract.normalize_entity, then alias_overrides
  (snapshot in eval/alias_overrides.json). A model mention matches a gold
  mention when its key equals the gold canonical_key or one of its
  accept_keys; failing that, when one key is the other plus extra trailing
  words ("lindustrie" vs "lindustrie pizzeria"), reported as a fuzzy match.
- ambiguous gold mentions are neither required nor penalised.
- Aspects are compared on the 7-point scale: model floats are bucketed with
  level = sign(v) * floor(|v| * 3 + 0.5). Any value in aspect_alternatives
  is also accepted.
- Errors on mentions the gold marks NOT resolvable in the run's mode are
  "context_gap"; the rest are "model_error".
- Reweighted figures use the single-comment items only: each stratum (the
  first risk group a comment matches, or "none") is weighted by its pool size
  over its labeled count (sampling_stats.json).
"""

import argparse
import collections
import csv
import datetime
import json
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from extract import CHAINS, normalize_entity  # noqa: E402

ASPECTS = ("food", "value", "service", "atmosphere", "wait")
PROD_MODE = {"ca5439be83b3": "thread", "5b02ac883c80": "thread",
             "1d5bac550078": "comment", "0d75b20b5f83": "comment"}


# ---------------------------------------------------------------- helpers
def bucket(v):
    """Model float (-1..1) -> 7-point level. 0.3 -> 1, 0.5/0.6 -> 2, 0.85 -> 3."""
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    v = max(-1.0, min(1.0, v))
    lvl = math.floor(abs(v) * 3 + 0.5)
    return int(math.copysign(lvl, v)) if lvl else 0


def sign(x):
    return (x > 0) - (x < 0)


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


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return p, r, f


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_alias():
    path = os.path.join(HERE, "alias_overrides.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------------- matching
def model_key(m, alias):
    k = normalize_entity(m.get("restaurant_raw") or "")
    return alias.get(k, k)


def fuzzy(a, b):
    return a.startswith(b + " ") or b.startswith(a + " ")


def match(gold_ms, model_ms):
    """Greedy one-to-one matching. Returns [(g, m, how)], unmatched model."""
    pairs, used = [], set()
    # required mentions first, so an ambiguous one cannot steal their match
    order = sorted(range(len(gold_ms)), key=lambda i: gold_ms[i]["ambiguous"])
    for how in ("exact", "fuzzy"):
        for gi in order:
            g = gold_ms[gi]
            if any(p[0] is g for p in pairs):
                continue
            keys = {g["canonical_key"], *g["accept_keys"]}
            for mi, m in enumerate(model_ms):
                if mi in used:
                    continue
                k = m["_key"]
                if (how == "exact" and k in keys) or (how == "fuzzy" and any(fuzzy(k, x) for x in keys)):
                    pairs.append((g, m, how))
                    used.add(mi)
                    break
    return pairs, [m for i, m in enumerate(model_ms) if i not in used]


# ---------------------------------------------------------------- scoring
class Acc:
    """Counters for one scope (overall, a risk group, a stratum)."""

    def __init__(self):
        self.c = collections.Counter()
        self.food_pairs = []           # (model float, gold level) for rank corr
        self.abs_err = []
        self.levels_model = collections.Counter()
        self.raw_values = collections.Counter()

    def add(self, other, w=1.0):
        for k, v in other.c.items():
            self.c[k] += v if w == 1 else v * w


def score_comment(gold, preds, mode, alias, drop_chains):
    """Counters for one comment. preds: list of model mention dicts."""
    a = Acc()
    ms = []
    seen = set()
    for m in preds or []:
        if not isinstance(m, dict) or not (m.get("restaurant_raw") or "").strip():
            continue
        m = dict(m, _key=model_key(m, alias))
        if not m["_key"] or (drop_chains and m["_key"] in CHAINS) or m["_key"] in seen:
            continue                          # production keeps one row per key
        seen.add(m["_key"])
        ms.append(m)
    gms = gold["mentions"]
    if drop_chains:
        gms = [g for g in gms if g["canonical_key"] not in CHAINS]
    required = [g for g in gms if not g["ambiguous"]]
    pairs, fps = match(gms, ms)
    rk = f"resolvable_{mode}_mode"

    a.c["comments"] += 1
    if required:
        a.c["comments_with_gold"] += 1
        if not ms:
            a.c["dropped_comments"] += 1
    elif ms and not pairs:
        a.c["false_alarm_comments"] += 1

    matched = {id(g) for g, _, _ in pairs}
    for g in required:
        if id(g) in matched:
            a.c["tp"] += 1
        else:
            a.c["fn"] += 1
            a.c["fn_context_gap" if g.get(rk) is False else "fn_model_error"] += 1
    a.c["fp"] += len(fps)
    a.c["fuzzy_matches"] += sum(1 for _, _, how in pairs if how == "fuzzy")

    for g, m, _ in pairs:
        if g["ambiguous"]:
            continue
        gap = g.get(rk) is False
        asp = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
        for name in ASPECTS:
            gv = g["aspects"].get(name)
            ok = {gv, *g["aspect_alternatives"].get(name, [])}
            raw = asp.get(name)
            mv = bucket(raw)
            if raw is not None:
                a.raw_values[(name, raw)] += 1
                if mv is not None:
                    a.levels_model[(name, mv)] += 1
            # presence, lenient: whichever state the model chose is fine if acceptable
            g_present = gv is not None
            m_present = mv is not None
            if m_present != g_present and ((None in ok) if not m_present else
                                           any(x is not None for x in ok)):
                g_present = m_present
            a.c[f"pres_tp_{name}"] += g_present and m_present
            a.c[f"pres_fp_{name}"] += (not g_present) and m_present
            a.c[f"pres_fn_{name}"] += g_present and not m_present
            vals = [x for x in ok if x is not None]
            if m_present and vals:
                near = min(vals, key=lambda x: abs(float(raw) * 3 - x))
                err = min(abs(float(raw) * 3 - x) for x in vals)
                a.c[f"val_n_{name}"] += 1
                a.c[f"val_exact_{name}"] += mv in vals
                a.c[f"val_within1_{name}"] += min(abs(mv - x) for x in vals) <= 1
                a.c[f"val_sign_{name}"] += sign(mv) == sign(near)
                a.c[f"val_abserr_{name}"] += err
                if near < 0:
                    a.c["neg_gold_n"] += 1
                    a.c["neg_softened"] += mv > near
                a.c["sign_err_context_gap" if gap else "sign_err_model_error"] += sign(mv) != sign(near)
                if name == "food":
                    a.food_pairs.append((float(raw), gv if gv is not None else near))
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


def summarize(a):
    c = a.c
    p, r, f = prf(c["tp"], c["fp"], c["fn"])
    out = {
        "comments": c["comments"],
        "drop_rate": c["dropped_comments"] / c["comments_with_gold"] if c["comments_with_gold"] else None,
        "false_alarm_comments": c["false_alarm_comments"],
        "mention_precision": p, "mention_recall": r, "mention_f1": f,
        "tp": c["tp"], "fp": c["fp"], "fn": c["fn"],
        "fn_model_error": c["fn_model_error"], "fn_context_gap": c["fn_context_gap"],
        "fuzzy_matches": c["fuzzy_matches"],
        "aspect_sign_err_model_error": c["sign_err_model_error"],
        "aspect_sign_err_context_gap": c["sign_err_context_gap"],
    }
    for name in ASPECTS:
        _, _, pf = prf(c[f"pres_tp_{name}"], c[f"pres_fp_{name}"], c[f"pres_fn_{name}"])
        n = c[f"val_n_{name}"]
        out[f"{name}_presence_f1"] = pf
        out[f"{name}_n"] = n
        out[f"{name}_sign_acc"] = c[f"val_sign_{name}"] / n if n else None
        out[f"{name}_exact_acc"] = c[f"val_exact_{name}"] / n if n else None
        out[f"{name}_within1_acc"] = c[f"val_within1_{name}"] / n if n else None
        out[f"{name}_mae_levels"] = c[f"val_abserr_{name}"] / n if n else None
    out["negative_softened_rate"] = c["neg_softened"] / c["neg_gold_n"] if c["neg_gold_n"] else None
    out["is_negated_acc"] = c["neg_ok"] / c["neg_n"] if c["neg_n"] else None
    out["is_negated_recall"] = c["neg_pos_hit"] / c["neg_pos_n"] if c["neg_pos_n"] else None
    out["is_firsthand_acc"] = c["first_ok"] / c["first_n"] if c["first_n"] else None
    if a.food_pairs:
        out["food_spearman"] = spearman([x for x, _ in a.food_pairs], [y for _, y in a.food_pairs])
    food_raw = collections.Counter({v: n for (asp, v), n in a.raw_values.items() if asp == "food"})
    out["food_distinct_values"] = len(food_raw) or None
    out["food_distinct_levels"] = len({lvl for (asp, lvl) in a.levels_model if asp == "food"}) or None
    tot = sum(food_raw.values())
    out["food_share_0.3_or_0.6"] = (sum(n for v, n in food_raw.items() if v in (0.3, 0.6)) / tot) if tot else None
    out["food_top_values"] = ", ".join(f"{v}:{n}" for v, n in food_raw.most_common(6))
    return out


# ---------------------------------------------------------------- runs
def load_run(path):
    """{rep: {comment_id: [mentions]}}, plus call stats and the mode."""
    recs = load_jsonl(path)
    reps = collections.defaultdict(dict)
    covered = collections.defaultdict(set)
    stats = {"calls": 0, "errors": 0, "json_bad": 0, "cost": 0.0, "latency": [],
             "prompt_tokens": 0, "completion_tokens": 0}
    modes = collections.Counter()
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
            reps[r["rep"]].setdefault(cid, []).extend(ms)
        # every comment the call covered, including ones with no mentions
        covered[r["rep"]].update(r.get("covered_comments") or [])
        if r["call_key"].startswith(("comment:", "stored:")):
            covered[r["rep"]].add(r["call_key"].split(":", 1)[1])
    return reps, covered, stats, modes.most_common(1)[0][0] if modes else None


def comments_of_call_keys(items):
    """thread:<tid>:<chunk> -> comment ids, so a thread call covers its chunk."""
    m = {}
    for it in items:
        if it["kind"] == "comment":
            t = it["inputs"]["thread"]
            m[f"thread:{it['thread_id']}:{t['chunk_index']}"] = set(t["short_ids"].values())
        else:
            for c in it["thread_chunks"]:
                m[f"thread:{it['thread_id']}:{c['chunk_index']}"] = set(c["short_ids"].values())
    return m


def evaluate(gold, items, run_path, alias, drop_chains, run=None):
    by_item = {it["item_id"]: it for it in items}
    stats_path = os.path.join(HERE, "sampling_stats.json")
    strata_pop = {}
    if os.path.exists(stats_path):
        with open(stats_path, encoding="utf-8") as f:
            strata_pop = json.load(f).get("strata_population", {})

    if run is None:
        reps, covered, cstats, mode = load_run(run_path)
        chunk_cover = comments_of_call_keys(items)
        for r in load_jsonl(run_path):
            if r["call_key"].startswith("thread:") and not r.get("error"):
                covered[r["rep"]].update(chunk_cover.get(r["call_key"], ()))
    else:
        reps, covered, cstats, mode = run

    per_rep = []
    for rep in sorted(reps) or [0]:
        preds = reps.get(rep, {})
        scopes = collections.defaultdict(Acc)
        strata = collections.defaultdict(Acc)
        strata_n = collections.Counter()
        missing = 0
        for g in gold:
            it = by_item[g["item_id"]]
            cid = g["comment_id"]
            if cid not in covered.get(rep, set()):
                missing += 1          # never sent / errored: not counted as a drop
                continue
            m = mode
            if mode == "stored":
                m = PROD_MODE.get(next((x.get("prompt_hash") for x in preds.get(cid, [])), None)) or \
                    it.get("production", {}).get("mode") or "thread"
            a = score_comment(g, preds.get(cid, []), m, alias, drop_chains)
            groups = it["risk_groups"] if it["kind"] == "comment" else it["risk_groups"]
            for scope in ["overall", *groups]:
                s = scopes[scope]
                s.add(a)
                s.food_pairs += a.food_pairs
                s.raw_values.update(a.raw_values)
                s.levels_model.update(a.levels_model)
            if it["kind"] == "comment":
                st = it.get("stratum", "none")
                strata[st].add(a)
                strata[st].food_pairs += a.food_pairs
                strata_n[st] += 1
        # population reweighting over strata that have labels
        rw = Acc()
        covered_pop = 0
        for st, acc in strata.items():
            n_pop = strata_pop.get(st)
            if not n_pop:
                continue
            rw.add(acc, n_pop / strata_n[st])
            covered_pop += n_pop
        total_pop = sum(strata_pop.values()) or None
        res = {k: summarize(v) for k, v in scopes.items()}
        res["reweighted"] = summarize(rw)
        res["reweighted"]["population_share_covered"] = covered_pop / total_pop if total_pop else None
        res["_missing"] = missing
        per_rep.append(res)

    # nondeterminism: how often a required gold mention's matched status flips
    flips = None
    if len(reps) > 1:
        status = collections.defaultdict(set)
        for rep, preds in reps.items():
            for g in gold:
                ms = [dict(m, _key=model_key(m, alias)) for m in preds.get(g["comment_id"], [])
                      if isinstance(m, dict)]
                pairs, _ = match(g["mentions"], ms)
                got = {id(x) for x, _, _ in pairs}
                for i, gm in enumerate(g["mentions"]):
                    if not gm["ambiguous"]:
                        status[(g["comment_id"], i)].add(id(gm) in got)
        flips = sum(len(v) > 1 for v in status.values()) / len(status) if status else None
    return per_rep, cstats, flips, mode


# ---------------------------------------------------------------- report
HEADLINE = ["comments", "drop_rate", "mention_precision", "mention_recall", "mention_f1",
            "fn_model_error", "fn_context_gap", "aspect_sign_err_model_error",
            "aspect_sign_err_context_gap", "food_presence_f1", "food_sign_acc",
            "food_exact_acc", "food_mae_levels", "food_spearman", "food_distinct_values",
            "food_share_0.3_or_0.6", "negative_softened_rate", "is_negated_acc",
            "is_negated_recall", "is_firsthand_acc"]


def fmt(v):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def report(run_path, per_rep, cstats, flips, mode, out_dir):
    name = os.path.basename(run_path).removesuffix(".jsonl")
    date = datetime.date.today().isoformat()
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"{date}__{name}.md")
    csv_path = os.path.join(out_dir, f"{date}__{name}.csv")
    r0 = per_rep[0]
    lat = sorted(cstats["latency"]) or [0]
    lines = [f"# {name}", "", f"mode: {mode}; reps: {len(per_rep)}; labeled comments missing "
             f"from run: {r0['_missing']}", "",
             f"calls {cstats['calls']}, errors {cstats['errors']}, invalid JSON {cstats['json_bad']}, "
             f"cost ${cstats['cost']:.4f}, tokens {cstats['prompt_tokens']:,} in / "
             f"{cstats['completion_tokens']:,} out, latency p50 {lat[len(lat)//2]:.1f}s "
             f"p90 {lat[int(len(lat)*0.9)]:.1f}s", ""]
    if flips is not None:
        lines += [f"mention match status flips across reps: {flips:.3f}", ""]
    scopes = ["overall", "reweighted"] + sorted(k for k in r0 if k not in ("overall", "reweighted", "_missing"))
    lines.append("| metric | " + " | ".join(scopes) + " |")
    lines.append("|---" * (len(scopes) + 1) + "|")
    for metric in HEADLINE:
        cells = []
        for s in scopes:
            vals = [r[s].get(metric) for r in per_rep if s in r]
            vals = [v for v in vals if v is not None]
            if not vals:
                cells.append("–")
            elif len(vals) > 1 and isinstance(vals[0], float):
                cells.append(f"{statistics.fmean(vals):.3f}±{statistics.pstdev(vals):.3f}")
            else:
                cells.append(fmt(vals[0]))
        lines.append(f"| {metric} | " + " | ".join(cells) + " |")
    lines += ["", "food values (rep 0, overall): " + (r0["overall"].get("food_top_values") or "–"), "",
              "Aspect detail (rep 0, overall):", "",
              "| aspect | presence F1 | n valued | sign | exact | within 1 | MAE (levels) |",
              "|---|---|---|---|---|---|---|"]
    for a in ASPECTS:
        o = r0["overall"]
        lines.append(f"| {a} | {fmt(o[f'{a}_presence_f1'])} | {o[f'{a}_n']} | {fmt(o[f'{a}_sign_acc'])} | "
                     f"{fmt(o[f'{a}_exact_acc'])} | {fmt(o[f'{a}_within1_acc'])} | {fmt(o[f'{a}_mae_levels'])} |")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["run", "rep", "scope", "metric", "value"])
        for rep, r in enumerate(per_rep):
            for s in scopes:
                for k, v in (r.get(s) or {}).items():
                    w.writerow([name, rep, s, k, v])
    return md_path, csv_path


def self_test(gold, items, alias):
    """Gold converted into a perfect run must score 1.0 everywhere."""
    preds, covered = {}, set()
    for g in gold:
        covered.add(g["comment_id"])
        preds[g["comment_id"]] = [{
            "restaurant_raw": m["restaurant_raw"],
            "aspects": {k: (None if v is None else v / 3) for k, v in m["aspects"].items()},
            "is_negated": m["is_negated"], "is_firsthand": bool(m["is_firsthand"]),
        } for m in g["mentions"]]
    run = ({0: preds}, {0: covered}, {"calls": 0, "errors": 0, "json_bad": 0, "cost": 0.0,
                                      "latency": [], "prompt_tokens": 0, "completion_tokens": 0}, "comment")
    per_rep, _, _, _ = evaluate(gold, items, None, alias, False, run=run)
    o = per_rep[0]["overall"]
    checks = {k: o[k] for k in ("drop_rate", "mention_precision", "mention_recall", "food_sign_acc",
                                "food_exact_acc", "food_mae_levels", "is_negated_acc")}
    print(json.dumps(checks, indent=1))
    assert o["mention_recall"] == 1 and o["drop_rate"] == 0 and o["food_exact_acc"] == 1
    assert o["food_mae_levels"] < 1e-9
    print("self-test ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--gold", default=os.path.join(HERE, "gold.jsonl"))
    ap.add_argument("--drop-chains", action="store_true",
                    help="drop chains.txt keys on both sides, as production does")
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    gold = load_jsonl(args.gold)
    items = load_jsonl(os.path.join(HERE, "items.jsonl"))
    alias = load_alias()
    if args.self_test:
        self_test(gold, items, alias)
        return
    for path in args.runs:
        per_rep, cstats, flips, mode = evaluate(gold, items, path, alias, args.drop_chains)
        md, cs = report(path, per_rep, cstats, flips, mode, args.out)
        print(f"{path}\n  -> {md}\n  -> {cs}")


if __name__ == "__main__":
    main()
