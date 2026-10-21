"""v6 extraction: r/FoodNYC's comments and posts through Claude Haiku 5.5, as benchmarked.

    python extract_v6.py --dry-run                         render and price the backlog; no API, no writes
    python extract_v6.py --batch --max-usd 70              the backlog through Message Batches at half price
    python extract_v6.py --batch --max-usd 5 --since 2026-09-01 --limit 3000 --scope comments
    python extract_v6.py --max-usd 1 --ids t1_abc,t3_def   direct calls, a few items
    python extract_v6.py --status                          cursor, errors, batches in flight, spend
    python extract_v6.py --read v6                         make the board count v6 rows (and refresh)
    python extract_v6.py --reset-hash 979dcd6b9267 --yes   redo what that prompt extracted (after a fix)
    python extract_v6.py --mode thread --dry-run --newest-first --limit 500   chunk and price threads
    python extract_v6.py --mode thread --batch --max-usd 20 --newest-first    a post and its comments per chunk

Thread mode (--mode thread) sends a thread's post and up to about 25 of its
comments as one request (thread_chunks.py says what goes together), with the
thread prompt (its own hash), effort medium unless --effort low, and 32k
max_tokens. Each item still gets its own extraction_state row, so the two
modes share one cursor and never extract an item twice. See the thread mode
section below and docs/handoffs/extraction-v6-thread.md.

`extract.py --v6 ...` runs this too. Like every pipeline script it reads
DATABASE_URL and writes to production, so it is run on purpose, one run at a
time. Only --dry-run and --status are read-only.

What runs is exactly the benchmarked setup: prompt_v6 (round 4, comment mode
979dcd6b9267, post mode 436d834d7edd) and anthropic_v6 (model, effort medium,
strict schema, cached system prompt, max_tokens 16k). What differs from the old
extractor (extract.py), on purpose:
  * every r/FoodNYC comment that is not [deleted]/[removed]/empty is a
    candidate, however short: "keens" and "+1" are real evidence. The old
    `length(body) > 15` cut is gone;
  * chain mentions are kept, with is_chain set, instead of deleted at write;
  * each r/FoodNYC post (title + body) is extracted too, in post mode, and its
    mentions name the thread instead of a comment;
  * mentions of excluded kinds (grocery, brand, venue, company, other) are
    stored with their kind, and live_mentions leaves them out;
  * the cursor is extraction_state, not comments.extracted_at, so the two
    extractors run side by side without either skipping the other's work.

Old mentions are never touched. v6 rows go in beside them with
schema_version 6, and the board keeps reading the old ones until
`--read v6` flips extraction_settings (see docs/handoffs/extraction-v6.md).

Spend: --max-usd is a hard cap for this invocation. Each request's worst case
(all input billed as a cache write, all 16k tokens out) is held before it is
sent; a batch holds the sum of its requests, and is sized to what remains.
Holds become actual cost as results come back, so the cap is on real spend
plus what is in flight. An attempt that may have been billed without an
answer (a timeout) is charged its worst case, and its retry must reserve
again or is not sent. Batches re-attached from an earlier run count against
this run's cap until collected.

One v6 run at a time: every run that writes takes a Postgres advisory lock
(try_lock), and the poller's pass skips while a manual run holds it.

A batch submission that times out or gets a 5xx may still have been
accepted, so it is never resubmitted: its 'pending-' row stays, the run
stops, and the next run adopts the one batch in the API's list that matches
it. If none matches once the row is over half an hour old and the list has
been read back past it, it made none, and its items are due again; anything
else stops for --resolve-pending. A batch the API answers 404 for is marked
lost, its items held back until --drop-batch.

An item that gets no usable answer (stop_reason max_tokens or refusal,
invalid JSON, a batch request that errored or expired) is retried once, then
parked with a coded extract_error until --retry-errors. A 4xx other than 429
stops the run without marking anything; so do rate limits or outages that
outlast the backoff.
"""

import argparse
import concurrent.futures
import datetime as dt
import os
import sys
import threading
import time
import uuid

from psycopg2.extras import Json, execute_values

import anthropic_v6 as AV
import db
import extract
import prompt_v6
import subreddits
import thread_chunks as T

VERSION = "v6"
KINDS = ("comment", "post")
BATCH_SIZE = 2000        # requests per sub-batch; ~60MB of request at ~29KB each
MAX_INFLIGHT = 4         # sub-batches in flight at once (also bounded by the cap)
POLL_SECONDS = 60
WORKERS = 8
# An item gets one retry: the first failure queues it again, the second parks it.
MAX_ATTEMPTS = 2
# Items stored per transaction when a batch is collected: few enough that a
# refused row costs one chunk's retry item by item, many enough that a
# 2,000-item batch is stored in ten transactions of a few statements each.
WRITE_CHUNK = 200
GONE = ("", "[deleted]", "[removed]")


class SchemaMissing(SystemExit):
    pass


def schema_ready(conn):
    """True when extract_v6_schema.sql has been applied (schema.sql applies it on boot)."""
    with conn.cursor() as cur:
        cur.execute("""select to_regclass('extraction_state') is not null
                          and to_regclass('extract_batches') is not null
                          and exists (select 1 from information_schema.columns
                                      where table_name = 'mentions' and column_name = 'schema_version'
                                        and table_schema = current_schema())""")
        ok = cur.fetchone()[0]
    conn.commit()
    return ok


# One v6 run at a time, across processes: the poller's pass and a manual
# backfill would otherwise both pick the same due items and pay for them
# twice. A session-level advisory lock, so it survives the commits a run
# makes and goes away by itself if the process or its connection dies.
LOCK_KEY = 0x6E796336_7636            # "nyc6" "v6"


def try_lock(conn):
    with conn.cursor() as cur:
        cur.execute("select pg_try_advisory_lock(%s)", (LOCK_KEY,))
        ok = cur.fetchone()[0]
    conn.commit()
    return ok


def unlock(conn):
    conn.rollback()           # a failed statement may have left the transaction aborted
    with conn.cursor() as cur:
        cur.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))
    conn.commit()


def require_schema(conn, thread=False):
    if not schema_ready(conn):
        raise SchemaMissing("v6 tables are missing: apply extract_v6_schema.sql first")
    if thread and not chunks_ready(conn):
        raise SchemaMissing("extract_chunks is missing: apply extract_v6_schema.sql again (thread mode adds it)")


def chunks_ready(conn):
    """True when thread mode's table is there. Comment and post mode never need it."""
    with conn.cursor() as cur:
        cur.execute("select to_regclass('extract_chunks') is not null")
        ok = cur.fetchone()[0]
    conn.commit()
    return ok


# ---------------------------------------------------------------- spend
class Budget:
    """A hard cap on one run's spend. Thread-safe.

    reserve() holds a direct request's worst case before it is sent; settle()
    swaps it for the real cost. hold() does the same for a whole batch, keyed
    by its id, so a re-attached batch is counted until it is collected.
    """

    def __init__(self, max_usd):
        self.max = float(max_usd)
        self.spent = 0.0
        self.reserved = 0.0
        self.held = {}
        self._lock = threading.Lock()

    def remaining(self):
        with self._lock:
            return self.max - self.spent - self.reserved - sum(self.held.values())

    def reserve(self, amount):
        with self._lock:
            if self.spent + self.reserved + sum(self.held.values()) + amount > self.max:
                return False
            self.reserved += amount
            return True

    def settle(self, reserved, actual):
        with self._lock:
            self.reserved -= reserved
            self.spent += actual

    def charge(self, amount):
        """Spend with no reservation behind it: an attempt that may have been billed unseen."""
        with self._lock:
            self.spent += amount

    def hold(self, key, amount, force=False):
        with self._lock:
            if not force and self.spent + self.reserved + sum(self.held.values()) + amount > self.max:
                return False
            self.held[key] = self.held.get(key, 0.0) + amount
            return True

    def rename(self, old, new):
        with self._lock:
            self.held[new] = self.held.pop(old)

    def release(self, key, actual):
        with self._lock:
            self.held.pop(key, None)
            self.spent += actual


class Stats:
    def __init__(self):
        self.done = self.mentions = self.failed = self.parked = self.refused = 0
        # Thread mode: chunks answered, chunks that failed (split or sent on
        # alone), mentions dropped for an id naming no item, threads not reached.
        self.chunks = self.chunk_failures = self.bad_ids = self.threads_left = 0
        self.tokens = {"input_tokens": 0, "cache_creation_input_tokens": 0,
                       "cache_read_input_tokens": 0, "output_tokens": 0}
        self.cost = 0.0

    def add_usage(self, usage, cost):
        for k in self.tokens:
            self.tokens[k] += (usage or {}).get(k) or 0
        self.cost += cost

    def line(self):
        t = self.tokens
        per = f", ${self.cost / self.done * 1000:.2f} per 1,000 items" if self.done else ""
        chunks = (f"{self.chunks:,} chunk(s) answered, {self.chunk_failures:,} failed and retried smaller, "
                  f"{self.bad_ids:,} mention(s) dropped for a bad id | ") if self.chunks or self.chunk_failures else ""
        return (f"{chunks}{self.done:,} extracted, {self.mentions:,} mentions, {self.failed:,} failed "
                f"({self.parked:,} parked), {self.refused:,} not sent (cap) | tokens in {t['input_tokens']:,} "
                f"+ cache write {t['cache_creation_input_tokens']:,} + cache read "
                f"{t['cache_read_input_tokens']:,}, out {t['output_tokens']:,} | ${self.cost:.4f}{per}")


# ---------------------------------------------------------------- candidates
QUEUED = "(s.item_id is null or (s.extracted_at is null and s.extract_error is null and s.batch_id is null))"


def candidate_ids(conn, kind, limit=None, since=None, ids=None, max_chars=None, seen_since=None):
    """Item ids still due under v6, in processing order.

    r/FoodNYC only (subreddits.HOME): the other cities are collected, never
    extracted. A comment is due unless it is [deleted]/[removed]/blank,
    however short. Comments come thread by thread, so an interrupted run
    leaves whole threads finished; posts oldest first.

    `since` is on created_utc (when it was written), `seen_since` on
    first_seen_at (when this database got it). The poller uses the second:
    a comment can arrive days after it was written (a backfill, a thread
    re-read, ~280 a week), and a window on created_utc never sees it.
    """
    p = {"home": subreddits.HOME, "v": VERSION, "since": since, "ids": list(ids) if ids else None,
         "max_chars": max_chars, "limit": limit, "seen": seen_since}
    if kind == "comment":
        sql = f"""
            select c.id from comments c
            left join extraction_state s on s.item_id = c.id and s.version = %(v)s
            where c.subreddit = %(home)s
              and btrim(c.body) not in ('', '[deleted]', '[removed]')
              and {QUEUED}
              and (%(since)s::timestamptz is null or c.created_utc >= %(since)s::timestamptz)
              -- first_seen_at is NOT NULL (default now() on insert), so it needs no
              -- coalesce with created_utc, and comments_first_seen_idx can serve it.
              and (%(seen)s::timestamptz is null or c.first_seen_at >= %(seen)s::timestamptz)
              and (%(ids)s::text[] is null or c.id = any(%(ids)s::text[]))
              and (%(max_chars)s::int is null or length(btrim(c.body)) <= %(max_chars)s::int)
            order by c.thread_id, c.created_utc, c.id
            limit %(limit)s"""
    else:
        sql = f"""
            select t.id from threads t
            left join extraction_state s on s.item_id = t.id and s.version = %(v)s
            where t.subreddit = %(home)s
              and {QUEUED}
              and (%(since)s::timestamptz is null or t.created_utc >= %(since)s::timestamptz)
              and (%(seen)s::timestamptz is null or t.first_seen_at >= %(seen)s::timestamptz)
              and (%(ids)s::text[] is null or t.id = any(%(ids)s::text[]))
            order by t.created_utc, t.id
            limit %(limit)s"""
    with conn.cursor() as cur:
        cur.execute(sql, p)
        out = [r[0] for r in cur.fetchall()]
    conn.commit()
    return out


def late_backlog(conn, seen_since, written_before):
    """How many due r/FoodNYC items reached the database since seen_since but
    were written before written_before: the late arrivals the poller leaves
    for a batch catch-up rather than buy at the direct price."""
    with conn.cursor() as cur:
        cur.execute(f"""
            select (select count(*) from comments c
                    left join extraction_state s on s.item_id = c.id and s.version = %(v)s
                    where c.subreddit = %(home)s and btrim(c.body) not in ('', '[deleted]', '[removed]')
                      and {QUEUED} and c.first_seen_at >= %(seen)s and c.created_utc < %(before)s)
                 + (select count(*) from threads t
                    left join extraction_state s on s.item_id = t.id and s.version = %(v)s
                    where t.subreddit = %(home)s
                      and {QUEUED} and t.first_seen_at >= %(seen)s and t.created_utc < %(before)s)""",
                    {"v": VERSION, "home": subreddits.HOME, "seen": seen_since, "before": written_before})
        n = cur.fetchone()[0]
    conn.commit()
    return n


