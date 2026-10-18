"""Qwen3-Embedding-8B through OpenRouter: what a vector means, and how to get one.

Everything that decides whether two vectors are comparable lives here, in one
place: the model, the provider it is pinned to, the dimensions it is cut to,
and the exact text each kind of input is turned into. embed.py stores
document vectors with these; search will embed its query with
`embed_query`, and the two only line up if both go through this module.

What the embedding benchmark (eval/embeddings on its own branch) settled, and
this copies:

- Documents are embedded raw: thread title, a blank line, then the comment
  body (or the thread's selftext, cut to 1,500 characters). No instruction.
- Queries get the model card's instruction prefix. OpenRouter silently
  ignores `input_type` for Qwen, so the prefix is typed into the text.
- The model returns 4,096 dims. The first 1,024, L2-renormalised, scored
  within noise of the full vector on comments, and pgvector's HNSW cannot
  index a halfvec over 4,000 dims anyway.
- DeepInfra and Nebius return measurably different vectors for the same text
  (cosine 0.9976), so every request is pinned to DeepInfra with no fallback.
  The provider is part of MODEL_KEY: moving to another provider is a model
  change, never a silent mix inside one index.

No database code here: the search endpoint will import this without the
pipeline.
"""

import base64
import hashlib
import math
import os
import struct
import threading
import time

import requests

URL = "https://openrouter.ai/api/v1/embeddings"
MODEL = "qwen/qwen3-embedding-8b"
DIMS = 1024
PROVIDER = "deepinfra"
# What `model` holds in the embedding tables. Vectors are only comparable
# within one value: a new model, new dims, new truncation or a new provider
# each get a new key, and are embedded as new rows beside the old ones.
MODEL_KEY = f"{MODEL}@{DIMS}:{PROVIDER}"

# OpenRouter's provider routing. `allow_fallbacks: false` makes an outage at
# DeepInfra an error instead of a quiet switch to a provider whose vectors
# disagree with everything already stored.
ROUTING = {"provider": {"order": [PROVIDER], "allow_fallbacks": False}}

# The benchmark measured `dimensions: 1024` on DeepInfra as identical to
# truncating the 4,096 vector (cosine 1.0), and a live check while building
# this confirmed it. Asking for 1,024 cuts the response to a quarter of the
# bytes. The vector is still truncated and renormalised here, so if a
# provider ever ignored the parameter the stored value would mean the same.
SEND_DIMENSIONS = True

# USD per token, from OpenRouter's catalog ($0.01 per million). Only a
# fallback: the response's own usage.cost is used whenever it is present.
PRICE_PER_TOKEN = 0.01e-6

# Measured on 97k comments and 7.6k threads billed by the benchmark: Qwen
# counts one token per 4.0 to 4.2 UTF-8 bytes of this corpus. Projections use
# that; the spend cap reserves twice as much per request, so even a batch of
# emoji-heavy or non-English text (which runs closer to 1.6 bytes a token)
# cannot slip past it.
BYTES_PER_TOKEN = 4.0
RESERVE_FACTOR = 2.0

# The benchmark's request sizes, which every provider accepted: 128 documents
# per request, and single queries.
DOC_BATCH = 128

ATTEMPTS = 6
TIMEOUT = 120
QUERY_ATTEMPTS = 2
QUERY_TIMEOUT = 10

# Selftext is long-tailed and a thread vector should say what was asked, not
# carry every paragraph of it. The benchmark's cut, ~350 tokens.
THREAD_SELFTEXT_CHARS = 1500

# Written once from the model card's convention before the benchmark ran, and
# never tuned. Changing a word of it changes every query vector, so it is
# pinned by a test.
QUERY_TASK = ("Given a search query for New York City restaurants, retrieve Reddit "
              "comments that recommend or describe places matching it")

# A dedicated key wins, so embeddings can be given their own spending limit
# and can never exhaust the key extraction runs on.
KEY_VARS = ("EMBED_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")


# --- formatting --------------------------------------------------------------

def format_comment(title, body):
    """Thread title + comment body, exactly as the benchmark embedded them.

    No parent comment and no selftext: selftext is shared by every comment in
    a thread and would pull them all toward one point.
    """
    return f"{title or ''}\n\n{body}"


def format_thread(title, selftext):
    """Thread title + the asker's selftext, cut to THREAD_SELFTEXT_CHARS.

    A removed post keeps its title; "[deleted]" is not what the thread was
    about. The empty case still ends in a blank line, because that is the
    string the benchmark embedded.
    """
    st = selftext or ""
    if st in ("[deleted]", "[removed]"):
        st = ""
    return f"{title or ''}\n\n{st[:THREAD_SELFTEXT_CHARS]}"


def format_query(query):
    """The model card's query instruction. Note: no space after `Query:`."""
    return f"Instruct: {QUERY_TASK}\nQuery:{query}"


