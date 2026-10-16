"""Regression checks for v4's tooling. No database, no model.

    python eval/v4/selftest.py

1. Misattachment: a deep chain rendered consecutively, past the depth-6
   indentation cap, counts as no misattachment, and production's
   time-ordered rendering of siblings still does.
2. labels.py (v5): export fails, writing nothing, on an invalid thread id, a
   packet labeled twice, a contract or format failure or a missing label,
   and succeeds on a clean pass. Its gold passes the v5 gold validator, its
   run holds contract mentions only, a non-quality avoid is accepted and
   tagged c2_nonquality, and --batch checks one labeler's file.
3. compare_v4 and next_round read v5 labels: the labels scored against
   their own gold are perfect, and a run that softens an avoid into a bare
   endorsement shows up as a miss and as stuck_default.
4. batches.py never crashes when a duplicate has nowhere to go, never puts
   both copies of an item in one batch, and every batch file carries the v5
   prompt of its own mode.
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
import compare_v4 as CV  # noqa: E402
import next_round as NR  # noqa: E402
import score as S  # noqa: E402


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


ITEMS = [
    {"item_id": "s0001", "kind": "comment", "mode": "comment", "comment_id": "t1_s", "thread_id": "t3_s",
     "inputs": {"thread": {"chunk_index": 0, "short_ids": {"1": "t1_s"}}},
     "tags": [], "split": "tuning", "draw": "random", "stratum": "none", "weight": 10.0},
    {"item_id": "t001", "kind": "thread", "mode": "thread", "thread_id": "t3_t", "chunk_index": 0,
     "thread_chunks": [{"chunk_index": 0, "short_ids": {"1": "t1_a", "2": "t1_b"}}],
     "comments": [{"comment_id": "t1_a", "short_id": 1, "tags": []}, {"comment_id": "t1_b", "short_id": 2, "tags": []}],
     "tags": [], "split": "tuning", "draw": "random", "stratum": "none", "weight": 5.0},
]


def label_dir(lines_by_batch, pass_name="same_input"):
    d = tempfile.mkdtemp(prefix="v4-selftest-")
    os.makedirs(os.path.join(d, "keys"))
    os.makedirs(os.path.join(d, "labels", pass_name))
    key = {"pc": {"item_id": "s0001", "mode": "comment", "copy": 0, "batch": "b001"},
           "pt": {"item_id": "t001", "mode": "thread", "copy": 0, "batch": "b002",
                  "short_ids": {"1": "t1_a", "2": "t1_b"}}}
    with open(os.path.join(d, "keys", pass_name + ".json"), "w") as f:
        json.dump(key, f)
    with open(os.path.join(d, "items.jsonl"), "w") as f:
        for it in ITEMS:
            f.write(json.dumps(it) + "\n")
    for b, lines in lines_by_batch.items():
        with open(os.path.join(d, "labels", pass_name, b + ".jsonl"), "w") as f:
            for rec in lines:
                f.write(json.dumps(rec) + "\n")
    return d


def mention(name, **extra):
    """A v5 label mention: contract keys plus the two required metadata keys."""
    m = {"restaurant_raw": name, "neighborhood_hint": None, "reference_only": False,
         "aspects": {"food": None, "value": None, "service": None, "atmosphere": None, "wait": None},
         "is_negated": False, "price": None, "experience": "unclear", "dishes_liked": [],
         "dishes_disliked": [], "dishes_mentioned": [], "descriptors": [],
         "canonical_name": name, "rationale": "test"}
    for k, v in extra.items():
        if k in m["aspects"]:
            m["aspects"][k] = v
        else:
            m[k] = v
    return m


def thread(*ms):
    return {"packet_id": "pt", "output": {"mentions": list(ms)}}


def expect_refused(lines, what, pass_name="same_input"):
    d = label_dir(lines, pass_name)
    try:
        L.export(d, pass_name)
    except L.LabelError as e:
        assert e.code, what      # a nonzero exit
    else:
        raise AssertionError(f"export accepted {what}")
    for s in (".gold.jsonl", ".run.jsonl"):
        assert not os.path.exists(os.path.join(d, "labels", pass_name + s)), what


def check_label_export():
    good_c = {"packet_id": "pc", "output": {"mentions": [mention("Lucali", food="good", experience="ate_there")]}}
    good_t = thread({"id": 2, **mention("Di Fara")},
                    {"id": 1, **mention("Green Bowl", is_negated=True, descriptors=["all seafood"])})

    d = label_dir({"b001": [good_c], "b002": [good_t]})
    L.export(d, "same_input")
    gold = [json.loads(l) for l in open(os.path.join(d, "labels", "same_input.gold.jsonl"))]
    assert {g["comment_id"]: len(g["mentions"]) for g in gold} == {"t1_s": 1, "t1_a": 1, "t1_b": 1}, gold
    nq = next(m for g in gold for m in g["mentions"] if m["canonical_name"] == "Green Bowl")
    assert nq["conventions"] == {"c2_nonquality": {"food": "bad"}} and nq["aspects"]["food"] is None, nq
    run = [json.loads(l) for l in open(os.path.join(d, "labels", "same_input.run.jsonl"))]
    for r in run:
        for ms in r["mentions_by_comment"].values():
            for m in ms:
                assert list(m) == L.CONTRACT, f"run mentions must be contract-only: {list(m)}"

    # One labeler's file checks on its own; the other batch's packet is not "missing".
    _, got, errors, missing = L.read_pass(d, "same_input", batch="b001")
    assert list(got) == ["pc"] and not errors and not missing

    bad = {
        "an invalid thread id": {"b001": [good_c], "b002": [thread({"id": 9, **mention("X")})]},
        "a duplicate label": {"b001": [good_c, good_c], "b002": [good_t]},
        "a float aspect": {"b001": [{"packet_id": "pc", "output": {"mentions": [mention("X", food=0.6)]}}],
                           "b002": [good_t]},
        "an unknown key": {"b001": [{"packet_id": "pc", "output": {"mentions": [mention("X", dishes=[])]}}],
                           "b002": [good_t]},
        "an id on a comment packet": {"b001": [{"packet_id": "pc", "output": {"mentions": [mention("X", id=1)]}}],
                                      "b002": [good_t]},
        "a reference with an opinion": {"b001": [{"packet_id": "pc", "output": {"mentions": [
            mention("X", reference_only=True, food="good")]}}], "b002": [good_t]},
        "an avoid with only positive aspects": {"b001": [{"packet_id": "pc", "output": {"mentions": [
            mention("X", is_negated=True, food="good")]}}], "b002": [good_t]},
        "a closed place that is not a reference": {"b001": [{"packet_id": "pc", "output": {"mentions": [
            mention("X", descriptors=["closed"])]}}], "b002": [good_t]},
        "a missing rationale": {"b001": [{"packet_id": "pc", "output": {"mentions": [
            {k: v for k, v in mention("X").items() if k != "rationale"}]}}], "b002": [good_t]},
        "the same place twice in a comment": {"b001": [{"packet_id": "pc", "output": {"mentions": [
            mention("Lucali"), mention("lucali")]}}], "b002": [good_t]},
        "a dish verdict with food null (c1)": {"b001": [{"packet_id": "pc", "output": {"mentions": [
            mention("X", dishes_liked=["slice"])]}}], "b002": [good_t]},
        "needs_context on the same_input pass": {"b001": [{"packet_id": "pc", "output": {"mentions": [
            mention("X", needs_context=True)]}}], "b002": [good_t]},
        "a missing label": {"b001": [good_c]},
    }
    for what, lines in bad.items():
        expect_refused(lines, what)
    L.export(label_dir(bad["a missing label"]), "same_input", allow_missing=True)
    # needs_context is allowed in full_context and marks the mode unresolvable.
    d = label_dir({"b001": [{"packet_id": "pc", "output": {"mentions": [
        mention("Okiku", food="meh", experience="ate_there", needs_context=True, named_in="ancestor")]}}],
        "b002": [good_t]}, "full_context")
    L.export(d, "full_context")
    g = next(json.loads(l) for l in open(os.path.join(d, "labels", "full_context.gold.jsonl"))
             if json.loads(l)["comment_id"] == "t1_s")
    assert g["mentions"][0]["resolvable_comment_mode"] is False and g["mentions"][0]["resolvable_thread_mode"]
    print("label export ok")


def check_scoring():
    """Labels scored against their own gold are perfect; softening an avoid
    into a bare endorsement is a miss and a stuck_default."""
    good_c = {"packet_id": "pc", "output": {"mentions": [
        mention("Bridge Diner", food="bad", is_negated=True, experience="ate_there", descriptors=["tourist trap"])]}}
    good_t = thread({"id": 2, **mention("Di Fara")}, {"id": 1, **mention("Okiku", reference_only=True)})
    d = label_dir({"b001": [good_c], "b002": [good_t]})
    L.export(d, "same_input")
    ref = S.load_jsonl(os.path.join(d, "labels", "same_input.gold.jsonl"))
    alias, excluded = S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json")
    run_path = os.path.join(d, "labels", "same_input.run.jsonl")
    res = CV.score_run("labels", [run_path], ref, ITEMS, alias, excluded, both_modes=True)["metrics"]["all"]
    for k in ("mention_recall", "negative_mention_recall", "reference_only_recall", "bare_endorsement_recall",
              "is_negated_recall", "sign_accuracy"):
        assert res[k] == 1.0, (k, res[k])
    assert res["drop_rate"] == 0 and res["mention_precision"] == 1.0, res

    soft = {"call_key": "comment:t1_s", "rep": 0, "mode": "comment", "json_ok": True, "error": None,
            "mentions_by_comment": {"t1_s": [L.contract(mention("Bridge Diner"))]}}
    sp = os.path.join(d, "soft.jsonl")
    with open(sp, "w") as f:
        f.write(json.dumps(soft) + "\n")
    res = CV.score_run("soft", [sp], ref, ITEMS, alias, excluded)["metrics"]["all"]
    assert res["negative_mention_recall"] == 0 and res["is_negated_recall"] == 0, res
    reps, _, _ = CV.load_runs([sp], ITEMS)
    gline = next(g for g in ref if g["comment_id"] == "t1_s")
    F = NR.failures(gline, reps[0]["t1_s"], alias, excluded)
    assert {"missed_negative", "missed_negation", "stuck_default", "scored_milder"} <= F, F
    print("v5 scoring ok")


def check_batches():
    for n in (1, 2, 3, 13, 25):
        packets = [{"item_id": f"s{i:04d}", "mode": "comment", "same_input": "x", "full_context": "x"}
                   for i in range(n)]
        cut = B.cut(packets, "same_input")
        for _, units in cut:
            items = [u[1]["item_id"] for u in units]
            assert len(items) == len(set(items)), "both copies of an item in one batch"
            assert len(units) <= B.BATCH_SIZE
        assert sum(len(u) for _, u in cut) == n + len(B.duplicates(packets))
    prompts = B.load_prompts()
    for mode in ("comment", "thread"):
        p = {"item_id": "x", "mode": mode, "same_input": "INPUT", "full_context": "CONTEXT"}
        text = B.render_batch("b001", [("abcd1234", p, 0)], "same_input", prompts)
        assert prompts[mode][0] in text and prompts[mode][1] not in text, f"{mode} batch must carry its prompt, no hash"
        other = prompts["thread" if mode == "comment" else "comment"][0]
        assert other not in text, f"{mode} batch carries the other mode's prompt"
    print("batches ok")


if __name__ == "__main__":
    check_misattachment()
    check_label_export()
    check_scoring()
    check_batches()
    print("selftest ok")
