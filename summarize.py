"""Place summaries: two or three sentences on what r/FoodNYC says about each busy place.

    python summarize.py --status                       what is written, failing, parked; spend so far
    python summarize.py --dry-run                      what qualifies, what is due, input sizes, cost; no API, no writes
    python summarize.py --dry-run --keys "katzs delicatessen" --print-input   the exact text a place would send
    python summarize.py --max-usd 1                    write what is due, under a $1 cap
    python summarize.py --keys "keens steakhouse,joes pizza" --force --max-usd 0.10
    python summarize.py --sample 50 --max-usd 0.50 --review summary_review.md
                                                       the quality check: ~50 chosen places, each
                                                       summary written next to the comments it was given
    python summarize.py --sample 50 --review summary_review.md --review-only
                                                       the same file from what is stored; no API
    python summarize.py --retry-errors --max-usd 1     unpark places that kept failing, then run

GitHub issue #2 is the design; its "Decisions (2026-11-03)" comment is what
this builds. Like every pipeline script it reads DATABASE_URL, which is
production: only --status and --dry-run (and --review-only) are read-only,
everything else calls the API and writes summaries and their cost.

Who gets a summary. A place qualifies with at least SUMMARY_MIN_MENTIONS
(n, 10) comments in the last WINDOW_DAYS (365) that mention it, counted on
thread-mode v6 mentions only (prompt_v6.PROMPT_HASH_THREAD, read through
live_mentions so every exclusion the board makes applies), r/FoodNYC,
leaving out comments deleted later, AutoModerator, and names in
excluded_entities. Every mention counts toward n, opinion or not. Mentions
are counted by comment: two spellings of one place in one comment are one.
A place with a summary is written again only when SUMMARY_NEW_MENTIONS (x,
5) qualifying comments have come in since, or the model or the prompt
changed (prompt_hash). Nothing is rewritten for age alone.

The watermark for "x new" is the newest qualifying comment the summary saw
(last_mention_at), not the count it saw (mention_count, kept for the
record). The count is over a rolling year, so for a place mentioned once a
week it stays near 52 forever as old comments fall out while new ones come
in, and a count difference would never reach x. Comments newer than the
watermark do.

What the model reads. Every comment from the last year whose mention of the
place gives an opinion (v6 opinion 'endorse' or 'stated'), leaving out
opinions about the past (timeframe 'past') and deleted comments. Under
TARGET_COMMENTS (60) of those, older opinionated comments are added, newest
first, until there are 60 or none are left. Mentions with no opinion are
never sent. Measured on production (Nov 3, 2026): 2,750 places qualify;
the median sends 24 comments and 6k characters (thread titles included),
the 99th percentile 316 comments and 86k, and the largest, Katz's, 1,123
comments and 323k characters (some 450k with the markup around each
comment, roughly 130k tokens). Haiku 5.5 reads 1M, so no place comes near
overflowing it, and the token budget (SUMMARY_MAX_INPUT_TOKENS, estimated at
a pessimistic 2.5 characters a token) keeps the newest comments only past
500k, which no place reaches today. Lower it to keep the busiest places'
calls under Haiku's 100k-token line, past which a whole call is billed at
five times the rate: about the 3 largest places today, a few cents a call.

One exception to "no opinion, no past": a closure. In that sample 2,000 of
the 2,100 mentions marked closed were also marked past ("RIP, it was the
best"), and a quarter carried no opinion ("they closed last month"), so the
two rules would hide almost every report that a place shut. The newest
STATUS_REPORTS (5) comments from the last year that say a place closed or
moved are sent in a section of their own, labelled as reports and nothing
else, so the summary can say so.

Each comment goes with its date, its thread's title (a comment often names
the place only through the thread it answers), the names it used, and how v6
read its view of this place (praise, criticism, mixed, recommends, warns
against). The label is there because a comment can be about several places:
it points the model at the part about this one, and a header counts the
labels so "most" and "some" come out right. The prompt says the text, not
the label, is the evidence. v6's notes and dish fields are not sent: they
are another model's paraphrase, and the summary should rest on what people
wrote.

Spend. Every call holds its worst case (extract_v6.Budget) under the pass's
cap (SUMMARY_RUN_USD, default $1, or --max-usd) and the lifetime ceiling
(SUMMARY_CEILING_USD, default $10), which is read from summary_calls every
time, so no restart can spend past it. Every call is recorded there, a
failed answer too (it was billed), and an attempt that may have been billed
with no answer (a timeout) at its worst case. When the cap or the ceiling
refuses a call the pass stops and says which loudly. A call that costs more
than was held for it, or recorded spend past the ceiling, trips a wire: the
pass stops, and the poller turns summaries off until it restarts.

Failures. An answer that cannot be used (cut off, refused, not JSON, empty,
naming a user) is the place's: its row keeps the last good summary, counts
the attempt, and after MAX_ATTEMPTS (3) the place is parked until
--retry-errors. A 4xx other than 429 is the request's or the account's and
stops the pass; so do rate limits or outages that outlast the retries.

Key: SUMMARY_ANTHROPIC_API_KEY and nothing else (anthropic_v6.client drops
every other Anthropic credential from the environment). Model claude-haiku-5-5,
direct calls (no batches), adaptive thinking at SUMMARY_EFFORT (low),
strict JSON output.

One run at a time, by advisory lock: the poller's step skips while a manual
run holds it.
"""

import argparse
import collections
import concurrent.futures
import dataclasses
import datetime as dt
import hashlib
import json
import os
import random
import re
import sys
import threading
import time

import anthropic_v6 as AV
import db
import extract_v6 as EV
import prompt_v6
import subreddits

KEY_VAR = "SUMMARY_ANTHROPIC_API_KEY"
MODEL = "claude-haiku-5-5"
MAX_TOKENS = 4000                 # thinking included; an answer is ~100 words
EFFORT_ENV = "SUMMARY_EFFORT"
EFFORTS = ("low", "medium", "high")
WINDOW_DAYS = 365
TARGET_COMMENTS = 60
STATUS_REPORTS = 5
MAX_ATTEMPTS = 3
# Haiku 5.5 reads 1M tokens. The default budget leaves room for the prompt
# and the answer, and is estimated at a pessimistic 2.5 characters a token
# (prose runs nearer 4), so it never lets a request reach the limit.
# SUMMARY_MAX_INPUT_TOKENS sets it; it is left out of prompt_hash, because
# it changes only the largest places' input, so after changing it rewrite
# those with --keys ... --force.
MAX_INPUT_TOKENS_ENV = "SUMMARY_MAX_INPUT_TOKENS"
CHARS_PER_TOKEN_BUDGET = 2.5
# For dry-run estimates only: English prose with light markup, and an answer
# of a short thinking pass plus ~100 words at effort low.
CHARS_PER_TOKEN_EST = 3.5
EST_OUTPUT_TOKENS = 600
COMMENT_OVERHEAD_CHARS = 110      # the tags, date, names and label around each comment

