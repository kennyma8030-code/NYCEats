"""Offline checks for run.py's spend cap. No real API: a fake OpenRouter on 127.0.0.1.

    python eval/budget_selftest.py

The fake server answers like OpenRouter. Most calls report usage.cost, every
fifth reports none (so the ledger must estimate it from tokens), and one
call in each run stalls past the client timeout (a lost attempt, charged at
its reservation). run.py is driven as a subprocess, exactly as
eval/bench_v6.py drives it, with a key file and a ledger in a temp
directory. The test checks:
  * the ledger never exceeds the cap, even with 8 workers in flight;
  * a capped run exits 3, writes only finished calls, and a re-run with a
    higher cap resumes without repeating any of them;
  * estimated and lost costs are flagged on the record and counted in the
    ledger;
  * the key is read from --key-file, sent as the bearer token, never printed;
  * no temperature is sent with --omit-temperature, and the system prompt
    carries cache_control with --cache.
"""

import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import budget  # noqa: E402

KEY = "sk-test-not-a-real-key"
COST = 0.0009
SEEN = {"auth": set(), "temperature": 0, "cache_control": 0, "requests": 0}
LOCK = threading.Lock()


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with LOCK:
            SEEN["requests"] += 1
            n = SEEN["requests"]
            SEEN["auth"].add(self.headers.get("Authorization"))
            SEEN["temperature"] += "temperature" in body
            sysc = body["messages"][0]["content"]
            SEEN["cache_control"] += isinstance(sysc, list) and "cache_control" in sysc[0]
        if n == 7:
            time.sleep(5)                  # past the client's 2 s timeout: a lost attempt
        usage = {"prompt_tokens": 3000, "completion_tokens": 600,
                 "completion_tokens_details": {"reasoning_tokens": 400}}
        if n % 5:
            usage["cost"] = COST
        out = json.dumps({"choices": [{"message": {"content": '{"mentions": []}'}}], "usage": usage})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        try:
            self.wfile.write(out.encode())
        except BrokenPipeError:
            pass


def run(tmp, port, budget_usd, limit):
    env = dict(os.environ, EVAL_API_URL=f"http://127.0.0.1:{port}/v1/chat/completions")
    env.pop("OPENROUTER_API_KEY", None)
    cmd = [sys.executable, os.path.join(HERE, "run.py"), "--model", "anthropic/claude-haiku-5.5",
           "--mode", "comment", "--prompt", "file:" + os.path.join(HERE, "prompts", "v6_comment.py"),
           "--labeled-only", "--limit", str(limit), "--workers", "8", "--max-tokens", "2000",
           "--timeout", "2", "--omit-temperature", "--cache", "--reasoning", "medium",
           "--key-file", os.path.join(tmp, ".env.eval"), "--runs-dir", tmp,
           "--budget-file", os.path.join(tmp, "ledger.json"), "--budget", str(budget_usd)]
    p = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    errs = []
    # The default listen backlog (5) resets connections under 8 workers.
    http.server.ThreadingHTTPServer.request_queue_size = 64
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, ".env.eval"), "w") as f:
            f.write(f"OPENROUTER_API_KEY={KEY}\n")
        # worst case of one call: ~8.4k chars of input /3 * $0.10/M + 2000 * $0.50/M ~ $0.0013
        cap = 0.02
        code, out = run(tmp, port, cap, 60)
        ledger = json.load(open(os.path.join(tmp, "ledger.json")))
        runfile = next(os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(".jsonl"))
        recs = [json.loads(l) for l in open(runfile)]
        if code != 3 or "budget reached" not in out:
            errs.append(f"capped run should exit 3 with a budget message (got {code})")
        if ledger["spent"] > cap + 1e-9:
            errs.append(f"ledger {ledger['spent']} exceeds cap {cap}")
        if len(recs) != ledger["calls"] or len(recs) >= 60:
            errs.append(f"{len(recs)} records vs {ledger['calls']} ledger calls")
        est = [r for r in recs if r.get("cost_estimated") == "from_tokens"]
        lost = [r for r in recs if r.get("cost_estimated") == "lost_attempt"]
        if not est or abs(est[0]["ledger_cost"] - budget.estimate_cost(
                {"prompt_tokens": 3000, "completion_tokens": 600,
                 "completion_tokens_details": {"reasoning_tokens": 400}})) > 1e-12:
            errs.append("a call without a reported cost was not estimated from tokens")
        if len(lost) != 1 or lost[0]["ledger_cost"] <= 0 or lost[0].get("raw") is not None:
            errs.append(f"expected one lost attempt charged at its reservation, got {len(lost)}")
        if ledger["estimated_calls"] != len(est) + len(lost):
            errs.append("ledger estimated_calls disagrees with the records")
        total = sum(r["ledger_cost"] for r in recs)
        if abs(total - ledger["spent"]) > 1e-6:
            errs.append(f"records sum {total} != ledger {ledger['spent']}")
        if KEY in out:
            errs.append("the key was printed")
        first = {r["call_key"] for r in recs if r.get("raw") is not None}

        # resume with a higher cap: only unfinished calls are sent
        before = SEEN["requests"]
        code2, out2 = run(tmp, port, 1.0, 60)
        recs2 = [json.loads(l) for l in open(runfile)]
        sent = SEEN["requests"] - before
        done2 = [r for r in recs2 if r.get("raw") is not None]
        if code2 != 0:
            errs.append(f"resumed run exited {code2}: {out2[-300:]}")
        if len({r['call_key'] for r in done2}) != 60 or len(done2) != 60:
            errs.append(f"after resume {len(done2)} finished records, expected 60 distinct")
        if sent != 60 - len(first):
            errs.append(f"resume sent {sent} requests, expected {60 - len(first)}")
        if SEEN["auth"] != {"Bearer " + KEY}:
            errs.append("the key from --key-file was not the one sent")
        if SEEN["temperature"]:
            errs.append("temperature was sent despite --omit-temperature")
        if SEEN["cache_control"] != SEEN["requests"]:
            errs.append("--cache did not mark the system prompt")
    srv.shutdown()
    if errs:
        print("FAILED (OpenRouter path)")
        for e in errs:
            print("  " + e)
        sys.exit(1)
    print(f"budget self-test ok (OpenRouter): capped at ${cap} after {len(first)} finished calls "
          f"(ledger ${ledger['spent']:.4f}, {ledger['estimated_calls']} estimated), resumed the rest")


