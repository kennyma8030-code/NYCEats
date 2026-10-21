"""Grade thread-mode runs: packets for judges, scores against round 4's answers. No database, no model.

    python eval/thread_v6/review.py finals             # rebuild round 4's sealed key locally, check it
    python eval/thread_v6/review.py provisional RUN    # fresh targets scored against round 4's finals
    python eval/thread_v6/review.py packets RUN [RUN ...] --sample-chunks 12
    python eval/thread_v6/review.py check              # every packet item judged once, valid
    python eval/thread_v6/review.py score              # -> eval/thread_v6/review/report.json, .md
    python eval/thread_v6/review.py posts RUN --postreview DIR   # [0] against post mode, same posts
    python eval/thread_v6/review.py cost RUN [RUN ...]  # $ per 1,000 comments, output fit a + b * items

Judging is round 4's (eval/review_v6r4/RUBRIC.md, whose rules are the
prompt's), with RUBRIC_THREAD.md here for what thread mode adds: the input
is a chunk of numbered comments, and the post itself can be item [0]. The
judgment line is round 4's, one per item, and eval/review_v6r4/judgments.py
checks and scores it, imported, so the two reviews cannot drift.

The fresh 300 compare with comment mode's 0.79 like this. Round 4's judges
left finals (the right answer) for every fresh comment. A thread-mode output
that equals its comment's finals is right and needs no judge, as round 4's
medium output took low's finals where the two were the same. Every other
output is judged afresh, blind, by the same rubric, so item_ok_rate is
computed exactly as it was for comment mode. `finals` first rebuilds round
4's sealed key (which items were planted) from the committed run files,
since build.py is deterministic, and checks that the rebuilt packets equal
the committed ones byte for byte and that comment mode's fresh-med score
comes out at 0.791 again.

The whole-thread slices (recent, big) have no earlier answers: a sample of
chunks is judged item by item, every numbered comment and the post, so a
mention filed under the wrong comment shows up (an output mention that is
not in its item's finals but is in another item's of the same chunk is
counted as misattributed). The post ([0]) is judged wherever it was an item.

About 8% of judged items show an output with one planted change, round 3's
five kinds plus one for thread mode (a place moved in from another item of
the same chunk). Which items, and the salt that picked them, are in
eval/thread_v6/.sealed/, which git ignores and judges must not open. The salt
is random, so unlike round 4's key this one cannot be rebuilt from the repo.
"""

import argparse
import collections
import copy
import hashlib
import importlib.util
import json
import os
import random
import secrets
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
R4_DIR = os.path.join(EVAL, "review_v6r4")
SEALED = os.path.join(HERE, ".sealed")
OUT = os.path.join(HERE, "review")
PACKETS = os.path.join(OUT, "packets")
JUDGMENTS = os.path.join(OUT, "judgments")
RUNS = os.path.join(EVAL, "runs")
R4_LOW = os.path.join(RUNS, "claude-haiku-5-5__979dcd6b9267__comment__bench6-low-r4_schema.jsonl")
R4_MED = os.path.join(RUNS, "claude-haiku-5-5__979dcd6b9267__comment__bench6-med-r4_schema.jsonl")
PER_PACKET = 25
PLANT_SHARE = 0.08
FOREIGN = "foreign_mention"
sys.path.insert(0, HERE)
import chunked as TC  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Round 4's checker and its helpers (round 3's J3, the adapter), as they ran.
J4 = _load("review_v6r4_judgments", os.path.join(R4_DIR, "judgments.py"))
B4 = J4.B
J3 = B4.J3
B3 = B4.B3
A = B4.A
KINDS = list(B3.KINDS) + [FOREIGN]


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)


# ---------------------------------------------------------------- round 4's finals
def r4_paths():
    p = B4.Paths(os.path.join(SEALED, "r4"))
    p.judgments = os.path.join(R4_DIR, "judgments")      # the committed judgments, read only
    return p