MIN_MENTIONS_ENV, NEW_MENTIONS_ENV = "SUMMARY_MIN_MENTIONS", "SUMMARY_NEW_MENTIONS"
RUN_ENV, CEILING_ENV = "SUMMARY_RUN_USD", "SUMMARY_CEILING_USD"
DEFAULTS = {MIN_MENTIONS_ENV: 10, NEW_MENTIONS_ENV: 5, RUN_ENV: 1.0, CEILING_ENV: 10.0,
            MAX_INPUT_TOKENS_ENV: 500_000}

# Inside the poller's pass a call may take TIMEOUT seconds and is tried
# ATTEMPTS times, and no new call starts after DEADLINE: an outage costs the
# polls a few minutes of freshness, never comments.
TIMEOUT = 90
ATTEMPTS = 2
DEADLINE = 5 * 60

LOCK_KEY = 0x6E796373_756D             # "nycs" "um"
TRIP_EPS = 1e-6

# Bumped when the user message's layout changes, so prompt_hash moves and
# every summary is written again from the new layout.
FORMAT_VERSION = "1"

SYSTEM_PROMPT = """\
You write a short summary of what commenters on r/FoodNYC, the New York City food subreddit, say about one place to eat or drink. It appears on the place's page on a site that ranks places by how the subreddit talks about them.

You are given the place's name and its comments, newest first. Each comment comes with its date, the title of the thread it was posted in, the name or names it used for the place, and a label saying how an automatic reader took its view of this place: praise, strong praise, criticism, harsh criticism, mixed, recommends (named it as a pick without saying why), warns against it, or opinion. The header counts the labels. The comment text is the evidence; the label is only a pointer. A comment may talk about several places: use only what it says about this one. There may also be status reports: recent comments that say the place closed or moved.

Write two or three sentences of plain prose and nothing else.
- Say what commenters say: what they like, what they complain about, and how opinion divides. Weigh by how many comments say a thing, with words like "most", "many", "some", "a few", and let the balance of the summary follow the balance of the comments: if most of them are negative, so is the summary.
- Keep the complaints. A criticism that several commenters make, or that runs through the discussion (prices, service, waits, a decline, hype), must be in the summary, stated as plainly as the commenters put it. Never soften or drop it to make the place sound better.
- Attribute everything to the commenters ("commenters say", "regulars recommend", "several people found"). Never state an opinion as fact, never name or quote a user, and write no usernames.
- If the status reports or recent comments say the place has closed or moved, say so first. If only one of several locations closed, say that. If the reports conflict or are vague, say commenters report it may have closed. Do not call it closed on the strength of reports that newer comments contradict.
- A comment about how a place used to be is not a view of it now, unless it says the place has changed.
- Serious claims (food poisoning, health problems) go in only if more than one commenter makes them, attributed.
- No lists of dishes: name a dish or two only when the discussion centres on them. No scores, counts, percentages, dates, links, quotes or citations.
- Use only what is in the comments. Add nothing you know about the place from elsewhere.

Answer with JSON: {"summary": "<the two or three sentences>"}."""

SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}},
          "required": ["summary"], "additionalProperties": False}


def effort():
    e = (os.environ.get(EFFORT_ENV) or "low").strip().lower()
    if e not in EFFORTS:
        raise SystemExit(f"{EFFORT_ENV}={e!r} is not one of {', '.join(EFFORTS)}")
    return e


