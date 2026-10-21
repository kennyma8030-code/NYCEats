"""Price the thread-mode head-to-head before anything is sent. No API, no database.

    python eval/thread_v6/plan.py            # the table, and plan.json next to this file

Each run is chunked exactly as eval/run.py --threads would chunk it (the same
chunked.jobs), then priced at batch prices three ways:

  * expected: input at the measured chars/token with the system prompt read
    from cache (the benchmark's batches hit the cache on 99% of requests),
    output from anthropic_v6.thread_output_tokens (fitted to the round-1
    thread runs, raised for round 4; those chunks were dense with places, so
    this leans high);
  * uncached: the same with the system prompt billed fresh every time;
  * worst: what the ledger holds before a chunk is sent (all input as cache
    writes, all 32,000 tokens out). A cap below a run's worst case still
    runs, in smaller sub-batches, one turnaround after another.

The caps are each run's expected cost plus a margin, rounded up, and they sum
to at most $5.00, the owner's ceiling for the whole head-to-head.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chunked as TC  # noqa: E402

ROOT = TC.ROOT
sys.path.insert(0, ROOT)
import anthropic_v6 as AV  # noqa: E402

SLICES = os.path.join(HERE, "slices")
MAX_TOKENS = 32000
# (run tag, slice, effort, chunk sizes, cap in USD)
# big-med32k-c25 measures whether bigger chunks are cheaper per comment (the
# fixed output a chunk costs is most of the backlog's price); its $0.30 came
# out of fresh-med32k's and v2half-med32k's margins.
RUNS = [
    ("fresh-med32k", "fresh", "medium", {}, 1.25),
    ("fresh-low", "fresh", "low", {}, 0.95),
    ("v1-med32k", "v1", "medium", {}, 0.20),
    ("v1-low", "v1", "low", {}, 0.15),
    ("v2half-med32k", "v2half", "medium", {}, 0.95),
    ("big-med32k", "big", "medium", {}, 0.40),
    ("recent-med32k", "recent", "medium", {}, 0.35),
    ("big-med32k-c12", "big", "medium", {"soft_comments": 12}, 0.45),
    ("big-med32k-c25", "big", "medium", {"soft_comments": 25}, 0.30),
]
CEILING = 5.00


def price(run):
    tag, slice_, effort, sizes, cap = run
    jobs = TC.jobs(os.path.join(SLICES, f"{slice_}.threads.jsonl"), **sizes)
    system = TC.SYSTEM_PROMPT
    t = {"run": tag, "slice": slice_, "effort": effort, "sizes": sizes, "cap": cap, "chunks": len(jobs),
         "items": 0, "graded": 0, "posts": 0, "in_tokens": 0.0, "out_tokens": 0.0,
         "expected": 0.0, "uncached": 0.0, "worst": 0.0, "post_extra": 0.0}
    for j in jobs:
        n = len(j["covers"])
        out = AV.thread_output_tokens(effort, n, MAX_TOKENS)
        t["items"] += n
        t["graded"] += len(j["item_ids"])
        t["posts"] += bool(j["chunk"]["post_item"])
        t["in_tokens"] += (len(system) + len(j["user"])) / AV.CHARS_PER_TOKEN + AV.SCHEMA_OVERHEAD_TOKENS
        t["out_tokens"] += out
        t["expected"] += AV.estimate(system, j["user"], batch=True, cached=True, output_tokens=out)
        t["uncached"] += AV.estimate(system, j["user"], batch=True, cached=False, output_tokens=out)
        t["worst"] += AV.worst_case(system, j["user"], batch=True, max_tokens=MAX_TOKENS)
        if j["chunk"]["post_item"]:
            # What the post as item [0] adds: its output (one more item) and its
            # body past the 800 characters context would have shown.
            t["post_extra"] += (AV.THREAD_OUTPUT[effort][1] * AV.PRICES["out"]
                                + max(0, len(j["user"].split("\n\n", 1)[0]) - 800) / AV.CHARS_PER_TOKEN
                                * AV.PRICES["in"]) * AV.BATCH_DISCOUNT
    return t


def table(rows):
    head = ("| run | slice | effort | chunks | items numbered | graded | in tok | out tok | expected | "
            "uncached | worst case | of which post [0] | cap |")
    out = [head, "|" + "---|" * 13]
    for r in rows:
        sizes = f" (soft {r['sizes']['soft_comments']})" if r["sizes"] else ""
        out.append(f"| {r['run']} | {r['slice']} | {r['effort']}{sizes} | {r['chunks']} | {r['items']:,} | "
                   f"{r['graded']:,} | {r['in_tokens'] / 1e6:.2f}M | {r['out_tokens'] / 1e6:.2f}M | "
                   f"${r['expected']:.2f} | ${r['uncached']:.2f} | ${r['worst']:.2f} | ${r['post_extra']:.3f} | "
                   f"${r['cap']:.2f} |")
    tot = {k: sum(r[k] for r in rows) for k in ("chunks", "items", "graded", "in_tokens", "out_tokens",
                                                 "expected", "uncached", "worst", "post_extra", "cap")}
    out.append(f"| **total** | | | {tot['chunks']} | {tot['items']:,} | {tot['graded']:,} | "
               f"{tot['in_tokens'] / 1e6:.2f}M | {tot['out_tokens'] / 1e6:.2f}M | **${tot['expected']:.2f}** | "
               f"${tot['uncached']:.2f} | ${tot['worst']:.2f} | ${tot['post_extra']:.3f} | **${tot['cap']:.2f}** |")
    return "\n".join(out), tot


def main():
    rows = [price(r) for r in RUNS]
    text, tot = table(rows)
    print(text)
    if tot["cap"] > CEILING + 1e-9:
        raise SystemExit(f"caps sum to ${tot['cap']:.2f}, over the ${CEILING:.2f} ceiling")
    for r in rows:
        if r["cap"] < r["expected"] * 1.1:
            print(f"warning: {r['run']}'s cap ${r['cap']:.2f} leaves under 10% over its expected ${r['expected']:.2f}")
    with open(os.path.join(HERE, "plan.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"runs": rows, "total": tot}, f, indent=1)


if __name__ == "__main__":
    main()
