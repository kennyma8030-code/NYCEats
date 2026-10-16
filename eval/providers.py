"""Where a model call goes: OpenRouter, or Anthropic's own API.

run.py and bench.py both call complete(); it returns the same record shape
whichever provider answered, so run files from either one score the same way.

    resolve("haiku-5.5")                 -> ("anthropic", "claude-haiku-5-5") if ANTHROPIC_API_KEY
                                            is set, else ("openrouter", "anthropic/claude-haiku-5.5")
    resolve("claude-haiku-5-5")          -> Anthropic's API (OpenRouter's slug if there is no key)
    resolve("anthropic/claude-haiku-5.5") -> OpenRouter, as written
    resolve("deepseek/deepseek-v4-flash") -> OpenRouter

Keys come from the environment, or from a .env in this checkout or in the
repo's main checkout (a worktree has no .env of its own). Only the two key
variables are read from it, and they are never printed.
"""

import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OPENROUTER_URL = os.environ.get("EVAL_API_URL", "https://openrouter.ai/api/v1/chat/completions")
CATALOG_URL = "https://openrouter.ai/api/v1/models"
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "nyceats-eval")
KEY_VARS = ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")

# Short names that work on either provider. Anthropic ids are the exact ids
# from the API's model list, never date-suffixed.
ALIASES = {
    "haiku-5.5": {"anthropic": "claude-haiku-5-5", "openrouter": "anthropic/claude-haiku-5.5"},
    "sonnet-5.5": {"anthropic": "claude-sonnet-5-5", "openrouter": "anthropic/claude-sonnet-5.5"},
    "opus-5.5": {"anthropic": "claude-opus-5-5", "openrouter": "anthropic/claude-opus-5.5"},
    "sonnet-5": {"anthropic": "claude-sonnet-5", "openrouter": "anthropic/claude-sonnet-5"},
    "opus-5": {"anthropic": "claude-opus-5", "openrouter": "anthropic/claude-opus-5"},
    "haiku-4.5": {"anthropic": "claude-haiku-4-5", "openrouter": "anthropic/claude-haiku-4.5"},
    "deepseek-v4-flash": {"openrouter": "deepseek/deepseek-v4-flash"},
    "deepseek-v4.1-flash": {"openrouter": "deepseek/deepseek-v4.1-flash"},
    "deepseek-v4-pro": {"openrouter": "deepseek/deepseek-v4-pro-0813"},
    "gemini-3.8-flash": {"openrouter": "google/gemini-3.8-flash"},
    "gpt-6-luna": {"openrouter": "openai/gpt-6-luna"},
    "gpt-6.1-sol": {"openrouter": "openai/gpt-6.1-sol"},
    "qwen3.8-flash": {"openrouter": "qwen/qwen3.8-flash"},
    "glm-5.3-flash": {"openrouter": "z-ai/glm-5.3-flash"},
}

# Anthropic first-party prices: input and output $ per million tokens, and a
# cache read as a fraction of input. Reads are 0.1x input on every model here
# except Opus 5.5, which reads at 0.05x (so $0.20, the same dollar figure as
# Sonnet 5.5's 0.1x of $2). A 5-minute cache write is 1.25x input on all of
# them. Haiku 5.5's rates hold for prompts up to 100K tokens, far above
# anything the eval sends.
ANTHROPIC_PRICES = {
    "claude-haiku-5-5": (0.10, 0.50, 0.10),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-opus-5-5": (4.00, 20.00, 0.05),
    "claude-sonnet-5": (2.00, 10.00, 0.10),
    "claude-opus-5": (5.00, 25.00, 0.10),
    "claude-haiku-4-5": (1.00, 5.00, 0.10),
}
CACHE_WRITE_FACTOR = 1.25
# The only Claude ids that still accept a non-default temperature; every
# newer Claude model rejects one with a 400, whichever provider relays it.
ANTHROPIC_SAMPLING_OK = {"claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-6"}

# A 403 from OpenRouter is usually the key (spend limit, no credit), but its
# moderation also answers 403 for one flagged input. Only the first kind is
# fatal; a body with none of these words is a per-call failure.
KEY_FAILURE_WORDS = ("key limit", "limit exceeded", "credit", "insufficient", "quota",
                     "api key", "unauthorized", "no auth", "billing", "payment")


