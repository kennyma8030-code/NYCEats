"""Build the round-4 review packets once steps n and o have run. No database, no model.

    python eval/review_v6r4/build.py                    # outputs of bench_v6 steps n (low) and o (medium)
    python eval/review_v6r4/build.py --low RUN [--medium RUN]

Same blind-first format as eval/review_v6 (round 3): each item shows what the model
saw, the wider thread context, a divider, then Haiku's output. The judge writes an own
read before looking, compares, and records final values (RUBRIC.md here, which carries
the owner's round-4 decisions). What gets judged:

  * round 3's 600 comments, low effort. The Opus finals from round 3 are reused where
    round 4's output equals them exactly (every place, every scored field, every dish),
    so only outputs that differ go to a judge. An old item is judged again anyway if
    its judge raised a rule question or marked a field "neither": those finals were
    unsettled, and most rule questions are exactly what the owner has since decided;
  * the 60 red-team hard cases and the 300 fresh held-out comments, low effort: all;
  * medium effort on the 600 and the 60, only where medium's output differs from low's.
    Medium's own item goes to a different packet than low's, so a judge reads the
    comment fresh; where medium equals low it takes low's result.

Haiku's output is shown as the counts will use it: the level labels mapped to the
owner's five (v6_adapter.normalize) and places of an excluded kind removed. Validators
are not applied; judgments.py scores with and without them.

Planted errors check that judging is careful, as in round 3: about 8% of the judged
items show an output with one change (an overall sign flipped, a mention dropped, a
negative upgraded to very_positive, the experience changed, a dish dropped). Which
items, which source (low or medium, which set) each item is, and which round-3 finals
were reused are all in .sealed/key.json, which the packets don't reference and this
script regenerates byte for byte from the run files.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
sys.path.insert(0, os.path.join(EVAL, "review_v6"))
import v6_adapter as A  # noqa: E402
import judgments as J3  # noqa: E402  round 3's checker: helpers and the old finals


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B3 = _load("review_v6_build", os.path.join(EVAL, "review_v6", "build.py"))
PC = _load("v6_comment_r4", os.path.join(EVAL, "prompts", "v6_comment.py"))

V1, V2 = os.path.join(EVAL, "items.jsonl"), os.path.join(EVAL, "v2", "items.jsonl")
HARD, FRESH = os.path.join(EVAL, "hard", "items.jsonl"), os.path.join(EVAL, "fresh", "items.jsonl")
SUBSET_600 = os.path.join(EVAL, "bench_v6", "subset_comment_r2.txt")
PER_PACKET = 25
PLANT_SHARE = 0.08
SEED = "nyceats-review-v6r4"
DIVIDER = B3.DIVIDER
ASPECTS = ("taste", "value", "service", "atmosphere", "wait")
# Every field a round-4 judge reads blind, plus price (graded after), compared exactly.
FIELDS = ["overall"] + [f"aspects.{a}" for a in ASPECTS] + ["experience", "opinion", "avoid",
                                                             "timeframe", "trend", "status", "price"]


def h(text):
    return hashlib.sha256(f"{SEED}|{text}".encode()).hexdigest()


class Paths:
    def __init__(self, base=HERE):
        self.base = base
        self.packets = os.path.join(base, "packets")
        self.judgments = os.path.join(base, "judgments")
        self.key = os.path.join(base, ".sealed", "key.json")


# ---------------------------------------------------------------- inputs
def comment_sets():
    """{set name: [comment ids]}: round 3's 600, the hard cases, the fresh draw."""
    six = sorted(k.split(":", 1)[1] for k in open(SUBSET_600, encoding="utf-8").read().split())
    hard = [json.loads(l)["comment_id"] for l in open(HARD, encoding="utf-8")]
    fresh = [json.loads(l)["comment_id"] for l in open(FRESH, encoding="utf-8")]
    return {"r600": six, "hard": hard, "fresh": fresh}


def rows_and_contexts():
    """({comment_id: comment_rows record}, {comment_id: wider context}) over every items file."""
    rows, ctx = {}, B3.contexts()
    for path in (V1, V2, HARD, FRESH):
        side = os.path.splitext(path)[0] + ".comment_rows.jsonl"
        for r in map(json.loads, open(side, encoding="utf-8")):
            rows[r["comment_id"]] = r
    for path in (HARD, FRESH):
        for it in map(json.loads, open(path, encoding="utf-8")):
            c = it["context"]
            ctx[it["comment_id"]] = (None, {
                "title": c["thread_title"], "selftext": c["thread_selftext"],
                "ancestors": [{"author": a.get("author"), "body": a.get("body") if not a.get("missing")
                               else "(parent not available)"} for a in c["ancestors"]],
                "author": c["author"], "body": c["body"],
                "replies": [{"author": r.get("author"), "body": r.get("body")} for r in c.get("replies", [])]})
    return rows, {cid: v[1] for cid, v in ctx.items()}


