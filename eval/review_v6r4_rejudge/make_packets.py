"""A second, independent review of 150 fresh comments, to measure judge-against-judge agreement.

    python eval/review_v6r4_rejudge/make_packets.py      # packets r2_001..r2_006, RUBRIC.md, sealed key

The first review (eval/review_v6r4) judged every round-4 output once. How much of what it
reports is the judge rather than Haiku is unknown until a second judge reads the same
comments blind. This draws 150 of the 300 fresh held-out comments by seeded hash and shows
each with round 4's medium-effort output (the recommended setting), in exactly the first
review's blind-first format and rules, so agree.py can compare the two reviews' final
values field by field and give the error bar on Haiku's accuracy.

Nothing points back at the first review: new item ids (S001...), new packet names, a
rubric copy whose only changes are the files a judge may open and where to write, and a
sealed key of its own (.sealed/key.json: comment ids and about 6% planted changes, the same
five kinds as before). The first review's packets and judgments are only read, never
written.
"""

import hashlib
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
R4 = os.path.join(EVAL, "review_v6r4")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


J4 = _load("review_v6r4_judgments", os.path.join(R4, "judgments.py"))
B4 = J4.B
SEED = "nyceats-rejudge-v6r4"
N_ITEMS = 150
PER_PACKET = 25
PLANT_SHARE = 0.06
DIVIDER = B4.DIVIDER


def h(text):
    return hashlib.sha256(f"{SEED}|{text}".encode()).hexdigest()


class Paths(B4.Paths):
    def __init__(self, base=HERE):
        super().__init__(base)
        self.rubric = os.path.join(base, "RUBRIC.md")


FILES_RULE = """## Files you may open

Open only this file and your one packet
(`eval/review_v6r4_rejudge/packets/r2_NNN.md` or `.json`), and write only your judgment
file (`eval/review_v6r4_rejudge/judgments/r2_NNN.jsonl`). **Do not open** anything else
under `eval/review_v6r4_rejudge/` or anything at all under `eval/review_v6r4/` (its
packets, judgments, reports and rubric), nor `eval/review_v6/`, `eval/runs/`,
`eval/bench_v6/`, any `.sealed/` directory, any gold or label file (`eval/gold.jsonl`,
`eval/v2/gold.jsonl`, `eval/labels/`, `eval/v2/labels/`, `eval/v4/`), or other judges'
judgments. They hold earlier answers, sources or planted changes, and reading them spoils
the blind read.
"""


def rubric_text():
    """The first review's rubric with two changes only: the files section and the paths."""
    src = open(os.path.join(R4, "RUBRIC.md"), encoding="utf-8").read()
    i = src.index("## Files you may open")
    j = src.index("## The rules are the prompt's")
    out = src[:i] + FILES_RULE + "\n" + src[j:]
    out = out.replace("`eval/review_v6r4/judgments/pNNN.jsonl`", "`eval/review_v6r4_rejudge/judgments/r2_NNN.jsonl`")
    return out


def header(name, n):
    return [f"# Review packet {name}: {n} comments", "",
            "Judge every item with `eval/review_v6r4_rejudge/RUBRIC.md`. For each item, write your `own_read` "
            "**before** reading below the divider. Write one JSON line per item to "
            f"`eval/review_v6r4_rejudge/judgments/{name}.jsonl`, in this order. Open nothing else: nothing "
            "under `eval/review_v6r4/`, `eval/review_v6/`, `eval/runs/` or `eval/bench_v6/`, no `.sealed/` "
            "directory, no gold or label file, no other packet or judgment.", ""]


def render(name, items):
    body = B4.render(name, items)
    return "\n".join(header(name, len(items))) + "\n" + body[body.index("\n## "):].lstrip("\n")


def fresh_med_outputs(key_a):
    path = (key_a.get("runs_path_by_source") or {}).get("fresh-med") or key_a["runs_path"]["medium"]
    return B4.outputs(path)


def build(paths=Paths(), key_a_path=None, quiet=False):
    key_a = json.load(open(key_a_path or os.path.join(R4, ".sealed", "key.json"), encoding="utf-8"))
    med = fresh_med_outputs(key_a)
    fresh = [c for c in B4.comment_sets()["fresh"] if c in med]
    sample = sorted(fresh, key=lambda c: h("draw|" + c))[:N_ITEMS]
    rows, ctx = B4.rows_and_contexts()
    order = sorted(sample, key=lambda c: h("order|" + c))
    plant, k = {}, 0
    for cid in sorted(sample, key=lambda c: h("plant|" + c)):
        if k >= round(N_ITEMS * PLANT_SHARE):
            break
        if not med[cid]:
            continue
        kinds = B4.B3.KINDS[k % len(B4.B3.KINDS):] + B4.B3.KINDS[:k % len(B4.B3.KINDS)]
        for kind in kinds:
            res = B4.B3.perturb(med[cid], kind)
            if res:
                plant[cid] = (res[0], {"kind": kind, **res[1]})
                k += 1
                break
    run = (key_a.get("runs_path_by_source") or {}).get("fresh-med") or key_a["runs_path"]["medium"]
    items, key = [], {"items": {}, "runs_path": run, "seed": SEED}
    for n, cid in enumerate(order, 1):
        p = plant.get(cid)
        items.append({"item_id": f"S{n:03d}", "comment_id": cid, "model_view": B4.PC.build_user_message(rows[cid]),
                      "context": ctx[cid], "shown": p[0] if p else med[cid]})
        key["items"][f"S{n:03d}"] = {"comment_id": cid, **({"planted": p[1]} if p else {})}
    os.makedirs(paths.packets, exist_ok=True)
    for fn in os.listdir(paths.packets):
        os.remove(os.path.join(paths.packets, fn))
    names = []
    for i in range(0, len(items), PER_PACKET):
        name = f"r2_{i // PER_PACKET + 1:03d}"
        group = items[i:i + PER_PACKET]
        with open(os.path.join(paths.packets, name + ".md"), "w", encoding="utf-8") as f:
            f.write(render(name, group))
        with open(os.path.join(paths.packets, name + ".json"), "w", encoding="utf-8") as f:
            json.dump({"packet": name, "items": group}, f, ensure_ascii=False, indent=1)
        names.append(name)
    with open(paths.rubric, "w", encoding="utf-8") as f:
        f.write(rubric_text())
    os.makedirs(os.path.dirname(paths.key), exist_ok=True)
    with open(paths.key, "w", encoding="utf-8") as f:
        json.dump(key, f, ensure_ascii=False, indent=1, sort_keys=True)
    summary = {"items": len(items), "packets": names, "planted": len(plant)}
    if not quiet:
        print(json.dumps(summary))
    return summary


if __name__ == "__main__":
    build()
