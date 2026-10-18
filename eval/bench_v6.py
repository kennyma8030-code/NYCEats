"""The budgeted Haiku 5.5 benchmark of the v6 prompts: plan, run, compare.

    python eval/bench_v6.py plan      # no API: dry-runs every step, counts calls, estimates cost
    python eval/bench_v6.py probe     # 2 tiny direct calls (effort medium, then low), counted in the ledger
    python eval/bench_v6.py run       # Message Batches, capped at BUDGET across every step (eval/budget.py)
    python eval/bench_v6.py compare   # no API: scores what ran -> eval/bench_v6/compare.json

Runs on Anthropic's API directly (anthropic SDK, eval/anthropic_backend.py),
model claude-haiku-5-5, every step through the Message Batches API at half
price. Thinking is adaptive (on by default for Haiku 5.5); effort medium is
the main setting, low the slice. v6 sends its strict schema as
output_config.format, and the system prompt is marked for caching. Each
sub-batch's worst case is held in the ledger before it is submitted and
replaced by the real cost when it ends. Batch ids are persisted next to each
run file, so an interrupted `run` re-attaches to batches in flight rather
than resubmitting them.

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
comment in both sets is called once. v6 uses the strict schema once the
probe shows it is accepted. The current prompt has no schema (it asks for
JSON in prose), so a and b differ in that too; compare.json records it.

The key is ANTHROPIC_API_KEY, read in-process from KEY_FILE and never printed;
no other variable in that file is read.
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
MODEL = "claude-haiku-5-5"                 # Claude API model id (claude-api skill, models.md)
BUDGET = 4.00                              # USD, owner-approved, across every step
# The repo root's .env. From a worktree, that is the main checkout's.
KEY_FILE = "/Users/kenny/NYCEats/.env"
KEY_VAR = "ANTHROPIC_API_KEY"
OUT = os.path.join(HERE, "bench_v6")
LEDGER = os.path.join(OUT, "ledger.json")
STATE = os.path.join(OUT, "state.json")
WORKERS = 8
# Thinking counts toward max_tokens. A comment rarely needs 3k of thinking plus
# 2k of JSON; a 25-comment chunk took ~6.7k of thinking in the v5 benchmark plus
# up to ~5k of JSON. Each request's worst case is held before its batch is sent.
MAX_TOKENS = {"comment": 6000, "thread": 16000}
V6 = {"comment": "file:" + os.path.join(HERE, "prompts", "v6_comment.py"),
      "thread": "file:" + os.path.join(HERE, "prompts", "v6_thread.py")}
# Round 1 of v6, frozen: every step up to k ran on it, and its run files are keyed by
# its hash (comment a15cfb978cce, thread 44e1a49c7781). "v6" is the live prompt.
V6R1 = {"comment": "file:" + os.path.join(HERE, "prompts", "v6r1_comment.py"),
        "thread": "file:" + os.path.join(HERE, "prompts", "v6r1_thread.py")}
V1, V2 = os.path.join(HERE, "items.jsonl"), os.path.join(HERE, "v2", "items.jsonl")
V1_THREADS = [f"t{i:03d}" for i in range(1, 18)]
LOW_COMMENTS = 300
SEED = "nyceats-bench-v6"
SUBSET_COMMENT = os.path.join(OUT, "subset_comment.txt")
SUBSET_THREAD = os.path.join(OUT, "subset_thread.txt")
# The round-2 re-test: a hashed 600 of a's comments. Same hash order as the 300-comment
# low subset, so it contains all of it.
R2_COMMENTS = 600
SUBSET_R2 = os.path.join(OUT, "subset_comment_r2.txt")
# The truncated calls of the first medium runs (stop_reason max_tokens), committed so
# the re-runs h and i are a fixed set. See DIAGNOSIS.md.
KEYS_H = os.path.join(OUT, "keys_h_thread_truncated.txt")
KEYS_I = os.path.join(OUT, "keys_i_comment_truncated.txt")
MERGED = os.path.join(OUT, "merged")        # derived run files for compare; not committed

# Claude Haiku 5.5, USD per token (prompts of 100k tokens or fewer), and the batch discount.
PRICE_IN, PRICE_OUT, BATCH = 0.10e-6, 0.50e-6, 0.5
# Measured by the probe (v6 comment, strict schema): 1.84 characters per input token.
CHARS_PER_TOKEN = 1.84
# Planning prices input at the cache-write rate: every request marks the system
# prompt for caching, and in a batch a hit is best effort, so a miss costs 1.25x.
PRICE_IN_PLAN = 0.125e-6
# Planning assumptions for output, per call. Reasoning on thread chunks is the
# v5 benchmark's ~6.7k; the rest are guesses the run will replace.
ASSUME = {("comment", "medium"): {"reasoning": 1200, "visible": {"v6": 300, "current": 150}},
          ("thread", "medium"): {"reasoning": 6700, "visible": {"v6": 2000, "current": 1200}},
          ("comment", "low"): {"reasoning": 500, "visible": {"v6": 300, "current": 150}},
          ("thread", "low"): {"reasoning": 2700, "visible": {"v6": 2000, "current": 1200}}}
# The v5 benchmark page (OpenRouter, full price): comment ~$0.41 per 1k comments at medium.
PAGE_COMMENT_PER_CALL = 0.41 / 1000 * BATCH


def inv(items, only=None, labeled=False, call_keys=None):
    return {"items": items, "only": only, "labeled": labeled, "call_keys": call_keys}


STEPS = [
    {"id": "a", "what": "v6 comment, medium, v1 labeled + v2", "prompt": "v6r1", "mode": "comment",
     "reasoning": "medium", "tag": "bench6-med", "invocations": [inv(V1, labeled=True), inv(V2)]},
    {"id": "b", "what": "current comment, medium, same comments", "prompt": "current", "mode": "comment",
     "reasoning": "medium", "tag": "bench6-med", "invocations": [inv(V1, labeled=True), inv(V2)]},
    {"id": "c", "what": "v6 thread, medium, v1 whole threads (render_chunk)", "prompt": "v6r1",
     "mode": "thread", "reasoning": "medium", "tag": "bench6-med", "invocations": [inv(V1, only=V1_THREADS)]},
    {"id": "d", "what": "current thread, medium, same chunks (stored rendering)", "prompt": "current",
     "mode": "thread", "reasoning": "medium", "tag": "bench6-med", "invocations": [inv(V1, only=V1_THREADS)]},
    {"id": "e-comment", "what": f"v6 comment, LOW, {LOW_COMMENTS}-comment subset of a", "prompt": "v6r1",
     "mode": "comment", "reasoning": "low", "tag": "bench6-low",
     "invocations": [inv(V1, labeled=True, call_keys=SUBSET_COMMENT), inv(V2, call_keys=SUBSET_COMMENT)]},
    {"id": "e-thread", "what": "v6 thread, LOW, a third of c's chunks", "prompt": "v6r1", "mode": "thread",
     "reasoning": "low", "tag": "bench6-low", "invocations": [inv(V1, only=V1_THREADS, call_keys=SUBSET_THREAD)]},
    {"id": "f", "what": "v6 thread, medium, v2 comments' chunks", "prompt": "v6r1", "mode": "thread",
     "reasoning": "medium", "tag": "bench6-med", "invocations": [inv(V2)]},
    {"id": "g", "what": "current thread, medium, v2 comments' chunks (baseline for f)", "prompt": "current",
     "mode": "thread", "reasoning": "medium", "tag": "bench6-med", "invocations": [inv(V2)]},
    # Re-runs of what medium effort truncated (DIAGNOSIS.md): own tags, so the first
    # attempts stay as they ran; compare merges them into a second view.
    {"id": "h", "what": "v6 thread, medium, the truncated chunks of c+f, max_tokens 32k", "prompt": "v6r1",
     "mode": "thread", "reasoning": "medium", "tag": "bench6-med32k", "max_tokens": 32000,
     "assume": {"reasoning": 20000, "visible": 4000},
     "invocations": [inv(V1, only=V1_THREADS, call_keys=KEYS_H), inv(V2, call_keys=KEYS_H)]},
    {"id": "i", "what": "v6 comment, medium, the 6 truncated calls of a, max_tokens 16k", "prompt": "v6r1",
     "mode": "comment", "reasoning": "medium", "tag": "bench6-med16k", "max_tokens": 16000,
     "assume": {"reasoning": 6000, "visible": 4000},
     "invocations": [inv(V1, labeled=True, call_keys=KEYS_I), inv(V2, call_keys=KEYS_I)]},
    # Low effort on every thread chunk c and f covered. Same tag and run file as
    # e-thread, so its 8 finished chunks are skipped; the cap stops it if money runs out.
    {"id": "j", "what": "v6 thread, LOW, every chunk of c+f, max_tokens 32k", "prompt": "v6r1", "mode": "thread",
     "reasoning": "low", "tag": "bench6-low", "max_tokens": 32000,
     "invocations": [inv(V1, only=V1_THREADS), inv(V2)]},
    {"id": "k", "what": "v6 comment, LOW, all of a's comments (widens e-comment)", "prompt": "v6r1",
     "mode": "comment", "reasoning": "low", "tag": "bench6-low", "max_tokens": 16000,
     "invocations": [inv(V1, labeled=True), inv(V2)]},
    # Round 2: the live v6 prompt (owner decisions and benchmark fixes, CONVENTIONS.md),
    # low effort, on a hashed 600 of a's comments. A subset because ~$0.39 is left under
    # the cap: 1,006 comments would expect ~$0.19 but could reach ~$0.44 with no cache hits.
    {"id": "l", "what": f"v6 round 2, comment, LOW, a hashed {R2_COMMENTS} of a's comments", "prompt": "v6",
     "mode": "comment", "reasoning": "low", "tag": "bench6-low-r2", "max_tokens": 16000,
     "assume": {"reasoning": 400, "visible": 300},
     "invocations": [inv(V1, labeled=True, call_keys=SUBSET_R2), inv(V2, call_keys=SUBSET_R2)]},
]


# ---------------------------------------------------------------- jobs
def prompt_spec(step):
    return {"v6": V6, "v6r1": V6R1}[step["prompt"]][step["mode"]] if step["prompt"].startswith("v6") else "current"


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


def max_tokens(step):
    return step.get("max_tokens", MAX_TOKENS[step["mode"]])


def write_rerun_keys():
    """The truncated calls of the first medium runs, read (never written) from their
    run files. Written once; the committed lists are what h and i run on."""
    for path, step in ((KEYS_H, STEPS[2]), (KEYS_I, STEPS[0])):
        if os.path.exists(path):
            continue
        src = run_file(step, True)
        keys = sorted({r["call_key"] for r in map(json.loads, open(src, encoding="utf-8"))
                       if r.get("stop_reason") == "max_tokens" or (r.get("raw") is not None and not r.get("json_ok"))})
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(keys) + "\n")


def finished(step, schema=True):
    """Call keys the step's run file already holds a finished record for (read-only)."""
    path = run_file(step, schema)
    if not os.path.exists(path):
        return set()
    done = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue                          # a line still being written
            if r.get("raw") is not None and r.get("rep", 0) == 0:
                done.add(r["call_key"])
    return done