class Item:
    __slots__ = ("kind", "id", "system", "user", "prompt_hash", "attempts")

    def __init__(self, kind, item_id, system, user, prompt_hash):
        self.kind, self.id, self.system, self.user, self.prompt_hash = kind, item_id, system, user, prompt_hash
        self.attempts = 0

    def worst(self, batch):
        return AV.worst_case(self.system, self.user, batch)

    def params(self):
        return AV.params(self.system, self.user)


def render_items(conn, kind, ids):
    """Items for these ids, in the given order, rendered exactly as benchmarked."""
    rows = (prompt_v6.fetch_comment_rows if kind == "comment" else prompt_v6.fetch_post_rows)(conn, ids)
    conn.commit()
    out = []
    for i in ids:
        if i in rows:
            system, user, ph = prompt_v6.render(kind, rows[i])
            out.append(Item(kind, i, system, user, ph))
    return out


# ---------------------------------------------------------------- writer
LEVELS = prompt_v6.LEVEL_INT


def _level(v):
    return LEVELS.get(v) if isinstance(v, str) else None


def mention_row(item, m):
    """One v6 mention as a mentions row: v6 columns, plus the legacy columns
    filled by the benchmark's adapter so scoring.sql reads it unchanged.
    None when it names nothing a key can be made of."""
    name = (m.get("name") or "").strip() if isinstance(m.get("name"), str) else ""
    key = extract.normalize_entity(name)
    if not name or not key:
        return None
    legacy = prompt_v6.adapter.to_legacy(m)
    asp = m.get("aspects") if isinstance(m.get("aspects"), dict) else {}
    dishes = [d for d in (m.get("dishes") or []) if isinstance(d, dict) and d.get("dish")]
    return {
        "comment_id": item.id if item.kind == "comment" else None,
        "thread_id": item.id if item.kind == "post" else None,
        "restaurant_raw": name,
        "entity_key": key,
        "neighborhood_hint": legacy["neighborhood_hint"],
        "dishes": Json(legacy["dishes"]),
        "descriptors": Json(legacy["descriptors"]),
        # Pinned to the five legacy keys and clamped, like db.insert_mentions.
        "aspects": Json({k: db._score(legacy["aspects"].get(k)) for k in db.ASPECTS}),
        "expensiveness": db._score(legacy["expensiveness"]),
        "is_firsthand": legacy["is_firsthand"],
        "is_negated": legacy["is_negated"],
        "model_version": prompt_v6.MODEL,
        "prompt_hash": item.prompt_hash,
        "schema_version": prompt_v6.SCHEMA_VERSION,
        "raw": Json(m),
        "kind": m.get("kind"),
        "named_in": m.get("named_in"),
        "experience": m.get("experience"),
        "opinion": m.get("opinion"),
        "overall_level": _level(m.get("overall")),
        "taste_level": _level(asp.get("taste")),
        "value_level": _level(asp.get("value")),
        "service_level": _level(asp.get("service")),
        "atmosphere_level": _level(asp.get("atmosphere")),
        "wait_level": _level(asp.get("wait")),
        "avoid": bool(m.get("avoid")),
        "dish_opinions": Json([{"dish": d["dish"], "level": _level(d.get("level")),
                                "avoid": bool(d.get("avoid"))} for d in dishes]),
        "notes": Json([n for n in (m.get("notes") or []) if isinstance(n, dict)]),
        "tags": Json([str(t) for t in (m.get("tags") or [])]),
        "price_level": prompt_v6.PRICE_INT.get(m.get("price")),
        "timeframe": m.get("timeframe"),
        "trend": m.get("trend"),
        "status": m.get("status"),
        "is_chain": extract.is_chain(key),
    }


COLUMNS = ("comment_id", "thread_id", "restaurant_raw", "entity_key", "neighborhood_hint", "dishes",
           "descriptors", "aspects", "expensiveness", "is_firsthand", "is_negated", "model_version",
           "prompt_hash", "schema_version", "raw", "kind", "named_in", "experience", "opinion",
           "overall_level", "taste_level", "value_level", "service_level", "atmosphere_level",
           "wait_level", "avoid", "dish_opinions", "notes", "tags", "price_level", "timeframe",
           "trend", "status", "is_chain")
_INSERT = (f"insert into mentions ({', '.join(COLUMNS)}) values %s "
           # Must match mentions_unique_idx / mentions_post_unique_idx exactly.
           "on conflict {target} do nothing returning id")
_TARGET = {"comment": "(comment_id, entity_key, prompt_hash)",
           "post": "(thread_id, entity_key, prompt_hash) where comment_id is null"}

# The state rows of many items in one statement. Every column is set from the
# values, so a row reads the same whether it was inserted or updated; the
# previous attempts and cost are read first and added to in Python, as before.
_STATE_DONE = """
    insert into extraction_state (item_id, version, kind, prompt_hash, model, batch_id, attempts,
                                  extracted_at, extract_error, output, usage, cost_usd)
    values %s
    on conflict (item_id, version) do update set
      prompt_hash = excluded.prompt_hash, model = excluded.model, batch_id = null,
      attempts = excluded.attempts, extracted_at = excluded.extracted_at, extract_error = null,
      output = excluded.output, usage = excluded.usage, cost_usd = excluded.cost_usd, updated_at = now()"""
# A failure leaves `output` as it was.
_STATE_FAILED = """
    insert into extraction_state (item_id, version, kind, prompt_hash, model, batch_id, attempts,
                                  extracted_at, extract_error, usage, cost_usd)
    values %s
    on conflict (item_id, version) do update set
      prompt_hash = excluded.prompt_hash, model = excluded.model, batch_id = null,
      attempts = excluded.attempts, extracted_at = null, extract_error = excluded.extract_error,
      usage = excluded.usage, cost_usd = excluded.cost_usd, updated_at = now()"""


class Done:
    """An answer to store: the item, the parsed output, what it cost."""
    __slots__ = ("item", "output", "usage", "cost")

    def __init__(self, item, output, usage, cost):
        self.item, self.output, self.usage, self.cost = item, output, usage, cost


class Failed:
    """An item that got no usable answer, and why."""
    __slots__ = ("item", "code", "usage", "cost")

    def __init__(self, item, code, usage=None, cost=0.0):
        self.item, self.code, self.usage, self.cost = item, code, usage, cost


def write(conn, entries, before=None):
    """Store many items' outcomes in one transaction, in a handful of
    statements whatever their number: one select for the previous attempts,
    one insert of mention rows per kind, one upsert of state rows per outcome.

    From a laptop each statement is a ~325 ms round trip to production, so a
    statement per item or per mention made a 2,000-item batch take close to
    an hour to store; in chunks of WRITE_CHUNK this takes about twenty
    seconds. Returns (mention rows written, ids of the items that are now
    parked). Raises if the database refuses any row, and then nothing of the
    call is kept (the caller rolls back).

    Two mentions of one place in an item (the model spelling it two ways)
    share an entity_key and are one row, as in the old writer; the second is
    still in extraction_state.output with everything else the model said.

    before(cur), when given, runs first in the same transaction: thread mode
    records its chunks' answers there, so a chunk and its items commit
    together.
    """
    if not entries and before is None:
        return 0, set()
    now = dt.datetime.now(dt.timezone.utc)
    by_kind = {}
    for e in entries:
        if isinstance(e, Done):
            # Unique on the conflict target within one statement: Postgres
            # refuses an INSERT ... ON CONFLICT that would touch a row twice.
            rows = by_kind.setdefault(e.item.kind, {})
            for r in (mention_row(e.item, m) for m in e.output["mentions"]):
                if r:
                    rows.setdefault((r["comment_id"] or r["thread_id"], r["entity_key"]), r)
    n, parked = 0, set()
    with conn.cursor() as cur:
        if before is not None:
            before(cur)
        cur.execute("select item_id, attempts, coalesce(cost_usd, 0) from extraction_state "
                    "where version = %s and item_id = any(%s)", (VERSION, [e.item.id for e in entries]))
        prev = {r[0]: (r[1], float(r[2])) for r in cur.fetchall()}
        for kind, rows in by_kind.items():
            if rows:
                got = execute_values(cur, _INSERT.format(target=_TARGET[kind]),
                                     [[r[c] for c in COLUMNS] for r in rows.values()],
                                     page_size=len(rows), fetch=True)
                n += len(got)
        done, failed = [], []
        for e in entries:
            it = e.item
            attempts, cost = prev.get(it.id, (0, 0.0))
            attempts += 1
            if isinstance(e, Done):
                done.append((it.id, VERSION, it.kind, it.prompt_hash, prompt_v6.MODEL, None, attempts, now,
                             None, Json(e.output), Json(e.usage), cost + e.cost))
            else:
                park = attempts >= MAX_ATTEMPTS
                if park:
                    parked.add(it.id)
                failed.append((it.id, VERSION, it.kind, it.prompt_hash, prompt_v6.MODEL, None, attempts, None,
                               str(e.code)[:500] if park else None, Json(e.usage) if e.usage else None,
                               cost + e.cost))
        for sql, vals in ((_STATE_DONE, done), (_STATE_FAILED, failed)):
            if vals:
                execute_values(cur, sql, vals, page_size=len(vals))
    conn.commit()
    return n, parked


def store(conn, item, output, usage, cost, batch_id=None):
    """Write one item's mentions and mark it done, in one transaction.
    Returns the number of mention rows written."""
    return write(conn, [Done(item, output, usage, cost)])[0]


def record_failure(conn, item, code, usage=None, cost=0.0, batch_id=None):
    """The item got no usable answer. The first time it is queued again; the
    second it is parked with extract_error until --retry-errors. Returns True
    when parked."""
    return item.id in write(conn, [Failed(item, code, usage, cost)])[1]


def _outcome(item, message, cost, stats):
    """One answer as a Done or a Failed (an ItemError: cut off, refused, not JSON)."""
    usage = AV.usage_of(message)
    stats.add_usage(usage, cost)
    try:
        return Done(item, AV.parse(message), usage, cost)
    except AV.ItemError as e:
        return Failed(item, str(e), usage, cost)


def _write_counted(conn, entries, stats, log=print, before=None):
    """write() the entries and count them. Returns the ids now parked.

    If the database refuses a row (a check constraint, say), the whole chunk
    rolls back and is written again one item at a time, so the refusal parks
    that item with the reason, and the run carries on. `before` (thread
    mode's chunk records) is then committed on its own first, so an answer is
    kept even when one of its items is refused."""
    try:
        n, parked = write(conn, entries, before)
    except Exception:
        conn.rollback()
        if before is not None:
            with conn.cursor() as cur:
                before(cur)
            conn.commit()
        elif len(entries) == 1:
            raise
        parked = set()
        for e in entries:
            parked |= (_write_counted(conn, [e], stats, log) if isinstance(e, Failed)
                       else _store_one(conn, e, stats, log))
        return parked
    stats.mentions += n
    for e in entries:
        if isinstance(e, Done):
            stats.done += 1
        else:
            stats.failed += 1
    stats.parked += len(parked)
    return parked


def _store_one(conn, e, stats, log):
    try:
        return _write_counted(conn, [e], stats, log)
    except Exception as err:
        conn.rollback()
        log(f"  {e.item.id}: store failed ({type(err).__name__}: {err})")
        return _write_counted(conn, [Failed(e.item, f"store_error: {type(err).__name__}: {err}",
                                            e.usage, e.cost)], stats, log)


def _handle(conn, item, message, cost, stats, batch_id=None, log=print):
    """Parse and store one answer, or record why it is not one."""
    e = _outcome(item, message, cost, stats)
    if isinstance(e, Failed):
        _write_counted(conn, [e], stats, log)
    else:
        _store_one(conn, e, stats, log)


# ---------------------------------------------------------------- direct
def run_direct(conn, cl, budget, kinds=KINDS, limit=None, since=None, ids=None, max_chars=None,
               workers=WORKERS, log=print, stats=None, seen_since=None):
    """Extract due items with direct calls, `workers` at a time. Returns Stats.

    The network half runs on threads and touches no database; every write is
    on this thread, because psycopg2 connections are not thread-safe. A
    FatalAPIError or TransientAPIError stops the pass after the answers
    already received are stored; items not sent stay due. When the cap stops
    it, stats.refused counts every due item that was not sent.
    """
    stats = stats or Stats()
    stop, capped = threading.Event(), threading.Event()
    lists, left = [], limit
    for kind in kinds:
        if left is not None and left <= 0:
            break
        todo = candidate_ids(conn, kind, left, since, ids, max_chars if kind == "comment" else None,
                             seen_since)
        lists.append((kind, todo))
        if left is not None:
            left -= len(todo)
    for n, (kind, todo) in enumerate(lists):
        for start in range(0, len(todo), PAGE):
            if stop.is_set():
                if capped.is_set():
                    stats.refused += len(todo) - start + sum(len(t) for _, t in lists[n + 1:])
                return stats
            items = render_items(conn, kind, todo[start:start + PAGE])
            _direct_page(conn, cl, budget, items, workers, stats, stop, capped, log)
    return stats


