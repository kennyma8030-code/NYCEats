"""Run the extraction prompt over the comment corpus and store the mentions.

Resumable by construction: `comments.extracted_at` and `comments.extract_error`
are the cursor, so killing this mid-run and restarting picks up exactly where it
stopped. One bad comment never stalls the run -- the error is written to its row
and the loop moves on.
"""

import argparse
import concurrent.futures
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.request

import db
import prompt

# Provider is configurable because the same model is reachable through
# DeepSeek directly or through OpenRouter, with different slugs and prices.
WORKERS = int(os.environ.get("LLM_WORKERS", "48"))   # measured: 200 comments/min
API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/chat/completions")
API_KEY_VAR = "OPENROUTER_API_KEY" if "openrouter" in API_URL else "DEEPSEEK_API_KEY"
MODEL = os.environ.get("LLM_MODEL", "deepseek-v4.1-flash")
BATCH = 200          # rows per SELECT; the work is one API call at a time anyway
LOG_EVERY = 25

# USD per token, DeepSeek list price.
PRICE_IN = 0.14 / 1_000_000
PRICE_OUT = 0.28 / 1_000_000

# Accumulated across the process so main() can price the run without threading
# a counter through every function.
USAGE = {"prompt_tokens": 0, "completion_tokens": 0}

_PUNCT = re.compile(r"[^a-z0-9]+")


def normalize_entity(raw):
    """Placeholder entity_key until real resolution exists (see SPEC.md).

    Folds case and punctuation only. Apostrophes are deleted rather than turned
    into a separator so "L'Industrie", "L’industrie" and "lindustrie"
    collapse to one key; every other punctuation mark becomes a space. This is
    deliberately NOT trying to merge "L'Industrie" with "L'Industrie Pizzeria" --
    that is the resolution problem, and guessing at it here would destroy
    evidence.
    """
    s = (raw or "").lower().replace("'", "").replace("’", "")
    s = " ".join(_PUNCT.sub(" ", s).split())
    if s.startswith("the "):
        s = s[4:]
    for suffix in (" restaurant", " nyc"):
        if s.endswith(suffix):
            s = s[:-len(suffix)]
    return s.strip()