def write_subsets():
    """Deterministic low-reasoning subsets, drawn from steps a and c."""
    os.makedirs(OUT, exist_ok=True)
    _, a = step_jobs(STEPS[0])
    _, c = step_jobs(STEPS[2])
    comment = hashed(a, LOW_COMMENTS)
    with open(SUBSET_R2, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(hashed(a, R2_COMMENTS))) + "\n")
    thread = hashed(c, math.ceil(len(c) / 3))
    for path, keys in ((SUBSET_COMMENT, comment), (SUBSET_THREAD, thread)):
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(keys)) + "\n")
    return len(comment), len(thread)


# ---------------------------------------------------------------- plan
def estimate(step, pmod, jobs, reps=1):
    """Batch-price estimate. Input is priced uncached (a cache hit only lowers it)."""
    import anthropic_backend as AB
    sys_chars = len(pmod.SYSTEM_PROMPT)
    tin = reps * sum(sys_chars + len(j["user"]) for j in jobs.values()) / CHARS_PER_TOKEN
    a = ASSUME[(step["mode"], step["reasoning"])]
    a = {"reasoning": step["assume"]["reasoning"], "visible": {step["prompt"]: step["assume"]["visible"]}} \
        if "assume" in step else a
    vis = a["visible"].get(step["prompt"], a["visible"].get("v6" if step["prompt"].startswith("v6") else step["prompt"]))
    tout = reps * len(jobs) * (a["reasoning"] + vis)
    tokens_cost = (tin * PRICE_IN_PLAN + tout * PRICE_OUT) * BATCH
    worst = reps * sum(AB.worst_case(pmod.SYSTEM_PROMPT, j["user"], max_tokens(step), batch=True)
                       for j in jobs.values())
    page = reps * len(jobs) * PAGE_COMMENT_PER_CALL if step["mode"] == "comment" else None
    return {"calls": len(jobs), "input_tokens": round(tin), "assumed_output_tokens": tout,
            "est_usd": round(tokens_cost, 3), "page_rate_usd": None if page is None else round(page, 3),
            "worst_case_usd": round(worst, 2)}