PAGE = 200


def _direct_page(conn, cl, budget, items, workers, stats, stop, capped, log):
    def work(item):
        if stop.is_set():
            return item, "skipped", 0.0
        w = item.worst(batch=False)
        if not budget.reserve(w):
            capped.set()
            stop.set()
            return item, "skipped", 0.0
        held = [True]

        def again():
            # The attempt that just timed out may have been billed: charge it
            # its worst case, and hold a fresh worst case for the retry.
            budget.settle(w, w)
            held[0] = budget.reserve(w)
            return held[0]
        try:
            msg = AV.call(cl, item.params(), log=log, retry_ok=again)
        except AV.CapReached:
            capped.set()
            stop.set()
            return item, "skipped", 0.0
        except (AV.FatalAPIError, AV.TransientAPIError) as e:
            if held[0]:
                budget.settle(w, w if getattr(e, "maybe_billed", False) else 0.0)
            stop.set()
            return item, e, 0.0
        c = AV.cost(AV.usage_of(msg), batch=False)
        budget.settle(w, c)
        return item, msg, c

    halt = None
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        for fut in concurrent.futures.as_completed([pool.submit(work, it) for it in items]):
            item, res, c = fut.result()
            if isinstance(res, str):
                stats.refused += capped.is_set()
            elif isinstance(res, Exception):
                halt = halt or res
            else:
                _handle(conn, item, res, c, stats, log=log)
    except BaseException:
        # Ctrl-C, or a bug while storing: nothing queued may go out after this.
        # Requests already on the wire finish (their spend is counted); the
        # rest are cancelled, and the work() of any that start sees stop.
        stop.set()
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    if halt is not None:
        raise halt


# ---------------------------------------------------------------- batches
def _pending(conn):
    with conn.cursor() as cur:
        cur.execute("select id from extract_batches where version = %s and status = 'pending'", (VERSION,))
        out = [r[0] for r in cur.fetchall()]
    conn.commit()
    return out


def _inflight(conn):
    with conn.cursor() as cur:
        cur.execute("""select id, hold_usd from extract_batches
                       where version = %s and status = 'submitted' order by created_at""", (VERSION,))
        out = [(r[0], float(r[1])) for r in cur.fetchall()]
    conn.commit()
    return out


def _submit(conn, cl, budget, batch, log):
    """Persist the hold and the items' membership, then submit, then record
    the id. A crash between the two writes leaves a 'pending-' row, which
    stops the next run rather than risk paying for the batch twice."""
    held = sum(it.worst(batch=True) for it in batch)
    pid = f"pending-{int(time.time() * 1000)}-{os.getpid()}"
    # One statement for the ledger row and every member's state row, and a
    # transaction that ends straight after it: a statement per item made this
    # 2,000 round trips (~10 minutes from a laptop) inside one open
    # transaction, holding row locks the whole time.
    with conn.cursor() as cur:
        cur.execute("""
            with b as (insert into extract_batches (id, version, requests, hold_usd)
                       values (%(pid)s, %(v)s, %(n)s, %(held)s))
            insert into extraction_state (item_id, version, kind, prompt_hash, model, batch_id)
            select u.item_id, %(v)s, u.kind, u.prompt_hash, %(model)s, %(pid)s
            from unnest(%(ids)s::text[], %(kinds)s::text[], %(hashes)s::text[]) as u(item_id, kind, prompt_hash)
            on conflict (item_id, version) do update set
              prompt_hash = excluded.prompt_hash, model = excluded.model, batch_id = excluded.batch_id,
              updated_at = now()""",
                    {"pid": pid, "v": VERSION, "n": len(batch), "held": held, "model": prompt_v6.MODEL,
                     "ids": [it.id for it in batch], "kinds": [it.kind for it in batch],
                     "hashes": [it.prompt_hash for it in batch]})
    conn.commit()
    budget.hold(pid, held, force=True)
    try:
        bid = AV.submit(cl, [(it.id, it.params()) for it in batch])
    except (AV.TransientAPIError, AV.FatalAPIError):
        # A refusal (4xx, 429): the API created nothing, so undo the bookkeeping.
        with conn.cursor() as cur:
            cur.execute("""with b as (delete from extract_batches where id = %(pid)s)
                           update extraction_state set batch_id = null where batch_id = %(pid)s""",
                        {"pid": pid})
        conn.commit()
        budget.release(pid, 0.0)
        raise
    except AV.AmbiguousSubmit:
        # The batch may exist and be billing. The pending row and its hold
        # stay, and the run stops; the next one matches it against the API's
        # batch list before anything else is sent (resolve_pending_auto).
        log(f"  submission of {pid} has an unknown outcome; kept as pending, run stops")
        raise
    with conn.cursor() as cur:
        cur.execute("""with b as (update extract_batches set id = %(bid)s, status = 'submitted',
                                                          submitted_at = now()
                                  where id = %(pid)s)
                       update extraction_state set batch_id = %(bid)s where batch_id = %(pid)s""",
                    {"bid": bid, "pid": pid})
    conn.commit()
    budget.rename(pid, bid)
    log(f"submitted batch {bid}: {len(batch)} requests, worst case ${held:.4f} held")
    return bid


def _collect(conn, cl, budget, bid, stats, log, sleep=None):
    """Store a finished batch's answers and settle its hold. Returns the
    items owed a retry (rendered again, so they go out as they would fresh).

    An invalid_request_error inside a batch is the batch-shaped version of a
    direct 4xx: those items are left due and unmarked, the rest is stored, and
    FatalAPIError is raised once the batch is settled."""
    res = AV.results(cl, bid, sleep=sleep, log=log)
    with conn.cursor() as cur:
        cur.execute("select item_id, kind, prompt_hash from extraction_state where batch_id = %s", (bid,))
        members = cur.fetchall()
    conn.commit()
    # The batch's cost is every answer it returned, whether or not its item
    # is still attached here: what was billed is what the cap must count.
    costs = {cid: AV.cost(AV.usage_of(r[1]), batch=True) for cid, r in res.items() if r[0] == "succeeded"}
    total = sum(costs.values())
    stray = set(costs) - {m[0] for m in members}
    if stray:
        log(f"  batch {bid}: {len(stray)} answer(s) for items no longer attached to it, counted, not stored")
    # Everything is parsed first, then written WRITE_CHUNK items per
    # transaction (see write()). A crash part way leaves the chunks already
    # committed done and detached from the batch; the next run re-attaches,
    # stores the rest, and counts the stored ones' cost as stray answers.
    entries, rebatch, invalid, invalid_ids = [], set(), [], []
    for item_id, kind, ph in members:
        item = Item(kind, item_id, None, None, ph)
        r = res.get(item_id, ("missing",))
        if r[0] == "succeeded":
            entries.append(_outcome(item, r[1], costs[item_id], stats))
        elif r[0] == "errored" and r[1] == "invalid_request_error":
            invalid.append(f"{item_id}: {r[2]}")
            invalid_ids.append(item_id)
        else:
            # Only these are sent again in this run; an answer that could not
            # be used is queued for the next run, as on the direct path.
            entries.append(Failed(item, f"batch_{r[0]}" + (f": {r[1]}: {r[2]}" if r[0] == "errored" else "")))
            rebatch.add(item_id)
    parked = set()
    for start in range(0, len(entries), WRITE_CHUNK):
        parked |= _write_counted(conn, entries[start:start + WRITE_CHUNK], stats, log)
    retry = [(e.item.kind, e.item.id) for e in entries if e.item.id in rebatch and e.item.id not in parked]
    with conn.cursor() as cur:
        if invalid_ids:
            cur.execute("update extraction_state set batch_id = null where version = %s and item_id = any(%s)",
                        (VERSION, invalid_ids))
        cur.execute("""update extract_batches set status = 'collected', cost_usd = %s, collected_at = now()
                       where id = %s""", (total, bid))
    conn.commit()
    budget.release(bid, total)
    log(f"  batch {bid} collected: ${total:.4f}, {len(members) - len(retry) - len(invalid)} settled, "
        f"{len(retry)} to retry" + (f", {len(invalid)} invalid" if invalid else ""))
    if invalid:
        log("  invalid_request_error in batch " + bid + ":\n    " + "\n    ".join(invalid[:10]))
        raise AV.FatalAPIError(f"batch {bid}: {len(invalid)} request(s) rejected as invalid; first: {invalid[0]}")
    return retry


def run_batch(conn, cl, budget, kinds=KINDS, limit=None, since=None, ids=None, max_chars=None,
              batch_size=BATCH_SIZE, max_inflight=MAX_INFLIGHT, poll_seconds=POLL_SECONDS,
              log=print, sleep=time.sleep, stats=None):
    """Extract due items through Message Batches under the cap. Returns Stats.

    1. A 'pending-' batch row means a submission whose outcome is unknown.
       It is matched against the API's batch list (resolve_pending_auto):
       exactly one match is adopted; anything else stops the run for a
       person to decide with --resolve-pending, so nothing is sent twice.
    2. Re-attach to batches submitted earlier and not collected; their holds
       count against this run's cap until they are. One the API no longer
       knows (404) is marked lost, not fatal (see _lost).
    3. Submit sub-batches that fit what remains under the cap, up to
       max_inflight at once; collect each as it ends, and send the items it
       hands back for a retry first.
    """
    stats = stats or Stats()
    for pid in _pending(conn):
        bid = resolve_pending_auto(conn, cl, pid, log)
        if bid is None:
            raise SystemExit(f"submission {pid} has an unknown outcome and no single batch in the API's "
                             "list matches it: check the Console, then run --resolve-pending "
                             f"{pid} <batch id | none>")
    inflight = []
    for bid, hold in _inflight(conn):
        budget.hold(bid, hold, force=True)
        inflight.append(bid)
        log(f"re-attaching to batch {bid} (${hold:.4f} held)")

    queue = []          # (kind, id), retries first
    for kind in kinds:
        n = None if limit is None else max(limit - len(queue), 0)
        if n == 0:
            break
        queue += [(kind, i) for i in candidate_ids(conn, kind, n, since, ids,
                                                   max_chars if kind == "comment" else None)]
    log(f"{len(queue):,} item(s) due, {len(inflight)} batch(es) in flight, cap ${budget.max:.2f}")
    capped = False
    while queue or inflight:
        # Top up.
        while queue and not capped and len(inflight) < max_inflight:
            head = queue[:batch_size]
            items = []
            for kind in KINDS:
                ids_k = [i for k, i in head if k == kind]
                items += render_items(conn, kind, ids_k) if ids_k else []
            if not items:
                # Every id in the head is gone from the database; nothing to send.
                queue = queue[len(head):]
                continue
            order = {i: n for n, (_, i) in enumerate(head)}
            items.sort(key=lambda it: order[it.id])
            room, batch, held = budget.remaining(), [], 0.0
            for it in items:
                w = it.worst(batch=True)
                if held + w > room:
                    break
                batch.append(it)
                held += w
            if not batch:
                capped = True
                break
            taken = {it.id for it in batch}
            # What was sent leaves the queue, and so do ids that no longer
            # exist (nothing rendered); the rest of the head goes back in front.
            queue = [(it.kind, it.id) for it in items if it.id not in taken] + queue[len(head):]
            inflight.append(_submit(conn, cl, budget, batch, log))
        if not inflight:
            break
        # Wait for one to end.
        ended, b, lost = None, None, None
        for bid in inflight:
            try:
                b = AV.retrieve(cl, bid, sleep=sleep, log=log)
            except AV.NotFound as e:
                lost = bid
                _lost(conn, budget, bid, e, log)
                break
            if b.processing_status == "ended":
                ended = bid
                break
        if lost is not None:
            inflight.remove(lost)
            capped = False
            continue
        if ended is None:
            c = getattr(b, "request_counts", None)
            if c is not None:
                log(f"  batch {bid}: {b.processing_status}, {c.processing} processing, "
                    f"{c.succeeded} succeeded, {c.errored} errored")
            sleep(poll_seconds)
            continue
        inflight.remove(ended)
        try:
            shape, retry = _collect_any(conn, cl, budget, ended, stats, log, sleep=sleep)
        except AV.NotFound as e:          # results past retention
            _lost(conn, budget, ended, e, log)
            capped = False
            continue
        if shape == "chunks":
            # A thread-mode batch re-attached here: its answers are stored,
            # and what failed waits in extract_chunks (or is due again) for
            # the next run, which sends it.
            if retry:
                log(f"  {len(retry)} thread(s) of {ended} owe a retry; the next run sends it")
            retry = []
        # Retries go first: they finish work already paid for. The hold just
        # became the (much smaller) actual cost, so there may be room again.
        queue = retry + queue
        capped = False
    stats.refused += len(queue)
    return stats


