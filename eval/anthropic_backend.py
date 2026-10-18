"""The Anthropic Messages API path for eval/run.py: direct calls and Message Batches.

Everything model-facing follows the Claude API docs for Claude Haiku 5.5
(model id `claude-haiku-5-5`):

  * thinking is adaptive and on by default. It is sent explicitly as
    {"type": "adaptive"}, and how much the model thinks is set with
    output_config.effort ("medium" is the model's default, "low" the
    cheap slice). budget_tokens, temperature/top_p/top_k and assistant
    prefill all return a 400 on this model, so none is ever sent;
  * structured outputs go in output_config.format as
    {"type": "json_schema", "schema": ...};
  * the system prompt carries cache_control {"type": "ephemeral"}. Haiku
    5.5 caches prefixes from 512 tokens, so every v6 prompt qualifies.
    In a batch, cache hits are best effort;
  * thinking counts toward max_tokens and is billed as output tokens.

Responses are reshaped into the OpenRouter-like body run.py already parses
(choices[0].message.content, usage.prompt_tokens / completion_tokens /
cost), so run records, score.py and bench_v6.py compare work unchanged.
Cost is computed here from the usage tokens at Haiku 5.5's prices, halved
for batch requests, and stored on every record.
"""

import copy
import json
import os
import time

MODEL = "claude-haiku-5-5"
# USD per token, Claude Haiku 5.5, prompts of 100k tokens or fewer. Output includes thinking.
PRICES = {"in": 0.10e-6, "out": 0.50e-6, "cache_read": 0.01e-6, "cache_write": 0.125e-6}
BATCH_DISCOUNT = 0.5
# Measured by the probe: 8,724 characters of v6 comment input (system + user) billed as
# 4,746 input tokens, 1.84 chars/token, the strict schema's own prompt overhead
# included. The worst case bounds input at chars/1.5 plus a fixed allowance for that
# overhead, so a reservation can't be undercut by the tokenizer.
CHARS_PER_TOKEN_UPPER = 1.5
SCHEMA_OVERHEAD_TOKENS = 2500

# Credentials and endpoints the SDK would otherwise pick up from the environment.
# Only the key read from --key-file may be used.
_ENV_OVERRIDES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "ANTHROPIC_BASE_URL",
                  "ANTHROPIC_FEDERATION_RULE_ID", "ANTHROPIC_IDENTITY_TOKEN", "ANTHROPIC_IDENTITY_TOKEN_FILE")


def client(key, base_url=None):
    import anthropic
    for var in _ENV_OVERRIDES:
        os.environ.pop(var, None)
    kw = {"api_key": key, "max_retries": 4}
    if base_url:
        kw["base_url"] = base_url
    return anthropic.Anthropic(**kw)


def strict_schema(schema):
    """The repo's strict schema in the form structured outputs documents.

    Drops the $schema/title annotations, and rewrites type unions
    ({"type": ["string", "null"], "enum": [..., null]}) as anyOf, which the
    Claude API lists as supported. The meaning is unchanged.
    """
    def walk(n):
        if isinstance(n, list):
            return [walk(x) for x in n]
        if not isinstance(n, dict):
            return n
        n = {k: walk(v) for k, v in n.items() if k not in ("$schema", "title")}
        t = n.get("type")
        if isinstance(t, list) and "null" in t:
            rest = [x for x in t if x != "null"]
            base = {k: v for k, v in n.items() if k != "type"}
            if "enum" in base:
                base["enum"] = [x for x in base["enum"] if x is not None]
            first = {"type": rest[0] if len(rest) == 1 else rest, **base}
            return {"anyOf": [first, {"type": "null"}]}
        return n
    return walk(copy.deepcopy(schema))


def params(system, user, max_tokens, effort, schema=None, cache=True, model=MODEL):
    sys_block = {"type": "text", "text": system}
    if cache:
        sys_block["cache_control"] = {"type": "ephemeral"}
    out = {"effort": effort or "medium"}
    if schema is not None:
        out["format"] = {"type": "json_schema", "schema": strict_schema(schema)}
    return {"model": model, "max_tokens": max_tokens, "system": [sys_block],
            "messages": [{"role": "user", "content": user}],
            "thinking": {"type": "adaptive"}, "output_config": out}