def rebuild_r4():
    """Rebuild round 4's packets and sealed key into .sealed/r4, and check them."""
    for path in (R4_LOW, R4_MED):
        if not os.path.exists(path):
            raise SystemExit(f"{path} is missing: git checkout origin/extraction-v6 -- {os.path.relpath(path, EVAL)}")
    paths = r4_paths()
    shutil.rmtree(paths.base, ignore_errors=True)
    B4.build(R4_LOW, R4_MED, paths=paths, quiet=True)
    B4.build_fresh_med(paths=paths, med_path=R4_MED, quiet=True)
    mine = sorted(os.listdir(paths.packets))
    theirs = sorted(os.listdir(os.path.join(R4_DIR, "packets")))
    if mine != theirs:
        raise SystemExit(f"rebuilt packets differ in names: {set(mine) ^ set(theirs)}")
    for fn in mine:
        a = open(os.path.join(paths.packets, fn), "rb").read().replace(b"\r\n", b"\n")
        b = open(os.path.join(R4_DIR, "packets", fn), "rb").read().replace(b"\r\n", b"\n")
        if a != b:
            raise SystemExit(f"rebuilt {fn} differs from eval/review_v6r4/packets/{fn}: the key would be wrong")
    return paths


def r4_finals(paths=None):
    """({(source, comment_id): finals}, {(source, comment_id): planted skips}, {(source, cid): rejected names}),
    computed exactly as round 4's aggregate() does."""
    paths = paths or r4_paths()
    if not os.path.exists(paths.key):
        raise SystemExit("round 4's key is not rebuilt yet: run `review.py finals` first")
    key = json.load(open(paths.key, encoding="utf-8"))
    got, problems, items = J4.read(paths)
    finals, rejected, skips = {}, {}, collections.defaultdict(set)
    for iid, meta in key["items"].items():
        k = (meta["source"], meta["comment_id"])
        if iid in got:
            finals[k] = J4.final_places(got[iid], items[iid]["shown"])
            rejected[k] = [c.get("name") for c in got[iid].get("compare") or []
                           if c.get("field") == "_mention" and c.get("final") is None]
        p = meta.get("planted")
        if p:
            skips[k].add((p["mention"], p["field"]))
    for a in key["auto"]:
        low_k = (a["same_as"], a["comment_id"])
        if low_k in finals:
            finals[(a["source"], a["comment_id"])] = finals[low_k]
            rejected[(a["source"], a["comment_id"])] = rejected.get(low_k, [])
            skips[(a["source"], a["comment_id"])] = skips.get(low_k, set())
    return finals, skips, rejected


def fresh_targets():
    return [it["comment_id"] for it in load_jsonl(os.path.join(EVAL, "fresh", "items.jsonl"))]


def cmd_finals(_args):
    paths = rebuild_r4()
    finals, skips, _ = r4_finals(paths)
    raw = J4.raw_outputs(R4_MED)
    acc = collections.Counter()
    for cid in fresh_targets():
        k = ("fresh-med", cid)
        if k in finals and cid in raw:
            J4.score(B4.shown_form(raw[cid]), finals[k], skips.get(k), acc)
    s = J4.summary(acc)
    want = json.load(open(os.path.join(R4_DIR, "report.json"), encoding="utf-8"))["by_source"]["fresh-med"]
    print(f"round 4 rebuilt in {paths.base}: packets identical to the committed ones")
    print(f"comment mode, fresh-med, rescored here: item_ok_rate {s['item_ok_rate']}, recall {s['mention_recall']}, "
          f"precision {s['mention_precision']} (report.json: {want['item_ok_rate']}, {want['mention_recall']}, "
          f"{want['mention_precision']})")
    if s["item_ok_rate"] != want["item_ok_rate"] or s["mention_recall"] != want["mention_recall"]:
        raise SystemExit("the rescored baseline does not match round 4's report; do not trust comparisons")


# ---------------------------------------------------------------- thread run records
def run_chunks(path):
    """[record] for a thread-slice run file (one per chunk, rep 0, the last answered one wins)."""
    out = {}
    for r in load_jsonl(path):
        if r.get("rep", 0) == 0 and r.get("chunk") and (r.get("raw") is not None or r["call_key"] not in out):
            out[r["call_key"]] = r
    return list(out.values())


def by_item(records):
    """{item id: (record, shown mentions)} over the items a run graded."""
    out = {}
    for r in records:
        if r.get("raw") is None:
            continue
        for i in r["item_ids"]:
            ms = (r.get("mentions_by_comment") or {}).get(i, [])
            out[i] = (r, B4.shown_form(ms))
    return out