def _lost(conn, budget, bid, err, log):
    """The API answered 404 for a batch we hold: expired past retention, or
    made under another key. Mark it lost so it stops being re-attached (and
    stops failing every later run), release its hold, and leave its items
    attached so nothing is resubmitted until a person says so with
    --drop-batch, which returns them to the queue."""
    with conn.cursor() as cur:
        cur.execute("update extract_batches set status = 'lost', collected_at = now() where id = %s", (bid,))
    conn.commit()
    budget.release(bid, 0.0)
    log(f"  BATCH LOST: {bid} ({err}). Its items stay out of the queue; if the Console confirms it is "
        f"gone, `extract_v6.py --drop-batch {bid}` returns them")


def drop_batch(conn, bid):
    """Return a lost (or abandoned) batch's items to the queue. Only after a
    person has checked the Console: if the batch is in fact still running,
    this pays for those items twice."""
    with conn.cursor() as cur:
        cur.execute("update extract_batches set status = 'lost', collected_at = coalesce(collected_at, now()) "
                    "where id = %s and status in ('lost', 'submitted')", (bid,))
        if cur.rowcount != 1:
            conn.rollback()
            raise SystemExit(f"no lost or submitted batch {bid}")
        cur.execute("""update extraction_state set batch_id = null, updated_at = now()
                       where batch_id = %s and extracted_at is null""", (bid,))
        n = cur.rowcount
        _chunks_requeue(cur, bid)
    conn.commit()
    return n


def _chunks_requeue(cur, batch_id):
    """A thread-mode batch that never ran (a pending submission settled as
    none, a lost batch dropped by hand): its chunks go back to the queue as
    they were, so a half of a failed chunk is still sent as a half."""
    cur.execute("select to_regclass('extract_chunks') is not null")
    if cur.fetchone()[0]:
        cur.execute("""update extract_chunks set status = 'queued', batch_id = null, updated_at = now()
                       where batch_id = %s and status = 'batched'""", (batch_id,))


# A pending row's batch, if the API made one, was created within this window
# of the row (database clock against API clock, and a slow submission).
MATCH_BEFORE = dt.timedelta(minutes=5)
MATCH_AFTER = dt.timedelta(minutes=30)


def pending_matches(conn, cl, pending_id):
    """Batches in the API's list that could be this pending submission: created
    near the row's time, with its number of requests, and not already ours.

    Returns (ids, settled). settled is True when an empty answer is final:
    the row is older than MATCH_AFTER (by the database's clock, which set
    created_at), so any batch it made has long been listed; the listing
    reached back past created - MATCH_BEFORE, so nothing was left unread;
    and no unowned batch of that size is in it at any time after that. The
    adoption window's upper bound does not apply to that last test: an
    upload slow enough to land after MATCH_AFTER is not a match to adopt
    blindly, but it is a reason to refuse "none" and leave it to a person."""
    with conn.cursor() as cur:
        cur.execute("""select created_at, requests, now() - created_at > %s from extract_batches
                       where id = %s and status = 'pending'""", (MATCH_AFTER, pending_id))
        row = cur.fetchone()
        cur.execute("select id from extract_batches")
        ours = {r[0] for r in cur.fetchall()}
    conn.commit()
    if row is None:
        raise SystemExit(f"no pending batch {pending_id}")
    created, n, old = row
    out, later = [], []
    listed, covered = AV.recent_batches(cl, until=created - MATCH_BEFORE)
    for b in listed:
        c = b.request_counts
        total = c.processing + c.succeeded + c.errored + c.canceled + c.expired
        if b.id not in ours and total == n and created - MATCH_BEFORE <= b.created_at:
            later.append(b.id)
            if b.created_at <= created + MATCH_AFTER:
                out.append(b.id)
    return out, bool(old and covered and not later)


def resolve_pending_auto(conn, cl, pending_id, log=print):
    """Adopt the one batch that matches a pending row. When none matches and
    that answer is final (see pending_matches), the submission made nothing:
    drop the row and return its items to the queue. Returns the batch id,
    "none", or None when a person has to decide."""
    found, settled = pending_matches(conn, cl, pending_id)
    if len(found) == 1:
        resolve_pending(conn, pending_id, found[0])
        log(f"pending submission {pending_id} matched batch {found[0]}: re-attaching to it")
        return found[0]
    if not found and settled:
        resolve_pending(conn, pending_id, "none")
        log(f"pending submission {pending_id}: no batch in the API's list was created near it, and it is "
            f"over {MATCH_AFTER.seconds // 60} minutes old, so it made none; its items are due again")
        return "none"
    log(f"pending submission {pending_id}: {len(found)} matching batch(es) in the API's list"
        + (f" ({', '.join(found)})" if found else "")
        + ("" if found else " (too soon, the list did not reach back far enough, or a batch of that size "
                             "was created later: not settled as none)"))
    return None


def resolve_pending(conn, pending_id, batch_id):
    """After an interrupted submission: adopt the batch the Console shows, or
    ('none') drop the pending row and return its items to the queue."""
    with conn.cursor() as cur:
        if batch_id == "none":
            cur.execute("update extraction_state set batch_id = null where batch_id = %s", (pending_id,))
            cur.execute("delete from extract_batches where id = %s and status = 'pending'", (pending_id,))
            _chunks_requeue(cur, pending_id)
        else:
            cur.execute("""update extract_batches set id = %s, status = 'submitted', submitted_at = now()
                           where id = %s and status = 'pending'""", (batch_id, pending_id))
            if cur.rowcount != 1:
                raise SystemExit(f"no pending batch {pending_id}")
            cur.execute("update extraction_state set batch_id = %s where batch_id = %s", (batch_id, pending_id))
            cur.execute("select to_regclass('extract_chunks') is not null")
            if cur.fetchone()[0]:
                cur.execute("update extract_chunks set batch_id = %s where batch_id = %s", (batch_id, pending_id))
    conn.commit()


# ---------------------------------------------------------------- thread mode
# One request per chunk of a thread (the post and up to about 25 comments)
# instead of one per comment: the system prompt, the post and the shared
# context are paid once a chunk, so the backlog costs a fraction of comment
# mode. What goes in a chunk is thread_chunks.py's (shared with the offline
# eval); this section is the I/O around it.
#
# The cursor is the same extraction_state: every item a chunk numbers gets
# its own row, done even with no mentions, carrying the thread prompt's hash,
# its own mentions as its output, and its share of the chunk's cost. So the
# two modes can never both extract an item, --reset-hash on the thread hash
# undoes only thread-mode rows, and live_mentions' hash check works as
# before. extract_chunks keeps each chunk's whole answer, and is the queue
# for the retries below.
#
# A chunk that fails (max_tokens, refusal, invalid JSON, or an error or
# expiry inside a batch) is split in half and both halves are queued; a half
# that fails too sends its items one at a time in comment and post mode,
# where an item is retried once more and then parked. No due item is ever
# dropped without a row that says why.
THREAD_PAGE = 50              # threads read and chunked at a time
QUEUED_P = QUEUED.replace("s.", "ps.")


class ThreadOpts:
    """Thread mode's settings: effort, chunk sizes, and whether posts are items."""

    def __init__(self, effort=prompt_v6.THREAD_EFFORT, soft_comments=T.SOFT_COMMENTS, soft_tokens=T.SOFT_TOKENS,
                 max_comments=T.MAX_COMMENTS, posts=True):
        if effort not in prompt_v6.THREAD_EFFORTS:
            raise ValueError(f"effort must be one of {prompt_v6.THREAD_EFFORTS}")
        self.effort, self.posts = effort, posts
        self.soft_comments, self.soft_tokens, self.max_comments = soft_comments, soft_tokens, max_comments


class ChunkJob:
    """One thread-mode request: a chunk, rendered, with the bracket map its answer is read against."""
    __slots__ = ("id", "chunk", "user", "ids", "context", "effort", "generation", "split_from", "system",
                 "prompt_hash")

    def __init__(self, cid, chunk, user, ids, context, effort, generation=0, split_from=None):
        self.id, self.chunk, self.user, self.ids, self.context = cid, chunk, user, ids, context
        self.effort, self.generation, self.split_from = effort, generation, split_from
        self.system = prompt_v6.SYSTEM_PROMPT_THREAD
        self.prompt_hash = prompt_v6.PROMPT_HASH_THREAD

    @classmethod
    def from_row(cls, row):
        """A chunk as extract_chunks recorded it, for reading its answer: members
        are in bracket order, from [0] when the post was an item, else from [1]."""
        cid, tid, post_item, members, generation, split_from, effort, ph = row
        start = 0 if post_item else 1
        ids = {n: m for n, m in enumerate(members, start)}
        job = cls(cid, T.Chunk(tid, post_item, [m for m in members if m != tid]), None, ids, [], effort,
                  generation, split_from)
        job.prompt_hash = ph
        return job

    @property
    def members(self):
        return [self.ids[n] for n in sorted(self.ids)]

    def items(self):
        return [Item("post" if i == self.chunk.thread_id else "comment", i, None, None, self.prompt_hash)
                for i in self.members]

    def worst(self, batch):
        return AV.worst_case(self.system, self.user, batch, prompt_v6.THREAD_MAX_TOKENS)

    def params(self):
        return AV.params(self.system, self.user, effort=self.effort, max_tokens=prompt_v6.THREAD_MAX_TOKENS,
                         schema=AV.OUTPUT_SCHEMA_THREAD)


def new_chunk_id():
    # A batch custom_id must match ^[a-zA-Z0-9_-]{1,64}$.
    return "ch-" + uuid.uuid4().hex


def thread_candidates(conn, limit=None, since=None, ids=None, newest_first=False, posts=True):
    """r/FoodNYC threads with anything due, in processing order.

    Due means a comment due under v6 (the same QUEUED rule as comment mode),
    or, when posts are items, the post itself. Threads that owe a retry
    (a queued half, or items sent on alone) come first, then by the post's
    created_utc, oldest first unless newest_first, so a capped run can spend
    on recent months first. `since` is on the post's created_utc."""
    p = {"home": subreddits.HOME, "v": VERSION, "since": since, "ids": list(ids) if ids else None,
         "limit": limit, "posts": posts}
    order = "desc" if newest_first else "asc"
    sql = f"""
        select t.id from threads t
        left join extraction_state ps on ps.item_id = t.id and ps.version = %(v)s
        where t.subreddit = %(home)s
          and (%(since)s::timestamptz is null or t.created_utc >= %(since)s::timestamptz)
          and (%(ids)s::text[] is null or t.id = any(%(ids)s::text[]))
          and ((%(posts)s and {QUEUED_P})
               or exists (select 1 from comments c
                          left join extraction_state s on s.item_id = c.id and s.version = %(v)s
                          where c.thread_id = t.id and c.subreddit = %(home)s
                            and btrim(c.body) not in ('', '[deleted]', '[removed]') and {QUEUED}))
        order by exists (select 1 from extract_chunks k where k.thread_id = t.id and k.version = %(v)s
                           and (k.status = 'queued' or k.fallback)) desc,
                 t.created_utc {order}, t.id
        limit %(limit)s"""
    with conn.cursor() as cur:
        cur.execute(sql, p)
        out = [r[0] for r in cur.fetchall()]
    conn.commit()
    return out


def _due_in(conn, tids):
    """({thread_id: due comment ids}, due post ids) for these threads."""
    with conn.cursor() as cur:
        cur.execute(f"""select c.thread_id, c.id from comments c
                        left join extraction_state s on s.item_id = c.id and s.version = %(v)s
                        where c.thread_id = any(%(t)s) and c.subreddit = %(home)s
                          and btrim(c.body) not in ('', '[deleted]', '[removed]') and {QUEUED}""",
                    {"v": VERSION, "t": list(tids), "home": subreddits.HOME})
        comments = {}
        for tid, cid in cur.fetchall():
            comments.setdefault(tid, set()).add(cid)
        cur.execute(f"""select t.id from threads t
                        left join extraction_state ps on ps.item_id = t.id and ps.version = %(v)s
                        where t.id = any(%(t)s) and t.subreddit = %(home)s and {QUEUED_P}""",
                    {"v": VERSION, "t": list(tids), "home": subreddits.HOME})
        posts = {r[0] for r in cur.fetchall()}
        cur.execute("""select id, thread_id, post_item, members, generation, split_from, status, fallback
                       from extract_chunks where version = %s and thread_id = any(%s)
                         and (status = 'queued' or (status = 'failed' and fallback))
                       order by created_at, id""", (VERSION, list(tids)))
        open_rows = cur.fetchall()
    conn.commit()
    return comments, posts, open_rows


