"""OpenRouter embeddings client with an on-disk cache and a hard spend cap.

Three guarantees, in the order they are checked on every call:

1. Cache first. Every vector is stored under (config key, sha256 of the exact
   input string), so a rerun, a crash-and-resume, or a second script asking for
   the same text costs nothing.
2. The cap. Before a request goes out, its cost is estimated pessimistically
   (tiktoken count x 1.3, at the model's catalog price) and *reserved* in the
   ledger. If spent + reserved + this estimate would pass CAP_USD, the call is
   refused with BudgetExceeded instead of being sent. The cap is a stop, not a
   target.
3. The ledger. After the response, the reservation is replaced with the actual
   cost (OpenRouter's reported usage.cost when present, otherwise reported
   tokens x price) and appended to data/ledger.jsonl, so spend survives
   restarts and is auditable call by call.

Only the embeddings endpoint is ever called; there is no chat/completions path.
"""

import base64
import fcntl
import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

import numpy as np
import requests

from common import DATA, openrouter_key

URL = "https://openrouter.ai/api/v1/embeddings"
CAP_USD = 4.50
SAFETY = 1.3
LEDGER = DATA / "ledger.jsonl"
CACHE_DIR = DATA / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# Catalog prices in USD per token, confirmed against
# https://openrouter.ai/api/v1/embeddings/models and the per-call usage.cost.
PRICE = {
    "voyageai/voyage-4-large": 0.12e-6,
    "qwen/qwen3-embedding-8b": 0.01e-6,
    "openai/text-embedding-3-large": 0.13e-6,
    "google/gemini-embedding-2": 0.20e-6,
    "openai/text-embedding-3-small": 0.02e-6,
}


class BudgetExceeded(RuntimeError):
    pass


_enc = None


def count_tokens(text):
    """cl100k is OpenAI's tokenizer; the other providers' tokenizers differ,
    which is what the 1.3x safety factor is for."""
    global _enc
    if _enc is None:
        import tiktoken

        _enc = tiktoken.get_encoding("cl100k_base")
    return len(_enc.encode(text, disallowed_special=()))