class FatalError(Exception):
    """The key itself was refused: out of credit, revoked, or not allowed.
    Every later call would fail the same way, so the whole run stops at the
    first one instead of writing hundreds of error rows."""


class PermanentError(Exception):
    """This one input was refused (a moderation 403) and would be refused
    again. It is recorded as an error row that resume does not retry."""


# ---------------------------------------------------------------- keys
def _main_checkout():
    try:
        common = subprocess.run(["git", "-C", ROOT, "rev-parse", "--path-format=absolute",
                                 "--git-common-dir"], capture_output=True, text=True,
                                check=True).stdout.strip()
        return os.path.dirname(common)
    except (OSError, subprocess.CalledProcessError):
        return None


def load_env():
    """Fill missing key variables from .env files. Never overrides the
    environment, never reads anything but the key variables."""
    paths = [os.path.join(ROOT, ".env")]
    main = _main_checkout()
    if main:
        paths.append(os.path.join(main, ".env"))
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                k, sep, v = line.strip().partition("=")
                k = k.strip().removeprefix("export ").strip()
                if sep and k in KEY_VARS and not os.environ.get(k):
                    os.environ[k] = v.strip().strip('"').strip("'")


# ---------------------------------------------------------------- models
def _native_to_slug(model_id):
    """claude-haiku-5-5 -> anthropic/claude-haiku-5.5."""
    m = re.fullmatch(r"claude-([a-z]+)-(\d+)-(\d+)", model_id)
    return f"anthropic/claude-{m.group(1)}-{m.group(2)}.{m.group(3)}" if m else f"anthropic/{model_id}"


def _slug_to_native(slug):
    """anthropic/claude-haiku-5.5 -> claude-haiku-5-5 (anthropic/claude-sonnet-5 -> claude-sonnet-5)."""
    s = slug.split("/", 1)[-1].split(":", 1)[0]
    m = re.fullmatch(r"claude-([a-z]+)-(\d+)\.(\d+)", s)
    return f"claude-{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else s


def resolve(model, api="auto"):
    """A model name -> (api, model id). api is auto, openrouter or anthropic."""
    have_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if model in ALIASES:
        entry = ALIASES[model]
        if api == "anthropic" or (api == "auto" and have_anthropic and "anthropic" in entry):
            if "anthropic" not in entry:
                raise SystemExit(f"{model} is not an Anthropic model")
            return "anthropic", entry["anthropic"]
        return "openrouter", entry["openrouter"]
    if model.startswith("claude-"):
        if api == "openrouter" or (api == "auto" and not have_anthropic):
            return "openrouter", _native_to_slug(model)
        return "anthropic", model
    if api == "anthropic":
        if model.startswith("anthropic/"):
            return "anthropic", _slug_to_native(model)
        raise SystemExit(f"{model} is not an Anthropic model")
    return "openrouter", model


_catalog = None
_catalog_lock = threading.Lock()
_catalog_failed_at = 0.0
CATALOG_RETRY_S = 300


def catalog(max_age_days=7):
    """OpenRouter's public model list (pricing, supported parameters), cached
    on disk for a week and in memory for the process. Needs no key.

    Worker threads call this concurrently, so loading is locked and the disk
    copy is replaced atomically. A failed load is not cached: it returns {}
    and is tried again after CATALOG_RETRY_S, rather than on every call."""
    global _catalog, _catalog_failed_at
    if _catalog is not None:
        return _catalog
    with _catalog_lock:
        if _catalog is not None:
            return _catalog
        if time.time() - _catalog_failed_at < CATALOG_RETRY_S:
            return {}
        cat = _load_catalog(max_age_days)
        if cat:
            _catalog = cat
        else:
            _catalog_failed_at = time.time()
        return cat


def _load_catalog(max_age_days):
    path = os.path.join(CACHE_DIR, "openrouter_models.json")
    fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_days * 86400
    if not fresh:
        try:
            with urllib.request.urlopen(CATALOG_URL, timeout=30) as r:
                data = r.read()
            json.loads(data)                        # never replace a good copy with junk
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except (OSError, ValueError, urllib.error.URLError):
            if not os.path.exists(path):
                return {}
    try:
        with open(path, encoding="utf-8") as f:
            return {m["id"]: m for m in json.load(f).get("data", [])}
    except (OSError, ValueError, KeyError):
        return {}


