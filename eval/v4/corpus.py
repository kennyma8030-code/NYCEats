"""The whole corpus, loaded once over a read-only connection and cached outside
the repo, plus the heuristics that tag each comment and each thread chunk.

    EVAL_DB_URL=postgresql://... python eval/v4/corpus.py        # load, cache, print tag counts

Every connection is opened read-only twice over: the libpq option
default_transaction_read_only and psycopg2's readonly session. Nothing here
writes anywhere but the cache directory ($V4_CACHE_DIR, default
~/.cache/nyceats-eval-v4), which holds comment text and production's stored
output and must never be committed.

The snapshot in that cache is an optional fast path. When it is missing, the
corpus is read again from the live database with the same cutoff; that
population may have drifted slightly from round 1's (snapshot_at is recorded
in design.json, and next_round.py warns when they differ).

Stored mentions are loaded ONLY to compute heuristics (a comment's mention
count, its ancestors', whether its scores sit at the +1 default). They are
never written into items or packets, so labeling stays blind.

The population is every comment production would send to the model: body not
'[deleted]' / '[removed]' and longer than 15 characters (extract.next_batch's
filter), created before CUTOFF so the draw is reproducible while the poller
keeps adding comments.
"""

import collections
import datetime
import os
import pickle
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
EVAL = os.path.dirname(HERE)
ROOT = os.path.dirname(EVAL)
sys.path.insert(0, ROOT)
import extract  # noqa: E402  (normalize_entity, CHAINS; imports db, which only reads .env)
import extract_threads  # noqa: E402  (CHUNK)
import prompt_thread  # noqa: E402  (MAX_DEPTH_INDENT)

# Comments created after this are left out. The poller extracts the last 3
# days, so anything older has settled: its stored extraction will not change
# under us between building the set and exporting production's output.
CUTOFF = datetime.datetime(2026, 10, 9, tzinfo=datetime.timezone.utc)
# A stable place outside the repo, not /tmp: the snapshot must survive reboots.
CACHE_DIR = os.environ.get("V4_CACHE_DIR") or os.path.expanduser("~/.cache/nyceats-eval-v4")
ORIGINAL_THREAD_PROMPT = "ca5439be83b3"


