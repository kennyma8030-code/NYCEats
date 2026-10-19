"""v6 extraction: r/FoodNYC's comments and posts through Claude Haiku 5.5, as benchmarked.

    python extract_v6.py --dry-run                         render and price the backlog; no API, no writes
    python extract_v6.py --batch --max-usd 70              the backlog through Message Batches at half price
    python extract_v6.py --batch --max-usd 5 --since 2026-09-01 --limit 3000 --scope comments
    python extract_v6.py --max-usd 1 --ids t1_abc,t3_def   direct calls, a few items
    python extract_v6.py --status                          cursor, errors, batches in flight, spend
    python extract_v6.py --read v6                         make the board count v6 rows (and refresh)
    python extract_v6.py --reset-hash 979dcd6b9267 --yes   redo what that prompt extracted (after a fix)

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

from psycopg2.extras import Json, execute_values

import anthropic_v6 as AV
import db
import extract
import prompt_v6
import subreddits

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


def require_schema(conn):
    if not schema_ready(conn):
        raise SchemaMissing("v6 tables are missing: apply extract_v6_schema.sql first")


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
        return (f"{self.done:,} extracted, {self.mentions:,} mentions, {self.failed:,} failed "
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


def write(conn, entries):
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
    """
    if not entries:
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


def _write_counted(conn, entries, stats, log=print):
    """write() the entries and count them. Returns the ids now parked.

    If the database refuses a row (a check constraint, say), the whole chunk
    rolls back and is written again one item at a time, so the refusal parks
    that item with the reason, and the run carries on."""
    try:
        n, parked = write(conn, entries)
    except Exception:
        conn.rollback()
        if len(entries) == 1:
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
            retry = _collect(conn, cl, budget, ended, stats, log, sleep=sleep)
        except AV.NotFound as e:          # results past retention
            _lost(conn, budget, ended, e, log)
            capped = False
            continue
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
    conn.commit()
    return n


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
        else:
            cur.execute("""update extract_batches set id = %s, status = 'submitted', submitted_at = now()
                           where id = %s and status = 'pending'""", (batch_id, pending_id))
            if cur.rowcount != 1:
                raise SystemExit(f"no pending batch {pending_id}")
            cur.execute("update extraction_state set batch_id = %s where batch_id = %s", (batch_id, pending_id))
    conn.commit()


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
    args = ap.parse_args(argv)
    kinds = {"comments": ("comment",), "posts": ("post",), "both": KINDS}[args.scope]
    since, ids = _parse_since(args.since), _parse_ids(args.ids)

    conn = db.connect()
    require_schema(conn)
    # Each of these returns 0, the exit status, never what the helper returned.
    if args.status:
        status(conn)
        return 0
    if args.dry_run:
        dry_run(conn, kinds, args.limit, since, ids, args.max_chars)
        return 0
    # Everything below changes v6 state, so it waits for no other v6 run.
    if not try_lock(conn):
        raise SystemExit("another v6 extraction is running (the poller's pass or a manual run); "
                         "try again when it is done")
    try:
        return _main_locked(conn, args, kinds, since, ids)
    finally:
        unlock(conn)


def _main_locked(conn, args, kinds, since, ids):
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
        if args.batch:
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
    if stats.refused:
        print(f"{stats.refused:,} item(s) not sent: the cap was reached. Re-run with a higher --max-usd to resume.")
        code = code or 3
    if stats.done and read_version(conn) == VERSION:
        import refresh
        print("refreshing scoring views")
        refresh.refresh_views(conn)
    return code


if __name__ == "__main__":
    sys.exit(main() or 0)