def prices(api, model_id, cat=None):
    """$ per token: (input, output, cache_read, cache_write), or None if unknown."""
    if api == "anthropic":
        p = ANTHROPIC_PRICES.get(model_id)
        if not p:
            return None
        inp, out, read = p
        return inp / 1e6, out / 1e6, inp * read / 1e6, inp * CACHE_WRITE_FACTOR / 1e6
    entry = (cat if cat is not None else catalog()).get(model_id)
    if not entry:
        return None
    pr = entry.get("pricing") or {}
    f = lambda k, d=None: float(pr[k]) if pr.get(k) not in (None, "") else d  # noqa: E731
    inp = f("prompt", 0.0)
    return inp, f("completion", 0.0), f("input_cache_read", inp), f("input_cache_write", inp)


def supports(api, model_id, param, cat=None):
    """Whether a request parameter may be sent. A Claude model's own rule
    wins, on either provider: OpenRouter's catalog lists temperature for
    models whose API then rejects it. Otherwise the catalog says per model,
    and with no catalog entry the old behavior (send it) stands."""
    if api == "anthropic":
        return param != "temperature" or model_id in ANTHROPIC_SAMPLING_OK
    if param == "temperature" and model_id.startswith("anthropic/"):
        return _slug_to_native(model_id) in ANTHROPIC_SAMPLING_OK
    entry =(cat if cat is not None else catalog()).get(model_id)
    if not entry or "supported_parameters" not in entry:
        return True
    return param in entry["supported_parameters"]


# ---------------------------------------------------------------- calls
def _openrouter_payload(model_id, system, user, opts, cat):
    if opts.get("thinking"):
        # Never record a setting the request did not carry.
        raise SystemExit("--thinking is only sent on Anthropic's API; on OpenRouter use --effort")
    if model_id.startswith("anthropic/"):
        # The system prompt is identical on every call; mark it so Anthropic
        # caches it instead of billing it in full each time.
        sys_msg = {"role": "system", "content": [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]}
    else:
        sys_msg = {"role": "system", "content": system}
    payload = {"model": model_id, "messages": [sys_msg, {"role": "user", "content": user}],
               "usage": {"include": True}}
    if supports("openrouter", model_id, "response_format", cat):
        payload["response_format"] = {"type": "json_object"}
    if opts.get("temperature") is not None and supports("openrouter", model_id, "temperature", cat):
        payload["temperature"] = opts["temperature"]
    if opts.get("max_tokens"):
        payload["max_tokens"] = opts["max_tokens"]
    if opts.get("provider"):
        payload["provider"] = {"order": opts["provider"].split(","), "allow_fallbacks": False}
    if opts.get("effort"):
        payload["reasoning"] = {"effort": opts["effort"]}
    return payload


def _call_openrouter(model_id, system, user, opts, cat):
    payload = _openrouter_payload(model_id, system, user, opts, cat)
    req = urllib.request.Request(OPENROUTER_URL, data=json.dumps(payload).encode(), headers={
        "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
        "Content-Type": "application/json",
    })
    last = None
    for attempt in range(6):
        t0 = time.time()
        try:
            with _urlopen(req, timeout=opts.get("timeout", 180)) as r:
                body = json.load(r)
            return parse_openrouter(body), time.time() - t0, None
        except urllib.error.HTTPError as e:
            body = e.read()[:300]
            last = f"http {e.code}: {body!r}"
            if is_key_failure(e.code, body):
                raise FatalError(f"OpenRouter refused the key ({last})")
            if e.code == 403:
                raise PermanentError(last)
            if e.code != 429 and e.code < 500:
                break
        except Exception as e:  # network; transient
            last = f"{type(e).__name__}: {e}"
        time.sleep(min(5 * 2 ** attempt, 60))
    return None, None, last


def is_key_failure(code, body):
    """401 and 402 are always the key; a 403 is the key only when it says so."""
    if code in (401, 402):
        return True
    text = (body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)).lower()
    return code == 403 and "flagged" not in text and any(w in text for w in KEY_FAILURE_WORDS)


