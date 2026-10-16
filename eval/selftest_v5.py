"""Regression checks for the v5 harness: normalizer, adapter, scorer, providers.

    python eval/selftest_v5.py

No network and no API key: both providers are replaced by fakes that answer
in their real response shapes (OpenRouter chat completions, Anthropic
Messages), so the whole path -- request, parse, normalize, store, resume,
score -- runs end to end. If eval/gold_v5.jsonl exists it is also scored
against itself, which must be perfect.
"""

import collections
import io
import json
import os
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import providers  # noqa: E402
import run as R  # noqa: E402
import schema_v5 as V  # noqa: E402
import score as S  # noqa: E402
import score_v5 as SV  # noqa: E402
from extract import normalize_entity  # noqa: E402

FAILS = []


def check(cond, what):
    if not cond:
        FAILS.append(what)
        print("FAIL", what)


def mention(name, **kw):
    m = {"restaurant_raw": name, "neighborhood_hint": None, "reference_only": False,
         "aspects": {a: None for a in V.ASPECTS}, "is_negated": False, "price": None,
         "experience": "unclear", "dishes_liked": [], "dishes_disliked": [], "dishes_mentioned": [],
         "descriptors": []}
    for k, v in kw.items():
        if k in V.ASPECTS:
            m["aspects"][k] = v
        else:
            m[k] = v
    return m


# ---------------------------------------------------------------- normalizer
def test_normalizer():
    fx = collections.Counter()
    clean = V.normalize_v5(mention("Lucali", food="good"), fx)
    check(sum(fx.values()) == 0 and clean["aspects"]["food"] == "good", "a valid mention needs no repair")

    fx = collections.Counter()
    m = V.normalize_v5({"restaurant_raw": " Di Fara ", "is_negated": "false", "reference_only": "true",
                        "aspects": {"food": 0.6, "service": "Bad", "vibes": "good"},
                        "price": "very pricey", "experience": True, "dishes_liked": "slice",
                        "dishes_disliked": ["Slice", "square"], "descriptors": [1, "cash only"],
                        "bonus": 1}, fx)
    check(m["is_negated"] is False, 'string "false" is false, not truthy')
    check(m["aspects"]["food"] == "good" and m["aspects"]["service"] == "bad", "numeric and cased labels repaired")
    check(m["reference_only"] is False and fx["reference_with_aspects"] == 1, "aspects beat reference_only")
    check(m["price"] == "very_pricey" and m["experience"] == "ate_there", "price spacing and bool experience")
    check(m["dishes_disliked"] == ["Slice", "square"] and m["dishes_liked"] == [], "a dish in two lists stays disliked")
    check(m["descriptors"] == ["cash only"], "non-string descriptors dropped")
    for k in ("is_negated_string", "aspect_numeric", "aspect_label_case", "aspect_extra_key", "extra_key",
              "dish_in_two_lists", "dishes_liked_string", "descriptors_non_string", "experience_bool"):
        check(fx[k] >= 1, f"repair counted: {k}")

    fx = collections.Counter()
    m = V.normalize_v5(mention("X", reference_only=True, is_negated=True), fx)
    check(not m["reference_only"] and fx["reference_with_negated"] == 1, "an avoid beats reference_only")
    m = V.normalize_v5(mention("X", reference_only=True, dishes_disliked=["fries"]), fx)
    check(not m["reference_only"], "a dish verdict beats reference_only")
    m = V.normalize_v5(mention("X", reference_only=True, dishes_mentioned=["fries"]), fx)
    check(m["reference_only"], "a mentioned dish keeps reference_only")
    check(V.normalize_v5({"aspects": {}}, fx) is None and V.normalize_v5("Lucali", fx) is None,
          "nameless and non-object mentions dropped")
    m = V.normalize_v5({"restaurant_raw": "Y"}, collections.Counter())
    check(m["experience"] == "unclear" and m["reference_only"] is False and m["aspects"]["food"] is None,
          "missing keys default safely")


