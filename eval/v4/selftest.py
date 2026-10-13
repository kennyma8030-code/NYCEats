"""Regression checks for v4's tooling. No database, no model.

    python eval/v4/selftest.py

1. Misattachment: a deep chain rendered consecutively, past the depth-6
   indentation cap, counts as no misattachment, and production's
   time-ordered rendering of siblings still does.
2. labels.py export fails, writing nothing, on an invalid thread id, a
   packet labeled twice, a schema failure or a missing label, and succeeds
   on a clean pass.
3. batches.py never crashes when a duplicate has nowhere to go, and never
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
    check_batches()
    print("selftest ok")
