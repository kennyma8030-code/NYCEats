"""A hard spend cap for eval/run.py, shared by every run that names the same ledger.

The ledger is a small JSON file of cumulative cost across runs:

    {"budget": 4.0, "spent": 1.2345, "calls": 812, "estimated_calls": 3,
     "runs": {"<run file>": {"spent": ..., "calls": ...}}}

Before a call, run.py reserves that call's worst case: input at chars/3
tokens, uncached, plus max_tokens of output. The call goes ahead only if
spent + every reservation still in flight + this one stays within the
budget. So the cap holds even with a pool of workers in flight, which
"refuse once spent >= budget" alone would not guarantee. After the call,
the reservation is swapped for the real cost: OpenRouter's reported
`usage.cost` when present, else an estimate from the token counts at the
model's prices, flagged in the ledger and on the record.

Some attempts may be billed with no response to show for it: a timeout or a
dropped connection after the request was sent. Those are charged their full
reservation and flagged. A budgeted run never retries them, so one call is
never billed twice unseen.

Updates are atomic (temp file + os.replace) under an exclusive flock, so
several processes on one ledger cannot lose an update. Reservations live in
the process that made them; run steps on one ledger one at a time, as
eval/bench_v6.py does, so another process's in-flight calls are not counted.
"""

import fcntl
import json
import os
import threading

# USD per token, from OpenRouter's model list (anthropic/claude-haiku-5.5, prompts
# under 100k tokens). Output covers reasoning tokens.
HAIKU_55 = {"in": 0.10e-6, "out": 0.50e-6, "cache_read": 0.01e-6, "cache_write": 0.125e-6}


def estimate_cost(usage, prices=HAIKU_55):
    """Cost of one call from its token counts, for calls with no reported cost.

    Conservative where the counts are ambiguous: reasoning is added on top of
    completion tokens unless completion already covers it.
    """
    usage = usage or {}
    pt = usage.get("prompt_tokens") or 0
    pdet = usage.get("prompt_tokens_details") or {}
    cached = pdet.get("cached_tokens") or 0
    written = pdet.get("cache_write_tokens") or 0
    ct = usage.get("completion_tokens") or 0
    rt = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    out = ct if ct >= rt else ct + rt
    fresh = max(pt - cached - written, 0)
    return (fresh * prices["in"] + cached * prices["cache_read"] + written * prices["cache_write"]
            + out * prices["out"])


def worst_case(system, user, max_tokens, prices=HAIKU_55):
    """The most one call can cost: input at chars/3 tokens, uncached, plus max_tokens out."""
    return (len(system) + len(user)) / 3 * prices["in"] + max_tokens * prices["out"]


class Ledger:
    def __init__(self, path, budget, run_name):
        self.path, self.budget, self.run = path, float(budget), run_name
        self._lock = threading.Lock()
        self.reserved = 0.0
        self.stopped = False
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)

    # -- file
    def _read(self):
        if not os.path.exists(self.path):
            return {"budget": self.budget, "spent": 0.0, "calls": 0, "estimated_calls": 0, "runs": {}}
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def _update(self, fn):
        with open(self.path + ".lock", "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                data = self._read()
                fn(data)
                tmp = f"{self.path}.{os.getpid()}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=1)
                os.replace(tmp, self.path)
                return data
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)

    def spent(self):
        with open(self.path + ".lock", "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_SH)
            try:
                return float(self._read().get("spent", 0.0))
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)

    # -- calls
    def reserve(self, amount):
        """True, holding `amount`, if the call fits under the cap. Once a call
        doesn't fit, every later reserve() refuses too, so the run winds down."""
        with self._lock:
            if self.stopped:
                return False
            if self.spent() + self.reserved + amount > self.budget:
                self.stopped = True
                return False
            self.reserved += amount
            return True

    def settle(self, reserved, cost, estimated):
        """Swap a reservation for the call's real (or estimated) cost."""
        def add(d):
            d["budget"] = self.budget
            d["spent"] = round(float(d.get("spent", 0.0)) + cost, 8)
            d["calls"] = d.get("calls", 0) + 1
            d["estimated_calls"] = d.get("estimated_calls", 0) + bool(estimated)
            r = d.setdefault("runs", {}).setdefault(self.run, {"spent": 0.0, "calls": 0, "estimated_calls": 0})
            r["spent"] = round(r["spent"] + cost, 8)
            r["calls"] += 1
            r["estimated_calls"] += bool(estimated)
        with self._lock:
            self._update(add)
            self.reserved -= reserved
