"""Sampling design shared by every round: draw, weight, split, and assemble items.

A round's spec says how many units to draw at random and how many from each
stratum, per mode. Everything is deterministic: candidates are ordered by
md5(seed || key), so the same spec over the same snapshot gives the same set.

Weights are inverse inclusion probabilities, so any metric can be re-weighted
to real traffic. Each mode has its own population and its own design:

comment mode   unit = one comment. A simple random sample of n_r comments
               from all N eligible comments, plus, in each stratum s, n_s more
               drawn at random from the N_s - r_s not already picked.
                   pi = n_r/N + (1 - n_r/N) * n_s/(N_s - r_s)
thread mode    unit = one production chunk (up to 25 comments). The random
               part is drawn proportional to size: comments are taken in
               random order and each brings in its chunk, until the comment
               budget is met (k draws).
                   pi_r = 1 - (1 - size/N_comments)^k
               then each stratum adds n_s chunks at random from its M_s - r_s.
                   pi = pi_r + (1 - pi_r) * n_s/(M_s - r_s)
               Every comment in a chunk carries the chunk's weight.

Strata are mutually exclusive (each unit's first matching heuristic in the
stratum order, else "none"), so pi is exact up to two approximations: at most
one chunk per thread is taken, and strata stop on a comment budget rather
than a fixed count. Both are documented in the README.

The v1 overlap items have no inclusion probability under this design and
carry weight None: they count in unweighted and agreement figures, never in
re-weighted ones.
"""

import collections
import datetime
import hashlib
import heapq
import json
import os

import corpus
import render


def h(*parts):
    return hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()


# ---------------------------------------------------------------- draws
def hash_order(xs, key, first):
    """xs in key order, lazily: the first `first` come from a heap, and the
    full sort happens only if the caller reads past them. The order is exactly
    sorted(xs, key=key), so draws are identical either way."""
    xs = list(xs)
    head = heapq.nsmallest(first, xs, key=key)
    yield from head
    if len(head) < len(xs):
        yield from sorted(xs, key=key)[first:]


def draw_threads(cp, spec, seed, exclude_ids, exclude_threads):
    """Chunks for thread mode. Returns (chosen [(chunk_key, draw)], stratum, design)."""
    order = spec.get("strata_order", corpus.CHUNK_STRATA)
    pop = {k: ch for k, ch in cp.chunks.items()
           if k[0] not in exclude_threads and not exclude_ids.intersection(ch["comment_ids"])}
    n_comments = sum(len(ch["comment_ids"]) for ch in pop.values())
    stratum, buckets = {}, collections.defaultdict(list)
    for key, ch in pop.items():
        stratum[key] = s = corpus.stratum_of(ch["tags"], order)
        buckets[s].append(key)

    chosen, threads = [], set()
    # random, proportional to size: comments in hashed order, each bringing its chunk
    budget, got, k = spec["random_comments"], 0, 0
    comments = (c for ch in pop.values() for c in ch["comment_ids"])
    for cid in hash_order(comments, lambda c: h(seed, "rand-t", c), 4 * budget + 64):
        if got >= budget:
            break
        k += 1
        key = cp.chunk_of[cid]
        if key[0] in threads:
            continue
        chosen.append((key, "random"))
        threads.add(key[0])
        got += len(pop[key]["comment_ids"])
    r = collections.Counter(stratum[key] for key, _ in chosen)

    # targeted, per stratum, until the stratum's comment budget is met
    n = collections.Counter()
    for s in order:
        budget, got = spec["strata_comments"].get(s, 0), 0
        for key in hash_order(buckets[s], lambda x: h(seed, "tgt-t", *x), 64):
            if got >= budget:
                break
            if key[0] in threads:
                continue
            chosen.append((key, "targeted"))
            threads.add(key[0])
            n[s] += 1
            got += len(pop[key]["comment_ids"])
    design = {"unit": "chunk", "population_chunks": len(pop), "population_comments": n_comments,
              "random_draws_k": k, "random_comments_budget": spec["random_comments"],
              "strata_order": order,
              "strata": {s: {"M": len(buckets[s]), "n": n[s], "r": r[s],
                             "comments": sum(len(pop[x]["comment_ids"]) for x in buckets[s])}
                         for s in order + ["none"]}}
    return chosen, stratum, design


