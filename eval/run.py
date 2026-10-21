"""Run a model x prompt x mode over eval/items.jsonl. Never touches the database.

    OPENROUTER_API_KEY=... python eval/run.py --model deepseek/deepseek-v4-flash --mode comment
    python eval/run.py --model openai/gpt-5-mini --mode thread --prompt git:0ea62ff~1 --repeat 3
    python eval/run.py --model x/y --mode comment --prompt file:eval/prompts/rubric_v1.py
    python eval/run.py --model x/y --mode thread --dry-run --limit 3
    python eval/run.py --api anthropic --model claude-haiku-5-5 --mode thread --schema --cache \\
        --threads eval/thread_v6/slices/fresh.threads.jsonl --reasoning low --max-tokens 32000 --dry-run

--threads takes a thread slice (eval/thread_v6/slices.py builds them) and runs
thread mode exactly as production would chunk and draw it: thread_chunks.py
and prompt_v6's thread prompt are imported, not copied. --chunk-comments,
--chunk-tokens and --chunk-max change the chunk sizes; --no-post-item keeps
the post as context only. docs/handoffs/extraction-v6-thread.md has the runs and their caps.

--prompt selects the SYSTEM PROMPT:
    current          prompt.py / prompt_thread.py in this checkout (default)
    git:<rev>        the same files at a git revision (0ea62ff~1 = the prompts
                     production ran: 1d5bac550078 comment, ca5439be83b3 thread)
    file:<path>      a python file defining SYSTEM_PROMPT (a future rubric
                     prompt). It may also define build_user_message (comment
                     mode) or render_chunk (thread mode); if it does, inputs
                     are re-rendered from raw rows instead of the stored
                     rendering. Thread re-rendering reads
                     <items>.thread_rows.jsonl, written read-only by
                     eval/build_thread_rows.py. A module that sets
                     COMMENT_ROWS renders each comment from
                     <items>.comment_rows.jsonl (eval/build_comment_rows.py).

Model inputs are the renderings stored in items.jsonl, produced by the repo's
own builders when the items were built. Thread mode makes one call per
distinct (thread, chunk), shared by every item in that chunk.

--budget-file PATH --budget USD puts a hard cap on spend across every run that
shares the ledger (eval/budget.py). Each call's worst case is reserved before
it is sent, and its OpenRouter-reported cost recorded after. A call the cap
refuses is not written, and the run exits with status 3, so raising the cap
and re-running resumes exactly where it stopped. --key-file reads the API key
from that file only (--key-var names the one variable read).

--api anthropic calls Anthropic's Messages API with the official SDK
(eval/anthropic_backend.py): adaptive thinking with --reasoning as
output_config.effort, --schema as output_config.format, --cache marking the
system prompt. Add --batch to send everything through the Message Batches API
at half price. Each sub-batch's worst case is held in the ledger, sized to fit
the cap, and batch ids are kept in <run file>.batches.json, so a re-run
re-attaches to batches in flight instead of resubmitting them.

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
sys.path.insert(0, HERE)
import budget  # noqa: E402
import anthropic_backend as AB  # noqa: E402
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


def build_jobs(items, mode, pmod, custom=False, thread_rows=None, comment_rows=None):
    """One job per model call: {call_key, item_ids, user, id_map}.

    id_map maps whatever id the model returns to a comment_id: the short
    bracket id in thread mode, None (the one comment) in comment mode.

    thread_rows ({call_key: sidecar record}) makes thread mode re-render each
    chunk with pmod.render_chunk. The renderer may renumber the comments, so
    its own id map replaces the stored one; a chunk whose sidecar is missing,
    or was built from a different chunking, stops the run rather than quietly
    mixing renderings.

    comment_rows ({call_key: sidecar record}) does the same for comment mode:
    every comment is rendered with pmod.build_user_message(record), and a
    comment with no row stops the run."""
    jobs = {}
    rerender = custom and mode == "comment" and hasattr(pmod, "build_user_message") \
        and comment_rows is None and not getattr(pmod, "COMMENT_ROWS", False)
    for it in items:
        if mode == "comment":
            if it["kind"] == "comment":
                units = [(it["comment_id"], it["inputs"]["comment"]["user_message"], it["context"])]
            else:
                units = [(c["comment_id"], c["comment_input"], None) for c in it["comments"]]
            for cid, user, ctx in units:
                if comment_rows is not None:
                    rec = comment_rows.get(f"comment:{cid}")
                    if rec is None:
                        raise SystemExit(f"comment:{cid}: no raw rows; run eval/build_comment_rows.py rows "
                                         "on this items file")
                    user = pmod.build_user_message(rec)
                elif rerender and ctx is not None:
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
                id_map = {int(k): v for k, v in sids.items()}
                if thread_rows is not None and key not in jobs:
                    rec = thread_rows.get(key)
                    if rec is None or rec["short_ids"] != sids:
                        raise SystemExit(f"{key}: no matching raw rows; run eval/build_thread_rows.py "
                                         "on this items file")
                    user, id_map = pmod.render_chunk(rec["title"], rec["selftext"], rec["rows"],
                                                     rec["outside"])
                j = jobs.setdefault(key, {"call_key": key, "item_ids": [], "user": user,
                                          "id_map": id_map, "rendered": thread_rows is not None})
                if it["item_id"] not in j["item_ids"]:
                    j["item_ids"].append(it["item_id"])
    if custom and mode == "thread" and hasattr(pmod, "build_message") and thread_rows is None:
        print("note: prompt module defines build_message; thread inputs still use the "
              "stored rendering (define render_chunk to re-render)", file=sys.stderr)
    return list(jobs.values())


def load_comment_rows(items_path, pmod, prompt_spec, mode):
    """{call_key: row} from <items>.comment_rows.jsonl when a file: prompt renders comment
    mode from raw rows (COMMENT_ROWS), else None."""
    if not (prompt_spec.startswith("file:") and mode == "comment" and getattr(pmod, "COMMENT_ROWS", False)):
        return None
    side = os.path.splitext(items_path)[0] + ".comment_rows.jsonl"
    if not os.path.exists(side):
        raise SystemExit(f"{side} is missing: this prompt re-renders comments. Build it read-only "
                         f"with eval/build_comment_rows.py rows {items_path} --env-file ...")
    with open(side, encoding="utf-8") as f:
        return {r["call_key"]: r for r in map(json.loads, f)}


# ---------------------------------------------------------------- client
def api_key(args):
    """The key from --key-file only, when given, so no other key in the
    environment can be used by accident. Never printed."""
    if args.key_file:
        with open(args.key_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip().removeprefix("export ")
                if line.startswith(args.key_var + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        raise SystemExit(f"{args.key_file} has no {args.key_var}")
    return os.environ.get(args.key_var)


def call(model, system, user, args):
    """(body, latency, error, lost). lost counts attempts that may have been
    billed with no response seen (timeouts, dropped connections)."""
    sys_content = system
    if args.cache:
        # Anthropic caches only marked prefixes; a prompt below the model's
        # minimum is simply not cached, at no extra charge.
        sys_content = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": sys_content},
                     {"role": "user", "content": user}],
        "response_format": args.response_format or {"type": "json_object"},
        "usage": {"include": True},
    }
    # Haiku 5.5 rejects non-default sampling parameters, so they can be left out.
    if not args.omit_temperature:
        payload["temperature"] = args.temperature
    if args.max_tokens:
        payload["max_tokens"] = args.max_tokens
    if args.provider:
        payload["provider"] = {"order": args.provider.split(","), "allow_fallbacks": False}
    if args.reasoning:
        payload["reasoning"] = {"effort": args.reasoning}
    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode(), headers={
        "Authorization": "Bearer " + args.key,
        "Content-Type": "application/json",
    })
    last, lost = None, 0
    for attempt in range(6):
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=args.timeout) as r:
                body = json.load(r)
            return body, time.time() - t0, None, lost
        except urllib.error.HTTPError as e:
            last = f"http {e.code}: {e.read()[:300]!r}"
            if e.code != 429 and e.code < 500:
                break
        except Exception as e:  # network; transient
            last = f"{type(e).__name__}: {e}"
            lost += 1
            # Under a budget, a request that may have been billed is not sent
            # again: the reservation covers one attempt, not six.
            if args.ledger is not None:
                break
        time.sleep(min(5 * 2 ** attempt, 60))
    return None, None, last, lost


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
    """One call, or None when the budget refused it (nothing is written, so a
    later run with a higher cap picks it up)."""
    reserve = 0.0
    anth = args.api == "anthropic"
    if args.ledger is not None:
        reserve = (AB.worst_case(system, job["user"], args.max_tokens, batch=False) if anth
                   else budget.worst_case(system, job["user"], args.max_tokens))
        if not args.ledger.reserve(reserve):
            return None
    if anth:
        body, latency, err = AB.call(args.client, anthropic_params(system, job, args))
        lost = 0
    else:
        body, latency, err, lost = call(model, system, job["user"], args)
    rec = record_head(job, rep, model, ph, mode, args, latency, err)
    if args.ledger is not None:
        usage = (body or {}).get("usage") or {}
        if body is not None and usage.get("cost") is not None:
            cost, estimated = float(usage["cost"]), False
        elif body is not None:
            cost, estimated = budget.estimate_cost(usage), "from_tokens"
        else:
            cost, estimated = reserve * min(lost, 1), ("lost_attempt" if lost else False)
        args.ledger.settle(reserve, cost, estimated)
        rec.update({"ledger_cost": cost, "cost_estimated": estimated})
    return fill_record(rec, body, job, mode)


def anthropic_params(system, job, args):
    return AB.params(system, job["user"], args.max_tokens, args.reasoning,
                     schema=args.schema_obj, cache=args.cache, model=args.model)


def record_head(job, rep, model, ph, mode, args, latency, err):
    return {"call_key": job["call_key"], "rep": rep, "item_ids": job["item_ids"],
            "model": model, "prompt_hash": ph, "mode": mode,
            # A re-rendered chunk is renumbered, so the stored short ids no longer
            # map the model's ids; keep the map the call actually used.
            **({"id_map": {str(k): v for k, v in job["id_map"].items()}} if job.get("rendered") else {}),
            # A thread-slice chunk (--threads): what it numbered and quoted, so
            # score.py knows which comments it covers and packets can redraw it.
            **({"chunk": job["chunk"], "covers": job["covers"]} if job.get("chunk") else {}),
            "reasoning_effort": args.reasoning, "schema": bool(args.response_format or args.schema_obj),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "latency_s": latency, "error": err}


def fill_record(rec, body, job, mode):
    """Parse a response body into the record (shared by every API path)."""
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
        if mode == "thread" and job.get("strict_ids"):
            # Production's rule (extract_v6._read_chunk): only an integer that
            # numbers an item counts; "1", 1.0 and true are dropped, not read.
            key = m.get("id") if type(m.get("id")) is int else -1
        elif mode == "thread":
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
                "usage_details": {k: usage.get(k) for k in ("prompt_tokens_details",
                                                             "completion_tokens_details")},
                "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get(
                    "reasoning_tokens")})
    if body.get("stop_reason"):
        rec["stop_reason"] = body["stop_reason"]
    return rec


# ---------------------------------------------------------------- Anthropic batches
def run_batches(todo, args, system, ph, out_path, f):
    """Run the jobs through the Message Batches API under the ledger.

    State lives in <run file>.batches.json: every submitted batch, with each
    custom_id mapped to [call_key, rep, attempt], its ledger hold, and
    whether it was collected. A re-run re-attaches to batches still in
    flight instead of resubmitting them.

    Before a submission the batch's worst case is held in the ledger. The
    hold is persisted, so an interruption keeps it counted. Sub-batches are
    sized to fit what remains under the cap. When a batch ends its records
    are written and the hold becomes the actual cost. Errored requests
    (except invalid ones, which would fail again) and expired requests get
    one retry, in a later batch; whatever happens on the retry is written.
    Returns (written, refused, errors).
    """
    state_path = out_path + ".batches.json"
    state = {"batches": {}}
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as sf:
            state = json.load(sf)

    def save():
        tmp = state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as sf:
            json.dump(state, sf, indent=1)
        os.replace(tmp, state_path)

    jobs = {(j["call_key"], rep): j for j, rep in todo}
    stats = {"written": 0, "refused": 0, "errors": 0}
    written = set()

    def collect(bid, info):
        """Wait for a batch, write its records, settle its hold. Returns the
        keys that get a retry."""
        b = AB.wait(args.client, bid, args.poll_seconds)
        res = AB.results(args.client, bid)
        secs = AB.batch_seconds(b)
        total, retry = 0.0, []
        for cid, (key, rep, attempt) in info["requests"].items():
            k = (key, rep)
            job = jobs.get(k)
            if job is None:
                raise SystemExit(f"batch {bid} holds {key}, which this run did not select; "
                                 "re-run with the same items and flags to collect it")
            kind, *rest = res.get(cid, ("missing", None))
            body = rest[0] if kind == "succeeded" else None
            if body is None and attempt == 1 and (kind == "expired" or (kind == "errored" and rest[1])):
                retry.append(k)
                continue
            err = None if body is not None else (rest[0] if kind == "errored" else kind)
            rec = record_head(job, rep, args.model, ph, args.mode, args, None, err)
            c = float(body["usage"]["cost"]) if body is not None else 0.0
            total += c
            rec.update({"batch_id": bid, "batch_seconds": secs, "attempt": attempt,
                        "ledger_cost": c, "cost_estimated": False})
            f.write(json.dumps(fill_record(rec, body, job, args.mode), ensure_ascii=False) + "\n")
            f.flush()
            written.add(k)
            stats["written"] += 1
            stats["errors"] += body is None
        args.ledger.release(info["hold"], total, len(info["requests"]) - len(retry))
        info.update({"collected": True, "retry": [list(k) for k in retry], "cost": round(total, 8)})
        save()
        print(f"  batch {bid} ended after {secs or 0:.0f}s: ${total:.4f}, "
              f"{len(info['requests']) - len(retry)} written, {len(retry)} to retry")
        return retry

    # 1. Re-attach to batches submitted earlier and not yet collected.
    for bid, info in list(state["batches"].items()):
        if bid.startswith("pending-"):
            raise SystemExit(f"{state_path}: a submission was interrupted ({bid}). Check the Console "
                             "for a batch with these requests, then remove the entry, before re-running")
        if not info.get("collected"):
            print(f"re-attaching to batch {bid}")
            collect(bid, info)

    # 2. Retries owed: requests a collected batch handed back for a retry that
    #    no later batch has taken yet (this also survives an interruption).
    retried = {(k, r) for info in state["batches"].values()
               for k, r, a in info["requests"].values() if a == 2}
    owed = [tuple(k) for info in state["batches"].values() for k in info.get("retry", [])]
    queue = [(k, 2) for k in owed if k not in retried and k in jobs and k not in written]
    queued = {k for k, _ in queue}
    # Retries go first: they finish work already paid for.
    queue = queue + [((j["call_key"], rep), 1) for j, rep in todo
                     if (j["call_key"], rep) not in written and (j["call_key"], rep) not in queued]

    # 3. Submit sub-batches that fit under the cap, collecting each before the next.
    while queue:
        remaining = args.ledger.remaining()
        batch, held = [], 0.0
        for k, attempt in queue:
            w = AB.worst_case(system, jobs[k]["user"], args.max_tokens, batch=True)
            if held + w > remaining or len(batch) >= args.batch_size:
                break
            batch.append((k, attempt))
            held += w
        if not batch:
            stats["refused"] += len(queue)
            break
        hold_id = f"pending-{int(time.time() * 1000)}-{os.getpid()}"
        if not args.ledger.hold(hold_id, held):
            stats["refused"] += len(queue)
            break
        queue = queue[len(batch):]
        reqs = {AB.custom_id(n): [k[0], k[1], a] for n, (k, a) in enumerate(batch)}
        state["batches"][hold_id] = {"requests": reqs, "hold": hold_id}
        save()
        bid = AB.submit(args.client, [(cid, anthropic_params(system, jobs[(r[0], r[1])], args))
                                      for cid, r in reqs.items()])
        args.ledger.rename_hold(hold_id, bid)
        info = state["batches"].pop(hold_id)
        info.update({"hold": bid, "submitted": time.strftime("%Y-%m-%dT%H:%M:%S")})
        state["batches"][bid] = info
        save()
        print(f"submitted batch {bid}: {len(batch)} requests, worst case ${held:.4f} held")
        if args.no_wait:
            continue
        queue = [(k, 2) for k in collect(bid, info)] + queue
    return stats["written"], stats["refused"], stats["errors"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="OpenRouter slug, or an Anthropic model id with --api anthropic")
    ap.add_argument("--api", choices=["openrouter", "anthropic"], default="openrouter")
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
    ap.add_argument("--runs-dir", default=os.path.join(HERE, "runs"), help="where run files go")
    ap.add_argument("--dry-run", action="store_true", help="print the first calls, no API")
    ap.add_argument("--schema", action="store_true",
                    help="send the prompt module's RESPONSE_FORMAT (strict JSON schema) "
                         "instead of json_object; the provider must support it")
    ap.add_argument("--omit-temperature", action="store_true",
                    help="send no temperature (models that reject sampling parameters)")
    ap.add_argument("--cache", action="store_true",
                    help="mark the system prompt for provider prompt caching")
    ap.add_argument("--call-keys", help="file of call keys (one per line); run only those")
    ap.add_argument("--key-file", help="read the API key from this file only (never printed)")
    ap.add_argument("--key-var", help="variable to read from --key-file (default OPENROUTER_API_KEY, "
                                      "or ANTHROPIC_API_KEY with --api anthropic); no other is read")
    ap.add_argument("--batch", action="store_true", help="--api anthropic: use the Message Batches API")
    ap.add_argument("--batch-size", type=int, default=2000, help="most requests per sub-batch")
    ap.add_argument("--poll-seconds", type=float, default=60)
    ap.add_argument("--no-wait", action="store_true", help="submit the batches that fit, then exit")
    ap.add_argument("--anthropic-base-url", help="override the API endpoint (tests only)")
    ap.add_argument("--budget-file", help="shared spend ledger (JSON); needs --budget and --max-tokens")
    ap.add_argument("--budget", type=float, help="hard cap in USD across every run on the ledger")
    ap.add_argument("--threads", help="a thread slice (eval/thread_v6/slices/*.threads.jsonl): thread mode "
                                      "with production's chunker, renderer and thread prompt "
                                      "(thread_chunks.py, prompt_v6); --items and --prompt are not used")
    ap.add_argument("--chunk-comments", type=int, help="with --threads: soft budget, items per chunk")
    ap.add_argument("--chunk-tokens", type=int, help="with --threads: soft budget, tokens of comment text")
    ap.add_argument("--chunk-max", type=int, help="with --threads: hard max comments per chunk")
    ap.add_argument("--no-post-item", action="store_true", help="with --threads: the post is context only")
    args = ap.parse_args()
    if (args.budget_file is None) != (args.budget is None):
        raise SystemExit("--budget-file and --budget go together")
    if args.budget_file and not args.max_tokens:
        raise SystemExit("--budget needs --max-tokens: a call's worst case is reserved before it is sent")
    if args.api == "anthropic" and not args.max_tokens:
        raise SystemExit("--api anthropic needs --max-tokens (thinking counts toward it)")
    if args.batch and (args.api != "anthropic" or not args.budget_file):
        raise SystemExit("--batch needs --api anthropic and a --budget-file")
    args.key_var = args.key_var or ("ANTHROPIC_API_KEY" if args.api == "anthropic" else KEY_VAR)
    args.schema_obj = None

    TC = None
    if args.threads:
        if args.mode != "thread":
            raise SystemExit("--threads is thread mode")
        sys.path.insert(0, os.path.join(HERE, "thread_v6"))
        import chunked as TC  # noqa: E402  production's chunker and thread prompt, imported
        pmod = types.SimpleNamespace(SYSTEM_PROMPT=TC.SYSTEM_PROMPT, SCHEMA=TC.SCHEMA,
                                     RESPONSE_FORMAT=TC.prompt_v6.thread.RESPONSE_FORMAT)
        label = "production thread prompt (prompt_v6)"
    else:
        pmod, label = load_prompt(args.prompt, args.mode)
    system = pmod.SYSTEM_PROMPT
    ph = prompt_hash(system)
    args.response_format = None
    if args.schema:
        if not hasattr(pmod, "RESPONSE_FORMAT"):
            raise SystemExit("--schema: this prompt module defines no RESPONSE_FORMAT")
        if args.api == "anthropic":
            args.schema_obj = pmod.SCHEMA          # sent as output_config.format
        else:
            args.response_format = pmod.RESPONSE_FORMAT
        # The hash only covers the system prompt, so a schema run needs its own
        # file or it would resume from (and mix with) a json_object run.
        args.tag = (args.tag + "_" if args.tag else "") + "schema"

    only = args.only
    if args.labeled_only:
        with open(os.path.join(HERE, "gold.jsonl"), encoding="utf-8") as f:
            only = sorted({json.loads(l)["item_id"] for l in f})
    thread_rows = None
    if TC is not None:
        sizes = {k: v for k, v in (("soft_comments", args.chunk_comments), ("soft_tokens", args.chunk_tokens),
                                   ("max_comments", args.chunk_max)) if v is not None}
        jobs = TC.jobs(args.threads, post_item=not args.no_post_item, **sizes)
    elif args.prompt.startswith("file:") and args.mode == "thread" and hasattr(pmod, "render_chunk"):
        side = os.path.splitext(args.items)[0] + ".thread_rows.jsonl"
        if not os.path.exists(side):
            raise SystemExit(f"{side} is missing: this prompt re-renders thread chunks. Build it "
                             f"read-only with eval/build_thread_rows.py {args.items} --env-file ...")
        with open(side, encoding="utf-8") as f:
            thread_rows = {r["call_key"]: r for r in map(json.loads, f)}
    if TC is None:
        comment_rows = load_comment_rows(args.items, pmod, args.prompt, args.mode)
        jobs = build_jobs(load_items(args.items, only), args.mode, pmod, thread_rows=thread_rows,
                          custom=args.prompt.startswith("file:"), comment_rows=comment_rows)
    if args.call_keys:
        with open(args.call_keys, encoding="utf-8") as f:
            keep = {l.strip() for l in f if l.strip()}
        jobs = [j for j in jobs if j["call_key"] in keep]
    if args.limit:
        jobs = jobs[:args.limit]

    slug = args.model.replace("/", "_").replace(":", "_")
    name = f"{slug}__{ph}__{args.mode}{('__' + args.tag) if args.tag else ''}.jsonl"
    out = os.path.join(args.runs_dir, name)

    if args.dry_run:
        print(f"prompt {label} hash {ph}; {len(jobs)} calls -> {out}")
        for j in jobs[:3]:
            print("=" * 80, "\n", j["call_key"], j["item_ids"])
            print(j["user"][:1500])
            print(f"[~{(len(system) + len(j['user'])) // 4:,} input tokens]")
        return

    args.key = api_key(args)
    if not args.key:
        raise SystemExit(f"{args.key_var} is not set")
    if args.api == "anthropic":
        args.client = AB.client(args.key, args.anthropic_base_url)
    args.ledger = budget.Ledger(args.budget_file, args.budget, name) if args.budget_file else None
    if args.ledger is not None:
        spent = args.ledger.spent()
        print(f"budget ${args.budget:.2f}, ${spent:.4f} already spent on {args.budget_file}")
        if spent >= args.budget:
            print("budget reached: exhausted before this run; nothing sent")
            sys.exit(3)

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

    if args.batch:
        with open(out, "a", encoding="utf-8") as f:
            n, refused, errors = run_batches(todo, args, system, ph, out, f)
        print(f"batch records written {n}, errors {errors}, ledger ${args.ledger.spent():.4f} spent, "
              f"${args.ledger.inflight():.4f} held for batches in flight")
        if refused:
            print(f"budget reached: {refused} request(s) not submitted. Finished results are saved; "
                  "rerun with a higher cap to resume.")
            sys.exit(3)
        return

    stats = {"calls": 0, "json_ok": 0, "errors": 0, "cost": 0.0, "latency": [], "refused": 0}
    with open(out, "a", encoding="utf-8") as f, \
            concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(run_job, j, rep, args.model, system, ph, args.mode, args)
                for j, rep in todo]
        for fut in concurrent.futures.as_completed(futs):
            rec = fut.result()
            if rec is None:                       # refused by the budget; not written
                stats["refused"] += 1
                continue
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
    if stats["refused"]:
        print(f"budget reached: {stats['refused']} call(s) not sent, ledger at "
              f"${args.ledger.spent():.4f} of ${args.budget:.2f}. Finished calls are saved; "
              "rerun with a higher cap to resume.")
        sys.exit(3)


if __name__ == "__main__":
    main()
