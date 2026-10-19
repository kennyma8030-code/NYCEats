"""Raw rows for comment-mode re-rendering, and the round-4 hard and fresh item sets. Read-only.

    python eval/build_comment_rows.py rows eval/items.jsonl eval/v2/items.jsonl --env-file PATH/.env
    python eval/build_comment_rows.py hard  --env-file PATH/.env   # eval/hard/items.jsonl (+ rows)
    python eval/build_comment_rows.py fresh --env-file PATH/.env   # eval/fresh/items.jsonl (+ rows)

Items store each comment only as production rendered it: the title, the first 400
characters of the post, the parent, the comment. v6 round 4 renders its own input
(v6_comment.build_user_message) with labelled sections, up to five ancestors, who
wrote what (the post's author, the commenter's own earlier comments), deleted
parents and quote blocks. That needs rows the items don't keep, chiefly the post's
author, so this writes them next to each items file as <items>.comment_rows.jsonl,
one line per comment-mode call:

    {"call_key": "comment:<id>", "comment_id", "thread_id", "author", "body",
     "title", "selftext", "thread_author",
     "ancestors": [{"id", "author", "body", "state"}], nearest last, at most ANCESTORS,
     "ancestors_total": the full depth of the chain}

state is "ok", "deleted" ([deleted] / [removed]) or "missing" (not in the database).

Every row is checked before anything is written: rendered with production's own
prompt.build_user_message, it must reproduce the stored user_message byte for byte,
so a sidecar can never disagree with the input the earlier rounds scored.

hard is the 60 comment ids of the red-team test set (eval/review_v6/analysis/redteam.md).
fresh is 300 comments drawn by hash from every extractable comment (not deleted,
longer than 15 characters, as production's extract.next_batch), leaving out every
comment id that appears anywhere in eval/ (items, gold, labels, packets, judgments,
analyses) and the hard set: a held-out test nothing was tuned on. Both are written in
the v1/v2 comment-item format (comment mode only) with their sidecars.

The connection is read-only (default_transaction_read_only plus a read-only
session). The URL comes from EVAL_DB_URL, else DATABASE_URL, else --env-file, which
is read in-process and never printed.
"""

import argparse
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import prompt  # noqa: E402  production's comment renderer, for verification

ANCESTORS = 6            # one more than the renderer shows, so it knows when it cut
HARD = os.path.join(HERE, "hard", "items.jsonl")
FRESH = os.path.join(HERE, "fresh", "items.jsonl")
REDTEAM = os.path.join(HERE, "review_v6", "analysis", "redteam.md")
FRESH_N = 300
FRESH_SEED = "nyceats-fresh-v6r4"
GONE = ("[deleted]", "[removed]")


def db_url(env_file):
    url = os.environ.get("EVAL_DB_URL") or os.environ.get("DATABASE_URL")
    if not url and env_file:
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip().removeprefix("export ")
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not url:
        raise SystemExit("set EVAL_DB_URL or pass --env-file")
    return url


def connect(env_file):
    import psycopg2
    conn = psycopg2.connect(db_url(env_file), options="-c default_transaction_read_only=on")
    conn.set_session(readonly=True)
    return conn


def units_of(items_path):
    """{comment_id: stored production rendering} for every comment-mode call in an items file."""
    out = {}
    with open(items_path, encoding="utf-8") as f:
        for line in f:
            it = json.loads(line)
            if it["kind"] == "comment":
                out[it["comment_id"]] = it["inputs"]["comment"]["user_message"]
            else:
                for c in it["comments"]:
                    out[c["comment_id"]] = c["comment_input"]
    return out


