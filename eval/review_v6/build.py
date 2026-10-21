"""Build the review packets: an Opus judge reads each comment, writes its own answer,
then grades Haiku's round-3 output. No database, no model.

    python eval/review_v6/build.py

Writes packets/rNNN.md and .json (~25 comments each, all 600 comments of the round-3
run) and the sealed key .sealed/key.json (gitignored; this script regenerates it
byte for byte).

Each item shows what the model saw (the comment-mode user message), the wider thread
context, and, below a divider, Haiku's output pretty-printed. Two kinds of items
check that judging is careful, and nothing in a packet marks them:
  * planted errors (~8%): Haiku's output with one change: an overall sign flipped,
    a mention dropped, a negative upgraded to very_positive, the experience changed,
    or a dish dropped;
  * round-1 substitutes (10): an item whose round-1 output was truncated or empty
    shows that output, the parsable part of it, in place of round 3's.
The key records which items these are and what changed.
"""

import copy
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
RUNS = os.path.join(EVAL, "runs")
R3 = os.path.join(RUNS, "claude-haiku-5-5__6b046d8ed65d__comment__bench6-low-r3_schema.jsonl")
R1 = [os.path.join(RUNS, "claude-haiku-5-5__a15cfb978cce__comment__bench6-med_schema.jsonl"),
      os.path.join(RUNS, "claude-haiku-5-5__a15cfb978cce__comment__bench6-low_schema.jsonl")]
PACKETS = os.path.join(HERE, "packets")
KEY = os.path.join(HERE, ".sealed", "key.json")
PER_PACKET = 25
PLANT_SHARE = 0.08
R1_SUBSTITUTES = 10
SEED = "nyceats-review-v6"
DIVIDER = "--- Haiku output below: write your own_read first ---"


def h(text):
    return hashlib.sha256(f"{SEED}|{text}".encode()).hexdigest()


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def run_records(path):
    out = {}
    for r in load_jsonl(path):
        if r.get("rep", 0) == 0 and (r.get("raw") is not None or r["call_key"] not in out):
            out[r["call_key"].split(":", 1)[1]] = r
    return out


def mentions_of(r):
    """Mention objects from a record: the parsed output, or the complete objects
    before the cut in a truncated one."""
    raw = r.get("raw") or ""
    try:
        return json.loads(raw).get("mentions") or []
    except Exception:
        pass
    start = raw.find("[")
    out, dec, i = [], json.JSONDecoder(), start + 1
    while 0 < i < len(raw):
        while i < len(raw) and raw[i] in " ,\n\t":
            i += 1
        try:
            obj, i = dec.raw_decode(raw, i)
        except json.JSONDecodeError:
            break
        out.append(obj)
    return out


def contexts():
    """{comment_id: (model view, wider context)} from the v1 and v2 items."""
    out = {}
    for it in load_jsonl(os.path.join(EVAL, "items.jsonl")):
        if it["kind"] == "thread":
            by = {c["comment_id"]: c for c in it["comments"]}
            kids = {}
            for c in it["comments"]:
                kids.setdefault(c.get("parent_comment_id"), []).append(c)
            for c in it["comments"]:
                anc, p = [], c.get("parent_comment_id")
                while p:
                    a = by.get(p)
                    if a is None:
                        anc.append({"author": None, "body": "(parent not available: deleted, or too short to keep)"})
                        break
                    anc.append({"author": a["author"], "body": a["body"]})
                    p = a.get("parent_comment_id")
                out[c["comment_id"]] = (c["comment_input"], {
                    "title": it["context"]["thread_title"], "selftext": it["context"]["thread_selftext"],
                    "ancestors": anc[::-1], "author": c["author"], "body": c["body"],
                    "replies": [{"author": k["author"], "body": k["body"]} for k in kids.get(c["comment_id"], [])]})
    for path in (os.path.join(EVAL, "items.jsonl"), os.path.join(EVAL, "v2", "items.jsonl")):
        for it in load_jsonl(path):
            if it["kind"] != "comment" or it["comment_id"] in out:
                continue
            ctx = it["context"]
            out[it["comment_id"]] = (it["inputs"]["comment"]["user_message"], {
                "title": ctx["thread_title"], "selftext": ctx["thread_selftext"],
                "ancestors": [{"author": a.get("author"), "body": a.get("body")} for a in ctx["ancestors"]],
                "author": ctx["author"], "body": ctx["body"],
                "replies": [{"author": r.get("author"), "body": r.get("body")} for r in ctx.get("replies", [])]})
    return out


# ---------------------------------------------------------------- planted errors
FLIP = {"positive": "negative", "negative": "positive", "very_positive": "very_negative",
        "very_negative": "very_positive"}


def perturb(ms, kind):
    """Apply one change; return (new mentions, record) or None if it doesn't apply."""
    ms = copy.deepcopy(ms)
    if kind == "flip_overall":
        for m in ms:
            if m.get("overall") in FLIP:
                old = m["overall"]
                m["overall"] = FLIP[old]
                return ms, {"mention": m["name"], "field": "overall", "original": old, "shown": m["overall"]}
    if kind == "drop_mention" and ms:
        m = ms.pop(0)
        return ms, {"mention": m["name"], "field": "_mention", "original": "present", "shown": None}
    if kind == "upgrade_negative":
        for m in ms:
            if m.get("overall") in ("negative", "very_negative"):
                old = m["overall"]
                m["overall"] = "very_positive"
                return ms, {"mention": m["name"], "field": "overall", "original": old, "shown": "very_positive"}
            for a, v in (m.get("aspects") or {}).items():
                if v in ("negative", "very_negative"):
                    m["aspects"][a] = "very_positive"
                    return ms, {"mention": m["name"], "field": f"aspects.{a}", "original": v, "shown": "very_positive"}
    if kind == "wrong_experience" and ms:
        m = ms[0]
        old = m.get("experience")
        m["experience"] = {"firsthand": "none", "none": "firsthand", "secondhand": "firsthand"}.get(old, "none")
        return ms, {"mention": m["name"], "field": "experience", "original": old, "shown": m["experience"]}
    if kind == "drop_dish":
        for m in ms:
            if m.get("dishes"):
                d = m["dishes"].pop(0)
                return ms, {"mention": m["name"], "field": f"dish:{d['dish']}", "original": d, "shown": None}
    return None