def draw_comments(cp, spec, seed, exclude_ids):
    """Single comments for comment mode. Returns (chosen [(cid, draw)], stratum, design)."""
    order = spec.get("strata_order", corpus.COMMENT_STRATA)
    pop = [c.id for c in cp.eligible if c.id not in exclude_ids]
    stratum, buckets = {}, collections.defaultdict(list)
    for cid in pop:
        stratum[cid] = s = corpus.stratum_of(cp.tags[cid], order)
        buckets[s].append(cid)
    N = len(pop)
    rand = heapq.nsmallest(spec["random"], pop, key=lambda c: h(seed, "rand-c", c))
    chosen = [(cid, "random") for cid in rand]
    taken = set(rand)
    r = collections.Counter(stratum[c] for c in rand)
    n = collections.Counter()
    for s in order:
        q = spec["strata"].get(s, 0)
        for cid in heapq.nsmallest(q, (c for c in buckets[s] if c not in taken),
                                   key=lambda c: h(seed, "tgt-c", c)):
            chosen.append((cid, "targeted"))
            taken.add(cid)
            n[s] += 1
    design = {"unit": "comment", "population": N, "random": spec["random"], "strata_order": order,
              "strata": {s: {"N": len(buckets[s]), "n": n[s], "r": r[s]} for s in order + ["none"]}}
    return chosen, stratum, design


def pi_comment(d, s):
    p_r = d["random"] / d["population"]
    st = d["strata"].get(s) or {"N": 0, "n": 0, "r": 0}
    left = st["N"] - st["r"]
    p_t = st["n"] / left if left > 0 else 0.0
    return p_r + (1 - p_r) * p_t


def pi_chunk(d, s, size):
    p_r = 1 - (1 - size / d["population_comments"]) ** d["random_draws_k"]
    st = d["strata"].get(s) or {"M": 0, "n": 0, "r": 0}
    left = st["M"] - st["r"]
    p_t = st["n"] / left if left > 0 else 0.0
    return p_r + (1 - p_r) * p_t


def assign_splits(items, seed, share=0.2):
    """Holdout ~20%, stratified by mode and stratum: within each mode, sort
    by (stratum, hash) and take every fifth unit, starting at a hashed offset.
    Systematic selection spreads the holdout over every stratum, even the
    ones with two or three units."""
    by_mode = collections.defaultdict(list)
    for it in items:
        by_mode[it["mode"]].append(it)
    for mode, its in by_mode.items():
        its.sort(key=lambda it: (it["stratum"], it["draw"], h(seed, "split", it["item_id"])))
        step = 1 / share
        offset = int(h(seed, "split-offset", mode), 16) % int(step)
        for i, it in enumerate(its):
            it["split"] = "holdout" if (i + offset) % int(step) == 0 else "tuning"


# ---------------------------------------------------------------- items
CONTEXT_LIMIT = 150


def _context_rows(rows, focus_ids, limit=CONTEXT_LIMIT):
    """Rows shown in a full-context packet: the whole thread when it is small,
    otherwise the focus comments, all their ancestors and their direct replies."""
    if len(rows) <= limit:
        return rows
    by_id = {r["id"]: r for r in rows}
    keep = set()
    for cid in focus_ids:
        keep.add(cid)
        p = by_id[cid]["parent"]
        while p in by_id and p not in keep:
            keep.add(p)
            p = by_id[p]["parent"]
    keep.update(r["id"] for r in rows if r["parent"] in focus_ids)
    return [r for r in rows if r["id"] in keep]


