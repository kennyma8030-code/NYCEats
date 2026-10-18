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
        print("FAILED")
        for e in errs:
            print("  " + e)
        sys.exit(1)
    print(f"budget self-test ok: capped at ${cap} after {len(first)} finished calls "
          f"(ledger ${ledger['spent']:.4f}, {ledger['estimated_calls']} estimated), resumed the rest")


if __name__ == "__main__":
    main()
