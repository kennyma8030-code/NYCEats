"""Summarise the spend ledger: per model and purpose, inputs, provider-reported
tokens, cost, and the ratio of reported tokens to our cl100k estimate (how far
each provider's tokenizer is from OpenAI's)."""

import json
from collections import defaultdict

from common import DATA, HERE


def main(write=False):
    agg = defaultdict(lambda: {"calls": 0, "inputs": 0, "tokens": 0, "cost": 0.0, "est": 0.0})
    for line in (DATA / "ledger.jsonl").read_text().splitlines():
        d = json.loads(line)
        for key in ((d["model"], d["purpose"]), (d["model"], "ALL")):
            a = agg[key]
            a["calls"] += 1
            a["inputs"] += d["n_inputs"]
            a["tokens"] += d["tokens"] or 0
            a["cost"] += d["cost_usd"]
            a["est"] += d["est_usd"]
    total = sum(v["cost"] for (m, p), v in agg.items() if p == "ALL")
    rows = [json.loads(l) for l in (DATA / "ledger.jsonl").read_text().splitlines() if l.strip()]
    maybe = [r for r in rows if r.get("possibly_billed")]
    lines = ["| model | purpose | calls | inputs | reported tokens | cost $ | cost / 1.3x estimate |",
             "|---|---|---|---|---|---|---|"]
    for (m, p), v in sorted(agg.items()):
        lines.append(f"| {m} | {p} | {v['calls']} | {v['inputs']:,} | {v['tokens']:,} | {v['cost']:.4f} | "
                     f"{v['cost'] / v['est']:.2f} |" if v["est"] else "")
    lines.append(f"\n**Ledger total: ${total:.4f}** (cap $4.50, hard budget $5.00), of which "
                 f"${sum(r['cost_usd'] for r in maybe):.4f} from {len(maybe)} possibly-billed failed attempts "
                 "charged at their pessimistic estimate.")
    lines.append("\nRuns before the retry accounting was added recorded only successful calls. OpenRouter's "
                 "own counter for this key (GET /api/v1/key, read 2026-10-18 before the latency re-run) "
                 "showed $2.8532 used against $2.7949 in the ledger at that time, so $0.0583 was billed "
                 "but not recorded: requests in flight when two runs were stopped, and silent retries while "
                 "the machine slept. True spend is the key's counter; confirm it on OpenRouter's usage page.")
    print("\n".join(lines))
    if write:
        (HERE / "SPEND.md").write_text("# OpenRouter spend\n\nFrom data/ledger.jsonl via spend.py.\n\n" + "\n".join(lines) + "\n")


if __name__ == "__main__":
    import sys
    main("--write" in sys.argv)
