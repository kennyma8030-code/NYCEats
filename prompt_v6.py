"""The v6 extraction prompt, exactly as benchmarked, and the inputs it is given.

The prompt text, the strict schema and the v6 -> legacy mapping are not
written here. They are the round-4 files from the benchmark branch
(extraction-v6: eval/prompts/v6_common.py, v6_comment.py, v6_schema.json and
eval/v6_adapter.py), copied byte for byte into prompts_v6/ and loaded from
there. tests/test_prompt_v6.py pins their hashes and compares them with the
branch, so production cannot drift from what the Opus review measured
without a test failing. To change the prompt, change it on the benchmark
branch, re-measure, and copy the files over again.

What this module adds is production's half of the input: reading the rows
the benchmark's renderer needs straight from the database. The benchmark
built those rows with eval/build_comment_rows.py (fetch_rows); fetch_comment_rows
below is the same walk, so a comment renders to the same bytes here as it did
in the benchmark. tests/test_extract_v6_db.py checks that on a real Postgres.

Comment mode sees the post title, the post body (cut at 1,200 characters,
author="you" when the commenter wrote the post), up to five ancestors (the
parent cut at 1,500, the rest at 300, labelled OP / you, earlier / another
user, with deleted and missing ones marked) and the comment, with '>' quote
blocks marked. Post mode sees the title and the body cut at 4,000.

Thread mode (prompts_v6/v6_thread.py) is the one prompt here that is not
byte for byte the benchmark's: it is round 4's thread prompt plus the
additions listed in tests/v6_thread_additions.py (the post as item [0], and
quoted ancestor chains), so it has its own hash. fetch_thread_rows reads the
whole comment tree it needs; thread_chunks.py cuts it into chunks.
"""

import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(HERE, "prompts_v6")


