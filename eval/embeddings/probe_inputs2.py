"""Second probe: explain what the first one found.

Round one showed input_type changes the vector for Voyage and Gemini (and,
slightly, Qwen), that Gemini's token count grows under input_type=query, and
that Qwen requests can land on different providers. This checks:

- Gemini: is input_type=query the same as typing Google's documented prefix
  "task: search result | query: ..." ourselves? And input_type=document vs
  "title: none | text: ..."?
- Qwen: is input_type=query the same as the model card's instruction prefix?
  Is the small change provider noise? Does pinning the provider fix it, and
  does dimensions=1024 equal truncating the 4096 vector on the same provider?
- Voyage: is input_type=query the same as Voyage's documented query prompt?
"""

import json

import numpy as np

from common import DATA
from openrouter import ledger, raw_embed

TEXTS = [
    "date night",
    "Best soup dumplings in Flushing — Nan Xiang, get the crab ones.",
    "Don't bring a date here, it's deafening and the service was rude.",
]
QWEN_WEB = "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:"


def cos(a, b):
    sims = []
    for x, y in zip(a, b):
        d = min(len(x), len(y))
        x, y = x[:d] / np.linalg.norm(x[:d]), y[:d] / np.linalg.norm(y[:d])
        sims.append(float(x @ y))
    return round(float(np.mean(sims)), 6)


def call(model, texts, extra=None):
    vecs, body, _ = raw_embed(model, texts, extra, "probe2")
    return vecs, body.get("provider"), body["usage"]["prompt_tokens"]


def main():
    out = {}
    g = "google/gemini-embedding-2"
    q_api, p1, t1 = call(g, TEXTS, {"input_type": "query"})
    q_man, p2, t2 = call(g, ["task: search result | query: " + t for t in TEXTS])
    d_api, _, t3 = call(g, TEXTS, {"input_type": "document"})
    d_man, _, t4 = call(g, ["title: none | text: " + t for t in TEXTS])
    out["gemini"] = {"query_api_vs_manual_prefix": cos(q_api, q_man), "tokens": [t1, t2],
                     "doc_api_vs_manual_prefix": cos(d_api, d_man), "doc_tokens": [t3, t4]}

    q = "qwen/qwen3-embedding-8b"
    pin = {"provider": {"order": ["deepinfra"], "allow_fallbacks": False}}
    base, pb, _ = call(q, TEXTS, pin)
    it, pi, _ = call(q, TEXTS, {**pin, "input_type": "query"})
    man, pm, _ = call(q, [QWEN_WEB + t for t in TEXTS], pin)
    d1024, pd, _ = call(q, TEXTS, {**pin, "dimensions": 1024})
    neb, pn, _ = call(q, TEXTS, {"provider": {"order": ["nebius"], "allow_fallbacks": False}})
    out["qwen"] = {"providers": [pb, pi, pm, pd, pn],
                   "input_type_query_vs_none": cos(base, it),
                   "input_type_query_vs_manual_instruct": cos(it, man),
                   "manual_instruct_vs_none": cos(base, man),
                   "dimensions1024_vs_truncated4096_same_provider": cos(base, d1024),
                   "nebius_vs_deepinfra_same_input": cos(base, neb)}

    v = "voyageai/voyage-4-large"
    vq, _, _ = call(v, TEXTS, {"input_type": "query"})
    vm, _, _ = call(v, ["Represent the query for retrieving supporting documents: " + t for t in TEXTS])
    vd, _, _ = call(v, TEXTS, {"input_type": "document"})
    vdm, _, _ = call(v, ["Represent the document for retrieval: " + t for t in TEXTS])
    out["voyage"] = {"query_api_vs_manual_prompt": cos(vq, vm),
                     "doc_api_vs_manual_prompt": cos(vd, vdm)}

    print(json.dumps(out, indent=2))
    (DATA / "probe2.json").write_text(json.dumps(out, indent=2))
    print("ledger total $%.6f" % ledger().spent)


if __name__ == "__main__":
    main()
