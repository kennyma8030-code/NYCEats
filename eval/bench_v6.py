"""The budgeted Haiku 5.5 benchmark of the v6 prompts: plan, run, compare.

    python eval/bench_v6.py plan      # no API: dry-runs every step, counts calls, estimates cost
    python eval/bench_v6.py run       # spends, capped at BUDGET across every step (eval/budget.py)
    python eval/bench_v6.py compare   # no API: scores what ran -> eval/bench_v6/compare.json

Steps run in priority order. Each stops cleanly when the shared ledger
reaches the cap, and so does every step after it. The ledger lives in
eval/bench_v6/ledger.json, so running `run` again resumes: finished calls
are cached in their run files and never re-sent or re-billed.

  a  v6 comment mode, reasoning medium, every labeled v1 comment + every v2 comment
  b  current prompt (prompt.py), comment mode, medium, the same comments (the baseline)
  c  v6 thread mode, medium, v1's 17 whole threads, re-rendered by render_chunk
  d  current prompt thread mode, medium, the same chunks in production's rendering
     (the missing Haiku thread baseline)
  e  reasoning LOW: v6 comment on a fixed 300-comment subset of (a), and v6 thread on
     a third of (c)'s chunks. Hashed choice, own run files, so low and medium compare
     on identical items
  f  if budget remains: v6 thread mode, medium, on the chunks of v2's comments

v1 and v2 share comments. Each step's invocations write to one run file, so a
comment in both sets is called once. v6 uses the strict schema (--schema)
if a one-call probe shows the provider accepts it, and json_object
otherwise. The current prompt has no schema, so a and b differ in that too;
compare.json records it.

The key comes only from KEY_FILE and is never printed. No other key is used.
"""

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import run as R  # noqa: E402

# ---------------------------------------------------------------- settings
MODEL = "anthropic/claude-haiku-5.5"      # OpenRouter slug, checked against /api/v1/models
BUDGET = 4.00                              # USD, owner-approved, across every step
KEY_FILE = os.path.join(ROOT, ".env.eval")
OUT = os.path.join(HERE, "bench_v6")
LEDGER = os.path.join(OUT, "ledger.json")
STATE = os.path.join(OUT, "state.json")
WORKERS = 8
MAX_TOKENS = {"comment": 8000, "thread": 16000}   # also each call's reserved worst case
V6 = {"comment": "file:" + os.path.join(HERE, "prompts", "v6_comment.py"),
      "thread": "file:" + os.path.join(HERE, "prompts", "v6_thread.py")}
V1, V2 = os.path.join(HERE, "items.jsonl"), os.path.join(HERE, "v2", "items.jsonl")
V1_THREADS = [f"t{i:03d}" for i in range(1, 18)]
LOW_COMMENTS = 300
SEED = "nyceats-bench-v6"
SUBSET_COMMENT = os.path.join(OUT, "subset_comment.txt")
SUBSET_THREAD = os.path.join(OUT, "subset_thread.txt")

# Haiku 5.5 on OpenRouter, USD per token (prompts under 100k tokens).
PRICE_IN, PRICE_OUT = 0.10e-6, 0.50e-6
# Planning assumptions for output, per call. Reasoning on thread chunks is the
# v5 benchmark's ~6.7k; the rest are guesses the run will replace.
ASSUME = {("comment", "medium"): {"reasoning": 1200, "visible": {"v6": 300, "current": 150}},
          ("thread", "medium"): {"reasoning": 6700, "visible": {"v6": 2000, "current": 1200}},
          ("comment", "low"): {"reasoning": 500, "visible": {"v6": 300, "current": 150}},
          ("thread", "low"): {"reasoning": 2700, "visible": {"v6": 2000, "current": 1200}}}
# The v5 benchmark page: comment ~$0.41 per 1k comments at medium (3x prompt).
PAGE_COMMENT_PER_CALL = 0.41 / 1000


def inv(items, only=None, labeled=False, call_keys=None):
    return {"items": items, "only": only, "labeled": labeled, "call_keys": call_keys}


