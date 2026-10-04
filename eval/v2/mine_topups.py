"""Mine comments similar to each thin v2 weakness, for BLIND labeling.

    EVAL_DB_URL=postgresql://... python eval/v2/mine_topups.py

The stored extraction is used only to FIND candidates (the same rule as v1
sampling); it is never written to the output, and labeling packets
(eval/packet.py --v2) show no model output. Comments already in v1 or v2 are
excluded. Candidates are drawn in md5(seed||id) order up to each weakness's
deficit to 25. Writes eval/v2/topup_items.jsonl (same item shape as v1 single
comments, plus mined_for).
"""

import collections
import hashlib
import json
import os
import re
import sys

V2 = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(V2)
sys.path.insert(0, EVAL)
import build_items as B  # noqa: E402

SEED = "nyceats-v2-topup"
TARGET = 25
I = re.IGNORECASE
NEG_MILD = re.compile(r"\b(mid|overrated|overhyped|not worth|meh|disappointing|underwhelming|just ok|nothing special|bland)\b", I)
NEG_STRONG = re.compile(r"(\bworst\b|disgusting|got sick|food poisoning|never again|never going back|inedible|terrible|awful|\bgross\b)", I)
POS_STRONG = re.compile(r"\b(best|amazing|incredible|favorite|favourite|phenomenal|outstanding|unreal|perfect)\b", I)
VALUE = re.compile(r"(overpriced|over priced|rip ?off|highway robbery|not worth the (money|price)|too expensive|for that price|\$\d+ for)", I)
CLOSED = re.compile(r"\b(closed|shut down|RIP|no longer (open|there)|went out of business|used to be (on|at))\b", I)
AVOID_LIST = re.compile(r"\b(skip|avoid|stay away from)\b[^.!?\n]{0,60}\b(and|or|,)\b", I)
REFERENCE = re.compile(r"\b(haven'?t been|never been|on my list|haven'?t tried|been meaning to|want to try)\b", I)
SERVICE_ATM = re.compile(r"\b(service|staff|waiter|server|rude|friendly|vibe|atmosphere|room|decor|loud|music|line|wait|reservation)\b", I)
PLACEHOLDER = re.compile(r"^(the |a |that |this )?(one|place|spot|cart|truck|guy|shop|deli|site)\b", I)
DISHES = {"pizza", "parm", "bagel", "bagels", "ramen", "pho", "tacos", "taco", "burger", "dumplings", "slice",
          "cheesesteak", "banh mi", "croissant", "cookie", "sandwich", "pastrami", "biryani"}

POOL = """
with mc as (
  select comment_id, count(*) n, array_agg(restaurant_raw) raws, array_agg(entity_key) keys,
         array_agg(coalesce((aspects->>'food')::float, 99)) foods,
         array_agg(coalesce((aspects->>'value')::float, 99)) vals,
         array_agg(least(coalesce((aspects->>'food')::float, 9), coalesce((aspects->>'value')::float, 9),
                         coalesce((aspects->>'service')::float, 9), coalesce((aspects->>'atmosphere')::float, 9),
                         coalesce((aspects->>'wait')::float, 9))) mins,
         array_agg((aspects->>'service' is not null or aspects->>'atmosphere' is not null)) svc_atm,
         array_agg(is_negated) negs
  from mentions group by 1)
select c.id, c.thread_id, coalesce(c.depth, 0) depth, c.body, c.extracted_with, t.title,
       c.parent_comment_id, p.id is not null parent_present,
       coalesce(m.n, 0) n, m.raws, m.keys, m.foods, m.vals, m.mins, m.svc_atm, m.negs,
       coalesce(pm.n, 0) pn, coalesce(gm.n, 0) gn
from comments c join threads t on t.id = c.thread_id
left join comments p on p.id = c.parent_comment_id
left join mc m on m.comment_id = c.id
left join mc pm on pm.comment_id = p.id
left join mc gm on gm.comment_id = p.parent_comment_id
where c.extracted_at is not null and c.body not in ('[deleted]', '[removed]') and length(c.body) > 15
"""


