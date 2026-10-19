"""v6 extraction: r/FoodNYC's comments and posts through Claude Haiku 5.5, as benchmarked.

    python extract_v6.py --dry-run                         render and price the backlog; no API, no writes
    python extract_v6.py --batch --max-usd 70              the backlog through Message Batches at half price
    python extract_v6.py --batch --max-usd 5 --since 2026-09-01 --limit 3000 --scope comments
    python extract_v6.py --max-usd 1 --ids t1_abc,t3_def   direct calls, a few items
    python extract_v6.py --status                          cursor, errors, batches in flight, spend
    python extract_v6.py --read v6                         make the board count v6 rows (and refresh)

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
plus what is in flight. Attempts that may have been billed without an answer
(timeouts) are charged at their worst case. Batches re-attached from an
earlier run count against this run's cap until collected.

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

from psycopg2.extras import Json

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


def candidate_ids(conn, kind, limit=None, since=None, ids=None, max_chars=None):
    """Item ids still due under v6, in processing order.

    r/FoodNYC only (subreddits.HOME): the other cities are collected, never
    extracted. A comment is due unless it is [deleted]/[removed]/blank,
    however short. Comments come thread by thread, so an interrupted run
    leaves whole threads finished; posts oldest first.
    """
    p = {"home": subreddits.HOME, "v": VERSION, "since": since, "ids": list(ids) if ids else None,
         "max_chars": max_chars, "limit": limit}
    if kind == "comment":
        sql = f"""
            select c.id from comments c
            left join extraction_state s on s.item_id = c.id and s.version = %(v)s
            where c.subreddit = %(home)s
              and btrim(c.body) not in ('', '[deleted]', '[removed]')
              and {QUEUED}
              and (%(since)s::timestamptz is null or c.created_utc >= %(since)s::timestamptz)
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
              and (%(ids)s::text[] is null or t.id = any(%(ids)s::text[]))
            order by t.created_utc, t.id
            limit %(limit)s"""
    with conn.cursor() as cur:
        cur.execute(sql, p)
        out = [r[0] for r in cur.fetchall()]
    conn.commit()
    return out


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
_INSERT = (f"insert into mentions ({', '.join(COLUMNS)}) values ({', '.join(['%s'] * len(COLUMNS))}) "
           # Must match mentions_unique_idx / mentions_post_unique_idx exactly.
           "on conflict {target} do nothing")
_TARGET = {"comment": "(comment_id, entity_key, prompt_hash)",
           "post": "(thread_id, entity_key, prompt_hash) where comment_id is null"}


def _state(cur, item, **f):
    """Upsert the item's extraction_state row with these fields set."""
    cols = ["item_id", "version", "kind"] + list(f)
    vals = [item.id, VERSION, item.kind] + list(f.values())
    sets = ", ".join(f"{k} = excluded.{k}" for k in f)
    cur.execute(f"""insert into extraction_state ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})
                    on conflict (item_id, version) do update set {sets}, updated_at = now()""", vals)


def store(conn, item, output, usage, cost, batch_id=None):
    """Write one item's mentions and mark it done, in one transaction.

    Two mentions of one place in an item (the model spelling it two ways)
    share an entity_key and are one row, as in the old writer; the second is
    still in extraction_state.output with everything else the model said.
    Returns the number of mention rows written.
    """
    rows = [r for r in (mention_row(item, m) for m in output["mentions"]) if r]
    n = 0
    with conn.cursor() as cur:
        sql = _INSERT.format(target=_TARGET[item.kind])
        for r in rows:
            cur.execute(sql, [r[c] for c in COLUMNS])
            n += cur.rowcount
        cur.execute("""select coalesce(cost_usd, 0), attempts from extraction_state
                       where item_id = %s and version = %s""", (item.id, VERSION))
        prev = cur.fetchone() or (0, 0)
        _state(cur, item, prompt_hash=item.prompt_hash, model=prompt_v6.MODEL, batch_id=None,
               attempts=prev[1] + 1, extracted_at=dt.datetime.now(dt.timezone.utc), extract_error=None,
               output=Json(output), usage=Json(usage), cost_usd=float(prev[0]) + cost)
    conn.commit()
    return n


