"""Embed comments and threads into the pgvector cache tables for semantic search.

    python embed.py --dry-run                 rows, tokens and projected cost; no API call, no write
    python embed.py --max-usd 1               the whole backlog, comments then threads
    python embed.py --scope comments --limit 500
    python embed.py --retry-errors            clear recorded errors, then try those rows again
    python embed.py --build-index             HNSW indexes, once the backlog has loaded
    python embed.py --build-index --dry-run   print the index SQL and stop

What gets a vector (see the "Semantic search" section of SPEC.md):
- every comment with at least one row in `mentions`, under any prompt hash,
  whose body is not [deleted] or [removed] -- embedded as thread title +
  comment body;
- every thread -- title + selftext cut to 1,500 characters.
Nothing is filtered for excluded_entities, unresolved names, is_negated or
reference_only. Those lists move with identity decisions and prompt versions,
and a vector is expensive to recompute only in comparison with a WHERE
clause, so search filters them when it reads.

Resumable the same way extract.py is: a row is still to do when it has no
vector for the current embedding.MODEL_KEY, or its stored input_hash no longer
matches the text it would be embedded from. Killing this mid-run and starting
again picks up where it stopped, and an edited comment is embedded again.
The hash is computed in SQL to find those rows, and again in Python from the
formatter that produced the text; if the two ever disagree the row is
recorded as an error rather than re-bought on every run.

One bad input never stalls the run. A request the provider refuses is split
until the one input at fault is found, and that row is recorded in
`embedding_errors` -- a cache table like the vectors, never the truth tables.
A failure of the service itself (auth, credit, routing, an outage that
outlasts the retries) stops the run instead, and those rows stay to-do.
"""

import argparse
import concurrent.futures
import re
import threading
import time
from dataclasses import dataclass, field

from psycopg2.extras import execute_values

import db
import embedding as E

WORKERS = 4                     # concurrent requests; the benchmark ran 8 per model
PAGE = E.DOC_BATCH * WORKERS * 2


@dataclass(frozen=True)
class Kind:
    """One embeddable table, and the SQL that mirrors its Python formatter."""
    name: str            # 'comment' | 'thread', the value in embedding_errors.kind
    scope: str           # the --scope spelling
    table: str
    key: str
    source: str          # select id, two text fields and the formatted text as `txt`
    fmt: object          # embedding.format_comment / format_thread


# Each `txt` expression must build the same string as its formatter, byte
# for byte, or every row looks changed. tests/test_embed_db.py checks that
# against a real Postgres, unicode and edge cases included. left() counts
# characters, as Python slicing counts code points.
COMMENTS = Kind(
    "comment", "comments", "comment_embeddings", "comment_id",
    """
    select c.id, t.title as a, c.body as b,
           coalesce(t.title, '') || E'\\n\\n' || c.body as txt
    from comments c
    join threads t on t.id = c.thread_id
    where c.body not in ('[deleted]', '[removed]')
      and exists (select 1 from mentions m where m.comment_id = c.id)
      and c.id > %(after)s
      and (%(since)s::timestamptz is null or c.created_utc >= %(since)s::timestamptz)
    """,
    E.format_comment)

THREADS = Kind(
    "thread", "threads", "thread_embeddings", "thread_id",
    f"""
    select t.id, t.title as a, t.selftext as b,
           coalesce(t.title, '') || E'\\n\\n' ||
           left(case when t.selftext in ('[deleted]', '[removed]') then ''
                     else coalesce(t.selftext, '') end, {E.THREAD_SELFTEXT_CHARS}) as txt
    from threads t
    where t.id > %(after)s
      and (%(since)s::timestamptz is null or t.created_utc >= %(since)s::timestamptz)
    """,
    E.format_thread)

KINDS = {"comments": [COMMENTS], "threads": [THREADS], "both": [COMMENTS, THREADS]}


