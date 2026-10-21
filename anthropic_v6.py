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
    anyway: AmbiguousSubmit, which the caller must never resubmit;
  * reading a batch back (status, results, the list) is safe to repeat, so
    any failure there short of a 404 or another 4xx is retried for several
    minutes before it becomes TransientAPIError (GET_WAITS).

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
OUTPUT_SCHEMA_THREAD = strict_schema(prompt_v6.SCHEMA_THREAD)


def params(system, user, effort=None, max_tokens=None, schema=None):
    """One request's parameters: the benchmark's params() at effort medium,
    with the schema and the cache marker it ran with.

    Comment and post mode never pass the keywords, so what they send is
    exactly the benchmark's. Thread mode passes its own effort, its 32k
    max_tokens and the thread schema (an integer "id" in every mention)."""
    return {"model": prompt_v6.MODEL, "max_tokens": max_tokens or prompt_v6.MAX_TOKENS,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort or prompt_v6.EFFORT,
                              "format": {"type": "json_schema", "schema": schema or OUTPUT_SCHEMA}}}


def cost(usage, batch):
    u = usage or {}
    c = ((u.get("input_tokens") or 0) * PRICES["in"]
         + (u.get("cache_creation_input_tokens") or 0) * PRICES["cache_write"]
         + (u.get("cache_read_input_tokens") or 0) * PRICES["cache_read"]
         + (u.get("output_tokens") or 0) * PRICES["out"])
    return c * (BATCH_DISCOUNT if batch else 1.0)


def worst_case(system, user, batch, max_tokens=None):
    """The most one request can cost: all input billed as a cache write, all of max_tokens out."""
    tin = (len(system) + len(user)) / CHARS_PER_TOKEN_UPPER + SCHEMA_OVERHEAD_TOKENS
    return (tin * PRICES["cache_write"] + (max_tokens or prompt_v6.MAX_TOKENS) * PRICES["out"]) \
        * (BATCH_DISCOUNT if batch else 1.0)


def estimate(system, user, batch, cached, output_tokens=None):
    """A typical request's cost, for dry runs: measured chars/token, the
    benchmark's assumed output (or the caller's), and the system prompt
    either all cache reads or all fresh input."""
    t_sys = len(system) / CHARS_PER_TOKEN + SCHEMA_OVERHEAD_TOKENS
    t_user = len(user) / CHARS_PER_TOKEN
    c = (t_sys * (PRICES["cache_read"] if cached else PRICES["in"]) + t_user * PRICES["in"]
         + (ASSUMED_OUTPUT_TOKENS if output_tokens is None else output_tokens) * PRICES["out"])
    return c * (BATCH_DISCOUNT if batch else 1.0)


# Thread mode's expected output, for dry runs and cost plans: a + b * items
# tokens a chunk, thinking included. Fitted to the benchmark's round-1 thread
# runs on 361 chunks of v2 comments (medium with 32k: 2,640 + 490 an item;
# low: 2,250 + 345), then raised by the 12% round 4 added to comment mode's
# output at medium (low's did not grow). Those chunks were picked for
# diagnostic comments, 1.1 places a comment, so the backlog's typical thread
# should come in under this. The post as item [0] counts as an item; post
# mode measured about 700 output tokens a post in production.
THREAD_OUTPUT = {"medium": (2950, 550), "low": (2250, 345)}


def thread_output_tokens(effort, items, max_tokens=None):
    a, b = THREAD_OUTPUT[effort]
    return min(a + b * items, max_tokens or prompt_v6.THREAD_MAX_TOKENS)


def _dump(message):
    return message.model_dump() if hasattr(message, "model_dump") else message


def usage_of(message):
    """The usage block as a dict, without the fields the API left empty."""
    return {k: v for k, v in ((_dump(message) or {}).get("usage") or {}).items() if v is not None}


