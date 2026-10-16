"""Score run files against the v5 gold (eval/gold_v5.jsonl, eval/v2/gold_v5.jsonl).

    python eval/score_v5.py eval/runs/<model>__<hash>__<mode>.jsonl [more runs ...]
    python eval/score_v5.py RUN --set v2                 # the v2 diagnostic set
    python eval/score_v5.py RUN --gold G --items I --stats ''
    python eval/score_v5.py --self-test                  # gold scored against itself

Every run is read through schema_v5: v5 output through the normalizer, old
output (production's prompts, the current prompt, rubric_v1) through the
adapter, so old and new prompts are scored by the same rules. Writes
eval/results/<date>__<run>__v5[__<set>].md and .csv. The contract and the
gold format are in eval/schema_v5.md.

The HEADLINE keeps score.py's order, the owner's priorities:

  a. comment drop rate        gold has >=1 required mention, model returned none
  b. mention recall           required gold mentions found
  c. negative-mention recall  gold mention with any aspect at meh or below whose
                              match carries a negative (an aspect below mixed, or is_negated)
  d. value-complaint recall   gold value_complaint; model value below mixed
                              (or rubric_v1's own value_complaint field)
  e. dish-negative recall     gold dishes_disliked found in the match's dishes_disliked,
                              names matched leniently. n/a for old runs with no dish verdicts
  f. sign accuracy + levels used

Then the v5 fields: reference_only and bare-endorsement precision/recall,
per-aspect exact and within-one agreement (gold aspect_alternatives honored),
dish list precision/recall, experience accuracy and confusion, price
agreement, is_negated precision/recall, and the run's parse failures,
normalizer repairs, bad thread ids, cost and latency.
"""

import argparse
import collections
import csv
import datetime
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import schema_v5 as V  # noqa: E402
import score as S  # noqa: E402
from score import CHAINS, lenient_same, prf, ratio, sign  # noqa: E402

SETS = {
    "v1": {"gold": os.path.join(HERE, "gold_v5.jsonl"), "items": os.path.join(HERE, "items.jsonl"),
           "stats": os.path.join(HERE, "sampling_stats.json")},
    "v2": {"gold": os.path.join(HERE, "v2", "gold_v5.jsonl"), "items": os.path.join(HERE, "v2", "items.jsonl"),
           "stats": ""},
}
ASPECTS = V.ASPECTS


# ---------------------------------------------------------------- reading runs
def set_calls(items):
    """Every call key a set's items can produce -> the comment_ids that call
    covers. One run file can hold calls for several sets (v1 and v2 share
    it), so a set's cost and health are counted over its own calls only."""
    keys = {}
    for it in items:
        cids = [it["comment_id"]] if it["kind"] == "comment" else [c["comment_id"] for c in it["comments"]]
        for cid in cids:
            keys[f"comment:{cid}"] = {cid}
            keys[f"stored:{cid}"] = {cid}
        chunks = [it["inputs"]["thread"]] if it["kind"] == "comment" else it["thread_chunks"]
        for ch in chunks:
            keys[f"thread:{it['thread_id']}:{ch['chunk_index']}"] = set(ch["short_ids"].values())
    return keys