def tables_exist(conn):
    with conn.cursor() as cur:
        cur.execute("""select to_regclass('comment_embeddings') is not null
                          and to_regclass('thread_embeddings') is not null
                          and to_regclass('embedding_errors') is not null""")
        return cur.fetchone()[0]


def select_todo(conn, kind, after, limit, since=None, have_tables=True):
    """The next rows still to embed, in id order after `after`.

    Keyset on id rather than OFFSET, so each page starts where the last one
    ended and a run is one pass over the table however many pages it takes.
    A row is skipped while an error is recorded for the same text; a new
    text (or --retry-errors) makes it due again.

    `have_tables=False` is for a dry run before the migration: everything is
    to do. Returns (id, field a, field b, sql_hash) tuples.
    """
    params = {"after": after, "since": since, "limit": limit, "model": E.MODEL_KEY,
              "kind": kind.name}
    if have_tables:
        sql = f"""
            select s.id, s.a, s.b, s.h
            from (select src.id, src.a, src.b,
                         encode(sha256(convert_to(src.txt, 'UTF8')), 'hex') as h
                  from ({kind.source}) src) s
            left join {kind.table} e on e.{kind.key} = s.id and e.model = %(model)s
            left join embedding_errors x
                   on x.kind = %(kind)s and x.item_id = s.id
                  and x.model = %(model)s and x.input_hash = s.h
            where e.input_hash is distinct from s.h
              and x.item_id is null
            order by s.id
            limit %(limit)s
        """
    else:
        sql = f"""
            select src.id, src.a, src.b,
                   encode(sha256(convert_to(src.txt, 'UTF8')), 'hex')
            from ({kind.source}) src
            order by src.id
            limit %(limit)s
        """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    # End the read transaction now: the API calls that follow take seconds,
    # and a connection idle in a transaction holds back vacuum on production.
    conn.commit()
    return rows


def prepare(kind, rows):
    """Format each row in Python and check it against the SQL's hash.

    Returns (items, drift): items are (id, text, hash) ready to embed; drift
    are (id, sql_hash, message) rows whose formatter and SQL disagree.
    """
    items, drift = [], []
    for item_id, a, b, sql_hash in rows:
        text = kind.fmt(a, b)
        h = E.input_hash(text)
        if h != sql_hash:
            drift.append((item_id, sql_hash,
                          "formatter drift: SQL and Python build different text"))
        else:
            items.append((item_id, text, h))
    return items, drift


def store_vectors(conn, kind, done):
    """done: (id, hash, vector). Upsert, and clear any old error for the row."""
    if not done:
        return 0
    with conn.cursor() as cur:
        execute_values(cur, f"""
            insert into {kind.table} ({kind.key}, model, input_hash, embedding)
            values %s
            on conflict ({kind.key}, model) do update
              set input_hash = excluded.input_hash,
                  embedding = excluded.embedding,
                  embedded_at = now()
        """, [(i, E.MODEL_KEY, h, E.to_pgvector(v)) for i, h, v in done],
            template="(%s, %s, %s, %s::halfvec)")
        cur.execute("""delete from embedding_errors
                       where kind = %s and model = %s and item_id = any(%s)""",
                    (kind.name, E.MODEL_KEY, [i for i, _, _ in done]))
    conn.commit()
    return len(done)


def store_errors(conn, kind, failed):
    """failed: (id, hash, message). Counted, so a row that keeps failing shows it."""
    if not failed:
        return 0
    with conn.cursor() as cur:
        execute_values(cur, """
            insert into embedding_errors (kind, item_id, model, input_hash, error)
            values %s
            on conflict (kind, item_id, model) do update
              set input_hash = excluded.input_hash,
                  error = excluded.error,
                  failures = embedding_errors.failures + 1,
                  failed_at = now()
        """, [(kind.name, i, E.MODEL_KEY, h, msg[:500]) for i, h, msg in failed])
    conn.commit()
    return len(failed)