def _job(chunk, th, tree, effort, cid=None, generation=0, split_from=None):
    user, ids, ctx = T.render(chunk, th["title"], th["selftext"], th["comments"], tree)
    return ChunkJob(cid or new_chunk_id(), chunk, user, ids, ctx, effort, generation, split_from)


def build_thread_jobs(conn, tids, opts, exclude=(), write=True, log=print):
    """(chunk jobs, [(kind, id)] to send alone) for these threads, in order.

    Retries come first: items of a chunk that failed twice go out alone (in
    comment or post mode); a queued half is sent as recorded, minus any item
    no longer due. Everything else due is chunked afresh. `exclude` holds
    items already queued in this run's memory, which must not be chunked a
    second time. A queued half with nothing left to send is marked dropped
    (unless write is False, as in a dry run)."""
    rows = prompt_v6.fetch_thread_rows(conn, tids)
    due_c, due_p, open_rows = _due_in(conn, tids)
    conn.commit()
    exclude = set(exclude)
    jobs, alone, dropped = [], [], []
    by_thread = {}
    for r in open_rows:
        by_thread.setdefault(r[1], []).append(r)
    for tid in tids:
        th = rows.get(tid)
        if th is None:
            continue
        dc = due_c.get(tid, set()) - exclude
        dp = opts.posts and tid in due_p and tid not in exclude
        claimed = set()
        open_ = by_thread.get(tid, [])
        for cid, _, post_item, members, _, _, status, fallback in open_:
            if status == "failed" and fallback:
                for i in members:
                    if i not in claimed and (i in dc or (i == tid and dp)):
                        alone.append(("post" if i == tid else "comment", i))
                        claimed.add(i)
        tree = T.Tree(th["comments"])
        for cid, _, post_item, members, generation, split_from, status, _ in open_:
            if status != "queued":
                continue
            mem = [i for i in members if i != tid and i in dc and i not in claimed]
            post = bool(post_item) and dp and tid not in claimed
            if not mem and not post:
                dropped.append(cid)
                continue
            claimed |= set(mem) | ({tid} if post else set())
            jobs.append(_job(T.Chunk(tid, post, mem), th, tree, opts.effort, cid, generation, split_from))
        rest = dc - claimed
        post = dp and tid not in claimed
        if rest or post:
            ptoks = T.text_tokens(f"{th['title'] or ''} {th['selftext'] or ''}", R_POST_CHARS) if post else 0.0
            for ch in T.chunk_thread(tid, th["comments"], rest, post, ptoks, opts.soft_comments,
                                     opts.soft_tokens, opts.max_comments):
                jobs.append(_job(ch, th, tree, opts.effort))
    if dropped and write:
        with conn.cursor() as cur:
            cur.execute("""update extract_chunks set status = 'dropped', updated_at = now(), finished_at = now()
                           where id = any(%s) and status = 'queued'""", (dropped,))
        conn.commit()
        log(f"  {len(dropped)} queued chunk(s) had nothing left due (extracted since), dropped")
    return jobs, alone


R_POST_CHARS = prompt_v6.thread.POST_ITEM_CHARS


def _chunk_record(job, status, batch_id=None, output=None, usage=None, cost=None, error=None, bad=None,
                  fallback=False):
    """One extract_chunks row's values, in _CHUNK_COLUMNS order."""
    return (job.id, VERSION, job.chunk.thread_id, job.prompt_hash, job.effort, job.chunk.post_item, job.members,
            job.context, job.generation, job.split_from, status, fallback, batch_id, error, bad,
            Json(output) if output is not None else None, Json(usage) if usage is not None else None, cost)


_CHUNK_COLUMNS = ("id", "version", "thread_id", "prompt_hash", "effort", "post_item", "members", "context_ids",
                  "generation", "split_from", "status", "fallback", "batch_id", "error", "bad_ids", "output",
                  "usage", "cost_usd")
# Every column is taken from the values, except the record of what was sent
# (members, context), which a batch's own row already holds when its answer
# is collected without the rendering.
_CHUNK_UPSERT = f"""
    insert into extract_chunks ({', '.join(_CHUNK_COLUMNS)}) values %s
    on conflict (id) do update set
      prompt_hash = excluded.prompt_hash, effort = excluded.effort, post_item = excluded.post_item,
      members = excluded.members,
      context_ids = case when cardinality(excluded.context_ids) > 0 or excluded.status in ('queued', 'batched')
                         then excluded.context_ids else extract_chunks.context_ids end,
      status = excluded.status, fallback = excluded.fallback, batch_id = excluded.batch_id,
      error = excluded.error, bad_ids = excluded.bad_ids, output = excluded.output, usage = excluded.usage,
      cost_usd = excluded.cost_usd, updated_at = now(),
      finished_at = case when excluded.status in ('done', 'failed') then now() end"""


def _upsert_chunks(cur, records):
    if records:
        execute_values(cur, _CHUNK_UPSERT, records, page_size=len(records))


def _read_chunk(job, message, cost, stats, log):
    """A chunk's answer as ("done", entries, record) or ("failed", code, usage).

    Each mention's id must be an integer that numbers an item in this chunk.
    An id out of range, pointing at the post when the post was context, at a
    quoted line (those have no number), or not an integer at all, is dropped
    and logged, never guessed. Every numbered item gets a Done entry, with no
    mentions if it got none, and an equal share of the cost."""
    usage = AV.usage_of(message)
    stats.add_usage(usage, cost)
    try:
        out = AV.parse(message, prompt_v6.THREAD_MAX_TOKENS)
    except AV.ItemError as e:
        return "failed", str(e), usage
    per = {i: [] for i in job.members}
    bad = []
    for m in out["mentions"]:
        n = m.get("id")
        if type(n) is int and n in job.ids:
            per[job.ids[n]].append(m)
        else:
            bad.append(n)
    if bad:
        stats.bad_ids += len(bad)
        log(f"  chunk {job.id} ({job.chunk.thread_id}): {len(bad)} mention(s) dropped, id(s) "
            f"{sorted({repr(b) for b in bad})[:5]} name no item of this chunk")
    share = cost / len(job.members)
    entries = [Done(it, {"mentions": per[it.id], "chunk_id": job.id}, {"chunk_id": job.id, "items": len(per)},
                    share) for it in job.items()]
    return "done", entries, (out, usage, len(bad))


def _store_chunk_answers(conn, answers, stats, log, batch_id=None):
    """Write answered chunks: their extract_chunks rows and every item's
    mentions and state row, in one transaction per WRITE_CHUNK items or so."""
    group, n = [], 0
    for a in answers + [None]:
        if a is not None:
            group.append(a)
            n += len(a[1])
        if group and (a is None or n >= WRITE_CHUNK):
            recs = [_chunk_record(job, "done", batch_id, out, usage, cost, bad=bad)
                    for job, _, (out, usage, bad), cost in group]
            _write_counted(conn, [e for _, es, _, _ in group for e in es], stats, log,
                           before=lambda cur, recs=recs: _upsert_chunks(cur, recs))
            stats.chunks += len(group)
            group, n = [], 0


def _chunk_failed(conn, job, code, usage, cost, log, batch_id=None):
    """Record a chunk that got no usable answer, and queue what comes next:
    its two halves, or (a half, or a chunk of one item) its items alone.
    In a batch its items are detached from it, so they are due again and the
    queued rows claim them. Returns the thread id, which owes a retry."""
    halves = T.split_half(job.chunk) if job.generation == 0 and len(job.chunk) > 1 else []
    rec = _chunk_record(job, "failed", batch_id, None, usage, cost, error=str(code)[:500], fallback=not halves)
    with conn.cursor() as cur:
        _upsert_chunks(cur, [rec])
        for h in halves:
            half = ChunkJob(new_chunk_id(), h, None, {n: i for n, i in enumerate(h.items, 0 if h.post_item else 1)},
                            [], job.effort, generation=job.generation + 1, split_from=job.id)
            _upsert_chunks(cur, [_chunk_record(half, "queued")])
        if batch_id:
            cur.execute("""update extraction_state set batch_id = null, updated_at = now()
                           where version = %s and batch_id = %s and item_id = any(%s)""",
                        (VERSION, batch_id, job.members))
    conn.commit()
    log(f"  chunk {job.id} ({job.chunk.thread_id}, {len(job.chunk)} items) failed ({str(code)[:80]}): "
        + (f"split into {len(halves)} halves" if halves else "its items go out one at a time"))
    return job.chunk.thread_id


def run_direct_threads(conn, cl, budget, opts, limit=None, since=None, ids=None, newest_first=False,
                       workers=WORKERS, log=print, stats=None):
    """Thread mode with direct calls, a page of threads at a time. Returns Stats.

    Each page's chunks go out `workers` at a time; then the halves of any that
    failed, then their items alone if a half failed too, before the next page.
    Holds, Ctrl-C and stopping on a fatal or lasting transient error work as
    in comment mode (_direct_page)."""
    stats = stats or Stats()
    stop, capped = threading.Event(), threading.Event()
    tids = thread_candidates(conn, limit, since, ids, newest_first, opts.posts)
    log(f"{len(tids):,} thread(s) with items due, cap ${budget.max:.2f}")
    for start in range(0, len(tids), THREAD_PAGE):
        todo = tids[start:start + THREAD_PAGE]
        after = len(tids) - start - len(todo)
        for _ in range(4):               # fresh chunks, halves, items alone, and a margin
            jobs, alone = build_thread_jobs(conn, todo, opts, log=log)
            if alone:
                items = []
                for kind in KINDS:
                    ids_k = [i for k, i in alone if k == kind]
                    items += render_items(conn, kind, ids_k) if ids_k else []
                _direct_page(conn, cl, budget, items, workers, stats, stop, capped, log)
            if not stop.is_set() and jobs:
                todo = sorted(_direct_chunks(conn, cl, budget, jobs, workers, stats, stop, capped, log))
            else:
                todo = []
            if stop.is_set():
                stats.threads_left += after
                return stats
            if not todo:
                break
    return stats


def _direct_chunks(conn, cl, budget, jobs, workers, stats, stop, capped, log):
    """Send chunk jobs concurrently under the cap; store each answer on this
    thread. Returns the thread ids that owe a retry."""
    def work(job):
        if stop.is_set():
            return job, "skipped", 0.0
        w = job.worst(batch=False)
        if not budget.reserve(w):
            capped.set()
            stop.set()
            return job, "skipped", 0.0
        held = [True]

        def again():
            budget.settle(w, w)
            held[0] = budget.reserve(w)
            return held[0]
        try:
            msg = AV.call(cl, job.params(), log=log, retry_ok=again)
        except AV.CapReached:
            capped.set()
            stop.set()
            return job, "skipped", 0.0
        except (AV.FatalAPIError, AV.TransientAPIError) as e:
            if held[0]:
                budget.settle(w, w if getattr(e, "maybe_billed", False) else 0.0)
            stop.set()
            return job, e, 0.0
        c = AV.cost(AV.usage_of(msg), batch=False)
        budget.settle(w, c)
        return job, msg, c

    halt, retry = None, set()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        for fut in concurrent.futures.as_completed([pool.submit(work, j) for j in jobs]):
            job, res, c = fut.result()
            if isinstance(res, str):
                stats.refused += len(job.chunk) if capped.is_set() else 0
            elif isinstance(res, Exception):
                halt = halt or res
            else:
                got = _read_chunk(job, res, c, stats, log)
                if got[0] == "done":
                    _store_chunk_answers(conn, [(job, got[1], got[2], c)], stats, log)
                else:
                    stats.chunk_failures += 1
                    retry.add(_chunk_failed(conn, job, got[1], got[2], c, log))
    except BaseException:
        stop.set()
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    if halt is not None:
        raise halt
    return retry