def outputs(path):
    """{comment_id: shown mentions} from a run file: owner level names, excluded kinds removed."""
    if not path or not os.path.exists(path):
        return {}
    out = {}
    for cid, r in B3.run_records(path).items():
        if r.get("raw") is None:
            continue
        out[cid] = shown_form(B3.mentions_of(r))
    return out


def shown_form(ms):
    return [A.normalize(m) for m in ms if isinstance(m, dict) and A.counted(m)]


# ---------------------------------------------------------------- equality with finals
def place_fields(m):
    """A mention reduced to what the finals record: the compared fields and the dishes."""
    out = {f: J3.get(m, f) for f in FIELDS}
    out["dishes"] = {d["dish"]: J3.dval(d) for d in m.get("dishes") or [] if isinstance(d, dict) and d.get("dish")}
    return out


def equal_to_finals(shown, finals):
    """True when an output names exactly the final places with exactly the final values."""
    if len(shown) != len(finals):
        return False
    used = set()
    for m in shown:
        j = next((i for i, (n, _) in enumerate(finals) if i not in used and J3.same(m.get("name"), n)), None)
        if j is None:
            return False
        used.add(j)
        mine, fin = place_fields(m), finals[j][1]
        if any(mine[f] != fin.get(f) for f in FIELDS):
            return False
        if len(mine["dishes"]) != len(fin["dishes"]):
            return False
        for dn, v in fin["dishes"].items():
            hv = next((x for d, x in mine["dishes"].items() if J3.S.lenient_same(d, dn)), "absent")
            if hv != v:
                return False
    return True


def same_output(a, b):
    """True when two outputs agree on every place, compared field and dish (low vs medium)."""
    return equal_to_finals(a, [(m.get("name"), place_fields(m)) for m in b])


def old_finals():
    """{comment_id: (finals [(name, fields)], unsettled)} from the round-3 review."""
    got, _, shown = J3.read()
    by_cid = {}
    for iid, j in got.items():
        fin = []
        for name, f, _, _ in J3.final_places(j, shown[iid]):
            fin.append((name, f))
        unsettled = bool(j.get("rule_questions")) or any(c.get("right") == "neither" for c in j.get("compare") or [])
        by_cid[j["comment_id"]] = (fin, unsettled, iid)
    return by_cid


# ---------------------------------------------------------------- render
def render(name, items):
    out = [f"# Review packet {name}: {len(items)} comments", "",
           "Judge every item with `eval/review_v6r4/RUBRIC.md`. For each item, write your `own_read` "
           "**before** reading below the divider. Write one JSON line per item to "
           f"`eval/review_v6r4/judgments/{name}.jsonl`, in this order.", ""]
    for it in items:
        c = it["context"]
        out += [f"## {it['item_id']}: comment {it['comment_id']}", "",
                "### What the model saw", "", B3.block(it["model_view"]), "",
                "### Wider thread context (the model did not see this)", "",
                f"**Title:** {c['title']}", "", "**Post body:**", "", B3.block(c["selftext"] or "(none)"), ""]
        if c["ancestors"]:
            out += ["**Ancestors, oldest first:**", ""]
            out += [f"- u/{a.get('author') or '?'}: " + " ".join((a.get("body") or "").split()) for a in c["ancestors"]]
            out.append("")
        out += [f"**>>> THE COMMENT (u/{c['author'] or '?'}):**", "", B3.block(c["body"]), ""]
        if c["replies"]:
            out += ["**Replies:**", ""]
            out += [f"- u/{r.get('author') or '?'}: " + " ".join((r.get("body") or "").split())[:400] for r in c["replies"]]
            out.append("")
        out += [DIVIDER, "", "### Haiku's output", "",
                B3.block(json.dumps({"mentions": it["shown"]}, ensure_ascii=False, indent=1), "json"), ""]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- build