STEPS = [
    {"id": "a", "what": "v6 comment, medium, v1 labeled + v2", "prompt": "v6", "mode": "comment",
     "reasoning": "medium", "tag": "bench6-med", "invocations": [inv(V1, labeled=True), inv(V2)]},
    {"id": "b", "what": "current comment, medium, same comments", "prompt": "current", "mode": "comment",
     "reasoning": "medium", "tag": "bench6-med", "invocations": [inv(V1, labeled=True), inv(V2)]},
    {"id": "c", "what": "v6 thread, medium, v1 whole threads (render_chunk)", "prompt": "v6",
     "mode": "thread", "reasoning": "medium", "tag": "bench6-med", "invocations": [inv(V1, only=V1_THREADS)]},
    {"id": "d", "what": "current thread, medium, same chunks (stored rendering)", "prompt": "current",
     "mode": "thread", "reasoning": "medium", "tag": "bench6-med", "invocations": [inv(V1, only=V1_THREADS)]},
    {"id": "e-comment", "what": f"v6 comment, LOW, {LOW_COMMENTS}-comment subset of a", "prompt": "v6",
     "mode": "comment", "reasoning": "low", "tag": "bench6-low",
     "invocations": [inv(V1, labeled=True, call_keys=SUBSET_COMMENT), inv(V2, call_keys=SUBSET_COMMENT)]},
    {"id": "e-thread", "what": "v6 thread, LOW, a third of c's chunks", "prompt": "v6", "mode": "thread",
     "reasoning": "low", "tag": "bench6-low", "invocations": [inv(V1, only=V1_THREADS, call_keys=SUBSET_THREAD)]},
    {"id": "f", "what": "v6 thread, medium, v2 comments' chunks", "prompt": "v6", "mode": "thread",
     "reasoning": "medium", "tag": "bench6-med", "invocations": [inv(V2)]},
]


# ---------------------------------------------------------------- jobs
def prompt_spec(step):
    return V6[step["mode"]] if step["prompt"] == "v6" else "current"


def load_pmod(step):
    pmod, _ = R.load_prompt(prompt_spec(step), step["mode"])
    return pmod


def jobs_for(step, invocation):
    """The exact jobs run.py would build for one invocation (same code path)."""
    pmod = load_pmod(step)
    only = invocation["only"]
    if invocation["labeled"]:
        with open(os.path.join(HERE, "gold.jsonl"), encoding="utf-8") as f:
            only = sorted({json.loads(l)["item_id"] for l in f})
    rows = None
    custom = prompt_spec(step).startswith("file:")
    if custom and step["mode"] == "thread" and hasattr(pmod, "render_chunk"):
        side = os.path.splitext(invocation["items"])[0] + ".thread_rows.jsonl"
        with open(side, encoding="utf-8") as f:
            rows = {r["call_key"]: r for r in map(json.loads, f)}
    jobs = R.build_jobs(R.load_items(invocation["items"], only), step["mode"], pmod,
                        custom=custom, thread_rows=rows)
    if invocation["call_keys"]:
        with open(invocation["call_keys"], encoding="utf-8") as f:
            keep = {l.strip() for l in f if l.strip()}
        jobs = [j for j in jobs if j["call_key"] in keep]
    return pmod, jobs


def step_jobs(step):
    """{call_key: job} across a step's invocations (shared comments counted once)."""
    out, pmod = {}, None
    for i in step["invocations"]:
        pmod, jobs = jobs_for(step, i)
        for j in jobs:
            out.setdefault(j["call_key"], j)
    return pmod, out


def run_file(step, schema):
    pmod = load_pmod(step)
    ph = R.prompt_hash(pmod.SYSTEM_PROMPT)
    tag = step["tag"] + ("_schema" if schema and hasattr(pmod, "RESPONSE_FORMAT") else "")
    return os.path.join(HERE, "runs", f"{MODEL.replace('/', '_')}__{ph}__{step['mode']}__{tag}.jsonl")


def hashed(keys, n):
    return sorted(keys, key=lambda k: hashlib.sha256(f"{SEED}|{k}".encode()).hexdigest())[:n]


def write_subsets():
    """Deterministic low-reasoning subsets, drawn from steps a and c."""
    os.makedirs(OUT, exist_ok=True)
    _, a = step_jobs(STEPS[0])
    _, c = step_jobs(STEPS[2])
    comment = hashed(a, LOW_COMMENTS)
    thread = hashed(c, math.ceil(len(c) / 3))
    for path, keys in ((SUBSET_COMMENT, comment), (SUBSET_THREAD, thread)):
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(keys)) + "\n")
    return len(comment), len(thread)


# ---------------------------------------------------------------- plan
def estimate(step, pmod, jobs):
    sys_chars = len(pmod.SYSTEM_PROMPT)
    tin = sum(sys_chars + len(j["user"]) for j in jobs.values()) / 4
    a = ASSUME[(step["mode"], step["reasoning"])]
    tout = len(jobs) * (a["reasoning"] + a["visible"][step["prompt"]])
    tokens_cost = tin * PRICE_IN + tout * PRICE_OUT
    worst = sum((sys_chars + len(j["user"])) / 3 * PRICE_IN + MAX_TOKENS[step["mode"]] * PRICE_OUT
                for j in jobs.values())
    page = len(jobs) * PAGE_COMMENT_PER_CALL if step["mode"] == "comment" else None
    return {"calls": len(jobs), "input_tokens": round(tin), "assumed_output_tokens": tout,
            "est_usd": round(tokens_cost, 3), "page_rate_usd": None if page is None else round(page, 3),
            "worst_case_usd": round(worst, 2)}