class Run:
    """A run file read once, for one set: per rep, comment_id -> contract
    mentions, plus the run-health numbers over that set's calls."""

    def __init__(self, path, items):
        self.path = path
        reps, covered, _, mode = S.load_run(path, items)
        self.covered, self.mode = covered, mode
        self.fixes = collections.Counter()
        self.comment_mode = {}          # stored runs: each comment's own mode

        # One schema for the whole run, by majority, so a drifted v5 mention
        # is repaired (and counted) by the normalizer, not adapted as old.
        every = [m for by_cid in reps.values() for ms in by_cid.values() for m in ms]
        self.raw_mentions = len(every)
        self.schema = V.run_schema(every) if every else None
        self.preds = {}
        for rep, by_cid in reps.items():
            out = {}
            for cid, ms in by_cid.items():
                if mode == "stored":
                    ph = next((x.get("prompt_hash") for x in ms if isinstance(x, dict)), None)
                    self.comment_mode[cid] = S.PROD_MODE.get(ph)
                out[cid] = [c for c in (V.to_v5(m, self.fixes, self.schema) for m in ms) if c is not None]
            self.preds[rep] = out

        keys = set_calls(items)
        in_set = set().union(*keys.values()) if keys else set()
        self.covered = {rep: cids & in_set for rep, cids in self.covered.items()}
        st = {"calls": 0, "errors": 0, "json_bad": 0, "cost": 0.0, "latency": [], "prompt_tokens": 0,
              "completion_tokens": 0, "permanent": 0, "comments_in_calls": 0}
        self.bad_ids = self.emitted = self.cache_read = self.cache_write = 0
        self.stop = collections.Counter()
        recs = [r for r in S.load_jsonl(path) if r.get("call_key") in keys]
        answered = {(r["call_key"], r["rep"]) for r in recs if not r.get("error") and r.get("raw", "") is not None}
        # Per rep, the calls tried and the calls settled (answered, or refused
        # for good). A rep 0 with tried-but-unsettled calls is partial.
        self.attempted = collections.defaultdict(set)
        self.settled = collections.defaultdict(set)
        for r in recs:
            self.attempted[r["rep"]].add(r["call_key"])
            if (r["call_key"], r["rep"]) in answered or r.get("permanent"):
                self.settled[r["rep"]].add(r["call_key"])
        for r in recs:
            st["calls"] += 1
            if r.get("error"):
                st["errors"] += 1
                if r.get("permanent") and (r["call_key"], r["rep"]) not in answered:
                    # Refused for good: the model never answers this input, so
                    # it counts as covered with nothing found, i.e. a drop.
                    st["permanent"] += 1
                    self.covered.setdefault(r["rep"], set()).update(keys[r["call_key"]])
                    self.preds.setdefault(r["rep"], {})
                continue
            if not r.get("json_ok"):
                st["json_bad"] += 1
            u = r.get("usage") or {}
            st["cost"] += float(u.get("cost") or 0)
            st["prompt_tokens"] += u.get("prompt_tokens") or 0
            st["completion_tokens"] += u.get("completion_tokens") or 0
            st["comments_in_calls"] += len(keys[r["call_key"]])
            if r.get("latency_s") is not None:
                st["latency"].append(r["latency_s"])
            self.bad_ids += r.get("bad_ids") or 0
            self.emitted += (r.get("bad_ids") or 0) + sum(len(v) for v in (r.get("mentions_by_comment") or {}).values())
            self.cache_read += u.get("cache_read_tokens") or 0
            self.cache_write += u.get("cache_write_tokens") or 0
            self.stop[r.get("stop_reason") or "?"] += 1
        self.stats = st
        self.n_reps = max(1, len(self.preds))

    @property
    def schema_name(self):
        return {None: "none", "v5": "v5", "old": "old (adapted)"}[self.schema]

    @property
    def reps(self):
        return sorted(set(self.covered) | set(self.preds)) or [0]

    def complete_reps(self):
        """The reps that cover everything rep 0 covers. Rep 0 defines the
        row's planned set; a later rep that stopped early (an exhausted key,
        say) would otherwise shrink every row's common comments to its own
        few, so it is left out of scoring instead and reported as such."""
        base = self.covered.get(0, set())
        return [rep for rep in self.reps if rep == 0 or self.covered.get(rep, set()) >= base]

    def rep0_partial(self, planned=None):
        """Whether rep 0 itself is short: a call it tried never settled, or a
        planned call key (bench's job list) was never made."""
        tried = set(self.attempted.get(0, set())) | set(planned or ())
        return bool(tried - self.settled.get(0, set()))

    def covered_complete(self):
        """Comments covered in every complete rep (rep 0's coverage, since
        complete reps contain it)."""
        sets = [self.covered.get(rep, set()) for rep in self.complete_reps()]
        return set.intersection(*sets) if sets else set()

    def mode_for(self, cid, item):
        if self.mode != "stored":
            return self.mode
        prod = item.get("production") or next((c["production"] for c in item.get("comments", [])
                                               if c["comment_id"] == cid), {})
        return self.comment_mode.get(cid) or prod.get("mode") or "thread"


# ---------------------------------------------------------------- per comment
class Acc:
    def __init__(self):
        self.c = collections.Counter()
        self.food_pairs = []
        self.levels = collections.Counter()

    def add(self, o, w=1):
        # Counts are weighted; the level histogram and food pairs are not,
        # since "levels used" and a rank correlation have no population form.
        for k, v in o.c.items():
            self.c[k] += v if w == 1 else v * w
        self.food_pairs += o.food_pairs
        self.levels.update(o.levels)