def run_source(path):
    """A run file's source label for reports: its tag, e.g. fresh-med32k."""
    base = os.path.basename(path)
    return base.split("__")[3].rsplit("_schema", 1)[0].replace(".jsonl", "") if base.count("__") >= 3 else base


def cmd_provisional(args):
    """Fresh targets scored against round 4's fresh-med finals, before any new judging. An output
    mention that matches no final counts against precision only if a judge rejected that name;
    otherwise it is unjudged, and the packets send those items to a judge."""
    finals, skips, rejected = r4_finals()
    for path in args.runs:
        got = by_item(run_chunks(path))
        acc = collections.Counter()
        same = 0
        for cid in fresh_targets():
            k = ("fresh-med", cid)
            if cid not in got or k not in finals:
                continue
            shown = got[cid][1]
            J4.score(shown, finals[k], skips.get(k), acc, rejected=rejected.get(k, []))
            same += B4.equal_to_finals(shown, finals[k])
        s = J4.summary(acc)
        print(f"{run_source(path)}: {s['items']} fresh targets, {same} equal to round 4's finals "
              f"(provisional item_ok_rate {s['item_ok_rate']}), recall {s['mention_recall']}, "
              f"precision {s['mention_precision']} over judged names, {s.get('unjudged_mentions', 0)} "
              f"mention(s) no judge has seen")


# ---------------------------------------------------------------- packets
def salt():
    path = os.path.join(SEALED, "salt")
    if not os.path.exists(path):
        os.makedirs(SEALED, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(16))
    return open(path, encoding="utf-8").read().strip()


def hsh(text):
    return hashlib.sha256(f"{salt()}|{text}".encode()).hexdigest()


def slice_threads():
    out = {}
    for fn in os.listdir(os.path.join(HERE, "slices")):
        if fn.endswith(".threads.jsonl"):
            for th in load_jsonl(os.path.join(HERE, "slices", fn)):
                out.setdefault(th["thread_id"], th)
    return out


def chunk_view(rec, threads):
    """The chunk exactly as the model saw it, redrawn from the slice (the same code drew it then)."""
    th = threads[rec["chunk"]["thread_id"]]
    tree = TC.T.Tree(th["comments"])
    ch = TC.T.Chunk(th["thread_id"], rec["chunk"]["post_item"],
                    [m for m in rec["chunk"]["members"] if m != th["thread_id"]])
    user, ids, _ = TC.T.render(ch, th.get("title"), th.get("selftext"), th["comments"], tree)
    if {str(k): v for k, v in ids.items()} != rec.get("id_map"):
        raise SystemExit(f"{rec['call_key']}: the slice no longer draws this chunk as it was sent")
    return user, ids, th, tree


def wider(th, tree, item):
    """The wider context for one item: the full post, every ancestor, the replies."""
    if item == th["thread_id"]:
        return {"title": th.get("title"), "selftext": th.get("selftext"), "ancestors": [], "author": th.get("author"),
                "body": "(the post itself is the item)", "replies": []}
    anc, p = [], tree.parent(item)
    while p:
        anc.append({"author": tree.rows[p].get("author"), "body": tree.rows[p].get("body")})
        p = tree.parent(p)
    return {"title": th.get("title"), "selftext": th.get("selftext"), "ancestors": anc[::-1],
            "author": tree.rows[item].get("author"), "body": tree.rows[item].get("body"),
            "replies": [{"author": tree.rows[k].get("author"), "body": tree.rows[k].get("body")}
                        for k in tree.kids.get(item, [])]}


def plant(item, k):
    """One planted change on a judged item, round 3's kinds in rotation plus a place moved
    in from another item of the same chunk. Returns (shown, record) or None."""
    order = KINDS[k % len(KINDS):] + KINDS[:k % len(KINDS)]
    for kind in order:
        if kind == FOREIGN:
            others = [m for m in item["neighbours"] if not any(J3.same(m.get("name"), x.get("name"))
                                                               for x in item["shown"])]
            if others:
                m = copy.deepcopy(others[0])
                return item["shown"] + [m], {"kind": kind, "mention": m.get("name"), "field": "_mention",
                                             "original": None, "shown": "present"}
            continue
        if not item["shown"]:
            continue
        res = B3.perturb(item["shown"], kind)
        if res:
            return res[0], {"kind": kind, **res[1]}
    return None


