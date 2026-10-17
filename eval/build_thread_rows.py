"""Fetch the raw rows behind every thread-mode chunk in an items file. Read-only.

    python eval/build_thread_rows.py eval/items.jsonl eval/v2/items.jsonl \\
        eval/v4/items_single.jsonl eval/v4/items_thread.jsonl --env-file PATH/.env

Items store each chunk only as production rendered it (user_message plus the
short-id map), and comment items carry no raw rows for the other comments in
their chunk. A prompt module that brings its own renderer (v6_thread's
render_chunk) needs the rows, so this writes them next to each items file, as
<items>.thread_rows.jsonl, one line per chunk:

    {"call_key": "thread:<thread_id>:<chunk_index>", "short_ids": {...},
     "title": ..., "selftext": ...,
     "rows": [{"short_id", "comment_id", "parent_comment_id", "depth", "author", "body"}],
     "outside": {parent_comment_id: {"author", "body"} or null}}

rows are in production's order (short id order), so chunk membership is
unchanged. outside holds every parent that is not in the chunk, null when
the parent is not in the database at all.

Every chunk is verified before anything is written: the fetched rows,
rendered with production's own prompt_thread.build_message, must reproduce
the stored user_message byte for byte. Any mismatch stops the run and
nothing is written, so a sidecar can never silently disagree with the input
the benchmark scored.

The connection is read-only (default_transaction_read_only plus a read-only
session). The URL comes from EVAL_DB_URL, else DATABASE_URL, else
--env-file, which is read in-process and never printed.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import prompt_thread  # noqa: E402  production's renderer, for verification


def db_url(env_file):
    url = os.environ.get("EVAL_DB_URL") or os.environ.get("DATABASE_URL")
    if not url and env_file:
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not url:
        raise SystemExit("set EVAL_DB_URL or pass --env-file")
    return url


def chunks_of(items_path):
    """{call_key: (thread_id, short_ids, stored user_message)}, as run.build_jobs keys them."""
    out = {}
    with open(items_path, encoding="utf-8") as f:
        for line in f:
            it = json.loads(line)
            if it["kind"] == "comment":
                t = it["inputs"]["thread"]
                found = [(it["thread_id"], t["chunk_index"], t["short_ids"], t["user_message"])]
            else:
                found = [(it["thread_id"], c["chunk_index"], c["short_ids"], c["user_message"])
                         for c in it["thread_chunks"]]
            for tid, ci, sids, msg in found:
                key = f"thread:{tid}:{ci}"
                if key in out and out[key][1] != sids:
                    raise SystemExit(f"{items_path}: {key} appears with two different chunkings")
                out[key] = (tid, sids, msg)
    return out


def fetch(conn, chunks):
    cids = sorted({c for _, sids, _ in chunks.values() for c in sids.values()})
    tids = sorted({tid for tid, _, _ in chunks.values()})
    with conn.cursor() as cur:
        cur.execute("""select id, parent_comment_id, coalesce(depth, 0), author, body
                       from comments where id = any(%s)""", (cids,))
        comments = {r[0]: r for r in cur.fetchall()}
        parents = sorted({r[1] for r in comments.values() if r[1]} - set(comments))
        cur.execute("select id, author, body from comments where id = any(%s)", (parents,))
        others = {r[0]: {"author": r[1], "body": r[2]} for r in cur.fetchall()}
        cur.execute("select id, title, selftext from threads where id = any(%s)", (tids,))
        threads = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    return comments, others, threads


def build(items_path, conn):
    chunks = chunks_of(items_path)
    comments, others, threads = fetch(conn, chunks)
    records, problems = [], []
    for key, (tid, sids, stored) in sorted(chunks.items()):
        order = sorted(sids.items(), key=lambda kv: int(kv[0]))
        missing = [cid for _, cid in order if cid not in comments]
        if missing or tid not in threads:
            problems.append(f"{key}: not in the database ({missing[:3]} {tid if tid not in threads else ''})")
            continue
        title, selftext = threads[tid]
        nodes = [(int(s), comments[c][2], comments[c][3], comments[c][4]) for s, c in order]
        if prompt_thread.build_message(title, selftext, nodes) != stored:
            problems.append(f"{key}: fetched rows do not reproduce the stored rendering")
            continue
        in_chunk = set(sids.values())
        rows, outside = [], {}
        for s, c in order:
            _, parent, depth, author, body = comments[c]
            rows.append({"short_id": int(s), "comment_id": c, "parent_comment_id": parent,
                         "depth": depth, "author": author, "body": body})
            if parent and parent not in in_chunk:
                p = comments.get(parent)
                outside[parent] = ({"author": p[3], "body": p[4]} if p else others.get(parent))
        records.append({"call_key": key, "short_ids": sids, "title": title, "selftext": selftext,
                        "rows": rows, "outside": outside})
    return records, problems


def sidecar_path(items_path):
    return os.path.splitext(items_path)[0] + ".thread_rows.jsonl"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("items", nargs="+")
    ap.add_argument("--env-file", help="read DATABASE_URL from this file (never printed)")
    args = ap.parse_args()

    import psycopg2
    conn = psycopg2.connect(db_url(args.env_file), options="-c default_transaction_read_only=on")
    conn.set_session(readonly=True)
    built, failed = {}, []
    for path in args.items:
        records, problems = build(path, conn)
        built[path] = records
        failed += [f"{path}: {p}" for p in problems]
        print(f"{path}: {len(records)} chunks verified, {len(problems)} problem(s)")
    if failed:
        print("\n".join(failed[:50]))
        raise SystemExit("nothing written")
    for path, records in built.items():
        with open(sidecar_path(path), "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  -> {sidecar_path(path)}")


if __name__ == "__main__":
    main()