def lv(label):
    return V.level(label)


def gold_negative(g):
    return any((lv(v) is not None and lv(v) <= -1) for v in g["aspects"].values())


def model_negative(m):
    return any((lv(v) or 0) < 0 for v in m["aspects"].values()) or m["is_negated"]


def model_value_complaint(m):
    if "_value_complaint" in m:
        return m["_value_complaint"]
    return (lv(m["aspects"]["value"]) or 0) < 0


def dish_capable(m):
    return not m.get("_adapted") or m.get("_dish_capable", False)


def match_lists(gold, model):
    """Greedy one-to-one lenient matching of two name lists -> (tp, fp, fn)."""
    used, tp = set(), 0
    for g in gold:
        for i, x in enumerate(model):
            if i not in used and lenient_same(g, x):
                used.add(i)
                tp += 1
                break
    return tp, len(model) - len(used), len(gold) - tp


def alternatives(g, field):
    return list((g.get("aspect_alternatives") or {}).get(field) or [])


def uncertain(g, field):
    return field in (g.get("uncertain_fields") or [])


def is_bare(m):
    return not m["reference_only"] and not m["is_negated"] and all(v is None for v in m["aspects"].values())


def score_comment(gold, preds, mode, alias, excluded, drop_chains):
    a = Acc()
    c = a.c
    ms = S.model_mentions(preds, alias, drop_chains)
    gms = [g for g in gold["mentions"] if not (drop_chains and g["canonical_key"] in CHAINS)]
    required = [g for g in gms if S.is_required(g)]
    pairs, fps = S.match(gms, ms)
    fps = [m for m in fps if m["_key"] not in excluded]
    rk = f"resolvable_{mode}_mode"
    matched = {id(g): m for g, m, _ in pairs}

    c["comments"] += 1
    if required:
        c["comments_with_gold"] += 1
        if not [m for m in ms if m["_key"] not in excluded]:
            c["dropped_comments"] += 1
    elif fps:
        c["false_alarm_comments"] += 1
    c["dish_capable_mentions"] += sum(dish_capable(m) for m in ms)

    for g in required:
        gap = g.get(rk) is False
        m = matched.get(id(g))
        c["tp" if m else "fn"] += 1
        if not m:
            c["fn_context_gap" if gap else "fn_model_error"] += 1
        if any(str(d).lower() == "closed" for d in g.get("descriptors") or []):
            c["closed_n"] += 1
            c["closed_hit"] += bool(m)
            c["closed_ok"] += bool(m) and m["reference_only"] and any(
                lenient_same("closed", d) for d in m["descriptors"])
        if g.get("reference_only"):
            c["reference_n"] += 1
            c["reference_hit"] += bool(m)
        if gold_negative(g):
            c["neg_mention_n"] += 1
            hit = bool(m) and model_negative(m)
            c["neg_mention_hit"] += hit
            if not hit:
                c["neg_miss_context_gap" if gap else "neg_miss_model_error"] += 1
            if m and not hit and any((lv(v) or 0) > 0 for v in m["aspects"].values()):
                c["neg_to_positive"] += 1
            if m and not hit and is_bare(m):
                c["neg_to_bare"] += 1
        if g.get("value_complaint"):
            c["vc_n"] += 1
            c["vc_hit"] += bool(m) and model_value_complaint(m)
        for d in g.get("dishes_disliked") or []:
            c["dishneg_n"] += 1
            c["dishneg_hit"] += bool(m) and any(lenient_same(d, x) for x in m["dishes_disliked"])
        if g.get("judgment_question"):
            valued = {k: lv(v) for k, v in g["aspects"].items() if v is not None}
            if valued:
                c["jq_n"] += 1
                c["jq_hit"] += bool(m) and all(sign(lv(m["aspects"][k]) or 0) == sign(x) for k, x in valued.items())
        terms = g.get("search_terms") or []
        if terms:
            pool = (m["descriptors"] + m["dishes_liked"] + m["dishes_disliked"] + m["dishes_mentioned"]) if m else []
            for t in terms:
                c["terms_n"] += 1
                c["terms_hit"] += any(lenient_same(t, p) for p in pool)
    c["fp"] += len(fps)
    c["fuzzy_matches"] += sum(1 for _, _, how in pairs if how == "fuzzy")

    for g, m, _ in pairs:
        if not S.is_required(g):
            continue
        gap = g.get(rk) is False
        for name in ASPECTS:
            gv = g["aspects"].get(name)
            ok = {gv, *alternatives(g, name)}
            vals = {lv(x) for x in ok if x is not None and lv(x) is not None}
            mv = lv(m["aspects"][name])
            if mv is not None:
                a.levels[mv] += 1
            g_present, m_present = gv is not None, mv is not None
            if m_present != g_present and ((None in ok) if not m_present else bool(vals)):
                g_present = m_present
            c[f"pres_tp_{name}"] += g_present and m_present
            c[f"pres_fp_{name}"] += (not g_present) and m_present
            c[f"pres_fn_{name}"] += g_present and not m_present
            if m_present and vals:
                near = min(vals, key=lambda x: abs(mv - x))
                c[f"n_{name}"] += 1
                c[f"exact_{name}"] += mv in vals
                c[f"within1_{name}"] += abs(mv - near) <= 1
                c[f"abserr_{name}"] += abs(mv - near)
                c["sign_n"] += 1
                c["sign_ok"] += sign(mv) == sign(near)
                c[f"sign_{name}"] += sign(mv) == sign(near)
                if sign(mv) != sign(near):
                    c["sign_err_context_gap" if gap else "sign_err_model_error"] += 1
                if near < 0:
                    c["softened_n"] += 1
                    c["softened"] += mv > near
                if name == "food":
                    a.food_pairs.append((mv, gv and lv(gv) if gv is not None else near))

        # price: an ordered fact, scored like an aspect on its own ranks
        gp = g.get("price")
        okp = {gp, *alternatives(g, "price")}
        ranks = {V.PRICE_RANK[x] for x in okp if x in V.PRICE_RANK}
        mp = V.PRICE_RANK.get(m["price"])
        g_present, m_present = gp is not None, mp is not None
        if m_present != g_present and ((None in okp) if not m_present else bool(ranks)):
            g_present = m_present
        c["pres_tp_price"] += g_present and m_present
        c["pres_fp_price"] += (not g_present) and m_present
        c["pres_fn_price"] += g_present and not m_present
        if m_present and ranks:
            c["n_price"] += 1
            c["exact_price"] += mp in ranks
            c["within1_price"] += min(abs(mp - r) for r in ranks) <= 1

        gr, mr = bool(g.get("reference_only")), m["reference_only"]
        if not uncertain(g, "reference_only"):
            c["ref_tp"] += gr and mr
            c["ref_fp"] += (not gr) and mr
            c["ref_fn"] += gr and not mr
        gb = is_bare({"reference_only": gr, "is_negated": bool(g.get("is_negated")), "aspects": g["aspects"]})
        mb = is_bare(m)
        c["bare_tp"] += gb and mb
        c["bare_fp"] += (not gb) and mb
        c["bare_fn"] += gb and not mb

        if not uncertain(g, "is_negated"):
            gn, mn = bool(g.get("is_negated")), m["is_negated"]
            c["negd_n"] += 1
            c["negd_ok"] += gn == mn
            c["negd_tp"] += gn and mn
            c["negd_fp"] += (not gn) and mn
            c["negd_fn"] += gn and not mn

        ge = g.get("experience")
        if ge in V.EXPERIENCES and not uncertain(g, "experience"):
            oke = {ge, *alternatives(g, "experience")}
            c["exp_n"] += 1
            c["exp_ok"] += m["experience"] in oke
            c[f"exp__{ge}__{m['experience']}"] += 1

        if dish_capable(m):
            for k in ("dishes_liked", "dishes_disliked"):
                tp, fp, fn = match_lists(g.get(k) or [], m[k])
                c[f"{k}_tp"] += tp
                c[f"{k}_fp"] += fp
                c[f"{k}_fn"] += fn
        allg = (g.get("dishes_liked") or []) + (g.get("dishes_disliked") or []) + (g.get("dishes_mentioned") or [])
        allm = m["dishes_liked"] + m["dishes_disliked"] + m["dishes_mentioned"]
        tp, fp, fn = match_lists(allg, allm)
        c["dishes_any_tp"] += tp
        c["dishes_any_fp"] += fp
        c["dishes_any_fn"] += fn
    return a