def build(low_path, med_path, paths=Paths(), quiet=False):
    sets = comment_sets()
    rows, ctx = rows_and_contexts()
    low, med = outputs(low_path), outputs(med_path)
    finals3 = old_finals()
    key = {"items": {}, "auto": [], "missing_outputs": []}
    todo = []                          # (order key, source, comment_id, shown)
    for setname, cids in sets.items():
        for cid in cids:
            if cid not in low:
                key["missing_outputs"].append({"source": f"{setname}-low", "comment_id": cid})
                continue
            old = finals3.get(cid) if setname == "r600" else None
            if old and not old[1] and equal_to_finals(low[cid], old[0]):
                key["auto"].append({"source": f"{setname}-low", "comment_id": cid, "reused": old[2]})
            else:
                todo.append((0, h("low|" + cid), f"{setname}-low", cid, low[cid]))
            if setname == "fresh":
                continue
            if cid not in med:
                if med:
                    key["missing_outputs"].append({"source": f"{setname}-med", "comment_id": cid})
                continue
            if same_output(med[cid], low[cid]):
                key["auto"].append({"source": f"{setname}-med", "comment_id": cid, "same_as": f"{setname}-low"})
            elif old and not old[1] and equal_to_finals(med[cid], old[0]):
                key["auto"].append({"source": f"{setname}-med", "comment_id": cid, "reused": old[2]})
            else:
                todo.append((1, h("med|" + cid), f"{setname}-med", cid, med[cid]))
    todo.sort()
    # planted errors on judged items that have a mention, kinds rotating as in round 3
    plant = {}
    n_plant = round(len(todo) * PLANT_SHARE)
    k = 0
    for _, _, src, cid, shown in sorted(todo, key=lambda t: h("plant|" + t[2] + t[3])):
        if k >= n_plant:
            break
        if not shown:
            continue
        order = B3.KINDS[k % len(B3.KINDS):] + B3.KINDS[:k % len(B3.KINDS)]
        for kind in order:
            res = B3.perturb(shown, kind)
            if res:
                plant[(src, cid)] = (res[0], {"kind": kind, **res[1]})
                k += 1
                break
    items = []
    for n, (_, _, src, cid, shown) in enumerate(todo, 1):
        p = plant.get((src, cid))
        items.append({"item_id": f"R{n:04d}", "comment_id": cid,
                      "model_view": PC.build_user_message(rows[cid]), "context": ctx[cid],
                      "shown": p[0] if p else shown})
        key["items"][f"R{n:04d}"] = {"source": src, "comment_id": cid, **({"planted": p[1]} if p else {})}
    packets = [items[i:i + PER_PACKET] for i in range(0, len(items), PER_PACKET)]
    # A comment judged twice (low and medium) must not sit in one packet: swap the second
    # copy with an item of another packet where neither comment is already present.
    for pi, group in enumerate(packets):
        for ii in range(len(group)):
            cid = group[ii]["comment_id"]
            if not any(g["comment_id"] == cid for g in group[:ii]):
                continue                  # the first copy in this packet stays
            here = {g["comment_id"] for g in group}
            for qi, other in enumerate(packets):
                there = {g["comment_id"] for g in other}
                if qi == pi or cid in there:
                    continue
                j = next((x for x, g in enumerate(other) if g["comment_id"] not in here), None)
                if j is not None:
                    group[ii], other[j] = other[j], group[ii]
                    break
    assert all(len({g["comment_id"] for g in p}) == len(p) for p in packets), "a comment twice in a packet"
    os.makedirs(paths.packets, exist_ok=True)
    for fn in os.listdir(paths.packets):
        os.remove(os.path.join(paths.packets, fn))
    for i, group in enumerate(packets, 1):
        name = f"p{i:03d}"
        with open(os.path.join(paths.packets, name + ".md"), "w", encoding="utf-8") as f:
            f.write(render(name, group))
        with open(os.path.join(paths.packets, name + ".json"), "w", encoding="utf-8") as f:
            json.dump({"packet": name, "items": group}, f, ensure_ascii=False, indent=1)
    key["runs_path"] = {"low": low_path, "medium": med_path}
    os.makedirs(os.path.dirname(paths.key), exist_ok=True)
    with open(paths.key, "w", encoding="utf-8") as f:
        json.dump(key, f, ensure_ascii=False, indent=1, sort_keys=True)
    counts = {}
    for v in key["items"].values():
        counts[v["source"]] = counts.get(v["source"], 0) + 1
    auto = {}
    for v in key["auto"]:
        auto[v["source"]] = auto.get(v["source"], 0) + 1
    summary = {"judged_items": len(items), "packets": len(packets), "judged_by_source": counts,
               "auto_resolved_by_source": auto, "planted": len(plant),
               "missing_outputs": len(key["missing_outputs"])}
    if not quiet:
        print(json.dumps(summary, indent=1))
    return summary


def default_runs():
    sys.path.insert(0, EVAL)
    import bench_v6 as BV
    steps = {s["id"]: s for s in BV.STEPS}
    return BV.run_file(steps["n"], True), BV.run_file(steps["o"], True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--low", help="round-4 low-effort run file (default: bench_v6 step n's)")
    ap.add_argument("--medium", help="round-4 medium-effort run file (default: bench_v6 step o's)")
    a = ap.parse_args()
    low, med = default_runs()
    low, med = a.low or low, a.medium or med
    if not os.path.exists(low):
        raise SystemExit(f"{low} does not exist: run bench_v6 step n first")
    build(low, med if os.path.exists(med) else None)


if __name__ == "__main__":
    main()