def _load_chains():
    """Resolved against this file, not the cwd -- it loads at import time."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chains.txt")
    with open(path, encoding="utf-8") as f:
        return {normalize_entity(line) for line in f if line.strip()}


CHAINS = _load_chains()


def is_chain(entity_key):
    return entity_key in CHAINS


def call_model(system, user, attempt=0):
    """One completion. Returns the raw JSON string the model produced."""
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, headers={
        "Authorization": "Bearer " + os.environ[API_KEY_VAR],
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            payload = json.load(r)
    # HTTPError is a subclass of OSError, so it has to be caught first.
    except urllib.error.HTTPError as e:
        if (e.code == 429 or e.code >= 500) and attempt < 7:
            wait = min(5 * (2 ** attempt), 120)
            print(f"    http {e.code}, retrying in {wait}s")
            time.sleep(wait)
            return call_model(system, user, attempt + 1)
        raise
    except (OSError, http.client.HTTPException) as e:
        # Covers URLError, timeouts, and RemoteDisconnected / connection resets.
        # Over hundreds of thousands of requests the server will drop a
        # connection sooner or later; that is transient and must not end the run.
        if attempt < 7:
            wait = min(5 * (2 ** attempt), 120)
            print(f"    {type(e).__name__}: {e}, retrying in {wait}s")
            time.sleep(wait)
            return call_model(system, user, attempt + 1)
        raise

    usage = payload.get("usage") or {}
    USAGE["prompt_tokens"] += usage.get("prompt_tokens") or 0
    USAGE["completion_tokens"] += usage.get("completion_tokens") or 0
    return payload["choices"][0]["message"]["content"]


def next_batch(conn, limit=200, since=None):
    """Comments still needing extraction, with everything the prompt asks for.

    One query rather than a lookup per comment: the thread is an inner join (the
    foreign key guarantees it exists), the parent a left join -- 70% of comments
    are top-level, and a parent that arrived late or was purged simply comes back
    null.

    Ordering by thread_id rides the partial index and keeps a thread's comments
    adjacent, so an interrupted run leaves whole threads finished.
    """
    with conn.cursor() as cur:
        cur.execute("""
            select c.id, c.body, t.title, t.selftext, p.body
            from comments c
            join threads t on t.id = c.thread_id
            left join comments p on p.id = c.parent_comment_id
            where c.extracted_at is null
              and c.extract_error is null
              and c.body not in ('[deleted]', '[removed]')
              and length(c.body) > 15
              and (%s is null or c.created_utc >= %s)
            order by c.thread_id, c.created_utc
            limit %s
        """, (since, since, limit))
        return cur.fetchall()


def _mark_extracted(conn, comment_id):
    with conn.cursor() as cur:
        cur.execute("""
            update comments
            set extracted_at = now(), extracted_with = %s, extract_error = null
            where id = %s
        """, (f"{MODEL}:{prompt.PROMPT_HASH}", comment_id))
    conn.commit()


def _mark_error(conn, comment_id, message):
    with conn.cursor() as cur:
        cur.execute("update comments set extract_error = %s where id = %s",
                    (message[:500], comment_id))
    conn.commit()


def fetch_one(row):
    """The network half. Runs on a worker thread: touches no database.

    Returns (comment_id, mentions, error). psycopg2 connections are not
    thread-safe, so every write is handed back to the main thread.
    """
    comment_id, body, title, selftext, parent = row
    user = prompt.build_user_message(body, title, selftext, parent)
    last = None
    # Malformed JSON runs about 1 in 600. It is not deterministic -- the same
    # prompt usually parses on a second attempt -- so retry before parking it.
    for attempt in range(2):
        try:
            raw = call_model(prompt.SYSTEM_PROMPT, user)
            return comment_id, json.loads(raw).get("mentions") or [], None
        except (json.JSONDecodeError, TypeError) as e:
            last = f"{type(e).__name__}: {e}"
        except Exception as e:
            # Network and HTTP failures already exhausted call_model's backoff;
            # retrying here would just double the wait.
            return comment_id, None, f"{type(e).__name__}: {e}"
    return comment_id, None, last


def store_one(conn, comment_id, mentions, error):
    """The database half. Main thread only."""
    if error is not None:
        _mark_error(conn, comment_id, error)
        return 0

    keep = []
    for m in mentions:
        name = (m.get("restaurant_raw") or "").strip()
        if not name:
            continue
        m["restaurant_raw"] = name
        m["entity_key"] = normalize_entity(name)
        # Chains are dropped at write time rather than filtered at query time:
        # 79 names over 12 years is a lot of rows nothing downstream will rank.
        if m["entity_key"] and not is_chain(m["entity_key"]):
            keep.append(m)

    n = db.insert_mentions(conn, comment_id, keep, MODEL, prompt.PROMPT_HASH)
    # Marked only after the insert commits, so a crash in between costs one
    # re-extracted comment rather than silently losing its mentions.
    _mark_extracted(conn, comment_id)
    return n


def run(conn, limit=None, since=None, workers=WORKERS):
    """Fan the API calls out across threads; keep every write on this thread.

    The work is pure latency -- a call takes ~9s and almost all of it is
    waiting. Sequentially that is ~7 comments/min, which is ten days for a
    six-month window. psycopg2 connections are not thread-safe, so the pool
    only ever runs fetch_one, and store_one stays here.
    """
    done = found = 0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            while limit is None or done < limit:
                take = BATCH if limit is None else min(BATCH, limit - done)
                rows = next_batch(conn, take, since)
                if not rows:
                    break
                for result in pool.map(fetch_one, rows):
                    found += store_one(conn, *result)
                    done += 1
                    if done % LOG_EVERY == 0:
                        print(f"  {done:,} comments  {found:,} mentions", flush=True)
    except KeyboardInterrupt:
        print("\ninterrupted -- finished comments are committed, re-run to resume")
    return done, found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after N comments")
    ap.add_argument("--workers", type=int, default=WORKERS,
                    help="concurrent API calls")
    ap.add_argument("--since", metavar="MONTHS", type=int, default=None,
                    help="only extract comments from the last N months")
    ap.add_argument("--retry-errors", action="store_true",
                    help="clear extract_error and reprocess those comments")
    ap.add_argument("--reset", metavar="PROMPT_HASH", nargs="?", const=prompt.PROMPT_HASH,
                    help="undo a run: delete its mentions and un-mark its comments "
                         "(defaults to the current prompt hash)")
    args = ap.parse_args()

    # --reset needs no API key and must run before the key check.
    if args.reset:
        conn = db.connect()
        with conn.cursor() as cur:
            cur.execute("delete from mentions where prompt_hash = %s", (args.reset,))
            gone = cur.rowcount
            cur.execute("update comments set extracted_at = null, extracted_with = null "
                        "where extracted_with = %s", (args.reset,))
            unmarked = cur.rowcount
        conn.commit()
        print(f"reset {args.reset}: {gone:,} mentions deleted, "
              f"{unmarked:,} comments returned to the queue")
        return

    # Fail here rather than per comment: a missing key raises inside
    # extract_comment, which would happily stamp 384k rows with the same error.
    # db's .env loader has already run by import time.
    if not os.environ.get(API_KEY_VAR):
        raise SystemExit(f"{API_KEY_VAR} is not set (add it to .env next to DATABASE_URL)")

    conn = db.connect()

    if args.retry_errors:
        with conn.cursor() as cur:
            cur.execute("update comments set extract_error = null "
                        "where extract_error is not null")
            print(f"cleared {cur.rowcount:,} error(s)")
        conn.commit()

    began = time.time()
    since = None
    if args.since:
        with conn.cursor() as cur:
            cur.execute("select now() - make_interval(months => %s)", (args.since,))
            since = cur.fetchone()[0]
        with conn.cursor() as cur:
            cur.execute("""select count(*) from comments
                           where extracted_at is null and extract_error is null
                             and body not in ('[deleted]','[removed]')
                             and length(body) > 15 and created_utc >= %s""", (since,))
            print(f"{cur.fetchone()[0]:,} comments from the last {args.since} months")

    done, found = run(conn, args.limit, since, args.workers)

    cost = (USAGE["prompt_tokens"] * PRICE_IN
            + USAGE["completion_tokens"] * PRICE_OUT)
    print(f"\n{done:,} comments, {found:,} mentions "
          f"({(time.time() - began) / 60:.1f} min)")
    print(f"tokens: {USAGE['prompt_tokens']:,} in / "
          f"{USAGE['completion_tokens']:,} out   est. ${cost:.2f}")
    if done:
        print(f"  ${cost / done * 1000:.2f} per 1,000 comments")


if __name__ == "__main__":
    main()
