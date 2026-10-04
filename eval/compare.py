"""Compare every run in eval/runs on COMMON comments, and write one JSON for the report.

A run that stopped early (rate limits, an exhausted key) covers a different
subset of comments than its neighbours, and scoring each on its own subset
would let a model look better for having finished the easy ones. So:

  comment_full   comment-mode runs that cover ~all 769 v1 comments, scored on
                 the comments every one of them covered.
  thread_full    thread-mode runs that cover the 17 whole threads, scored on
                 the thread comments every one of them covered.
  partial        each run that finished only part of the set, scored on its own
                 covered comments next to the baseline model with the same
                 prompt and the original production output ON THE SAME comments.
  v2             comment_full runs on the v2 weakness set (the v1-derived part;
                 v2 top-ups were never sent to models), by weakness.

Everything uses rep 0, production's chain filter, and score.py's metrics.

    python eval/compare.py            -> eval/results/comparison.json
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import score as S  # noqa: E402

PROMPTS = {"1d5bac550078": "original", "ca5439be83b3": "original",
           "0d75b20b5f83": "revised", "5b02ac883c80": "revised",
           "3a6940dd5cc1": "rubric_v1", "bd4467215908": "rubric_v1"}
BASELINE_MODEL = "deepseek/deepseek-v4-flash"
FULL = 0.97          # share of the set a run must cover to count as complete
MIN_PARTIAL = 60     # fewer covered comments than this is not worth reporting
KEEP = S.HEADLINE + ["neg_mention_n", "vc_n", "dishneg_n", "mention_precision", "mention_f1", "food_share_0.3_or_0.6", "food_distinct_values",
                     "level_histogram", "food_mae_levels", "negative_softened_rate", "negative_to_positive_rate",
                     "reference_mention_recall", "search_terms_recall", "fn_model_error", "fn_context_gap",
                     "comments"]


def load(path, items):
    run = S.load_run(path, items)
    recs = S.load_jsonl(path)
    ok = [r for r in recs if not r.get("error")]
    meta = {"file": os.path.basename(path)}
    if ok:
        meta.update(model=ok[0]["model"], prompt=PROMPTS.get(ok[0]["prompt_hash"], ok[0]["prompt_hash"]),
                    mode=ok[0]["mode"], prompt_hash=ok[0]["prompt_hash"])
        strict = [r.get("json_ok_strict", r.get("json_ok")) for r in ok]
        meta["json_strict_rate"] = sum(bool(x) for x in strict) / len(strict)
        lat = sorted(r["latency_s"] for r in ok if r.get("latency_s") is not None)
        meta["latency_p50"] = lat[len(lat) // 2] if lat else None
        meta["reps"] = sorted({r["rep"] for r in ok})
    return run, meta


def restrict(run, subset):
    reps, covered, stats, mode = run
    return {0: reps.get(0, {})}, {0: covered.get(0, set()) & subset}, stats, mode


def metrics(gold, items, run, subset, stats_path, alias, excluded):
    per_rep, _, _, _ = S.evaluate(gold, items, restrict(run, subset), alias, excluded, True, stats_path)
    r = per_rep[0]
    out = {}
    for scope, d in r.items():
        if isinstance(d, dict):
            out[scope] = {k: d.get(k) for k in KEEP if k in d}
    return out


def cost_per_1k(run, n_comments_rep0):
    """OpenRouter-reported spend per 1,000 comments, from the calls that succeeded."""
    reps, covered, stats, _ = run
    total = sum(len(c) for c in covered.values())
    return stats["cost"] / total * 1000 if total and stats["cost"] else None


def main():
    gold = S.load_jsonl(os.path.join(HERE, "gold.jsonl"))
    items = S.load_jsonl(os.path.join(HERE, "items.jsonl"))
    alias, excluded = S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json")
    stats_path = os.path.join(HERE, "sampling_stats.json")
    all_ids = {g["comment_id"] for g in gold}
    thread_ids = {c["comment_id"] for it in items if it["kind"] != "comment" for c in it["comments"]}

    runs = {}
    for path in sorted(glob.glob(os.path.join(HERE, "runs", "*.jsonl"))):
        run, meta = load(path, items)
        if "model" not in meta:
            continue
        cov = run[1].get(0, set())
        scope = thread_ids if meta["mode"] == "thread" else all_ids
        meta["covered"] = len(cov & scope)
        meta["coverage"] = meta["covered"] / len(scope)
        meta["cost_per_1k_comments"] = cost_per_1k(run, meta["covered"])
        meta["cost_total"] = run[2]["cost"]
        runs[meta["file"]] = (run, meta)
    stored_path = os.path.join(HERE, "baseline", "production__stored__all.jsonl")
    stored = S.load_run(stored_path, items)

    out = {"gold": {"comments": len(gold), "mentions": sum(len(g["mentions"]) for g in gold),
                    "thread_comments": len(thread_ids)},
           "runs": {f: m for f, (_, m) in runs.items()}, "panels": {}}

    # comment_full: complete comment-mode runs, on their common comments, plus production's stored output
    full_c = [f for f, (_, m) in runs.items() if m["mode"] == "comment" and m["coverage"] >= FULL]
    common = set(all_ids)
    for f in full_c:
        common &= runs[f][0][1].get(0, set())
    panel = {"n_comments": len(common), "rows": []}
    panel["rows"].append({"label": "production (stored output)", **{"metrics": metrics(gold, items, stored, common, stats_path, alias, excluded)}})
    for f in full_c:
        run, m = runs[f]
        panel["rows"].append({"file": f, "label": f"{m['model']} · {m['prompt']}",
                              "metrics": metrics(gold, items, run, common, stats_path, alias, excluded)})
    out["panels"]["comment_full"] = panel

    # thread_full
    full_t = [f for f, (_, m) in runs.items() if m["mode"] == "thread" and m["coverage"] >= FULL]
    tcommon = set(thread_ids)
    for f in full_t:
        tcommon &= runs[f][0][1].get(0, set())
    panel = {"n_comments": len(tcommon), "rows": [
        {"label": "production (stored output)", "metrics": metrics(gold, items, stored, tcommon, stats_path, alias, excluded)}]}
    for f in full_t:
        run, m = runs[f]
        panel["rows"].append({"file": f, "label": f"{m['model']} · {m['prompt']}",
                              "metrics": metrics(gold, items, run, tcommon, stats_path, alias, excluded)})
    out["panels"]["thread_full"] = panel

    # partial: each incomplete comment-mode run vs the baseline model with the same prompt, same comments
    partial = []
    for f, (run, m) in runs.items():
        if m["mode"] != "comment" or m["coverage"] >= FULL or m["covered"] < MIN_PARTIAL:
            continue
        sub = run[1].get(0, set()) & all_ids
        base = next((g for g, (_, bm) in runs.items() if bm["model"] == BASELINE_MODEL and bm["mode"] == "comment"
                     and bm["prompt"] == m["prompt"] and bm["coverage"] >= FULL), None)
        if base:
            sub &= runs[base][0][1].get(0, set())
        row = {"file": f, "label": f"{m['model']} · {m['prompt']}", "n_comments": len(sub),
               "metrics": metrics(gold, items, run, sub, stats_path, alias, excluded),
               "production": metrics(gold, items, stored, sub, stats_path, alias, excluded)}
        if base:
            row["baseline_file"] = base
            row["baseline"] = metrics(gold, items, runs[base][0], sub, stats_path, alias, excluded)
        partial.append(row)
    out["panels"]["partial"] = partial

    # v2: weakness breakdown for complete comment-mode runs (v1-derived v2 items only)
    v2_gold = S.load_jsonl(os.path.join(HERE, "v2", "gold.jsonl"))
    v2_items = S.load_jsonl(os.path.join(HERE, "v2", "items.jsonl"))
    v2_ids = {g["comment_id"] for g in v2_gold}
    vcommon = v2_ids & common
    panel = {"n_comments": len(vcommon), "rows": [
        {"label": "production (stored output)",
         "metrics": metrics(v2_gold, v2_items, S.load_run(os.path.join(HERE, "baseline", "production__stored__v2.jsonl"), v2_items),
                            vcommon, "", alias, excluded)}]}
    for f in full_c:
        run = S.load_run(os.path.join(HERE, "runs", f), v2_items)
        panel["rows"].append({"file": f, "label": f"{runs[f][1]['model']} · {runs[f][1]['prompt']}",
                              "metrics": metrics(v2_gold, v2_items, run, vcommon, "", alias, excluded)})
    out["panels"]["v2"] = panel

    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    path = os.path.join(HERE, "results", "comparison.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=lambda o: sorted(o) if isinstance(o, set) else str(o))
    print(path)
    for name, p in out["panels"].items():
        rows = p if isinstance(p, list) else p["rows"]
        print(f"\n== {name} ({'' if isinstance(p, list) else str(p['n_comments']) + ' common comments'})")
        for r in rows:
            o = r["metrics"].get("reweighted") or r["metrics"].get("threads") or r["metrics"].get("overall", {})
            print(f"  {r['label'][:58]:58} n={r.get('n_comments', ''):>4} drop={S.fmt(o.get('drop_rate'))} "
                  f"recall={S.fmt(o.get('mention_recall'))} neg={S.fmt(o.get('negative_mention_recall'))} "
                  f"value={S.fmt(o.get('value_complaint_recall'))} dish={S.fmt(o.get('dish_negative_recall'))}")


if __name__ == "__main__":
    main()