# ---------------------------------------------------------------- adapter
def test_adapter():
    old = {"restaurant_raw": "Tong", "aspects": {"food": 0.3, "value": None, "service": None,
                                                 "atmosphere": None, "wait": None},
           "expensiveness": None, "is_firsthand": True, "is_negated": False, "dishes": ["noodles"]}
    m = V.adapt_old(old)
    check(V.is_bare(m) if hasattr(V, "is_bare") else SV.is_bare(m), "food 0.3 alone is a bare endorsement")
    check(m["dishes_mentioned"] == ["noodles"] and m["experience"] == "ate_there", "dishes and firsthand carried")
    old2 = dict(old, aspects=dict(old["aspects"], food=0.33, wait=-0.33))
    m = V.adapt_old(old2)
    check(m["aspects"]["food"] == "decent" and m["aspects"]["wait"] == "meh", "0.33 with another aspect is decent")
    old3 = dict(old, aspects={a: None for a in V.ASPECTS}, is_firsthand=None, expensiveness=0.7)
    m = V.adapt_old(old3)
    check(m["reference_only"] and m["experience"] == "unclear" and m["price"] == "pricey",
          "all-null old mention is reference_only; 0.7 is pricey")
    check(V.price_of_float(-1) == "cheap" and V.price_of_float(0) == "moderate" and V.price_of_float(1) == "very_pricey",
          "price thresholds")
    rubric = dict(old, aspects=dict(old["aspects"], food=-0.67), value_complaint=True,
                  dish_sentiment=[{"dish": "dumplings", "level": -0.67, "avoid": True},
                                  {"dish": "noodles", "level": 0.67, "avoid": False}])
    m = V.adapt_old(rubric)
    check(m["dishes_disliked"] == ["dumplings"] and m["dishes_liked"] == ["noodles"]
          and m["dishes_mentioned"] == [], "rubric dish_sentiment splits into liked/disliked")
    check(m["_dish_capable"] and m["_value_complaint"], "rubric runs keep dish capability and value_complaint")
    check(not V.adapt_old(old)["_dish_capable"], "production runs are not dish capable")
    check(V.is_v5(mention("A")) and not V.is_v5(old), "schema detection")
    check(V.to_production_floats(V.normalize_v5(mention("A")))["food"] == 0.3,
          "a v5 bare endorsement writes food 0.3 exactly")


# ---------------------------------------------------------------- scorer
def gold_line(item, cid, mentions):
    gms = []
    for m in mentions:
        g = dict(m)
        k = normalize_entity(m["restaurant_raw"])
        g.update({"canonical_name": m["restaurant_raw"], "canonical_key": k, "accept_keys": [k],
                  "entity_type": "restaurant", "out_of_scope": False, "ambiguous": False,
                  "confidence": "high", "named_in": "comment", "resolvable_comment_mode": True,
                  "resolvable_thread_mode": True, "uncertain_fields": [], "rationale": "",
                  "value_complaint": (V.level(m["aspects"]["value"]) or 0) < 0,
                  "aspect_alternatives": {}, "judgment_question": False})
        gms.append(g)
    return {"item_id": item["item_id"], "comment_id": cid, "thread_id": item["thread_id"],
            "label_version": 3, "has_mention": bool(gms), "mentions": gms, "note": ""}


def fixture():
    items = [it for it in R.load_items(os.path.join(HERE, "items.jsonl")) if it["kind"] == "comment"][:3]
    answers = [
        [mention("Testaurant Alpha", food="awful", service="bad", experience="ate_there",
                 dishes_disliked=["vodka slice"], descriptors=["tourist trap"], is_negated=True)],
        [mention("Testaurant Beta"), mention("Testaurant Gamma", reference_only=True, descriptors=["closed"])],
        [],
    ]
    gold = [gold_line(it, it["comment_id"], ans) for it, ans in zip(items, answers)]
    return items, answers, gold


def test_scorer_perfect():
    items, answers, gold = fixture()
    run = SV.gold_as_run(gold, items)
    per_rep, _ = SV.evaluate(gold, items, run, {}, set(), False, "")
    o = per_rep[0]["overall"]
    for k in ("mention_recall", "negative_mention_recall", "dish_negative_recall", "reference_only_recall",
              "bare_endorsement_recall", "is_negated_recall", "experience_acc", "dishes_disliked_recall",
              "closed_handled_rate"):
        check(o[k] == 1.0, f"gold vs itself is perfect: {k}={o[k]}")
    check(o["drop_rate"] == 0, "gold vs itself drops nothing")


