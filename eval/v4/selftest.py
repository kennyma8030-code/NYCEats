"""Regression checks for v4's tooling. No database, no model.

    python eval/v4/selftest.py

1. Misattachment: a deep chain rendered consecutively, past the depth-6
   indentation cap, counts as no misattachment, and production's
   time-ordered rendering of siblings still does.
2. labels.py export fails, writing nothing, on an invalid thread id, a
   packet labeled twice, a schema failure or a missing label, and succeeds
   on a clean pass.
   A pass the manifest marks v6 also fails on anything the strict v6
   schema rejects or on a key that is not the one the labels were made
   against, and exports the adapted mentions with the v6 original. check
   --batch fails on an unknown batch, export rejects --batch, and a changed
   renderer is reported as drift.
3. Scoring: the fixes' negative-overall rule skips closed and past
   mentions on both sides, next_round types failures with the same switch,
   and schema_errors refuses keywords it does not implement.
4. batches.py never crashes when a duplicate has nowhere to go, and never
   puts both copies of an item in one batch.
"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import batches as B  # noqa: E402
import corpus  # noqa: E402
import labels as L  # noqa: E402


def comment(cid, parent, depth):
    return corpus.C(cid, "t3_x", parent, None, depth, "u", "body " * 5, None, "", False, None, False, False)


def check_misattachment():
    # A chain 11 deep, each reply right under its parent: indentation stops at
    # 6, but every line's parent is the line above it.
    chain = [comment("c0", None, 0)] + [comment(f"c{i}", f"c{i - 1}", i) for i in range(1, 11)]
    assert corpus.count_misattached(chain) == 0, "consecutive deep chain must read correctly"
    # Crossing the cap: depth 5 -> 6 -> 7 -> 8.
    cross = [comment("p5", None, 5), comment("p6", "p5", 6), comment("p7", "p6", 7), comment("p8", "p7", 8)]
    assert corpus.count_misattached(cross) == 0
    # Production's time order: A, B (reply to A), C (reply to A), D (reply to B).
    # D is indented one step under C, so it reads as a reply to C.
    timed = [comment("A", None, 0), comment("B", "A", 1), comment("C", "A", 1), comment("D", "B", 2)]
    assert corpus.count_misattached(timed) == 1
    # Depth-first order of the same thread reads correctly.
    tree = [timed[0], timed[1], timed[3], timed[2]]
    assert corpus.count_misattached(tree) == 0
    # Two replies to the same capped parent: the second is flush with the
    # first and can only be read as replying to it.
    siblings = [comment("P", None, 6), comment("X", "P", 7), comment("Y", "P", 7)]
    assert corpus.count_misattached(siblings) == 1
    print("misattachment ok")


def label_dir(lines_by_batch):
    d = tempfile.mkdtemp(prefix="v4-selftest-")
    os.makedirs(os.path.join(d, "keys"))
    os.makedirs(os.path.join(d, "labels", "same_input"))
    key = {"pc": {"item_id": "s0001", "mode": "comment", "copy": 0, "batch": "b001"},
           "pt": {"item_id": "t001", "mode": "thread", "copy": 0, "batch": "b002",
                  "short_ids": {"1": "t1_a", "2": "t1_b"}}}
    with open(os.path.join(d, "keys", "same_input.json"), "w") as f:
        json.dump(key, f)
    items = [{"item_id": "s0001", "kind": "comment", "mode": "comment", "comment_id": "t1_s", "thread_id": "t3_s"},
             {"item_id": "t001", "kind": "thread", "mode": "thread", "thread_id": "t3_t", "chunk_index": 0,
              "comments": [{"comment_id": "t1_a", "short_id": 1}, {"comment_id": "t1_b", "short_id": 2}]}]
    with open(os.path.join(d, "items.jsonl"), "w") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")
    for b, lines in lines_by_batch.items():
        with open(os.path.join(d, "labels", "same_input", b + ".jsonl"), "w") as f:
            for rec in lines:
                f.write(json.dumps(rec) + "\n")
    return d


def mention(name, **extra):
    m = {"restaurant_raw": name, "neighborhood_hint": None, "dishes": [], "descriptors": [],
         "aspects": {"food": 0.3, "value": None, "service": None, "atmosphere": None, "wait": None},
         "expensiveness": None, "is_firsthand": True, "is_negated": False}
    m.update(extra)
    return m


def check_label_export():
    good_c = {"packet_id": "pc", "output": {"mentions": [mention("Lucali")]}}
    good_t = {"packet_id": "pt", "output": {"mentions": [mention("Di Fara", id=2)]}}

    d = label_dir({"b001": [good_c], "b002": [good_t]})
    L.export(d, "same_input")
    gold = [json.loads(l) for l in open(os.path.join(d, "labels", "same_input.gold.jsonl"))]
    assert {g["comment_id"]: len(g["mentions"]) for g in gold} == {"t1_s": 1, "t1_a": 0, "t1_b": 1}, gold

    bad = {
        "invalid thread id": {"b001": [good_c], "b002": [{"packet_id": "pt", "output": {"mentions": [mention("X", id=9)]}}]},
        "duplicate label": {"b001": [good_c, good_c], "b002": [good_t]},
        "schema failure": {"b001": [{"packet_id": "pc", "output": {"mentions": [
            mention("X", aspects={"food": 2, "value": None, "service": None, "atmosphere": None, "wait": None})]}}],
            "b002": [good_t]},
        "missing label": {"b001": [good_c]},
    }
    for what, lines in bad.items():
        d = label_dir(lines)
        try:
            L.export(d, "same_input")
        except L.LabelError as e:
            assert e.code, what      # a nonzero exit
        else:
            raise AssertionError(f"export accepted a {what}")
        assert not os.path.exists(os.path.join(d, "labels", "same_input.gold.jsonl")), what
        assert not os.path.exists(os.path.join(d, "labels", "same_input.run.jsonl")), what
    L.export(label_dir(bad["missing label"]), "same_input", allow_missing=True)
    print("label export ok")


def v6_mention(name, **extra):
    m = {"name": name, "named_in": "comment", "location": None, "experience": "firsthand",
         "opinion": "stated", "overall": "negative",
         "aspects": {"taste": "positive", "value": None, "service": None, "atmosphere": None, "wait": None},
         "avoid": False, "dishes": [], "price": None, "timeframe": "current", "trend": None,
         "status": None, "tags": [], "notes": []}
    m.update(extra)
    return m


def check_v6_label_export():
    """A pass the manifest marks v6 must validate strictly against the v6
    schema; anything less (a missing field, an extra key, a bad level, an id
    on a comment packet) refuses the whole export."""
    def v6_dir(lines):
        d = label_dir(lines)
        key = json.load(open(os.path.join(d, "keys", "same_input.json")))
        fp = L.key_fingerprint(key)
        with open(os.path.join(d, "keys", "same_input.meta.json"), "w") as f:
            json.dump({"renderer": "v6", "short_ids_sha256": fp}, f)
        with open(os.path.join(d, "labels", L.MANIFEST), "w") as f:
            json.dump({"same_input": {"schema": "v6", "prompts": {},
                                      "key": {"renderer": "v6", "short_ids_sha256": fp}}}, f)
        return d

    good_c = {"packet_id": "pc", "output": {"mentions": [v6_mention("Lucali")]}}
    good_t = {"packet_id": "pt", "output": {"mentions": [dict(id=2, **v6_mention("Di Fara"))]}}
    d = v6_dir({"b001": [good_c], "b002": [good_t]})
    L.export(d, "same_input")
    gold = {g["comment_id"]: g for g in map(json.loads, open(os.path.join(d, "labels", "same_input.gold.jsonl")))}
    g = gold["t1_s"]["mentions"][0]
    assert g["aspects"]["food"] == 2 and g["v6"]["overall"] == "negative", g
    assert len(gold["t1_b"]["mentions"]) == 1 and not gold["t1_a"]["mentions"]

    no_notes = v6_mention("X")
    del no_notes["notes"]
    bad = {
        "missing field": {"b001": [{"packet_id": "pc", "output": {"mentions": [no_notes]}}], "b002": [good_t]},
        "bad level": {"b001": [{"packet_id": "pc", "output": {"mentions": [v6_mention("X", overall="mid")]}}],
                      "b002": [good_t]},
        "id on a comment packet": {"b001": [{"packet_id": "pc", "output": {"mentions": [dict(id=1, **v6_mention("X"))]}}],
                                   "b002": [good_t]},
        "extra top-level key": {"b001": [{"packet_id": "pc", "output": {"mentions": [], "notes": "x"}}],
                                "b002": [good_t]},
        "thread id outside the packet": {"b001": [good_c],
                                         "b002": [{"packet_id": "pt", "output": {"mentions": [dict(id=7, **v6_mention("X"))]}}]},
        "thread mention without id": {"b001": [good_c], "b002": [{"packet_id": "pt", "output": {"mentions": [v6_mention("X")]}}]},
        "production-shaped mention": {"b001": [{"packet_id": "pc", "output": {"mentions": [mention("X")]}}],
                                      "b002": [good_t]},
    }
    for what, lines in bad.items():
        d = v6_dir(lines)
        try:
            L.export(d, "same_input")
        except L.LabelError as e:
            assert e.code, what
        else:
            raise AssertionError(f"v6 export accepted a {what}")
        assert not os.path.exists(os.path.join(d, "labels", "same_input.gold.jsonl")), what

    # The key must be the one the labels were made against. A key rebuilt
    # with another renderer, or with other bracket numbers, refuses export.
    for what, change in (("renderer", production_renderer),
                         ("bracket numbers", renumber),
                         ("missing meta", lambda d: os.remove(os.path.join(d, "keys", "same_input.meta.json")))):
        d = v6_dir({"b001": [good_c], "b002": [good_t]})
        change(d)
        try:
            L.export(d, "same_input")
        except L.LabelError as e:
            assert e.code, what
        else:
            raise AssertionError(f"v6 export accepted a key with a different {what}")
        assert not os.path.exists(os.path.join(d, "labels", "same_input.gold.jsonl")), what

    # check --batch fails on a batch the key does not have; export rejects --batch.
    d = v6_dir({"b001": [good_c], "b002": [good_t]})
    for argv, ok in ((["check", "--pass", "same_input", "--dir", d, "--batch", "b001"], True),
                     (["check", "--pass", "same_input", "--dir", d, "--batch", "b999"], False),
                     (["export", "--pass", "same_input", "--dir", d, "--batch", "b001"], False)):
        sys.argv = ["labels.py"] + argv
        try:
            L.main()
            code = 0
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        assert (code == 0) == ok, (argv, code)

    # Drift: a changed renderer, builder or schema since labeling is reported.
    spec = {"inputs": L.input_fingerprints(), "prompts": L.prompt_fingerprints()}
    assert not L.drift(spec), L.drift(spec)
    spec["inputs"]["thread_renderer"] = dict(spec["inputs"]["thread_renderer"], sha256="0" * 64)
    assert any("thread_renderer" in w for w in L.drift(spec))
    print("v6 label export ok")


def production_renderer(d):
    """Rewrite the key's meta as if packets.py had run with --renderer production."""
    meta = os.path.join(d, "keys", "same_input.meta.json")
    rec = json.load(open(meta))
    json.dump(dict(rec, renderer="production"), open(meta, "w"))