def parse_openrouter(body):
    choice = (body.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    u = body.get("usage") or {}
    details = u.get("prompt_tokens_details") or {}
    err = body.get("error")
    return {
        "raw": msg.get("content"),
        "error": None if not err else f"provider error: {json.dumps(err)[:300]}",
        "api": "openrouter",
        "provider": body.get("provider"),
        "stop_reason": choice.get("finish_reason"),
        "usage": {"prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
                  "total_tokens": u.get("total_tokens"), "cost": u.get("cost"),
                  "cache_read_tokens": details.get("cached_tokens"),
                  "cache_write_tokens": details.get("cache_write_tokens")},
        "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
    }


def anthropic_request(model_id, system, user, opts):
    """The Messages API arguments. The system prompt carries a cache marker:
    it is the same on every call and well over the minimum cacheable size."""
    kw = {
        "model": model_id,
        "max_tokens": opts.get("max_tokens") or 16000,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
    }
    if opts.get("effort"):
        kw["output_config"] = {"effort": opts["effort"]}
    if opts.get("thinking"):
        kw["thinking"] = {"type": opts["thinking"]}
    if opts.get("temperature") is not None and supports("anthropic", model_id, "temperature"):
        kw["temperature"] = opts["temperature"]
    return kw


def parse_anthropic(msg, model_id):
    """A Messages API response (as a dict) -> the common record. Thinking
    blocks are skipped; the answer is the text blocks."""
    text = "".join(b.get("text", "") for b in msg.get("content") or [] if b.get("type") == "text")
    u = msg.get("usage") or {}
    inp, out = u.get("input_tokens") or 0, u.get("output_tokens") or 0
    cr, cw = u.get("cache_read_input_tokens") or 0, u.get("cache_creation_input_tokens") or 0
    p = prices("anthropic", model_id)
    cost = None if p is None else inp * p[0] + out * p[1] + cr * p[2] + cw * p[3]
    return {
        "raw": text if text or msg.get("stop_reason") != "refusal" else None,
        "api": "anthropic",
        "provider": "Anthropic",
        "stop_reason": msg.get("stop_reason"),
        "usage": {"prompt_tokens": inp + cr + cw, "completion_tokens": out,
                  "total_tokens": inp + cr + cw + out, "cost": cost,
                  "cache_read_tokens": cr, "cache_write_tokens": cw},
        "reasoning_tokens": None,
    }


# Tests swap these for fakes; nothing else should touch them.
_urlopen = urllib.request.urlopen
_sdk = None
_client = None
_client_lock = threading.Lock()


def _anthropic_sdk():
    global _sdk
    if _sdk is None:
        try:
            import anthropic
        except ImportError:
            raise SystemExit("the Anthropic path needs the SDK: pip install anthropic "
                             "(or unset ANTHROPIC_API_KEY to go through OpenRouter)")
        _sdk = anthropic
    return _sdk


def _call_anthropic(model_id, system, user, opts):
    global _client
    anthropic = _anthropic_sdk()
    with _client_lock:
        if _client is None:
            _client = anthropic.Anthropic(max_retries=5, timeout=opts.get("timeout", 180))
    t0 = time.time()
    try:
        msg = _client.messages.create(**anthropic_request(model_id, system, user, opts))
    except anthropic.APIStatusError as e:
        err = f"http {e.status_code}: {str(e.message)[:300]}"
        if e.status_code in (401, 402, 403) or "credit balance" in str(e.message).lower():
            raise FatalError(f"Anthropic refused the key ({err})")
        return None, None, err
    except anthropic.APIConnectionError as e:
        return None, None, f"{type(e).__name__}: {e}"
    out = parse_anthropic(msg.to_dict(), model_id)
    if out["raw"] is None:
        return None, time.time() - t0, f"refusal: {msg.to_dict().get('stop_details')}"
    return out, time.time() - t0, None


def check_opts(api, opts):
    """Refuse settings this provider would not send, before any call, so a
    run file is never named for a setting it didn't use."""
    if api == "openrouter" and opts.get("thinking"):
        raise SystemExit("--thinking is only sent on Anthropic's API; on OpenRouter use --effort")


def complete(api, model_id, system, user, opts, cat=None):
    """One call -> (record or None, latency seconds, error string or None)."""
    if api == "anthropic":
        return _call_anthropic(model_id, system, user, opts)
    return _call_openrouter(model_id, system, user, opts, cat if cat is not None else catalog())


def require_key(api):
    var = "ANTHROPIC_API_KEY" if api == "anthropic" else "OPENROUTER_API_KEY"
    if not os.environ.get(var):
        raise SystemExit(f"{var} is not set (environment or .env)")