def _load(name):
    spec = importlib.util.spec_from_file_location(f"prompts_v6_{name}", os.path.join(VENDOR, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_comment = _load("v6_comment")   # loads v6_common.py and v6_schema.json from the same folder
adapter = _load("v6_adapter")
# Thread mode: the round-4 thread prompt and renderer plus two production
# additions (the post as item [0], quoted ancestor chains), each listed in
# tests/v6_thread_additions.py. thread_chunks.py decides what goes in a chunk.
thread = _load("v6_thread")

SYSTEM_PROMPT = _comment.SYSTEM_PROMPT
SYSTEM_PROMPT_POST = _comment.SYSTEM_PROMPT_POST
SCHEMA = _comment.SCHEMA
PROMPT_HASH = _comment.PROMPT_HASH                 # 979dcd6b9267
PROMPT_HASH_POST = _comment.PROMPT_HASH_POST       # 436d834d7edd
build_user_message = _comment.build_user_message   # (comment_rows record) -> str
build_post_message = _comment.build_post_message   # (title, selftext) -> str
SYSTEM_PROMPT_THREAD = thread.SYSTEM_PROMPT
SCHEMA_THREAD = thread.SCHEMA                      # the comment schema with an integer "id" first
PROMPT_HASH_THREAD = thread.PROMPT_HASH            # ac9b063da8e6

GONE = ("[deleted]", "[removed]")
# One more ancestor than the renderer shows, so it knows when it cut and says
# "(N earlier comments not shown)". Same constant as the benchmark's builder.
ANCESTORS = 6

# The benchmark's settings (eval/bench_v6.py steps o and p, the run the Opus
# review measured). Not tunables: changing one is a new benchmark.
MODEL = "claude-haiku-5-5"
EFFORT = "medium"
MAX_TOKENS = 16000
SCHEMA_VERSION = 6
# Thread mode was benchmarked with round 1's prompt at low and medium: at
# medium 109 of 361 chunks overflowed 16k on thinking, and at low the worst
# chunk used 29k (eval/bench_v6/DIAGNOSIS.md), so a chunk gets 32k. Medium is
# the owner's default; low is the cheaper setting under test.
THREAD_MAX_TOKENS = 32000
THREAD_EFFORTS = ("low", "medium")
THREAD_EFFORT = "medium"

# The owner's five levels as the small integers the v6 columns store, so they
# sort and count directly. NULL means the text said nothing; 0 is "mixed".
LEVEL_INT = {"superlative_praise": 2, "praise": 1, "mixed": 0, "knock": -1, "extreme_knock": -2}
PRICE_INT = {"very_cheap": -2, "cheap": -1, "moderate": 0, "expensive": 1, "very_expensive": 2}
KINDS_EXCLUDED = tuple(adapter.EXCLUDED_KINDS)     # grocery, brand, venue, company, other


def comment_record(cid, tid, author, body, title, selftext, thread_author, chain):
    """One comment's input record, in the shape build_user_message reads.

    `chain` is the ancestors nearest first, each {"id", "author", "body",
    "state"}; the record keeps the nearest ANCESTORS of them, oldest first,
    and the full depth in ancestors_total. Same layout as the benchmark's
    <items>.comment_rows.jsonl.
    """
    return {"call_key": f"comment:{cid}", "comment_id": cid, "thread_id": tid,
            "author": author, "body": body, "title": title, "selftext": selftext,
            "thread_author": thread_author, "ancestors": chain[:ANCESTORS][::-1],
            "ancestors_total": len(chain)}


def fetch_comment_rows(conn, cids):
    """{comment_id: input record} for the given comment ids that exist.

    The walk up the reply chain is the benchmark's (build_comment_rows.fetch_rows):
    one query per level for every comment at once, an ancestor not in the
    database ends the chain as "missing", and a [deleted]/[removed] one is
    kept as "deleted" with no body. It follows the whole chain, not just six
    levels, because ancestors_total is the full depth.
    """
    cids = sorted(set(cids))
    if not cids:
        return {}
    with conn.cursor() as cur:
        cur.execute("""select c.id, c.thread_id, c.author, c.body, c.parent_comment_id,
                              t.title, t.selftext, t.author
                       from comments c join threads t on t.id = c.thread_id
                       where c.id = any(%s)""", (cids,))
        base = {r[0]: r for r in cur.fetchall()}
        rows = {}
        frontier = {r[4] for r in base.values() if r[4]}
        while frontier:
            cur.execute("select id, author, body, parent_comment_id from comments where id = any(%s)",
                        (sorted(frontier),))
            got = {r[0]: r for r in cur.fetchall()}
            rows.update(got)
            frontier = {r[3] for r in got.values() if r[3] and r[3] not in rows}
    out = {}
    for cid, (_, tid, author, body, parent, title, selftext, tauthor) in base.items():
        chain, p, seen = [], parent, set()
        # `seen` only guards against a corrupt cycle in parent ids, which the
        # benchmark's corpus never had; on a clean chain it changes nothing.
        while p and p not in seen:
            seen.add(p)
            r = rows.get(p)
            if r is None:
                chain.append({"id": p, "author": None, "body": None, "state": "missing"})
                break
            gone = (r[2] or "").strip() in GONE
            chain.append({"id": p, "author": r[1], "body": None if gone else r[2],
                          "state": "deleted" if gone else "ok"})
            p = r[3]
        out[cid] = comment_record(cid, tid, author, body, title, selftext, tauthor, chain)
    return out


def fetch_post_rows(conn, tids):
    """{thread_id: (title, selftext, author)} for the given posts that exist."""
    tids = sorted(set(tids))
    if not tids:
        return {}
    with conn.cursor() as cur:
        cur.execute("select id, title, selftext, author from threads where id = any(%s)", (tids,))
        return {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}


def fetch_thread_rows(conn, tids):
    """{thread_id: {"title", "selftext", "author", "comments": [row]}} for the given posts that exist.

    Every comment of each thread, due or not and deleted or not, because the
    chunker needs the whole tree to group replies and to quote ancestors. A
    row is {"comment_id", "parent_comment_id", "author", "body", "created_utc"},
    which is what thread_chunks reads."""
    tids = sorted(set(tids))
    if not tids:
        return {}
    with conn.cursor() as cur:
        cur.execute("select id, title, selftext, author from threads where id = any(%s)", (tids,))
        out = {r[0]: {"title": r[1], "selftext": r[2], "author": r[3], "comments": []} for r in cur.fetchall()}
        cur.execute("""select id, thread_id, parent_comment_id, author, body, created_utc from comments
                       where thread_id = any(%s) order by thread_id, created_utc, id""", (tids,))
        for cid, tid, parent, author, body, created in cur.fetchall():
            if tid in out:
                out[tid]["comments"].append({"comment_id": cid, "parent_comment_id": parent, "author": author,
                                             "body": body, "created_utc": created.isoformat() if created else ""})
    return out


def render(kind, row):
    """(system prompt, user message, prompt hash) for one item.

    kind "comment" takes a fetch_comment_rows record, kind "post" a
    fetch_post_rows tuple.
    """
    if kind == "comment":
        return SYSTEM_PROMPT, build_user_message(row), PROMPT_HASH
    title, selftext, _author = row
    return SYSTEM_PROMPT_POST, build_post_message(title, selftext), PROMPT_HASH_POST