def record_failure(conn, item, code, usage=None, cost=0.0, batch_id=None):
    """The item got no usable answer. The first time it is queued again; the
    second it is parked with extract_error until --retry-errors. Returns True
    when parked."""
    with conn.cursor() as cur:
        cur.execute("""select coalesce(cost_usd, 0), attempts from extraction_state
                       where item_id = %s and version = %s""", (item.id, VERSION))
        prev = cur.fetchone() or (0, 0)
        attempts = prev[1] + 1
        parked = attempts >= MAX_ATTEMPTS
        _state(cur, item, prompt_hash=item.prompt_hash, model=prompt_v6.MODEL, batch_id=None,
               attempts=attempts, extracted_at=None,
               extract_error=str(code)[:500] if parked else None,
               usage=Json(usage) if usage else None, cost_usd=float(prev[0]) + cost)
    conn.commit()
    return parked


def _handle(conn, item, message, cost, stats, batch_id=None, log=print):
    """Parse and store one answer, or record why it is not one."""
    usage = AV.usage_of(message)
    stats.add_usage(usage, cost)
    try:
        output = AV.parse(message)
    except AV.ItemError as e:
        stats.failed += 1
        stats.parked += record_failure(conn, item, str(e), usage, cost, batch_id)
        return
    try:
        stats.mentions += store(conn, item, output, usage, cost, batch_id)
    except Exception as e:
        # A row the database refuses (a check constraint, say) is this item's
        # problem, not the run's: park it with the reason and carry on.
        conn.rollback()
        stats.failed += 1
        stats.parked += record_failure(conn, item, f"store_error: {type(e).__name__}: {e}", usage, cost, batch_id)
        log(f"  {item.id}: store failed ({type(e).__name__}: {e})")
        return
    stats.done += 1


# ---------------------------------------------------------------- direct
def run_direct(conn, cl, budget, kinds=KINDS, limit=None, since=None, ids=None, max_chars=None,
               workers=WORKERS, log=print, stats=None):
    """Extract due items with direct calls, `workers` at a time. Returns Stats.

    The network half runs on threads and touches no database; every write is
    on this thread, because psycopg2 connections are not thread-safe. A
    FatalAPIError or TransientAPIError stops the pass after the answers
    already received are stored; items not sent stay due.
    """
    stats = stats or Stats()
    stop = threading.Event()
    left = limit
    for kind in kinds:
        if stop.is_set() or (left is not None and left <= 0):
            break
        todo = candidate_ids(conn, kind, left, since, ids, max_chars if kind == "comment" else None)
        if left is not None:
            left -= len(todo)
        for start in range(0, len(todo), 200):
            if stop.is_set():
                break
            items = render_items(conn, kind, todo[start:start + 200])
            _direct_page(conn, cl, budget, items, workers, stats, stop, log)
    return stats


def _direct_page(conn, cl, budget, items, workers, stats, stop, log):
    def work(item):
        if stop.is_set():
            return item, None, 0.0
        w = item.worst(batch=False)
        if not budget.reserve(w):
            stop.set()
            return item, "refused", 0.0
        try:
            msg = AV.call(cl, item.params(), log=log, on_lost=lambda n: budget.charge(w * n))
        except (AV.FatalAPIError, AV.TransientAPIError) as e:
            budget.settle(w, 0.0)
            stop.set()
            return item, e, 0.0
        c = AV.cost(AV.usage_of(msg), batch=False)
        budget.settle(w, c)
        return item, msg, c

    halt = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in concurrent.futures.as_completed([pool.submit(work, it) for it in items]):
            item, res, c = fut.result()
            if res is None:
                continue
            if isinstance(res, str):
                stats.refused += 1
            elif isinstance(res, Exception):
                halt = halt or res
            else:
                _handle(conn, item, res, c, stats, log=log)
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
    with conn.cursor() as cur:
        cur.execute("insert into extract_batches (id, version, requests, hold_usd) values (%s, %s, %s, %s)",
                    (pid, VERSION, len(batch), held))
        for it in batch:
            _state(cur, it, prompt_hash=it.prompt_hash, model=prompt_v6.MODEL, batch_id=pid)
    conn.commit()
    budget.hold(pid, held, force=True)
    try:
        bid = AV.submit(cl, [(it.id, it.params()) for it in batch])
    except AV.TransientAPIError:
        # Nothing was created (the API said so), so undo the bookkeeping.
        with conn.cursor() as cur:
            cur.execute("update extraction_state set batch_id = null where batch_id = %s", (pid,))
            cur.execute("delete from extract_batches where id = %s", (pid,))
        conn.commit()
        budget.release(pid, 0.0)
        raise
    except AV.FatalAPIError:
        with conn.cursor() as cur:
            cur.execute("update extraction_state set batch_id = null where batch_id = %s", (pid,))
            cur.execute("delete from extract_batches where id = %s", (pid,))
        conn.commit()
        budget.release(pid, 0.0)
        raise
    with conn.cursor() as cur:
        cur.execute("""update extract_batches set id = %s, status = 'submitted', submitted_at = now()
                       where id = %s""", (bid, pid))
        cur.execute("update extraction_state set batch_id = %s where batch_id = %s", (bid, pid))
    conn.commit()
    budget.rename(pid, bid)
    log(f"submitted batch {bid}: {len(batch)} requests, worst case ${held:.4f} held")
    return bid