def dry_run_args(step, invocation, schema=False):
    a = [sys.executable, os.path.join(HERE, "run.py"), "--api", "anthropic", "--model", MODEL,
         "--mode", step["mode"], "--prompt", prompt_spec(step), "--items", invocation["items"],
         "--tag", step["tag"], "--reasoning", step["reasoning"],
         "--max-tokens", str(max_tokens(step)), "--workers", str(WORKERS), "--cache"]
    if invocation["only"]:
        a += ["--only", *invocation["only"]]
    if invocation["labeled"]:
        a += ["--labeled-only"]
    if invocation["call_keys"]:
        a += ["--call-keys", invocation["call_keys"]]
    if schema and step["prompt"].startswith("v6"):
        a += ["--schema"]
    return a


def additions():
    """Candidates for leftover budget, in priority order. Proposed, never run by `run`."""
    a, c = STEPS[0], STEPS[2]
    v1_all = [inv(V1)]
    return [
        ({**a, "id": "+low-all", "reasoning": "low", "what": "low slice widened to all of a (adds ~706 comments)"},
         "low-all", None),
        ({**a, "id": "+repeat-a", "what": "repeat of a (rep 2) for run-to-run noise"}, None, 1),
        ({**c, "id": "+v6-v1-all-thread", "invocations": v1_all,
          "what": "v6 thread on every v1 chunk (390 more than c; all 769 labeled comments)"}, "minus-c", None),
        ({**c, "id": "+cur-v1-all-thread", "prompt": "current", "invocations": v1_all,
          "what": "current thread on the same 390 chunks (pairs with the line above)"}, "minus-c", None),
    ]