def embed_items(items, budget, stop, attempts, timeout):
    """The network half; runs on a worker thread and touches no database.

    Returns (id, hash, vector, error) per item, or None if the run was
    stopped before this batch started. A refused request is split in two
    and each half retried, down to single inputs, so the error lands on the
    one row at fault.
    """
    if stop.is_set():
        return None
    try:
        got = E.embed_batch([t for _, t, _ in items], budget,
                            attempts=attempts, timeout=timeout)
    except E.InputRejected as e:
        if len(items) == 1:
            return [(items[0][0], items[0][2], None, f"rejected: {e}")]
        mid = len(items) // 2
        left = embed_items(items[:mid], budget, stop, attempts, timeout)
        right = embed_items(items[mid:], budget, stop, attempts, timeout)
        if left is None or right is None:
            # Stopped half way: keep what was paid for, leave the rest to-do.
            return (left or []) + (right or [])
        return left + right
    except (E.BudgetExceeded, E.ServiceError):
        stop.set()
        raise
    return [(i, h, v, err) for (i, _, h), (v, err) in zip(items, got)]


@dataclass
class Stats:
    embedded: dict = field(default_factory=dict)
    failed: dict = field(default_factory=dict)
    stop: str = None

    @property
    def attempted(self):
        return sum(self.embedded.values()) + sum(self.failed.values())


def run(conn, kinds, budget, *, limit=None, since=None, workers=WORKERS,
        batch=E.DOC_BATCH, attempts=E.ATTEMPTS, timeout=E.TIMEOUT,
        deadline=None, log=print):
    """Embed what is still to do. Returns Stats; Stats.stop says why it ended early.

    Requests fan out across threads; every database write stays on this
    thread, because psycopg2 connections are not thread-safe. Vectors that
    were paid for are stored even when another batch stops the run.
    `deadline` is a time.monotonic() value after which no new page starts --
    the poller's bound, so an outage cannot hold up the refresh behind it.
    """
    stats = Stats()
    stop = threading.Event()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        for kind in kinds:
            stats.embedded.setdefault(kind.name, 0)
            stats.failed.setdefault(kind.name, 0)
            after = ""
            while not stop.is_set():
                if limit is not None and stats.attempted >= limit:
                    break
                if deadline is not None and time.monotonic() > deadline:
                    stats.stop = "out of time for this cycle"
                    stop.set()
                    break
                take = PAGE if limit is None else min(PAGE, limit - stats.attempted)
                rows = select_todo(conn, kind, after, take, since)
                if not rows:
                    break
                after = rows[-1][0]
                items, drift = prepare(kind, rows)
                stats.failed[kind.name] += store_errors(conn, kind, drift)

                futures = [pool.submit(embed_items, items[i:i + batch], budget, stop,
                                       attempts, timeout)
                           for i in range(0, len(items), batch)]
                for f in concurrent.futures.as_completed(futures):
                    try:
                        results = f.result()
                    except (E.BudgetExceeded, E.ServiceError) as e:
                        stats.stop = stats.stop or f"{type(e).__name__}: {e}"
                        continue
                    if not results:
                        continue
                    stats.embedded[kind.name] += store_vectors(
                        conn, kind, [(i, h, v) for i, h, v, err in results if v is not None])
                    stats.failed[kind.name] += store_errors(
                        conn, kind, [(i, h, err) for i, h, v, err in results if v is None])
                log(f"  {kind.scope}: {stats.embedded[kind.name]:,} embedded, "
                    f"{stats.failed[kind.name]:,} failed, ${budget.spent:.4f} spent")
            if stop.is_set():
                break
    except KeyboardInterrupt:
        stop.set()
        stats.stop = "interrupted -- finished batches are committed, re-run to resume"
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    return stats