# ---------------------------------------------------------------- fakes
class FakeHTTP:
    """Stands in for urllib's urlopen. Answers by the user message, in the
    OpenRouter chat-completions shape, and records every request body."""

    def __init__(self, table, status=200):
        self.table, self.status, self.requests = table, status, []

    def __call__(self, req, timeout=None):
        body = json.loads(req.data)
        self.requests.append(body)
        if self.status != 200:
            raise urllib.error.HTTPError(req.full_url, self.status, "no",
                                         {}, io.BytesIO(b'{"error":{"message":"Key limit exceeded"}}'))
        user = body["messages"][1]["content"]
        content = json.dumps({"mentions": self.table[user]})
        return io.BytesIO(json.dumps({
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "provider": "Fake",
            "usage": {"prompt_tokens": 5000, "completion_tokens": 120, "total_tokens": 5120, "cost": 0.00056,
                      "prompt_tokens_details": {"cached_tokens": 4800}},
        }).encode())


class FakeSDK:
    """Stands in for the anthropic module: Anthropic().messages.create returns
    a Messages-shaped object; the first call writes the cache, later ones read."""

    class APIStatusError(Exception):
        def __init__(self, status_code, message):
            super().__init__(message)
            self.status_code, self.message = status_code, message

    class APIConnectionError(Exception):
        pass

    def __init__(self, table, fail=None):
        sdk = self

        class Messages:
            def create(self, **kw):
                sdk.requests.append(kw)
                if sdk.fail:
                    raise FakeSDK.APIStatusError(*sdk.fail)
                first = len(sdk.requests) == 1
                text = json.dumps({"mentions": sdk.table[kw["messages"][0]["content"]]})
                msg = {"content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": text}],
                       "stop_reason": "end_turn",
                       "usage": {"input_tokens": 200, "output_tokens": 150,
                                 "cache_creation_input_tokens": 4800 if first else 0,
                                 "cache_read_input_tokens": 0 if first else 4800}}
                return type("Msg", (), {"to_dict": lambda self: msg})()

        class Anthropic:
            def __init__(self, **kw):
                self.messages = Messages()

        self.Anthropic, self.table, self.fail, self.requests = Anthropic, table, fail, []


def install(http=None, sdk=None):
    providers._urlopen = http or providers.urllib.request.urlopen
    providers._sdk, providers._client = sdk, None
    providers._catalog = {"anthropic/claude-haiku-5.5": {
        "supported_parameters": ["max_tokens", "reasoning", "response_format"],
        "pricing": {"prompt": "0.0000001", "completion": "0.0000005", "input_cache_read": "0.00000001",
                    "input_cache_write": "0.000000125"}}}


SYSTEM = "SYSTEM " * 800      # stands in for a ~5k-token v5 prompt


def jobs_for(items, answers, mode):
    jobs = R.build_jobs(items, mode, None)
    table = {}
    for j in jobs:
        ms = []
        for sid, cid in j["id_map"].items():
            it = next((x for x in items if x["comment_id"] == cid), None)
            if it is None:
                continue
            for m in answers[items.index(it)]:
                ms.append(dict(m, id=sid) if mode == "thread" else m)
        table[j["user"]] = ms
    return jobs, table


def end_to_end(api, model, mode, tmp):
    items, answers, gold = fixture()
    jobs, table = jobs_for(items, answers, mode)
    http, sdk = FakeHTTP(table), FakeSDK(table)
    install(http, sdk)
    out = os.path.join(tmp, f"{api}_{mode}.jsonl")
    opts = {"temperature": 0.0, "timeout": 5}
    todo = [(j, 0) for j in jobs]
    st = R.execute(todo, model, SYSTEM, "testhash", mode, opts, api, out, workers=2, progress=False)
    check(st["calls"] == len(jobs) and st["errors"] == 0, f"{api}/{mode}: every call recorded")
    check(len(R.cached_calls(out)) == len(jobs), f"{api}/{mode}: resume sees every call as done")
    reqs = http.requests if api == "openrouter" else sdk.requests
    if api == "openrouter":
        sysmsg = reqs[0]["messages"][0]["content"]
        check(isinstance(sysmsg, list) and sysmsg[0].get("cache_control"), "openrouter: system prompt marked for caching")
        check("temperature" not in reqs[0], "openrouter: no temperature for a model that rejects it")
    else:
        check(reqs[0]["system"][0].get("cache_control") == {"type": "ephemeral"}, "anthropic: system prompt cached")
        check("temperature" not in reqs[0], "anthropic: no temperature for claude-haiku-5-5")
    run = SV.Run(out, items)
    h = SV.run_health(run)
    check(h["schema"] == "v5" and h["parse_failure_rate"] == 0, f"{api}/{mode}: parsed as v5")
    check(h["cache_read_tokens"] > 0, f"{api}/{mode}: cache reads recorded")
    if api == "anthropic":
        check(h["cache_write_tokens"] == 4800, "anthropic: exactly one cache write (first call ran alone)")
        check(h["cost"] > 0, "anthropic: cost computed from the price table")
    per_rep, _ = SV.evaluate(gold, items, run, {}, set(), False, "")
    o = per_rep[0]["overall"]
    check(o["mention_recall"] == 1.0 and o["dish_negative_recall"] == 1.0 and o["reference_only_recall"] == 1.0,
          f"{api}/{mode}: scored perfect through the whole path ({o['mention_recall']}, {o['dish_negative_recall']})")