KINDS = ["flip_overall", "drop_mention", "upgrade_negative", "wrong_experience", "drop_dish"]


def block(text, lang="text"):
    return f"```{lang}\n" + (text or "").replace("```", "'''") + "\n```"


def render(name, items):
    out = [f"# Review packet {name}: {len(items)} comments", "",
           "Judge every item with `eval/review_v6/RUBRIC.md`. For each item, write your `own_read` "
           "**before** reading below the divider. Write one JSON line per item to "
           f"`eval/review_v6/judgments/{name}.jsonl`, in this order.", ""]
    for it in items:
        c = it["context"]
        out += [f"## {it['item_id']}: comment {it['comment_id']}", "",
                "### What the model saw", "", block(it["model_view"]), "",
                "### Wider thread context (the model did not see this)", "",
                f"**Title:** {c['title']}", "", "**Post body:**", "", block(c["selftext"] or "(none)"), ""]
        if c["ancestors"]:
            out += ["**Ancestors, oldest first:**", ""]
            out += [f"- u/{a.get('author') or '?'}: " + " ".join((a.get("body") or "").split()) for a in c["ancestors"]]
            out.append("")
        out += [f"**>>> THE COMMENT (u/{c['author'] or '?'}):**", "", block(c["body"]), ""]
        if c["replies"]:
            out += ["**Replies:**", ""]
            out += [f"- u/{r.get('author') or '?'}: " + " ".join((r.get("body") or "").split())[:400] for r in c["replies"]]
            out.append("")
        out += [DIVIDER, "", "### Haiku's output", "",
                block(json.dumps({"mentions": it["shown"]}, ensure_ascii=False, indent=1), "json"), ""]
    return "\n".join(out) + "\n"


def main():
    r3 = run_records(R3)
    r1 = [run_records(p) for p in R1]
    ctx = contexts()
    cids = sorted((c for c, r in r3.items() if r.get("raw") is not None), key=h)
    missing = [c for c in cids if c not in ctx]
    if missing:
        raise SystemExit(f"{len(missing)} comments have no context, e.g. {missing[:3]}")

    shown, key = {}, {}
    out3 = {c: mentions_of(r3[c]) for c in cids}
    # round-1 substitutes: truncated first, then empty outputs where round 3 found places
    subs = []
    for c in cids:
        for rr in r1:
            r = rr.get(c)
            if not r or r.get("raw") is None:
                continue
            if r.get("stop_reason") == "max_tokens" or (not mentions_of(r) and out3[c]):
                subs.append((0 if r.get("stop_reason") == "max_tokens" else 1, h("sub|" + c), c, r))
                break
    subs.sort()
    for _, _, c, r in subs[:R1_SUBSTITUTES]:
        shown[c] = mentions_of(r)
        key[c] = {"kind": "r1_substitute", "truncated": r.get("stop_reason") == "max_tokens",
                  "shown_mentions": len(shown[c]), "round3_mentions": len(out3[c])}
    # planted errors on items with at least one mention
    eligible = [c for c in sorted(cids, key=lambda x: h("plant|" + x)) if c not in key and out3[c]]
    n_plant = round(len(cids) * PLANT_SHARE)
    k = 0
    for c in eligible:
        if k >= n_plant:
            break
        order = KINDS[k % len(KINDS):] + KINDS[:k % len(KINDS)]
        for kind in order:
            res = perturb(out3[c], kind)
            if res:
                shown[c], rec = res
                key[c] = {"kind": kind, **rec}
                k += 1
                break
    items = []
    for n, c in enumerate(cids, 1):
        view, wider = ctx[c]
        items.append({"item_id": f"Q{n:04d}", "comment_id": c, "model_view": view, "context": wider,
                      "shown": shown.get(c, out3[c])})
    os.makedirs(PACKETS, exist_ok=True)
    for fn in os.listdir(PACKETS):
        os.remove(os.path.join(PACKETS, fn))
    packets = [items[i:i + PER_PACKET] for i in range(0, len(items), PER_PACKET)]
    for i, group in enumerate(packets, 1):
        name = f"r{i:03d}"
        with open(os.path.join(PACKETS, name + ".md"), "w", encoding="utf-8") as f:
            f.write(render(name, group))
        with open(os.path.join(PACKETS, name + ".json"), "w", encoding="utf-8") as f:
            json.dump({"packet": name, "items": group}, f, ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(KEY), exist_ok=True)
    by_item = {it["comment_id"]: it["item_id"] for it in items}
    with open(KEY, "w", encoding="utf-8") as f:
        json.dump({by_item[c]: dict(v, comment_id=c) for c, v in sorted(key.items(), key=lambda kv: by_item[kv[0]])},
                  f, ensure_ascii=False, indent=1)
    kinds = {}
    for v in key.values():
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    print(f"{len(items)} items in {len(packets)} packets; planted {kinds}")


if __name__ == "__main__":
    main()
