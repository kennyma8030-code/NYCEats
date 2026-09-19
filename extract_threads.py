"""Extract a whole thread per API call instead of a comment per call.

Roughly 3-4x cheaper than comment mode: the post body is sent once per thread
rather than once per comment, and the system prompt is amortised across ~19
comments instead of paid for each one.

Reuses extract.py for the API client, entity normalization and chain filtering
so there is one implementation of each. What is different here is the batching,
the tree rendering, and validating the ids that come back.
"""

import argparse
import collections
import concurrent.futures
import json
import os
import time
import traceback

import db
import extract
import prompt_thread

# A thread larger than this is split. Threads run to 1,096 comments and one
# call that size is slow, expensive to retry, and past the point where the
# model tracks ids reliably.
CHUNK = 25
LOG_EVERY = 25


def pending_threads(conn, since=None, limit=500):
    """Threads with comments still needing extraction, biggest first.

    Biggest first, because that is the whole point. The system prompt is paid
    once per CALL, not per comment, so a 25-comment thread amortises it 25
    ways. Measured on this corpus: 109 input tokens per comment on the largest
    threads against 1,582 in comment mode, a 14.5x difference.

    Smallest-first was tried and is a trap: 3,024 pending threads hold exactly
    one comment, and on those "thread mode" is comment mode paying full price.
    It feels faster because the thread counter moves, and it costs ~20x.
    """
    with conn.cursor() as cur:
        cur.execute("""
            select c.thread_id, count(*) as n
            from comments c
            where c.extracted_at is null and c.extract_error is null
              and c.body not in ('[deleted]', '[removed]')
              and length(c.body) > 15
              and (%s is null or c.created_utc >= %s)
            group by c.thread_id
            order by n desc
            limit %s
        """, (since, since, limit))
        return cur.fetchall()


def thread_rows(conn, thread_id, since=None):
    """The post plus every comment still needing extraction, in reading order.

    Ordered by (root_comment_id, created_utc) so a chain stays contiguous --
    that is what makes the indentation meaningful.
    """
    with conn.cursor() as cur:
        cur.execute("select title, selftext from threads where id = %s", (thread_id,))
        row = cur.fetchone()
        if not row:
            return None, []
        title, selftext = row
        cur.execute("""
            select c.id, coalesce(c.depth, 0), c.author, c.body
            from comments c
            where c.thread_id = %s
              and c.extracted_at is null and c.extract_error is null
              and c.body not in ('[deleted]', '[removed]')
              and length(c.body) > 15
              and (%s is null or c.created_utc >= %s)
            order by coalesce(c.root_comment_id, c.id), c.created_utc
        """, (thread_id, since, since))
        return (title, selftext), cur.fetchall()


def chunks(rows, size=CHUNK):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def fetch_chunk(job):
    """Network half, worker thread only. Returns (ids, mentions_by_id, error).

    Short ids are assigned here and never leave this function's mapping, so a
    hallucinated id cannot reach the database -- it has nothing to resolve to.
    """
    (title, selftext), rows = job
    nodes, by_short = [], {}
    for i, (cid, depth, author, body) in enumerate(rows, start=1):
        nodes.append((i, depth, author, body))
        by_short[i] = cid

    user = prompt_thread.build_message(title, selftext, nodes)
    last = None
    for _ in range(2):          # malformed JSON is not deterministic
        try:
            raw = extract.call_model(prompt_thread.SYSTEM_PROMPT, user)
            mentions = json.loads(raw).get("mentions") or []
            break
        except (json.JSONDecodeError, TypeError) as e:
            last = f"{type(e).__name__}: {e}"
        except Exception as e:
            return list(by_short.values()), None, f"{type(e).__name__}: {e}"
    else:
        return list(by_short.values()), None, last

    grouped, bad = collections.defaultdict(list), 0
    for m in mentions:
        cid = by_short.get(m.get("id"))
        if cid is None:
            bad += 1            # an id we never sent; drop it, do not guess
            continue
        grouped[cid].append(m)
    return list(by_short.values()), (dict(grouped), bad), None


