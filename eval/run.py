"""Run a model x prompt x mode over eval/items.jsonl. Never touches the database.

    OPENROUTER_API_KEY=... python eval/run.py --model deepseek/deepseek-v4-flash --mode comment
    python eval/run.py --model openai/gpt-5-mini --mode thread --prompt git:0ea62ff~1 --repeat 3
    python eval/run.py --model x/y --mode comment --prompt file:eval/prompts/rubric_v1.py
    python eval/run.py --model x/y --mode thread --dry-run --limit 3

--prompt selects the SYSTEM PROMPT:
    current          prompt.py / prompt_thread.py in this checkout (default)
    git:<rev>        the same files at a git revision (0ea62ff~1 = the prompts
                     production ran: 1d5bac550078 comment, ca5439be83b3 thread)
    file:<path>      a python file defining SYSTEM_PROMPT (a future rubric
                     prompt). It may also define build_user_message /
                     build_message; if it does, inputs are re-rendered from the
                     item's raw context instead of the stored rendering.

Model inputs are the renderings stored in items.jsonl, produced by the repo's
own builders when the items were built. Thread mode makes one call per
distinct (thread, chunk), shared by every item in that chunk.

Output is appended to eval/runs/<model>__<prompthash>__<mode>.jsonl, one line
per call and repetition. A call already present (same call_key and rep) is
skipped, so an interrupted run resumes and --repeat N only adds the missing
repetitions. Each line records the raw output, whether it parsed as JSON,
latency, token usage and OpenRouter's reported cost.
"""

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import types
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
API_URL = os.environ.get("EVAL_API_URL", "https://openrouter.ai/api/v1/chat/completions")
KEY_VAR = "OPENROUTER_API_KEY"


# ---------------------------------------------------------------- prompts
def _module_from_source(name, src):
    mod = types.ModuleType(name)
    exec(compile(src, name, "exec"), mod.__dict__)
    return mod


def load_prompt(spec, mode):
    """Returns a module-like object with SYSTEM_PROMPT (and maybe builders)."""
    fname = "prompt.py" if mode == "comment" else "prompt_thread.py"
    if spec == "current":
        with open(os.path.join(ROOT, fname), encoding="utf-8") as f:
            return _module_from_source(fname, f.read()), "current"
    if spec.startswith("git:"):
        rev = spec[4:]
        src = subprocess.run(["git", "-C", ROOT, "show", f"{rev}:{fname}"],
                             check=True, capture_output=True, text=True).stdout
        return _module_from_source(f"{rev}:{fname}", src), spec
    if spec.startswith("file:"):
        path = spec[5:]
        s = importlib.util.spec_from_file_location("eval_prompt", path)
        mod = importlib.util.module_from_spec(s)
        s.loader.exec_module(mod)
        return mod, spec
    raise SystemExit(f"bad --prompt {spec!r}")


def prompt_hash(system_prompt):
    # Same definition as prompt.PROMPT_HASH, so run files line up with the
    # hashes stamped on production rows.
    return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------- jobs
def load_items(path, ids=None):
    with open(path, encoding="utf-8") as f:
        items = [json.loads(l) for l in f]
    if ids:
        want = set(ids)
        items = [i for i in items if i["item_id"] in want]
    return items