def _submit_chunks(conn, cl, budget, jobs, log):
    """The thread-mode _submit: the ledger row, every chunk's row and every
    member's state row are written first (in one transaction), so a re-run
    re-attaches and nothing is sent twice; then the batch, one request per
    chunk with the chunk id as custom_id."""
    held = sum(j.worst(batch=True) for j in jobs)
    pid = f"pending-{int(time.time() * 1000)}-{os.getpid()}"
    items = [(it.id, it.kind) for j in jobs for it in j.items()]
    with conn.cursor() as cur:
        cur.execute("insert into extract_batches (id, version, requests, hold_usd) values (%s, %s, %s, %s)",
                    (pid, VERSION, len(jobs), held))
        _upsert_chunks(cur, [_chunk_record(j, "batched", pid) for j in jobs])
        cur.execute("""
            insert into extraction_state (item_id, version, kind, prompt_hash, model, batch_id)
            select u.item_id, %(v)s, u.kind, %(ph)s, %(model)s, %(pid)s
            from unnest(%(ids)s::text[], %(kinds)s::text[]) as u(item_id, kind)
            on conflict (item_id, version) do update set
              prompt_hash = excluded.prompt_hash, model = excluded.model, batch_id = excluded.batch_id,
              updated_at = now()""",
                    {"v": VERSION, "ph": prompt_v6.PROMPT_HASH_THREAD, "model": prompt_v6.MODEL, "pid": pid,
                     "ids": [i for i, _ in items], "kinds": [k for _, k in items]})
    conn.commit()
    budget.hold(pid, held, force=True)
    try:
        bid = AV.submit(cl, [(j.id, j.params()) for j in jobs])
    except (AV.TransientAPIError, AV.FatalAPIError):
        with conn.cursor() as cur:
            cur.execute("delete from extract_batches where id = %s", (pid,))
            cur.execute("update extraction_state set batch_id = null where batch_id = %s", (pid,))
            _chunks_requeue(cur, pid)
        conn.commit()
        budget.release(pid, 0.0)
        raise
    except AV.AmbiguousSubmit:
        log(f"  submission of {pid} has an unknown outcome; kept as pending, run stops")
        raise
    with conn.cursor() as cur:
        cur.execute("""update extract_batches set id = %s, status = 'submitted', submitted_at = now()
                       where id = %s""", (bid, pid))
        cur.execute("update extraction_state set batch_id = %s where batch_id = %s", (bid, pid))
        cur.execute("update extract_chunks set batch_id = %s where batch_id = %s", (bid, pid))
    conn.commit()
    budget.rename(pid, bid)
    log(f"submitted batch {bid}: {len(jobs)} chunk(s), {len(items)} item(s), worst case ${held:.4f} held")
    return bid


def _batch_chunks(conn, bid):
    """The chunk rows a batch carries, or [] when it is a comment- or post-mode batch."""
    with conn.cursor() as cur:
        cur.execute("select to_regclass('extract_chunks') is not null")
        if not cur.fetchone()[0]:
            conn.commit()
            return []
        cur.execute("""select id, thread_id, post_item, members, generation, split_from, effort, prompt_hash
                       from extract_chunks where batch_id = %s and status = 'batched' order by id""", (bid,))
        rows = cur.fetchall()
    conn.commit()
    return rows


def _collect_any(conn, cl, budget, bid, stats, log, sleep=None):
    """Collect a batch of either shape. Returns ("items", [(kind, id)] owed a
    retry) for a comment- or post-mode batch, ("chunks", [thread ids] owing a
    retry) for a thread-mode one."""
    rows = _batch_chunks(conn, bid)
    if not rows:
        return "items", _collect(conn, cl, budget, bid, stats, log, sleep=sleep)
    return "chunks", _collect_chunks(conn, cl, budget, bid, rows, stats, log, sleep=sleep)


def _collect_chunks(conn, cl, budget, bid, rows, stats, log, sleep=None):
    """Store a finished thread-mode batch and settle its hold. Answers are read
    against the bracket order extract_chunks recorded at submit. An
    invalid_request_error is fatal as in comment mode: that chunk is queued
    again unchanged, its items left due, and the run stops once the rest is
    stored."""
    res = AV.results(cl, bid, sleep=sleep, log=log)
    costs = {cid: AV.cost(AV.usage_of(r[1]), batch=True) for cid, r in res.items() if r[0] == "succeeded"}
    total = sum(costs.values())
    stray = set(costs) - {r[0] for r in rows}
    if stray:
        log(f"  batch {bid}: {len(stray)} answer(s) for chunks no longer attached to it, counted, not stored")
    answers, failures, invalid = [], [], []
    for row in rows:
        job = ChunkJob.from_row(row)
        r = res.get(job.id, ("missing",))
        if r[0] == "succeeded":
            got = _read_chunk(job, r[1], costs[job.id], stats, log)
            if got[0] == "done":
                answers.append((job, got[1], got[2], costs[job.id]))
            else:
                failures.append((job, got[1], got[2], costs[job.id]))
        elif r[0] == "errored" and r[1] == "invalid_request_error":
            invalid.append((job, f"{job.id}: {r[2]}"))
        else:
            failures.append((job, f"batch_{r[0]}" + (f": {r[1]}: {r[2]}" if r[0] == "errored" else ""), None, 0.0))
    _store_chunk_answers(conn, answers, stats, log, batch_id=bid)
    retry = set()
    for job, code, usage, cost in failures:
        stats.chunk_failures += 1
        retry.add(_chunk_failed(conn, job, code, usage, cost, log, batch_id=bid))
    with conn.cursor() as cur:
        for job, _ in invalid:
            cur.execute("update extract_chunks set status = 'queued', batch_id = null, updated_at = now() "
                        "where id = %s", (job.id,))
            cur.execute("update extraction_state set batch_id = null where version = %s and batch_id = %s "
                        "and item_id = any(%s)", (VERSION, bid, job.members))
        cur.execute("""update extract_batches set status = 'collected', cost_usd = %s, collected_at = now()
                       where id = %s""", (total, bid))
    conn.commit()
    budget.release(bid, total)
    log(f"  batch {bid} collected: ${total:.4f}, {len(answers)} chunk(s) stored, {len(failures)} to retry smaller"
        + (f", {len(invalid)} invalid" if invalid else ""))
    if invalid:
        log("  invalid_request_error in batch " + bid + ":\n    " + "\n    ".join(m for _, m in invalid[:10]))
        raise AV.FatalAPIError(f"batch {bid}: {len(invalid)} request(s) rejected as invalid; first: {invalid[0][1]}")
    return sorted(retry)


def run_batch_threads(conn, cl, budget, opts, limit=None, since=None, ids=None, newest_first=False,
                      batch_size=BATCH_SIZE, max_inflight=MAX_INFLIGHT, poll_seconds=POLL_SECONDS,
                      log=print, sleep=time.sleep, stats=None):
    """Thread mode through Message Batches, as run_batch does it for items:
    pending submissions matched first, batches in flight re-attached (of
    either shape), then sub-batches of up to batch_size chunks that fit what
    remains under the cap, max_inflight at once. Items owed a retry alone go
    out first, in their own comment- or post-mode batches; threads with a
    chunk that failed are chunked again (their halves) before new threads."""
    stats = stats or Stats()
    for pid in _pending(conn):
        bid = resolve_pending_auto(conn, cl, pid, log)
        if bid is None:
            raise SystemExit(f"submission {pid} has an unknown outcome and no single batch in the API's "
                             "list matches it: check the Console, then run --resolve-pending "
                             f"{pid} <batch id | none>")
    inflight = []
    for bid, hold in _inflight(conn):
        budget.hold(bid, hold, force=True)
        inflight.append(bid)
        log(f"re-attaching to batch {bid} (${hold:.4f} held)")
    tids = thread_candidates(conn, limit, since, ids, newest_first, opts.posts)
    log(f"{len(tids):,} thread(s) with items due, {len(inflight)} batch(es) in flight, cap ${budget.max:.2f}")
    pos, retry_tids, jobs_q, items_q = 0, [], [], []
    capped = False

    def held_items():
        return {i for j in jobs_q for i in j.chunk.items} | {i for _, i in items_q}

    while True:
        while not capped and len(inflight) < max_inflight:
            if retry_tids:
                j, a = build_thread_jobs(conn, retry_tids, opts, exclude=held_items(), log=log)
                retry_tids = []
                jobs_q, items_q = j + jobs_q, a + items_q
            while not items_q and len(jobs_q) < batch_size and pos < len(tids):
                page = tids[pos:pos + THREAD_PAGE]
                pos += len(page)
                j, a = build_thread_jobs(conn, page, opts, exclude=held_items(), log=log)
                jobs_q, items_q = jobs_q + j, items_q + a
            room = budget.remaining()
            if items_q:
                head = items_q[:batch_size]
                items = []
                for kind in KINDS:
                    ids_k = [i for k, i in head if k == kind]
                    items += render_items(conn, kind, ids_k) if ids_k else []
                batch, held = [], 0.0
                for it in items:
                    w = it.worst(batch=True)
                    if held + w > room:
                        break
                    batch.append(it)
                    held += w
                if not batch:
                    if not items:
                        items_q = items_q[len(head):]
                        continue
                    capped = True
                    break
                taken = {it.id for it in batch}
                items_q = [(it.kind, it.id) for it in items if it.id not in taken] + items_q[len(head):]
                inflight.append(_submit(conn, cl, budget, batch, log))
                continue
            if not jobs_q:
                break
            batch, held = [], 0.0
            for j in jobs_q[:batch_size]:
                w = j.worst(batch=True)
                if held + w > room:
                    break
                batch.append(j)
                held += w
            if not batch:
                capped = True
                break
            jobs_q = jobs_q[len(batch):]
            inflight.append(_submit_chunks(conn, cl, budget, batch, log))
        if not inflight:
            break
        ended, b, lost = None, None, None
        for bid in inflight:
            try:
                b = AV.retrieve(cl, bid, sleep=sleep, log=log)
            except AV.NotFound as e:
                lost = bid
                _lost(conn, budget, bid, e, log)
                break
            if b.processing_status == "ended":
                ended = bid
                break
        if lost is not None:
            inflight.remove(lost)
            capped = False
            continue
        if ended is None:
            c = getattr(b, "request_counts", None)
            if c is not None:
                log(f"  batch {bid}: {b.processing_status}, {c.processing} processing, "
                    f"{c.succeeded} succeeded, {c.errored} errored")
            sleep(poll_seconds)
            continue
        inflight.remove(ended)
        try:
            shape, retry = _collect_any(conn, cl, budget, ended, stats, log, sleep=sleep)
        except AV.NotFound as e:
            _lost(conn, budget, ended, e, log)
            capped = False
            continue
        if shape == "items":
            items_q = retry + items_q
        else:
            retry_tids += [t for t in retry if t not in retry_tids]
        capped = False
    stats.refused += sum(len(j.chunk) for j in jobs_q) + len(items_q)
    stats.threads_left += len(tids) - pos
    return stats


def dry_run_threads(conn, opts, limit=None, since=None, ids=None, newest_first=False, show=2, log=print):
    """Chunk, render and price what a thread-mode run would send. Reads only.

    Prices are batch prices for every chunk at both efforts: typical (the
    measured output for the chunk's size, anthropic_v6.thread_output_tokens, with the
    system prompt all cached and all fresh) and the worst case the cap
    holds (all input as cache writes, all 32k out)."""
    conn.rollback()
    conn.set_session(readonly=True)
    try:
        return _dry_run_threads(conn, opts, limit, since, ids, newest_first, show, log)
    finally:
        conn.rollback()
        conn.set_session(readonly=False)


def _dry_run_threads(conn, opts, limit, since, ids, newest_first, show, log):
    tids = thread_candidates(conn, limit, since, ids, newest_first, opts.posts)
    chunks, alone, shown = [], 0, 0
    t = {"user_chars": 0, "context_chars": 0, "context_lines": 0, "worst": 0.0,
         "medium": [0.0, 0.0], "low": [0.0, 0.0]}
    for start in range(0, len(tids), THREAD_PAGE):
        jobs, a = build_thread_jobs(conn, tids[start:start + THREAD_PAGE], opts, write=False, log=log)
        alone += len(a)
        for j in jobs:
            chunks.append(j.chunk)
            t["user_chars"] += len(j.user)
            head = j.user.split(prompt_v6.thread.CONTEXT_HEADER, 1)
            if len(head) == 2:
                block = head[1].split("\n\n", 1)[0]
                t["context_chars"] += len(block)
                t["context_lines"] += block.count("\n")
            t["worst"] += j.worst(batch=True)
            for effort in ("medium", "low"):
                out = AV.thread_output_tokens(effort, len(j.chunk))
                t[effort][0] += AV.estimate(j.system, j.user, batch=True, cached=True, output_tokens=out)
                t[effort][1] += AV.estimate(j.system, j.user, batch=True, cached=False, output_tokens=out)
            if shown < show:
                shown += 1
                log(f"--- {j.chunk.thread_id} chunk of {len(j.chunk)} item(s) (prompt {j.prompt_hash})\n{j.user}\n")
    s = T.stats(chunks)
    if not s["chunks"] and not alone:
        log("nothing due")
        return {"threads": len(tids), **s}
    n = s["items"]
    log(f"threads: {len(tids):,}, chunks: {s['chunks']:,}, items: {n:,} ({s.get('posts', 0):,} posts as item [0])"
        + (f", plus {alone:,} item(s) owed a retry alone" if alone else ""))
    if s["chunks"]:
        log(f"items per chunk: min {s['min']}, p50 {s['p50']}, p90 {s['p90']}, max {s['max']} "
            f"(soft {opts.soft_comments} items / {opts.soft_tokens} tokens, hard max {opts.max_comments})")
        log(f"quoted context: {t['context_lines']:,} line(s), {t['context_chars']:,} of {t['user_chars']:,} "
            f"user-message characters ({t['context_chars'] / max(t['user_chars'], 1):.1%})")
        for effort in ("medium", "low"):
            c, f = t[effort]
            log(f"batch, effort {effort}: typical ${c:.2f} (cached) to ${f:.2f} (uncached), "
                f"${c / n * 1000:.3f}-${f / n * 1000:.3f} per 1,000 items")
        log(f"worst case the cap holds (any effort): ${t['worst']:.2f}; direct calls cost twice the batch price")
    return {"threads": len(tids), "alone": alone, **s, **{k: v for k, v in t.items()}}