def dry_run_args(step, invocation, schema=False):
    a = [sys.executable, os.path.join(HERE, "run.py"), "--model", MODEL, "--mode", step["mode"],
         "--prompt", prompt_spec(step), "--items", invocation["items"], "--tag", step["tag"],
         "--reasoning", step["reasoning"], "--max-tokens", str(MAX_TOKENS[step["mode"]]),
         "--workers", str(WORKERS), "--omit-temperature", "--cache"]
    if invocation["only"]:
        a += ["--only", *invocation["only"]]
    if invocation["labeled"]:
        a += ["--labeled-only"]
    if invocation["call_keys"]:
        a += ["--call-keys", invocation["call_keys"]]
    if schema and step["prompt"] == "v6":
        a += ["--schema"]
    return a


def plan():
    nc, nt = write_subsets()
    print(f"model {MODEL}; budget ${BUDGET:.2f}; subsets: {nc} comment calls, {nt} thread chunks (hashed)\n")
    rows, running = [], 0.0
    for step in STEPS:
        for i in step["invocations"]:
            p = subprocess.run(dry_run_args(step, i) + ["--dry-run"], capture_output=True, text=True)
            if p.returncode != 0:
                raise SystemExit(f"step {step['id']}: dry run failed\n{p.stderr[-800:]}")
            first = p.stdout.splitlines()[0]
            print(f"  dry run {step['id']}: {first.split(';')[1].split('->')[0].strip()} "
                  f"({os.path.relpath(i['items'], HERE)})")
        pmod, jobs = step_jobs(step)
        e = estimate(step, pmod, jobs)
        running += e["est_usd"]
        rows.append({"step": step["id"], "what": step["what"], **e, "cumulative_est_usd": round(running, 3)})
    print()
    print(f"{'step':10s} {'calls':>6s} {'in tok':>10s} {'est $':>7s} {'page $':>7s} {'worst $':>8s} {'cum $':>7s}  what")
    for r in rows:
        print(f"{r['step']:10s} {r['calls']:6d} {r['input_tokens']:10,d} {r['est_usd']:7.3f} "
              f"{(r['page_rate_usd'] if r['page_rate_usd'] is not None else float('nan')):7.3f} "
              f"{r['worst_case_usd']:8.2f} {r['cumulative_est_usd']:7.3f}  {r['what']}")
    with open(os.path.join(OUT, "plan.json"), "w", encoding="utf-8") as f:
        json.dump({"model": MODEL, "budget": BUDGET, "assumptions": {str(k): v for k, v in ASSUME.items()},
                   "prices_per_token": {"in": PRICE_IN, "out": PRICE_OUT}, "steps": rows}, f, indent=1)
    print(f"\nwritten {os.path.join(OUT, 'plan.json')}")


# ---------------------------------------------------------------- run
def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"model": MODEL, "budget": BUDGET, "schema": None, "steps": {}}


def save_state(st):
    os.makedirs(OUT, exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)


def invoke(step, invocation, schema, extra=()):
    a = dry_run_args(step, invocation, schema) + ["--key-file", KEY_FILE, "--budget-file", LEDGER,
                                                  "--budget", str(BUDGET), *extra]
    p = subprocess.run(a, text=True)
    return p.returncode


def last_records(path, n=1):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f][-n:]


def probe_schema(st):
    """One call with --schema. If the provider rejects it, one without. Any other
    failure (bad key, rejected parameter) stops the plan before it spends more."""
    if st.get("schema") is not None:
        return st["schema"]
    step, first = STEPS[0], STEPS[0]["invocations"][0]
    for schema in (True, False):
        code = invoke(step, first, schema, ["--limit", "1"])
        recs = last_records(run_file(step, schema))
        if code == 0 and recs and recs[-1].get("raw") is not None:
            st["schema"] = schema
            save_state(st)
            print(f"probe: {'strict schema accepted' if schema else 'json_object (schema rejected)'}")
            return schema
        err = recs[-1].get("error") if recs else f"exit {code}"
        print(f"probe with schema={schema} failed: {str(err)[:300]}")
        if code == 3:
            raise SystemExit("budget already exhausted")
    raise SystemExit("both probes failed; check the key file, the slug and the parameters before spending more")


