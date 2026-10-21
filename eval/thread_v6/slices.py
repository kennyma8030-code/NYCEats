"""Build the thread-mode eval slices from the database, read-only.

    python eval/thread_v6/slices.py --env-file PATH/.env [--postreview DIR]

Writes eval/thread_v6/slices/<name>.threads.jsonl, one line per thread:

    {"slice", "thread_id", "title", "selftext", "author", "created_utc",
     "comments": [{"comment_id", "parent_comment_id", "author", "body", "created_utc"}],
     "targets": [comment ids to grade] or null (every item of the thread),
     "post_target": true: the post is graded wherever it is item [0] of a
                    chunk that is sent (the owner's rule), never sent for}

Every comment of each thread is kept, deleted ones included, because the
chunker (thread_chunks.py, the production code, imported by eval/run.py)
needs the whole tree to group replies and to quote ancestors. Every
non-deleted comment counts as due here, and so does the post: offline, no
production record applies, so the post is item [0] of each thread's first
chunk wherever that chunk is sent.

The slices (the owner's ~$5 plan, see docs/handoffs/extraction-v6-thread.md):

  fresh     the 300 held-out comments of eval/fresh/items.jsonl in their
            threads; targets = those 300. Graded with the round-4 rubric, so
            the result compares with comment mode's 0.79.
  v1        v1's 17 whole threads (eval/items.jsonl kind "thread"), graded
            against eval/gold.jsonl.
  v2half    a fixed-seed random half of v2's 481 comments in their threads;
            targets = that half. Graded against eval/v2/gold.jsonl.
  big       about 10 r/FoodNYC threads of the last 12 months holding a reply
            group over 25 comments (so the splitter runs), at most
            BIG_MAX_COMMENTS comments each to bound cost; whole threads.
  recent    about 40 threads whose posts the owner already graded in post
            mode (the post-review files, Aug 1 to Oct 21 2026); whole threads.

The connection is read-only (default_transaction_read_only plus a read-only
session) and closed at the end. The URL comes from EVAL_DB_URL, else
--env-file (read in-process, never printed).
"""

import argparse
import collections
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
ROOT = os.path.dirname(EVAL)
OUT = os.path.join(HERE, "slices")
sys.path.insert(0, ROOT)
import subreddits  # noqa: E402

SEED = "nyceats-thread-v6-slices"
V2_SHARE = 0.5
BIG_N = 10
BIG_MAX_COMMENTS = 150
RECENT_N = 40
RECENT_FROM, RECENT_TO = "2026-08-01", "2026-10-22"


def db_url(env_file):
    url = os.environ.get("EVAL_DB_URL")
    if not url and env_file:
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not url:
        raise SystemExit("set EVAL_DB_URL or pass --env-file")
    return url


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def fetch_threads(cur, tids):
    tids = sorted(set(tids))
    cur.execute("select id, title, selftext, author, created_utc from threads where id = any(%s)", (tids,))
    out = {r[0]: {"thread_id": r[0], "title": r[1], "selftext": r[2], "author": r[3],
                  "created_utc": r[4].isoformat(), "comments": []} for r in cur.fetchall()}
    cur.execute("""select id, thread_id, parent_comment_id, author, body, created_utc from comments
                   where thread_id = any(%s) order by thread_id, created_utc, id""", (tids,))
    for cid, tid, parent, author, body, created in cur.fetchall():
        out[tid]["comments"].append({"comment_id": cid, "parent_comment_id": parent, "author": author,
                                     "body": body, "created_utc": created.isoformat()})
    return out


def postreview_ids(folder):
    ids = []
    for n in range(1, 10):
        p = os.path.join(folder, f"batch{n}.txt")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^########## ITEM \d+ \| (t3_\w+) \| posted (\S+)", line)
                if m:
                    ids.append((m.group(1), m.group(2)))
    return ids


def build(cur, postreview):
    rng = random.Random(SEED)
    slices = {}

    fresh = load_jsonl(os.path.join(EVAL, "fresh", "items.jsonl"))
    targets = collections.defaultdict(list)
    for it in fresh:
        targets[it["thread_id"]].append(it["comment_id"])
    slices["fresh"] = (targets, False)

    v1 = [it for it in load_jsonl(os.path.join(EVAL, "items.jsonl")) if it["kind"] == "thread"]
    slices["v1"] = ({it["thread_id"]: None for it in v1}, True)

    v2 = load_jsonl(os.path.join(EVAL, "v2", "items.jsonl"))
    pick = sorted(rng.sample(sorted(it["item_id"] for it in v2), round(len(v2) * V2_SHARE)))
    chosen = set(pick)
    targets = collections.defaultdict(list)
    for it in v2:
        if it["item_id"] in chosen:
            targets[it["thread_id"]].append(it["comment_id"])
    slices["v2half"] = (targets, False)

    reviewed = [t for t, d in postreview_ids(postreview) if RECENT_FROM <= d < RECENT_TO]
    recent = sorted(rng.sample(sorted(set(reviewed)), min(RECENT_N, len(set(reviewed)))))
    slices["recent"] = ({t: None for t in recent}, True)

    cur.execute("""
        with g as (select c.thread_id, coalesce(c.root_comment_id, c.id) r, count(*) n
                   from comments c join threads t on t.id = c.thread_id
                   where t.subreddit = %s and t.created_utc >= now() - interval '12 months'
                   group by 1, 2),
             t as (select thread_id, max(n) big, sum(n) total from g group by 1)
        select thread_id from t where big > 25 and total <= %s order by thread_id""",
                (subreddits.HOME, BIG_MAX_COMMENTS))
    pool = [r[0] for r in cur.fetchall() if r[0] not in set(recent)]
    big = sorted(rng.sample(pool, min(BIG_N, len(pool))))
    slices["big"] = ({t: None for t in big}, True)

    out = {}
    for name, (tmap, whole) in slices.items():
        rows = fetch_threads(cur, list(tmap))
        lines, missing = [], []
        for tid in sorted(tmap):
            th = rows.get(tid)
            if th is None:
                missing.append(tid)
                continue
            have = {c["comment_id"] for c in th["comments"]}
            t = tmap[tid]
            if t is not None:
                gone = [c for c in t if c not in have]
                missing += gone
                t = [c for c in t if c in have]
            lines.append({"slice": name, **th, "targets": t, "post_target": True})
        out[name] = (lines, missing)
    return out, pick


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", help="read DATABASE_URL from this file (never printed)")
    ap.add_argument("--postreview", required=True, help="folder with the post-review batch*.txt files")
    args = ap.parse_args()
    import psycopg2
    conn = psycopg2.connect(db_url(args.env_file), connect_timeout=15, application_name="eval-thread-slices",
                            options="-c default_transaction_read_only=on -c statement_timeout=60000 "
                                    "-c idle_in_transaction_session_timeout=20000")
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor() as cur:
            out, pick = build(cur, args.postreview)
    finally:
        conn.close()
    os.makedirs(OUT, exist_ok=True)
    for name, (lines, missing) in out.items():
        path = os.path.join(OUT, f"{name}.threads.jsonl")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for line in lines:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        n = sum(len(x["comments"]) for x in lines)
        t = sum(len(x["targets"]) if x["targets"] is not None else 0 for x in lines)
        print(f"{name}: {len(lines)} threads, {n} comments, {t or 'all'} targets"
              + (f", {len(missing)} missing from the database: {missing[:5]}" if missing else ""))
    with open(os.path.join(OUT, "v2half.items.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(pick) + "\n")


if __name__ == "__main__":
    main()