def dry_run(conn, kinds, since=None, limit=None, log=print):
    """Walk exactly the rows a real run would, through the same query and
    formatters, and price them. No API call and no write: safe on a
    read-only connection, and before the migration (then everything is to do).
    """
    have = tables_exist(conn)
    if not have:
        log("embedding tables not found (migration not applied): counting every eligible row")
    totals = []
    for kind in kinds:
        n = drift = 0
        nbytes = 0
        after = ""
        while limit is None or n < limit:
            take = PAGE if limit is None else min(PAGE, limit - n)
            rows = select_todo(conn, kind, after, take, since, have_tables=have)
            if not rows:
                break
            after = rows[-1][0]
            items, bad = prepare(kind, rows)
            drift += len(bad)
            n += len(rows)
            nbytes += sum(len(t.encode("utf-8")) for _, t, _ in items)
        tokens = nbytes / E.BYTES_PER_TOKEN
        totals.append((kind.scope, n, drift, tokens))
    log(f"\nmodel {E.MODEL_KEY}   price ${E.PRICE_PER_TOKEN * 1e6:.2f}/M tokens")
    log(f"{'scope':10} {'rows':>9} {'drift':>6} {'est tokens':>12} {'projected':>10} {'cap needs':>10}")
    for scope, n, drift, tokens in totals:
        cost = tokens * E.PRICE_PER_TOKEN
        log(f"{scope:10} {n:9,} {drift:6,} {tokens:12,.0f} ${cost:9.4f} ${cost * E.RESERVE_FACTOR:9.4f}")
    t = sum(x[3] for x in totals)
    log(f"{'total':10} {sum(x[1] for x in totals):9,} {sum(x[2] for x in totals):6,} "
        f"{t:12,.0f} ${t * E.PRICE_PER_TOKEN:9.4f} ${t * E.PRICE_PER_TOKEN * E.RESERVE_FACTOR:9.4f}")
    log("\nprojected = tokens at 4 bytes each (what the benchmark was billed); "
        "'cap needs' is the in-flight reservation the spend cap holds against it")
    return totals


# --- the HNSW index ----------------------------------------------------------

def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def index_name(kind):
    """One partial index per (table, model), named after the model, so a new
    model's index can be built beside the old one before the swap."""
    name = f"{kind.table}_hnsw_{_slug(E.MODEL_KEY.split('/', 1)[-1])}"
    return name[:63]


def index_statements(mem):
    """The SQL --build-index runs, one statement per entry.

    Partial on the current model: vectors of different models never share a
    graph, and the planner uses it only when a query says `model = '<key>'`
    as a literal. Serial on purpose: Railway's Postgres has a small /dev/shm,
    and a parallel build allocates its shared memory there -- the same
    failure that forced the serial refresh in poller.py.
    """
    if not re.fullmatch(r"\d+(kB|MB|GB)", mem):
        raise SystemExit(f"--index-mem must look like 256MB, not {mem!r}")
    out = [f"set maintenance_work_mem = '{mem}'",
           "set max_parallel_maintenance_workers = 0"]
    for kind in (COMMENTS, THREADS):
        out.append(
            f"create index concurrently if not exists {index_name(kind)} "
            f"on {kind.table} using hnsw (embedding halfvec_cosine_ops) "
            f"where model = '{E.MODEL_KEY}'")
    return out