# ---------------------------------------------------------------- summaries
HEADLINE = ["drop_rate", "mention_recall", "negative_mention_recall", "value_complaint_recall",
            "dish_negative_recall", "sign_accuracy", "levels_used"]
V5_METRICS = ["reference_only_precision", "reference_only_recall", "bare_endorsement_precision",
              "bare_endorsement_recall", "is_negated_precision", "is_negated_recall",
              "experience_acc", "price_exact_acc", "price_within1_acc", "price_presence_f1",
              "dishes_liked_precision", "dishes_liked_recall", "dishes_disliked_precision",
              "dishes_disliked_recall", "dishes_any_recall", "judgment_question_acc"]
SECONDARY = ["comments", "mention_precision", "mention_f1", "fn_model_error", "fn_context_gap",
             "neg_miss_model_error", "neg_miss_context_gap", "negative_to_positive_rate",
             "negative_to_bare_rate", "negative_softened_rate", "reference_mention_recall",
             "closed_mention_recall", "closed_handled_rate", "search_terms_recall",
             "food_presence_f1", "food_exact_acc", "food_within1_acc", "food_mae_levels",
             "value_presence_f1", "value_exact_acc", "service_presence_f1", "atmosphere_presence_f1",
             "wait_presence_f1", "food_spearman", "sign_err_model_error", "sign_err_context_gap",
             "neg_mention_n", "vc_n", "dishneg_n", "jq_n"]


