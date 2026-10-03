"""Build eval/items.jsonl: the extraction eval sample. Read-only against the DB.

    EVAL_DB_URL=postgresql://... python eval/build_items.py      # or DATABASE_URL

Every connection is opened read-only. The stored extraction (mention counts,
entity keys) is used ONLY to find candidates for the risk groups; it is never
written into items.jsonl, so labeling stays blind.

Sampling is deterministic: candidates in each group are ordered by
md5(SEED || comment_id), so re-running against the same data gives the same
items. See eval/sampling.md for the heuristics and the counts they produced.
"""

import collections
import datetime
import hashlib
import json
import os
import re
import sys

import psycopg2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import extract_threads  # noqa: E402  (CHUNK; imports db/extract, no side effects)
import prompt  # noqa: E402
import prompt_thread  # noqa: E402

SEED = "nyceats-eval-v1"
OUT = os.path.join(ROOT, "eval", "items.jsonl")
STATS = os.path.join(ROOT, "eval", "sampling_stats.json")

# Draw order matters: a comment is drawn for the first group that wants it,
# but is TAGGED with every group it matches. Rarer groups draw first.
TARGETS = [
    ("nameless_reply", 40),
    ("deep_chain", 30),
    ("strong_negative", 35),
    ("avoid_list_negation", 35),
    ("ambiguous_name", 25),
    ("out_of_scope", 25),
    ("long_list", 30),
    ("zero_mentions_suspicious", 50),
    ("messy_text", 25),
    ("random", 100),
]
THREAD_TARGETS = [("thread_long", 5), ("thread_title_names_place", 6),
                  ("thread_where_to_eat", 6)]
THREAD_COMMENT_BUDGET = 400

PROD_MODE = {"ca5439be83b3": "thread", "5b02ac883c80": "thread",
             "1d5bac550078": "comment", "0d75b20b5f83": "comment"}

# ---------------------------------------------------------------- heuristics
I = re.IGNORECASE
PLACE_WORDS = re.compile(r"\b(try|tried|go to|went to|spot|place|recommend|check out|"
                         r"love|loved|favorite|fav|go-to|get the|order the|"
                         r"pizzeria|deli|bakery|ramen|tacos?)\b", I)
CAP_MID = re.compile(r"[a-z,;:(] +[A-Z][A-Za-z'’&\-]{2,}")      # capitalized token mid-sentence
POSSESSIVE = re.compile(r"\b[A-Za-z]{2,}(?:'|’)s\b")
REC_TITLE = re.compile(r"\b(recommend|recs?|suggestions?|where|best|looking for|"
                       r"favorite|must[- ]try|help|ideas|go-to)\b", I)
NAMELESS = re.compile(r"^\W*(mid|overrated|underrated|this|same|agreed?|hard disagree|"
                      r"disagree|seconded|second(ed)? this|\+1|facts|so good|meh|"
                      r"yes+|no+|nah|lol no|truth|eh+|trash|it'?s fine|fine|"
                      r"came here to say this|this is the answer|was going to say)\b", I)
AVOID = re.compile(r"\b(avoid|skip|tourist trap|don'?t go|dont bother|don'?t bother|"
                   r"not worth|overrated|stay away|overhyped)\b", I)
STRONG_NEG = re.compile(r"(got sick|food poisoning|\brude\b|\bworst\b|never again|"
                        r"never going back|never go back|\bregret|disgusting|inedible)", I)
BULLET = re.compile(r"^\s*(?:[-*•+]|\d{1,2}[.)])\s+\S", re.M)
OUT_OF_SCOPE = re.compile(r"(whole foods|zabar|trader joe|chelsea market|eataly|food hall|"
                          r"time out market|urbanspace|essex market|dekalb market|"
                          r"mcdonald|chipotle|shake shack|starbucks|dunkin|sweetgreen|"
                          r"\bh ?mart\b|fairway|wine bar|cocktail bar|\bbodega\b|"
                          r"grocery|supermarket|costco|wegmans)", I)


