"""A stand-in for OpenRouter's embeddings endpoint, so no test spends money.

FakeOpenRouter replaces embedding._session for the duration of a test. Each
request goes through `handler(payload) -> FakeResponse | Exception`; the
default handler answers like DeepInfra does: deterministic unit vectors
(1,024 dims when `dimensions` is sent, 4,096 otherwise), base64 float32, and a
usage block with the cost at catalog price.
"""

import base64
import hashlib
import json
import math
import os
import random
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import embedding  # noqa: E402


def fake_vector(text, dims):
    """Deterministic per text, so the same input always gives the same vector."""
    rng = random.Random(hashlib.sha256(text.encode("utf-8")).digest())
    v = [rng.gauss(0, 1) for _ in range(dims)]
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def b64(vec):
    return base64.b64encode(struct.pack(f"<{len(vec)}f", *vec)).decode()


def ok_body(payload, provider="DeepInfra", cost=True):
    dims = payload.get("dimensions", 4096)
    texts = payload["input"]
    tokens = sum(max(1, len(t.encode("utf-8")) // 4) for t in texts)
    usage = {"prompt_tokens": tokens, "total_tokens": tokens}
    if cost:
        usage["cost"] = tokens * embedding.PRICE_PER_TOKEN
    return {"object": "list", "model": "Qwen/Qwen3-Embedding-8B", "provider": provider,
            "data": [{"object": "embedding", "index": i,
                      "embedding": b64(fake_vector(t, dims))} for i, t in enumerate(texts)],
            "usage": usage}


class FakeResponse:
    def __init__(self, status_code=200, body=None, text=None):
        self.status_code = status_code
        self._body = body
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    def __init__(self, owner):
        self.owner = owner

    def post(self, url, json=None, timeout=None):
        self.owner.requests.append({"url": url, "payload": json, "timeout": timeout})
        out = self.owner.handler(json)
        if isinstance(out, BaseException):
            raise out
        return out


class FakeOpenRouter:
    """Context manager: patches embedding._session; records every request."""

    def __init__(self, handler=None):
        self.handler = handler or (lambda p: FakeResponse(200, ok_body(p)))
        self.requests = []
        self.session = FakeSession(self)

    def __enter__(self):
        self._orig = embedding._session
        embedding._session = lambda: self.session
        return self

    def __exit__(self, *exc):
        embedding._session = self._orig
        return False

    @property
    def inputs(self):
        return [t for r in self.requests for t in r["payload"]["input"]]