def summarize(a, capable):
    c = a.c
    p, r, f = prf(c["tp"], c["fp"], c["fn"])
    out = {
        "comments": c["comments"],
        "drop_rate": ratio(c["dropped_comments"], c["comments_with_gold"]),
        "mention_recall": r,
        "negative_mention_recall": ratio(c["neg_mention_hit"], c["neg_mention_n"]),
        "value_complaint_recall": ratio(c["vc_hit"], c["vc_n"]),
        "dish_negative_recall": ratio(c["dishneg_hit"], c["dishneg_n"]) if capable else "n/a",
        "sign_accuracy": ratio(c["sign_ok"], c["sign_n"]),
        "levels_used": len(a.levels) or None,
        "mention_precision": p, "mention_f1": f,
        "tp": c["tp"], "fp": c["fp"], "fn": c["fn"],
        "fn_model_error": c["fn_model_error"], "fn_context_gap": c["fn_context_gap"],
        "neg_miss_model_error": c["neg_miss_model_error"], "neg_miss_context_gap": c["neg_miss_context_gap"],
        "negative_to_positive_rate": ratio(c["neg_to_positive"], c["neg_mention_n"]),
        "negative_to_bare_rate": ratio(c["neg_to_bare"], c["neg_mention_n"]),
        "negative_softened_rate": ratio(c["softened"], c["softened_n"]),
        "reference_mention_recall": ratio(c["reference_hit"], c["reference_n"]),
        "closed_mention_recall": ratio(c["closed_hit"], c["closed_n"]),
        "closed_handled_rate": ratio(c["closed_ok"], c["closed_n"]),
        "search_terms_recall": ratio(c["terms_hit"], c["terms_n"]),
        "sign_err_model_error": c["sign_err_model_error"], "sign_err_context_gap": c["sign_err_context_gap"],
        "neg_mention_n": c["neg_mention_n"], "vc_n": c["vc_n"], "dishneg_n": c["dishneg_n"], "jq_n": c["jq_n"],
        "judgment_question_acc": ratio(c["jq_hit"], c["jq_n"]),
        "experience_acc": ratio(c["exp_ok"], c["exp_n"]),
        "is_negated_acc": ratio(c["negd_ok"], c["negd_n"]),
    }
    for key, tp, fp, fn in (("reference_only", "ref_tp", "ref_fp", "ref_fn"),
                            ("bare_endorsement", "bare_tp", "bare_fp", "bare_fn"),
                            ("is_negated", "negd_tp", "negd_fp", "negd_fn"),
                            ("dishes_liked", "dishes_liked_tp", "dishes_liked_fp", "dishes_liked_fn"),
                            ("dishes_disliked", "dishes_disliked_tp", "dishes_disliked_fp", "dishes_disliked_fn"),
                            ("dishes_any", "dishes_any_tp", "dishes_any_fp", "dishes_any_fn")):
        pp, rr, _ = prf(c[tp], c[fp], c[fn])
        dish = key in ("dishes_liked", "dishes_disliked")
        out[f"{key}_precision"] = pp if capable or not dish else "n/a"
        out[f"{key}_recall"] = rr if capable or not dish else "n/a"
    for name in ASPECTS + ("price",):
        _, _, pf = prf(c[f"pres_tp_{name}"], c[f"pres_fp_{name}"], c[f"pres_fn_{name}"])
        n = c[f"n_{name}"]
        out[f"{name}_presence_f1"] = pf
        out[f"{name}_n"] = n
        out[f"{name}_exact_acc"] = ratio(c[f"exact_{name}"], n)
        out[f"{name}_within1_acc"] = ratio(c[f"within1_{name}"], n)
        if name != "price":
            out[f"{name}_sign_acc"] = ratio(c[f"sign_{name}"], n)
            out[f"{name}_mae_levels"] = ratio(c[f"abserr_{name}"], n)
    if a.food_pairs:
        out["food_spearman"] = S.spearman([x for x, _ in a.food_pairs], [y for _, y in a.food_pairs])
    conf = {k[5:]: v for k, v in c.items() if k.startswith("exp__")}
    out["experience_confusion"] = " ".join(f"{k.replace('__', '>')}:{v:g}" for k, v in sorted(conf.items()))
    out["level_histogram"] = " ".join(f"{k:+d}:{a.levels[k]}" for k in sorted(a.levels))
    return out