def render(name, group):
    """A packet: per chunk, the chunk once and the wider context of each judged item, a
    divider, then the output per judged item. Own reads for every item come first."""
    out = [f"# Thread-mode review packet {name}: {sum(len(g['items']) for g in group)} items in {len(group)} chunk(s)",
           "", "Judge every item with `eval/review_v6r4/RUBRIC.md` and `eval/thread_v6/RUBRIC_THREAD.md`. For each "
           "chunk, write your `own_read` for **every** item listed **before** reading below that chunk's divider. "
           f"Write one JSON line per item to `eval/thread_v6/review/judgments/{name}.jsonl`, in this order. Open "
           "nothing else: not `eval/runs/`, any `.sealed/` directory, gold or label files, other packets or "
           "judgments.", ""]
    for g in group:
        out += [f"## Chunk {g['chunk_key']}", "", "### What the model saw", "", B3.block(g["view"]), ""]
        for it in g["items"]:
            c = it["context"]
            out += [f"### {it['item_id']}: item [{it['bracket']}]" + (" (the post)" if it["bracket"] == 0 else
                                                                      f", comment {it['comment_id']}"), ""]
            if it["bracket"] == 0:
                out += ["**Full post body:**", "", B3.block(c["selftext"] or "(none)"), ""]
                continue
            if c["ancestors"]:
                out += ["**Every ancestor, oldest first:**", ""]
                out += [f"- u/{a.get('author') or '?'}: " + " ".join((a.get("body") or "").split()) for a in c["ancestors"]]
                out.append("")
            out += [f"**>>> THE COMMENT (u/{c['author'] or '?'}):**", "", B3.block(c["body"]), ""]
            if c["replies"]:
                out += ["**Replies:**", ""]
                out += [f"- u/{r.get('author') or '?'}: " + " ".join((r.get("body") or "").split())[:400]
                        for r in c["replies"]]
                out.append("")
        out += [B3.DIVIDER, ""]
        for it in g["items"]:
            out += [f"### {it['item_id']}: Haiku's output for item [{it['bracket']}]", "",
                    B3.block(json.dumps({"mentions": it["shown"]}, ensure_ascii=False, indent=1), "json"), ""]
    return "\n".join(out) + "\n"


