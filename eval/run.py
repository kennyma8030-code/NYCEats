"""Run a model x prompt x mode over eval/v1/items.jsonl. Never touches the database.

    python eval/run.py --model deepseek/deepseek-v4-flash --mode comment
    python eval/run.py --model haiku-5.5 --mode thread --prompt file:eval/prompts/v5_thread.py
    python eval/run.py --model openai/gpt-5-mini --mode thread --prompt git:0ea62ff~1 --repeat 3
    python eval/run.py --model x/y --mode thread --dry-run --limit 3

--model takes an alias (providers.ALIASES), an Anthropic id or an OpenRouter
slug. Claude models go to Anthropic's own API when ANTHROPIC_API_KEY is set,
otherwise through OpenRouter; --api forces one. Keys are read from the
environment or from .env (see providers.py). eval/bench.py drives this for a
whole grid and scores it; use run.py for one run.

--prompt selects the SYSTEM PROMPT:
    current          prompt.py / prompt_thread.py in this checkout (default)
    git:<rev>        the same files at a git revision (0ea62ff~1 = the prompts
                     production ran: 1d5bac550078 comment, ca5439be83b3 thread)
    file:<path>      a python file defining SYSTEM_PROMPT (a future rubric
                     prompt). It may also define build_user_message /
                     build_message; if it does, inputs are re-rendered from the
                     item's raw context instead of the stored rendering.

Model inputs are the renderings stored in the items file, produced by the repo's
own builders when the items were built. Thread mode makes one call per
distinct (thread, chunk), shared by every item in that chunk.

Output is appended to eval/runs/<model>__<prompthash>__<mode>.jsonl, one line
per call and repetition. A call already present (same call_key and rep) is
skipped, so an interrupted run resumes and --repeat N only adds the missing
repetitions. Each line records the raw output, whether it parsed as JSON,
latency, token usage (with cache reads and writes) and cost: OpenRouter's
reported cost, or for Anthropic's API one computed from its price table.
Effort and thinking settings are added to the file name.
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

import _paths  # noqa: E402,F401  (puts eval/ and eval/lib on sys.path)

HERE = _paths.EVAL
ROOT = _paths.ROOT
import providers  # noqa: E402


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
def call_opts(args):
    """The request options providers.complete() reads, from run.py's flags."""
    return {"temperature": args.temperature, "max_tokens": args.max_tokens,
            "provider": args.provider, "effort": args.effort or args.reasoning,
            "thinking": args.thinking, "timeout": args.timeout}


def config_tag(opts, tag=""):
    """Effort and thinking change the output, so they go in the run file name;
    otherwise a resumed run would mix configurations in one file."""
    parts = [tag] if tag else []
    if opts.get("effort"):
        parts.append(f"effort-{opts['effort']}")
    if opts.get("thinking"):
        parts.append(f"thinking-{opts['thinking']}")
    return "__".join(parts)


def run_path(model_id, ph, mode, tag=""):
    slug = model_id.replace("/", "_").replace(":", "_")
    return os.path.join(HERE, "runs", f"{slug}__{ph}__{mode}{('__' + tag) if tag else ''}.jsonl")


def cached_calls(out):
    """(call_key, rep) pairs already settled in a run file: answered, or
    refused for good (a moderation 403 on that input). Other errors are not
    cached, so they are retried."""
    done = set()
    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            for l in f:
                r = json.loads(l)
                if r.get("raw") is not None or r.get("permanent"):
                    done.add((r["call_key"], r["rep"]))
    return done


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