# ---------------------------------------------------------------- evaluate
def evaluate(gold, items, run, alias, excluded, drop_chains, stats_path, only=None):
    """Per-rep results for one run on one set. `only` limits scoring to a set
    of comment_ids, so several runs can be compared on the comments all of
    them covered."""
    by_item = {it["item_id"]: it for it in items}
    strata_pop = {}
    if stats_path and os.path.exists(stats_path):
        with open(stats_path, encoding="utf-8") as f:
            strata_pop = json.load(f).get("strata_population", {})
    per_rep = []
    reps = run.complete_reps()
    for rep in reps:
        preds = run.preds.get(rep, {})
        capable = any(dish_capable(m) for ms in preds.values() for m in ms)
        scopes = collections.defaultdict(Acc)
        strata = collections.defaultdict(Acc)
        strata_n = collections.Counter()
        missing = 0
        for g in gold:
            it = by_item.get(g["item_id"])
            cid = g["comment_id"]
            if it is None or cid not in run.covered.get(rep, set()) or (only is not None and cid not in only):
                missing += 1
                continue
            a = score_comment(g, preds.get(cid, []), run.mode_for(cid, it), alias, excluded, drop_chains)
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
        res ={k: summarize(v, capable) for k, v in scopes.items()}
        if strata_pop:
            rw, covered_pop = Acc(), 0
            for st, acc in strata.items():
                n_pop = strata_pop.get(st)
                if n_pop:
                    rw.add(acc, n_pop / strata_n[st])
                    covered_pop += n_pop
            res["reweighted"] = summarize(rw, capable)
            res["reweighted"]["population_share_covered"] = ratio(covered_pop, sum(strata_pop.values()))
        res["_missing"] = missing
        per_rep.append(res)

    flips = None
    if len(reps) > 1:
        status = collections.defaultdict(set)
        for rep in reps:
            preds = run.preds.get(rep, {})
            for g in gold:
                if only is not None and g["comment_id"] not in only:
                    continue
                ms = S.model_mentions(preds.get(g["comment_id"], []), alias, False)
                pairs, _ = S.match(g["mentions"], ms)
                got = {id(x) for x, _, _ in pairs}
                for i, gm in enumerate(g["mentions"]):
                    if S.is_required(gm):
                        status[(g["comment_id"], i)].add(id(gm) in got)
        flips = ratio(sum(len(v) > 1 for v in status.values()), len(status))
    return per_rep, flips


