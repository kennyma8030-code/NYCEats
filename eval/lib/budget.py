"""The hard spend cap: no harness command spends more than HARD_CAP_USD on one key.

The key the user benchmarks with is an Anthropic API key with a $6 limit. A
standard Anthropic key has no usage endpoint (the cost report needs an Admin
key), so the source of truth is a ledger on this machine: every completed
call's actual cost is written to eval/.spend/<sha256(key)[:12]>.json the moment
the call returns. It only sees spend from this harness on this machine; the
console's figure can be copied in with `bench.py --budget-set-spent`.

The cap holds under concurrency because spending is reserved before it
happens. Before a call is dispatched, its ceiling is reserved under a lock:
UTF-8 bytes of the whole input at the dearest input rate (a token always
covers at least one byte, so bytes bound tokens), plus max_tokens at the
output rate, times every attempt that might bill. A call is not sent unless
spent + reserved + its ceiling fits in what is left. When it returns, the
reservation is replaced with what it actually cost.

What can bill without telling us is an attempt that timed out or lost its
connection: the server may have run it. Those are charged at the attempt's
ceiling, and at most MAX_UNCERTAIN_RETRIES of them are retried, so the
reservation covers them too. 429s and 5xx are rejected before any work is
billed and are retried freely.
"""

import hashlib
import json
import os
import sys
import threading
import time

import providers

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)

# The one place the cap lives. A flag or EVAL_BUDGET_CAP_USD may lower it for a
# run; raising it means editing this line.
HARD_CAP_USD = 6.00

# An attempt that times out may have billed, so one retry of it is allowed and
# both are reserved for. Rate limits and server errors don't count here.
MAX_UNCERTAIN_RETRIES = 1

# Every request carries an explicit max_tokens so its worst case is bounded.
# Measured on the v1 + v2 gold: the biggest single-comment answer is 9,380
# bytes (28 mentions, about 2.7k tokens) and the biggest thread chunk's is
# 13,559 bytes (39 mentions, about 3.9k tokens). Haiku 5.5 thinks by default
# and its thinking counts inside max_tokens, so each mode gets roughly 3-4x
# its largest answer. 16,000 is also the ceiling for a non-streaming call.
DEFAULT_MAX_TOKENS = {"comment": 8000, "thread": 16000}
NONSTREAMING_MAX_TOKENS = 16000

# Request framing (roles, message wrappers) is a few tokens the bytes of the
# text don't count.
OVERHEAD_TOKENS = 200


def spend_dir():
    return os.environ.get("EVAL_SPEND_DIR") or os.path.join(EVAL, ".spend")


def effective_cap(requested=None):
    """The cap for this run: the hard cap, lowered by --cap or
    EVAL_BUDGET_CAP_USD, never raised."""
    cap = HARD_CAP_USD
    for source, value in (("EVAL_BUDGET_CAP_USD", os.environ.get("EVAL_BUDGET_CAP_USD")),
                          ("--cap", requested)):
        if value in (None, ""):
            continue
        v = float(value)
        if v > HARD_CAP_USD + 1e-12:
            raise SystemExit(f"{source} ${v:.2f} is above the hard cap ${HARD_CAP_USD:.2f}; a run may only "
                             f"lower the cap (raising it means editing HARD_CAP_USD in eval/lib/budget.py)")
        if v < 0:
            raise SystemExit(f"{source} must not be negative")
        cap = min(cap, v)
    return cap


def key_var(api):
    return "ANTHROPIC_API_KEY" if api == "anthropic" else "OPENROUTER_API_KEY"