# ---------------------------------------------------------------- dry run
def dry_run(conn, kinds=KINDS, limit=None, since=None, ids=None, max_chars=None, show=2, log=print):
    """Render and price what a run would send. Reads only; no API call.

    Three prices per kind: the worst case the cap reserves, and a typical
    cost at the benchmark's measured rate with the system prompt all cached
    and all fresh (a batch caches on a best-effort basis, so the truth is in
    between). Batch prices are half the direct ones.
    """
    conn.rollback()
    conn.set_session(readonly=True)
    try:
        return _dry_run(conn, kinds, limit, since, ids, max_chars, show, log)
    finally:
        conn.rollback()
        conn.set_session(readonly=False)


def _dry_run(conn, kinds, limit, since, ids, max_chars, show, log):
    totals = {}
    left = limit
    for kind in kinds:
        if left is not None and left <= 0:
            break
        todo = candidate_ids(conn, kind, left, since, ids, max_chars if kind == "comment" else None)
        if left is not None:
            left -= len(todo)
        t = totals.setdefault(kind, {"n": 0, "chars": 0, "worst": 0.0, "cached": 0.0, "fresh": 0.0})
        shown = 0
        for start in range(0, len(todo), 2000):
            for it in render_items(conn, kind, todo[start:start + 2000]):
                t["n"] += 1
                t["chars"] += len(it.user)
                t["worst"] += it.worst(batch=True)
                t["cached"] += AV.estimate(it.system, it.user, batch=True, cached=True)
                t["fresh"] += AV.estimate(it.system, it.user, batch=True, cached=False)
                if shown < show:
                    shown += 1
                    log(f"--- {it.id} ({kind}, prompt {it.prompt_hash})\n{it.user}\n")
    n = sum(t["n"] for t in totals.values())
    for kind, t in totals.items():
        if t["n"]:
            log(f"{kind}s: {t['n']:,}, user message avg {t['chars'] / t['n']:,.0f} chars | batch: typical "
                f"${t['cached']:.2f} (cached) to ${t['fresh']:.2f} (uncached), worst case ${t['worst']:.2f}; "
                f"direct: twice that")
    if n:
        cached = sum(t["cached"] for t in totals.values())
        fresh = sum(t["fresh"] for t in totals.values())
        log(f"total {n:,} items: batch ${cached:.2f}-${fresh:.2f} "
            f"(${cached / n * 1000:.2f}-${fresh / n * 1000:.2f} per 1,000); "
            f"a --max-usd below the worst case still runs, in smaller sub-batches")
    else:
        log("nothing due")
    return totals


# ---------------------------------------------------------------- status, switch
def status(conn, log=print):
    with conn.cursor() as cur:
        cur.execute("select read_version, updated_at from extraction_settings")
        row = cur.fetchone()
        log(f"board reads: {row[0] if row else 'legacy'}" + (f" (since {row[1]:%Y-%m-%d %H:%M})" if row else ""))
        cur.execute("""select kind,
                              count(*) filter (where extracted_at is not null),
                              count(*) filter (where extract_error is not null),
                              count(*) filter (where batch_id is not null and extracted_at is null),
                              count(*) filter (where extracted_at is null and extract_error is null
                                               and batch_id is null),
                              coalesce(sum(cost_usd), 0)
                       from extraction_state where version = %s group by kind order by kind""", (VERSION,))
        for kind, done, err, inb, queued, cost in cur.fetchall():
            log(f"{kind}s: {done:,} done, {err:,} parked, {inb:,} in a batch, {queued:,} owed a retry, "
                f"${float(cost):.2f} spent")
        cur.execute("""select split_part(extract_error, ':', 1), count(*) from extraction_state
                       where version = %s and extract_error is not null group by 1 order by 2 desc""",
                    (VERSION,))
        for code, n in cur.fetchall():
            log(f"  error {code}: {n:,}")
        cur.execute("""select status, count(*), coalesce(sum(hold_usd), 0), coalesce(sum(cost_usd), 0)
                       from extract_batches where version = %s group by 1 order by 1""", (VERSION,))
        for st, n, hold, cost in cur.fetchall():
            log(f"batches {st}: {n}, held ${float(hold):.2f}, cost ${float(cost):.2f}")
        cur.execute("""select count(*) from mentions where schema_version = %s""", (prompt_v6.SCHEMA_VERSION,))
        log(f"v6 mention rows: {cur.fetchone()[0]:,}")
        # Which prompt did what: comment mode, post mode and thread mode each
        # stamp their own hash, and --reset-hash works by it.
        cur.execute("""select kind, prompt_hash, count(*) filter (where extracted_at is not null),
                              count(*) filter (where extract_error is not null),
                              count(*) filter (where batch_id is not null and extracted_at is null),
                              coalesce(sum(cost_usd), 0)
                       from extraction_state where version = %s group by 1, 2 order by 1, 2""", (VERSION,))
        names = {prompt_v6.PROMPT_HASH: "comment mode", prompt_v6.PROMPT_HASH_POST: "post mode",
                 prompt_v6.PROMPT_HASH_THREAD: "thread mode"}
        for kind, ph, done, err, inb, cost in cur.fetchall():
            log(f"  {kind}s under {ph} ({names.get(ph, 'an earlier prompt')}): {done:,} done, {err:,} parked, "
                f"{inb:,} in a batch, ${float(cost):.2f}")
        cur.execute("select to_regclass('extract_chunks') is not null")
        if cur.fetchone()[0]:
            cur.execute("""select status, fallback, effort, count(*), coalesce(sum(cardinality(members)), 0),
                                  coalesce(sum(cost_usd), 0), coalesce(sum(bad_ids), 0)
                           from extract_chunks where version = %s group by 1, 2, 3 order by 1, 2, 3""", (VERSION,))
            for st, fb, effort, n, items, cost, bad in cur.fetchall():
                what = {"queued": "queued (a retry owed)", "batched": "in a batch", "done": "answered",
                        "failed": "failed, items sent alone" if fb else "failed, split in half",
                        "dropped": "dropped (nothing left due)"}[st]
                log(f"thread chunks {what}, effort {effort}: {n:,} chunk(s), {items:,} item(s), "
                    f"${float(cost):.2f}" + (f", {bad:,} mention(s) dropped for a bad id" if bad else ""))
        else:
            log("thread chunks: extract_chunks is not there yet (thread mode needs extract_v6_schema.sql again)")
    conn.rollback()


def set_read_version(conn, version, refresh_views=True, log=print):
    """The board's switch: which extraction live_mentions (and so scoring and
    the API) reads. Refreshes the scoring views straight after, so the
    materialized board and the API's direct reads agree again.

    Not one transaction, on purpose: momentum_windows cannot refresh
    concurrently, and inside one transaction its exclusive lock would block
    every board read until the last view was done. So there is a window, as
    long as the refresh (minutes), in which the API's direct reads (a place's
    mention list, dishes, the feed's places) already show the new extraction
    while the leaderboard still ranks the old one. Flip at a quiet hour."""
    with conn.cursor() as cur:
        cur.execute("update extraction_settings set read_version = %s, updated_at = now()", (version,))
        if cur.rowcount == 0:
            cur.execute("insert into extraction_settings (read_version) values (%s)", (version,))
    conn.commit()
    log(f"board now reads {version} mentions")
    if refresh_views:
        import refresh
        refresh.refresh_views(conn)


# --read v6 refuses while more than this share of v6 items is parked: a board
# missing that many comments' mentions is a worse board, and parked items
# mostly need a look (and --retry-errors), not a flip.
FLIP_MAX_PARKED_SHARE = 0.002


# The old poller keeps extracting (and setting extracted_at) until it is
# switched to v6, right after the flip, so the newest of its comments can be
# a pass or two ahead of the last v6 sweep. The check forgives those, and
# only those.
FLIP_GRACE = dt.timedelta(hours=2)


def flip_check(conn, grace=FLIP_GRACE):
    """What --read v6 checks before it flips: {"missing", "recent", "parked",
    "done", "max_parked"} and a list of reasons to refuse (empty when it may go).

    missing is every r/FoodNYC comment the old extractor read (extracted_at
    set) more than `grace` ago that v6 has not finished: no state row, owed a
    retry, or in a batch. Those comments' mentions would disappear from the
    board at the flip. recent is the same for the last `grace`, which the old
    poller is still adding to; it is reported, not refused. Comments now
    [deleted]/[removed]/blank are not counted (v6 never takes them), and
    parked ones are counted apart, against the threshold."""
    with conn.cursor() as cur:
        cur.execute("""select count(*) filter (where c.extracted_at < now() - %s),
                              count(*) filter (where c.extracted_at >= now() - %s)
                       from comments c
                       left join extraction_state s on s.item_id = c.id and s.version = %s
                       where c.subreddit = %s and c.extracted_at is not null
                         and btrim(c.body) not in ('', '[deleted]', '[removed]')
                         and (s.item_id is null or (s.extracted_at is null and s.extract_error is null))""",
                    (grace, grace, VERSION, subreddits.HOME))
        missing, recent = cur.fetchone()
        cur.execute("""select count(*) filter (where extract_error is not null),
                              count(*) filter (where extracted_at is not null)
                       from extraction_state where version = %s""", (VERSION,))
        parked, done = cur.fetchone()
    conn.commit()
    max_parked = int(FLIP_MAX_PARKED_SHARE * (done + parked))
    out = {"missing": missing, "recent": recent, "parked": parked, "done": done, "max_parked": max_parked}
    reasons = []
    if missing:
        hours = grace.total_seconds() / 3600
        reasons.append(f"{missing:,} r/FoodNYC comment(s) the old extractor read over {hours:g}h ago have no "
                       "finished v6 extraction (run the catch-up: extract_v6.py --batch --max-usd N with no "
                       "--since, then extract_v6.py --max-usd 1)")
    if parked > max_parked:
        reasons.append(f"{parked:,} v6 item(s) are parked, over the {max_parked:,} allowed "
                       f"({FLIP_MAX_PARKED_SHARE:.1%} of {done + parked:,}); see --status, then --retry-errors")
    return out, reasons


