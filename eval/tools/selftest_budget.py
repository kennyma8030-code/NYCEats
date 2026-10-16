"""Checks for the spend cap (eval/lib/budget.py), with fake providers only.

    python eval/tools/selftest_budget.py

Nothing here makes a network call or touches the real ledger: every test
points EVAL_SPEND_DIR at a temporary folder and uses fake keys.
"""

import os
import random
import sys
import tempfile
import threading
import time
import types

EVAL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EVAL)
import _paths  # noqa: E402,F401

import bench as BN  # noqa: E402
import budget as B  # noqa: E402
import providers  # noqa: E402
import run as R  # noqa: E402

FAILS = []
MODEL = "claude-haiku-5-5"
SYSTEM = "S" * 20000            # about the v5 comment prompt's size in bytes


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("FAIL:", msg)


class FakeAnthropic:
    """Stands in for the anthropic module. Each call sleeps a little, then
    bills random output up to max_tokens. Call keys in `timeouts` time out
    that many times first."""

    class APIStatusError(Exception):
        def __init__(self, status_code, message):
            super().__init__(message)
            self.status_code, self.message = status_code, message

    class APIConnectionError(Exception):
        pass

    def __init__(self, seed=0, timeouts=None, max_out=None):
        self.rng = random.Random(seed)
        self.lock = threading.Lock()
        self.calls = []
        self.timeouts = dict(timeouts or {})
        self.max_out = max_out
        fake = self

        class Messages:
            def create(self, **kw):
                user = kw["messages"][0]["content"]
                with fake.lock:
                    fake.calls.append(user)
                    left = fake.timeouts.get(user, 0)
                    if left:
                        fake.timeouts[user] = left - 1
                    out = fake.rng.randint(1, fake.max_out or kw["max_tokens"])
                    nap = fake.rng.uniform(0, 0.01)
                time.sleep(nap)
                if left:
                    raise FakeAnthropic.APIConnectionError("timed out")
                inp = len(kw["system"][0]["text"]) // 4 + len(user) // 4
                msg = {"content": [{"type": "text", "text": '{"mentions": []}'}], "stop_reason": "end_turn",
                       "usage": {"input_tokens": inp, "output_tokens": out,
                                 "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}
                return types.SimpleNamespace(to_dict=lambda: msg)

        class Anthropic:
            def __init__(self, **kw):
                self.messages = Messages()

        self.Anthropic = Anthropic


def install(sdk):
    providers._sdk, providers._client = sdk, None
    providers.RETRY_BASE_S = 0


def jobs(n, prefix="c"):
    return [{"call_key": f"comment:{prefix}{i}", "item_ids": [f"i{i}"], "user": f"COMMENT {prefix}{i} " + "x" * 2000,
             "id_map": {None: f"{prefix}{i}"}} for i in range(n)]


class Env:
    """Temporary ledger folder, fake key and optional lower cap."""

    def __init__(self, cap=None, key="fake-anthropic-key"):
        self.cap, self.key = cap, key

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = {k: os.environ.get(k) for k in ("EVAL_SPEND_DIR", "ANTHROPIC_API_KEY", "EVAL_BUDGET_CAP_USD")}
        os.environ["EVAL_SPEND_DIR"] = self.tmp.name
        os.environ["ANTHROPIC_API_KEY"] = self.key
        if self.cap is None:
            os.environ.pop("EVAL_BUDGET_CAP_USD", None)
        else:
            os.environ["EVAL_BUDGET_CAP_USD"] = str(self.cap)
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()


def watch(b):
    """Wrap a budget's reserve to record the most it ever had committed."""
    peak = {"v": 0.0}
    real = b.reserve

    def reserve(usd):
        got = real(usd)
        with b._lock:
            peak["v"] = max(peak["v"], b.spent_run + b.reserved)
        return got
    b.reserve = reserve
    return peak


# ---------------------------------------------------------------- tests
def test_cap_flags():
    check(B.effective_cap() == B.HARD_CAP_USD, "the default cap is the hard cap")
    check(B.effective_cap(2.5) == 2.5, "--cap lowers the cap")
    try:
        B.effective_cap(B.HARD_CAP_USD + 1)
        check(False, "--cap must not raise the cap")
    except SystemExit as e:
        check("only lower" in str(e), "raising the cap is refused with the reason")
    os.environ["EVAL_BUDGET_CAP_USD"] = "1.5"
    try:
        check(B.effective_cap() == 1.5 and B.effective_cap(3) == 1.5, "the env var lowers too, and the lower wins")
        os.environ["EVAL_BUDGET_CAP_USD"] = "99"
        try:
            B.effective_cap()
            check(False, "the env var must not raise the cap")
        except SystemExit:
            pass
    finally:
        os.environ.pop("EVAL_BUDGET_CAP_USD", None)


def test_concurrent_reservations_never_pass_the_cap():
    with Env(cap=0.05):
        install(FakeAnthropic(seed=1))
        b = B.Budget.open("anthropic")
        peak = watch(b)
        out = os.path.join(os.environ["EVAL_SPEND_DIR"], "run.jsonl")
        todo = [(j, 0) for j in jobs(400)]
        try:
            R.execute(todo, MODEL, SYSTEM, "h", "comment", {"timeout": 5}, "anthropic", out, 16, False, spend=b)
            check(False, "400 calls can't fit in $0.05")
        except B.BudgetExhausted as e:
            check(e.stats["calls"] > 0, f"some calls ran before the cap ({e.stats['calls']})")
        check(peak["v"] <= b.remaining + 1e-12, f"spent + reserved never passed what was left "
                                                f"({peak['v']:.6f} vs {b.remaining:.6f})")
        check(b.reserved < 1e-12, "every reservation was settled")
        check(b.ledger.spent <= 0.05 + 1e-12, f"the ledger stayed under the cap (${b.ledger.spent:.6f})")
        check(b.overruns == 0, "no call cost more than it reserved")
        check(abs(b.ledger.spent - b.spent_run) < 1e-9, "the ledger holds exactly what this run spent")
        b.close()


def test_stop_and_resume():
    with Env(cap=0.03):
        sdk = FakeAnthropic(seed=2)
        install(sdk)
        out = os.path.join(os.environ["EVAL_SPEND_DIR"], "run.jsonl")
        js = jobs(60)
        try:
            R.execute([(j, 0) for j in js], MODEL, SYSTEM, "h", "comment", {"timeout": 5}, "anthropic", out, 8, False)
            check(False, "the first pass must hit the cap")
        except B.BudgetExhausted as e:
            first = e.stats["calls"]
        done = R.cached_calls(out)
        check(len(done) == first, f"everything made before the stop is written ({len(done)} vs {first})")
        made_first = set(sdk.calls)
        # A new budget: the user lifts the env cap back to the hard cap.
        os.environ.pop("EVAL_BUDGET_CAP_USD", None)
        sdk2 = FakeAnthropic(seed=3)
        install(sdk2)
        todo = [(j, 0) for j in js if (j["call_key"], 0) not in R.cached_calls(out)]
        R.execute(todo, MODEL, SYSTEM, "h", "comment", {"timeout": 5}, "anthropic", out, 8, False)
        check(len(R.cached_calls(out)) == len(js), "the resume finished every call")
        check(not (set(sdk2.calls) & made_first), "the resume repeated no paid call")
        b = B.Budget.open("anthropic", lock=False)
        check(b.ledger.calls == len(js), f"the ledger counted every call once ({b.ledger.calls})")


def test_ledger_persists_and_is_never_reset():
    with Env():
        install(FakeAnthropic(seed=4))
        out = os.path.join(os.environ["EVAL_SPEND_DIR"], "run.jsonl")
        R.execute([(j, 0) for j in jobs(5)], MODEL, SYSTEM, "h", "comment", {"timeout": 5}, "anthropic", out, 2, False)
        b1 = B.Budget.open("anthropic", lock=False)
        spent = b1.ledger.spent
        check(spent > 0, "the first run's spend is on disk")
        R.execute([(j, 0) for j in jobs(5, "d")], MODEL, SYSTEM, "h", "comment", {"timeout": 5}, "anthropic", out, 2,
                  False)
        b2 = B.Budget.open("anthropic", lock=False)
        check(b2.ledger.spent > spent, "a second run adds to it")
        check(abs(b2.remaining - (B.HARD_CAP_USD - b2.ledger.spent)) < 1e-9, "remaining = cap - ledger")
        # A crash between the journal append and the total's rewrite: the
        # journal is ahead, and loading takes it.
        led = b2.ledger
        with open(led.journal, "a", encoding="utf-8") as f:
            f.write('{"kind": "call", "usd": 0.5}\n')
        check(abs(B.Budget.open("anthropic", lock=False).ledger.spent - (led.spent + 0.5)) < 1e-9,
              "a journal ahead of the total wins")
        with open(led.path, "w", encoding="utf-8") as f:
            f.write("{not json")
        try:
            B.Budget.open("anthropic", lock=False)
            check(False, "a corrupt ledger must stop the run, not read as $0")
        except SystemExit as e:
            check("refusing" in str(e), "a corrupt ledger is refused with the reason")


def test_set_spent():
    with Env():
        prev, now = B.set_spent("anthropic", 1.25)
        check(prev == 0 and now == 1.25, "seeding the ledger from the console figure")
        check(abs(B.Budget.open("anthropic", lock=False).remaining - (B.HARD_CAP_USD - 1.25)) < 1e-9,
              "the seeded spend counts against the cap")
        B.set_spent("anthropic", 2.0)
        try:
            B.set_spent("anthropic", 0.5)
            check(False, "lowering the recorded spend needs --yes")
        except SystemExit as e:
            check("--yes" in str(e), "lowering without --yes says how")
        B.set_spent("anthropic", 0.5, allow_lower=True)
        check(abs(B.Budget.open("anthropic", lock=False).ledger.spent - 0.5) < 1e-9, "lowering with --yes")


def test_provider_usage_and_ledger():
    with Env():
        led = B.Ledger(os.environ["EVAL_SPEND_DIR"], "fp", "openrouter")
        led.spent = 1.0
        b = B.Budget("openrouter", led, 6.0, provider_usage=2.5, provider_limit=None)
        check(abs(b.remaining - 3.5) < 1e-9, "provider usage above the ledger wins")
        b = B.Budget("openrouter", led, 6.0, provider_usage=0.4, provider_limit=None)
        check(abs(b.remaining - 5.0) < 1e-9, "the ledger above provider usage wins")
        b = B.Budget("openrouter", led, 6.0, provider_usage=0.4, provider_limit=2.0)
        check(abs(b.remaining - 1.6) < 1e-9, "a provider limit below the cap binds")


def test_refusals():
    try:
        B.preflight(7.0, 5.0, partial=False, hint="")
        check(False, "a pessimistic estimate above what's left must be refused")
    except SystemExit as e:
        check("refusing" in str(e), "the refusal says why")
    B.preflight(7.0, 5.0, partial=True, hint="")   # --partial: the cap does the stopping
    B.preflight(4.0, 5.0, partial=False, hint="")
    with Env():
        saved = providers._catalog
        providers._catalog = {}
        try:
            R.execute([(jobs(1)[0], 0)], "nobody/unpriced-model", SYSTEM, "h", "comment", {"timeout": 5},
                      "openrouter", os.path.join(os.environ["EVAL_SPEND_DIR"], "x.jsonl"), 1, False)
            check(False, "a model with no known price must be refused")
        except SystemExit as e:
            check("no known price" in str(e), "unknown price is refused with the reason")
        finally:
            providers._catalog = saved
        try:
            B.check_max_tokens("anthropic", 64000)
            check(False, "max_tokens above the non-streaming ceiling must be refused")
        except SystemExit:
            pass
        os.environ.pop("ANTHROPIC_API_KEY")
        try:
            B.Budget.open("anthropic")
            check(False, "no key: refuse rather than spend untracked")
        except SystemExit:
            pass


def test_uncertain_attempts_are_charged():
    """A timed-out attempt may have billed: it is charged at its ceiling, and
    only one is retried, so the reservation covers it."""
    with Env():
        js = jobs(2)
        sdk = FakeAnthropic(seed=5, timeouts={js[0]["user"]: 1, js[1]["user"]: 5}, max_out=10)
        install(sdk)
        b = B.Budget.open("anthropic")
        out = os.path.join(os.environ["EVAL_SPEND_DIR"], "t.jsonl")
        R.execute([(j, 0) for j in js], MODEL, SYSTEM, "h", "comment", {"timeout": 5}, "anthropic", out, 1, False,
                  spend=b)
        ceiling = B.attempt_ceiling("anthropic", MODEL, SYSTEM, js[0]["user"], B.DEFAULT_MAX_TOKENS["comment"])
        check(sdk.calls.count(js[1]["user"]) == 1 + B.MAX_UNCERTAIN_RETRIES,
              f"a call that keeps timing out is retried {B.MAX_UNCERTAIN_RETRIES} time(s), no more")
        check(b.spent_run >= 3 * ceiling - 1e-12, "three timed-out attempts were charged at their ceiling")
        check(b.overruns == 0, "the reservation covered the uncertain attempts")
        check(len(R.cached_calls(out)) == 1, "the call that answered is cached; the one that never did is not")
        b.close()


def test_one_process_per_key():
    with Env():
        b = B.Budget.open("anthropic")
        try:
            B.Budget.open("anthropic")
            check(False, "a second spender on the same key must be refused")
        except SystemExit as e:
            check("locked" in str(e), "the second spender is told the key is locked")
        b.close()
        B.Budget.open("anthropic").close()      # released: opens again


def test_spend_order():
    modes, sets = BN.spend_order(["thread", "comment"], ["v2", "v1"])
    check(modes == ["comment", "thread"] and sets == ["v1", "v2"], "comment before thread, v1 before v2")
    plans = [{"todo": [(None, 0), (None, 1)]}, {"todo": [(None, 0)]}, {"todo": [(None, 1)]}]
    check(BN.spend_queue(plans, 2) == [(0, 0), (1, 0), (0, 1), (2, 1)],
          "one rep of every row before the next rep of any, rows in order")
    args = types.SimpleNamespace(limit=None, repeat=1, tag="")
    opts = {"temperature": 0.0, "max_tokens": None, "timeout": 5}
    v5 = BN.plan_run(MODEL, "anthropic", "file:" + os.path.join(EVAL, "prompts", "v5_{mode}.py"), "comment",
                     ["v1", "v2"], args, opts)
    v1_items = {i["item_id"] for i in R.load_items(os.path.join(EVAL, "v1", "items.jsonl"))}
    first_v2 = next((k for k, j in enumerate(v5["jobs"]) if not set(j["item_ids"]) & v1_items), None)
    check(first_v2 is not None and all(set(j["item_ids"]) & v1_items for j in v5["jobs"][:first_v2]),
          "within a row, v1's calls come before v2's own")
    check(v5["opts"]["max_tokens"] == B.DEFAULT_MAX_TOKENS["comment"], "the plan carries an explicit max_tokens")


def main():
    test_cap_flags()
    test_concurrent_reservations_never_pass_the_cap()
    test_stop_and_resume()
    test_ledger_persists_and_is_never_reset()
    test_set_spent()
    test_provider_usage_and_ledger()
    test_refusals()
    test_uncertain_attempts_are_charged()
    test_one_process_per_key()
    test_spend_order()
    providers._sdk, providers._client = None, None
    if FAILS:
        raise SystemExit(f"{len(FAILS)} checks failed")
    print("selftest_budget ok")


if __name__ == "__main__":
    main()