def match_weakness(r, rkeys):
    """Weaknesses this comment is a candidate for (heuristics; stored output used to find only)."""
    b, n = r["body"], r["n"]
    raws = r["raws"] or []
    foods = [f for f in (r["foods"] or []) if f != 99]
    mins = [m for m in (r["mins"] or []) if m != 9]
    out = set()
    lines = [l for l in b.splitlines() if l.strip()]
    if len(lines) >= 5 and 0 < n < len(lines) - 2 and len(b) < 1500:
        out.add("dropped_in_list")
    if n == 0 and len(b) < 400 and any(k in b.lower() for k in rkeys.get(r["thread_id"], ())):
        out.add("dropped_named_mention")
    if n == 0 and REFERENCE.search(b) and re.search(r"[a-z] [A-Z][a-z]+", b):
        out.add("dropped_reference_mention")
    if CLOSED.search(b) and n > 0:
        out.add("closed_place")
    if r["depth"] >= 3 and r["gn"] > 0 and r["pn"] == 0 and n == 0 and len(b) < 300:
        out.add("context_gap")
    if NEG_MILD.search(b) and foods and max(foods) > 0 and len(b) < 400:
        out.add("negative_softened_to_positive")
    if NEG_STRONG.search(b) and mins and min(mins) > -0.9 and len(b) < 500:
        out.add("softened_negative")
    if (POS_STRONG.search(b) and foods and min(foods) < 0) or (NEG_STRONG.search(b) and foods and max(foods) > 0):
        out.add("wrong_sign")
    if VALUE.search(b) and n > 0 and not any(v < 0 for v in (r["vals"] or []) if v != 99):
        out.add("missed_value_complaint")
    if AVOID_LIST.search(b) and n >= 2:
        out.add("negation_scope")
    if n > 0 and any(r["svc_atm"] or []) and not SERVICE_ATM.search(b) and len(b) < 300:
        out.add("inferred_aspect")
    if POS_STRONG.search(b) and 0.3 in foods and len(b) < 250:
        out.add("default_0.3")
    if any(PLACEHOLDER.search(x or "") for x in raws):
        out.add("hallucinated_place")
    if any((x or "").lower().startswith("their ") or (x or "").lower() in DISHES for x in raws):
        out.add("dish_as_place")
    if any((k or "") in DISHES for k in (r["keys"] or [])):
        out.add("wrong_target")
    return out


def h(x):
    return hashlib.md5((SEED + x).encode()).hexdigest()


def main():
    with open(os.path.join(V2, "counts.json"), encoding="utf-8") as f:
        counts = json.load(f)["per_weakness"]
    deficit = {w: TARGET - c["total"] for w, c in counts.items() if c["total"] < TARGET}
    used = set()
    for p in (os.path.join(EVAL, "items.jsonl"),):
        with open(p, encoding="utf-8") as f:
            for l in f:
                it = json.loads(l)
                used.add(it.get("comment_id"))
                used.update(c["comment_id"] for c in it.get("comments", []))
    conn = B.connect()
    cur = conn.cursor()
    # names mentioned anywhere upthread in the same thread: a comment that types one but got 0 mentions
    cur.execute("select c.thread_id, array_agg(distinct m.restaurant_raw) from mentions m "
                "join comments c on c.id = m.comment_id group by 1")
    rkeys = {tid: {(x or "").lower() for x in raws if x and len(x) >= 5} for tid, raws in cur.fetchall()}
    cur.execute(POOL)
    cols = [d[0] for d in cur.description]
    cands = collections.defaultdict(list)
    for row in cur.fetchall():
        r = dict(zip(cols, row))
        if r["id"] in used or (r["parent_comment_id"] and not r["parent_present"]):
            continue
        for w in match_weakness(r, rkeys) & set(deficit):
            cands[w].append(r)
    chosen, taken = [], set()
    for w in sorted(deficit, key=lambda w: len(cands[w])):
        got = 0
        for r in sorted(cands[w], key=lambda r: h(r["id"])):
            if got >= deficit[w]:
                break
            if r["id"] in taken:
                continue
            chosen.append((r, w))
            taken.add(r["id"])
            got += 1
    out = []
    rendered = {}
    for r, w in chosen:
        if r["thread_id"] not in rendered:
            rendered[r["thread_id"]] = B.thread_render(cur, r["thread_id"])
        tr = rendered[r["thread_id"]]
        ci, sid = tr["where"][r["id"]]
        chain, replies = B.ancestors_and_replies(cur, r["id"])
        row = next(x for x in tr["rows"] if x[0] == r["id"])
        out.append({
            "kind": "comment", "modes": ["comment", "thread"], "comment_id": r["id"], "thread_id": r["thread_id"],
            "mined_for": w, "production": B.prod_info(r["extracted_with"]),
            "inputs": {"comment": {"user_message": B.comment_input(cur, r["id"])},
                       "thread": {"chunk_index": ci, "n_chunks": len(tr["chunks"]), "short_id": sid,
                                  "short_ids": tr["chunks"][ci]["short_ids"],
                                  "user_message": tr["chunks"][ci]["user_message"]}},
            "context": {"thread_id": r["thread_id"], "permalink": row[5], "thread_title": tr["title"],
                        "thread_selftext": tr["selftext"], "thread_eligible_comments": len(tr["rows"]),
                        "depth": r["depth"], "author": row[2], "body": r["body"], "ancestors": chain, "replies": replies},
        })
    with open(os.path.join(V2, "topup_items.jsonl"), "w", encoding="utf-8") as f:
        for it in out:
            f.write(json.dumps(it, ensure_ascii=False, default=str) + "\n")
    print({w: (len(cands[w]), sum(1 for _, x in chosen if x == w), deficit[w]) for w in deficit})


if __name__ == "__main__":
    main()