def store_chunk(conn, comment_ids, result, error):
    """Database half, main thread only."""
    if error is not None:
        for cid in comment_ids:
            extract._mark_error(conn, cid, error)
        return 0, 0

    grouped, bad = result
    found = 0
    for cid in comment_ids:
        keep = []
        for m in grouped.get(cid, []):
            name = (m.get("restaurant_raw") or "").strip()
            if not name:
                continue
            m.pop("id", None)
            m["restaurant_raw"] = name
            m["entity_key"] = extract.normalize_entity(name)
            if m["entity_key"] and not extract.is_chain(m["entity_key"]):
                keep.append(m)
        found += db.insert_mentions(conn, cid, keep, extract.MODEL,
                                    prompt_thread.PROMPT_HASH)
        extract._mark_extracted(conn, cid, prompt_thread.PROMPT_HASH)
    return found, bad


def run(conn, since=None, workers=None, max_threads=None):
    workers = workers or extract.WORKERS
    done = found = bad_ids = threads = 0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            while max_threads is None or threads < max_threads:
                todo = pending_threads(conn, since, limit=workers * 2)
                if not todo:
                    break
                # Bounded: pool.map materialises every job, and each holds up
                # to CHUNK comment bodies. Pulling 128 big threads at once was
                # enough to get the process OOM-killed.
                jobs = []
                for thread_id, _ in todo:
                    if len(jobs) >= workers * 2:
                        break
                    head, rows = thread_rows(conn, thread_id, since)
                    if not rows:
                        continue
                    for chunk in chunks(rows):
                        jobs.append((head, chunk))
                    threads += 1
                    if max_threads and threads >= max_threads:
                        break
                if not jobs:
                    break
                for ids, result, error in pool.map(fetch_chunk, jobs):
                    f, b = store_chunk(conn, ids, result, error)
                    found += f
                    bad_ids += b
                    done += len(ids)
                    if done // LOG_EVERY != (done - len(ids)) // LOG_EVERY:
                        print(f"  {done:,} comments  {found:,} mentions  "
                              f"{threads:,} threads", flush=True)
    except KeyboardInterrupt:
        print("\ninterrupted -- finished comments are committed, re-run to resume")
    return done, found, bad_ids, threads


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", metavar="MONTHS", type=int, default=None)
    ap.add_argument("--threads", type=int, default=None,
                    help="stop after N threads")
    ap.add_argument("--workers", type=int, default=extract.WORKERS)
    ap.add_argument("--dry-run", action="store_true",
                    help="render one thread and exit without calling the API")
    args = ap.parse_args()

    conn = db.connect()
    since = None
    if args.since:
        with conn.cursor() as cur:
            cur.execute("select now() - make_interval(months => %s)", (args.since,))
            since = cur.fetchone()[0]

    if args.dry_run:
        todo = pending_threads(conn, since, limit=1)
        if not todo:
            raise SystemExit("nothing pending")
        head, rows = thread_rows(conn, todo[0][0], since)
        nodes = [(i, d, a, b) for i, (_, d, a, b) in enumerate(rows[:CHUNK], 1)]
        msg = prompt_thread.build_message(head[0], head[1], nodes)
        print(msg[:3000])
        print(f"\n[{len(rows)} comments, ~{len(msg)//4:,} input tokens]")
        return

    if not os.environ.get(extract.API_KEY_VAR):
        raise SystemExit(f"{extract.API_KEY_VAR} is not set")

    began = time.time()
    try:
        done, found, bad, threads = run(conn, since, args.workers, args.threads)
    except Exception:
        traceback.print_exc()
        conn.rollback()
        return

    mins = (time.time() - began) / 60
    print(f"\n{done:,} comments in {threads:,} threads -> {found:,} mentions "
          f"({mins:.1f} min)")
    if bad:
        print(f"  {bad} mention(s) dropped for referencing an id we never sent")
    U = extract.USAGE
    cost = U["cost"] if U["priced_calls"] == U["calls"] and U["calls"] else (
        U["prompt_tokens"] * extract.PRICE_IN + U["completion_tokens"] * extract.PRICE_OUT)
    print(f"tokens: {extract.USAGE['prompt_tokens']:,} in / "
          f"{extract.USAGE['completion_tokens']:,} out   est. ${cost:.2f}")
    if done:
        print(f"  ${cost / done * 1000:.3f} per 1,000 comments")


if __name__ == "__main__":
    main()