# ---------------------------------------------------------------- Anthropic
AKEY = "sk-ant-test-not-a-real-key"
A = {"messages": [], "creates": 0, "batches": {}, "seen": {}, "keys": set(), "polls": {}}
USAGE = {"input_tokens": 200, "cache_read_input_tokens": 2000, "cache_creation_input_tokens": 0,
         "output_tokens": 900, "output_tokens_details": {"thinking_tokens": 600}}


def message(text="{\"mentions\": []}", usage=USAGE):
    return {"id": "msg_test", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
            "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                        {"type": "text", "text": text}],
            "stop_reason": "end_turn", "stop_sequence": None, "usage": usage}


class FakeAnthropic(http.server.BaseHTTPRequestHandler):
    """Messages and Message Batches, shaped like the Claude API. A request's
    first appearance in a batch errors (retryable) when its text hashes to
    0 mod 7, and expires at 1 mod 11; its second appearance succeeds."""

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        out = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def _batch(self, bid):
        b = A["batches"][bid]
        ended = A["polls"].get(bid, 0) >= 1
        port = self.server.server_address[1]
        n = len(b["requests"])
        return {"id": bid, "type": "message_batch", "processing_status": "ended" if ended else "in_progress",
                "request_counts": {"processing": 0 if ended else n, "succeeded": n if ended else 0,
                                   "errored": 0, "canceled": 0, "expired": 0},
                "created_at": "2026-10-17T00:00:00Z", "ended_at": "2026-10-17T00:01:00Z" if ended else None,
                "expires_at": "2026-10-18T00:00:00Z", "archived_at": None, "cancel_initiated_at": None,
                "results_url": f"http://127.0.0.1:{port}/v1/messages/batches/{bid}/results" if ended else None}

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with LOCK:
            A["keys"].add(self.headers.get("x-api-key"))
        if self.path.startswith("/v1/messages/batches"):
            with LOCK:
                A["creates"] += 1
                bid = f"msgbatch_test_{A['creates']}"
                A["batches"][bid] = {"requests": body["requests"]}
            return self._json(self._batch(bid))
        with LOCK:
            A["messages"].append(body)
        return self._json(message(usage=dict(USAGE, cache_read_input_tokens=0, cache_creation_input_tokens=2000)))

    def do_GET(self):
        parts = self.path.split("?")[0].strip("/").split("/")
        bid = parts[3]
        if parts[-1] == "results":
            lines = []
            for r in A["batches"][bid]["requests"]:
                text = r["params"]["messages"][0]["content"]
                with LOCK:
                    n = A["seen"].get(text, 0)
                    A["seen"][text] = n + 1
                h = sum(map(ord, text))
                if n == 0 and h % 7 == 0:
                    res = {"type": "errored", "error": {"type": "error",
                                                        "error": {"type": "api_error", "message": "overloaded"}}}
                elif n == 0 and h % 11 == 1:
                    res = {"type": "expired"}
                else:
                    res = {"type": "succeeded", "message": message()}
                lines.append(json.dumps({"custom_id": r["custom_id"], "result": res}))
            out = ("\n".join(lines) + "\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/binary")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return
        with LOCK:
            A["polls"][bid] = A["polls"].get(bid, 0) + 1
        return self._json(self._batch(bid))