def _collect(conn, cl, budget, bid, stats, log):
    """Store a finished batch's answers and settle its hold. Returns the
    items owed a retry (rendered again, so they go out as they would fresh).

    An invalid_request_error inside a batch is the batch-shaped version of a
    direct 4xx: those items are left due and unmarked, the rest is stored, and
    FatalAPIError is raised once the batch is settled."""
    res = AV.results(cl, bid)
    with conn.cursor() as cur:
        cur.execute("select item_id, kind, prompt_hash from extraction_state where batch_id = %s", (bid,))
        members = cur.fetchall()
    conn.commit()
    total, retry, invalid = 0.0, [], []
    for item_id, kind, ph in members:
        item = Item(kind, item_id, None, None, ph)
        r = res.get(item_id, ("missing",))
        if r[0] == "succeeded":
            c = AV.cost(AV.usage_of(r[1]), batch=True)
            total += c
            _handle(conn, item, r[1], c, stats, batch_id=bid, log=log)
            continue
        if r[0] == "errored" and r[1] == "invalid_request_error":
            invalid.append(f"{item_id}: {r[2]}")
            with conn.cursor() as cur:
                cur.execute("update extraction_state set batch_id = null where item_id = %s and version = %s",
                            (item_id, VERSION))
            conn.commit()
            continue
        code = f"batch_{r[0]}" + (f": {r[1]}: {r[2]}" if r[0] == "errored" else "")
        stats.failed += 1
        parked = record_failure(conn, item, code, batch_id=bid)
        stats.parked += parked
        if not parked:
            retry.append((kind, item_id))
    with conn.cursor() as cur:
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

    1. A 'pending-' batch row means a submission was interrupted: stop, and
       let a person check the Console (--resolve-pending).
    2. Re-attach to batches submitted earlier and not collected; their holds
       count against this run's cap until they are.
    3. Submit sub-batches that fit what remains under the cap, up to
       max_inflight at once; collect each as it ends, and send the items it
       hands back for a retry first.
    """
    stats = stats or Stats()
    pend = _pending(conn)
    if pend:
        raise SystemExit(f"interrupted submission(s) {', '.join(pend)}: check the Console for a batch "
                         "submitted at that time, then run --resolve-pending ID BATCH_ID (or none)")
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
        ended = None
        for bid in inflight:
            b = AV.retrieve(cl, bid)
            if b.processing_status == "ended":
                ended = bid
                break
        if ended is None:
            c = getattr(b, "request_counts", None)
            if c is not None:
                log(f"  batch {bid}: {b.processing_status}, {c.processing} processing, "
                    f"{c.succeeded} succeeded, {c.errored} errored")
            sleep(poll_seconds)
            continue
        inflight.remove(ended)
        retry = _collect(conn, cl, budget, ended, stats, log)
        # Retries go first: they finish work already paid for. The hold just
        # became the (much smaller) actual cost, so there may be room again.
        queue = retry + queue
        capped = False
    stats.refused += len(queue)
    return stats


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
    materialized board and the API's direct reads agree again."""
    with conn.cursor() as cur:
        cur.execute("update extraction_settings set read_version = %s, updated_at = now()", (version,))
        if cur.rowcount == 0:
            cur.execute("insert into extraction_settings (read_version) values (%s)", (version,))
    conn.commit()
    log(f"board now reads {version} mentions")
    if refresh_views:
        import refresh
        refresh.refresh_views(conn)


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
                    help="adopt the batch an interrupted submission created, or 'none' to drop it")
    args = ap.parse_args(argv)
    kinds = {"comments": ("comment",), "posts": ("post",), "both": KINDS}[args.scope]
    since, ids = _parse_since(args.since), _parse_ids(args.ids)

    conn = db.connect()
    require_schema(conn)
    # Each of these returns 0, the exit status, never what the helper returned.
    if args.status:
        status(conn)
        return 0
    if args.read:
        set_read_version(conn, args.read)
        return 0
    if args.resolve_pending:
        resolve_pending(conn, *args.resolve_pending)
        return 0
    if args.dry_run:
        dry_run(conn, kinds, args.limit, since, ids, args.max_chars)
        return 0

    if args.max_usd is None:
        raise SystemExit("--max-usd is required: every run that calls the API has a hard cap")
    key = AV.api_key()
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