def run_all():
    if not os.path.exists(KEY_FILE):
        raise SystemExit(f"{KEY_FILE} does not exist")
    with open(KEY_FILE, encoding="utf-8") as f:
        if not any(l.strip().startswith("OPENROUTER_API_KEY=") for l in f):
            raise SystemExit(f"{KEY_FILE} has no OPENROUTER_API_KEY line")
    write_subsets()
    st = load_state()
    schema = probe_schema(st)
    for step in STEPS:
        status = "done"
        for i in step["invocations"]:
            # A budgeted run never retries a lost attempt itself, so each
            # invocation gets one more pass that re-sends only errored calls.
            for _ in range(2):
                code = invoke(step, i, schema)
                if code == 3:
                    status = "capped"
                    break
                if code != 0:
                    status = f"failed (exit {code})"
                    break
            if status != "done":
                break
        st["steps"][step["id"]] = {"status": status, "run_file": os.path.relpath(run_file(step, schema), ROOT),
                                   "schema": bool(schema and step["prompt"] == "v6")}
        save_state(st)
        print(f"step {step['id']}: {status}")
        if status == "capped":
            print("budget reached; later steps skipped. `python eval/bench_v6.py compare` scores what ran.")
            break
        if status.startswith("failed"):
            raise SystemExit(f"step {step['id']} {status}; stopping")


# ---------------------------------------------------------------- compare
METRICS = ["drop_rate", "mention_recall", "mention_precision", "negative_mention_recall",
           "value_complaint_recall", "dish_negative_recall", "sign_accuracy", "is_firsthand_acc"]


