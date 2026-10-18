"""Measure live query-embedding latency per model, cold and warm.

Search embeds the query on every request, so this is latency a user waits
for. Each model embeds 25 single queries, one call at a time, uncached, with
rounds interleaved across models so a slow minute on the network hits all of
them alike.

  cold  a new connection for every call (DNS + TCP + TLS each time), which is
        what the first version of this benchmark measured
  warm  one keep-alive connection per model, after a discarded warm-up call;
        this is what a long-running server with a shared Session sees

p90 is nearest-rank: the ceil(0.9 n)-th smallest of n samples.

Measured from this machine through OpenRouter. Railway will differ in the
network constant, but the ordering between models should hold. Every call
goes through the same ledger and cap; the run refuses to start if its
pessimistic estimate is over MAX_USD.
"""

import json
import math
import statistics
import time

import openrouter
from common import DATA, HERE, read_jsonl
from configs import MODELS
from openrouter import PRICE, SAFETY, count_tokens, ledger, raw_embed

N = 25
MAX_USD = 0.05


def nearest_rank(sorted_vals, pct):
    return sorted_vals[max(0, math.ceil(pct * len(sorted_vals)) - 1)]


def summarise(ts):
    ts = sorted(ts)
    return {"n": len(ts), "median_ms": round(1000 * statistics.median(ts)),
            "p90_ms": round(1000 * nearest_rank(ts, 0.9)), "min_ms": round(1000 * ts[0])}


def main():
    qs = [q["text"] for q in read_jsonl(HERE / "queries.jsonl")][:N]
    # Two modes x N queries, plus one warm-up per model.
    est = sum((2 * sum(count_tokens(m.fmt_query(q)) for q in qs) + count_tokens(m.fmt_query(qs[0])))
              * SAFETY * PRICE[m.model] for m in MODELS)
    print(f"estimated cost ${est:.5f} (limit ${MAX_USD})")
    if est > MAX_USD:
        raise SystemExit("over the latency budget; not running")
    spent_before = ledger().spent

    times = {mode: {m.name: [] for m in MODELS} for mode in ("cold", "warm")}
    for q in qs:
        for m in MODELS:
            openrouter._tls.session = None  # force a fresh connection
            t0 = time.perf_counter()
            raw_embed(m.model, [m.fmt_query(q)], m.query_cfg.extra, "latency-cold")
            times["cold"][m.name].append(time.perf_counter() - t0)

    sessions = {}
    for m in MODELS:
        openrouter._tls.session = None
        raw_embed(m.model, [m.fmt_query(qs[0])], m.query_cfg.extra, "latency-warmup")
        sessions[m.name] = openrouter._tls.session
    for q in qs:
        for m in MODELS:
            openrouter._tls.session = sessions[m.name]
            t0 = time.perf_counter()
            raw_embed(m.model, [m.fmt_query(q)], m.query_cfg.extra, "latency-warm")
            times["warm"][m.name].append(time.perf_counter() - t0)

    out = {mode: {name: summarise(ts) for name, ts in by.items()} for mode, by in times.items()}
    for m in MODELS:
        print(f"{m.name:16} cold {out['cold'][m.name]}  warm {out['warm'][m.name]}")
    out["cost_usd"] = round(ledger().spent - spent_before, 6)
    (HERE / "latency.json").write_text(json.dumps(out, indent=2))
    print(f"latency run cost ${out['cost_usd']:.5f}; ledger ${ledger().spent:.4f}")


if __name__ == "__main__":
    main()