def prompt_hash(eff=None):
    """What a summary was written under, beside the model: the instructions,
    the input's layout and how it is chosen, and the request's settings.
    Change any and every summary is due again."""
    spec = {"system": SYSTEM_PROMPT, "format": FORMAT_VERSION, "schema": SCHEMA,
            "effort": eff or effort(), "max_tokens": MAX_TOKENS, "window_days": WINDOW_DAYS,
            "target": TARGET_COMMENTS, "status_reports": STATUS_REPORTS,
            "source_hash": prompt_v6.PROMPT_HASH_THREAD}
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def setting(name, cast=float):
    """An env-configurable number; a value that is not a positive number refuses to run."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return cast(DEFAULTS[name])
    try:
        v = cast(raw)
    except ValueError:
        raise SystemExit(f"{name} must be a number, not {raw!r}")
    if not v > 0:
        raise SystemExit(f"{name} must be above zero, not {raw!r}")
    return v


def api_key():
    return os.environ.get(KEY_VAR) or None


def client(key, timeout=None):
    return AV.client(key, timeout=timeout)


# ---------------------------------------------------------------- database
def tables_exist(conn):
    with conn.cursor() as cur:
        cur.execute("select to_regclass('place_summaries') is not null and to_regclass('summary_calls') is not null")
        ok = cur.fetchone()[0]
    conn.commit()
    return ok


def try_lock(conn):
    with conn.cursor() as cur:
        cur.execute("select pg_try_advisory_lock(%s)", (LOCK_KEY,))
        ok = cur.fetchone()[0]
    conn.commit()
    return ok


def unlock(conn):
    if conn.closed:
        return
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))
    conn.commit()


def spend_on_record(cur):
    """(every summary call's recorded cost, 0): extract_v6.Ceiling's ledger
    reader for summaries. Nothing is ever in flight between passes: calls
    are direct and recorded as they are answered."""
    cur.execute("select coalesce(sum(cost_usd), 0) from summary_calls")
    return float(cur.fetchone()[0]), 0.0


def make_budget(max_usd, ceiling_usd, connect=None):
    """The pass's cap under the lifetime ceiling, read from summary_calls on a
    connection of its own (connect, db.connect by default)."""
    ceiling = EV.Ceiling(ceiling_usd, connect or db.connect, spend=spend_on_record)
    return EV.Budget(max_usd, ceiling)


def _since(conn, days=WINDOW_DAYS):
    with conn.cursor() as cur:
        cur.execute("select now(), now() - make_interval(days => %s)", (days,))
        now, since = cur.fetchone()
    conn.commit()
    return now, since


@dataclasses.dataclass
class Place:
    key: str
    n: int                    # qualifying comments in the window
    newest: dt.datetime       # the newest of them: the next watermark
    opinions: int             # of them, ones with an opinion that would be sent
    negative: int             # of those, criticism or warnings
    closed: int               # comments in the window saying it closed or moved
    fresh: int                # qualifying comments newer than the stored watermark
    has_summary: bool
    model: str = None
    prompt_hash: str = None
    attempts: int = 0
    error: str = None
    written_at: dt.datetime = None


_QUALIFYING = """
with base as (
  select coalesce(a.resolved_key, m.entity_key) as rkey, m.comment_id, c.created_utc,
         m.opinion in ('endorse', 'stated') and m.timeframe is distinct from 'past' as op,
         m.opinion in ('endorse', 'stated') and m.timeframe is distinct from 'past'
           and (coalesce(m.avoid, false) or (m.opinion = 'stated' and m.overall_level < 0)) as neg,
         m.status in ('closed', 'moved') as moved
  from live_mentions m
  join comments c on c.id = m.comment_id
  left join entity_alias a on a.entity_key = m.entity_key
  where m.prompt_hash = %(hash)s
    and c.subreddit = %(sub)s
    and c.created_utc > %(since)s
    and not coalesce(c.was_deleted_later, false)
    and c.author is distinct from 'AutoModerator'
)
select b.rkey, count(distinct b.comment_id), max(b.created_utc),
       count(distinct b.comment_id) filter (where b.op),
       count(distinct b.comment_id) filter (where b.neg),
       count(distinct b.comment_id) filter (where b.moved),
       count(distinct b.comment_id) filter (where b.created_utc > s.last_mention_at),
       s.summary is not null, s.model, s.prompt_hash, coalesce(s.attempts, 0), s.error, s.written_at
from base b
left join {summaries} s on s.resolved_key = b.rkey
where not exists (select 1 from excluded_entities x where x.entity_key = b.rkey)
  {keys}
group by b.rkey, s.resolved_key, s.summary, s.model, s.prompt_hash, s.attempts, s.error, s.written_at
having count(distinct b.comment_id) >= %(n)s
"""
# Stands in for place_summaries in a dry run before summary_schema.sql is
# applied: every place reads as never summarized.
_NO_SUMMARIES = """(select null::text as resolved_key, null::text as summary, null::text as model,
                     null::text as prompt_hash, 0 as attempts, null::text as error,
                     null::timestamptz as written_at, null::timestamptz as last_mention_at limit 0)"""


def qualifying(conn, n, keys=None, since=None):
    """Every place that qualifies now, with where its summary stands."""
    if keys is not None and not keys:
        return []
    if since is None:
        _, since = _since(conn)
    sql = _QUALIFYING.format(keys="and b.rkey = any(%(keys)s)" if keys is not None else "",
                             summaries="place_summaries" if tables_exist(conn) else _NO_SUMMARIES)
    with conn.cursor() as cur:
        cur.execute(sql, {"hash": prompt_v6.PROMPT_HASH_THREAD, "sub": subreddits.HOME, "since": since,
                          "n": n, "keys": list(keys or [])})
        rows = cur.fetchall()
    conn.commit()
    return [Place(*r) for r in rows]


REASONS = ("new", "fresh", "prompt")


def due_reason(p, model, phash, x, force=False):
    """Why a qualifying place is due ('new', 'fresh', 'prompt'), 'parked' for
    one that failed MAX_ATTEMPTS times, or None when its summary is current."""
    if p.attempts >= MAX_ATTEMPTS:
        return "parked"
    if not p.has_summary:
        return "new"
    if p.model != model or p.prompt_hash != phash:
        return "prompt"
    if p.fresh >= x:
        return "fresh"
    return "forced" if force else None


def due(places, model, phash, x, force=False):
    """[(place, reason)] for the places to write, first places with no
    summary, then the ones with most new discussion, then prompt changes,
    the busiest first within each."""
    order = {"new": 0, "fresh": 1, "forced": 1, "prompt": 2}
    out = [(p, r) for p in places for r in [due_reason(p, model, phash, x, force)] if r in order]
    return sorted(out, key=lambda pr: (order[pr[1]], -pr[0].fresh if pr[1] == "fresh" else 0, -pr[0].n, pr[0].key))


# ---------------------------------------------------------------- input
@dataclasses.dataclass
class Comment:
    id: str
    created: dt.datetime
    title: str
    body: str
    chars: int                        # body + title, when only sizes were read
    names: list = dataclasses.field(default_factory=list)
    reads: list = dataclasses.field(default_factory=list)   # (opinion, level, avoid) of its opinions
    status: str = None                # 'closed' | 'moved'

    @property
    def opinionated(self):
        return bool(self.reads)

    def label(self):
        """How v6 read this comment's view of the place. An avoid outranks
        everything (a warning is never a recommendation), a stated opinion
        outranks a bare endorse, and of two stated levels the stronger one."""
        if any(a for _, _, a in self.reads):
            return "warns against it"
        stated = [lv for op, lv, _ in self.reads if op == "stated"]
        if stated:
            levels = [lv for lv in stated if lv is not None]
            if not levels:
                return "opinion"
            lv = sorted(levels, key=lambda v: (-abs(v), v))[0]
            return {2: "strong praise", 1: "praise", 0: "mixed", -1: "criticism", -2: "harsh criticism"}[lv]
        return "recommends"


TALLY = {"strong praise": "praise", "praise": "praise", "criticism": "criticism",
         "harsh criticism": "criticism", "warns against it": "criticism", "mixed": "mixed",
         "recommends": "recommends", "opinion": "other"}


@dataclasses.dataclass
class Input:
    key: str
    name: str
    comments: list            # sent as opinions, newest first
    reports: list             # sent as status reports
    recent: int               # opinionated comments in the window
    available: int            # opinionated comments at all
    dropped: int = 0          # cut by the token budget (oldest)

    @property
    def chars(self):
        return sum(c.chars for c in self.comments + self.reports)


_INPUT_ROWS = """
select coalesce(a.resolved_key, m.entity_key), m.comment_id, c.created_utc,
       {text}, length(c.body) + length(t.title), m.restaurant_raw,
       m.opinion in ('endorse', 'stated') and m.timeframe is distinct from 'past',
       m.opinion, m.overall_level, coalesce(m.avoid, false),
       case when m.status in ('closed', 'moved') and c.created_utc > %(since)s then m.status end
from live_mentions m
join comments c on c.id = m.comment_id
join threads t on t.id = c.thread_id
left join entity_alias a on a.entity_key = m.entity_key
where m.entity_key in (select entity_key from entity_alias where resolved_key = any(%(keys)s)
                       union all select unnest(%(keys)s::text[]))
  and m.prompt_hash = %(hash)s
  and c.subreddit = %(sub)s
  and not coalesce(c.was_deleted_later, false)
  and c.author is distinct from 'AutoModerator'
  and ((m.opinion in ('endorse', 'stated') and m.timeframe is distinct from 'past')
       or (m.status in ('closed', 'moved') and c.created_utc > %(since)s))
"""


def read_inputs(conn, keys, since, text=True, budget_tokens=None):
    """{key: Input} for these places, chosen as the module docstring says.
    text=False reads only sizes, for dry runs over every place."""
    keys = list(keys)
    if not keys:
        return {}
    if budget_tokens is None:
        budget_tokens = setting(MAX_INPUT_TOKENS_ENV, int)
    cols = "t.title, c.body" if text else "null::text, null::text"
    with conn.cursor() as cur:
        cur.execute(_INPUT_ROWS.format(text=cols),
                    {"keys": keys, "hash": prompt_v6.PROMPT_HASH_THREAD, "sub": subreddits.HOME,
                     "since": since})
        rows = cur.fetchall()
    conn.commit()
    want = set(keys)
    per = collections.defaultdict(dict)
    for rkey, cid, created, title, body, chars, raw, op, opinion, level, avoid, status in rows:
        if rkey not in want:          # a typed key equal to a wanted one that resolves elsewhere
            continue
        c = per[rkey].get(cid)
        if c is None:
            c = per[rkey][cid] = Comment(cid, created, title, body, chars)
        if raw not in c.names:
            c.names.append(raw)
        if op:
            c.reads.append((opinion, level, avoid))
        if status and not c.status:
            c.status = status
    return {k: select(k, list(per[k].values()), since, budget_tokens=budget_tokens) for k in keys}


def select(key, comments, since, target=TARGET_COMMENTS, reports=STATUS_REPORTS,
           budget_tokens=DEFAULTS[MAX_INPUT_TOKENS_ENV]):
    """The comments a place's summary is written from (see the module docstring)."""
    newest_first = sorted(comments, key=lambda c: (c.created, c.id), reverse=True)
    ops = [c for c in newest_first if c.opinionated]
    recent = [c for c in ops if c.created > since]
    picked = recent if len(recent) >= target else ops[:target]
    kept, used = [], 0
    for c in picked:
        t = (c.chars + COMMENT_OVERHEAD_CHARS) / CHARS_PER_TOKEN_BUDGET
        if kept and used + t > budget_tokens:
            break
        kept.append(c)
        used += t
    sent = {c.id for c in kept}
    status = [c for c in newest_first if c.status and c.id not in sent][:reports]
    names = collections.Counter(n for c in kept + status for n in c.names)
    name = names.most_common(1)[0][0] if names else key
    return Input(key, name, kept, status, len(recent), len(ops), len(picked) - len(kept))


def _attr(v):
    """An attribute value: only the double quote would break it, and an
    entity in a name ("Ferrara&#x27;s") is noise to the model."""
    return str(v).replace('"', "'")


def render(inp, today):
    """The user message: today's date, the place, the comments and the status reports."""
    tally = collections.Counter(TALLY[c.label()] for c in inp.comments)
    out = [f"<today>{today:%Y-%m-%d}</today>", f"<place>{inp.name}</place>",
           f'<comments count="{len(inp.comments)}" praise="{tally["praise"]}" '
           f'criticism="{tally["criticism"]}" mixed="{tally["mixed"]}" '
           f'recommends="{tally["recommends"]}" other="{tally["other"]}">']
    for c in inp.comments:
        status = f' reports="{c.status}"' if c.status else ""
        out += [f'<comment date="{c.created:%Y-%m-%d}" names="{_attr("; ".join(c.names))}" '
                f'read_as="{c.label()}"{status}>',
                f"<thread_title>{c.title or ''}</thread_title>", (c.body or "").strip(), "</comment>"]
    out.append("</comments>")
    if inp.reports:
        out.append(f'<status_reports count="{len(inp.reports)}">')
        for c in inp.reports:
            out += [f'<comment date="{c.created:%Y-%m-%d}" names="{_attr("; ".join(c.names))}" '
                    f'reports="{c.status}">',
                    f"<thread_title>{c.title or ''}</thread_title>", (c.body or "").strip(), "</comment>"]
        out.append("</status_reports>")
    return "\n".join(out)


def params(user, eff=None):
    return {"model": MODEL, "max_tokens": MAX_TOKENS,
            "system": [{"type": "text", "text": SYSTEM_PROMPT}],
            "messages": [{"role": "user", "content": user}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": eff or effort(),
                              "format": {"type": "json_schema", "schema": SCHEMA}}}


def worst(user):
    return AV.worst_case(SYSTEM_PROMPT, user, batch=False, max_tokens=MAX_TOKENS, model=MODEL)


def estimate_chars(chars, comments):
    """A typical call's cost for a dry run, from the input's size alone."""
    tin = (len(SYSTEM_PROMPT) + chars + comments * COMMENT_OVERHEAD_CHARS) / CHARS_PER_TOKEN_EST
    p = AV._rates(tin, MODEL)
    return tin * p["in"] + EST_OUTPUT_TOKENS * p["out"]


_USER = re.compile(r"(?<![\w/])/?u/[A-Za-z0-9_-]{2,}")


def read_summary(message):
    """The summary in an answer, or AV.ItemError with the reason it can't be used."""
    obj = AV.answer_json(message, MAX_TOKENS)
    text = obj.get("summary") if isinstance(obj, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise AV.ItemError("empty_summary")
    text = " ".join(text.split())
    if _USER.search(text):
        raise AV.ItemError("names_user", text[:200])
    if len(text) > 1500:
        raise AV.ItemError("too_long", f"{len(text)} characters")
    return text


# ---------------------------------------------------------------- writes
def _ledger(cur, key, phash, outcome, cost, usage=None):
    cur.execute("""insert into summary_calls (resolved_key, model, prompt_hash, outcome, cost_usd, usage)
                   values (%s, %s, %s, %s, %s, %s)""",
                (key, MODEL, phash, outcome, round(cost, 8), json.dumps(usage) if usage is not None else None))


def store(conn, place, inp, summary, usage, cost, phash):
    """Write a summary and its call in one transaction. The watermark is the
    newest qualifying comment when the place was read."""
    with conn.cursor() as cur:
        _ledger(cur, place.key, phash, "written", cost, usage)
        cur.execute("""
            insert into place_summaries (resolved_key, summary, model, prompt_hash, mention_count,
                                         last_mention_at, input_comments, input_chars, written_at,
                                         cost_usd, usage, attempts, error, failed_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, now(), %s, %s, 0, null, null, now())
            on conflict (resolved_key) do update set
              summary = excluded.summary, model = excluded.model, prompt_hash = excluded.prompt_hash,
              mention_count = excluded.mention_count, last_mention_at = excluded.last_mention_at,
              input_comments = excluded.input_comments, input_chars = excluded.input_chars,
              written_at = now(), cost_usd = excluded.cost_usd, usage = excluded.usage,
              attempts = 0, error = null, failed_at = null, updated_at = now()""",
                    (place.key, summary, MODEL, phash, place.n, place.newest,
                     len(inp.comments) + len(inp.reports), inp.chars, round(cost, 8), json.dumps(usage)))
    conn.commit()


def record_failure(conn, key, err, usage, cost, phash):
    """An answer that could not be used (err, an AV.ItemError): its cost goes
    in the ledger under its code, the attempt on the place, whose last good
    summary, if any, stays."""
    with conn.cursor() as cur:
        _ledger(cur, key, phash, err.code, cost, usage)
        cur.execute("""
            insert into place_summaries (resolved_key, attempts, error, failed_at, updated_at)
            values (%s, 1, %s, now(), now())
            on conflict (resolved_key) do update set
              attempts = place_summaries.attempts + 1, error = excluded.error,
              failed_at = now(), updated_at = now()
            returning attempts""", (key, str(err)[:500]))
        attempts = cur.fetchone()[0]
    conn.commit()
    return attempts


def record_unseen(conn, key, amounts, phash):
    """Attempts that may have been billed with no answer, at their worst case."""
    if not amounts:
        return
    with conn.cursor() as cur:
        for a in amounts:
            _ledger(cur, key, phash, "unseen", a)
    conn.commit()


def retry_errors(conn):
    with conn.cursor() as cur:
        cur.execute("update place_summaries set attempts = 0 where attempts >= %s", (MAX_ATTEMPTS,))
        n = cur.rowcount
    conn.commit()
    return n


# ---------------------------------------------------------------- run
class Stats:
    def __init__(self):
        self.written = self.failed = self.parked = self.empty = self.refused = 0
        self.stop = None          # why the pass ended early, if it did
        self.results = []         # (place, input, user, summary or None, cost, error) for --review

    def line(self, budget=None):
        out = f"{self.written} written, {self.failed} failed ({self.parked} parked), {self.empty} with nothing to send"
        if budget is not None:
            out += f", ${budget.spent:.4f}"
        return out + (f" -- stopped: {self.stop}" if self.stop else "")


@dataclasses.dataclass
class Request:
    place: Place
    inp: Input
    user: str
    worst: float


def _work(cl, budget, req, stop, attempts, sleep, log):
    """The network half, on a worker thread: reserve, call, settle. Touches no
    database. Returns (status, message or error, cost, unseen charges)."""
    if stop.is_set():
        return "skipped", None, 0.0, []
    w = req.worst
    if not budget.reserve(w):
        stop.set()
        return "capped", None, 0.0, []
    held, unseen = [True], []

    def again():
        # The attempt that timed out may have been billed: charge it its
        # worst case and hold a fresh one for the retry.
        budget.settle(w, w)
        unseen.append(w)
        held[0] = budget.reserve(w)
        return held[0]
    try:
        msg = AV.call(cl, params(req.user), attempts=attempts, sleep=sleep, log=log, retry_ok=again)
    except AV.CapReached:
        stop.set()
        return "capped", None, 0.0, unseen
    except (AV.FatalAPIError, AV.TransientAPIError) as e:
        if held[0]:
            billed = w if getattr(e, "maybe_billed", False) else 0.0
            budget.settle(w, billed)
            if billed:
                unseen.append(billed)
        stop.set()
        return "error", e, 0.0, unseen
    c = AV.cost(AV.usage_of(msg), batch=False, model=MODEL)
    budget.settle(w, c)
    if c > w + TRIP_EPS:
        budget.trip(f"{req.place.key} cost ${c:.6f}, over the ${w:.6f} held for it")
        stop.set()
    return "answered", msg, c, unseen


def _trip(budget, why, log):
    budget.trip(why)
    log(f"\n!!!!!!!! SUMMARY SPEND TRIPWIRE: {why}. Nothing more is sent; summaries stay off until "
        "a person has looked. !!!!!!!!\n")
    raise EV.Tripped(why)


def run(conn, cl, budget, todo, workers=4, attempts=ATTEMPTS, deadline=None, sleep=None, log=print,
        keep=False, now=None, since=None):
    """Write summaries for todo, [(place, reason)] in order, until it is done,
    the cap or the ceiling refuses a call, the API stops the pass, or the
    deadline (time.monotonic()) passes. Places are read and sent a page at a
    time; every write happens here, on the caller's connection, as answers
    arrive. keep=True keeps each request and answer in stats.results."""
    stats = Stats()
    phash = prompt_hash()
    if now is None or since is None:
        now, since = _since(conn)
    stop = threading.Event()
    page = max(1, workers * 2)
    halt = None
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers))
    try:
        for start in range(0, len(todo), page):
            if deadline is not None and time.monotonic() >= deadline:
                stats.stop = stats.stop or "out of time for this pass"
                break
            chunk = [p for p, _ in todo[start:start + page]]
            inputs = read_inputs(conn, [p.key for p in chunk], since)
            reqs = []
            for p in chunk:
                inp = inputs[p.key]
                if not inp.comments and not inp.reports:
                    stats.empty += 1
                    continue
                user = render(inp, now)
                reqs.append(Request(p, inp, user, worst(user)))
            futures = {pool.submit(_work, cl, budget, r, stop, attempts, sleep, log): r for r in reqs}
            for fut in concurrent.futures.as_completed(futures):
                req = futures[fut]
                status, res, c, unseen = fut.result()
                record_unseen(conn, req.place.key, unseen, phash)
                if status == "capped":
                    stats.refused += 1
                elif status == "error":
                    halt = halt or res
                    if keep:
                        stats.results.append((req, None, 0.0, f"{type(res).__name__}: {res}"))
                elif status == "answered":
                    usage = AV.usage_of(res)
                    try:
                        summary = read_summary(res)
                    except AV.ItemError as e:
                        n = record_failure(conn, req.place.key, e, usage, c, phash)
                        stats.failed += 1
                        stats.parked += n >= MAX_ATTEMPTS
                        log(f"  {req.place.key}: {e}" + (" -- parked" if n >= MAX_ATTEMPTS else ""))
                        if keep:
                            stats.results.append((req, None, c, str(e)))
                    else:
                        store(conn, req.place, req.inp, summary, usage, c, phash)
                        stats.written += 1
                        if keep:
                            stats.results.append((req, summary, c, None))
            if budget.tripped:
                _trip(budget, budget.tripped, log)
            recorded, _ = budget.ceiling.read()
            if recorded > budget.ceiling.allowance() + TRIP_EPS:
                _trip(budget, f"recorded summary spend ${recorded:.4f} is over the "
                              f"${budget.ceiling.limit:.2f} ceiling", log)
            if halt is not None:
                stats.stop = f"{type(halt).__name__}: {halt}"
                break
            if stats.refused:
                which = budget.refused_by or "cap"
                stats.stop = (f"the {'lifetime ceiling' if which == 'ceiling' else 'per-pass cap'} "
                              f"(${budget.ceiling.limit if which == 'ceiling' else budget.max:.2f}) "
                              "has no room for the next call")
                log(f"\n!!!!!!!! SUMMARIES STOPPED: {stats.stop}; ${budget.spent:.4f} spent this pass. "
                    + ("Raise SUMMARY_CEILING_USD to write more. " if which == "ceiling" else "")
                    + "!!!!!!!!\n")
                break
    except BaseException:
        stop.set()
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    if isinstance(halt, AV.FatalAPIError):
        log(f"  SUMMARIES STOPPED -- the API rejected the request itself: {halt}")
    elif halt is not None:
        log(f"  summaries stopped early, will retry next pass: {halt}")
    return stats