def connect():
    import psycopg2
    url = os.environ.get("EVAL_DB_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("set EVAL_DB_URL or DATABASE_URL (read-only use only)")
    conn = psycopg2.connect(url, options="-c default_transaction_read_only=on")
    conn.set_session(readonly=True)
    return conn


class C:
    """One comment row. Slots keep 765k of them affordable in memory."""
    __slots__ = ("id", "thread_id", "parent", "root", "depth", "author", "body", "created",
                 "permalink", "extracted", "extracted_with", "error", "deleted_later")

    def __init__(self, *vals):
        for k, v in zip(self.__slots__, vals):
            setattr(self, k, v)

    @property
    def eligible(self):
        return self.body not in ("[deleted]", "[removed]") and len(self.body) > 15

    @property
    def prompt_hash(self):
        return (self.extracted_with or "").rpartition(":")[2] or None


# ---------------------------------------------------------------- load
def _fetch(conn):
    cur = conn.cursor(name="v4_comments")
    cur.itersize = 20000
    cur.execute("""
        select id, thread_id, parent_comment_id, root_comment_id, coalesce(depth, 0), author,
               body, created_utc, permalink, extracted_at is not null, extracted_with,
               extract_error is not null, was_deleted_later
        from comments where created_utc < %s""", (CUTOFF,))
    comments = {r[0]: C(*r) for r in cur}
    cur.close()
    cur = conn.cursor()
    cur.execute("select id, title, selftext, created_utc, num_comments from threads")
    threads = {r[0]: {"title": r[1], "selftext": r[2], "created_utc": r[3], "num_comments": r[4]}
               for r in cur.fetchall()}
    cur.execute("""select comment_id, restaurant_raw, entity_key, aspects, expensiveness,
                          is_negated, is_firsthand, prompt_hash from mentions order by id""")
    mentions = collections.defaultdict(list)
    for cid, raw, key, asp, exp, neg, first, ph in cur.fetchall():
        mentions[cid].append({"restaurant_raw": raw, "entity_key": key, "aspects": asp or {},
                              "expensiveness": exp, "is_negated": neg, "is_firsthand": first,
                              "prompt_hash": ph})
    cur.execute("select now()")
    snap = cur.fetchone()[0]
    return {"comments": comments, "threads": threads, "mentions": dict(mentions),
            "snapshot_at": snap.isoformat(), "cutoff": CUTOFF.isoformat()}


def snapshot_path():
    return os.path.join(CACHE_DIR, f"snapshot_{CUTOFF:%Y%m%d}.pickle")


def load(refresh=False, fetch_ok=True):
    """The raw snapshot, from cache when present.

    Reading a new one from the live DB gives a different population, so it
    only happens when fetch_ok (round 1) or refresh is set, and says so."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = snapshot_path()
    if os.path.exists(path) and not refresh:
        with open(path, "rb") as f:
            return pickle.load(f)
    if not (fetch_ok or refresh):
        raise SystemExit(f"no corpus snapshot at {path}. Point V4_CACHE_DIR at the cache that built "
                         "round 1; a new snapshot is a different population and cannot be pooled.")
    print(f"reading a NEW snapshot from the live database into {path}", file=sys.stderr)
    conn = connect()
    snap = _fetch(conn)
    conn.close()
    with open(path, "wb") as f:
        pickle.dump(snap, f, protocol=pickle.HIGHEST_PROTOCOL)
    return snap


# ---------------------------------------------------------------- old eval sets
def old_set_ids():
    """Every comment id in the v1/v2 eval sets, and the threads v1 sampled whole.

    v4 excludes all of them except the deliberate overlap, so agreement with
    the old labels is measured on a known, chosen subset."""
    import json
    ids, threads = set(), set()
    for rel in ("items.jsonl", "v2/items.jsonl", "v2/topup_items.jsonl"):
        path = os.path.join(EVAL, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                it = json.loads(line)
                if it.get("kind") == "thread":
                    threads.add(it["thread_id"])
                    ids.update(c["comment_id"] for c in it["comments"])
                else:
                    ids.add(it["comment_id"])
    return ids, threads


# ---------------------------------------------------------------- heuristics
I = re.IGNORECASE

# Short replies that pass judgement, the way "v mid" or "skip it" do.
SHORT_OPINION = re.compile(
    r"(^\W*(this|same|\+1|yes+|no+|nah|facts|agreed?|seconded|word)\b)|"
    r"\b(mid|meh|overrated|overhyped|underwhelming|mediocre|not worth|skip|pass on|hard pass|avoid|"
    r"tourist trap|trash|garbage|bland|disappointing|disagree|hard disagree|second this|"
    r"underrated|so good|it'?s fine|it'?s ok(ay)?|just ok(ay)?|decent|solid|fell off|"
    r"gone downhill|went downhill|nothing special)\b", I)

NEG_WORDS = re.compile(
    r"\b(mid|meh|overrated|overhyped|underwhelming|mediocre|disappoint\w*|bland|terrible|awful|"
    r"horrible|gross|disgusting|inedible|worst|trash|garbage|sucks?|sucked|rude|dirty|"
    r"food poisoning|got sick|never again|never going back|not worth|overpriced|rip ?-?off|"
    r"tourist trap|avoid|skip|stay away|don'?t bother|wouldn'?t (go|recommend|return)|"
    r"nothing special|fell off|(gone|went) downhill|not what it used to be|soggy|stale|"
    r"greasy|overcooked|undercooked|lukewarm|flavorless|tasteless)\b", I)

POS_WORDS = re.compile(
    r"\b(amazing|incredible|delicious|great|awesome|best|love|loved|favou?rite|fav|excellent|"
    r"fantastic|outstanding|phenomenal|underrated|insane|unreal|bomb|slaps|fire|perfect|"
    r"worth it|worth the)\b", I)

PRICE_COMPLAINT = re.compile(
    r"\b(over-? ?priced|rip-? ?off|highway robbery|robbery|price gouging|money grab|"
    r"not worth (it|the (money|price|cost|hype))|"
    r"(too|so|very|way|crazy|insanely|ridiculously|absurdly|really) (expensive|pricey|overpriced)|"
    r"for (that|the|this) price|at (that|this) price|"
    r"prices? (are|is|have gone|went) (up|insane|crazy|ridiculous|absurd|way up)|"
    r"\$\d+(\.\d\d)? for (a|an|one|two|three|\d) \w+)", I)

DISH_COMPLAINT = re.compile(
    r"(\b(skip|avoid|don'?t (get|order|bother with)|pass on|stay away from|steer clear of) "
    r"(the|their|any of the)\b)|"
    r"(\b(the|their|my) [\w'’ -]{2,30}? (was|is|were|are|tasted|felt) (kind of |kinda |a bit |pretty |so |very |really |super |too )?"
    r"(bland|dry|soggy|overcooked|undercooked|under-?seasoned|salty|too salty|greasy|stale|"
    r"rubbery|mushy|tough|chewy|lukewarm|mid|meh|forgettable|disappointing|overrated|"
    r"not good|terrible|awful|inedible|gross|burnt|flavorless|tasteless)\b)", I)

QUESTION_OR_UNVISITED = re.compile(
    r"\b(haven'?t (been|tried|gone|had|made it)|have not (been|tried)|never (been|tried)|"
    r"on my (list|radar)|want(ed)? to try|wanna try|planning (to|on) (go|try)|"
    r"heard (good|great|amazing|mixed|bad|nothing but) things|"
    r"(has|have) any ?one (been|tried|gone)|any ?one (been|tried)|have you (been|tried)|"
    r"is it (good|worth)|worth (it|going|the hype|the wait)\s*\?|how (is|was|are|were) [^?]{1,40}\?)", I)

AVOID_OR_STRONG_NEG = re.compile(
    r"\b(avoid|skip|tourist trap|don'?t go|dont bother|don'?t bother|not worth|overrated|"
    r"stay away|overhyped|got sick|food poisoning|rude|worst|never again|never going back|"
    r"never go back|regret\w*|disgusting|inedible)\b", I)

BULLET = re.compile(r"^\s*(?:[-*•+]|\d{1,2}[.)])\s+\S", re.M)

# Old v1 rule for "named a place but nothing was extracted".
PLACE_WORDS = re.compile(r"\b(try|tried|go to|went to|spot|place|recommend|check out|love|loved|"
                         r"favorite|fav|go-to|get the|order the|pizzeria|deli|bakery|ramen|tacos?)\b", I)
CAP_MID = re.compile(r"[a-z,;:(] +[A-Z][A-Za-z'’&\-]{2,}")
POSSESSIVE = re.compile(r"\b[A-Za-z]{2,}(?:'|’)s\b")


def is_default(m):
    """The prompt's "named as an answer, nothing said" score: food 0.3, rest null."""
    a = m.get("aspects") or {}
    f = a.get("food")
    return (isinstance(f, (int, float)) and abs(f - 0.3) < 0.011
            and all(a.get(k) is None for k in ("value", "service", "atmosphere", "wait")))


def is_neg(m):
    a = m.get("aspects") or {}
    return bool(m.get("is_negated")) or any(isinstance(v, (int, float)) and v < 0 for v in a.values())


class Gazetteer:
    """Known place names, to tell when a parent or ancestor names a place even
    if production never extracted it (70% of the corpus is unextracted).

    Built from production's own entity keys with at least MIN mentions.
    Single-word keys that are mostly ordinary words ("best", "via") are
    dropped: a single-word key is kept only when the word appears in the
    corpus at most RATIO times as often as it was extracted as a place."""
    MIN, RATIO, MAXN = 8, 4, 4
    # Keys made only of these words are categories or areas, not places
    # ("best pizza", "coffee shop", "little italy").
    GENERIC = set("""best good great pizza pizzeria slice coffee shop cafe bar deli bagel bagels bakery
        diner grill kitchen house place spot ramen sushi taco tacos burger burgers thai chinese italian
        pho dumpling dumplings halal cart market food foods new york city nyc brooklyn queens bronx
        manhattan little italy china town chinatown east west north south upper lower village
        restaurant restaurants hall the and of""".split())
    # A key ending in one of these is a location ("7th street", "bryant park").
    PLACE_SUFFIX = {"street", "st", "avenue", "ave", "park", "square", "blvd", "boulevard", "road", "heights"}

    def __init__(self, mentions, comments, excluded):
        counts = collections.Counter(m["entity_key"] for ms in mentions.values() for m in ms)
        keys = {k for k, n in counts.items() if n >= self.MIN and len(k) >= 3 and not k.isdigit()
                and k not in excluded and k not in extract.CHAINS and len(k.split()) <= self.MAXN
                and max(len(w) for w in k.split()) >= 3
                and not all(w in self.GENERIC for w in k.split())
                and k.split()[-1] not in self.PLACE_SUFFIX}
        single = {k for k in keys if " " not in k}
        words = collections.Counter()
        for c in comments.values():
            if c.eligible:
                words.update(w for w in extract.normalize_entity(c.body).split() if w in single)
        self.keys = {k for k in keys if " " in k or words[k] <= self.RATIO * counts[k]}

    def hits(self, text):
        toks = extract.normalize_entity(text or "").split()
        out = set()
        for n in range(1, self.MAXN + 1):
            for i in range(len(toks) - n + 1):
                g = " ".join(toks[i:i + n])
                if g in self.keys:
                    out.add(g)
        return out


def ancestors(c, comments, limit=50):
    """Parent first, then up toward the root. Stops at a missing parent."""
    out, seen = [], set()
    p = c.parent
    while p and p not in seen and len(out) < limit:
        seen.add(p)
        a = comments.get(p)
        if a is None:
            break
        out.append(a)
        p = a.parent
    return out


# Every comment-level tag, with its one-line definition (copied into the README).
COMMENT_TAGS = {
    "dish_complaint": "body matches DISH_COMPLAINT: 'skip/avoid/don't get the ...', or 'the <dish> was bland/dry/soggy/...'",
    "price_complaint": "body matches PRICE_COMPLAINT: overpriced, rip-off, not worth it/the money, too expensive, for that price, '$N for a ...'",
    "neg_wording_nonneg_score": "extracted with >= 1 stored mention, body matches NEG_WORDS, and no stored mention has an aspect < 0 or is_negated",
    "deep_chain_context_gap": "depth >= 2, length <= 400, no stored mention and no gazetteer name in the comment or its parent, but the grandparent or great-grandparent has a stored mention or a gazetteer name (comment mode cannot see it)",
    "reply_ancestor_named": "depth >= 1, length <= 400, no stored mention (or never extracted) and no gazetteer name in the comment, while the parent or grandparent has a stored mention or a gazetteer name",
    "short_opinion_reply": "depth >= 1, length <= 150, body matches SHORT_OPINION (mid, skip, overrated, not worth, meh, this, +1, agreed, disagree, so good, ...)",
    "avoid_or_strong_negative": "body matches AVOID_OR_STRONG_NEG (avoid, skip, tourist trap, not worth, overrated, rude, worst, got sick, never again, regret, ...)",
    "question_or_unvisited": "body matches QUESTION_OR_UNVISITED (haven't been, never tried, on my list, want to try, heard good things, anyone been, is it worth, how is X?)",
    "stuck_default_with_opinion": "extracted, >= 1 stored mention at the 'named, nothing said' default (food 0.3, rest null), and the body carries opinion words (NEG_WORDS or POS_WORDS)",
    "zero_mentions_suspicious": "extracted with no stored mention, and the body names a gazetteer place or meets v1's rule (place word plus a mid-sentence capital, possessive, or top-level answer)",
    "long_list": ">= 4 bullet/numbered lines, >= 8 line breaks, or >= 6 stored mentions",
    # tags only: too common to target, or descriptive
    "never_extracted": "extracted_at is null (pending, or parked with extract_error)",
    "extract_error": "extract_error is set",
    "extracted_no_mentions": "extracted with no stored mention",
    "original_thread_prompt": "extracted_with carries the original thread prompt ca5439be83b3",
    "mixed_prompt_mentions": "stored mentions carry a prompt hash other than the comment's extracted_with (comment-mode re-run on top of thread-mode mentions)",
    "parent_missing": "a reply whose parent is not in the database (comment mode sends no parent)",
    "parent_not_sent": "a reply whose parent exists but is [deleted]/[removed] (comment mode omits it)",
    "long_parent": "comment mode sends a parent longer than 1,500 characters (production never truncates the parent)",
}
# Strata for comment mode, in priority order: each comment's stratum is the
# first of these it matches, else "none". Rarer and more valuable first.
COMMENT_STRATA = ["dish_complaint", "price_complaint", "neg_wording_nonneg_score",
                  "deep_chain_context_gap", "reply_ancestor_named", "short_opinion_reply",
                  "avoid_or_strong_negative", "question_or_unvisited",
                  "stuck_default_with_opinion", "zero_mentions_suspicious", "long_list"]
# Tags that count as a "failure signal" when deciding whether a chunk is dense.
FAILURE_SIGNALS = set(COMMENT_STRATA) - {"long_list", "question_or_unvisited"}


def comment_tags(c, comments, threads, mentions, gaz, hits):
    """hits(c) is gaz.hits(c.body), memoized: ancestors are shared by many replies."""
    body = c.body
    ms = mentions.get(c.id, [])
    n = len(ms)
    t = set()
    nameless_here = not ms and not hits(c)
    anc = ancestors(c, comments)
    def named(a):
        return bool(mentions.get(a.id)) or bool(hits(a))
    if DISH_COMPLAINT.search(body):
        t.add("dish_complaint")
    if PRICE_COMPLAINT.search(body):
        t.add("price_complaint")
    if c.extracted and n and NEG_WORDS.search(body) and not any(is_neg(m) for m in ms):
        t.add("neg_wording_nonneg_score")
    if c.depth >= 1 and len(body) <= 400 and nameless_here and anc:
        # Parent or grandparent only: further up, a deep chain has usually
        # wandered off the place it started with.
        if any(named(a) for a in anc[:2]):
            t.add("reply_ancestor_named")
        if len(anc) >= 2 and not named(anc[0]) and any(named(a) for a in anc[1:3]):
            t.add("deep_chain_context_gap")
    if c.depth >= 1 and len(body) <= 150 and SHORT_OPINION.search(body):
        t.add("short_opinion_reply")
    if AVOID_OR_STRONG_NEG.search(body):
        t.add("avoid_or_strong_negative")
    if QUESTION_OR_UNVISITED.search(body):
        t.add("question_or_unvisited")
    if c.extracted and any(is_default(m) for m in ms) and (NEG_WORDS.search(body) or POS_WORDS.search(body)):
        t.add("stuck_default_with_opinion")
    if c.extracted and not n:
        t.add("extracted_no_mentions")
        title = (threads.get(c.thread_id) or {}).get("title") or ""
        if hits(c) or (PLACE_WORDS.search(body) and (
                CAP_MID.search(body) or POSSESSIVE.search(body)
                or (c.depth == 0 and re.search(r"\b(recommend|recs?|suggestions?|where|best|looking for)\b", title, I)))):
            t.add("zero_mentions_suspicious")
    if body.count("\n") >= 8 or len(BULLET.findall(body)) >= 4 or n >= 6:
        t.add("long_list")
    if not c.extracted:
        t.add("never_extracted")
    if c.error:
        t.add("extract_error")
    if c.prompt_hash == ORIGINAL_THREAD_PROMPT:
        t.add("original_thread_prompt")
    if any(m["prompt_hash"] != c.prompt_hash for m in ms):
        t.add("mixed_prompt_mentions")
    if c.parent:
        p = comments.get(c.parent)
        if p is None:
            t.add("parent_missing")
        elif p.body.strip() in ("[deleted]", "[removed]") or not p.body.strip():
            t.add("parent_not_sent")
        elif len(p.body.strip()) > 1500:
            t.add("long_parent")
    return t


def stratum_of(tags, order):
    return next((s for s in order if s in tags), "none")


# ---------------------------------------------------------------- thread chunks
def production_order(rows):
    """extract_threads.thread_rows' ORDER BY coalesce(root_comment_id, id), created_utc.

    Only used to stratify the population. Sampled items are re-rendered from
    the database with production's own SQL, and verify_inputs.py checks the
    two agree."""
    return sorted(rows, key=lambda c: (c.root or c.id, c.created))


def visual_parent(seq, i):
    """The comment a reader of the rendered chunk would take as i's parent.

    Normally that is the nearest earlier line indented exactly one step less.
    Indentation stops at MAX_DEPTH_INDENT (prompt_thread.build_message), so a
    comment deeper than the cap is drawn flush with its parent; for it the
    only readable parent is the line right above, whether that line sits at
    the cap or one step short of it. A deep chain rendered consecutively
    therefore reads correctly and counts as no misattachment."""
    cap = prompt_thread.MAX_DEPTH_INDENT
    d = min(seq[i].depth, cap)
    if d == 0 or i == 0:
        return None
    if seq[i].depth > cap:
        prev = seq[i - 1]
        return prev.id if min(prev.depth, cap) >= cap - 1 else None
    for j in range(i - 1, -1, -1):
        dj = min(seq[j].depth, cap)
        if dj == d - 1:
            return seq[j].id
        if dj < d - 1:
            return None
    return None


def count_misattached(part):
    """Replies whose real parent is in this chunk but is not the line the
    indentation points to."""
    ids = {c.id for c in part}
    return sum(1 for i, c in enumerate(part)
               if c.parent and c.parent in ids and visual_parent(part, i) != c.parent)


CHUNK_TAGS = {
    "chunk_failure_dense": ">= 3 comments, and >= 40% of the chunk, carry a comment-level failure signal (any comment stratum except long_list and question_or_unvisited)",
    "chunk_title_names_place": "the post title names a gazetteer place, and the chunk has >= 3 replies (depth >= 1) that name no place themselves",
    "chunk_parent_outside": ">= 3 replies whose parent is not in this chunk (an earlier chunk, or not sent because it is deleted / <= 15 chars)",
    "chunk_misattached": ">= 2 replies whose real parent is in the chunk but is not the line the indentation points to (production orders a root's replies by time, not depth-first)",
    # tags only
    "chunk_later": "not the first chunk of its thread",
    "chunk_never_extracted": "every comment in the chunk is unextracted",
}
# Structural, thread-mode-only problems first: they are rarer, and the
# failure-dense stratum would otherwise swallow them.
CHUNK_STRATA = ["chunk_misattached", "chunk_parent_outside", "chunk_title_names_place",
                "chunk_failure_dense"]


def build_chunks(comments, threads, ctags, gaz, hits, skip_threads=()):
    """Every production chunk of every thread, keyed (thread_id, chunk_index)."""
    by_thread = collections.defaultdict(list)
    for c in comments.values():
        if c.eligible and c.thread_id not in skip_threads:
            by_thread[c.thread_id].append(c)
    title_named = {}
    chunks = {}
    for tid, rows in by_thread.items():
        seq = production_order(rows)
        if tid not in title_named:
            title_named[tid] = bool(gaz.hits((threads.get(tid) or {}).get("title")))
        size = extract_threads.CHUNK
        n_chunks = (len(seq) + size - 1) // size
        for ci in range(n_chunks):
            part = seq[ci * size:(ci + 1) * size]
            ids = {c.id for c in part}
            fails = sum(1 for c in part if ctags[c.id] & FAILURE_SIGNALS)
            outside = sum(1 for c in part if c.parent and c.parent not in ids)
            mis = count_misattached(part)
            nameless_replies = sum(1 for c in part if c.depth >= 1 and not hits(c))
            t = set()
            if fails >= 3 and fails >= 0.4 * len(part):
                t.add("chunk_failure_dense")
            if title_named[tid] and nameless_replies >= 3:
                t.add("chunk_title_names_place")
            if outside >= 3:
                t.add("chunk_parent_outside")
            if mis >= 2:
                t.add("chunk_misattached")
            if ci > 0:
                t.add("chunk_later")
            if all(not c.extracted for c in part):
                t.add("chunk_never_extracted")
            chunks[(tid, ci)] = {"thread_id": tid, "chunk_index": ci, "n_chunks": n_chunks,
                                 "comment_ids": [c.id for c in part], "tags": t,
                                 "failure_signals": fails, "parent_outside": outside,
                                 "misattached": mis}
    return chunks


class Corpus:
    """Snapshot plus derived tags. Building the tags takes a few minutes."""

    def __init__(self, snap):
        import json
        self.snapshot_at, self.cutoff = snap["snapshot_at"], snap["cutoff"]
        self.comments, self.threads, self.mentions = snap["comments"], snap["threads"], snap["mentions"]
        with open(os.path.join(EVAL, "excluded_entities.json"), encoding="utf-8") as f:
            excluded = set(json.load(f))
        self.gaz = Gazetteer(self.mentions, self.comments, excluded)
        memo = {}
        def hits(c):
            if c.id not in memo:
                memo[c.id] = self.gaz.hits(c.body)
            return memo[c.id]
        self.hits = hits
        self.eligible = [c for c in self.comments.values() if c.eligible]
        self.tags = {c.id: comment_tags(c, self.comments, self.threads, self.mentions, self.gaz, hits)
                     for c in self.eligible}
        self.old_ids, self.old_threads = old_set_ids()
        self.chunks = build_chunks(self.comments, self.threads, self.tags, self.gaz, hits)
        self.chunk_of = {cid: key for key, ch in self.chunks.items() for cid in ch["comment_ids"]}


# Everything the derived tags depend on besides the snapshot itself: the
# heuristics, entity normalization and chain list, the renderer constants,
# the exclusion list, and the old eval sets that are excluded.
KEY_FILES = [os.path.realpath(__file__),
             os.path.join(ROOT, "extract.py"), os.path.join(ROOT, "chains.txt"),
             os.path.join(ROOT, "extract_threads.py"), os.path.join(ROOT, "prompt_thread.py"),
             os.path.join(EVAL, "excluded_entities.json"), os.path.join(EVAL, "items.jsonl"),
             os.path.join(EVAL, "v2", "items.jsonl"), os.path.join(EVAL, "v2", "topup_items.jsonl")]


def cache_key():
    """Hash of every KEY_FILES file plus the snapshot file's identity, so a
    changed heuristic, exclusion list or snapshot rebuilds the tags."""
    import hashlib
    h = hashlib.md5()
    for p in KEY_FILES:
        h.update(p.encode())
        if os.path.exists(p):
            with open(p, "rb") as f:
                h.update(f.read())
    sp = snapshot_path()
    if os.path.exists(sp):
        st = os.stat(sp)
        h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
    return h.hexdigest()[:12]


def cached_corpus(refresh=False, fetch_ok=True):
    """Corpus with its tags, cached next to the snapshot under cache_key().
    Without a snapshot file it reads one from the live database (load)."""
    snap = None
    if refresh or not os.path.exists(snapshot_path()):
        snap = load(refresh, fetch_ok)
    path = os.path.join(CACHE_DIR, f"corpus_{CUTOFF:%Y%m%d}_{cache_key()}.pickle")
    if os.path.exists(path):
        with open(path, "rb") as f:
            cp = pickle.load(f)
    else:
        cp = Corpus(snap or load(False, fetch_ok))
        cp.hits = None          # a closure; not picklable
        with open(path, "wb") as f:
            pickle.dump(cp, f, protocol=pickle.HIGHEST_PROTOCOL)
    memo = {}
    def hits(c):
        if c.id not in memo:
            memo[c.id] = cp.gaz.hits(c.body)
        return memo[c.id]
    cp.hits = hits
    return cp


def main():
    import time
    t0 = time.time()
    cp = cached_corpus(refresh="--refresh" in sys.argv)
    print(f"snapshot {cp.snapshot_at} cutoff {cp.cutoff}: {len(cp.comments):,} comments, "
          f"{len(cp.eligible):,} eligible, {len(cp.chunks):,} chunks, gazetteer {len(cp.gaz.keys):,} keys "
          f"({time.time() - t0:.0f}s)")
    tc = collections.Counter(t for ts in cp.tags.values() for t in ts)
    sc = collections.Counter(stratum_of(ts, COMMENT_STRATA) for ts in cp.tags.values())
    for t in COMMENT_TAGS:
        print(f"  {t:28} tagged {tc[t]:>8,}   stratum {sc.get(t, 0):>8,}")
    print(f"  {'none':28} {'':15} stratum {sc['none']:>8,}")
    ct = collections.Counter(t for ch in cp.chunks.values() for t in ch["tags"])
    cs = collections.Counter(stratum_of(ch["tags"], CHUNK_STRATA) for ch in cp.chunks.values())
    for t in CHUNK_TAGS:
        print(f"  {t:28} tagged {ct[t]:>8,}   stratum {cs.get(t, 0):>8,}")
    print(f"  {'none':28} {'':15} stratum {cs['none']:>8,}")
    fh = collections.Counter(min(ch["failure_signals"], 10) for ch in cp.chunks.values())
    print("  chunks by failure signals:", dict(sorted(fh.items())))


if __name__ == "__main__":
    # Re-import under the module's own name so the cached pickle refers to
    # corpus.C, not __main__.C, and loads from the other scripts.
    import corpus
    corpus.main()