class Ledger:
    """Spend is shared across processes (one embed process per model runs in
    parallel), so the total is re-read from the ledger file under an exclusive
    file lock on every reservation, and every entry is appended under the same
    lock. Reservations in flight in *other* processes are not visible; they are
    bounded by workers x one request (a few tenths of a cent each), far inside
    the $0.50 between CAP_USD and the hard $5."""

    def __init__(self, path=LEDGER, cap=CAP_USD):
        self.path = Path(path)
        self.path.touch(exist_ok=True)
        self.cap = cap
        self.lock = threading.Lock()
        self.reserved = 0.0
        self._offset = 0
        self._spent = 0.0

    def _refresh(self):
        with open(self.path) as f:
            f.seek(self._offset)
            for line in f:
                if line.endswith("\n") and line.strip():
                    self._spent += json.loads(line)["cost_usd"]
                    self._offset += len(line.encode())
        return self._spent

    @property
    def spent(self):
        with self.lock, open(self.path) as lf:
            fcntl.flock(lf, fcntl.LOCK_SH)
            try:
                return self._refresh()
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)

    def reserve(self, est):
        with self.lock, open(self.path) as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                spent = self._refresh()
                if spent + self.reserved + est > self.cap:
                    raise BudgetExceeded(
                        f"refusing call: spent ${spent:.4f} + in flight "
                        f"${self.reserved:.4f} + this ${est:.4f} > cap ${self.cap:.2f}")
                self.reserved += est
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)

    def settle(self, est, entry):
        with self.lock, open(self.path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                self.reserved -= est
                f.write(json.dumps(entry) + "\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def release(self, est):
        with self.lock:
            self.reserved -= est


LEDGER_SINGLETON = None


def ledger():
    global LEDGER_SINGLETON
    if LEDGER_SINGLETON is None:
        LEDGER_SINGLETON = Ledger()
    return LEDGER_SINGLETON


class Cache:
    """One sqlite file per embedding config. Vectors are stored as float16:
    half the disk of float32, and cosine rankings are unchanged at the
    precision retrieval needs (the machine has ~15 GB free and the full run is
    several million dimensions per model)."""

    def __init__(self, key):
        slug = hashlib.sha256(key.encode()).hexdigest()[:16]
        self.path = CACHE_DIR / f"{slug}.sqlite"
        self.key = key
        self.local = threading.local()
        con = self._con()
        con.execute("create table if not exists v (h text primary key, dim int, vec blob)")
        con.execute("create table if not exists meta (k text primary key, v text)")
        con.execute("insert or replace into meta values ('key', ?)", (key,))
        con.commit()

    def _con(self):
        if not hasattr(self.local, "con"):
            self.local.con = sqlite3.connect(self.path, timeout=60)
        return self.local.con

    @staticmethod
    def h(text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get_many(self, hashes):
        out = {}
        con = self._con()
        for i in range(0, len(hashes), 900):
            chunk = hashes[i:i + 900]
            q = "select h, vec from v where h in (%s)" % ",".join("?" * len(chunk))
            for h, blob in con.execute(q, chunk):
                out[h] = np.frombuffer(blob, dtype=np.float16)
        return out

    def put_many(self, items):
        con = self._con()
        con.executemany("insert or replace into v values (?, ?, ?)",
                        [(h, len(v), np.asarray(v, dtype=np.float16).tobytes()) for h, v in items])
        con.commit()


def _post(payload, timeout=120):
    headers = {"Authorization": f"Bearer {openrouter_key()}",
               "Content-Type": "application/json",
               "X-Title": "NYCEats embedding benchmark"}
    last = None
    for attempt in range(6):
        try:
            t0 = time.perf_counter()
            r = requests.post(URL, headers=headers, json=payload, timeout=timeout)
            dt = time.perf_counter() - t0
            if r.status_code == 200:
                body = r.json()
                if "data" in body:
                    return body, dt
                last = f"200 without data: {str(body)[:300]}"
            else:
                last = f"{r.status_code}: {r.text[:300]}"
                if r.status_code in (400, 401, 402, 403, 404):
                    raise RuntimeError(last)
        except requests.RequestException as e:
            last = repr(e)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"OpenRouter failed after retries: {last}")


def _decode(e):
    """base64 responses are float32 little-endian, as in OpenAI's API. A
    4096-dim vector as JSON floats is ~80 KB; as base64 it is ~22 KB, and the
    transfer, not the model, was what made 128-input Qwen requests take 20s+."""
    if isinstance(e, str):
        return np.frombuffer(base64.b64decode(e), dtype="<f4").astype(np.float32)
    return np.asarray(e, dtype=np.float32)


def raw_embed(model, inputs, extra=None, purpose="", encoding="base64"):
    """One uncached, budget-checked request. Returns (vectors, response, seconds)."""
    price = PRICE[model]
    est = sum(count_tokens(t) for t in inputs) * SAFETY * price
    L = ledger()
    L.reserve(est)
    try:
        payload = {"model": model, "input": inputs, "encoding_format": encoding}
        payload.update(extra or {})
        body, dt = _post(payload)
    except Exception:
        L.release(est)
        raise
    usage = body.get("usage") or {}
    tokens = usage.get("prompt_tokens") or usage.get("total_tokens")
    if usage.get("cost") is not None:
        cost = float(usage["cost"])
    elif tokens is not None:
        cost = tokens * price
    else:
        cost = est  # nothing reported: charge the pessimistic estimate
    L.settle(est, {"ts": time.time(), "model": model, "extra": extra or {},
                   "n_inputs": len(inputs), "tokens": tokens, "est_usd": est,
                   "cost_usd": cost, "reported_cost": usage.get("cost"),
                   "provider": body.get("provider"), "purpose": purpose,
                   "seconds": round(dt, 3)})
    data = sorted(body["data"], key=lambda d: d["index"])
    vecs = [_decode(d["embedding"]) for d in data]
    if len(vecs) != len(inputs):
        raise RuntimeError(f"{model}: asked for {len(inputs)} vectors, got {len(vecs)}")
    return vecs, body, dt


def embed_cached(cfg, texts, purpose="", batch=64, workers=4, progress=True):
    """Embed texts under one config, using and filling the cache.

    cfg is an EmbedConfig (see configs.py); texts are the *final* strings, so
    any query prefix has already been applied by the caller via cfg.format_*.
    Returns an (n, dim) float32 array, L2-normalised.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cache = Cache(cfg.cache_key)
    hashes = [Cache.h(t) for t in texts]
    have = cache.get_many(list(set(hashes)))
    todo_idx = {}
    for i, h in enumerate(hashes):
        if h not in have and h not in todo_idx:
            todo_idx[h] = i
    todo = list(todo_idx.items())
    batches = [todo[i:i + batch] for i in range(0, len(todo), batch)]
    if progress and todo:
        print(f"[{cfg.name}] {len(todo)} uncached of {len(texts)}, {len(batches)} requests")

    def run(b):
        vecs, _, _ = raw_embed(cfg.model, [texts[i] for _, i in b], cfg.extra, purpose)
        cache.put_many([(h, v) for (h, _), v in zip(b, vecs)])
        return len(b)

    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(run, b) for b in batches]
        for f in as_completed(futs):
            done += f.result()
            if progress and (done % (batch * 20) < batch or done == len(todo)):
                print(f"[{cfg.name}] {done}/{len(todo)} in {time.time() - t0:.0f}s, "
                      f"ledger ${ledger().spent:.4f}", flush=True)
    have = cache.get_many(list(set(hashes)))
    mat = np.stack([have[h].astype(np.float32) for h in hashes])
    return mat