def renumber(d):
    """Swap a thread packet's bracket numbers, as a different renderer would."""
    path = os.path.join(d, "keys", "same_input.json")
    key = json.load(open(path))
    key["pt"]["short_ids"] = {"1": "t1_b", "2": "t1_a"}
    json.dump(key, open(path, "w"))


def check_scoring():
    """score.py's fixes count a current negative v6 overall as a negative on
    both sides, but not a closed place or a past verdict; next_round types
    failures with the same switch; schema_errors refuses keywords it does not
    implement and reads additionalProperties as JSON Schema does."""
    import score as S
    import v6_adapter as A
    import next_round as NR

    def v6(overall, **kw):
        return {"name": "X", "named_in": "comment", "location": None, "experience": "firsthand",
                "opinion": "stated", "overall": overall,
                "aspects": {"taste": "positive", "value": None, "service": None, "atmosphere": None, "wait": None},
                "avoid": False, "dishes": [], "price": None, "timeframe": kw.get("timeframe", "current"),
                "trend": None, "status": kw.get("status"), "tags": [], "notes": []}

    alias, excluded = {}, {}
    gold_of = lambda m: L.as_gold_mention(A.adapt(m), alias, excluded)  # noqa: E731
    now, closed, past = v6("negative"), v6("negative", status="closed"), v6("negative", timeframe="past")
    assert S.gold_negative(gold_of(now), True) and not S.gold_negative(gold_of(now))
    assert not S.gold_negative(gold_of(closed), True) and not S.gold_negative(gold_of(past), True)
    assert S.model_negative(A.adapt(now), True) and not S.model_negative(A.adapt(past), True)

    line = {"mentions": [gold_of(now)]}
    model_pos = [A.adapt(v6("positive"))]
    assert "missed_negative" in NR.failures(line, model_pos, alias, excluded, "comment", fixes=True)
    assert "missed_negative" not in NR.failures(line, model_pos, alias, excluded, "comment", fixes=False)
    assert "missed_negative" not in NR.failures(line, [A.adapt(now)], alias, excluded, "comment", fixes=True)

    closed_schema = {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": False}
    assert A.schema_errors({"a": "x", "b": 1}, closed_schema) == ["$: extra key b"]
    assert A.schema_errors({"a": "x", "b": 1}, dict(closed_schema, additionalProperties=True)) == []
    assert A.schema_errors({"a": "x", "b": 1}, dict(closed_schema, additionalProperties={"type": "string"}))
    for bad in ({"type": "string", "maxLength": 3}, {"type": "array", "minItems": 1}, {"$ref": "other.json#/x"}):
        try:
            A.schema_errors("x", bad)
        except A.UnsupportedSchema:
            continue
        raise AssertionError(f"schema_errors ignored {bad}")
    print("scoring ok")


def check_batches():
    for n in (1, 2, 3, 21, 41):
        packets = [{"item_id": f"s{i:04d}", "mode": "comment", "same_input": "x", "full_context": "x"}
                   for i in range(n)]
        cut = B.cut(packets, "same_input")
        for _, units in cut:
            items = [u[1]["item_id"] for u in units]
            assert len(items) == len(set(items)), "both copies of an item in one batch"
        assert sum(len(u) for _, u in cut) == n + len(B.duplicates(packets))
    print("batches ok")


if __name__ == "__main__":
    check_misattachment()
    check_label_export()
    check_v6_label_export()
    check_scoring()
    check_batches()
    print("selftest ok")
