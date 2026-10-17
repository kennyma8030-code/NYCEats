"""Find out, by real calls, which query/document settings OpenRouter passes
through to each provider and which it silently drops.

The test for "passed through" is whether the vector changes. Each model embeds
the same three texts with no setting, then again with no setting (the noise
floor: some providers are not bit-for-bit deterministic), then with each
candidate setting. A setting whose vectors match the baseline as closely as the
repeat does was ignored. Dimension settings are checked by the returned length,
and for Matryoshka models by whether the short vector equals the long one
truncated and renormalised, which decides whether a cheaper variant can be
scored without a second embedding pass.

Costs a fraction of a cent. Every call goes through the same ledger and cap as
the main run. Output: data/probe.json and probe_findings.md.
"""

import json

import numpy as np

from common import DATA, HERE
from openrouter import ledger, raw_embed

TEXTS = [
    "date night",
    "Best soup dumplings in Flushing — Nan Xiang, get the crab ones.",
    "Don't bring a date here, it's deafening and the service was rude.",
]

TESTS = {
    "voyageai/voyage-4-large": [
        {"input_type": "query"},
        {"input_type": "document"},
        {"dimensions": 512},
        {"output_dimension": 512},
    ],
    "qwen/qwen3-embedding-8b": [
        {"input_type": "query"},
        {"dimensions": 1024},
    ],
    "openai/text-embedding-3-large": [
        {"dimensions": 1024},
        {"input_type": "query"},
    ],
    "google/gemini-embedding-2": [
        {"input_type": "query"},
        {"task_type": "RETRIEVAL_QUERY"},
        {"dimensions": 768},
        {"output_dimensionality": 768},
    ],
    "openai/text-embedding-3-small": [
        {"input_type": "query"},
    ],
}


def unit(v):
    return v / np.linalg.norm(v)


def compare(base, other):
    """Mean cosine of the matching vectors, comparing on the shared prefix
    when lengths differ (truncate-and-renormalise the longer one)."""
    sims = []
    for a, b in zip(base, other):
        d = min(len(a), len(b))
        sims.append(float(unit(a[:d]) @ unit(b[:d])))
    return float(np.mean(sims))


def main():
    out = {}
    for model, tests in TESTS.items():
        base, body, dt = raw_embed(model, TEXTS, None, "probe")
        rep, _, _ = raw_embed(model, TEXTS, None, "probe")
        res = {"dims": len(base[0]), "norm": float(np.linalg.norm(base[0])),
               "usage": body.get("usage"), "provider": body.get("provider"),
               "seconds": round(dt, 3),
               "repeat_cos": compare(base, rep), "settings": []}
        print(model, "dims", res["dims"], "norm %.4f" % res["norm"], "usage", body.get("usage"),
              "provider", body.get("provider"), "repeat cos %.6f" % res["repeat_cos"])
        for extra in tests:
            try:
                vecs, b2, _ = raw_embed(model, TEXTS, extra, "probe")
                r = {"extra": extra, "dims": len(vecs[0]), "cos_vs_base": compare(base, vecs),
                     "norm": float(np.linalg.norm(vecs[0]))}
            except Exception as e:
                r = {"extra": extra, "error": str(e)[:300]}
            res["settings"].append(r)
            print("   ", json.dumps(r))
        out[model] = res
    (DATA / "probe.json").write_text(json.dumps(out, indent=2))
    print("ledger total $%.6f" % ledger().spent)


if __name__ == "__main__":
    main()