def cmd_packets(args):
    """Packets for every run given: fresh targets whose output differs from round 4's finals
    (and the post wherever it was item [0]); for whole-thread slices, a sample of chunks, every
    item in them. Existing packets and judgments are kept: run once per batch of runs."""
    if os.path.exists(os.path.join(SEALED, "key.json")):
        raise SystemExit("packets were built already (.sealed/key.json exists); judge them, or move them away")
    finals = r4_finals()[0] if any("fresh" in run_source(p) for p in args.runs) else {}
    threads = slice_threads()
    fresh = set(fresh_targets())
    chunks, auto = [], []
    first_seen = {}       # item id -> (source, shown) of the first run that sends it to a judge
    for path in args.runs:
        src = run_source(path)
        recs = [r for r in run_chunks(path) if r.get("raw") is not None]
        whole = threads[recs[0]["chunk"]["thread_id"]].get("targets") is None if recs else False
        if whole:
            recs = sorted(recs, key=lambda r: hsh("sample|" + src + r["call_key"]))[:args.sample_chunks]
        for r in recs:
            view, ids, th, tree = chunk_view(r, threads)
            per = {i: B4.shown_form((r.get("mentions_by_comment") or {}).get(i, [])) for i in r["covers"]}
            items = []
            for n in sorted(ids):
                i = ids[n]
                if i not in r["item_ids"]:
                    continue
                if i in fresh and src.startswith("fresh") and ("fresh-med", i) in finals \
                        and B4.equal_to_finals(per[i], finals[("fresh-med", i)]):
                    auto.append({"source": src, "comment_id": i, "same_as": "fresh-med finals"})
                    continue
                # The same output for the same item from an earlier run (medium and low
                # agreeing, say) is judged once and takes that judgment, as round 4 did.
                prev = first_seen.get(i)
                if prev and B4.same_output(per[i], prev[1]):
                    auto.append({"source": src, "comment_id": i, "same_as": prev[0]})
                    continue
                first_seen.setdefault(i, (src, per[i]))
                neighbours = [m for j, ms in per.items() if j != i for m in ms]
                items.append({"source": src, "comment_id": i, "bracket": n, "shown": per[i],
                              "neighbours": neighbours, "context": wider(th, tree, i)})
            if items:
                chunks.append({"chunk_key": f"{src}:{r['call_key']}", "view": view, "items": items})
    todo = [it for g in chunks for it in g["items"]]
    planted, k = {}, 0
    for it in sorted(todo, key=lambda x: hsh("plant|" + x["source"] + x["comment_id"])):
        if k >= round(len(todo) * PLANT_SHARE):
            break
        res = plant(it, k)
        if res:
            planted[(it["source"], it["comment_id"])] = res
            k += 1
    random.Random(hsh("order")).shuffle(chunks)
    key = {"items": {}, "auto": auto, "runs": [os.path.relpath(p, EVAL) for p in args.runs]}
    n = 0
    for g in chunks:
        for it in g["items"]:
            n += 1
            it["item_id"] = f"T{n:04d}"
            p = planted.get((it["source"], it["comment_id"]))
            if p:
                it["shown"] = p[0]
            key["items"][it["item_id"]] = {"source": it["source"], "comment_id": it["comment_id"],
                                           "chunk_key": g["chunk_key"], "bracket": it["bracket"],
                                           **({"planted": p[1]} if p else {})}
    # Whole chunks per packet, and never one comment twice in a packet (two runs'
    # chunks of one thread go to different judges, so each reads it fresh).
    packets = []
    for g in chunks:
        ids = {it["comment_id"] for it in g["items"]}
        home = next((p for p in packets if sum(len(x["items"]) for x in p) + len(g["items"]) <= PER_PACKET
                     and not ids & {it["comment_id"] for x in p for it in x["items"]}), None)
        if home is None:
            packets.append([g])
        else:
            home.append(g)
    os.makedirs(PACKETS, exist_ok=True)
    os.makedirs(JUDGMENTS, exist_ok=True)
    for i, group in enumerate(packets, 1):
        name = f"t{i:03d}"
        with open(os.path.join(PACKETS, name + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(render(name, group))
        public = [{"item_id": it["item_id"], "comment_id": it["comment_id"], "bracket": it["bracket"],
                   "chunk": g["chunk_key"], "model_view": g["view"], "context": it["context"], "shown": it["shown"]}
                  for g in group for it in g["items"]]
        write_json(os.path.join(PACKETS, name + ".json"), {"packet": name, "items": public})
    write_json(os.path.join(SEALED, "key.json"), key)
    by = collections.Counter(v["source"] for v in key["items"].values())
    print(json.dumps({"packets": len(packets), "judged_items": n, "by_source": by, "auto_resolved": len(auto),
                      "planted": len(planted)}, indent=1))


# ---------------------------------------------------------------- checking and scoring
def paths():
    p = B4.Paths(OUT)
    p.key = os.path.join(SEALED, "key.json")
    return p


def cmd_check(_args):
    got, problems, items = J4.read(paths())
    print(f"{len(got)} of {len(items)} items judged, {len(problems)} problem(s)")
    for p in problems[:50]:
        print("  " + p)
    return 1 if problems or len(got) < len(items) else 0


def cmd_score(_args):
    """Per run: item_ok_rate, recall, precision, negative recall and field accuracy against the
    finals (round 4's for fresh outputs equal to them, the new judges' for the rest), the posts
    apart, misattributed mentions, and the planted catch rate."""
    key = json.load(open(paths().key, encoding="utf-8"))
    got, problems, items = J4.read(paths())
    r4f, r4s = r4_finals()[:2] if any(a["same_as"] == "fresh-med finals" for a in key["auto"]) else ({}, {})
    outputs = {}
    for p in key["runs"]:
        src = run_source(p)
        for i, (rec, shown) in by_item(run_chunks(os.path.join(EVAL, p))).items():
            outputs[(src, i)] = (rec, shown)
    finals, skips = {}, {}
    for iid, meta in key["items"].items():
        if iid in got:
            k = (meta["source"], meta["comment_id"])
            finals[k] = J4.final_places(got[iid], items[iid]["shown"])
            if meta.get("planted"):
                skips[k] = {(meta["planted"]["mention"], meta["planted"]["field"])}
    for a in key["auto"]:
        k = (a["source"], a["comment_id"])
        if a["same_as"] == "fresh-med finals":
            finals[k] = r4f[("fresh-med", a["comment_id"])]
            skips[k] = r4s.get(("fresh-med", a["comment_id"]), set())
        elif (a["same_as"], a["comment_id"]) in finals:
            finals[k] = finals[(a["same_as"], a["comment_id"])]
            skips[k] = skips.get((a["same_as"], a["comment_id"]), set())
    acc = collections.defaultdict(collections.Counter)
    misattributed = collections.Counter()
    by_chunk = collections.defaultdict(dict)
    for iid, meta in key["items"].items():
        by_chunk[meta["chunk_key"]][meta["comment_id"]] = (meta["source"], meta["comment_id"])
    for (src, cid), fin in finals.items():
        if (src, cid) not in outputs:
            continue
        rec, shown = outputs[(src, cid)]
        group = src + ("-posts" if cid.startswith("t3_") else "")
        J4.score(shown, fin, skips.get((src, cid)), acc[group])
        # A mention that is not in this item's finals but is in another judged item's of the same chunk.
        others = [finals[k] for k in by_chunk.get(f"{src}:{rec['call_key']}", {}).values()
                  if k != (src, cid) and k in finals]
        for m in shown:
            if any(J3.same(m.get("name"), n) for n, _ in fin):
                continue
            if any(J3.same(m.get("name"), n) for f in others for n, _ in f):
                misattributed[group] += 1
    report = {"judged": len(got), "expected": len(key["items"]), "problems": problems[:100],
              "auto_resolved": collections.Counter(a["source"] for a in key["auto"]),
              "by_source": {s: J4.summary(a) for s, a in sorted(acc.items())},
              "misattributed_mentions": dict(misattributed),
              "baseline_comment_mode_fresh_med": json.load(open(os.path.join(R4_DIR, "report.json"),
                                                                encoding="utf-8"))["by_source"]["fresh-med"]}
    catch = collections.defaultdict(lambda: [0, 0])
    for iid, meta in key["items"].items():
        p = meta.get("planted")
        if not p or iid not in got:
            continue
        fin = J4.final_places(got[iid], items[iid]["shown"])
        if p["kind"] == "drop_mention":
            hit = any(J3.same(n, p["mention"]) for n, _ in fin)
        elif p["kind"] == FOREIGN:
            hit = not any(J3.same(n, p["mention"]) for n, _ in fin)
        elif p["kind"] == "drop_dish":
            hit = any(J3.same(n, p["mention"]) and any(J3.S.lenient_same(d, p["field"][5:]) for d in f["dishes"])
                      for n, f in fin)
        else:
            hit = any(J3.same(n, p["mention"]) and f.get(p["field"]) != p["shown"] for n, f in fin)
        catch[p["kind"]][0] += hit
        catch[p["kind"]][1] += 1
    report["planted_catch_rate"] = {k: {"caught": v[0], "n": v[1]} for k, v in sorted(catch.items())}
    write_json(os.path.join(OUT, "report.json"), report)
    lines = ["# Thread-mode review", "", f"Judged {len(got)} of {len(key['items'])} items.", "",
             "| | items | item_ok_rate | mention_recall | mention_precision | negative_recall |", "|---|---:|---:|---:|---:|---:|"]
    b = report["baseline_comment_mode_fresh_med"]
    lines.append(f"| comment mode, fresh-med (round 4) | {b['items']} | {b['item_ok_rate']} | {b['mention_recall']} | "
                 f"{b['mention_precision']} | {b['negative_recall']} |")
    for s, v in report["by_source"].items():
        lines.append(f"| {s} | {v['items']} | {v['item_ok_rate']} | {v['mention_recall']} | {v['mention_precision']} | "
                     f"{v['negative_recall']} |")
    lines += ["", f"Misattributed mentions: {report['misattributed_mentions']}",
              f"Planted catch: {report['planted_catch_rate']}"]
    with open(os.path.join(OUT, "report.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


# ---------------------------------------------------------------- posts against post mode
def post_mode_outputs(folder):
    """{thread_id: [mention]} from the post-review files (post mode's production answers)."""
    out, cur = {}, None
    for fn in sorted(os.listdir(folder)):
        if not fn.startswith("batch"):
            continue
        for line in open(os.path.join(folder, fn), encoding="utf-8"):
            if line.startswith("########## ITEM"):
                cur = line.split("|")[1].strip()
                out[cur] = []
            elif cur and line.startswith("* entity_key=") and "| raw=" in line:
                out[cur].append(json.loads(line.split("| raw=", 1)[1]))
    return out


def cmd_posts(args):
    """Each graded post that thread mode extracted as [0], beside post mode's answer for it: the
    same places with the same values, or what differs. Where they agree, the owner's post-mode
    grade carries over; the rest is what to read."""
    pm = post_mode_outputs(args.postreview)
    rows = []
    for path in args.runs:
        for i, (rec, shown) in by_item(run_chunks(path)).items():
            if not i.startswith("t3_") or i not in pm:
                continue
            theirs = B4.shown_form(pm[i])
            same = B4.same_output(shown, theirs)
            names = lambda ms: sorted(m.get("name") for m in ms)  # noqa: E731
            rows.append({"run": run_source(path), "thread_id": i, "same": same, "thread_mode": names(shown),
                         "post_mode": names(theirs),
                         "diffs": [] if same else J4.diffs(theirs, shown)})
    write_json(os.path.join(OUT, "posts_vs_post_mode.json"), rows)
    n = len(rows)
    print(f"{n} post(s) compared, {sum(r['same'] for r in rows)} identical to post mode -> "
          f"{os.path.relpath(os.path.join(OUT, 'posts_vs_post_mode.json'), EVAL)}")


def cmd_cost(args):
    """What each run cost per 1,000 comments, and the output fit (tokens = a + b * items a
    chunk) to put in anthropic_v6.THREAD_OUTPUT before the production dry run prices the
    backlog."""
    for path in args.runs:
        recs = [r for r in run_chunks(path) if r.get("raw") is not None]
        if not recs:
            continue
        xs = [len(r["covers"]) for r in recs]
        ys = [(r.get("usage") or {}).get("completion_tokens") or 0 for r in recs]
        cost = sum(float((r.get("usage") or {}).get("cost") or 0) for r in recs)
        comments = sum(len([c for c in r["covers"] if not c.startswith("t3_")]) for r in recs)
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        var = sum((x - mx) ** 2 for x in xs)
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var if var else 0.0
        stops = collections.Counter(r.get("stop_reason") for r in recs)
        print(f"{run_source(path)}: {n} chunks, {comments} comments, ${cost:.4f}, "
              f"${cost / max(comments, 1) * 1000:.3f} per 1,000 comments | output {my:,.0f} a chunk, "
              f"max {max(ys):,}, fit {my - b * mx:,.0f} + {b:,.0f} an item | stops {dict(stops)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("cost")
    p.add_argument("runs", nargs="+")
    sub.add_parser("finals")
    p = sub.add_parser("provisional")
    p.add_argument("runs", nargs="+")
    p = sub.add_parser("packets")
    p.add_argument("runs", nargs="+")
    p.add_argument("--sample-chunks", type=int, default=12, help="chunks judged per whole-thread run")
    sub.add_parser("check")
    sub.add_parser("score")
    p = sub.add_parser("posts")
    p.add_argument("runs", nargs="+")
    p.add_argument("--postreview", required=True)
    args = ap.parse_args()
    sys.exit({"finals": cmd_finals, "provisional": cmd_provisional, "packets": cmd_packets, "check": cmd_check,
              "score": cmd_score, "posts": cmd_posts, "cost": cmd_cost}[args.cmd](args) or 0)


if __name__ == "__main__":
    main()