def fatal_stops(api, tmp, model=None):
    """model=None: the cached-prompt path, where the first call runs alone.
    A non-Claude model takes the parallel path straight away."""
    items, answers, _ = fixture()
    jobs, table = jobs_for(items, answers, "comment")
    if api == "openrouter":
        install(http=FakeHTTP(table, status=403))
        model = model or "anthropic/claude-haiku-5.5"
    else:
        install(sdk=FakeSDK(table, fail=(400, "Your credit balance is too low")))
        model = "claude-haiku-5-5"
    out = os.path.join(tmp, f"fatal_{api}_{model.replace('/', '_')}.jsonl")
    try:
        R.execute([(j, 0) for j in jobs], model, SYSTEM, "h", "comment", {"timeout": 5}, api, out, 2, False)
        check(False, f"{api}: a refused key must stop the run")
    except SystemExit as e:
        check("refused the key" in str(e), f"{api}: the stop says why ({e})")
    rows = S.load_jsonl(out) if os.path.exists(out) else []
    check(not rows, f"{api}: no error rows written for a refused key ({len(rows)} written)")


def test_resolve():
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        check(providers.resolve("haiku-5.5") == ("openrouter", "anthropic/claude-haiku-5.5"), "alias without a key")
        check(providers.resolve("claude-haiku-5-5") == ("openrouter", "anthropic/claude-haiku-5.5"),
              "native id falls back to OpenRouter's slug")
        os.environ["ANTHROPIC_API_KEY"] = "test"
        check(providers.resolve("haiku-5.5") == ("anthropic", "claude-haiku-5-5"), "alias with a key")
        check(providers.resolve("anthropic/claude-haiku-5.5") == ("openrouter", "anthropic/claude-haiku-5.5"),
              "an explicit slug stays on OpenRouter")
        check(providers.resolve("anthropic/claude-haiku-5.5", "anthropic") == ("anthropic", "claude-haiku-5-5"),
              "--api anthropic converts a slug")
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved


def test_real_gold():
    path = SV.SETS["v1"]["gold"]
    if not os.path.exists(path):
        print(f"skip: {path} not built yet")
        return
    gold, items = S.load_jsonl(path), S.load_jsonl(SV.SETS["v1"]["items"])
    SV.self_test(gold, items, S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json"),
                 SV.SETS["v1"]["stats"])


def main():
    test_normalizer()
    test_adapter()
    test_scorer_perfect()
    test_resolve()
    # The fakes never send anything, but the request is built with a key.
    saved = os.environ.get("OPENROUTER_API_KEY")
    os.environ["OPENROUTER_API_KEY"] = "fake-key-for-selftest"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for api, model in (("openrouter", "anthropic/claude-haiku-5.5"), ("anthropic", "claude-haiku-5-5")):
                for mode in ("comment", "thread"):
                    end_to_end(api, model, mode, tmp)
                fatal_stops(api, tmp)
            fatal_stops("openrouter", tmp, "deepseek/deepseek-v4-flash")
    finally:
        if saved is None:
            os.environ.pop("OPENROUTER_API_KEY", None)
        else:
            os.environ["OPENROUTER_API_KEY"] = saved
    install()
    providers._catalog = None
    test_real_gold()
    if FAILS:
        raise SystemExit(f"{len(FAILS)} checks failed")
    print("selftest_v5 ok")


if __name__ == "__main__":
    main()