def fetch_rows(conn, cids):
    """{comment_id: sidecar record} for the given ids (those found in the database)."""
    cids = sorted(set(cids))
    with conn.cursor() as cur:
        cur.execute("""select c.id, c.thread_id, c.author, c.body, c.parent_comment_id,
                              t.title, t.selftext, t.author
                       from comments c join threads t on t.id = c.thread_id
                       where c.id = any(%s)""", (cids,))
        base = {r[0]: r for r in cur.fetchall()}
        # Walk every chain up, a level at a time for all comments at once.
        parent_of = {cid: r[4] for cid, r in base.items()}
        rows = {}
        frontier = {p for p in parent_of.values() if p}
        while frontier:
            cur.execute("select id, author, body, parent_comment_id from comments where id = any(%s)",
                        (sorted(frontier),))
            got = {r[0]: r for r in cur.fetchall()}
            rows.update(got)
            frontier = {r[3] for r in got.values() if r[3] and r[3] not in rows}
    out = {}
    for cid, (_, tid, author, body, parent, title, selftext, tauthor) in base.items():
        chain, p = [], parent
        while p:
            r = rows.get(p)
            if r is None:
                chain.append({"id": p, "author": None, "body": None, "state": "missing"})
                break
            gone = (r[2] or "").strip() in GONE
            chain.append({"id": p, "author": r[1], "body": None if gone else r[2],
                          "state": "deleted" if gone else "ok"})
            p = r[3]
        out[cid] = {"call_key": f"comment:{cid}", "comment_id": cid, "thread_id": tid,
                    "author": author, "body": body, "title": title, "selftext": selftext,
                    "thread_author": tauthor, "ancestors": chain[:ANCESTORS][::-1],
                    "ancestors_total": len(chain)}
    return out


def production_render(rec):
    parent = rec["ancestors"][-1] if rec["ancestors"] else None
    pbody = parent["body"] if parent and parent["state"] == "ok" else (
        "[deleted]" if parent and parent["state"] == "deleted" else None)
    return prompt.build_user_message(rec["body"], rec["title"], rec["selftext"], pbody)


def sidecar_path(items_path):
    return os.path.splitext(items_path)[0] + ".comment_rows.jsonl"