def run_job(job, rep, model, system, ph, mode, opts, api="openrouter"):
    rec = {"call_key": job["call_key"], "rep": rep, "item_ids": job["item_ids"],
           "model": model, "prompt_hash": ph, "mode": mode,
           "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        out, latency, err = providers.complete(api, model, system, job["user"], opts)
    except providers.PermanentError as e:
        rec.update({"latency_s": None, "error": str(e), "permanent": True})
        return rec
    rec.update({"latency_s": latency, "error": err})
    if out is None:
        return rec
    raw = out["raw"]
    if raw is None:
        rec["error"] = out.get("error") or f"empty response (stop {out.get('stop_reason')})"
        return rec
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
    rec.update({"raw": raw, "json_ok": ok,
                "json_ok_strict": ok and unfence(raw) == (raw or "").strip(),
                "mentions_by_comment": by_comment,
                "bad_ids": bad_ids, "provider": out.get("provider"), "api": out.get("api"),
                "stop_reason": out.get("stop_reason"),
                "usage": out["usage"], "reasoning_tokens": out.get("reasoning_tokens"),
                "opts": {k: v for k, v in opts.items() if v is not None and k != "timeout"}})
    return rec


def caches_prompt(api, model):
    return api == "anthropic" or model.startswith("anthropic/")


def execute(todo, model, system, ph, mode, opts, api, out, workers, progress=True):
    """Run (job, rep) pairs in parallel, appending each record as it lands so
    an interrupted run resumes. Returns summary stats.

    Where the system prompt is cached, the first call runs alone: calls
    started together all miss the cache and each pays the write, so one call
    writes it and the rest read it.

    A refused key (providers.FatalError) stops everything: pending calls are
    cancelled, calls already in flight are still recorded if they succeed,
    and nothing is written for the refused call, so a resume after topping
    up the key starts exactly where this one stopped."""
    providers.check_opts(api, opts)
    if api == "openrouter":
        providers.catalog()         # load once here, not raced by every worker
    os.makedirs(os.path.dirname(out), exist_ok=True)
    stats = {"calls": 0, "json_ok": 0, "errors": 0, "cost": 0.0, "latency": []}
    fatal = None

    def record(f, rec):
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        stats["calls"] += 1
        if rec.get("error"):
            stats["errors"] += 1
        else:
            stats["json_ok"] += bool(rec.get("json_ok"))
            stats["cost"] += float((rec.get("usage") or {}).get("cost") or 0)
            stats["latency"].append(rec["latency_s"])
        if progress and stats["calls"] % 50 == 0:
            print(f"  {stats['calls']}/{len(todo)} calls, {stats['errors']} errors, "
                  f"${stats['cost']:.4f}", file=sys.stderr)

    with open(out, "a", encoding="utf-8") as f:
        rest = list(todo)
        if rest and caches_prompt(api, model):
            j, rep = rest.pop(0)
            try:
                record(f, run_job(j, rep, model, system, ph, mode, opts, api))
            except providers.FatalError as e:
                raise SystemExit(f"stopped: {e}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(run_job, j, rep, model, system, ph, mode, opts, api) for j, rep in rest]
            for fut in concurrent.futures.as_completed(futs):
                if fut.cancelled():
                    continue
                try:
                    rec = fut.result()
                except providers.FatalError as e:
                    if fatal is None:
                        fatal = e
                        for other in futs:
                            other.cancel()
                    continue
                record(f, rec)
    if fatal is not None:
        raise SystemExit(f"stopped: {fatal}\n{stats['calls']} calls were recorded before the stop; "
                         f"re-running resumes from there.")
    return stats


def print_stats(stats):
    lat = sorted(stats["latency"]) or [0]
    print(f"calls {stats['calls']}  errors {stats['errors']}  json_ok {stats['json_ok']}  "
          f"cost ${stats['cost']:.4f}  latency p50 {lat[len(lat)//2]:.1f}s "
          f"p90 {lat[int(len(lat)*0.9)]:.1f}s")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True,
                    help="an alias (haiku-5.5), an Anthropic id (claude-haiku-5-5) or an OpenRouter slug")
    ap.add_argument("--api", choices=["auto", "openrouter", "anthropic"], default="auto",
                    help="auto: Anthropic's API for Claude models when ANTHROPIC_API_KEY is set")
    ap.add_argument("--mode", choices=["comment", "thread"], required=True)
    ap.add_argument("--prompt", default="current")
    ap.add_argument("--items", default=os.path.join(HERE, "v1", "items.jsonl"))
    ap.add_argument("--only", nargs="*", help="item ids to run")
    ap.add_argument("--labeled-only", action="store_true",
                    help="only items that have a gold label (--gold, default: gold.jsonl beside --items)")
    ap.add_argument("--gold", help="gold file for --labeled-only (default: gold.jsonl in --items' folder)")
    ap.add_argument("--limit", type=int, help="at most N calls")
    ap.add_argument("--repeat", type=int, default=1, help="repetitions per call")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--temperature", type=float, default=0.0,
                    help="sent only to models that accept it (current Claude models do not)")
    ap.add_argument("--max-tokens", type=int)
    ap.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                    help="reasoning effort; omitted means the model's default")
    ap.add_argument("--reasoning", choices=["low", "medium", "high"], help="old name for --effort")
    ap.add_argument("--thinking", choices=["adaptive", "disabled", "between_tools"],
                    help="Anthropic API only: the thinking type, sent as given")
    ap.add_argument("--provider", help="comma list; pins OpenRouter routing")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--tag", default="", help="suffix for the run file name")
    ap.add_argument("--dry-run", action="store_true", help="print the first calls, no API")
    args = ap.parse_args()

    providers.load_env()
    api, model = providers.resolve(args.model, args.api)
    opts = call_opts(args)
    providers.check_opts(api, opts)
    pmod, label = load_prompt(args.prompt, args.mode)
    system = pmod.SYSTEM_PROMPT
    ph = prompt_hash(system)

    only = args.only
    if args.labeled_only:
        gold = args.gold or os.path.join(os.path.dirname(os.path.abspath(args.items)), "gold.jsonl")
        if not os.path.exists(gold):
            sys.exit(f"--labeled-only: no gold file at {gold}; pass --gold")
        with open(gold, encoding="utf-8") as f:
            only = sorted({json.loads(l)["item_id"] for l in f})
    jobs = build_jobs(load_items(args.items, only), args.mode, pmod,
                      custom=args.prompt.startswith("file:"))
    if only is not None and not jobs:
        sys.exit(f"no items selected from {args.items} by --only/--labeled-only"
                 + (f" (gold: {gold})" if args.labeled_only else ""))
    if args.limit:
        jobs = jobs[:args.limit]

    out = run_path(model, ph, args.mode, config_tag(opts, args.tag))

    if args.dry_run:
        print(f"{api}:{model} prompt {label} hash {ph}; {len(jobs)} calls -> {out}")
        for j in jobs[:3]:
            print("=" * 80, "\n", j["call_key"], j["item_ids"])
            print(j["user"][:1500])
            print(f"[~{(len(system) + len(j['user'])) // 4:,} input tokens]")
        return

    providers.require_key(api)
    done = cached_calls(out)
    todo = [(j, rep) for rep in range(args.repeat) for j in jobs
            if (j["call_key"], rep) not in done]
    print(f"{api}:{model} prompt={label} ({ph}) mode={args.mode}: "
          f"{len(todo)} calls to make, {len(done)} cached -> {out}")
    print_stats(execute(todo, model, system, ph, args.mode, opts, api, out, args.workers))


if __name__ == "__main__":
    main()