# ---------------------------------------------------------------- the poller's step
def poll_once(conn, limit, max_usd=None, ceiling_usd=None, workers=4, connect=None, cl=None, log=print,
              deadline=None, sleep=None):
    """One chores-pass step: write what is due, up to `limit` places, under
    the pass's cap and the lifetime ceiling. Never raises for a missing key
    or missing tables; a spend tripwire is raised (EV.Tripped) so the
    poller can switch summaries off."""
    if not api_key() and cl is None:
        log(f"  summaries: no {KEY_VAR}; skipping")
        return None
    if not tables_exist(conn):
        log("  summaries: tables missing -- apply summary_schema.sql; skipping")
        return None
    if not try_lock(conn):
        log("  summaries: another summary run holds the lock; skipping this pass")
        return None
    try:
        n, x = setting(MIN_MENTIONS_ENV, int), setting(NEW_MENTIONS_ENV, int)
        now, since = _since(conn)
        todo = due(qualifying(conn, n, since=since), MODEL, prompt_hash(), x)[:limit]
        if not todo:
            return Stats()
        budget = make_budget(max_usd if max_usd is not None else setting(RUN_ENV),
                             ceiling_usd if ceiling_usd is not None else setting(CEILING_ENV), connect)
        try:
            cl = cl or client(api_key(), timeout=TIMEOUT)
            stats = run(conn, cl, budget, todo, workers=workers, attempts=ATTEMPTS,
                        deadline=deadline if deadline is not None else time.monotonic() + DEADLINE,
                        sleep=sleep, log=log, now=now, since=since)
        finally:
            budget.ceiling.close()
        if stats.written or stats.failed or stats.stop:
            log(f"  summaries: {stats.line(budget)} ({len(todo)} due this pass)")
        return stats
    finally:
        try:
            unlock(conn)
        except Exception:
            pass        # a dead connection has already dropped the lock


