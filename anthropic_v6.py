"""The Anthropic Messages API path for v6 extraction: direct calls and Message Batches.

Every model-facing setting is the benchmark's (extraction-v6:
eval/anthropic_backend.py, run as eval/bench_v6.py steps o and p), so what
production sends is what the Opus review measured:

  * model claude-haiku-5-5, max_tokens 16,000 (thinking counts toward it);
  * thinking {"type": "adaptive"}, depth set by output_config.effort "medium".
    No temperature, top_p, top_k, budget_tokens or prefill: Haiku 5.5
    rejects them;
  * output_config.format is the strict json_schema, with nullable type unions
    rewritten as anyOf (strict_schema), which is the form structured outputs
    documents;
  * the system prompt carries cache_control {"type": "ephemeral"}.

The benchmark's code validators are not used: at medium effort they were
measured to add nothing.

Failures are sorted three ways, and the callers act on the sort:
  * a 200 that is no answer (stop_reason max_tokens or refusal, JSON that does
    not parse or has no mentions list) is the item's problem: ItemError, with
    a code that goes into extraction_state.extract_error;
  * a 4xx other than 429 is about the request or the account (a bad
    parameter, a revoked key, no credit), so every item would get it:
    FatalAPIError, with the response body, and the pass stops without
    marking anything;
  * 429, 5xx (529 overloaded included) and connection failures are
    transient: they are retried with backoff, and if they outlast it,
    TransientAPIError stops the pass, again without marking anything. A
    timeout may have been billed, so its retry needs a fresh reservation
    under the cap (call's retry_ok), or the request is given up (CapReached);
  * a batch submission that times out or gets a 5xx may have been accepted
    anyway: AmbiguousSubmit, which the caller must never resubmit.

Cost is computed from the usage block at Haiku 5.5's prices: $0.10/MTok in,
$0.50 out (thinking included), $0.01 cache reads, $0.125 cache writes, all
halved in a batch.
"""

import copy
import json
import os
import random
import time

import prompt_v6

KEY_VAR = "EXTRACT_ANTHROPIC_API_KEY"
# USD per token, Claude Haiku 5.5, prompts of 100k tokens or fewer.
PRICES = {"in": 0.10e-6, "out": 0.50e-6, "cache_read": 0.01e-6, "cache_write": 0.125e-6}
BATCH_DISCOUNT = 0.5
# The benchmark's probe billed 8,724 characters of v6 input as 4,746 tokens,
# 1.84 chars/token with the strict schema's own overhead included. The worst
# case bounds input at chars/1.5 plus a fixed allowance for that overhead, so
# a reservation can't be undercut by the tokenizer.
CHARS_PER_TOKEN_UPPER = 1.5
SCHEMA_OVERHEAD_TOKENS = 2500
# For estimates only (dry runs): the measured rate, and the output the
# benchmark planned round 4 at medium with (900 thinking + 300 visible).
CHARS_PER_TOKEN = 1.84
ASSUMED_OUTPUT_TOKENS = 1200

# Credentials and endpoints the SDK would otherwise pick up from the
# environment. Extraction uses EXTRACT_ANTHROPIC_API_KEY and nothing else, so
# a key meant for something else can never be billed by accident.
_ENV_OVERRIDES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "ANTHROPIC_BASE_URL",
                  "ANTHROPIC_FEDERATION_RULE_ID", "ANTHROPIC_IDENTITY_TOKEN", "ANTHROPIC_IDENTITY_TOKEN_FILE")

# Direct calls: how long one may take, and how often a transient failure is
# retried before the pass gives up and leaves the rest for the next one.
TIMEOUT = 300
ATTEMPTS = 6
MAX_WAIT = 120


class ItemError(Exception):
    """The API answered, but not with a usable extraction. Charged, recorded on the item."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class FatalAPIError(Exception):
    """A request-level refusal (4xx other than 429). Stop the pass; mark nothing."""


class CapReached(Exception):
    """A retry after a possibly-billed attempt would not fit under the spend cap."""


class AmbiguousSubmit(Exception):
    """A batch submission whose outcome is unknown (timeout, dropped connection,
    5xx): the batch may exist and be billing. Never resubmit; resolve the
    pending row first (extract_v6.py --resolve-pending)."""


class NotFound(Exception):
    """The API has no such batch for this key (404): expired past retention,
    or made under another key."""


class TransientAPIError(Exception):
    """Rate limits, overload or the network outlasted the backoff. Stop the pass; mark nothing."""


def api_key():
    return os.environ.get(KEY_VAR) or None


def client(key, base_url=None):
    """The SDK client, with its own retries off: call() retries, so it can
    count what each attempt may have cost."""
    import anthropic
    for var in _ENV_OVERRIDES:
        os.environ.pop(var, None)
    kw = {"api_key": key, "max_retries": 0, "timeout": TIMEOUT}
    if base_url:
        kw["base_url"] = base_url
    return anthropic.Anthropic(**kw)


def strict_schema(schema):
    """The repo's strict schema in the form structured outputs documents.

    Verbatim from the benchmark's anthropic_backend.strict_schema: drops the
    $schema/title annotations, and rewrites type unions
    ({"type": ["string", "null"], "enum": [..., null]}) as anyOf. The meaning
    is unchanged.
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