def plan():
    nc, nt = write_subsets()
    write_rerun_keys()
    print(f"model {MODEL} (Message Batches, {BATCH:.0%} price); budget ${BUDGET:.2f}; "
          f"subsets: {nc} comment calls, {nt} thread chunks (hashed)\n")
    rows, running = [], 0.0
    for step in STEPS:
        for i in step["invocations"]:
            p = subprocess.run(dry_run_args(step, i, schema=True) + ["--dry-run"], capture_output=True, text=True)
            if p.returncode != 0:
                raise SystemExit(f"step {step['id']}: dry run failed\n{p.stderr[-800:]}")
            first = p.stdout.splitlines()[0]
            print(f"  dry run {step['id']}: {first.split(';')[1].split('->')[0].strip()} "
                  f"({os.path.relpath(i['items'], HERE)})")
        pmod, jobs = step_jobs(step)
        done = finished(step) & set(jobs)
        todo = {k: v for k, v in jobs.items() if k not in done}
        e = estimate(step, pmod, todo)
        running += e["est_usd"]
        rows.append({"step": step["id"], "what": step["what"], **e, "already_done": len(done),
                     "max_tokens": max_tokens(step), "cumulative_est_usd": round(running, 3)})

    _, a_jobs = step_jobs(STEPS[0])
    _, c_jobs = step_jobs(STEPS[2])
    low_done = set(open(SUBSET_COMMENT).read().split())
    extra = []
    for step, trim, rep in additions():
        pmod, jobs = step_jobs(step)
        if trim == "low-all":
            jobs = {k: v for k, v in a_jobs.items() if k not in low_done}
        elif trim == "minus-c":
            jobs = {k: v for k, v in jobs.items() if k not in c_jobs}
        e = estimate(step, pmod, jobs)
        running += e["est_usd"]
        extra.append({"step": step["id"], "what": step["what"], **e, "cumulative_est_usd": round(running, 3)})

    def show(rs):
        for r in rs:
            print(f"{r['step']:18s} {r.get('already_done', 0):5d} {r['calls']:6d} {r['input_tokens']:10,d} {r['est_usd']:7.3f} "
                  f"{(r['page_rate_usd'] if r['page_rate_usd'] is not None else float('nan')):7.3f} "
                  f"{r['worst_case_usd']:8.2f} {r['cumulative_est_usd']:7.3f}  {r['what']}")
    head = f"{'step':18s} {'done':>5s} {'to run':>6s} {'in tok':>10s} {'est $':>7s} {'page $':>7s} {'worst $':>8s} {'cum $':>7s}  what"
    print("\nPLAN (batch prices; estimates cover only what is not finished yet)\n" + head)
    show(rows)
    print(f"\nPROPOSED ADDITIONS, in priority order (not run unless added to STEPS)\n{head}")
    show(extra)
    with open(os.path.join(OUT, "plan.json"), "w", encoding="utf-8") as f:
        json.dump({"model": MODEL, "api": "anthropic", "batch_discount": BATCH, "budget": BUDGET,
                   "max_tokens": MAX_TOKENS, "assumptions": {str(k): v for k, v in ASSUME.items()},
                   "prices_per_token": {"in": PRICE_IN, "out": PRICE_OUT}, "steps": rows,
                   "proposed_additions": extra}, f, indent=1)
    print(f"\nwritten {os.path.join(OUT, 'plan.json')}")