def flags_for(r, amb_keys):
    """All risk groups a comment matches. r is a dict from the pool query."""
    body, n, depth = r["body"], r["n"], r["depth"]
    g = set()
    if n == 0 and PLACE_WORDS.search(body) and (
            CAP_MID.search(body) or POSSESSIVE.search(body)
            or (depth == 0 and REC_TITLE.search(r["title"] or ""))):
        g.add("zero_mentions_suspicious")
    if r["pn"] > 0 and depth >= 1 and len(body) <= 120 and (
            NAMELESS.search(body) or len(body) <= 50):
        g.add("nameless_reply")
    if AVOID.search(body):
        g.add("avoid_list_negation")
    if STRONG_NEG.search(body):
        g.add("strong_negative")
    if body.count("\n") >= 8 or len(BULLET.findall(body)) >= 4 or n >= 6:
        g.add("long_list")
    if depth >= 3 and r["gn"] > 0 and r["pn"] == 0 and len(body) <= 400:
        g.add("deep_chain")
    if amb_keys.intersection(r["keys"] or []):
        g.add("ambiguous_name")
    if OUT_OF_SCOPE.search(body):
        g.add("out_of_scope")
    if len(body) >= 1500 or (len(body) >= 60 and body == body.lower()
                             and re.search(r"[a-z]", body)):
        g.add("messy_text")
    return g


def h(x):
    return hashlib.md5((SEED + x).encode()).hexdigest()


# ---------------------------------------------------------------- db
POOL_SQL = """
with mc as (select comment_id, count(*) n, array_agg(entity_key) keys
            from mentions group by 1)
select c.id, c.thread_id, coalesce(c.depth, 0) depth, c.body, c.extracted_with,
       t.title, c.parent_comment_id, p.id is not null as parent_present,
       coalesce(m.n, 0) n, m.keys, coalesce(pm.n, 0) pn, coalesce(gm.n, 0) gn
from comments c
join threads t on t.id = c.thread_id
left join comments p on p.id = c.parent_comment_id
left join mc m on m.comment_id = c.id
left join mc pm on pm.comment_id = p.id
left join mc gm on gm.comment_id = p.parent_comment_id
where c.extracted_at is not null
  and c.body not in ('[deleted]', '[removed]')
  and length(c.body) > 15
"""

AMB_SQL = """
with k as (select entity_key, count(*) n from mentions group by 1 having count(*) >= 15)
select entity_key from k
where entity_key !~ ' ' and length(entity_key) >= 3
  and (select count(*) from restaurants r where r.name_key like k.entity_key || ' %%') >= 3
union
select entity_key from alias_overrides
"""

# Threads whose every eligible comment has a stored extraction, sized so a
# whole-thread label job stays bounded.
THREAD_SQL = """
select t.id, t.title, count(*) n,
       count(*) filter (where c.extracted_at is null) pending
from threads t
join comments c on c.thread_id = t.id
where c.body not in ('[deleted]', '[removed]') and length(c.body) > 15
group by t.id, t.title
having count(*) between 8 and 60 and count(*) filter (where c.extracted_at is null) = 0
"""

TOP_KEYS_SQL = """
select entity_key from mentions group by 1 order by count(*) desc limit 300
"""