# ---------------------------------------------------------------- read-only reports
def status(conn, log=print):
    with conn.cursor() as cur:
        cur.execute("""select count(*) filter (where summary is not null),
                              count(*) filter (where summary is not null and prompt_hash = %s and model = %s),
                              count(*) filter (where attempts > 0 and attempts < %s),
                              count(*) filter (where attempts >= %s),
                              max(written_at)
                       from place_summaries""", (prompt_hash(), MODEL, MAX_ATTEMPTS, MAX_ATTEMPTS))
        written, current, failing, parked, last = cur.fetchone()
        cur.execute("""select coalesce(sum(cost_usd), 0), count(*),
                              coalesce(sum(cost_usd) filter (where called_at > now() - interval '1 day'), 0),
                              coalesce(sum(cost_usd) filter (where called_at > now() - interval '30 days'), 0)
                       from summary_calls""")
        total, calls, day, month = cur.fetchone()
        cur.execute("""select outcome, count(*) from summary_calls where outcome <> 'written'
                       group by 1 order by 2 desc""")
        outcomes = cur.fetchall()
        cur.execute("""select resolved_key, attempts, error from place_summaries where attempts > 0
                       order by attempts desc, failed_at desc limit 10""")
        errors = cur.fetchall()
    conn.commit()
    log(f"model {MODEL}, prompt {prompt_hash()}, effort {effort()}")
    log(f"summaries: {written:,} written ({current:,} current), {failing} failing, {parked} parked; "
        f"last written {last}")
    log(f"spend: ${float(total):.4f} over {calls:,} calls (${float(day):.4f} in 24h, ${float(month):.4f} in 30d); "
        f"ceiling ${setting(CEILING_ENV):.2f}")
    for o, k in outcomes:
        log(f"  {k:6,}  {o}")
    for key, a, err in errors:
        log(f"  {key}: {a} attempt(s), {err}")