def run_anthropic(tmp, port, budget_usd, limit, extra=()):
    env = dict(os.environ)
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "OPENROUTER_API_KEY"):
        env.pop(v, None)
    cmd = [sys.executable, os.path.join(HERE, "run.py"), "--api", "anthropic", "--model", "claude-haiku-5-5",
           "--mode", "comment", "--prompt", "file:" + os.path.join(HERE, "prompts", "v6_comment.py"),
           "--labeled-only", "--limit", str(limit), "--max-tokens", "2000", "--reasoning", "medium",
           "--schema", "--cache", "--key-file", os.path.join(tmp, "keys.env"),
           "--anthropic-base-url", f"http://127.0.0.1:{port}", "--runs-dir", tmp, "--poll-seconds", "0.05",
           "--budget-file", os.path.join(tmp, "ledger.json"), "--budget", str(budget_usd), *extra]
    p = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def anthropic_test():
    errs = []
    import anthropic_backend as AB
    http.server.ThreadingHTTPServer.request_queue_size = 64
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeAnthropic)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    expect_batch = AB.cost(USAGE, batch=True)
    try:
        # 1. one direct call: the parameters, the key, and the cost at full price
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "keys.env"), "w") as f:
                f.write(f"OPENROUTER_API_KEY=sk-or-wrong\nANTHROPIC_API_KEY={AKEY}\nDATABASE_URL=postgres://x\n")
            code, out = run_anthropic(tmp, port, 1.0, 1)
            p = A["messages"][-1] if A["messages"] else {}
            rec = json.loads(open(next(os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(".jsonl"))).readline())
            schema_txt = json.dumps(p.get("output_config", {}).get("format", {}))
            checks = [
                (code == 0, f"direct call exited {code}: {out[-300:]}"),
                (A["keys"] == {AKEY}, "a key other than ANTHROPIC_API_KEY from the key file was sent"),
                (AKEY not in out and "sk-or-wrong" not in out, "a key was printed"),
                (p.get("model") == "claude-haiku-5-5", "wrong model id"),
                (p.get("thinking") == {"type": "adaptive"}, f"thinking {p.get('thinking')}"),
                (p.get("output_config", {}).get("effort") == "medium", "effort not medium"),
                (p.get("output_config", {}).get("format", {}).get("type") == "json_schema", "no json_schema format"),
                ('"type": ["' not in schema_txt and "anyOf" in schema_txt, "type unions not rewritten as anyOf"),
                (not any(k in p for k in ("temperature", "top_p", "top_k")), "a sampling parameter was sent"),
                (p.get("system", [{}])[0].get("cache_control") == {"type": "ephemeral"}, "system prompt not cached"),
                (abs(rec["ledger_cost"] - AB.cost(dict(USAGE, cache_read_input_tokens=0,
                                                       cache_creation_input_tokens=2000), batch=False)) < 1e-12,
                 "direct call cost is not tokens x price"),
                (rec.get("reasoning_tokens") == 600 and rec.get("json_ok"), "thinking tokens or JSON not recorded"),
            ]
            errs += [msg for ok, msg in checks if not ok]

        # 2. batches under a cap that is hit, then resumed with a higher cap
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "keys.env"), "w") as f:
                f.write(f"ANTHROPIC_API_KEY={AKEY}\n")
            cap = 0.01
            code, out = run_anthropic(tmp, port, cap, 60, ["--batch"])
            ledger = json.load(open(os.path.join(tmp, "ledger.json")))
            runfile = next(os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(".jsonl"))
            recs = [json.loads(l) for l in open(runfile)]
            ok_recs = [r for r in recs if r.get("raw") is not None]
            if code != 3 or "budget reached" not in out:
                errs.append(f"capped batch run should exit 3 (got {code}): {out[-300:]}")
            if ledger["spent"] > cap + 1e-9 or ledger.get("inflight"):
                errs.append(f"ledger {ledger['spent']} over cap {cap}, or holds left {ledger.get('inflight')}")
            if abs(sum(r["ledger_cost"] for r in recs) - ledger["spent"]) > 1e-9:
                errs.append("batch records do not sum to the ledger")
            if any(abs(r["ledger_cost"] - expect_batch) > 1e-12 for r in ok_recs):
                errs.append("a batch record's cost is not tokens x price x 0.5")
            if not any(r.get("attempt") == 2 for r in recs):
                errs.append("no errored/expired request was retried")
            if len({r["call_key"] for r in ok_recs}) != len(ok_recs) or len(ok_recs) >= 60:
                errs.append(f"{len(ok_recs)} finished records under the cap")
            creates = A["creates"]
            code2, out2 = run_anthropic(tmp, port, 1.0, 60, ["--batch"])
            recs2 = [json.loads(l) for l in open(runfile)]
            ok2 = {r["call_key"] for r in recs2 if r.get("raw") is not None}
            if code2 != 0 or len(ok2) != 60:
                errs.append(f"resume: exit {code2}, {len(ok2)} of 60 finished: {out2[-300:]}")
            sent_again = [r for r in A["batches"][f"msgbatch_test_{creates + 1}"]["requests"]]
            done_before = {r["call_key"] for r in ok_recs}
            state = json.load(open(runfile + ".batches.json"))
            for bid, info in state["batches"].items():
                if int(bid.rsplit("_", 1)[1]) > creates:
                    for k, rep, att in info["requests"].values():
                        if k in done_before:
                            errs.append(f"resume resubmitted finished {k}")
            del sent_again

        # 3. submit without waiting, then re-attach instead of resubmitting
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "keys.env"), "w") as f:
                f.write(f"ANTHROPIC_API_KEY={AKEY}\n")
            before = A["creates"]
            code, out = run_anthropic(tmp, port, 1.0, 30, ["--batch", "--no-wait"])
            ledger = json.load(open(os.path.join(tmp, "ledger.json")))
            if A["creates"] != before + 1 or not ledger.get("inflight") or ledger["spent"] != 0:
                errs.append(f"--no-wait should leave one batch held in flight: {ledger}")
            code, out = run_anthropic(tmp, port, 1.0, 30, ["--batch"])
            ledger = json.load(open(os.path.join(tmp, "ledger.json")))
            runfile = next(os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(".jsonl"))
            ok3 = {json.loads(l)["call_key"] for l in open(runfile) if json.loads(l).get("raw") is not None}
            if "re-attaching" not in out or ledger.get("inflight") or len(ok3) != 30:
                errs.append(f"re-attach failed: {len(ok3)} finished, inflight {ledger.get('inflight')}: {out[-300:]}")
            first_batch = A["batches"][f"msgbatch_test_{before + 1}"]["requests"]
            later = [b for k, b in A["batches"].items() if int(k.rsplit("_", 1)[1]) > before + 1]
            first_texts = {r["params"]["messages"][0]["content"] for r in first_batch}
            again = [r for b in later for r in b["requests"] if r["params"]["messages"][0]["content"] in first_texts]
            # only the first batch's errored/expired requests may appear again (as retries)
            if len(again) >= len(first_batch):
                errs.append("re-attach resubmitted the in-flight batch")
    finally:
        srv.shutdown()
    if errs:
        print("FAILED (Anthropic path)")
        for e in errs:
            print("  " + e)
        sys.exit(1)
    print(f"budget self-test ok (Anthropic): direct call parameters and cost; batches capped at ${cap}, "
          f"retried, resumed, and re-attached; {A['creates']} batches created")


if __name__ == "__main__":
    main()
    anthropic_test()