def write_sidecar(items_path, records):
    with open(sidecar_path(items_path), "w", encoding="utf-8") as f:
        for r in sorted(records, key=lambda r: r["call_key"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  -> {sidecar_path(items_path)} ({len(records)} rows)")


def cmd_rows(conn, paths):
    built, failed = {}, []
    for path in paths:
        units = units_of(path)
        got = fetch_rows(conn, units)
        recs = []
        for cid, stored in sorted(units.items()):
            rec = got.get(cid)
            if rec is None:
                failed.append(f"{path}: {cid} not in the database")
            elif production_render(rec) != stored:
                failed.append(f"{path}: {cid} rows do not reproduce the stored rendering")
            else:
                recs.append(rec)
        built[path] = recs
        print(f"{path}: {len(recs)} of {len(units)} comments verified")
    if failed:
        print("\n".join(failed[:50]))
        raise SystemExit(f"{len(failed)} problem(s); nothing written")
    for path, recs in built.items():
        write_sidecar(path, recs)


# ---------------------------------------------------------------- new item sets
def item_record(cur, rec, item_id, sampled_for):
    """A comment item in the v1/v2 format (comment mode), with the labeler's full context."""
    cur.execute("select depth, permalink from comments where id = %s", (rec["comment_id"],))
    depth, permalink = cur.fetchone()
    # the whole chain for the judge's wider context (the sidecar keeps only the nearest)
    chain, p = [], (rec["ancestors"][-1]["id"] if rec["ancestors"] else None)
    while p:
        cur.execute("select id, coalesce(depth, 0), author, body, parent_comment_id from comments where id = %s", (p,))
        r = cur.fetchone()
        if not r:
            chain.append({"id": p, "missing": True})
            break
        chain.append({"id": r[0], "depth": r[1], "author": r[2], "body": r[3]})
        p = r[4]
    cur.execute("select id, coalesce(depth, 0), author, body from comments where parent_comment_id = %s "
                "order by created_utc", (rec["comment_id"],))
    replies = [{"id": a, "depth": b, "author": c, "body": d} for a, b, c, d in cur.fetchall()]
    return {"item_id": item_id, "kind": "comment", "modes": ["comment"], "comment_id": rec["comment_id"],
            "thread_id": rec["thread_id"], "sampled_for": sampled_for,
            "inputs": {"comment": {"user_message": production_render(rec)}},
            "context": {"thread_id": rec["thread_id"], "permalink": permalink, "thread_title": rec["title"],
                        "thread_selftext": rec["selftext"], "thread_author": rec["thread_author"],
                        "depth": depth, "author": rec["author"], "body": rec["body"],
                        "ancestors": chain[::-1], "replies": replies}}


def write_items(conn, path, ids, prefix, sampled_for):
    got = fetch_rows(conn, ids)
    missing = [c for c in ids if c not in got]
    if missing:
        raise SystemExit(f"{len(missing)} ids not in the database, e.g. {missing[:3]}; nothing written")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with conn.cursor() as cur:
        items = [item_record(cur, got[c], f"{prefix}{n:03d}", sampled_for(c)) for n, c in enumerate(ids, 1)]
    with open(path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"{path}: {len(items)} items")
    write_sidecar(path, [got[c] for c in ids])


def hard_ids():
    """The red-team hard cases, in the note's order, with the mode each was listed under."""
    text = open(REDTEAM, encoding="utf-8").read()
    section = text.split("## Hard-case test set", 1)[1].split("## Caveats", 1)[0]
    ids, mode = {}, None
    for line in section.splitlines():
        m = re.match(r"- \*\*(.+?)\*\*", line)
        if m:
            mode = m.group(1)
        for cid in re.findall(r"t1_[a-z0-9]+", line):
            ids.setdefault(cid, mode)
    return ids


def used_ids():
    """Every comment id written anywhere under eval/ except run outputs."""
    seen = set()
    for d, dirs, files in os.walk(HERE):
        dirs[:] = [x for x in dirs if x not in ("runs", "merged", "__pycache__", "fresh")]
        for fn in files:
            if fn.endswith((".jsonl", ".json", ".md", ".txt", ".py")):
                with open(os.path.join(d, fn), encoding="utf-8", errors="ignore") as f:
                    seen.update(re.findall(r"t1_[a-z0-9]{5,9}", f.read()))
    return seen


def cmd_hard(conn):
    ids = hard_ids()
    if len(ids) != 60:
        raise SystemExit(f"expected 60 hard-case ids, found {len(ids)}")
    write_items(conn, HARD, list(ids), "h", lambda c: "hard: " + ids[c])


def cmd_fresh(conn):
    exclude = used_ids() | set(hard_ids())
    with conn.cursor() as cur:
        # Production's own eligibility (extract.next_batch), ordered by a seeded hash.
        cur.execute("""select id from comments
                       where body not in ('[deleted]', '[removed]') and length(body) > 15
                       order by md5(%s || id) limit %s""", (FRESH_SEED + "|", FRESH_N + len(exclude) + 100))
        pool = [r[0] for r in cur.fetchall()]
    ids = [c for c in pool if c not in exclude][:FRESH_N]
    if len(ids) < FRESH_N:
        raise SystemExit("not enough fresh comments")
    print(f"fresh: {len(exclude)} ids excluded as used; drew {len(ids)}")
    write_items(conn, FRESH, ids, "f", lambda c: "fresh")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("rows", "hard", "fresh"))
    ap.add_argument("items", nargs="*")
    ap.add_argument("--env-file", help="read DATABASE_URL from this file (never printed)")
    args = ap.parse_args()
    conn = connect(args.env_file)
    if args.cmd == "rows":
        cmd_rows(conn, args.items)
    elif args.cmd == "hard":
        cmd_hard(conn)
    else:
        cmd_fresh(conn)


if __name__ == "__main__":
    main()