def build_items(conn, cp, singles, chunks, stratum_c, stratum_t, design, round_no, seed, overlap=()):
    """Render every chosen unit from the database into item dicts.

    singles: [(comment_id, draw)]; chunks: [((thread_id, chunk_index), draw)];
    overlap: [(comment_id, v1_item_id)]. Item ids are assigned in hashed
    order, so an id says nothing about how the item was drawn."""
    cur = conn.cursor()
    chunks = sorted(chunks, key=lambda x: h(seed, "order", *x[0]))
    items, mismatches = [], []
    rendered = {}

    def thread(tid):
        if tid not in rendered:
            head, chs = render.thread_chunks(cur, tid)
            rows = render.thread_context(cur, tid)
            rendered[tid] = (head, chs, rows)
        return rendered[tid]

    prefix = {1: ""}.get(round_no, f"r{round_no}")
    # ---- thread chunks
    for n, (key, draw) in enumerate(chunks, start=1):
        tid, ci = key
        head, chs, rows = thread(tid)
        ch = chs[ci]
        mine = cp.chunks[key]["comment_ids"]
        db_ids = [ch["short_ids"][str(i)] for i in range(1, len(ch["short_ids"]) + 1)]
        if db_ids != mine:
            mismatches.append({"thread_id": tid, "chunk_index": ci, "corpus": mine, "db": db_ids})
        s = stratum_t[key]
        size = len(db_ids)
        pi = pi_chunk(design["thread"], s, size)
        cinputs = render.comment_inputs(cur, db_ids)
        by_id = {r["id"]: r for r in rows}
        comments = []
        for sid, cid in enumerate(db_ids, start=1):
            r = by_id[cid]
            comments.append({"comment_id": cid, "parent_comment_id": r["parent"], "depth": r["depth"],
                             "author": r["author"], "body": r["body"], "permalink": r["permalink"],
                             "was_deleted_later": r["was_deleted_later"],
                             "chunk_index": ci, "short_id": sid, "comment_input": cinputs[cid],
                             "tags": sorted(cp.tags.get(cid, ()))})
        t = cp.threads[tid]
        items.append({
            "item_id": f"{prefix}t{n:03d}", "round": round_no, "kind": "thread", "mode": "thread",
            "modes": ["thread"], "thread_id": tid, "chunk_index": ci, "n_chunks": len(chs),
            "chunk_size": size, "draw": draw, "stratum": s,
            "tags": sorted(cp.chunks[key]["tags"]),
            "risk_groups": sorted(cp.chunks[key]["tags"] | {f"draw_{draw}"}),
            "pi": pi, "weight": 1 / pi,
            "comments": comments,
            "thread_chunks": [{"chunk_index": ci, "short_ids": ch["short_ids"],
                               "user_message": ch["user_message"]}],
            "context": {"thread_title": head[0], "thread_selftext": head[1],
                        "created_utc": t["created_utc"].isoformat(), "num_comments": t["num_comments"],
                        "thread_eligible_comments": sum(len(c["rows"]) for c in chs),
                        "rows": _context_rows(rows, set(db_ids)),
                        "rows_complete": len(rows) <= CONTEXT_LIMIT, "thread_rows_total": len(rows)},
        })

    # ---- single comments (and the v1 overlap)
    units = [(cid, draw, None) for cid, draw in singles] + [(cid, "overlap_v1", v1) for cid, v1 in overlap]
    units.sort(key=lambda u: h(seed, "order", u[0]))
    cinputs = render.comment_inputs(cur, [u[0] for u in units])
    for n, (cid, draw, v1) in enumerate(units, start=1):
        c = cp.comments[cid]
        head, chs, rows = thread(c.thread_id)
        ci = next(i for i, ch in enumerate(chs) if cid in ch["short_ids"].values())
        ch = chs[ci]
        sid = next(int(k) for k, v in ch["short_ids"].items() if v == cid)
        by_id = {r["id"]: r for r in rows}
        anc, replies = render.ancestors_and_replies(by_id, cid)
        tags = set(cp.tags.get(cid, ()))
        if draw == "overlap_v1":
            s, pi = "overlap_v1", None
        else:
            s = stratum_c[cid]
            pi = pi_comment(design["comment"], s)
        r = by_id[cid]
        items.append({
            "item_id": f"{prefix}s{n:04d}", "round": round_no, "kind": "comment", "mode": "comment",
            "modes": ["comment"], "comment_id": cid, "thread_id": c.thread_id,
            "draw": draw, "stratum": s, "tags": sorted(tags),
            "risk_groups": sorted(tags | {f"draw_{draw}"}),
            "pi": pi, "weight": (1 / pi) if pi else None,
            **({"v1_item_id": v1} if v1 else {}),
            "inputs": {
                "comment": {"user_message": cinputs[cid]},
                # Kept for run.py / score.py compatibility. v4 scores single
                # items in comment mode only; this chunk is unlabeled context.
                "thread": {"chunk_index": ci, "n_chunks": len(chs), "short_id": sid,
                           "short_ids": ch["short_ids"], "user_message": ch["user_message"]},
            },
            "context": {
                "thread_id": c.thread_id, "permalink": r["permalink"],
                "was_deleted_later": r["was_deleted_later"],
                "thread_title": head[0], "thread_selftext": head[1],
                "thread_eligible_comments": sum(len(x["rows"]) for x in chs),
                "depth": r["depth"], "author": r["author"], "body": r["body"],
                "ancestors": anc, "replies": replies,
            },
        })
    return items, mismatches