def fingerprint(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


class BudgetExhausted(Exception):
    """The cap stopped dispatching. Calls in flight were finished and written;
    re-running the same command later resumes without repeating a paid call."""

    def __init__(self, message, stats=None):
        super().__init__(message)
        self.stats = stats


# ---------------------------------------------------------------- the ledger
class Ledger:
    """What this harness has spent on one key, kept in two files:

    <fp>.json   the running total, replaced atomically after every call
    <fp>.jsonl  one line per charge or correction, fsync'd, for audit

    The journal is appended first, so a crash between the two leaves the
    journal ahead, and loading takes the larger of the two. A file that can't
    be read stops the run: an unreadable ledger is never taken to mean $0,
    and nothing resets it."""

    def __init__(self, directory, fp, api):
        self.fp, self.api = fp, api
        self.path = os.path.join(directory, f"{fp}.json")
        self.journal = os.path.join(directory, f"{fp}.jsonl")
        self._lock = threading.Lock()
        self.spent, self.calls = self._load()

    def _load(self):
        spent = calls = 0
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    d = json.load(f)
                spent, calls = float(d["spent_usd"]), int(d.get("calls", 0))
            except (OSError, ValueError, KeyError, TypeError) as e:
                raise SystemExit(f"the spend ledger {self.path} can't be read ({e}); refusing to run rather "
                                 f"than assume nothing was spent. Fix the file or seed it with "
                                 f"--budget-set-spent.")
        replayed, n = self._replay()
        if replayed is not None and replayed > spent + 1e-9:
            spent, calls = replayed, max(calls, n)
        return spent, calls

    def _replay(self):
        if not os.path.exists(self.journal):
            return None, 0
        total, n = 0.0, 0
        with open(self.journal, encoding="utf-8") as f:
            lines = f.read().splitlines()
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except ValueError:
                if i == len(lines) - 1:      # a torn last line from a crash mid-append
                    continue
                raise SystemExit(f"the spend journal {self.journal} is corrupt at line {i + 1}; refusing to run")
            if e.get("kind") == "set_spent":
                total = float(e["usd"])
            else:
                total += float(e.get("usd") or 0)
                n += 1
        return total, n

    def _append(self, event):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.journal, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _write_total(self):
        tmp = f"{self.path}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"key_fp": self.fp, "api": self.api, "spent_usd": round(self.spent, 9),
                       "calls": self.calls, "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def charge(self, usd, **meta):
        with self._lock:
            self._append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "call", "usd": usd, **meta})
            self.spent += usd
            self.calls += 1
            self._write_total()

    def set_spent(self, usd, note=""):
        with self._lock:
            self._append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "set_spent", "usd": usd,
                          "previous": self.spent, "note": note})
            self.spent = usd
            self._write_total()