def _pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else 0


def dry_run(conn, n, x, keys=None, limit=None, force=False, print_input=False, log=print):
    """What qualifies and is due, the inputs' sizes, and what writing them
    would cost. Reads only."""
    now, since = _since(conn)
    phash = prompt_hash()
    places = qualifying(conn, n, keys=keys, since=since)
    reasons = collections.Counter(due_reason(p, MODEL, phash, x, force) or "current" for p in places)
    log(f"{len(places):,} places qualify (n={n} comments in {WINDOW_DAYS}d, thread-mode v6 "
        f"{prompt_v6.PROMPT_HASH_THREAD}); prompt {phash}, x={x}")
    if keys is not None:
        missing = sorted(set(keys) - {p.key for p in places})
        if missing:
            log(f"  not qualifying: {', '.join(missing)}")
    log("  " + ", ".join(f"{k} {v:,}" for k, v in reasons.most_common()))
    todo = due(places, MODEL, phash, x, force)[:limit] if limit else due(places, MODEL, phash, x, force)
    inputs = read_inputs(conn, [p.key for p, _ in todo], since, text=print_input)
    sizes = [(p, inputs[p.key]) for p, _ in todo]
    sendable = [(p, i) for p, i in sizes if i.comments or i.reports]
    comments = [len(i.comments) for _, i in sendable]
    chars = [i.chars for _, i in sendable]
    log(f"due now: {len(todo):,}, of which {len(sizes) - len(sendable)} have nothing to send")
    if sendable:
        log(f"  comments sent: median {_pct(comments, .5)}, p90 {_pct(comments, .9)}, "
            f"p99 {_pct(comments, .99)}, max {max(comments)}")
        log(f"  characters: median {_pct(chars, .5):,}, p90 {_pct(chars, .9):,}, p99 {_pct(chars, .99):,}, "
            f"max {max(chars):,}, total {sum(chars):,}")
        log(f"  topped up from older comments (<{TARGET_COMMENTS} in the year): "
            f"{sum(1 for _, i in sendable if i.recent < TARGET_COMMENTS):,}; with status reports: "
            f"{sum(1 for _, i in sendable if i.reports):,}; cut by the token budget: "
            f"{sum(1 for _, i in sendable if i.dropped):,}")
        line = AV.PRICE_TABLE[MODEL]["long_above"]
        over = [p.key for p, i in sendable
                if (len(SYSTEM_PROMPT) + i.chars + (len(i.comments) + len(i.reports)) * COMMENT_OVERHEAD_CHARS)
                / CHARS_PER_TOKEN_EST > line]
        if over:
            log(f"  over the {line:,}-token line, billed at the long-prompt rate (estimated): "
                f"{len(over)} ({', '.join(over[:5])}{', ...' if len(over) > 5 else ''})")
        est = sum(estimate_chars(i.chars, len(i.comments) + len(i.reports)) for _, i in sendable)
        log(f"  estimated cost ${est:.2f} (at {CHARS_PER_TOKEN_EST} chars/token in, "
            f"~{EST_OUTPUT_TOKENS} tokens out a call; Haiku 5.5 ${AV.PRICE_TABLE[MODEL]['base']['in'] * 1e6:.2f}"
            f"/${AV.PRICE_TABLE[MODEL]['base']['out'] * 1e6:.2f} per MTok)")
        big = sorted(sendable, key=lambda pi: -pi[1].chars)[:5]
        for p, i in big:
            log(f"    {p.key}: {p.n} comments in the year, {len(i.comments)} sent, {i.chars:,} chars")
    if print_input:
        for p, i in sendable:
            log(f"\n===== {p.key} ({p.n} qualifying) =====\n{render(i, now)}")
    return todo, inputs


