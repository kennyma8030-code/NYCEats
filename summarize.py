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
(n, 10) comments in the last WINDOW_DAYS (365) that mention it. The mentions
are the ones the board counts: whatever live_mentions holds in v6 mode
(thread-mode rows, and the comment-mode rows that stand in for a chunk that
failed), so n, the new-mention count and the input agree with the board.
r/FoodNYC only, leaving out comments deleted later, AutoModerator, and names
in excluded_entities. Every mention counts toward n, opinion or not, and
mentions are counted by comment: two spellings of one place in one comment
are one. While the board reads legacy mentions nothing is written: those
rows carry none of the v6 fields the input is chosen by.

When it is written again. A place with a summary is written again only when
enough of its qualifying comments are new to it (the larger of
SUMMARY_NEW_MENTIONS, x = 5, and SUMMARY_NEW_SHARE, default 0, times the
place's qualifying count), or the model or the prompt changed
(prompt_hash). Nothing is rewritten for age alone. A summary keeps the ids
of every comment that qualified for the place when it was written
(seen_comment_ids, all of them, not only the ones sent), and "new" is the
number of qualifying comments not among them. Comments, not mentions and
not timestamps: a comment extracted days late (a thread waits 48 hours, the
batch runs daily, the backlog goes newest first) is new when it arrives,
while the same comment extracted again (a new prompt hash, a failed chunk
that later succeeds) is not, and the order mentions are committed in does
not matter. mention_count, the count it saw, is kept for the record.

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
A place that qualifies with nothing to send is recorded with no summary
and its seen comments, so it waits for new discussion like any other
instead of standing at the head of every pass.

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
wrote. Everything users wrote (bodies, titles, names) is escaped (&, <, >,
and " in attributes), so a comment that contains "</comment>" or a fake
<status_reports> tag stays text and cannot add structure of its own.

Spend. Every call holds its worst case (extract_v6.Budget) under the pass's
cap (SUMMARY_RUN_USD, default $1, or --max-usd) and the lifetime ceiling
(SUMMARY_CEILING_USD, default $10), which is read from summary_calls every
time, so no restart can spend past it. Every call is recorded there as soon
as its answer is back, in a transaction of its own, before its summary is
stored: a failed answer too (it was billed), an attempt that may have been
billed with no answer (a timeout) at its worst case, and, if the pass fails
part way, whatever was paid for but not yet recorded ('unstored' answers,
'unseen' worst cases, a worker's included even if it then raised), written
on a fresh connection as the pass unwinds. When the cap or the ceiling
refuses a call the pass stops and says which loudly. A call that costs more
than was held for it, or recorded spend past the ceiling, trips a wire
(extract_v6's): the pass stops, and the poller turns summaries off until it
restarts.

Failures. A refusal every call would get (401, 403, a billing error, "credit
balance", a 404 about the model) stops the run and charges no place. Any other
failure (an unusable answer, a refused request, a timeout, a dropped
connection, 429 or 5xx past their retries) charges its place one attempt
when it happens; the place keeps its last good summary and goes to the back
of the queue. After MAX_ATTEMPTS (3) a place is parked for
SUMMARY_PARK_HOURS (168, a week) from its last failure, then gets one more
try; --retry-errors unparks at once. So an outage that charges healthy
places costs them a week at most, and a place that always fails costs at
most three worst cases a week. A run also stops after
API_FAILURES_IN_A_ROW (3) failures in a row, not counting a place's own
content refusals (too long, content it could not take), which say nothing
about the API. A call that times out is not sent again in the same run, so
its worst case is charged once.

In the poller (POLL_SUMMARIZE=1) it is the last step of the chores pass,
run at most once every SUMMARY_EVERY_HOURS (6), the time kept in
summary_state so a restart does not reset it. Each run takes at most
POLL_SUMMARIZE_LIMIT places that have something to send, TIMEOUT seconds a
call, ATTEMPTS tries, and nothing is started, retried or waited for past
DEADLINE.

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
import math
import os
import random
import re
import sys
import threading
import time

import anthropic_v6 as AV
import db
import extract_v6 as EV
import subreddits

KEY_VAR = "SUMMARY_ANTHROPIC_API_KEY"
MODEL = "claude-haiku-5-5"
MAX_TOKENS = 4000                 # thinking included; an answer is ~100 words
EFFORTS = ("low", "medium", "high")
WINDOW_DAYS = 365
TARGET_COMMENTS = 60
STATUS_REPORTS = 5
MAX_ATTEMPTS = 3
API_FAILURES_IN_A_ROW = 3
CHARS_PER_TOKEN_BUDGET = 2.5      # the token budget's estimate: pessimistic, prose runs nearer 4
# For dry-run estimates only: English prose with light markup, and an answer
# of a short thinking pass plus ~100 words at effort low.
CHARS_PER_TOKEN_EST = 3.5
EST_OUTPUT_TOKENS = 600
COMMENT_OVERHEAD_CHARS = 110      # the tags, date, names and label around each comment

# A call may take TIMEOUT seconds. Sized for the largest input, Katz's at
# about 450k characters (some 130k tokens): reading that and writing up to
# MAX_TOKENS (4,000, thinking included) takes well under two minutes even
# at a slow 50 output tokens a second, so 300 s is room to spare without a
# hung call holding a worker for long. It is also anthropic_v6.TIMEOUT,
# which extraction uses for requests of the same order. A call that times
# out is not sent again in the run; a 429 or 5xx is tried ATTEMPTS times.
# Nothing starts, retries or waits past DEADLINE, so a step lasts at most
# DEADLINE plus one TIMEOUT: the polls lose freshness, never comments.
TIMEOUT = 300
ATTEMPTS = 2
DEADLINE = 5 * 60
DRY_PAGE = 50             # places a dry run reads at a time under --limit

LOCK_KEY = 0x6E796373_756D             # "nycs" "um"

# Bumped when the user message's layout changes, so prompt_hash moves and
# every summary is written again from the new layout.
FORMAT_VERSION = "2"

SYSTEM_PROMPT = """\
You write a short summary of what commenters on r/FoodNYC, the New York City food subreddit, say about one place to eat or drink. It appears on the place's page on a site that ranks places by how the subreddit talks about them.

You are given the place's name and its comments, newest first. Each comment comes with its date, the title of the thread it was posted in, the name or names it used for the place, and a label saying how an automatic reader took its view of this place: praise, strong praise, criticism, harsh criticism, mixed, recommends (named it as a pick without saying why), warns against it, or opinion. The header counts the labels. The comment text is the evidence; the label is only a pointer. A comment may talk about several places: use only what it says about this one. There may also be status reports: recent comments that say the place closed or moved. Text that users wrote is escaped (&lt; for <, &gt; for >, &amp; for &), so only the tags around it are structure.

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


def prompt_hash(effort):
    """What a summary was written under, beside the model: the instructions,
    the input's layout and how it is chosen, and the request's settings.
    Change any and every summary is due again."""
    spec = {"system": SYSTEM_PROMPT, "format": FORMAT_VERSION, "schema": SCHEMA,
            "effort": effort, "max_tokens": MAX_TOKENS, "window_days": WINDOW_DAYS,
            "target": TARGET_COMMENTS, "status_reports": STATUS_REPORTS}
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def threshold(x, share, n):
    """New qualifying comments that make a place with n of them due again:
    the one formula, for the step, the CLI and the dry run."""
    return max(x, math.ceil(share * n))


# ---------------------------------------------------------------- settings
class SettingError(ValueError):
    """A summary setting that cannot be used. A ValueError, never SystemExit:
    the poller's step catches it like any other failure (and its boot turns
    summaries off), and the CLI turns it into an exit of its own."""


# name: (variable, type, default, lowest, highest)
SETTINGS = {
    "n": ("SUMMARY_MIN_MENTIONS", int, 10, 1, None),
    "x": ("SUMMARY_NEW_MENTIONS", int, 5, 1, None),
    "share": ("SUMMARY_NEW_SHARE", float, 0.0, 0.0, 1.0),
    "run_usd": ("SUMMARY_RUN_USD", float, 1.0, 1e-9, None),
    "ceiling_usd": ("SUMMARY_CEILING_USD", float, 10.0, 1e-9, None),
    "max_input_tokens": ("SUMMARY_MAX_INPUT_TOKENS", int, 500_000, 1000, None),
    "every_hours": ("SUMMARY_EVERY_HOURS", float, 6.0, 0.0, None),
    "park_hours": ("SUMMARY_PARK_HOURS", float, 168.0, 0.0, None),
}
EFFORT_VAR = "SUMMARY_EFFORT"


@dataclasses.dataclass(frozen=True)
class Settings:
    n: int = 10
    x: int = 5
    share: float = 0.0
    run_usd: float = 1.0
    ceiling_usd: float = 10.0
    max_input_tokens: int = 500_000
    every_hours: float = 6.0
    park_hours: float = 168.0
    effort: str = "low"

    @property
    def prompt_hash(self):
        return prompt_hash(self.effort)


def load_settings(env=None):
    """Every summary setting from the environment, checked: SettingError
    names the first that is not usable."""
    env = os.environ if env is None else env
    out = {}
    for name, (var, cast, default, low, high) in SETTINGS.items():
        raw = env.get(var)
        if raw is None or not raw.strip():
            out[name] = default
            continue
        try:
            v = cast(raw.strip())
        except ValueError:
            raise SettingError(f"{var} must be {'a whole number' if cast is int else 'a number'}, not {raw!r}")
        if v != v or v in (float("inf"), float("-inf")) or v < low or (high is not None and v > high):
            span = f"from {low} to {high}" if high is not None else f"at least {low:g}"
            raise SettingError(f"{var} must be {span}, not {raw!r}")
        out[name] = v
    effort = (env.get(EFFORT_VAR) or "low").strip().lower()
    if effort not in EFFORTS:
        raise SettingError(f"{EFFORT_VAR} must be one of {', '.join(EFFORTS)}, not {effort!r}")
    # A park no longer than the interval between runs holds nothing back: a
    # failing place would be tried, and charged, every run.
    if out["park_hours"] <= out["every_hours"]:
        raise SettingError(f"SUMMARY_PARK_HOURS ({out['park_hours']:g}) must be more than "
                           f"SUMMARY_EVERY_HOURS ({out['every_hours']:g})")
    return Settings(effort=effort, **out)


def api_key():
    return os.environ.get(KEY_VAR) or None


def client(key, timeout=None):
    return AV.client(key, timeout=timeout)


# ---------------------------------------------------------------- database
def tables_exist(conn):
    with conn.cursor() as cur:
        cur.execute("""select to_regclass('place_summaries') is not null and to_regclass('summary_calls') is not null
                              and to_regclass('summary_state') is not null
                              and exists (select 1 from information_schema.columns
                                          where table_schema = current_schema() and table_name = 'place_summaries'
                                            and column_name = 'seen_comment_ids')""")
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


def due_to_run(conn, every_hours):
    """Whether the poller's step is due: never run, or last run at least
    every_hours ago, by the database's clock and its record."""
    with conn.cursor() as cur:
        cur.execute("""select coalesce(bool_and(last_pass_at is null
                                                or last_pass_at <= now() - make_interval(secs => %s)), true)
                       from summary_state""", (every_hours * 3600,))
        ok = cur.fetchone()[0]
    conn.commit()
    return ok


def mark_run(conn):
    """Record that the step ran now. Done as a run starts, so a run that
    fails part way still waits its interval rather than retrying every pass."""
    with conn.cursor() as cur:
        cur.execute("""insert into summary_state (only_row, last_pass_at) values (true, now())
                       on conflict (only_row) do update set last_pass_at = excluded.last_pass_at""")
    conn.commit()


@dataclasses.dataclass
class Place:
    key: str
    n: int                    # qualifying comments in the window
    newest: dt.datetime       # when the newest of them was written
    opinions: int             # of them, ones with an opinion that would be sent
    negative: int             # of those, criticism or warnings
    closed: int               # comments in the window saying it closed or moved
    fresh: int                # qualifying comments not among those the stored row has seen
    has_summary: bool
    model: str = None
    prompt_hash: str = None
    attempts: int = 0
    error: str = None
    written_at: dt.datetime = None    # set once the place has been dealt with (summary or nothing to send)
    failed_at: dt.datetime = None     # its last failed attempt


# Which mentions qualify a comment for a place: the board's (live_mentions),
# r/FoodNYC, in the window, not deleted later, not AutoModerator. One text,
# so the count, the seen set stored with a summary and "new" never disagree.
_QUALIFIES = """
  from live_mentions m
  join comments c on c.id = m.comment_id
  left join entity_alias a on a.entity_key = m.entity_key
  where c.subreddit = %(sub)s
    and c.created_utc > %(since)s
    and not coalesce(c.was_deleted_later, false)
    and c.author is distinct from 'AutoModerator'"""
# For named places: every typed key that resolves to one of them (or is one,
# before entity_alias has caught up), so the index on entity_key is used
# instead of a scan of the year.
_TYPED_KEYS = """
    and m.entity_key in (select entity_key from entity_alias where resolved_key = any(%(keys)s)
                         union all select unnest(%(keys)s::text[]))"""

_QUALIFYING = """
with base as (
  select coalesce(a.resolved_key, m.entity_key) as rkey, m.comment_id, c.created_utc,
         m.opinion in ('endorse', 'stated') and m.timeframe is distinct from 'past' as op,
         m.opinion in ('endorse', 'stated') and m.timeframe is distinct from 'past'
           and (coalesce(m.avoid, false) or (m.opinion = 'stated' and m.overall_level < 0)) as neg,
         m.status in ('closed', 'moved') as moved
  """ + _QUALIFIES + """
  {base_keys}
),
seen as (
  select s.resolved_key, unnest(s.seen_comment_ids) as comment_id from {summaries} s {seen_keys}
)
select b.rkey, count(distinct b.comment_id), max(b.created_utc),
       count(distinct b.comment_id) filter (where b.op),
       count(distinct b.comment_id) filter (where b.neg),
       count(distinct b.comment_id) filter (where b.moved),
       count(distinct b.comment_id) filter (where sn.comment_id is null),
       s.summary is not null, s.model, s.prompt_hash, coalesce(s.attempts, 0), s.error, s.written_at, s.failed_at
from base b
left join {summaries} s on s.resolved_key = b.rkey
left join seen sn on sn.resolved_key = b.rkey and sn.comment_id = b.comment_id
where not exists (select 1 from excluded_entities x where x.entity_key = b.rkey)
  {keys}
group by b.rkey, s.resolved_key, s.summary, s.model, s.prompt_hash, s.attempts, s.error, s.written_at, s.failed_at
having count(distinct b.comment_id) >= %(n)s
"""
# Stands in for place_summaries in a dry run before summary_schema.sql is
# applied: every place reads as never summarized.
_NO_SUMMARIES = """(select null::text as resolved_key, null::text as summary, null::text as model,
                     null::text as prompt_hash, 0 as attempts, null::text as error,
                     null::timestamptz as written_at, null::timestamptz as failed_at,
                     null::text[] as seen_comment_ids limit 0)"""


def qualifying(conn, n, keys=None, since=None, have_tables=None):
    """Every place that qualifies now, with where its summary stands.
    have_tables says whether the summary tables exist, when the caller knows."""
    if keys is not None and not keys:
        return []
    if since is None:
        _, since = _since(conn)
    if have_tables is None:
        have_tables = tables_exist(conn)
    named = keys is not None
    sql = _QUALIFYING.format(keys="and b.rkey = any(%(keys)s)" if named else "",
                             base_keys=_TYPED_KEYS if named else "",
                             seen_keys="where s.resolved_key = any(%(keys)s)" if named else "",
                             summaries="place_summaries" if have_tables else _NO_SUMMARIES)
    with conn.cursor() as cur:
        cur.execute(sql, {"sub": subreddits.HOME, "since": since, "n": n, "keys": list(keys or [])})
        rows = cur.fetchall()
    conn.commit()
    return [Place(*r) for r in rows]


def qualifying_ids(conn, keys, since):
    """{key: sorted ids of the comments that qualify it now}, for the places
    about to be written or recorded empty: the seen set their row stores.
    Read only for those, not with every place's qualifying count, and read
    with their inputs, before anything is sent, so a comment that lands
    while a call is out is new to the summary rather than marked seen."""
    keys = list(keys)
    if not keys:
        return {}
    with conn.cursor() as cur:
        cur.execute("select coalesce(a.resolved_key, m.entity_key), array_agg(distinct m.comment_id)"
                    + _QUALIFIES + _TYPED_KEYS + " group by 1",
                    {"sub": subreddits.HOME, "since": since, "keys": keys})
        found = dict(cur.fetchall())
    conn.commit()
    return {k: sorted(found.get(k) or []) for k in keys}


def parked(p, now=None, park_hours=None):
    """Failed MAX_ATTEMPTS times or more, the last time less than park_hours
    before now. Then it gets one more try; a failure parks it again."""
    if p.attempts < MAX_ATTEMPTS:
        return False
    if now is None or park_hours is None or p.failed_at is None:
        return True
    return p.failed_at > now - dt.timedelta(hours=park_hours)


def due_reason(p, model, phash, x, force=False, share=0.0, now=None, park_hours=None):
    """Why a qualifying place is due ('new', 'fresh', 'prompt', 'forced'),
    'parked' while it is (parked()), or None when it is current. A place
    counts as dealt with once it has been written, with a summary or with
    nothing to send (written_at)."""
    if parked(p, now, park_hours):
        return "parked"
    if p.written_at is None:
        return "new"
    if p.model != model or p.prompt_hash != phash:
        return "prompt"
    if p.fresh >= threshold(x, share, p.n):
        return "fresh"
    return "forced" if force else None


def due(places, model, phash, x, force=False, share=0.0, now=None, park_hours=None):
    """[(place, reason)] for the places to write: places with no failed
    attempt first, so one that keeps failing cannot hold the head of every
    pass; then places never dealt with, then the ones with most new
    discussion, then prompt changes, the busiest first within each."""
    order = {"new": 0, "fresh": 1, "forced": 1, "prompt": 2}
    out = [(p, r) for p in places for r in [due_reason(p, model, phash, x, force, share, now, park_hours)]
           if r in order]
    return sorted(out, key=lambda pr: (pr[0].attempts, order[pr[1]], -pr[0].fresh if pr[1] == "fresh" else 0,
                                       -pr[0].n, pr[0].key))


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
  and c.subreddit = %(sub)s
  and not coalesce(c.was_deleted_later, false)
  and c.author is distinct from 'AutoModerator'
  and ((m.opinion in ('endorse', 'stated') and m.timeframe is distinct from 'past')
       or (m.status in ('closed', 'moved') and c.created_utc > %(since)s))
"""


def read_inputs(conn, keys, since, text=True, budget_tokens=Settings.max_input_tokens):
    """{key: Input} for these places, chosen as the module docstring says.
    text=False reads only sizes, for dry runs over every place."""
    keys = list(keys)
    if not keys:
        return {}
    cols = "t.title, c.body" if text else "null::text, null::text"
    with conn.cursor() as cur:
        cur.execute(_INPUT_ROWS.format(text=cols), {"keys": keys, "sub": subreddits.HOME, "since": since})
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
           budget_tokens=Settings.max_input_tokens):
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


def _esc(text):
    """Text a user wrote, made inert inside the tags: & first, so an entity
    someone typed ("&lt;") reaches the model as they typed it."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _attr(text):
    return _esc(text).replace('"', "&quot;")


def render(inp, today):
    """The user message: today's date, the place, the comments and the status
    reports. Every string a user wrote goes through _esc or _attr."""
    tally = collections.Counter(TALLY[c.label()] for c in inp.comments)
    out = [f"<today>{today:%Y-%m-%d}</today>", f"<place>{_esc(inp.name)}</place>",
           f'<comments count="{len(inp.comments)}" praise="{tally["praise"]}" '
           f'criticism="{tally["criticism"]}" mixed="{tally["mixed"]}" '
           f'recommends="{tally["recommends"]}" other="{tally["other"]}">']
    for c in inp.comments:
        status = f' reports="{c.status}"' if c.status else ""
        out += [f'<comment date="{c.created:%Y-%m-%d}" names="{_attr("; ".join(c.names))}" '
                f'read_as="{c.label()}"{status}>',
                f"<thread_title>{_esc(c.title)}</thread_title>", _esc(c.body).strip(), "</comment>"]
    out.append("</comments>")
    if inp.reports:
        out.append(f'<status_reports count="{len(inp.reports)}">')
        for c in inp.reports:
            out += [f'<comment date="{c.created:%Y-%m-%d}" names="{_attr("; ".join(c.names))}" '
                    f'reports="{c.status}">',
                    f"<thread_title>{_esc(c.title)}</thread_title>", _esc(c.body).strip(), "</comment>"]
        out.append("</status_reports>")
    return "\n".join(out)


def params(user, effort):
    return {"model": MODEL, "max_tokens": MAX_TOKENS,
            "system": [{"type": "text", "text": SYSTEM_PROMPT}],
            "messages": [{"role": "user", "content": user}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort,
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
def record_calls(conn, key, phash, rows):
    """Paid calls into the ledger, [(outcome, cost, usage)], in a transaction
    of their own, so nothing that fails afterwards can lose them."""
    if not rows:
        return
    with conn.cursor() as cur:
        for outcome, cost, usage in rows:
            cur.execute("""insert into summary_calls (resolved_key, model, prompt_hash, outcome, cost_usd, usage)
                           values (%s, %s, %s, %s, %s, %s)""",
                        (key, MODEL, phash, outcome, round(cost, 8),
                         json.dumps(usage) if usage is not None else None))
    conn.commit()


_WRITE = """
insert into place_summaries (resolved_key, summary, model, prompt_hash, mention_count, last_mention_at,
                             seen_comment_ids, input_comments, input_chars, written_at, cost_usd, usage,
                             attempts, error, failed_at, updated_at)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s, %s, 0, null, null, now())
on conflict (resolved_key) do update set
  summary = excluded.summary, model = excluded.model, prompt_hash = excluded.prompt_hash,
  mention_count = excluded.mention_count, last_mention_at = excluded.last_mention_at,
  seen_comment_ids = excluded.seen_comment_ids,
  input_comments = excluded.input_comments, input_chars = excluded.input_chars,
  written_at = now(), cost_usd = excluded.cost_usd, usage = excluded.usage,
  attempts = 0, error = null, failed_at = null, updated_at = now()"""


def store(conn, place, inp, summary, usage, cost, phash, seen):
    """Write a summary (its call is already in the ledger), with seen, every
    comment that qualified for the place when it was read, as the ones it
    has seen."""
    with conn.cursor() as cur:
        cur.execute(_WRITE, (place.key, summary, MODEL, phash, place.n, place.newest, list(seen),
                             len(inp.comments) + len(inp.reports), inp.chars, round(cost, 8), json.dumps(usage)))
    conn.commit()


def record_empty(conn, place, phash, seen):
    """A place that qualifies but has nothing to send: no summary (any old one
    has lost its evidence), its comments marked seen, so it waits for new
    discussion like any other place instead of heading every pass."""
    with conn.cursor() as cur:
        cur.execute(_WRITE, (place.key, None, MODEL, phash, place.n, place.newest, list(seen),
                             0, 0, None, None))
    conn.commit()


def record_attempt(conn, key, error):
    """A failed attempt on a place, whose last good summary, if any, stays.
    Returns its attempts so far."""
    with conn.cursor() as cur:
        cur.execute("""
            insert into place_summaries (resolved_key, attempts, error, failed_at, updated_at)
            values (%s, 1, %s, now(), now())
            on conflict (resolved_key) do update set
              attempts = place_summaries.attempts + 1, error = excluded.error,
              failed_at = now(), updated_at = now()
            returning attempts""", (key, str(error)[:500]))
        attempts = cur.fetchone()[0]
    conn.commit()
    return attempts


def retry_errors(conn):
    with conn.cursor() as cur:
        cur.execute("update place_summaries set attempts = 0 where attempts >= %s", (MAX_ATTEMPTS,))
        n = cur.rowcount
    conn.commit()
    return n


# ---------------------------------------------------------------- run
class Stats:
    def __init__(self):
        self.written = self.failed = self.parked = self.empty = self.refused = self.late = 0
        self.skipped = False      # the step was not due yet (SUMMARY_EVERY_HOURS)
        self.stop = None          # why the pass ended early, if it did
        self.results = []         # (request, summary or None, cost, error) for --review

    def line(self, budget=None):
        out = (f"{self.written} written, {self.failed} failed ({self.parked} parked), "
               f"{self.empty} with nothing to send")
        if budget is not None:
            out += f", ${budget.spent:.4f}"
        return out + (f" -- stopped: {self.stop}" if self.stop else "")


@dataclasses.dataclass
class Request:
    place: Place
    inp: Input
    user: str
    worst: float
    # Worst cases of attempts that may have been billed with no answer. On
    # the request, not the result, so they reach the ledger even when the
    # worker raises after charging them.
    unseen: list = dataclasses.field(default_factory=list)
    seen: list = dataclasses.field(default_factory=list)    # the comment ids its row will store


@dataclasses.dataclass
class Result:
    status: str                       # answered | error | capped | late | skipped
    message: object = None
    cost: float = 0.0
    error: Exception = None


class DeadlineReached(Exception):
    """A retry, or the wait before one, would run past the pass's deadline."""


class TimedOut(Exception):
    """A call timed out (or its connection dropped) and is not sent again in
    this run. Its worst case is already charged; like any failure it costs
    the place an attempt."""


_ACCOUNT_TYPES = ("authentication_error", "permission_error", "billing_error")
# The API's no-credit refusal is a 400 saying "Your credit balance is too
# low"; the phrase, not a lone word, so a request that mentions a balance in
# passing is not taken for the account's.
_NO_CREDIT = re.compile(r"credit balance", re.I)
_MODEL = re.compile(r"\bmodel\b", re.I)
# A 400/413 that is about this request's own content: it would come back for
# this place and no other.
_PLACE_WORDS = re.compile(r"too (long|large)|exceed|maximum|messages\.\d+\.content|invalid (utf|unicode|character)"
                          r"|could not process", re.I)


def account_wide(e):
    """A refusal every request would get: no key or a revoked one (401), no
    permission (403), a billing error, no credit, or a model the API does
    not have (a not_found_error about the model). Anything else, another
    404 included, is charged to its place, so no refusal can hold the head
    of the queue forever."""
    if not isinstance(e, AV.FatalAPIError):
        return False
    status, kind, text = getattr(e, "status", None), getattr(e, "kind", None), str(e)
    return (status in (401, 403) or kind in _ACCOUNT_TYPES or bool(_NO_CREDIT.search(text))
            or (kind == "not_found_error" and status in (404, None) and bool(_MODEL.search(text))))


def place_error(e):
    """A refusal about this place's request itself (too long, content it
    could not take): it says nothing about the API, so it never counts
    toward the run's failures in a row."""
    return (isinstance(e, AV.FatalAPIError) and not account_wide(e)
            and getattr(e, "status", None) in (400, 413) and bool(_PLACE_WORDS.search(str(e))))


class Streak:
    """API failures in a row, across the pass's workers. Counted where the
    calls are made, so the call that would be one too many sees the stop
    before it starts, rather than after the main thread has caught up."""

    def __init__(self, limit=API_FAILURES_IN_A_ROW):
        self.limit, self.n, self.hit = limit, 0, False
        self._lock = threading.Lock()

    def failed(self, stop):
        with self._lock:
            self.n += 1
            if self.n >= self.limit:
                self.hit = True
                stop.set()

    def answered(self):
        with self._lock:
            self.n = 0


def _work(cl, budget, req, effort, stop, attempts, sleep, log, deadline, streak=None):
    """The network half, on a worker thread: reserve, call, settle. Touches no
    database. Nothing starts, retries or waits for a retry past the
    deadline, or once the pass is stopping."""
    if stop.is_set():
        return Result("skipped")

    def past(wait=0.0):
        return deadline is not None and time.monotonic() + wait >= deadline
    if past():
        return Result("late")
    w = req.worst
    if not budget.reserve(w):
        stop.set()
        return Result("capped")
    held = [True]

    def again():
        # The attempt that timed out (or lost its connection) may have been
        # billed: charge it its worst case, and do not send it again this
        # run. The same request is the likeliest to time out the same way,
        # at the same worst case (about $0.19 for Katz's), and the next run
        # is hours away, not seconds; a place that keeps doing it is parked
        # (run). 429 and 5xx answers are not billed and are still retried.
        budget.settle(w, w)
        req.unseen.append(w)
        held[0] = False
        raise TimedOut("timed out or lost its connection; not sent again this run")

    def wait(seconds):
        if past(seconds):
            raise DeadlineReached(f"a {seconds:.0f}s wait would run past the deadline")
        (sleep or time.sleep)(seconds)
    try:
        msg = AV.call(cl, params(req.user, effort), attempts=attempts, sleep=wait, log=log, retry_ok=again)
    except DeadlineReached:
        if held[0]:
            budget.settle(w, 0.0)       # held for a retry that was never sent
        return Result("late")
    except AV.CapReached:
        stop.set()
        return Result("capped")
    except TimedOut as e:
        if streak is not None:
            streak.failed(stop)
        return Result("error", error=e)
    except (AV.FatalAPIError, AV.TransientAPIError) as e:
        if held[0]:
            billed = w if getattr(e, "maybe_billed", False) else 0.0
            budget.settle(w, billed)
            if billed:
                req.unseen.append(billed)
        if account_wide(e):
            stop.set()
        elif not place_error(e) and streak is not None:
            # Only failures of the run count toward the streak: a request
            # refused for its own content says nothing about the API.
            streak.failed(stop)
        return Result("error", error=e)
    if streak is not None:
        streak.answered()
    c = AV.cost(AV.usage_of(msg), batch=False, model=MODEL)
    budget.settle(w, c)
    if c > w + EV.TRIP_EPS:
        budget.trip(f"{req.place.key} cost ${c:.6f}, over the ${w:.6f} held for it")
        stop.set()
    return Result("answered", msg, c)


def _ledger_rows(req, res, outcome):
    rows = [("unseen", a, None) for a in req.unseen]
    if res is not None and res.status == "answered":
        rows.append((outcome, res.cost, AV.usage_of(res.message)))
    return rows


def _flush(pending, connect, phash, log):
    """As a failed pass unwinds: everything paid for and not yet in the
    ledger goes in now, on a fresh connection (the pass's own may be what
    failed), so the ceiling never under-counts: the 'unseen' worst cases a
    worker charged, whether or not it then raised, and answers not stored."""
    rows = []
    for fut, req in pending.items():
        res = None
        if fut.done() and not fut.cancelled() and fut.exception() is None:
            res = fut.result()
        r = _ledger_rows(req, res, "unstored")
        if r:
            rows.append((req.place.key, r))
    if not rows:
        return
    total = sum(c for _, r in rows for _, c, _ in r)
    try:
        c = connect()
        try:
            for key, r in rows:
                record_calls(c, key, phash, r)
        finally:
            c.close()
        log(f"  summaries: recorded ${total:.6f} of calls the failed pass had not recorded")
    except Exception as e:
        log(f"\n!!!!!!!! SUMMARY LEDGER: could not record ${total:.6f} of paid calls ({e}); "
            "summary_calls under-counts by that much !!!!!!!!\n")


def run(conn, cl, budget, todo, settings=None, workers=4, attempts=ATTEMPTS, deadline=None, sleep=None,
        log=print, keep=False, now=None, since=None, connect=None, limit=None):
    """Write summaries for todo, [(place, reason)] in order, until it is done,
    `limit` places with something to send have been sent, the cap or the
    ceiling refuses a call, the API refuses every call or fails too often in
    a row, or the deadline (time.monotonic()) passes. Places are taken in
    order: one with nothing to send is recorded and does not count toward
    the limit, and nothing after the limit is touched, so --dry-run --limit
    picks the same places. Places are read and sent a page at a time. Every
    write happens here, on the caller's connection, as answers arrive: a
    call's ledger row first, then its outcome. keep=True keeps each request
    and answer in stats.results.

    Failures: an account-wide refusal stops the run and charges no place;
    every other failure charges its place one attempt when it happens."""
    settings = settings or Settings()
    stats = Stats()
    phash = settings.prompt_hash
    if now is None or since is None:
        now, since = _since(conn)
    stop = threading.Event()
    page = max(1, workers * 2)
    halt, streak, sent = None, Streak(), 0
    pending = {}
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers))

    def failed(req, error, cost=0.0):
        n = record_attempt(conn, req.place.key, error)
        stats.failed += 1
        stats.parked += n >= MAX_ATTEMPTS
        log(f"  {req.place.key}: {error}" + (" -- parked" if n >= MAX_ATTEMPTS else ""))
        if keep:
            stats.results.append((req, None, cost, str(error)))
    try:
        for start in range(0, len(todo), page):
            if limit is not None and sent >= limit:
                break
            if deadline is not None and time.monotonic() >= deadline:
                stats.stop = "out of time for this pass"
                break
            chunk = [p for p, _ in todo[start:start + page]]
            # The seen ids before the inputs: a comment that lands between
            # the two reads is then sent but not marked seen (it reads as new
            # next time), never marked seen without having been sent.
            seen = qualifying_ids(conn, [p.key for p in chunk], since)
            inputs = read_inputs(conn, [p.key for p in chunk], since, budget_tokens=settings.max_input_tokens)
            reqs = []
            for p in chunk:
                if limit is not None and sent + len(reqs) >= limit:
                    break
                inp = inputs[p.key]
                if not inp.comments and not inp.reports:
                    record_empty(conn, p, phash, seen[p.key])
                    stats.empty += 1
                    continue
                user = render(inp, now)
                reqs.append(Request(p, inp, user, worst(user), seen=seen[p.key]))
            sent += len(reqs)
            futures = {pool.submit(_work, cl, budget, r, settings.effort, stop, attempts, sleep, log, deadline,
                                   streak): r
                       for r in reqs}
            pending.update(futures)
            for fut in concurrent.futures.as_completed(futures):
                req = futures[fut]
                res = fut.result()
                summary = err = None
                if res.status == "answered":
                    try:
                        summary = read_summary(res.message)
                    except AV.ItemError as e:
                        err = e
                record_calls(conn, req.place.key, phash, _ledger_rows(req, res, err.code if err else "written"))
                del pending[fut]
                if res.status == "capped":
                    stats.refused += 1
                elif res.status == "late":
                    stats.late += 1
                elif res.status == "error" and account_wide(res.error):
                    halt = res.error                  # outranks a streak halt: it says why
                    if keep:
                        stats.results.append((req, None, 0.0, f"{type(res.error).__name__}: {res.error}"))
                elif res.status == "error":
                    failed(req, f"api: {type(res.error).__name__}: {res.error}")
                    if streak.hit and halt is None:
                        halt = res.error
                elif res.status == "answered" and err is not None:
                    failed(req, err, res.cost)
                elif res.status == "answered":
                    store(conn, req.place, req.inp, summary, AV.usage_of(res.message), res.cost, phash, req.seen)
                    stats.written += 1
                    if keep:
                        stats.results.append((req, summary, res.cost, None))
            if budget.tripped:
                EV._trip(budget, budget.tripped, log)
            EV._check_ceiling(budget, log, what="summary")
            if halt is not None:
                stats.stop = (f"{type(halt).__name__}: {halt}" if account_wide(halt) else
                              f"{API_FAILURES_IN_A_ROW} calls in a row failed at the API, last {halt}")
                break
            if stats.late:
                stats.stop = "out of time for this pass"
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
        _flush(pending, connect or db.connect, phash, log)
        raise
    pool.shutdown(wait=True)
    if halt is not None and account_wide(halt):
        log(f"  SUMMARIES STOPPED -- the API refuses every request: {halt}")
    elif halt is not None:
        log(f"  summaries stopped early, will retry next run: {stats.stop}")
    return stats


# ---------------------------------------------------------------- the poller's step
def poll_once(conn, limit, settings=None, workers=4, connect=None, cl=None, log=print,
              deadline=None, sleep=None, max_usd=None, ceiling_usd=None):
    """One chores-pass step: if SUMMARY_EVERY_HOURS have passed since the last
    run, write what is due, up to `limit` places with something to send,
    under the run's cap and the lifetime ceiling. Never raises for a missing
    key, missing tables or the legacy read mode, and raises nothing that is
    not an Exception; a spend tripwire is raised (EV.Tripped) so the poller
    can switch summaries off. settings are the ones checked at boot."""
    settings = settings or load_settings()
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
        if EV.read_version(conn) != "v6":
            log("  summaries: the board reads legacy mentions, which carry no v6 fields; skipping")
            return None
        if not due_to_run(conn, settings.every_hours):
            stats = Stats()
            stats.skipped = True
            return stats
        mark_run(conn)
        now, since = _since(conn)
        due_now = due(qualifying(conn, settings.n, since=since, have_tables=True), MODEL, settings.prompt_hash,
                      settings.x, share=settings.share, now=now, park_hours=settings.park_hours)
        stats = Stats()
        if due_now:
            budget = make_budget(max_usd if max_usd is not None else settings.run_usd,
                                 ceiling_usd if ceiling_usd is not None else settings.ceiling_usd, connect)
            try:
                cl = cl or client(api_key(), timeout=TIMEOUT)
                stats = run(conn, cl, budget, due_now, settings, workers=workers, attempts=ATTEMPTS,
                            deadline=deadline if deadline is not None else time.monotonic() + DEADLINE,
                            sleep=sleep, log=log, now=now, since=since, connect=connect, limit=limit)
            finally:
                budget.ceiling.close()
            if stats.written or stats.failed or stats.empty or stats.stop:
                log(f"  summaries: {stats.line(budget)} ({len(due_now)} due)")
        return stats
    finally:
        try:
            unlock(conn)
        except Exception:
            pass        # a dead connection has already dropped the lock


# ---------------------------------------------------------------- read-only reports
def status(conn, settings, log=print):
    phash = settings.prompt_hash
    with conn.cursor() as cur:
        cur.execute("""select count(*) filter (where summary is not null),
                              count(*) filter (where summary is not null and prompt_hash = %s and model = %s),
                              count(*) filter (where summary is null and written_at is not null),
                              count(*) filter (where attempts > 0 and attempts < %s),
                              count(*) filter (where attempts >= %s),
                              max(written_at)
                       from place_summaries""", (phash, MODEL, MAX_ATTEMPTS, MAX_ATTEMPTS))
        written, current, empty, failing, parked, last = cur.fetchone()
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
        cur.execute("select max(last_pass_at) from summary_state")
        last_pass = cur.fetchone()[0]
    conn.commit()
    log(f"model {MODEL}, prompt {phash}, effort {settings.effort}")
    log(f"summaries: {written:,} written ({current:,} current), {empty:,} with nothing to send, "
        f"{failing} failing, {parked} parked; last written {last}")
    log(f"poller step: last ran {last_pass}, every {settings.every_hours:g}h")
    log(f"spend: ${float(total):.4f} over {calls:,} calls (${float(day):.4f} in 24h, ${float(month):.4f} in 30d); "
        f"ceiling ${settings.ceiling_usd:.2f}")
    for o, k in outcomes:
        log(f"  {k:6,}  {o}")
    for key, a, err in errors:
        log(f"  {key}: {a} attempt(s), {err}")


def _pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else 0


def dry_run(conn, settings, keys=None, limit=None, force=False, print_input=False, log=print):
    """What qualifies and is due, the inputs' sizes, and what writing them
    would cost. Reads only."""
    now, since = _since(conn)
    phash = settings.prompt_hash
    if EV.read_version(conn) != "v6":
        log("WARNING: the board reads legacy mentions; nothing is written until it reads v6")
    places = qualifying(conn, settings.n, keys=keys, since=since)
    reasons = collections.Counter(due_reason(p, MODEL, phash, settings.x, force, settings.share, now,
                                             settings.park_hours) or "current"
                                  for p in places)
    log(f"{len(places):,} places qualify (n={settings.n} comments in {WINDOW_DAYS}d, the v6 mentions the board "
        f"counts); prompt {phash}, rewrite after max({settings.x}, {settings.share:g} x count) new comments")
    if keys is not None:
        missing = sorted(set(keys) - {p.key for p in places})
        if missing:
            log(f"  not qualifying: {', '.join(missing)}")
    log("  " + ", ".join(f"{k} {v:,}" for k, v in reasons.most_common()))
    todo = due(places, MODEL, phash, settings.x, force, settings.share, now, settings.park_hours)
    if limit:
        # As run() takes --limit: places in order, a page at a time, those
        # with nothing to send passed (and, in a real run, recorded) without
        # counting, and nothing after the limit read at all.
        kept, inputs, n_sent = [], {}, 0
        for start in range(0, len(todo), DRY_PAGE):
            if n_sent >= limit:
                break
            chunk = todo[start:start + DRY_PAGE]
            got = read_inputs(conn, [p.key for p, _ in chunk], since, text=print_input,
                              budget_tokens=settings.max_input_tokens)
            for p, r in chunk:
                if n_sent >= limit:
                    break
                kept.append((p, r))
                inputs[p.key] = got[p.key]
                n_sent += bool(got[p.key].comments or got[p.key].reports)
        todo = kept
    else:
        inputs = read_inputs(conn, [p.key for p, _ in todo], since, text=print_input,
                             budget_tokens=settings.max_input_tokens)
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
    worst_ = [p for p in pool if p.negative >= 8]
    take(sorted(worst_, key=lambda p: (-p.negative / p.opinions, -p.negative)), k["complaints"], "complaints")
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


def _sample_or_keys(conn, args, settings, since):
    keys = args.keys
    places = qualifying(conn, settings.n, keys=keys, since=since)
    if args.sample:
        chosen = pick_sample(places, args.sample)
    else:
        found = {p.key: p for p in places}
        chosen = [(found[k], "asked for") for k in keys if k in found]
        missing = [k for k in keys if k not in found]
        if missing:
            print(f"not qualifying, skipped: {', '.join(missing)}")
    return chosen


def review_only(conn, args, settings, log=print):
    """The review file from stored summaries and the inputs as they would be
    chosen now (which may differ from what a summary was written from if
    comments have come in since). Reads only."""
    now, since = _since(conn)
    chosen = _sample_or_keys(conn, args, settings, since)
    inputs = read_inputs(conn, [p.key for p, _ in chosen], since, budget_tokens=settings.max_input_tokens)
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
                  f"model {MODEL}, prompt {settings.prompt_hash}."], log)


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
    ap.add_argument("--limit", type=int, help="at most this many places with something to send")
    ap.add_argument("--max-usd", type=float, help="cap on this run (default $SUMMARY_RUN_USD or $1)")
    ap.add_argument("--ceiling-usd", type=float,
                    help="lifetime ceiling on all summary spend (default $SUMMARY_CEILING_USD or $10)")
    ap.add_argument("--workers", type=int, default=4, help="calls at once (default 4)")
    ap.add_argument("--retry-errors", action="store_true", help="unpark places that failed too often, then run")
    args = ap.parse_args(argv)

    try:
        settings = load_settings()
    except SettingError as e:
        raise SystemExit(str(e))
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
        raise SystemExit("the summary tables are missing or out of date: apply summary_schema.sql first")
    if args.status:
        return status(conn, settings)
    if args.review_only:
        return review_only(conn, args, settings)
    if args.dry_run:
        if args.sample:
            _, since = _since(conn)
            chosen = _sample_or_keys(conn, args, settings, since)
            for p, why in chosen:
                print(f"  {why:16} {p.key} ({p.n} comments, {p.opinions} opinions, {p.negative} critical, "
                      f"{p.closed} closed/moved)")
            args.keys = [p.key for p, _ in chosen]
            args.force = True
        dry_run(conn, settings, keys=args.keys, limit=args.limit, force=args.force, print_input=args.print_input)
        return

    key = api_key()
    if not key:
        raise SystemExit(f"{KEY_VAR} is not set")
    AV.check_prices(MODEL)
    if EV.read_version(conn) != "v6":
        raise SystemExit("the board reads legacy mentions, which carry no v6 fields: nothing to summarize")
    max_usd = args.max_usd if args.max_usd is not None else settings.run_usd
    ceiling = args.ceiling_usd if args.ceiling_usd is not None else settings.ceiling_usd
    phash = settings.prompt_hash
    if not try_lock(conn):
        raise SystemExit("another summary run (or the poller's step) holds the lock; try again shortly")
    try:
        if args.retry_errors:
            print(f"unparked {retry_errors(conn)} place(s)")
        now, since = _since(conn)
        if args.sample or args.keys:
            chosen = _sample_or_keys(conn, args, settings, since)
            why = {p.key: w for p, w in chosen}
            force = args.force or bool(args.sample)
            todo = due([p for p, _ in chosen], MODEL, phash, settings.x, force, settings.share, now,
                       settings.park_hours)
        else:
            why = {}
            todo = due(qualifying(conn, settings.n, since=since, have_tables=True), MODEL, phash,
                       settings.x, share=settings.share, now=now, park_hours=settings.park_hours)
        print(f"{len(todo):,} place(s) due, {args.limit or 'no'} limit, ${max_usd:.2f} cap, ${ceiling:.2f} ceiling, "
              f"{MODEL} at effort {settings.effort}, prompt {phash}")
        budget = make_budget(max_usd, ceiling)
        print(f"  recorded summary spend so far: ${budget.ceiling.start:.4f}")
        try:
            stats = run(conn, client(key), budget, todo, settings, workers=args.workers, attempts=AV.ATTEMPTS,
                        keep=bool(args.review), now=now, since=since, limit=args.limit)
        except EV.Tripped:
            return EV.TRIPPED
        finally:
            budget.ceiling.close()
        print(f"done: {stats.line(budget)}")
        if args.review:
            done = [(req, why.get(req.place.key, "due"), s, c, e) for req, s, c, e in stats.results]
            write_review(args.review, done,
                         [f"Written {now:%Y-%m-%d %H:%M} UTC with {MODEL} at effort {settings.effort}, prompt "
                          f"{phash}; ${budget.spent:.4f} spent."])
    finally:
        unlock(conn)


if __name__ == "__main__":
    sys.exit(main())