# ---------------------------------------------------------------- run
def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"model": MODEL, "budget": BUDGET, "probe": {}, "steps": {}}


def save_state(st):
    os.makedirs(OUT, exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)


def invoke(step, invocation, schema, extra=(), batch=True):
    a = dry_run_args(step, invocation, schema) + ["--key-file", KEY_FILE, "--key-var", KEY_VAR,
                                                  "--budget-file", LEDGER, "--budget", str(BUDGET), *extra]
    if batch:
        a += ["--batch"]
    return subprocess.run(a, text=True).returncode


def check_key_file():
    if not os.path.exists(KEY_FILE):
        raise SystemExit(f"{KEY_FILE} does not exist")
    with open(KEY_FILE, encoding="utf-8") as f:
        if not any(l.strip().removeprefix("export ").startswith(KEY_VAR + "=") for l in f):
            raise SystemExit(f"{KEY_FILE} has no {KEY_VAR} line")


def probe():
    """Two direct (non-batch) calls on one v6 comment item with the strict schema:
    effort medium, then low. Each is counted in the ledger. Stops after the first
    if it is rejected, so no more than two calls are ever made."""
    check_key_file()
    st = load_state()
    a = STEPS[0]
    for effort in ("medium", "low"):
        step = {**a, "reasoning": effort, "tag": f"bench6-probe-{effort}"}
        code = invoke(step, a["invocations"][0], True, ["--limit", "1"], batch=False)
        path = run_file(step, True)
        recs = [json.loads(l) for l in open(path, encoding="utf-8")] if os.path.exists(path) else []
        r = recs[-1] if recs else {}
        u = r.get("usage") or {}
        res = {"ok": code == 0 and r.get("raw") is not None, "exit": code, "error": r.get("error"),
               "cost_usd": r.get("ledger_cost"), "thinking_tokens": r.get("reasoning_tokens"),
               "output_tokens": u.get("completion_tokens"), "input_tokens": u.get("prompt_tokens"),
               "stop_reason": r.get("stop_reason"), "json_ok": r.get("json_ok"),
               "mentions": sum(len(v) for v in (r.get("mentions_by_comment") or {}).values()),
               "latency_s": r.get("latency_s"), "run_file": os.path.relpath(path, ROOT)}
        st["probe"][effort] = res
        save_state(st)
        print(f"probe effort={effort}: " + json.dumps({k: v for k, v in res.items() if k != "run_file"}))
        if not res["ok"]:
            raise SystemExit(f"probe at effort {effort} failed; fix before `run` (no further calls made)")