# ---------------------------------------------------------------- the quality check
def pick_sample(places, size=50, seed=20261103):
    """A mixed sample of places to read summaries against: the busiest, the
    middle, the ones that only just qualify, the most complained about, and
    the ones with reports that they closed or moved. [(place, why)]."""
    rng = random.Random(seed)
    pool = sorted((p for p in places if p.opinions), key=lambda p: p.key)
    taken, out = set(), []

    def take(cands, k, why):
        for p in cands:
            if len([1 for _, w in out if w == why]) >= k:
                break
            if p.key not in taken:
                taken.add(p.key)
                out.append((p, why))

    k = {"busiest": round(size * .2), "complaints": round(size * .24), "closed": round(size * .1),
         "just qualifying": round(size * .2)}
    take(sorted(pool, key=lambda p: -p.n), k["busiest"], "busiest")
    # Most complained about by share, among places with enough criticism
    # that leaving it out would be a real miss.
    worst = [p for p in pool if p.negative >= 8]
    take(sorted(worst, key=lambda p: (-p.negative / p.opinions, -p.negative)), k["complaints"], "complaints")
    take(sorted((p for p in pool if p.closed), key=lambda p: -p.closed), k["closed"], "closed or moved")
    low = min((p.n for p in pool), default=0)
    small = [p for p in pool if p.n <= low + 2]
    rng.shuffle(small)
    take(small, k["just qualifying"], "just qualifying")
    ns = sorted(p.n for p in pool)
    lo, hi = _pct(ns, .4), _pct(ns, .9)
    middle = [p for p in pool if lo <= p.n <= hi]
    rng.shuffle(middle)
    take(middle, size - len(out), "middle")
    return out[:size]