def reset_hash(conn, prompt_hash, kinds=KINDS, yes=False, chunk=5000, log=print):
    """Undo every v6 extraction made with this prompt hash, so the items are
    due again (and go out under the current prompt): their mention rows and
    their extraction_state rows are deleted, `chunk` items per transaction,
    an item's mentions and its state row in the same one, so an interruption
    never leaves an item marked done with its mentions gone. Old (legacy)
    rows are never touched: only schema_version 6 rows are.

    Refuses while any item of that hash is in a batch (pending, submitted or
    lost): its answers would come back to nothing, or the batch would be paid
    for twice. Without yes=True it only counts. Returns (items, mentions)."""
    kinds = list(kinds)
    with conn.cursor() as cur:
        cur.execute("""select count(*) filter (where batch_id is not null and extracted_at is null),
                              count(*)
                       from extraction_state where version = %s and prompt_hash = %s and kind = any(%s)""",
                    (VERSION, prompt_hash, kinds))
        inflight, items = cur.fetchone()
        cur.execute("""select count(*) from mentions
                       where schema_version = %s and prompt_hash = %s
                         and ((comment_id is not null and 'comment' = any(%s))
                              or (comment_id is null and 'post' = any(%s)))""",
                    (prompt_v6.SCHEMA_VERSION, prompt_hash, kinds, kinds))
        mentions = cur.fetchone()[0]
    conn.commit()
    log(f"prompt {prompt_hash} ({', '.join(kinds)}): {items:,} item(s) in extraction_state, "
        f"{mentions:,} v6 mention row(s)")
    if inflight:
        raise SystemExit(f"{inflight:,} item(s) of prompt {prompt_hash} are in a batch (pending, submitted or "
                         "lost): let it finish (re-run to collect) or settle it with --resolve-pending / "
                         "--drop-batch first")
    if not yes:
        log("nothing deleted; re-run with --yes to delete them and queue the items again")
        return items, mentions
    with conn.cursor() as cur:
        cur.execute("select item_id, kind from extraction_state where version = %s and prompt_hash = %s "
                    "and kind = any(%s) order by item_id", (VERSION, prompt_hash, kinds))
        todo = cur.fetchall()
    conn.commit()
    gone_items = gone_mentions = 0
    for start in range(0, len(todo), chunk):
        part = todo[start:start + chunk]
        cids = [i for i, k in part if k == "comment"]
        tids = [i for i, k in part if k == "post"]
        with conn.cursor() as cur:
            cur.execute("""delete from mentions where schema_version = %s and prompt_hash = %s
                           and comment_id = any(%s)""", (prompt_v6.SCHEMA_VERSION, prompt_hash, cids))
            gone_mentions += cur.rowcount
            cur.execute("""delete from mentions where schema_version = %s and prompt_hash = %s
                           and comment_id is null and thread_id = any(%s)""",
                        (prompt_v6.SCHEMA_VERSION, prompt_hash, tids))
            gone_mentions += cur.rowcount
            cur.execute("delete from extraction_state where version = %s and prompt_hash = %s "
                        "and item_id = any(%s)", (VERSION, prompt_hash, cids + tids))
            gone_items += cur.rowcount
        conn.commit()
        log(f"  {min(start + chunk, len(todo)):,} / {len(todo):,} item(s) reset")
    # Rows of that hash whose state row is gone or names another hash (an
    # item since re-extracted under a newer prompt): the view already hides
    # them; delete them too, by id, in chunks.
    with conn.cursor() as cur:
        cur.execute("""select id from mentions where schema_version = %s and prompt_hash = %s
                         and ((comment_id is not null and 'comment' = any(%s))
                              or (comment_id is null and 'post' = any(%s)))""",
                    (prompt_v6.SCHEMA_VERSION, prompt_hash, kinds, kinds))
        stray = [r[0] for r in cur.fetchall()]
    conn.commit()
    for start in range(0, len(stray), chunk):
        with conn.cursor() as cur:
            cur.execute("delete from mentions where id = any(%s)", (stray[start:start + chunk],))
            gone_mentions += cur.rowcount
        conn.commit()
    log(f"reset prompt {prompt_hash}: {gone_items:,} item(s) are due again, {gone_mentions:,} mention row(s) "
        "deleted")
    return gone_items, gone_mentions


def read_version(conn):
    with conn.cursor() as cur:
        cur.execute("select read_version from extraction_settings")
        row = cur.fetchone()
    conn.commit()
    return row[0] if row else "legacy"


# ---------------------------------------------------------------- cli
def _parse_since(s):
    if s is None:
        return None
    if s.endswith("d") and s[:-1].isdigit():
        return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(s[:-1]))
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _parse_ids(s):
    if not s:
        return None
    if s.startswith("@"):
        with open(s[1:], encoding="utf-8") as f:
            return [x.strip() for x in f if x.strip()]
    return [x.strip() for x in s.split(",") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", action="store_true", help="use the Message Batches API (half price)")
    ap.add_argument("--max-usd", type=float, help="hard spend cap for this run (required to call the API)")
    ap.add_argument("--dry-run", action="store_true", help="render and price; no API call, no write")
    ap.add_argument("--scope", choices=("comments", "posts", "both"), default="both")
    ap.add_argument("--limit", type=int, help="at most N items this run")
    ap.add_argument("--since", help="only items created on or after this date (YYYY-MM-DD) or in the last Nd")
    ap.add_argument("--ids", help="only these ids: t1_x,t3_y or @file with one per line")
    ap.add_argument("--max-chars", type=int, help="only comments at most N characters long (the short-comment pilot)")
    ap.add_argument("--workers", type=int, default=WORKERS, help="concurrent direct calls")
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--max-inflight", type=int, default=MAX_INFLIGHT)
    ap.add_argument("--poll-seconds", type=float, default=POLL_SECONDS)
    ap.add_argument("--retry-errors", action="store_true", help="return parked items to the queue first")
    ap.add_argument("--status", action="store_true", help="print the v6 cursor, errors, batches and spend")
    ap.add_argument("--read", choices=("legacy", "v6"), help="switch what the board reads, then refresh")
    ap.add_argument("--resolve-pending", nargs=2, metavar=("PENDING_ID", "BATCH_ID"),
                    help="settle a submission with an unknown outcome: the batch id the Console shows, "
                         "'none' if it made none, or 'auto' to match the API's batch list")
    ap.add_argument("--drop-batch", metavar="BATCH_ID",
                    help="return a lost batch's items to the queue (only once the Console confirms it is gone)")
    ap.add_argument("--reset-hash", metavar="PROMPT_HASH",
                    help="delete the v6 mentions and cursor rows of this prompt hash (by --scope), so those "
                         "items are extracted again; counts only, unless --yes")
    ap.add_argument("--yes", action="store_true", help="with --reset-hash: really delete")
    ap.add_argument("--flip-grace-hours", type=float, default=FLIP_GRACE.total_seconds() / 3600,
                    help="with --read v6: forgive comments the old extractor read this recently "
                         "(default 2; it keeps running until the poller is switched)")
    ap.add_argument("--force", action="store_true",
                    help="with --read v6: flip even though v6 has not covered the old extractor's comments "
                         "or too many items are parked")
    th = ap.add_argument_group("thread mode (--mode thread)")
    th.add_argument("--mode", choices=("comment", "thread"), default="comment",
                    help="comment: one request per comment or post (the benchmarked default); thread: one per "
                         "chunk of a thread, the post as item [0] while it is due. With thread, --limit counts "
                         "threads, --ids takes thread ids, --since is on the post's date, and --scope comments "
                         "keeps posts as context only")
    th.add_argument("--effort", choices=prompt_v6.THREAD_EFFORTS, default=prompt_v6.THREAD_EFFORT,
                    help="thread mode's effort (default medium)")
    th.add_argument("--newest-first", action="store_true", help="newest threads first, so a capped run spends "
                                                                "on recent months first")
    th.add_argument("--chunk-comments", type=int, default=T.SOFT_COMMENTS,
                    help=f"soft budget: items per chunk (default {T.SOFT_COMMENTS})")
    th.add_argument("--chunk-tokens", type=int, default=T.SOFT_TOKENS,
                    help=f"soft budget: estimated tokens of comment text per chunk (default {T.SOFT_TOKENS})")
    th.add_argument("--chunk-max", type=int, default=T.MAX_COMMENTS,
                    help=f"hard max: comments in one chunk; only bigger reply groups are split "
                         f"(default {T.MAX_COMMENTS})")
    args = ap.parse_args(argv)
    kinds = {"comments": ("comment",), "posts": ("post",), "both": KINDS}[args.scope]
    since, ids = _parse_since(args.since), _parse_ids(args.ids)
    thread = args.mode == "thread"
    opts = None
    if thread:
        # Posts stay with post mode only if asked: --scope comments. A
        # thread-mode run never takes posts alone; post mode does that.
        if args.scope == "posts":
            raise SystemExit("--mode thread extracts comments, and posts as item [0]; for posts alone use "
                             "--mode comment --scope posts")
        if args.max_chars is not None:
            raise SystemExit("--max-chars is a comment-mode filter")
        if min(args.chunk_comments, args.chunk_tokens, args.chunk_max) < 1:
            raise SystemExit("chunk sizes must be positive")
        opts = ThreadOpts(args.effort, args.chunk_comments, args.chunk_tokens, args.chunk_max,
                          posts=args.scope == "both")
    elif args.effort != prompt_v6.THREAD_EFFORT or args.newest_first:
        raise SystemExit("--effort and --newest-first are thread-mode settings (comment mode runs as benchmarked)")

    conn = db.connect()
    require_schema(conn, thread=thread)
    # Each of these returns 0, the exit status, never what the helper returned.
    if args.status:
        status(conn)
        return 0
    if args.dry_run:
        if thread:
            dry_run_threads(conn, opts, args.limit, since, ids, args.newest_first)
        else:
            dry_run(conn, kinds, args.limit, since, ids, args.max_chars)
        return 0
    # Everything below changes v6 state, so it waits for no other v6 run.
    if not try_lock(conn):
        raise SystemExit("another v6 extraction is running (the poller's pass or a manual run); "
                         "try again when it is done")
    try:
        return _main_locked(conn, args, kinds, since, ids, opts)
    finally:
        unlock(conn)


def _main_locked(conn, args, kinds, since, ids, opts=None):
    if args.read:
        if args.read == VERSION:
            counts, reasons = flip_check(conn, dt.timedelta(hours=args.flip_grace_hours))
            print(f"v6 coverage: {counts['done']:,} item(s) done, {counts['parked']:,} parked "
                  f"(at most {counts['max_parked']:,}), {counts['missing']:,} old-extractor comment(s) "
                  f"without a finished v6 extraction, and {counts['recent']:,} more from the last "
                  f"{args.flip_grace_hours:g}h (allowed)")
            if reasons and not args.force:
                raise SystemExit("not flipping:\n  " + "\n  ".join(reasons) + "\n(--force flips anyway)")
        set_read_version(conn, args.read)
        return 0
    if args.reset_hash:
        items, mentions = reset_hash(conn, args.reset_hash, kinds, yes=args.yes)
        # Deleting live rows changes what the API reads at once; refresh the
        # materialized board too, as set_read_version does, so the two agree.
        if args.yes and (items or mentions) and read_version(conn) == VERSION:
            import refresh
            print("refreshing scoring views")
            refresh.refresh_views(conn)
        return 0
    if args.drop_batch:
        print(f"{drop_batch(conn, args.drop_batch):,} item(s) of {args.drop_batch} returned to the queue")
        return 0
    if args.resolve_pending and args.resolve_pending[1] != "auto":
        resolve_pending(conn, *args.resolve_pending)
        return 0

    key = AV.api_key()
    if args.resolve_pending:
        if not key:
            raise SystemExit(f"{AV.KEY_VAR} is not set")
        found = resolve_pending_auto(conn, AV.client(key), args.resolve_pending[0])
        return 0 if found else 4

    if args.max_usd is None:
        raise SystemExit("--max-usd is required: every run that calls the API has a hard cap")
    if not key:
        raise SystemExit(f"{AV.KEY_VAR} is not set (extraction uses its own key and no other)")
    if args.retry_errors:
        with conn.cursor() as cur:
            cur.execute("""update extraction_state set extract_error = null, attempts = 0, updated_at = now()
                           where version = %s and extract_error is not null and kind = any(%s)""",
                        (VERSION, list(kinds)))
            print(f"cleared {cur.rowcount:,} error(s)")
        conn.commit()

    cl = AV.client(key)
    budget = Budget(args.max_usd)
    stats = Stats()
    began = time.time()
    code = 0
    try:
        if opts is not None and args.batch:
            run_batch_threads(conn, cl, budget, opts, args.limit, since, ids, args.newest_first,
                              args.batch_size, args.max_inflight, args.poll_seconds, stats=stats)
        elif opts is not None:
            run_direct_threads(conn, cl, budget, opts, args.limit, since, ids, args.newest_first, args.workers,
                               stats=stats)
        elif args.batch:
            run_batch(conn, cl, budget, kinds, args.limit, since, ids, args.max_chars,
                      args.batch_size, args.max_inflight, args.poll_seconds, stats=stats)
        else:
            run_direct(conn, cl, budget, kinds, args.limit, since, ids, args.max_chars, args.workers,
                       stats=stats)
    except AV.AmbiguousSubmit as e:
        print(f"\nSTOPPED: a batch submission's outcome is unknown ({e}). It is kept as pending; the "
              "next run matches it against the API's batch list, or use --resolve-pending")
        code = 2
    except (AV.FatalAPIError, AV.TransientAPIError) as e:
        print(f"\nSTOPPED: {type(e).__name__}: {e}\nnothing unsent was marked; fix the cause and re-run")
        code = 2
    except KeyboardInterrupt:
        print("\ninterrupted -- finished items are committed and batches in flight re-attach on the next run")
        code = 130
    print(f"\n{stats.line()}  ({(time.time() - began) / 60:.1f} min)")
    print(f"cap ${budget.max:.2f}: ${budget.spent:.4f} spent, ${sum(budget.held.values()):.4f} "
          f"still held for batches in flight")
    if stats.refused or stats.threads_left:
        left = f" and {stats.threads_left:,} thread(s) not reached" if stats.threads_left else ""
        print(f"{stats.refused:,} item(s) not sent{left}: the cap was reached. Re-run with a higher --max-usd "
              "to resume.")
        code = code or 3
    if stats.done and read_version(conn) == VERSION:
        import refresh
        print("refreshing scoring views")
        refresh.refresh_views(conn)
    return code


if __name__ == "__main__":
    sys.exit(main() or 0)