def parse(message, max_tokens=None):
    """The extraction in an Anthropic message, as {"mentions": [...]}, or ItemError.

    stop_reason is checked before the text: a max_tokens stop is cut-off JSON,
    and a refusal has none, and neither may be stored as "no mentions".
    """
    m = _dump(message) or {}
    stop = m.get("stop_reason")
    if stop == "max_tokens":
        raise ItemError("max_tokens", f"stopped at {max_tokens or prompt_v6.MAX_TOKENS} output tokens")
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


# Reading a batch (its status, its results, the key's batch list) changes
# nothing on the API's side, so it is safe to repeat. A backfill polls for a
# day or more, and one 529, a reset connection or a stream cut halfway through
# a results file must not end it: these are retried for several minutes
# (GET_WAITS adds up to about seven) before TransientAPIError stops the run.
GET_WAITS = (5, 10, 20, 40, 60, 60, 60, 60, 60, 60)


def _stream_errors():
    """What the SDK's HTTP library raises while a body is being read (a
    dropped connection, a truncated stream), which the SDK does not wrap."""
    # A results line cut mid-JSON or mid-character, not every ValueError: a
    # ValueError from a bug in our own parsing must surface, not be retried.
    out = [OSError, json.JSONDecodeError, UnicodeDecodeError]
    for name in ("httpx2", "httpx"):
        try:
            mod = __import__(name)
        except ImportError:
            continue
        out += [mod.HTTPError, mod.StreamError]
    return tuple(out)


def _get(what, fn, sleep=None, log=print):
    """fn() with retries, for a read that is safe to repeat. NotFound and
    FatalAPIError are facts about the batch or the request and are raised at
    once. Everything else is retried, then raised as TransientAPIError: 429,
    5xx, connection and stream failures, and the SDK's own errors (a missing
    results_url, say)."""
    import anthropic
    sleep = sleep or time.sleep
    waits = GET_WAITS
    stream = _stream_errors()
    last = cause = None
    for attempt in range(len(waits) + 1):
        wait = None
        try:
            return fn()
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            err = _batch_errors(what, e)
            if not isinstance(err, TransientAPIError):
                raise err from e
            last, cause = err, e
            if isinstance(e, anthropic.APIStatusError):
                wait = _retry_after(e)
        except (anthropic.AnthropicError, *stream) as e:
            last, cause = TransientAPIError(f"{what}: {type(e).__name__}: {e}"), e
        if attempt == len(waits):
            break
        wait = min(MAX_WAIT, wait if wait is not None else waits[attempt] + random.uniform(0, 1))
        log(f"  {last}, retrying in {wait:.0f}s")
        sleep(wait)
    raise TransientAPIError(f"gave up after {len(waits) + 1} attempts: {last}") from cause


def retrieve(cl, batch_id, sleep=None, log=print):
    return _get(f"batch {batch_id}", lambda: cl.messages.batches.retrieve(batch_id), sleep, log)


def recent_batches(cl, until=None, limit=100, max_pages=50, sleep=None, log=print):
    """The key's batches, newest first, back to the first one created before
    `until` (or to the end of the list), at most max_pages pages.

    Returns (batches, covered). covered says the listing reached a batch older
    than `until`, or the end of the list, so a batch created after `until`
    that is not in it does not exist. A pending row may only be settled as
    "none" on a covered listing."""
    out, after = [], None
    for _ in range(max_pages):
        kw = {"limit": limit} if after is None else {"limit": limit, "after_id": after}
        page = _get("batch list", lambda: cl.messages.batches.list(**kw), sleep, log)
        data = list(page.data)
        out += data
        if until is not None and any(b.created_at < until for b in data):
            return out, True
        if not data or not getattr(page, "has_more", False):
            return out, True
        after = getattr(page, "last_id", None) or data[-1].id
    return out, False


def results(cl, batch_id, sleep=None, log=print):
    """{custom_id: ("succeeded", message) | ("errored", error_type, message) | ("expired"|"canceled",)}.

    Results arrive in any order; they are keyed by custom_id, which is the
    item id itself. The whole file is read inside the retry, so a stream cut
    halfway is read again from the start, never half-used.
    """
    def read():
        out = {}
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
        return out
    return _get(f"batch {batch_id} results", read, sleep, log)