def run_all():
    check_key_file()
    st = load_state()
    if not (st.get("probe", {}).get("medium", {}).get("ok") and st["probe"].get("low", {}).get("ok")):
        raise SystemExit("run `python eval/bench_v6.py probe` first: both efforts must be accepted")
    write_subsets()
    write_rerun_keys()
    schema = True
    for step in STEPS:
        status = "done"
        for i in step["invocations"]:
            code = invoke(step, i, schema)
            if code == 3:
                status = "capped"
                break
            if code != 0:
                status = f"failed (exit {code})"
                break
        st["steps"][step["id"]] = {"status": status, "run_file": os.path.relpath(run_file(step, schema), ROOT),
                                   "schema": bool(schema and step["prompt"].startswith("v6"))}
        save_state(st)
        print(f"step {step['id']}: {status}")
        if status == "capped":
            print("budget reached; later steps skipped. `python eval/bench_v6.py compare` scores what ran.")
            break
        if status.startswith("failed"):
            raise SystemExit(f"step {step['id']} {status}; stopping (re-run resumes and re-attaches)")


# ---------------------------------------------------------------- compare
METRICS = ["drop_rate", "mention_recall", "mention_precision", "negative_mention_recall",
           "value_complaint_recall", "dish_negative_recall", "sign_accuracy", "is_firsthand_acc",
           # five-level views (score.py): gold's 7 points collapsed to the owner's 5
           "food_5level_acc", "value_5level_acc", "service_5level_acc", "atmosphere_5level_acc",
           "wait_5level_acc", "overall_5level_agree", "overall_sign_agree",
           "opinion_type_acc", "opinion_none_acc", "opinion_stated_acc"]