# ---------------------------------------------------------------- output
def summarize(cp, items, design, mismatches, round_no, seed, spec):
    """Everything design.json records: snapshot, spec, populations, counts."""
    out = {"built_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "round": round_no, "seed": seed, "spec": spec,
           "snapshot_at": cp.snapshot_at, "cutoff": cp.cutoff,
           "corpus": {"comments": len(cp.comments), "eligible": len(cp.eligible),
                      "chunks": len(cp.chunks), "gazetteer_keys": len(cp.gaz.keys),
                      "old_set_comments_excluded": len(cp.old_ids & set(cp.tags)),
                      "old_set_threads_excluded": len(cp.old_threads)},
           "design": design, "chunk_order_mismatches": mismatches}
    pop_tags = collections.Counter(t for ts in cp.tags.values() for t in ts)
    pop_ctags = collections.Counter(t for ch in cp.chunks.values() for t in ch["tags"])
    counts = {}
    for mode in ("comment", "thread"):
        its = [i for i in items if i["mode"] == mode]
        cm = lambda i: len(i["comments"]) if i["kind"] == "thread" else 1  # noqa: E731
        by = lambda key: {k: {"items": sum(1 for i in its if i[key] == k),  # noqa: E731
                              "comments": sum(cm(i) for i in its if i[key] == k)}
                          for k in sorted({i[key] for i in its})}
        tagged = collections.Counter()
        for i in its:
            if i["kind"] == "thread":
                tagged.update(i["tags"])
                for c in i["comments"]:
                    tagged.update(c["tags"])
            else:
                tagged.update(i["tags"])
        counts[mode] = {"items": len(its), "comments": sum(cm(i) for i in its),
                        "by_draw": by("draw"), "by_stratum": by("stratum"), "by_split": by("split"),
                        "tagged_in_sample": dict(sorted(tagged.items()))}
    out["counts"] = counts
    out["population_tags"] = {t: pop_tags[t] for t in corpus.COMMENT_TAGS}
    out["population_chunk_tags"] = {t: pop_ctags[t] for t in corpus.CHUNK_TAGS}
    return out


def write_round(out_dir, items, meta):
    os.makedirs(out_dir, exist_ok=True)
    def dump(path, its):
        with open(path, "w", encoding="utf-8") as f:
            for it in its:
                f.write(json.dumps(it, ensure_ascii=False, default=str) + "\n")
    dump(os.path.join(out_dir, "items.jsonl"), items)
    dump(os.path.join(out_dir, "items_single.jsonl"), [i for i in items if i["kind"] == "comment"])
    dump(os.path.join(out_dir, "items_thread.jsonl"), [i for i in items if i["kind"] == "thread"])
    with open(os.path.join(out_dir, "design.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, default=str)