OUTPUT_SCHEMA = strict_schema(prompt_v6.SCHEMA)


def params(system, user):
    """One request's parameters: the benchmark's params() at effort medium,
    with the schema and the cache marker it ran with."""
    return {"model": prompt_v6.MODEL, "max_tokens": prompt_v6.MAX_TOKENS,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": prompt_v6.EFFORT,
                              "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}}}


def cost(usage, batch):
    u = usage or {}
    c = ((u.get("input_tokens") or 0) * PRICES["in"]
         + (u.get("cache_creation_input_tokens") or 0) * PRICES["cache_write"]
         + (u.get("cache_read_input_tokens") or 0) * PRICES["cache_read"]
         + (u.get("output_tokens") or 0) * PRICES["out"])
    return c * (BATCH_DISCOUNT if batch else 1.0)


def worst_case(system, user, batch):
    """The most one request can cost: all input billed as a cache write, all of max_tokens out."""
    tin = (len(system) + len(user)) / CHARS_PER_TOKEN_UPPER + SCHEMA_OVERHEAD_TOKENS
    return (tin * PRICES["cache_write"] + prompt_v6.MAX_TOKENS * PRICES["out"]) \
        * (BATCH_DISCOUNT if batch else 1.0)


def estimate(system, user, batch, cached):
    """A typical request's cost, for dry runs: measured chars/token, the
    benchmark's assumed output, and the system prompt either all cache reads
    or all fresh input."""
    t_sys = len(system) / CHARS_PER_TOKEN + SCHEMA_OVERHEAD_TOKENS
    t_user = len(user) / CHARS_PER_TOKEN
    c = (t_sys * (PRICES["cache_read"] if cached else PRICES["in"]) + t_user * PRICES["in"]
         + ASSUMED_OUTPUT_TOKENS * PRICES["out"])
    return c * (BATCH_DISCOUNT if batch else 1.0)


def _dump(message):
    return message.model_dump() if hasattr(message, "model_dump") else message


def usage_of(message):
    """The usage block as a dict, without the fields the API left empty."""
    return {k: v for k, v in ((_dump(message) or {}).get("usage") or {}).items() if v is not None}


def parse(message):
    """The extraction in an Anthropic message, as {"mentions": [...]}, or ItemError.

    stop_reason is checked before the text: a max_tokens stop is cut-off JSON,
    and a refusal has none, and neither may be stored as "no mentions".
    """
    m = _dump(message) or {}
    stop = m.get("stop_reason")
    if stop == "max_tokens":
        raise ItemError("max_tokens", f"stopped at {prompt_v6.MAX_TOKENS} output tokens")
    if stop == "refusal":
        details = m.get("stop_details") or {}
        raise ItemError("refusal", str(details.get("category") or ""))
    if stop not in ("end_turn", None):
        raise ItemError("stop_" + str(stop))
    text = "".join(b.get("text") or "" for b in m.get("content") or [] if b.get("type") == "text")
    try:
        obj = json.loads(text)
    except (TypeError, ValueError) as e:
        raise ItemError("invalid_json", f"{type(e).__name__}: {e}"[:200])
    if not isinstance(obj, dict) or not isinstance(obj.get("mentions"), list) \
            or not all(isinstance(x, dict) for x in obj["mentions"]):
        raise ItemError("invalid_json", "no mentions list")
    return obj


def _body(e):
    """What the API said, for the log: the parsed error body, else the raw text."""
    body = getattr(e, "body", None)
    if body is None:
        try:
            body = e.response.text
        except Exception:
            body = str(e)
    return json.dumps(body)[:2000] if not isinstance(body, str) else body[:2000]


def _retry_after(e):
    try:
        return float(e.response.headers.get("retry-after"))
    except Exception:
        return None


def call(cl, p, attempts=None, sleep=None, log=print, retry_ok=None):
    """One direct request. Returns the Message (SDK object); raises FatalAPIError,
    TransientAPIError or CapReached. ItemError is the caller's: parse() the result.

    A timeout or a dropped connection may have been billed with nothing to
    show for it. Before retrying after one, retry_ok() is asked: the caller
    charges the lost attempt and reserves the next one, and if that does not
    fit under the cap it returns False and the request is given up
    (CapReached). A 429 or 5xx answer was not billed, so it is retried
    without asking.
    """
    import anthropic
    attempts = attempts or ATTEMPTS
    sleep = sleep or time.sleep
    last = None
    for attempt in range(attempts):
        billed = False
        try:
            return cl.messages.create(**p)
        except anthropic.APIStatusError as e:
            status = e.status_code
            if status != 429 and status < 500:
                log(f"  anthropic {status}: {_body(e)}")
                raise FatalAPIError(f"http {status}: {_body(e)[:500]}") from e
            last = f"http {status}"
            wait = _retry_after(e)
        except anthropic.APIConnectionError as e:          # APITimeoutError included
            last = f"{type(e).__name__}: {e}"
            wait = None
            billed = True
        if attempt == attempts - 1:
            break
        if billed and retry_ok is not None and not retry_ok():
            raise CapReached(f"no room under the cap to retry after {last}")
        wait = min(MAX_WAIT, wait if wait is not None else 5 * 2 ** attempt + random.uniform(0, 1))
        log(f"  anthropic {last}, retrying in {wait:.0f}s")
        sleep(wait)
    e = TransientAPIError(f"gave up after {attempts} attempts: {last}")
    e.maybe_billed = billed          # the last attempt timed out: charge it
    raise e


# ---------------------------------------------------------------- batches
def _batch_errors(what, e):
    """Map an SDK error on a batch endpoint to ours. 404 is NotFound: the batch
    is gone or belongs to another key, which is a fact about that batch, not
    about the run."""
    import anthropic
    if isinstance(e, anthropic.APIStatusError):
        if e.status_code == 404:
            return NotFound(f"{what}: http 404: {_body(e)[:300]}")
        if e.status_code != 429 and e.status_code < 500:
            return FatalAPIError(f"{what}: http {e.status_code}: {_body(e)[:500]}")
        return TransientAPIError(f"{what}: http {e.status_code}")
    return TransientAPIError(f"{what}: {type(e).__name__}: {e}")


def submit(cl, requests):
    """requests: [(custom_id, params)]. Returns the batch id.

    Three outcomes the caller must keep apart:
      * a 4xx other than 429 is a refusal of the whole batch (too large, a bad
        parameter), so nothing was created: FatalAPIError;
      * a 429 is a refusal too, nothing created: TransientAPIError;
      * a timeout, a dropped connection or a 5xx may come after the API
        accepted the batch, which then runs and bills: AmbiguousSubmit. The
        caller keeps its pending row and stops; resubmitting could pay twice.
    """
    import anthropic
    try:
        b = cl.messages.batches.create(requests=[{"custom_id": cid, "params": p} for cid, p in requests])
    except anthropic.APIStatusError as e:
        if e.status_code == 429:
            raise TransientAPIError("batch submit http 429") from e
        if e.status_code < 500:
            raise FatalAPIError(f"batch submit http {e.status_code}: {_body(e)[:500]}") from e
        raise AmbiguousSubmit(f"batch submit http {e.status_code}: {_body(e)[:300]}") from e
    except anthropic.APIConnectionError as e:
        raise AmbiguousSubmit(f"batch submit: {type(e).__name__}: {e}") from e
    return b.id


def retrieve(cl, batch_id):
    import anthropic
    try:
        return cl.messages.batches.retrieve(batch_id)
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        raise _batch_errors(f"batch {batch_id}", e) from e


def recent_batches(cl, limit=100):
    """The key's most recent batches (newest first), for matching a pending row."""
    import anthropic
    try:
        page = cl.messages.batches.list(limit=limit)
        return list(page.data)
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        raise _batch_errors("batch list", e) from e


def results(cl, batch_id):
    """{custom_id: ("succeeded", message) | ("errored", error_type, message) | ("expired"|"canceled",)}.

    Results arrive in any order; they are keyed by custom_id, which is the
    item id itself.
    """
    import anthropic
    out = {}
    try:
        for r in cl.messages.batches.results(batch_id):
            res = r.result
            if res.type == "succeeded":
                out[r.custom_id] = ("succeeded", res.message)
            elif res.type == "errored":
                err = _dump(res.error) or {}
                inner = err.get("error") or {}
                out[r.custom_id] = ("errored", inner.get("type") or "error",
                                    str(inner.get("message") or "")[:300])
            else:
                out[r.custom_id] = (res.type,)
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        raise _batch_errors(f"batch {batch_id} results", e) from e
    return out