def build_index(conn, mem, log=print):
    """CONCURRENTLY, so the poller can keep writing vectors while it builds.

    That needs autocommit and one statement at a time. A concurrent build that
    fails leaves an INVALID index behind, which `if not exists` would then
    skip forever, so an invalid one is dropped and rebuilt.
    """
    conn.commit()            # autocommit cannot be switched on mid-transaction
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for kind in (COMMENTS, THREADS):
                cur.execute("""select i.indisvalid from pg_index i
                               join pg_class c on c.oid = i.indexrelid
                               where c.relname = %s""", (index_name(kind),))
                row = cur.fetchone()
                if row is not None and not row[0]:
                    log(f"  dropping invalid {index_name(kind)} from a failed build")
                    cur.execute(f"drop index concurrently if exists {index_name(kind)}")
            for stmt in index_statements(mem):
                began = time.time()
                cur.execute(stmt)
                if stmt.startswith("create"):
                    log(f"  {stmt.split(' if not exists ')[1].split(' on ')[0]} "
                        f"({time.time() - began:.0f}s)")
    finally:
        conn.autocommit = False

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="report rows, tokens and projected cost; no API call, no write")
    ap.add_argument("--scope", choices=tuple(KINDS), default="both")
    ap.add_argument("--limit", type=int, default=None, help="stop after N rows per run")
    ap.add_argument("--max-usd", type=float, default=1.0,
                    help="spend cap for this run, checked before every request (default 1.00)")
    ap.add_argument("--workers", type=int, default=WORKERS, help="concurrent requests")
    ap.add_argument("--since-days", type=int, default=None,
                    help="only rows created in the last N days")
    ap.add_argument("--retry-errors", action="store_true",
                    help="clear this model's recorded errors so those rows are tried again")
    ap.add_argument("--build-index", action="store_true",
                    help="build the HNSW indexes (after the backlog has loaded)")
    ap.add_argument("--index-mem", default="256MB",
                    help="maintenance_work_mem for the index build (default 256MB)")
    args = ap.parse_args()

    if args.build_index:
        if args.dry_run:
            print(";\n".join(index_statements(args.index_mem)) + ";")
            return
        conn = db.connect()
        if not tables_exist(conn):
            raise SystemExit("embedding tables are missing: apply embed_schema.sql first")
        build_index(conn, args.index_mem)
        return

    conn = db.connect()
    since = None
    if args.since_days:
        with conn.cursor() as cur:
            cur.execute("select now() - make_interval(days => %s)", (args.since_days,))
            since = cur.fetchone()[0]
        conn.commit()
    kinds = KINDS[args.scope]

    if args.dry_run:
        if args.retry_errors and tables_exist(conn):
            with conn.cursor() as cur:
                cur.execute("select count(*) from embedding_errors where model = %s",
                            (E.MODEL_KEY,))
                print(f"--retry-errors would clear {cur.fetchone()[0]:,} error(s); "
                      f"the counts below do not include them")
            conn.commit()
        dry_run(conn, kinds, since, args.limit)
        return

    # Fail here rather than per row, like extract.py: a missing key would
    # otherwise stop the run on its first request anyway, but say why first.
    if not E.api_key_var():
        raise SystemExit(f"no OpenRouter key: set {' or '.join(E.KEY_VARS)} "
                         f"(in .env next to DATABASE_URL)")
    if not tables_exist(conn):
        raise SystemExit("embedding tables are missing: apply embed_schema.sql first")

    if args.retry_errors:
        with conn.cursor() as cur:
            cur.execute("delete from embedding_errors where model = %s", (E.MODEL_KEY,))
            print(f"cleared {cur.rowcount:,} error(s)")
        conn.commit()

    print(f"embedding {args.scope} with {E.MODEL_KEY} (key from {E.api_key_var()}), "
          f"cap ${args.max_usd:.2f}, {args.workers} workers")
    budget = E.Budget(args.max_usd)
    began = time.time()
    stats = run(conn, kinds, budget, limit=args.limit, since=since, workers=args.workers)

    print(f"\n{sum(stats.embedded.values()):,} embedded, {sum(stats.failed.values()):,} failed "
          f"({(time.time() - began) / 60:.1f} min)")
    for name in stats.embedded:
        print(f"  {name}s: {stats.embedded[name]:,} embedded, {stats.failed[name]:,} failed")
    if stats.stop:
        print(f"stopped early: {stats.stop}")
    print(f"cost ${budget.spent:.4f} over {budget.calls:,} call(s), {budget.tokens:,} tokens"
          + (f"; {budget.possibly_billed} failed attempt(s) charged at estimate"
             if budget.possibly_billed else "")
          + (f"; {budget.unpriced} call(s) priced from tokens" if budget.unpriced else ""))


if __name__ == "__main__":
    main()