def run_health(run):
    """Run-level numbers that are not per comment: parse failures, repairs,
    bad ids, cost and latency."""
    st = run.stats
    answered = st["calls"] - st["errors"]
    lat = sorted(st["latency"]) or [0]
    return {
        "schema": run.schema_name,
        "calls": st["calls"], "errors": st["errors"], "refused_inputs": st["permanent"],
        "error_rate": ratio(st["errors"], st["calls"]),
        "parse_failure_rate": ratio(st["json_bad"], answered),
        "mentions_emitted": run.raw_mentions,
        "repairs_per_100_mentions": None if not run.raw_mentions else 100 * sum(run.fixes.values()) / run.raw_mentions,
        "top_repairs": ", ".join(f"{k}:{v}" for k, v in run.fixes.most_common(8)),
        "bad_id_rate": ratio(run.bad_ids, run.emitted),
        "cost": st["cost"],
        "cost_per_call": ratio(st["cost"], answered),
        # Cost and comments over the same answered calls of this set: a
        # thread chunk's cost against every comment that chunk rendered.
        "cost_per_1k_comments": ratio(1000 * st["cost"], st["comments_in_calls"]),
        "cache_read_share": ratio(run.cache_read, st["prompt_tokens"]),
        "cache_read_tokens": run.cache_read, "cache_write_tokens": run.cache_write,
        "latency_p50": lat[len(lat) // 2], "latency_p90": lat[int(len(lat) * 0.9)],
        "prompt_tokens": st["prompt_tokens"], "completion_tokens": st["completion_tokens"],
        "stop_reasons": ", ".join(f"{k}:{v}" for k, v in run.stop.most_common()),
    }


# ---------------------------------------------------------------- report
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


LABELS = {"drop_rate": "a. comment drop rate (lower is better)", "mention_recall": "b. mention recall",
          "negative_mention_recall": "c. negative-mention recall", "value_complaint_recall": "d. value-complaint recall",
          "dish_negative_recall": "e. dish-negative recall", "sign_accuracy": "f. sign accuracy",
          "levels_used": "f. aspect levels used (of 7)"}


def report(run, per_rep, flips, out_dir, tag=""):
    name = os.path.basename(run.path).removesuffix(".jsonl") + "__v5" + tag
    date = datetime.date.today().isoformat()
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"{date}__{name}.md")
    csv_path = os.path.join(out_dir, f"{date}__{name}.csv")
    h = run_health(run)
    r0 = per_rep[0]
    main = [s for s in ("overall", "reweighted", "single_comments", "threads") if s in r0]
    groups = sorted(k for k in r0 if k not in main and not k.startswith("_"))
    lines = [f"# {name}", "",
             f"mode: {run.mode}; schema: {h['schema']}; reps used {len(per_rep)} of {len(run.reps)}{' (rep 0 partial)' if run.rep0_partial() else ''}; labeled comments not in run: {r0['_missing']}",
             f"calls {h['calls']}, errors {h['errors']} (inputs refused for good: {h['refused_inputs']}), "
             f"parse failures {fmt(h['parse_failure_rate'])}, "
             f"cost ${h['cost']:.4f} (${fmt(h['cost_per_1k_comments'])} per 1k comments), "
             f"latency p50 {h['latency_p50']:.1f}s p90 {h['latency_p90']:.1f}s",
             f"input tokens {h['prompt_tokens']:,} (cache reads {h['cache_read_tokens']:,}, cache writes "
             f"{h['cache_write_tokens']:,}; read share {fmt(h['cache_read_share'])}), output tokens {h['completion_tokens']:,}",
             f"normalizer repairs per 100 mentions: {fmt(h['repairs_per_100_mentions'])} ({h['top_repairs'] or 'none'}); "
             f"bad thread ids: {fmt(h['bad_id_rate'])}"]
    if h["schema"].startswith("old"):
        lines.append("Old-schema run, read through the adapter: reference_only is derived (every aspect null, "
                     "no avoid) and bare endorsement is food 0.3 alone; see schema_v5.md.")
    if flips is not None:
        lines.append(f"required-mention match status flips across reps: {flips:.3f}")
    head = "| metric | " + " | ".join(main) + " |"
    rule = "|---" * (len(main) + 1) + "|"
    lines += ["", "## Headline (owner priorities, in order)", "", head, rule]
    lines += [f"| {LABELS[m]} | " + " | ".join(cell(per_rep, s, m) for s in main) + " |" for m in HEADLINE]
    lines += ["", "## v5 fields", "", head, rule]
    lines += [f"| {m} | " + " | ".join(cell(per_rep, s, m) for s in main) + " |" for m in V5_METRICS]
    lines += ["", "## Everything else", "", head, rule]
    lines += [f"| {m} | " + " | ".join(cell(per_rep, s, m) for s in main) + " |" for m in SECONDARY]
    lines += ["", f"experience confusion (gold>model, rep 0, overall): {r0['overall'].get('experience_confusion') or '–'}",
              f"aspect level histogram (rep 0, overall): {r0['overall'].get('level_histogram') or '–'}",
              f"stop reasons: {h['stop_reasons'] or '–'}"]
    if groups:
        lines += ["", "## By group", "", "| metric | " + " | ".join(groups) + " |", "|---" * (len(groups) + 1) + "|"]
        for m in HEADLINE + ["reference_only_recall", "bare_endorsement_recall", "comments", "mention_precision",
                             "fn_model_error", "fn_context_gap"]:
            lines.append(f"| {m} | " + " | ".join(cell(per_rep, s, m) for s in groups) + " |")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["run", "rep", "scope", "metric", "value"])
        for k, v in h.items():
            w.writerow([name, "", "run", k, v])
        for rep, r in enumerate(per_rep):
            for s, d in r.items():
                if isinstance(d, dict):
                    for k, v in d.items():
                        w.writerow([name, rep, s, k, v])
    return md_path, csv_path