def connect():
    url = os.environ.get("EVAL_DB_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("set EVAL_DB_URL or DATABASE_URL")
    conn = psycopg2.connect(url)
    conn.set_session(readonly=True)
    return conn


def thread_render(cur, thread_id):
    """Everything both modes need for one thread, rendered with the repo's own
    builders. Thread mode renders ALL eligible comments (not only pending ones,
    which is what production saw at the time) in extract_threads.py's order and
    CHUNK size."""
    cur.execute("select title, selftext, created_utc, num_comments from threads where id=%s",
                (thread_id,))
    title, selftext, created, num_comments = cur.fetchone()
    cur.execute("""
        select c.id, coalesce(c.depth, 0), c.author, c.body, c.parent_comment_id,
               c.permalink, c.extracted_with, c.score
        from comments c
        where c.thread_id = %s
          and c.body not in ('[deleted]', '[removed]') and length(c.body) > 15
        order by coalesce(c.root_comment_id, c.id), c.created_utc
    """, (thread_id,))
    rows = cur.fetchall()
    chunks = []
    where = {}
    for ci in range(0, len(rows), extract_threads.CHUNK):
        part = rows[ci:ci + extract_threads.CHUNK]
        nodes, ids = [], {}
        for i, (cid, depth, author, body, *_rest) in enumerate(part, start=1):
            nodes.append((i, depth, author, body))
            ids[i] = cid
            where[cid] = (len(chunks), i)
        chunks.append({"chunk_index": len(chunks),
                       "short_ids": {str(k): v for k, v in ids.items()},
                       "user_message": prompt_thread.build_message(title, selftext, nodes)})
    return {"title": title, "selftext": selftext, "created_utc": created.isoformat(),
            "num_comments": num_comments, "rows": rows, "chunks": chunks, "where": where}


def comment_input(cur, cid):
    cur.execute("""
        select c.body, t.title, t.selftext, p.body
        from comments c join threads t on t.id = c.thread_id
        left join comments p on p.id = c.parent_comment_id
        where c.id = %s""", (cid,))
    body, title, selftext, parent = cur.fetchone()
    return prompt.build_user_message(body, title, selftext, parent)


def ancestors_and_replies(cur, cid):
    """Full-thread context for the labeler: the whole ancestor chain (untruncated)
    and the direct replies. The rest of the thread is by reference (thread_id)."""
    chain = []
    cur.execute("select parent_comment_id from comments where id=%s", (cid,))
    pid = cur.fetchone()[0]
    while pid:
        cur.execute("select id, coalesce(depth,0), author, body, parent_comment_id "
                    "from comments where id=%s", (pid,))
        r = cur.fetchone()
        if not r:
            chain.append({"id": pid, "missing": True})
            break
        chain.append({"id": r[0], "depth": r[1], "author": r[2], "body": r[3]})
        pid = r[4]
    cur.execute("select id, coalesce(depth,0), author, body from comments "
                "where parent_comment_id=%s order by created_utc", (cid,))
    replies = [{"id": a, "depth": b, "author": c, "body": d} for a, b, c, d in cur.fetchall()]
    return list(reversed(chain)), replies


def prod_info(extracted_with):
    model, _, ph = (extracted_with or "").rpartition(":")
    return {"extracted_with": extracted_with, "model": model or None,
            "prompt_hash": ph or None, "mode": PROD_MODE.get(ph)}


def main():
    conn = connect()
    cur = conn.cursor()

    cur.execute(AMB_SQL)
    amb_keys = {r[0] for r in cur.fetchall()}

    cur.execute(POOL_SQL)
    cols = [d[0] for d in cur.description]
    pool = [dict(zip(cols, r)) for r in cur.fetchall()]
    orphans = {r["id"] for r in pool if r["parent_comment_id"] and not r["parent_present"]}
    pool = [r for r in pool if r["id"] not in orphans]
    for r in pool:
        r["groups"] = flags_for(r, amb_keys)

    # ---- whole threads first, so single-comment items can avoid them
    cur.execute(TOP_KEYS_SQL)
    top_keys = [k for (k,) in cur.fetchall() if len(k) >= 4]
    cur.execute(THREAD_SQL)
    tcands = cur.fetchall()
    def tgroups(tid, title, n):
        g = set()
        if n > extract_threads.CHUNK:
            g.add("thread_long")
        low = extract_threads.extract.normalize_entity(title)
        if any(re.search(r"\b" + re.escape(k) + r"\b", low) for k in top_keys) \
                or POSSESSIVE.search(title):
            g.add("thread_title_names_place")
        if REC_TITLE.search(title):
            g.add("thread_where_to_eat")
        return g
    tinfo = {tid: (title, n, tgroups(tid, title, n)) for tid, title, n, _ in tcands}
    tcount = collections.Counter(g for _, _, gs in tinfo.values() for g in gs)
    chosen_threads, budget = [], THREAD_COMMENT_BUDGET
    for grp, k in THREAD_TARGETS:
        picks = sorted((t for t, (_, n, gs) in tinfo.items()
                        if grp in gs and t not in {c for c, _ in chosen_threads}),
                       key=h)
        got = 0
        for t in picks:
            n = tinfo[t][1]
            # thread_long wants 2-3 chunks; the others stay small
            if grp == "thread_long" and not 26 <= n <= 60:
                continue
            if grp != "thread_long" and n > 30:
                continue
            if n > budget:
                continue
            chosen_threads.append((t, grp))
            budget -= n
            got += 1
            if got == k:
                break
    thread_ids = {t for t, _ in chosen_threads}

    # ---- single comments
    pool = [r for r in pool if r["thread_id"] not in thread_ids]
    gcount = collections.Counter(g for r in pool for g in r["groups"])
    gcount["random"] = len(pool)
    # Strata for population reweighting: every pool comment falls in exactly
    # one cell, the first risk group (in draw order) it matches, else "none".
    order = [g for g, _ in TARGETS if g != "random"]
    def stratum(groups):
        return next((g for g in order if g in groups), "none")
    strata = collections.Counter(stratum(r["groups"]) for r in pool)
    chosen, seen = [], set()
    for grp, k in TARGETS:
        cands = sorted((r for r in pool if (grp == "random" or grp in r["groups"])),
                       key=lambda r: h(r["id"]))
        got = 0
        for r in cands:
            if r["id"] in seen:
                continue
            chosen.append((r, grp))
            seen.add(r["id"])
            got += 1
            if got == k:
                break

    # Label order: shuffled, then round-robin across draw groups so any prefix
    # (the 50-item checkpoint) is a mix.
    by_grp = collections.defaultdict(list)
    for r, grp in sorted(chosen, key=lambda x: h("order" + x[0]["id"])):
        by_grp[grp].append((r, grp))
    ordered, i = [], 0
    while any(by_grp.values()):
        for grp, _ in TARGETS:
            if by_grp[grp]:
                ordered.append(by_grp[grp].pop(0))

    rendered = {}
    def render(tid):
        if tid not in rendered:
            rendered[tid] = thread_render(cur, tid)
        return rendered[tid]

    items = []
    for n, (r, grp) in enumerate(ordered, start=1):
        tr = render(r["thread_id"])
        ci, sid = tr["where"][r["id"]]
        chain, replies = ancestors_and_replies(cur, r["id"])
        row = next(x for x in tr["rows"] if x[0] == r["id"])
        groups = sorted(r["groups"] | ({"random"} if grp == "random" else set()))
        items.append({
            "item_id": f"c{n:04d}",
            "kind": "comment",
            "modes": ["comment", "thread"],
            "comment_id": r["id"],
            "thread_id": r["thread_id"],
            "sampled_for": grp,
            "risk_groups": groups,
            "stratum": stratum(r["groups"]),
            "production": prod_info(r["extracted_with"]),
            "inputs": {
                "comment": {"user_message": comment_input(cur, r["id"])},
                "thread": {"chunk_index": ci, "n_chunks": len(tr["chunks"]),
                           "short_id": sid,
                           "short_ids": tr["chunks"][ci]["short_ids"],
                           "user_message": tr["chunks"][ci]["user_message"]},
            },
            "context": {
                "thread_id": r["thread_id"], "permalink": row[5],
                "thread_title": tr["title"], "thread_selftext": tr["selftext"],
                "thread_eligible_comments": len(tr["rows"]),
                "depth": r["depth"], "author": row[2], "body": r["body"],
                "ancestors": chain, "replies": replies,
            },
        })

    for n, (tid, grp) in enumerate(chosen_threads, start=1):
        tr = render(tid)
        title, cnt, gs = tinfo[tid]
        comments = []
        for (cid, depth, author, body, parent, permalink, ew, score) in tr["rows"]:
            ci, sid = tr["where"][cid]
            comments.append({"comment_id": cid, "parent_comment_id": parent,
                             "depth": depth, "author": author, "body": body,
                             "permalink": permalink, "chunk_index": ci, "short_id": sid,
                             "production": prod_info(ew),
                             "comment_input": comment_input(cur, cid)})
        items.append({
            "item_id": f"t{n:03d}",
            "kind": "thread",
            "modes": ["comment", "thread"],
            "thread_id": tid,
            "sampled_for": grp,
            "risk_groups": sorted(gs | {"threads"}),
            "context": {"thread_title": tr["title"], "thread_selftext": tr["selftext"],
                        "created_utc": tr["created_utc"], "num_comments": tr["num_comments"]},
            "comments": comments,
            "thread_chunks": tr["chunks"],
        })

    with open(OUT, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False, default=str) + "\n")

    sampled = collections.Counter()
    drawn = collections.Counter()
    for it in items:
        if it["kind"] == "comment":
            drawn[it["sampled_for"]] += 1
            sampled.update(it["risk_groups"])
    stats = {
        "built_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "seed": SEED,
        "pool_size": len(pool) + 0,
        "orphan_replies_excluded": len(orphans),
        "ambiguous_keys": len(amb_keys),
        "candidates_per_group": dict(gcount),
        "strata_population": dict(strata),
        "drawn_for_group": dict(drawn),
        "tagged_in_sample": dict(sampled),
        "thread_candidates": len(tinfo),
        "thread_candidates_per_group": dict(tcount),
        "threads": [{"thread_id": t, "drawn_for": g, "title": tinfo[t][0],
                     "eligible_comments": tinfo[t][1], "groups": sorted(tinfo[t][2])}
                    for t, g in chosen_threads],
        "thread_comments_total": sum(tinfo[t][1] for t, _ in chosen_threads),
        "prompt_hashes": {"comment_current": prompt.PROMPT_HASH,
                          "thread_current": prompt_thread.PROMPT_HASH},
    }
    with open(STATS, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, default=str)
    print(json.dumps({k: v for k, v in stats.items() if k != "threads"}, indent=2, default=str))
    for t in stats["threads"]:
        print(t)


if __name__ == "__main__":
    main()
