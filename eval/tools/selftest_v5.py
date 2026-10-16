"""Regression checks for the v5 harness: normalizer, adapter, scorer, providers.

    python eval/tools/selftest_v5.py

No network and no API key: both providers are replaced by fakes that answer
in their real response shapes (OpenRouter chat completions, Anthropic
Messages), so the whole path -- request, parse, normalize, store, resume,
score -- runs end to end. If eval/v1/gold_v5.jsonl exists it is also scored
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
EVAL = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
sys.path.insert(0, os.path.join(EVAL, "lib"))
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
    for k in ("is_negated_string", "aspect_numeric_float", "aspect_label_case", "aspect_extra_key", "extra_key",
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
    items = [it for it in R.load_items(os.path.join(EVAL, "v1", "items.jsonl")) if it["kind"] == "comment"][:3]
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

    KEY_LIMIT = b'{"error":{"message":"Key limit exceeded ($30.00 of $30.00 used; does not reset)","code":403}}'
    FLAGGED = b'{"error":{"message":"Input was flagged by moderation","code":403}}'

    def __init__(self, table, status=200, body=KEY_LIMIT, only=None):
        self.table, self.status, self.body, self.only, self.requests = table, status, body, only, []

    def __call__(self, req, timeout=None):
        body = json.loads(req.data)
        self.requests.append(body)
        user = body["messages"][1]["content"]
        if self.status != 200 and (self.only is None or user in self.only):
            raise urllib.error.HTTPError(req.full_url, self.status, "no", {}, io.BytesIO(self.body))
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
    # The catalog lists temperature even for the Claude model that rejects
    # it: the Claude rule has to win over the catalog.
    params = ["max_tokens", "reasoning", "response_format", "temperature"]
    pricing = {"prompt": "0.0000001", "completion": "0.0000005", "input_cache_read": "0.00000001",
               "input_cache_write": "0.000000125"}
    providers._catalog = {m: {"supported_parameters": params, "pricing": pricing}
                          for m in ("anthropic/claude-haiku-5.5", "anthropic/claude-haiku-4.5",
                                    "deepseek/deepseek-v4-flash")}


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


def test_temperature():
    install()
    pay = lambda m: providers._openrouter_payload(m, "s", "u", {"temperature": 0.0}, providers._catalog)  # noqa: E731
    check("temperature" not in pay("anthropic/claude-haiku-5.5"),
          "openrouter: Claude 5.5 gets no temperature even when the catalog lists it")
    check(pay("anthropic/claude-haiku-4.5").get("temperature") == 0.0, "openrouter: Haiku 4.5 still gets temperature")
    check(pay("deepseek/deepseek-v4-flash").get("temperature") == 0.0, "openrouter: other models follow the catalog")


def test_integer_levels():
    fx = collections.Counter()
    lab = lambda v: V._label(v, fx, "aspect")  # noqa: E731
    for v, want in ((1, "decent"), (-1, "meh"), (2, "good"), (-3, "awful"), (3, "rave"), (0, "mixed"),
                    ("2", "good"), ("+1", "decent"), ("-2", "bad"), (2.0, "good"), (7, "rave"),
                    (0.6, "good"), (-0.33, "meh"), (0.3, "decent"), (-0.9, "awful"), (True, None)):
        check(lab(v) == want, f"aspect value {v!r} reads as {want} (got {lab(v)})")
    check(fx["aspect_numeric_level"] and fx["aspect_numeric_float"], "both numeric repairs counted")
    check(V._price(1, fx) == "pricey" and V._price(-2, fx) == "cheap" and V._price(0.9, fx) == "very_pricey",
          "price levels and floats")


def write_run(path, recs):
    with open(path, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


def rec(key, rep, by_cid, mode="comment", cost=0.001, **kw):
    r = {"call_key": key, "rep": rep, "item_ids": [], "model": "m", "prompt_hash": "h", "mode": mode,
         "error": None, "raw": "{}", "json_ok": True, "mentions_by_comment": by_cid, "bad_ids": 0,
         "latency_s": 1.0, "usage": {"prompt_tokens": 100, "completion_tokens": 10, "cost": cost}}
    r.update(kw)
    return r


def test_moderation_403(tmp):
    """A flagged input is one error row, the run goes on, resume skips it,
    and it scores as a dropped comment."""
    items, answers, gold = fixture()
    jobs, table = jobs_for(items, answers, "comment")
    flagged = jobs[0]["user"]
    install(http=FakeHTTP(table, status=403, body=FakeHTTP.FLAGGED, only={flagged}))
    out = os.path.join(tmp, "flagged.jsonl")
    st = R.execute([(j, 0) for j in jobs], "deepseek/deepseek-v4-flash", SYSTEM, "h", "comment",
                   {"timeout": 5}, "openrouter", out, 2, False)
    rows = S.load_jsonl(out)
    bad = [r for r in rows if r.get("error")]
    check(st["calls"] == len(jobs) and len(bad) == 1 and bad[0].get("permanent"),
          "a flagged 403 is one permanent error row and the run continues")
    check(len(R.cached_calls(out)) == len(jobs), "resume does not retry a refused input")
    install(http=FakeHTTP(table, status=402, body=b'{"error":{"message":"Payment required"}}'))
    try:
        R.execute([(jobs[0], 1)], "deepseek/deepseek-v4-flash", SYSTEM, "h", "comment", {"timeout": 5},
                  "openrouter", out, 2, False)
        check(False, "a 402 must stop the run")
    except SystemExit:
        pass
    check(providers.is_key_failure(403, FakeHTTP.KEY_LIMIT) and not providers.is_key_failure(403, FakeHTTP.FLAGGED)
          and providers.is_key_failure(401, b"") and not providers.is_key_failure(403, b"forbidden"),
          "only key-shaped 403s are fatal")
    run = SV.Run(out, items)
    h = SV.run_health(run)
    check(h["refused_inputs"] == 1, "run health counts the refused input")
    cid = jobs[0]["id_map"][None]
    check(cid in run.covered[0] and run.preds[0].get(cid, []) == [], "a refused input is covered with nothing found")


def test_rep_coverage_and_set_cost(tmp):
    items, answers, gold = fixture()
    a, b = items[0]["comment_id"], items[1]["comment_id"]
    path = os.path.join(tmp, "reps.jsonl")
    write_run(path, [rec(f"comment:{a}", 0, {a: []}), rec(f"comment:{b}", 0, {b: []}),
                     rec(f"comment:{a}", 1, {a: []}),
                     rec(f"comment:{b}", 1, {}, error="http 500", raw=None),
                     rec("comment:t1_not_in_this_set", 0, {"t1_not_in_this_set": []}, cost=5.0)])
    run = SV.Run(path, items)
    check(run.complete_reps() == [0] and run.covered_complete() == {a, b},
          f"a rep missing a call is not complete ({run.complete_reps()}, {run.covered_complete()})")
    h = SV.run_health(run)
    check(h["calls"] == 4 and abs(h["cost"] - 0.003) < 1e-9, "another set's calls are not counted in this set's cost")
    check(abs(h["cost_per_1k_comments"] - 1.0) < 1e-9, f"cost per 1k comments over the same calls ({h['cost_per_1k_comments']})")

    # Thread mode: a chunk's cost is spread over every comment it rendered.
    it = items[0]
    ch = it["inputs"]["thread"]
    key = f"thread:{it['thread_id']}:{ch['chunk_index']}"
    path = os.path.join(tmp, "thread_cost.jsonl")
    write_run(path, [rec(key, 0, {}, mode="thread", cost=0.01),
                     rec("thread:t3_other_set:0", 0, {}, mode="thread", cost=9.0)])
    h = SV.run_health(SV.Run(path, items))
    n = len(ch["short_ids"])
    check(abs(h["cost_per_1k_comments"] - 10.0 / n) < 1e-9, "thread cost per 1k comments counts only this set's chunks")


def test_complete_reps(tmp):
    """A later rep that stopped early is left out, not allowed to shrink the
    common comments; a short rep 0 stays but is flagged."""
    import bench as B
    items, answers, gold = fixture()
    a, b, c = (it["comment_id"] for it in items)
    full = [rec(f"comment:{x}", rep, {x: []}) for rep in (0, 1) for x in (a, b, c)]
    path = os.path.join(tmp, "three_reps.jsonl")
    write_run(path, full + [rec(f"comment:{a}", 2, {a: []}),
                            rec(f"comment:{b}", 2, {}, error="http 403: key limit", raw=None)])
    run = SV.Run(path, items)
    check(run.complete_reps() == [0, 1] and len(run.reps) == 3, f"rep 2 is partial and dropped ({run.complete_reps()})")
    check(run.covered_complete() == {a, b, c}, "the complete reps keep the full coverage")
    check(not run.rep0_partial(), "rep 0 is complete")
    per_rep, _ = SV.evaluate(gold, items, run, {}, set(), False, "")
    check(len(per_rep) == 2, "only complete reps are scored")

    other = os.path.join(tmp, "one_rep.jsonl")
    write_run(other, [rec(f"comment:{x}", 0, {x: []}) for x in (a, b, c)])
    short = os.path.join(tmp, "short_rep0.jsonl")
    write_run(short, [rec(f"comment:{a}", 0, {a: []}), rec(f"comment:{b}", 0, {b: []}),
                      rec(f"comment:{c}", 0, {}, error="http 500", raw=None)])
    r_other, r_short = SV.Run(other, items), SV.Run(short, items)
    check(r_short.rep0_partial() and r_short.complete_reps() == [0], "a short rep 0 is kept and flagged")
    check(r_other.rep0_partial({f"comment:{a}", "comment:t1_never_made"}), "an unmade planned call flags rep 0")

    class A:
        drop_chains = False
    rows = [("three", "comment", run), ("one", "comment", r_other)]
    n, out = B.score_set(gold, items, "", rows, A(), {}, set())["comment"]
    check(n == 3 and [len(x[2]) for x in out] == [2, 1], f"common set is rep 0's full coverage ({n})")
    n, _ = B.score_set(gold, items, "", rows + [("short", "comment", r_short)], A(), {}, set())["comment"]
    check(n == 2, "a short rep 0 narrows the common set to what it covered")


def test_run_level_schema(tmp):
    items, answers, gold = fixture()
    a = items[0]["comment_id"]
    drifted = {"restaurant_raw": "Testaurant Alpha", "aspects": {"food": -3, "service": -2}}
    path = os.path.join(tmp, "drift.jsonl")
    v5 = [mention("Other One"), mention("Other Two", food="good")]
    write_run(path, [rec(f"comment:{a}", 0, {a: v5 + [drifted]})])
    run = SV.Run(path, items)
    got = next(m for m in run.preds[0][a] if m["restaurant_raw"] == "Testaurant Alpha")
    check(run.schema == "v5", "the run is v5 by majority")
    check(got["aspects"]["food"] == "awful" and not got.get("_adapted"),
          "a drifted mention in a v5 run goes through the normalizer (levels, not old floats)")
    check(run.fixes["aspect_numeric_level"] == 2 and run.fixes["experience_missing"] == 1,
          "its repairs are counted")
    old = {"restaurant_raw": "Tong", "aspects": {"food": 0.3}, "is_negated": False}
    path = os.path.join(tmp, "old.jsonl")
    write_run(path, [rec(f"comment:{a}", 0, {a: [old, dict(old, restaurant_raw="Keens")]})])
    run = SV.Run(path, items)
    check(run.schema == "old" and all(m.get("_adapted") for m in run.preds[0][a]), "an old run is adapted")


def test_catalog():
    calls = []
    real = providers._load_catalog
    try:
        providers._catalog, providers._catalog_failed_at = None, 0.0
        providers._load_catalog = lambda days: (calls.append(1), {})[1]
        check(providers.catalog() == {} and providers._catalog is None, "a failed load is not cached")
        check(providers.catalog() == {} and len(calls) == 1, "and is not retried on every call")
        providers._catalog_failed_at = 0.0

        def slow(days):
            import time as _t
            calls.append(1)
            _t.sleep(0.05)
            return {"x/y": {"pricing": {}}}
        providers._load_catalog = slow
        calls.clear()
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(8) as pool:
            got = list(pool.map(lambda _: providers.catalog(), range(16)))
        check(len(calls) == 1 and all("x/y" in g for g in got), f"concurrent callers load once ({len(calls)})")
    finally:
        providers._load_catalog = real
        providers._catalog, providers._catalog_failed_at = None, 0.0


def test_prices_and_thinking():
    p = lambda m: [round(x * 1e6, 4) for x in providers.prices("anthropic", m)]  # noqa: E731
    check(p("claude-opus-5-5") == [4.0, 20.0, 0.2, 5.0], f"Opus 5.5 reads at 0.05x input ({p('claude-opus-5-5')})")
    check(p("claude-sonnet-5-5") == [2.0, 10.0, 0.2, 2.5], "Sonnet 5.5 reads at 0.1x")
    check(p("claude-haiku-5-5") == [0.1, 0.5, 0.01, 0.125], "Haiku 5.5 reads at 0.1x")
    check(p("claude-opus-5") == [5.0, 25.0, 0.5, 6.25], "Opus 5 reads at 0.1x")
    try:
        providers.check_opts("openrouter", {"thinking": "disabled"})
        check(False, "--thinking on OpenRouter must be refused")
    except SystemExit:
        pass
    providers.check_opts("anthropic", {"thinking": "disabled"})
    kw = providers.anthropic_request("claude-haiku-5-5", "s", "u", {"thinking": "disabled", "effort": "low"})
    check(kw["thinking"] == {"type": "disabled"} and kw["output_config"] == {"effort": "low"},
          "the Anthropic path sends the thinking and effort it is tagged with")


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
            test_temperature()
            test_moderation_403(tmp)
            test_rep_coverage_and_set_cost(tmp)
            test_run_level_schema(tmp)
            test_complete_reps(tmp)
    finally:
        if saved is None:
            os.environ.pop("OPENROUTER_API_KEY", None)
        else:
            os.environ["OPENROUTER_API_KEY"] = saved
    install()
    providers._catalog = None
    test_integer_levels()
    test_catalog()
    test_prices_and_thinking()
    test_real_gold()
    if FAILS:
        raise SystemExit(f"{len(FAILS)} checks failed")
    print("selftest_v5 ok")


if __name__ == "__main__":
    main()