def build_jobs(items, mode, pmod, custom=False):
    """One job per model call: {call_key, item_ids, user, id_map}.

    id_map maps whatever id the model returns to a comment_id: the short
    bracket id in thread mode, None (the one comment) in comment mode."""
    jobs = {}
    rerender = custom and mode == "comment" and hasattr(pmod, "build_user_message")
    for it in items:
        if mode == "comment":
            if it["kind"] == "comment":
                units = [(it["comment_id"], it["inputs"]["comment"]["user_message"], it["context"])]
            else:
                units = [(c["comment_id"], c["comment_input"], None) for c in it["comments"]]
            for cid, user, ctx in units:
                if rerender and ctx is not None:
                    parent = ctx["ancestors"][-1]["body"] if ctx["ancestors"] and \
                        not ctx["ancestors"][-1].get("missing") else None
                    user = pmod.build_user_message(ctx["body"], ctx["thread_title"],
                                                   ctx["thread_selftext"], parent)
                key = f"comment:{cid}"
                j = jobs.setdefault(key, {"call_key": key, "item_ids": [], "user": user,
                                          "id_map": {None: cid}})
                j["item_ids"].append(it["item_id"])
        else:
            if it["kind"] == "comment":
                t = it["inputs"]["thread"]
                chunks = [(it["thread_id"], t["chunk_index"], t["user_message"], t["short_ids"])]
            else:
                chunks = [(it["thread_id"], c["chunk_index"], c["user_message"], c["short_ids"])
                          for c in it["thread_chunks"]]
            for tid, ci, user, sids in chunks:
                key = f"thread:{tid}:{ci}"
                j = jobs.setdefault(key, {"call_key": key, "item_ids": [], "user": user,
                                          "id_map": {int(k): v for k, v in sids.items()}})
                if it["item_id"] not in j["item_ids"]:
                    j["item_ids"].append(it["item_id"])
    if custom and mode == "thread" and hasattr(pmod, "build_message"):
        print("note: prompt module defines build_message; thread inputs still use the "
              "stored rendering (re-run build_items.py with that renderer to change it)",
              file=sys.stderr)
    return list(jobs.values())


# ---------------------------------------------------------------- client
def call(model, system, user, args):
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": args.temperature,
        "usage": {"include": True},
    }
    if args.max_tokens:
        payload["max_tokens"] = args.max_tokens
    if args.provider:
        payload["provider"] = {"order": args.provider.split(","), "allow_fallbacks": False}
    if args.reasoning:
        payload["reasoning"] = {"effort": args.reasoning}
    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode(), headers={
        "Authorization": "Bearer " + os.environ[KEY_VAR],
        "Content-Type": "application/json",
    })
    last = None
    for attempt in range(6):
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=args.timeout) as r:
                body = json.load(r)
            return body, time.time() - t0, None
        except urllib.error.HTTPError as e:
            last = f"http {e.code}: {e.read()[:300]!r}"
            if e.code != 429 and e.code < 500:
                break
        except Exception as e:  # network; transient
            last = f"{type(e).__name__}: {e}"
        time.sleep(min(5 * 2 ** attempt, 60))
    return None, None, last


