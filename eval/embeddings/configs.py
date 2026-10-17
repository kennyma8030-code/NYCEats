"""How each model is asked to embed a query and a document.

Every model gets its provider's recommended query/document handling, as far as
OpenRouter lets it through. What passes through was established by real calls
(probe_inputs.py, probe_inputs2.py); see RESULTS.md for the numbers:

- Voyage: OpenRouter forwards `input_type` (query/document), and the vectors
  equal Voyage's documented prompts typed by hand. Used.
- Gemini Embedding 2: Google's `task_type` is not supported by this model and
  OpenRouter drops it. OpenRouter's `input_type: query` adds exactly Google's
  "task: search result | query: " prefix; its `input_type: document` adds
  something else (2 tokens, not Google's documented "title: ... | text: ...").
  So both sides are formatted by hand, per Google's docs, which also lets the
  thread title fill Google's `title:` slot.
- Qwen3: `input_type` is silently ignored. The model card's convention is an
  instruction prefix on queries only, typed by hand. Requests are pinned to one
  provider, because DeepInfra and Nebius return measurably different vectors
  for the same text (cosine 0.9976) and a corpus must not mix them.
- OpenAI: symmetric models, no query/document distinction; `input_type` is
  ignored. `dimensions=1024` on 3-large equals truncating the 3072 vector and
  renormalising (cosine 0.99999998), so the 1024 variant is scored from the
  3072 vectors at no extra cost. The same holds for Qwen (1.0 at 1024 on the
  same provider) and Gemini (0.99999996 at 768).
"""

import json
from dataclasses import dataclass, field

QWEN_TASK = ("Given a search query for New York City restaurants, retrieve Reddit "
             "comments that recommend or describe places matching it")


def plain_doc(title, body):
    return f"{title}\n\n{body}"


@dataclass
class EmbedConfig:
    name: str
    model: str
    extra: dict = field(default_factory=dict)

    @property
    def cache_key(self):
        return self.model + "|" + json.dumps(self.extra, sort_keys=True)


@dataclass
class Model:
    name: str           # short system name used in tables
    model: str          # OpenRouter id
    dims: int           # native dims as stored
    doc_cfg: EmbedConfig
    query_cfg: EmbedConfig
    fmt_doc: callable = plain_doc
    fmt_query: callable = lambda q: q
    variants: dict = field(default_factory=dict)  # name -> truncated dims


def _cfg(name, model, extra=None):
    return EmbedConfig(name, model, extra or {})


QWEN_PIN = {"provider": {"order": ["deepinfra"], "allow_fallbacks": False}}

MODELS = [
    Model("voyage-4-large", "voyageai/voyage-4-large", 1024,
          _cfg("voyage-4-large/doc", "voyageai/voyage-4-large", {"input_type": "document"}),
          _cfg("voyage-4-large/query", "voyageai/voyage-4-large", {"input_type": "query"})),
    Model("qwen3-8b", "qwen/qwen3-embedding-8b", 4096,
          _cfg("qwen3-8b/doc", "qwen/qwen3-embedding-8b", QWEN_PIN),
          _cfg("qwen3-8b/query", "qwen/qwen3-embedding-8b", QWEN_PIN),
          fmt_query=lambda q: f"Instruct: {QWEN_TASK}\nQuery:{q}",
          variants={"qwen3-8b@1024": 1024}),
    Model("oai-3-large", "openai/text-embedding-3-large", 3072,
          _cfg("oai-3-large", "openai/text-embedding-3-large"),
          _cfg("oai-3-large", "openai/text-embedding-3-large"),
          variants={"oai-3-large@1024": 1024}),
    Model("gemini-2", "google/gemini-embedding-2", 3072,
          _cfg("gemini-2", "google/gemini-embedding-2"),
          _cfg("gemini-2", "google/gemini-embedding-2"),
          fmt_doc=lambda title, body: f"title: {title or 'none'} | text: {body}",
          fmt_query=lambda q: f"task: search result | query: {q}",
          variants={"gemini-2@1024": 1024}),
    Model("oai-3-small", "openai/text-embedding-3-small", 1536,
          _cfg("oai-3-small", "openai/text-embedding-3-small"),
          _cfg("oai-3-small", "openai/text-embedding-3-small")),
]

BY_NAME = {m.name: m for m in MODELS}


def dense_systems():
    """Every dense system scored: each model at native dims plus its
    truncated variants, as (system name, model, dims)."""
    out = []
    for m in MODELS:
        out.append((m.name, m, m.dims))
        for vname, d in m.variants.items():
            out.append((vname, m, d))
    return out
