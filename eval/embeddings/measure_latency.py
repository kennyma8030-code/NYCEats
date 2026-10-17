"""Measure live query-embedding latency per model.

Search embeds the query on every request, so this is latency the user waits
for. Each model embeds 25 single queries one call at a time, uncached, rounds
interleaved across models so a slow minute on the network hits all of them.
Measured from this machine through OpenRouter; Railway will differ in the
constant (network path) but the ordering between models should hold.
Costs well under a cent and goes through the same ledger and cap.
"""

import json
import statistics
import time

from common import DATA, HERE, read_jsonl
from configs import MODELS
from openrouter import ledger, raw_embed

N = 25


def main():
    qs = [q["text"] for q in read_jsonl(HERE / "queries.jsonl")][:N]
    times = {m.name: [] for m in MODELS}
    for i, q in enumerate(qs):
        for m in MODELS:
            t0 = time.perf_counter()
            raw_embed(m.model, [m.fmt_query(q)], m.query_cfg.extra, "latency")
            times[m.name].append(time.perf_counter() - t0)
    out = {}
    for name, ts in times.items():
        ts = sorted(ts)
        out[name] = {"n": len(ts), "median_ms": round(1000 * statistics.median(ts)),
                     "p90_ms": round(1000 * ts[int(0.9 * len(ts)) - 1]),
                     "min_ms": round(1000 * ts[0])}
        print(name, out[name])
    (DATA / "latency.json").write_text(json.dumps(out, indent=2))
    (HERE / "latency.json").write_text(json.dumps(out, indent=2))
    print("ledger $%.4f" % ledger().spent)


if __name__ == "__main__":
    main()