# ---------------------------------------------------------------- self-test
def gold_as_run(gold, items, path="<gold>"):
    """A perfect run built from gold, emitted in the v5 output shape."""
    run = Run.__new__(Run)
    preds, covered = {}, set()
    for g in gold:
        covered.add(g["comment_id"])
        preds[g["comment_id"]] = [{k: m.get(k) for k in V.V5_KEYS} for m in g["mentions"]]
    fixes = collections.Counter()
    run.path, run.covered, run.mode, run.fixes = path, {0: covered}, "comment", fixes
    run.stats = {"calls": 0, "errors": 0, "json_bad": 0, "cost": 0.0, "latency": [],
                 "prompt_tokens": 0, "completion_tokens": 0, "permanent": 0, "comments_in_calls": 0}
    run.preds = {0: {cid: [V.normalize_v5(m, fixes) for m in ms] for cid, ms in preds.items()}}
    run.raw_mentions = sum(len(v) for v in preds.values())
    run.schema = "v5"
    run.comment_mode, run.n_reps = {}, 1
    run.attempted, run.settled = collections.defaultdict(set), collections.defaultdict(set)
    run.bad_ids = run.emitted = run.cache_read = run.cache_write = 0
    run.stop = collections.Counter()
    return run


def self_test(gold, items, alias, excluded, stats):
    run = gold_as_run(gold, items)
    per_rep, _ = evaluate(gold, items, run, alias, excluded, False, stats)
    o = per_rep[0]["overall"]
    keys = HEADLINE + V5_METRICS + ["mention_precision", "food_exact_acc", "closed_handled_rate"]
    print(json.dumps({k: o.get(k) for k in keys}, indent=1))
    perfect = [k for k in keys if o.get(k) not in (None, "n/a", 1.0, 1) and k not in ("drop_rate", "levels_used")]
    assert o["drop_rate"] == 0, o["drop_rate"]
    assert not perfect, f"not perfect against itself: {perfect}"
    assert sum(run.fixes.values()) == 0, f"gold needed repairs: {run.fixes.most_common(5)}"
    print("self-test ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--set", choices=sorted(SETS), default="v1")
    ap.add_argument("--gold")
    ap.add_argument("--items")
    ap.add_argument("--stats", help="strata populations for reweighting ('' to skip)")
    ap.add_argument("--drop-chains", action="store_true", help="drop chains.txt keys on both sides, as production does")
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    ap.add_argument("--tag", default="")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    st = SETS[args.set]
    gold_path, items_path = args.gold or st["gold"], args.items or st["items"]
    stats = st["stats"] if args.stats is None else args.stats
    if not os.path.exists(gold_path):
        raise SystemExit(f"no v5 gold at {gold_path} (pass --gold)")
    gold, items = S.load_jsonl(gold_path), S.load_jsonl(items_path)
    alias, excluded = S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json")
    if args.self_test:
        self_test(gold, items, alias, excluded, stats)
        return
    tag = args.tag or ("" if args.set == "v1" else f"__{args.set}")
    for path in args.runs:
        run = Run(path, items)
        per_rep, flips = evaluate(gold, items, run, alias, excluded, args.drop_chains, stats)
        md, cs = report(run, per_rep, flips, args.out, tag)
        print(f"{path}\n  -> {md}\n  -> {cs}")


if __name__ == "__main__":
    main()