def run_stats(path, keys):
    """Cost, calls, tokens and latency for the records of the given call keys."""
    s = {"records": 0, "errors": 0, "json_ok": 0, "cost_usd": 0.0, "estimated_cost_calls": 0,
         "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "latency": []}
    seen = set()
    for r in map(json.loads, open(path, encoding="utf-8")):
        if r["call_key"] not in keys or r.get("rep", 0) != 0:
            continue
        s["records"] += 1
        s["cost_usd"] += float(r.get("ledger_cost") or (r.get("usage") or {}).get("cost") or 0)
        s["estimated_cost_calls"] += bool(r.get("cost_estimated"))
        if r.get("raw") is None:
            s["errors"] += 1
            continue
        seen.add(r["call_key"])
        s["json_ok"] += bool(r.get("json_ok"))
        u = r.get("usage") or {}
        s["prompt_tokens"] += u.get("prompt_tokens") or 0
        s["completion_tokens"] += u.get("completion_tokens") or 0
        s["reasoning_tokens"] += r.get("reasoning_tokens") or 0
        if r.get("latency_s") is not None:
            s["latency"].append(r["latency_s"])
    lat = s.pop("latency")
    s["mean_latency_s"] = round(sum(lat) / len(lat), 2) if lat else None
    s["cost_usd"] = round(s["cost_usd"], 4)
    s["finished_calls"] = len(seen)
    return s


def score(paths_keys, gold_path, items_path, stats_path):
    """Score several runs on the comments every one of them covered."""
    import score as S
    items = S.load_jsonl(items_path)
    alias, excluded = S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json")
    loaded = {name: S.load_run(path, items) for name, (path, _) in paths_keys.items()}
    common = None
    for reps, covered, _, _ in loaded.values():
        common = set(covered.get(0, set())) if common is None else common & covered.get(0, set())
    common = common or set()
    gold = [g for g in S.load_jsonl(gold_path) if g["comment_id"] in common]
    # The calls behind the shared comments, so cost and tokens compare like with like
    # (a 300-comment low run against the same 300 comments of the medium run).
    cover = {}
    for it in items:
        chunks = ([it["inputs"]["thread"]] if it["kind"] == "comment" else it["thread_chunks"])
        for ch in chunks:
            cover[f"thread:{it['thread_id']}:{ch['chunk_index']}"] = set(ch["short_ids"].values())

    def behind(key):
        if key.startswith("comment:"):
            return key.split(":", 1)[1] in common
        return bool(cover.get(key, set()) & common)

    out = {}
    for name, run in loaded.items():
        per_rep, _, _, _ = S.evaluate(gold, items, run, alias, excluded, True, stats_path)
        r0 = per_rep[0]
        res = {"comments": len(gold), "with_mention": sum(g["has_mention"] for g in gold)}
        for scope in ("overall", "reweighted"):
            if scope in r0:
                res[scope] = {m: r0[scope].get(m) for m in METRICS}
        path, keys = paths_keys[name]
        res["run"] = run_stats(path, {k for k in keys if behind(k)})
        out[name] = res
    return out


def delta(a, b, scope="overall"):
    d = {}
    for m in METRICS:
        x, y = (a.get(scope) or {}).get(m), (b.get(scope) or {}).get(m)
        d[m] = round(x - y, 4) if isinstance(x, (int, float)) and isinstance(y, (int, float)) else None
    for k in ("cost_usd", "reasoning_tokens", "completion_tokens", "mean_latency_s"):
        x, y = a["run"].get(k), b["run"].get(k)
        d[k] = round(x - y, 4) if x is not None and y is not None else None
    return d


def compare():
    st = load_state()
    steps = {s["id"]: s for s in STEPS}
    ran = {k: v for k, v in st.get("steps", {}).items() if os.path.exists(os.path.join(ROOT, v["run_file"]))}

    def pk(sid, inv_filter=None):
        _, jobs = step_jobs(steps[sid])
        return os.path.join(ROOT, ran[sid]["run_file"]), set(jobs)

    stats = os.path.join(HERE, "sampling_stats.json")
    out = {"model": MODEL, "budget": BUDGET, "steps": st.get("steps"), "schema_for_v6": st.get("schema"),
           "note": ("identical comment sets per comparison (the comments every run in it covered); "
                    "chains dropped on both sides as production does; 'reweighted' is v1's "
                    "population estimate over single-comment strata"),
           "comparisons": {}}
    if os.path.exists(LEDGER):
        with open(LEDGER, encoding="utf-8") as f:
            out["ledger"] = json.load(f)
    C = out["comparisons"]
    if "a" in ran and "b" in ran:
        C["comment_medium_v1"] = score({"v6": pk("a"), "current": pk("b")}, os.path.join(HERE, "gold.jsonl"), V1, stats)
        C["comment_medium_v2"] = score({"v6": pk("a"), "current": pk("b")},
                                       os.path.join(HERE, "v2", "gold.jsonl"), V2, "")
    if "c" in ran and "d" in ran:
        C["thread_medium_v1"] = score({"v6": pk("c"), "current": pk("d")}, os.path.join(HERE, "gold.jsonl"), V1, "")
    if "a" in ran and "c" in ran:
        C["v6_comment_vs_thread_v1"] = score({"comment": pk("a"), "thread": pk("c")},
                                             os.path.join(HERE, "gold.jsonl"), V1, "")
    if "a" in ran and "e-comment" in ran:
        for g, items, tag in ((os.path.join(HERE, "gold.jsonl"), V1, "v1"),
                              (os.path.join(HERE, "v2", "gold.jsonl"), V2, "v2")):
            r = score({"low": pk("e-comment"), "medium": pk("a")}, g, items, "")
            r["delta_low_minus_medium"] = delta(r["low"], r["medium"])
            C[f"comment_low_vs_medium_{tag}"] = r
    if "c" in ran and "e-thread" in ran:
        r = score({"low": pk("e-thread"), "medium": pk("c")}, os.path.join(HERE, "gold.jsonl"), V1, "")
        r["delta_low_minus_medium"] = delta(r["low"], r["medium"])
        C["thread_low_vs_medium_v1"] = r
    if "f" in ran and "a" in ran:
        C["v6_thread_vs_comment_v2"] = score({"thread": pk("f"), "comment": pk("a")},
                                             os.path.join(HERE, "v2", "gold.jsonl"), V2, "")
    for name, r in C.items():
        pairs = [k for k in r if isinstance(r[k], dict) and "run" in r[k]]
        if len(pairs) == 2 and "delta_low_minus_medium" not in r:
            r["delta_" + "_minus_".join(pairs)] = delta(r[pairs[0]], r[pairs[1]])
    path = os.path.join(OUT, "compare.json")
    os.makedirs(OUT, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    for name, r in C.items():
        print(f"== {name}")
        for k, v in r.items():
            if isinstance(v, dict) and "run" in v:
                o = v.get("overall") or {}
                print(f"  {k:8s} n={v['comments']:4d}  " + "  ".join(
                    f"{m.split('_')[0][:6]}:{o.get(m):.3f}" if isinstance(o.get(m), float) else f"{m.split('_')[0][:6]}:{o.get(m)}"
                    for m in METRICS) + f"  ${v['run']['cost_usd']:.3f}")
    print(f"written {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("plan", "run", "compare"))
    a = ap.parse_args()
    {"plan": plan, "run": run_all, "compare": compare}[a.cmd]()


if __name__ == "__main__":
    main()