# ---------------------------------------------------------------- process lock
class KeyLock:
    """One live harness process per key. Reservations are in memory, so two
    processes spending on the same key would each think they had the whole
    remainder. The OS drops the lock if the process dies."""

    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.f = open(path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.f.close()
            raise SystemExit(f"another harness process is spending on this key ({path} is locked); "
                             f"wait for it to finish")

    def release(self):
        if self.f.closed:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self.f.close()


# ---------------------------------------------------------------- prices and ceilings
def call_prices(api, model_id, input_bytes=0, cat=None):
    """(input, output, cache_read, cache_write) $ per token, or None. Uses the
    long-prompt tier where a model has one and the input could reach it."""
    p = providers.prices(api, model_id, cat)
    if p is None:
        return None
    if api == "anthropic":
        long = providers.long_context_prices(model_id, input_bytes + OVERHEAD_TOKENS)
        if long:
            return long
    return p


def attempt_ceiling(api, model_id, system, user, max_tokens, cat=None):
    """The most one attempt can cost: every input byte as a token at the
    dearest input rate (a cache write costs more than plain input), plus
    max_tokens of output. None if the model has no known price."""
    tokens_in = len(system.encode("utf-8")) + len(user.encode("utf-8")) + OVERHEAD_TOKENS
    p = call_prices(api, model_id, tokens_in, cat)
    if p is None:
        return None
    pin, pout, pread, pwrite = p
    return tokens_in * max(pin, pread, pwrite) + max_tokens * pout


def pessimistic_call(api, model_id, system, user, max_tokens, first, cat=None):
    """One call in the pre-flight's pessimistic estimate: the first call per
    prompt writes the cache at the write rate, every later one pays full
    input as if caching never applied, and output runs to max_tokens. Bytes
    stand in for tokens, as in the ceiling."""
    sys_t = len(system.encode("utf-8"))
    user_t = len(user.encode("utf-8")) + OVERHEAD_TOKENS
    p = call_prices(api, model_id, sys_t + user_t, cat)
    if p is None:
        return None
    pin, pout, _, pwrite = p
    return sys_t * (max(pin, pwrite) if first else pin) + user_t * pin + max_tokens * pout


def check_max_tokens(api, max_tokens):
    if not max_tokens or max_tokens <= 0:
        raise SystemExit("every request needs an explicit positive max_tokens under the spend cap")
    if api == "anthropic" and max_tokens > NONSTREAMING_MAX_TOKENS:
        raise SystemExit(f"--max-tokens {max_tokens} is above {NONSTREAMING_MAX_TOKENS}, the most a "
                         f"non-streaming Anthropic call should ask for")


def new_meter():
    """What a provider reports back about one call's billing, filled in by
    providers.complete(): known cost, responses it couldn't price, and
    attempts that may have billed without answering."""
    return {"cost": 0.0, "unpriced": [], "uncertain": 0, "max_uncertain": MAX_UNCERTAIN_RETRIES}


def usage_cost(api, model_id, usage, cat=None):
    """A response's cost from its token counts, for a provider that didn't
    report one. None when the counts are missing."""
    pt, ct = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if pt is None or ct is None:
        return None
    p = call_prices(api, model_id, pt, cat)
    if p is None:
        return None
    pin, pout, pread, pwrite = p
    cr, cw = usage.get("cache_read_tokens") or 0, usage.get("cache_write_tokens") or 0
    plain = max(pt - cr - cw, 0)
    return plain * pin + cr * pread + cw * pwrite + ct * pout


# ---------------------------------------------------------------- the budget
class Budget:
    """The remaining budget for one key, and the reservations against it.

    remaining is fixed when the budget opens: cap - max(provider usage,
    ledger). Everything after that is this process's own spending and
    reservations, checked under one lock."""

    def __init__(self, api, ledger, cap, provider_usage=None, provider_limit=None, lock=None):
        self.api, self.ledger, self.cap = api, ledger, cap
        self.provider_usage, self.provider_limit = provider_usage, provider_limit
        self.lock_handle = lock
        self.spent_at_open = max(provider_usage or 0.0, ledger.spent)
        self.remaining = cap - self.spent_at_open
        if provider_limit is not None:
            self.remaining = min(self.remaining, provider_limit - (provider_usage or 0.0))
        self.remaining = max(self.remaining, 0.0)
        self.spent_run = 0.0
        self.reserved = 0.0
        self.overruns = 0
        self._lock = threading.Lock()

    # -- opening
    @classmethod
    def open(cls, api, cap=None, lock=True, need_key=True):
        """The budget for the key this api uses. lock=False opens it read-only
        (a dry run or a status print); it can't spend. The key comes from the
        environment; run.py and bench.py load .env into it first."""
        key = os.environ.get(key_var(api))
        if not key:
            if need_key:
                raise SystemExit(f"{key_var(api)} is not set (environment or .env); refusing to run "
                                 f"without a key whose spend can be tracked")
            return None
        fp = fingerprint(key)
        directory = spend_dir()
        handle = KeyLock(os.path.join(directory, f"{fp}.lock")) if lock else None
        try:
            ledger = Ledger(directory, fp, api)
        except BaseException:
            if handle:
                handle.release()
            raise
        usage = limit = None
        if api == "openrouter" and os.environ.get("EVAL_OPENROUTER_KEY_CHECK") == "1":
            # UNTESTED, optional: OpenRouter's own record of this key's usage.
            status = providers.openrouter_key_status()
            if status:
                usage, limit = status.get("usage"), status.get("limit")
        return cls(api, ledger, effective_cap(cap), usage, limit, handle)

    def close(self):
        if self.lock_handle:
            self.lock_handle.release()
            self.lock_handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- spending
    def available(self):
        with self._lock:
            return self.remaining - self.spent_run - self.reserved

    def reserve(self, usd):
        """Hold usd against the cap; None if it doesn't fit."""
        if self.lock_handle is None:
            raise RuntimeError("a read-only budget can't spend")
        with self._lock:
            if self.spent_run + self.reserved + usd > self.remaining + 1e-12:
                return None
            self.reserved += usd
            return usd

    def settle(self, reservation, meter, attempt_cost, model_id, call_key=None, cat=None):
        """Replace a reservation with what the call actually cost: what the
        provider reported, plus token-priced responses it didn't price, plus
        every attempt that may have billed without answering, at its ceiling."""
        actual = float(meter.get("cost") or 0.0)
        for u in meter.get("unpriced") or []:
            c = usage_cost(self.api, model_id, u, cat)
            actual += attempt_cost if c is None else c
        actual += (meter.get("uncertain") or 0) * attempt_cost
        with self._lock:
            self.reserved -= reservation
            self.spent_run += actual
            if actual > reservation + 1e-12:
                self.overruns += 1
                print(f"budget warning: {call_key} cost ${actual:.6f}, above its reservation "
                      f"${reservation:.6f}", file=sys.stderr)
        if actual > 0:
            self.ledger.charge(actual, model=model_id, call_key=call_key)
        return actual

    # -- reporting
    def status(self):
        return {"api": self.api, "key_fp": self.ledger.fp, "cap": self.cap,
                "provider_usage": self.provider_usage, "provider_limit": self.provider_limit,
                "ledger": self.ledger.spent, "remaining_at_open": self.remaining,
                "spent_run": self.spent_run, "available": self.available()}

    def lines(self, pessimistic=None, expected=None):
        s = self.status()
        pu = "n/a (no usage endpoint for this key)" if s["provider_usage"] is None else f"${s['provider_usage']:.4f}"
        out = [f"budget [{s['api']} key {s['key_fp']}]: cap ${s['cap']:.2f}  provider usage {pu}  "
               f"ledger ${s['ledger']:.4f}  remaining ${s['remaining_at_open']:.4f}"]
        if pessimistic is not None or expected is not None:
            money = lambda v: "n/a" if v is None else f"${v:.4f}"  # noqa: E731
            out.append(f"  plan: pessimistic {money(pessimistic)}  expected {money(expected)}")
        out.append(f"  spent this run ${s['spent_run']:.4f}  left now ${s['available']:.4f}")
        return out


def set_spent(api, usd, allow_lower=False, note="--budget-set-spent"):
    """Seed or correct the ledger, e.g. from the Anthropic console's figure.
    Raising the recorded spend is always allowed; lowering it needs --yes."""
    if usd < 0:
        raise SystemExit("spent can't be negative")
    b = Budget.open(api)           # takes the key's lock: no run may be spending meanwhile
    try:
        if usd < b.ledger.spent - 1e-12 and not allow_lower:
            raise SystemExit(f"lowering the recorded spend from ${b.ledger.spent:.4f} to ${usd:.4f} frees "
                             f"budget; re-run with --yes if the console really shows that")
        prev = b.ledger.spent
        b.ledger.set_spent(usd, note)
        return prev, usd
    finally:
        b.close()


def preflight(pessimistic, remaining, partial, hint):
    """Refuse a run whose pessimistic cost is above what's left, unless
    --partial: then calls go in order and the cap stops them, which it does
    either way. --yes has no say here."""
    if pessimistic > remaining + 1e-12 and not partial:
        raise SystemExit(f"refusing: the pessimistic estimate ${pessimistic:.4f} is above the ${remaining:.4f} "
                         f"left under the cap. {hint}")


def fits(calls, available):
    """How many calls, taken in order, fit in available dollars. calls is a
    list of pessimistic per-call costs."""
    total, n = 0.0, 0
    for c in calls:
        if total + c > available + 1e-12:
            break
        total += c
        n += 1
    return n, total