def unfence(raw):
    """Strip one surrounding ```json ... ``` fence. Some models add it despite the
    prompt; production's client would reject such output, so json_ok_strict
    records whether it was needed, and scoring uses the unfenced parse."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s


def parse(raw):
    """(ok, mentions). ok means valid JSON with a mentions list, once unfenced."""
    try:
        obj = json.loads(unfence(raw))
    except (TypeError, json.JSONDecodeError):
        return False, None
    ms = obj.get("mentions") if isinstance(obj, dict) else None
    return isinstance(ms, list), ms if isinstance(ms, list) else None


def run_job(job, rep, model, system, ph, mode, args):
    body, latency, err = call(model, system, job["user"], args)
    rec = {"call_key": job["call_key"], "rep": rep, "item_ids": job["item_ids"],
           "model": model, "prompt_hash": ph, "mode": mode,
           "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "latency_s": latency, "error": err}
    if body is None:
        return rec
    msg = (body.get("choices") or [{}])[0].get("message") or {}
    raw = msg.get("content")
    ok, mentions = parse(raw)
    by_comment = {}
    bad_ids = 0
    for m in mentions or []:
        if not isinstance(m, dict):
            continue
        key = None
        if mode == "thread":
            try:
                key = int(m.get("id"))
            except (TypeError, ValueError):
                key = -1
        cid = job["id_map"].get(key)
        if cid is None:
            bad_ids += 1
            continue
        by_comment.setdefault(cid, []).append(m)
    usage = body.get("usage") or {}
    rec.update({"raw": raw, "json_ok": ok,
                "json_ok_strict": ok and unfence(raw) == (raw or "").strip(),
                "mentions_by_comment": by_comment,
                "bad_ids": bad_ids, "provider": body.get("provider"),
                "usage": {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens",
                                                     "total_tokens", "cost")},
                "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get(
                    "reasoning_tokens")})
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="OpenRouter model slug")
    ap.add_argument("--mode", choices=["comment", "thread"], required=True)
    ap.add_argument("--prompt", default="current")
    ap.add_argument("--items", default=os.path.join(HERE, "items.jsonl"))
    ap.add_argument("--only", nargs="*", help="item ids to run")
    ap.add_argument("--labeled-only", action="store_true",
                    help="only items that have a gold label (eval/gold.jsonl)")
    ap.add_argument("--limit", type=int, help="at most N calls")
    ap.add_argument("--repeat", type=int, default=1, help="repetitions per call")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int)
    ap.add_argument("--reasoning", choices=["low", "medium", "high"])
    ap.add_argument("--provider", help="comma list; pins OpenRouter routing")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--tag", default="", help="suffix for the run file name")
    ap.add_argument("--dry-run", action="store_true", help="print the first calls, no API")
    args = ap.parse_args()

    pmod, label = load_prompt(args.prompt, args.mode)
    system = pmod.SYSTEM_PROMPT
    ph = prompt_hash(system)

    only = args.only
    if args.labeled_only:
        with open(os.path.join(HERE, "gold.jsonl"), encoding="utf-8") as f:
            only = sorted({json.loads(l)["item_id"] for l in f})
    jobs = build_jobs(load_items(args.items, only), args.mode, pmod,
                      custom=args.prompt.startswith("file:"))
    if args.limit:
        jobs = jobs[:args.limit]

    slug = args.model.replace("/", "_").replace(":", "_")
    name = f"{slug}__{ph}__{args.mode}{('__' + args.tag) if args.tag else ''}.jsonl"
    out = os.path.join(HERE, "runs", name)

    if args.dry_run:
        print(f"prompt {label} hash {ph}; {len(jobs)} calls -> {out}")
        for j in jobs[:3]:
            print("=" * 80, "\n", j["call_key"], j["item_ids"])
            print(j["user"][:1500])
            print(f"[~{(len(system) + len(j['user'])) // 4:,} input tokens]")
        return

    if not os.environ.get(KEY_VAR):
        raise SystemExit(f"{KEY_VAR} is not set")

    done = set()
    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            for l in f:
                r = json.loads(l)
                if r.get("raw") is not None:      # errors are retried
                    done.add((r["call_key"], r["rep"]))
    todo = [(j, rep) for rep in range(args.repeat) for j in jobs
            if (j["call_key"], rep) not in done]
    print(f"{args.model} prompt={label} ({ph}) mode={args.mode}: "
          f"{len(todo)} calls to make, {len(done)} cached -> {out}")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    stats = {"calls": 0, "json_ok": 0, "errors": 0, "cost": 0.0, "latency": []}
    with open(out, "a", encoding="utf-8") as f, \
            concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(run_job, j, rep, args.model, system, ph, args.mode, args)
                for j, rep in todo]
        for fut in concurrent.futures.as_completed(futs):
            rec = fut.result()
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            stats["calls"] += 1
            if rec.get("error"):
                stats["errors"] += 1
                continue
            stats["json_ok"] += bool(rec.get("json_ok"))
            stats["cost"] += float((rec.get("usage") or {}).get("cost") or 0)
            stats["latency"].append(rec["latency_s"])
    lat = sorted(stats["latency"]) or [0]
    print(f"calls {stats['calls']}  errors {stats['errors']}  json_ok {stats['json_ok']}  "
          f"cost ${stats['cost']:.4f}  latency p50 {lat[len(lat)//2]:.1f}s "
          f"p90 {lat[int(len(lat)*0.9)]:.1f}s")


if __name__ == "__main__":
    main()
