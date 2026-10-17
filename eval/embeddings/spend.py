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
    lines = ["| model | purpose | calls | inputs | reported tokens | cost $ | cost / 1.3x estimate |",
             "|---|---|---|---|---|---|---|"]
    for (m, p), v in sorted(agg.items()):
        lines.append(f"| {m} | {p} | {v['calls']} | {v['inputs']:,} | {v['tokens']:,} | {v['cost']:.4f} | "
                     f"{v['cost'] / v['est']:.2f} |" if v["est"] else "")
    lines.append(f"\n**Total spend: ${total:.4f}** (cap $4.50, hard budget $5.00)")
    print("\n".join(lines))
    if write:
        (HERE / "SPEND.md").write_text("# OpenRouter spend\n\nFrom data/ledger.jsonl via spend.py.\n\n" + "\n".join(lines) + "\n")


if __name__ == "__main__":
    import sys
    main("--write" in sys.argv)