def write_review(path, results, header, log=print):
    """Each summary next to the exact text it was written from, as Markdown."""
    lines = ["# Place summaries: quality check", "", *header, "",
             "For each place: is anything in the summary not in its comments, and is any complaint "
             "that recurs in them missing or softened? Are closures right?", ""]
    for i, (req, why, summary, cost, error) in enumerate(results, 1):
        p, inp = req.place, req.inp
        lines += [f"## {i}. {inp.name} (`{p.key}`)", "",
                  f"Sampled as: {why}. {p.n} comments in the year mention it; {inp.recent} give an opinion "
                  f"({p.negative} critical); {len(inp.comments)} sent"
                  + (f" ({inp.dropped} older cut by the budget)" if inp.dropped else "")
                  + (f", plus {len(inp.reports)} status report(s)" if inp.reports else "")
                  + f"; {inp.chars:,} characters"
                  + (f"; ${cost:.4f}" if cost else "") + ".", ""]
        if summary:
            lines += [f"> {summary}", ""]
        else:
            lines += [f"**No summary**: {error or 'not written'}", ""]
        lines += ["<details><summary>What the model was given</summary>", "", "~~~~text", req.user,
                  "~~~~", "", "</details>", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    log(f"wrote {path} ({len(results)} places)")


def _sample_or_keys(conn, args, n, since):
    keys = args.keys
    places = qualifying(conn, n, keys=keys, since=since)
    if args.sample:
        chosen = pick_sample(places, args.sample)
    else:
        found = {p.key: p for p in places}
        chosen = [(found[k], "asked for") for k in keys if k in found]
        missing = [k for k in keys if k not in found]
        if missing:
            print(f"not qualifying, skipped: {', '.join(missing)}")
    return chosen


def review_only(conn, args, n, log=print):
    """The review file from stored summaries and the inputs as they would be
    chosen now (which may differ from what a summary was written from if
    comments have come in since). Reads only."""
    now, since = _since(conn)
    chosen = _sample_or_keys(conn, args, n, since)
    inputs = read_inputs(conn, [p.key for p, _ in chosen], since)
    stored = {}
    if tables_exist(conn):
        with conn.cursor() as cur:
            cur.execute("""select resolved_key, summary, cost_usd, error from place_summaries
                           where resolved_key = any(%s)""", ([p.key for p, _ in chosen],))
            stored = {r[0]: r[1:] for r in cur.fetchall()}
        conn.commit()
    results = []
    for p, why in chosen:
        inp = inputs[p.key]
        s, c, err = stored.get(p.key, (None, None, None))
        results.append((Request(p, inp, render(inp, now), 0.0), why, s, float(c or 0), err))
    write_review(args.review, results,
                 [f"From stored summaries, inputs as chosen at {now:%Y-%m-%d %H:%M} UTC; "
                  f"model {MODEL}, prompt {prompt_hash()}."], log)


# ---------------------------------------------------------------- main
def _parse_keys(s):
    return [k.strip() for k in s.split(",") if k.strip()] if s else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true", help="what is written and what it cost; read-only")
    ap.add_argument("--dry-run", action="store_true",
                    help="what qualifies and is due, input sizes and estimated cost; read-only")
    ap.add_argument("--print-input", action="store_true", help="with --dry-run: print each due place's message")
    ap.add_argument("--keys", type=_parse_keys, help="only these resolved keys, comma-separated")
    ap.add_argument("--sample", type=int, help="the quality check: a mixed sample of this many places")
    ap.add_argument("--review", help="write each summary beside its input to this Markdown file")
    ap.add_argument("--review-only", action="store_true",
                    help="with --review: from stored summaries, no API calls; read-only")
    ap.add_argument("--force", action="store_true", help="with --keys: rewrite even a current summary")
    ap.add_argument("--limit", type=int, help="at most this many places")
    ap.add_argument("--max-usd", type=float, help=f"cap on this run (default ${RUN_ENV} or $1)")
    ap.add_argument("--ceiling-usd", type=float,
                    help=f"lifetime ceiling on all summary spend (default ${CEILING_ENV} or $10)")
    ap.add_argument("--workers", type=int, default=4, help="calls at once (default 4)")
    ap.add_argument("--retry-errors", action="store_true", help="unpark places that failed too often, then run")
    args = ap.parse_args(argv)

    n, x = setting(MIN_MENTIONS_ENV, int), setting(NEW_MENTIONS_ENV, int)
    effort()
    if args.review_only and not args.review:
        raise SystemExit("--review-only needs --review FILE")
    if (args.review or args.review_only) and not (args.sample or args.keys):
        raise SystemExit("--review needs --sample N or --keys")
    if args.force and not (args.keys or args.sample):
        raise SystemExit("--force needs --keys (or --sample): it rewrites current summaries")

    conn = db.connect()
    read_only = args.status or args.dry_run or args.review_only
    if read_only:
        conn.set_session(readonly=True)
    # A dry run works before the schema is applied (every place reads as
    # never summarized), so the first run can be priced first.
    if not (args.dry_run or args.review_only) and not tables_exist(conn):
        raise SystemExit("place_summaries is missing: apply summary_schema.sql first")
    if args.status:
        return status(conn)
    if args.review_only:
        return review_only(conn, args, n)
    if args.dry_run:
        if args.sample:
            _, since = _since(conn)
            chosen = _sample_or_keys(conn, args, n, since)
            for p, why in chosen:
                print(f"  {why:16} {p.key} ({p.n} comments, {p.opinions} opinions, {p.negative} critical, "
                      f"{p.closed} closed/moved)")
            args.keys = [p.key for p, _ in chosen]
            args.force = True
        dry_run(conn, n, x, keys=args.keys, limit=args.limit, force=args.force, print_input=args.print_input)
        return

    key = api_key()
    if not key:
        raise SystemExit(f"{KEY_VAR} is not set")
    AV.check_prices(MODEL)
    max_usd = args.max_usd if args.max_usd is not None else setting(RUN_ENV)
    ceiling = args.ceiling_usd if args.ceiling_usd is not None else setting(CEILING_ENV)
    if not try_lock(conn):
        raise SystemExit("another summary run (or the poller's step) holds the lock; try again shortly")
    try:
        if args.retry_errors:
            print(f"unparked {retry_errors(conn)} place(s)")
        now, since = _since(conn)
        if args.sample or args.keys:
            chosen = _sample_or_keys(conn, args, n, since)
            why = {p.key: w for p, w in chosen}
            force = args.force or bool(args.sample)
            todo = due([p for p, _ in chosen], MODEL, prompt_hash(), x, force)
        else:
            why = {}
            todo = due(qualifying(conn, n, since=since), MODEL, prompt_hash(), x)
        todo = todo[:args.limit] if args.limit else todo
        print(f"{len(todo):,} place(s) to write, ${max_usd:.2f} cap, ${ceiling:.2f} ceiling, "
              f"{MODEL} at effort {effort()}, prompt {prompt_hash()}")
        budget = make_budget(max_usd, ceiling)
        print(f"  recorded summary spend so far: ${budget.ceiling.start:.4f}")
        try:
            stats = run(conn, client(key), budget, todo, workers=args.workers, attempts=AV.ATTEMPTS,
                        keep=bool(args.review), now=now, since=since)
        except EV.Tripped:
            return EV.TRIPPED
        finally:
            budget.ceiling.close()
        print(f"done: {stats.line(budget)}")
        if args.review:
            done = [(req, why.get(req.place.key, "due"), s, c, e) for req, s, c, e in stats.results]
            write_review(args.review, done,
                         [f"Written {now:%Y-%m-%d %H:%M} UTC with {MODEL} at effort {effort()}, prompt "
                          f"{prompt_hash()}; ${budget.spent:.4f} spent."])
    finally:
        unlock(conn)


if __name__ == "__main__":
    sys.exit(main())