def run_stats(path, keys):
    """Cost, calls, tokens and latency for the records of the given call keys."""
    s = {"records": 0, "errors": 0, "json_ok": 0, "cost_usd": 0.0, "estimated_cost_calls": 0,
         "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "latency": []}
    seen, batch_secs = set(), {}
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
        if r.get("batch_id") and r.get("batch_seconds") is not None:
            batch_secs[r["batch_id"]] = r["batch_seconds"]
        s["json_ok"] += bool(r.get("json_ok"))
        u = r.get("usage") or {}
        s["prompt_tokens"] += u.get("prompt_tokens") or 0
        s["completion_tokens"] += u.get("completion_tokens") or 0
        s["reasoning_tokens"] += r.get("reasoning_tokens") or 0
        if r.get("latency_s") is not None:
            s["latency"].append(r["latency_s"])
    lat = s.pop("latency")
    s["mean_latency_s"] = round(sum(lat) / len(lat), 2) if lat else None
    s["batches"] = len(batch_secs)
    s["batch_wall_seconds"] = round(sum(batch_secs.values()), 1) if batch_secs else None
    s["cost_usd"] = round(s["cost_usd"], 4)
    s["finished_calls"] = len(seen)
    return s


def score(paths_keys, gold_path, items_path, stats_path, fixes=False):
    """Score several runs on the comments every one of them covered."""
    import score as S
    items = S.load_jsonl(items_path)
    alias, excluded = S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json")
    # Several steps share a run file (c and f; d and g), so each run is cut to its
    # own step's calls first; otherwise one step's comparison picks up another's.
    loaded = {name: S.load_run(scoped(path, keys), items) for name, (path, keys) in paths_keys.items()}
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
        per_rep, _, _, _ = S.evaluate(gold, items, run, alias, excluded, True, stats_path, fixes)
        r0 = per_rep[0]
        res = {"comments": len(gold), "with_mention": sum(g["has_mention"] for g in gold)}
        for scope in ("overall", "reweighted"):
            if scope in r0:
                res[scope] = {m: r0[scope].get(m) for m in METRICS}
        res["food_confusion"] = r0["overall"].get("food_confusion")
        path, keys = paths_keys[name]
        res["run"] = run_stats(path, {k for k in keys if behind(k)})
        out[name] = res
    return out


def scoped(path, keys):
    """A copy of the run file with only the given call keys, under bench_v6/merged/."""
    os.makedirs(MERGED, exist_ok=True)
    tag = hashlib.sha256((path + "|" + "|".join(sorted(keys))).encode()).hexdigest()[:12]
    out = os.path.join(MERGED, f"_scope_{tag}.jsonl")
    with open(path, encoding="utf-8") as src, open(out, "w", encoding="utf-8") as f:
        for line in src:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue                          # a line still being written
            if r["call_key"] in keys:
                f.write(line if line.endswith("\n") else line + "\n")
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


def comparisons(P, fixes=True):
    """Every comparison the available steps allow. P: {step id: (run file, call keys)}."""
    G1, G2 = os.path.join(HERE, "gold.jsonl"), os.path.join(HERE, "v2", "gold.jsonl")
    stats = os.path.join(HERE, "sampling_stats.json")
    C = {}

    def have(*ids):
        return all(i in P for i in ids)

    def pair(name, a, b, gold, items, st="", label=("", "")):
        C[name] = score({label[0]: P[a], label[1]: P[b]}, gold, items, st, fixes)

    if have("a", "b"):
        pair("comment_medium_v1", "a", "b", G1, V1, stats, ("v6", "current"))
        pair("comment_medium_v2", "a", "b", G2, V2, "", ("v6", "current"))
    if have("c", "d"):
        pair("thread_medium_v1", "c", "d", G1, V1, "", ("v6", "current"))
    if have("f", "g"):
        pair("thread_medium_v2", "f", "g", G2, V2, "", ("v6", "current"))
    if have("a", "c"):
        pair("v6_comment_vs_thread_v1", "a", "c", G1, V1, "", ("comment", "thread"))
    if have("e-comment", "a"):
        pair("comment_low_vs_medium_v1", "e-comment", "a", G1, V1, "", ("low", "medium"))
        pair("comment_low_vs_medium_v2", "e-comment", "a", G2, V2, "", ("low", "medium"))
    if have("e-thread", "c"):
        pair("thread_low_vs_medium_v1", "e-thread", "c", G1, V1, "", ("low", "medium"))
    if have("f", "a"):
        pair("v6_thread_vs_comment_v2", "f", "a", G2, V2, "", ("thread", "comment"))
    if have("j", "c"):
        pair("thread_low_vs_medium_full_v1", "j", "c", G1, V1, "", ("low", "medium"))
    if have("j", "f"):
        pair("thread_low_vs_medium_full_v2", "j", "f", G2, V2, "", ("low", "medium"))
    if have("l", "k"):
        pair("comment_low_r2_vs_r1_v1", "l", "k", G1, V1, stats, ("r2_low", "r1_low"))
        pair("comment_low_r2_vs_r1_v2", "l", "k", G2, V2, "", ("r2_low", "r1_low"))
    if have("l", "a"):
        pair("comment_low_r2_vs_r1_medium_v1", "l", "a", G1, V1, stats, ("r2_low", "r1_medium"))
        pair("comment_low_r2_vs_r1_medium_v2", "l", "a", G2, V2, "", ("r2_low", "r1_medium"))
    if have("l", "b"):
        pair("comment_low_r2_vs_current_v1", "l", "b", G1, V1, stats, ("r2_low", "current"))
        pair("comment_low_r2_vs_current_v2", "l", "b", G2, V2, "", ("r2_low", "current"))
    if have("k", "a"):
        pair("comment_low_vs_medium_full_v1", "k", "a", G1, V1, stats, ("low", "medium"))
        pair("comment_low_vs_medium_full_v2", "k", "a", G2, V2, "", ("low", "medium"))
    for name, r in C.items():
        a, b = [k for k in r if isinstance(r[k], dict) and "run" in r[k]]
        r[f"delta_{a}_minus_{b}"] = delta(r[a], r[b])
    return C


def merged(base, rerun, name):
    """The base run file with every call the re-run finished replaced by the re-run's
    record. Written under bench_v6/merged/ (derived, not committed); the run files
    themselves are never modified. Returns (path, calls replaced)."""
    rer = {}
    if rerun and os.path.exists(rerun):
        for r in map(json.loads, open(rerun, encoding="utf-8")):
            if r.get("raw") is not None and r.get("rep", 0) == 0:
                rer[r["call_key"]] = r
    os.makedirs(MERGED, exist_ok=True)
    out = os.path.join(MERGED, name)
    with open(out, "w", encoding="utf-8") as f:
        for r in map(json.loads, open(base, encoding="utf-8")):
            if not (r["call_key"] in rer and r.get("rep", 0) == 0):
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        for r in rer.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out, len(rer)


def show(title, C):
    print(f"\n######## {title}")
    for name, r in C.items():
        print(f"== {name}")
        for k, v in r.items():
            if isinstance(v, dict) and "run" in v:
                o = v.get("overall") or {}
                print(f"  {k:8s} n={v['comments']:4d}  " + "  ".join(
                    f"{m.split('_')[0][:6]}:{o.get(m):.3f}" if isinstance(o.get(m), float)
                    else f"{m.split('_')[0][:6]}:{o.get(m)}" for m in METRICS) + f"  ${v['run']['cost_usd']:.3f}")


def compare():
    st = load_state()
    steps = {s["id"]: s for s in STEPS}
    ran = {k: v for k, v in st.get("steps", {}).items()
           if k in steps and os.path.exists(os.path.join(ROOT, v["run_file"]))}
    P = {sid: (os.path.join(ROOT, v["run_file"]), set(step_jobs(steps[sid])[1])) for sid, v in ran.items()}

    out = {"model": MODEL, "api": "anthropic (Message Batches)", "budget": BUDGET, "steps": st.get("steps"),
           "probe": st.get("probe"), "schema_for_v6": True,
           "note": ("identical comment sets per comparison (the comments every run in it covered); "
                    "chains dropped on both sides as production does; 'reweighted' is v1's "
                    "population estimate over single-comment strata"),
           "comparisons": comparisons(P)}
    if os.path.exists(LEDGER):
        with open(LEDGER, encoding="utf-8") as f:
            out["ledger"] = json.load(f)
    show("as run (scorer fixes on, the default)", out["comparisons"])

    # With the truncation re-runs: h's records stand in for truncated v6 thread chunks
    # (c and f share one run file), i's for truncated v6 comment calls (a).
    Q = dict(P)
    notes = {}
    if "h" in P and ("c" in P or "f" in P):
        base = P["c"][0] if "c" in P else P["f"][0]
        path, n = merged(base, P["h"][0], "v6_thread_medium_with_h.jsonl")
        notes["thread_chunks_replaced_by_h"] = n
        for sid in ("c", "f"):
            if sid in P:
                Q[sid] = (path, P[sid][1] | P["h"][1])
    if "i" in P and "a" in P:
        path, n = merged(P["a"][0], P["i"][0], "v6_comment_medium_with_i.jsonl")
        notes["comment_calls_replaced_by_i"] = n
        Q["a"] = (path, P["a"][1] | P["i"][1])
    if notes:
        out["with_truncation_rerun"] = comparisons(Q)
        out["with_truncation_rerun_notes"] = dict(notes, cost_note=(
            "run costs in this view count the re-run's records only; the truncated attempts "
            "they replace were also paid for (see the as-run view and the ledger)"))
        show("with truncation re-run", out["with_truncation_rerun"])

    # The legacy scorer (score.py fixes=False, --legacy-scorer) on the as-run files, to
    # reproduce the numbers scored before the scorer fixes became the default.
    out["legacy_scorer"] = comparisons(P, fixes=False)
    out["legacy_scorer_note"] = ("as-run files scored without the scorer fixes (overall-negative as a "
                                 "negative mention, street-word matching, context-named no-opinion "
                                 "mentions not counted as false positives)")
    show("legacy scorer", out["legacy_scorer"])

    path = os.path.join(OUT, "compare.json")
    os.makedirs(OUT, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"\nwritten {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("plan", "probe", "run", "compare"))
    a = ap.parse_args()
    {"plan": plan, "probe": probe, "run": run_all, "compare": compare}[a.cmd]()


if __name__ == "__main__":
    main()