def input_hash(text):
    """What `input_hash` stores: sha256 of the exact string that was embedded.

    embed.py recomputes the same hash in SQL to find rows whose text has
    changed, so the two must agree byte for byte (tests/test_embed_db.py).
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def estimate_tokens(text):
    return len(text.encode("utf-8")) / BYTES_PER_TOKEN


# --- vectors -----------------------------------------------------------------

def decode(raw):
    """base64 float32 little-endian (what we ask for), or a plain JSON list."""
    if isinstance(raw, str):
        buf = base64.b64decode(raw)
        return list(struct.unpack(f"<{len(buf) // 4}f", buf))
    return [float(x) for x in raw]


def truncate_normalize(vec, dims=DIMS):
    """Keep the first `dims` values and rescale them to unit length.

    Qwen3 is trained so its leading dimensions carry the most meaning; cutting
    leaves a vector that is no longer unit length, and cosine search in an
    index wants it to be. Raises ValueError on anything that cannot be a
    direction: too short, all zeros, or not finite.
    """
    if len(vec) < dims:
        raise ValueError(f"vector has {len(vec)} dims, need {dims}")
    v = vec[:dims]
    norm = math.sqrt(math.fsum(x * x for x in v))
    if not math.isfinite(norm) or norm == 0.0:
        raise ValueError(f"vector norm is {norm}")
    return [x / norm for x in v]


def to_pgvector(vec):
    """Text form pgvector parses for vector and halfvec: '[0.1,-0.2,...]'.

    Seven significant digits is more than halfvec keeps (about three), and
    keeps the statement a third the size of repr().
    """
    return "[" + ",".join(f"{x:.7g}" for x in vec) + "]"


# --- spend -------------------------------------------------------------------

class BudgetExceeded(RuntimeError):
    pass


class Budget:
    """A spend cap that stops before it is passed, not after.

    Every request reserves a pessimistic estimate before it is sent, and is
    refused if what has been spent, plus what is in flight on other threads,
    plus this one would pass the cap. The reservation is then replaced by the
    real charge. An attempt that may have been billed without returning
    anything usable -- a timeout, a dropped connection, a 5xx, a 200 with no
    vectors -- is charged at its estimate: an overstatement, never a silent
    undercount. cap=None tracks spend without limiting it.
    """

    def __init__(self, cap_usd=None):
        self.cap = cap_usd
        self.spent = 0.0
        self.reserved = 0.0
        self.tokens = 0
        self.calls = 0
        self.possibly_billed = 0
        self.unpriced = 0          # successful calls with no reported cost
        self._lock = threading.Lock()

    def reserve(self, est):
        with self._lock:
            if self.cap is not None and self.spent + self.reserved + est > self.cap:
                raise BudgetExceeded(
                    f"spent ${self.spent:.4f} + in flight ${self.reserved:.4f} "
                    f"+ next ${est:.4f} would pass the ${self.cap:.4f} cap")
            self.reserved += est

    def settle(self, est, cost, tokens=None, *, possibly_billed=False, priced=True):
        with self._lock:
            self.reserved -= est
            self.spent += cost
            self.calls += 1
            self.tokens += tokens or 0
            self.possibly_billed += possibly_billed
            self.unpriced += not priced and not possibly_billed

    def release(self, est):
        with self._lock:
            self.reserved -= est


# --- HTTP --------------------------------------------------------------------

class EmbedError(RuntimeError):
    """Anything that stopped a request from producing vectors."""


class InputRejected(EmbedError):
    """The provider refused the inputs themselves (400/413/422).

    Not billed and not worth retrying as is. The caller splits the batch to
    find the one input at fault, so one bad comment never sinks 127 good ones.
    """


class ServiceError(EmbedError):
    """The service, not the input: auth, credit, routing, or retries exhausted.

    A run stops on this instead of stamping every remaining row with the
    same error; the rows stay to-do for the next run.
    """


_tls = threading.local()


def api_key():
    for var in KEY_VARS:
        if os.environ.get(var):
            return os.environ[var]
    raise ServiceError(f"no OpenRouter key: set {' or '.join(KEY_VARS)}")


def api_key_var():
    """Which variable the key would come from, for logs. None if unset."""
    return next((v for v in KEY_VARS if os.environ.get(v)), None)


def _session():
    """One keep-alive Session per thread.

    requests.Session is not safe to share across threads, and reusing the
    connection skips DNS, TCP and TLS on every call after the first -- about
    75-150 ms of a single query's latency.
    """
    s = getattr(_tls, "session", None)
    if s is None:
        s = _tls.session = requests.Session()
        s.headers.update({"Authorization": f"Bearer {api_key()}",
                          "Content-Type": "application/json",
                          "X-Title": "NYCEats embeddings"})
    return s


class _Attempt:
    """One HTTP attempt. `may_have_billed` is false only when the provider
    clearly refused before doing any work."""

    def __init__(self, body=None, error=None, may_have_billed=False,
                 retry=True, rejected=False):
        self.body, self.error = body, error
        self.may_have_billed, self.retry, self.rejected = may_have_billed, retry, rejected


def _post_once(payload, timeout):
    try:
        r = _session().post(URL, json=payload, timeout=timeout)
    except requests.RequestException as e:
        return _Attempt(error=f"{type(e).__name__}: {e}", may_have_billed=True)
    if r.status_code == 200:
        try:
            body = r.json()
        except ValueError:
            return _Attempt(error="200 with an unparseable body", may_have_billed=True)
        if isinstance(body, dict) and body.get("data"):
            return _Attempt(body=body)
        return _Attempt(error=f"200 without vectors: {str(body)[:300]}",
                        may_have_billed=True)
    msg = f"http {r.status_code}: {r.text[:300]}"
    if r.status_code in (400, 413, 422):
        return _Attempt(error=msg, retry=False, rejected=True)
    if r.status_code in (401, 402, 403, 404):
        return _Attempt(error=msg, retry=False)
    return _Attempt(error=msg, may_have_billed=True)


def _cost(body, est):
    """The charge for one successful call, and whether the provider stated it."""
    usage = body.get("usage") or {}
    tokens = usage.get("prompt_tokens") or usage.get("total_tokens")
    if usage.get("cost") is not None:
        return float(usage["cost"]), tokens, True
    if tokens is not None:
        return tokens * PRICE_PER_TOKEN, tokens, False
    return est, tokens, False


def embed_batch(texts, budget, *, attempts=ATTEMPTS, timeout=TIMEOUT, sleep=None):
    """Embed already-formatted texts in one request. Returns one
    (vector, error) pair per text, in order.

    A vector that comes back unusable (zero, NaN, too short) is an error for
    that text alone; everything wrong with the request as a whole raises.
    Retries back off on timeouts, dropped connections, 429 and 5xx; each
    attempt reserves its own estimate, so retries are capped like any other
    spend, and the finally clause frees a reservation an exception left held.
    """
    sleep = sleep or time.sleep
    est = sum(estimate_tokens(t) for t in texts) * RESERVE_FACTOR * PRICE_PER_TOKEN
    payload = {"model": MODEL, "input": list(texts), "encoding_format": "base64", **ROUTING}
    if SEND_DIMENSIONS:
        payload["dimensions"] = DIMS
    held = False
    last = None
    body = None
    try:
        for attempt in range(attempts):
            if attempt:
                sleep(min(2 ** (attempt - 1), 30))
            budget.reserve(est)
            held = True
            a = _post_once(payload, timeout)
            if a.body is not None:
                cost, tokens, priced = _cost(a.body, est)
                budget.settle(est, cost, tokens, priced=priced)
                held = False
                got = provider_of(a.body)
                if got is not None and got != PROVIDER:
                    # Routing ignored the pin. Storing these would mix two
                    # providers' vectors under one key.
                    raise ServiceError(f"served by {got!r}, pinned to {PROVIDER!r}")
                shape = _shape_error(a.body["data"])
                if shape:
                    # Paid for and settled above; the rest of the run stops
                    # cleanly rather than crashing on a field it expected.
                    raise ServiceError(f"malformed response: {shape}")
                if len(a.body["data"]) == len(texts):
                    body = a.body
                    break
                last = f"asked for {len(texts)} vectors, got {len(a.body['data'])}"
                continue
            if a.may_have_billed:
                budget.settle(est, est, possibly_billed=True)
            else:
                budget.release(est)
            held = False
            last = a.error
            if a.rejected:
                raise InputRejected(a.error)
            if not a.retry:
                raise ServiceError(a.error)
        else:
            raise ServiceError(f"failed after {attempts} attempts: {last}")
    finally:
        if held:
            budget.release(est)

    out = []
    for d in sorted(body["data"], key=lambda d: d["index"]):
        try:
            out.append((truncate_normalize(decode(d["embedding"])), None))
        except (ValueError, struct.error, TypeError, KeyError) as e:
            out.append((None, f"unusable vector: {e}"))
    return out


def _shape_error(data):
    """Why `data` is not a list of {index, embedding} covering 0..n-1, or None.

    A count that is merely short is not a shape error; that is retried.
    """
    if not isinstance(data, list):
        return f"data is a {type(data).__name__}, not a list"
    for d in data:
        if not isinstance(d, dict) or "embedding" not in d:
            return f"item without an embedding: {str(d)[:100]}"
        if not isinstance(d.get("index"), int) or isinstance(d.get("index"), bool):
            return f"item without an integer index: {str(d)[:100]}"
    idx = sorted(d["index"] for d in data)
    if idx != list(range(len(data))):
        return f"indexes are not 0..{len(data) - 1}"
    return None


def provider_of(body):
    p = body.get("provider")
    return p.strip().lower() if isinstance(p, str) and p.strip() else None


def embed_query(query, budget=None):
    """Embed one search query: same model, provider, cut and normalisation as
    the stored documents, plus the query instruction, over the same
    keep-alive Session. Sync on purpose; endpoints here are `def`.

    Fewer attempts and a short timeout than the batch path: a search waiting
    on the third retry is worse than one that fails and says so.
    """
    q = (query or "").strip()
    if not q:
        raise ValueError("empty query")
    [(vec, err)] = embed_batch([format_query(q)], budget or Budget(),
                               attempts=QUERY_ATTEMPTS, timeout=QUERY_TIMEOUT)
    if err:
        raise EmbedError(err)
    return vec