def cost(usage, batch):
    u = usage or {}
    c = ((u.get("input_tokens") or 0) * PRICES["in"]
         + (u.get("cache_creation_input_tokens") or 0) * PRICES["cache_write"]
         + (u.get("cache_read_input_tokens") or 0) * PRICES["cache_read"]
         + (u.get("output_tokens") or 0) * PRICES["out"])
    return c * (BATCH_DISCOUNT if batch else 1.0)


def worst_case(system, user, max_tokens, batch):
    """The most one request can cost: all input billed as a cache write, all of max_tokens out."""
    tin = (len(system) + len(user)) / CHARS_PER_TOKEN_UPPER + SCHEMA_OVERHEAD_TOKENS
    return (tin * PRICES["cache_write"] + max_tokens * PRICES["out"]) * (BATCH_DISCOUNT if batch else 1.0)


def as_body(message, batch):
    """An Anthropic Message (SDK object or dict) as the body run.py parses."""
    m = message.model_dump() if hasattr(message, "model_dump") else message
    text = "".join(b.get("text") or "" for b in m.get("content") or [] if b.get("type") == "text")
    u = m.get("usage") or {}
    thinking = (u.get("output_tokens_details") or {}).get("thinking_tokens")
    return {
        "choices": [{"message": {"content": text}}],
        "provider": "anthropic" + ("-batch" if batch else ""),
        "stop_reason": m.get("stop_reason"),
        "usage": {
            "prompt_tokens": (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                             + (u.get("cache_read_input_tokens") or 0),
            "completion_tokens": u.get("output_tokens"),
            "cost": cost(u, batch),
            "prompt_tokens_details": {"cached_tokens": u.get("cache_read_input_tokens") or 0,
                                      "cache_write_tokens": u.get("cache_creation_input_tokens") or 0},
            "completion_tokens_details": {"reasoning_tokens": thinking},
        },
        "anthropic_usage": u,
    }


def call(cl, p):
    """One direct (non-batch) request. Returns (body, latency, error)."""
    import anthropic
    t0 = time.time()
    try:
        msg = cl.messages.create(**p)
    except anthropic.APIStatusError as e:
        return None, None, f"http {e.status_code}: {str(e)[:300]}"
    except anthropic.APIConnectionError as e:
        return None, None, f"{type(e).__name__}: {e}"
    return as_body(msg, batch=False), time.time() - t0, None


# ---------------------------------------------------------------- batches
def custom_id(n):
    return f"r{n:06d}"            # ^[a-zA-Z0-9_-]{1,64}$; call keys contain ':'


def submit(cl, requests):
    """requests: [(custom_id, params)]. Returns the batch id."""
    b = cl.messages.batches.create(requests=[{"custom_id": cid, "params": p} for cid, p in requests])
    return b.id


def wait(cl, batch_id, poll_seconds, log=print):
    while True:
        b = cl.messages.batches.retrieve(batch_id)
        if b.processing_status == "ended":
            return b
        c = b.request_counts
        log(f"  batch {batch_id}: {b.processing_status}, {c.processing} processing, "
            f"{c.succeeded} succeeded, {c.errored} errored")
        time.sleep(poll_seconds)


def results(cl, batch_id):
    """{custom_id: ("succeeded", body) | ("errored", message, retryable) | ("expired"|"canceled", None)}."""
    out = {}
    for r in cl.messages.batches.results(batch_id):
        res = r.result
        if res.type == "succeeded":
            out[r.custom_id] = ("succeeded", as_body(res.message, batch=True))
        elif res.type == "errored":
            err = res.error.model_dump() if hasattr(res.error, "model_dump") else res.error
            inner = (err or {}).get("error") or {}
            kind = inner.get("type") or "error"
            out[r.custom_id] = ("errored", f"{kind}: {inner.get('message', '')}"[:300],
                                kind != "invalid_request_error")
        else:
            out[r.custom_id] = (res.type, None)
    return out


def batch_seconds(b):
    try:
        return (b.ended_at - b.created_at).total_seconds()
    except Exception:
        return None
