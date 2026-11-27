"""Search: what a typed query means, and which places the comments back for it.

Three steps, and a model is in at most one of them.

  1. Match (the browser). The vocabulary below -- cuisines, areas, dishes and
     the commenters' own descriptors -- is sent whole, like /api/names, and
     matched locally on every keystroke.

  2. Understand (understand). When the vocabulary explains every word of a
     query, no model runs: "romantic italian in brooklyn" is two filters and
     a phrase. When a word is left over, a small model reads the query into
     a fixed shape (app/parse.py) and code resolves every name it returns
     against the same vocabulary. Its answer is kept for good, so the same
     words never pay twice.

  3. Retrieve and rank (retrieve). Filters and exclusions are SQL. The rest
     of the query is embedded and the nearest comments found; comments that
     knock a place are dropped; what is left is grouped by place and ranked
     by ONE number: how many different people wrote a matching comment.
     Every result carries that number and the comments it counts: the
     first few in full, and the id of every one, so the whole count can be
     opened (comments()). With nothing to embed, the rank is the board's
     own people count. Where the text cannot be matched by meaning (a city
     whose comments are not embedded, a provider or an index that did not
     answer) its words are matched as text instead, as the ledger's topic
     is, so what was typed still filters the list in every city.

Rules that hold throughout: results never wait on a model (mode=fast answers
from the vocabulary and from readings already kept, and the client asks for
mode=full only when a model could read more); a list ranked on words nobody
read says so (AS_TYPED);
a model interprets and never picks or ranks; nothing here is evidence
(search_parses and search_log are a cache and a log); the query and the
comments are untrusted text, bound into SQL and wrapped as data for the
model.

Every number marked TUNE was set from a first look at production and has
not been measured against real searches yet.
"""

import difflib
import functools
import logging
import os
import re
import threading
import time
import unicodedata
from collections import OrderedDict, deque
from dataclasses import dataclass, field

import psycopg2
import psycopg2.errors

import embedding
import subreddits

from . import parse as model_parse
from . import queries
from .db import connection, fetch_all, fetch_value, transaction
from .rankcache import RankCache

log = logging.getLogger("uvicorn.error")

# A dish or descriptor is vocabulary once this many mentions used it.      TUNE
TERM_MIN = 5
# A neighbourhood, likewise; and a place belongs to one when at least this
# share of the mentions that place it anywhere place it there.            TUNE
AREA_MIN = 5
AREA_SHARE = 0.2
# A place is filed under a cuisine it has no official label for when at
# least this many people, and this share of everyone who brought it up,
# tagged it so. On production the share splits cleanly: a real second
# cuisine is tagged by a fifth of a place's people or more (Rubirosa as
# Italian, L'Artusi as Italian), a stray tag by under a twentieth (three of
# Breads Bakery's 293 said pizza).                                         TUNE
CUISINE_TAG_MIN = 2
CUISINE_TAG_SHARE = 0.1
# How many nearest comments one search reads. A place's count can never
# exceed what falls inside this, so a very popular match is understated
# rather than the long tail read on every search.                          TUNE
NEAREST = int(os.environ.get("SEARCH_NEAREST", "500"))
# Comments less similar than this do not count as matching. Not calibrated:
# 0.0 keeps all NEAREST, so the cut is only the nearest-K until it is set
# from real query vectors (SEARCH_MIN_SIMILARITY).                         TUNE
MIN_SIMILARITY = float(os.environ.get("SEARCH_MIN_SIMILARITY", "0"))
EVIDENCE_PER_PLACE = 3
MAX_WORDS = 4                     # the longest vocabulary phrase looked for

# How long a vocabulary is served before asking whether the scoring views
# moved, and how long at most whatever they say (public.FACETS_MAX_AGE).
VOCAB_CHECK = 60
VOCAB_MAX_AGE = 1800

# Words that carry no meaning in a search box here, so they neither filter
# nor reach the model. This list never interprets a query: it only keeps
# "best pizza in brooklyn" from paying for a model call over "best" and
# "in". Anything that changes meaning ("not", "without", "near") is absent
# on purpose and goes to the model.
FILLER = frozenset("""
    a an the of in on at for to with and or
    best good great top favorite favourite
    restaurant restaurants place places spot spots food eats
    nyc ny
""".split())

FILTER_KINDS = ("cuisine", "area", "restaurant")
TEXT_KINDS = ("tag", "dish")


# --- words -------------------------------------------------------------------

def fold(text):
    """Case, apostrophes (straight and curly), accents and punctuation folded
    away, so "Katz’s" and "katzs", "Café" and "cafe" meet in one form."""
    s = re.sub(r"['’‘]", "", (text or "").lower())
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def name_key(text):
    """fold(), then what extract.py's normalize_entity drops from a stored
    key: "and", a leading "the", a trailing "restaurant" or "nyc". The same
    folding as the browser's (frontend/src/lib/search.ts normalize)."""
    s = " ".join(w for w in fold(text).split() if w != "and")
    if s.startswith("the "):
        s = s[4:]
    for suffix in (" restaurant", " nyc"):
        if s.endswith(suffix):
            s = s[:-len(suffix)]
    return s.strip()


def normalize(query):
    """A query as the cache and the log key it: case and spacing only.
    Punctuation stays, because it can carry meaning to the model."""
    return " ".join((query or "").lower().split())


def _variants(word):
    """A phrase with its last word's plural toggled, so "bagel" finds
    "bagels" and "steakhouses" finds "steakhouse"."""
    out = [word]
    if word.endswith("es") and len(word) > 4:
        out.append(word[:-2])
    if word.endswith("s") and len(word) > 3:
        out.append(word[:-1])
    else:
        out.append(word + "s")
    return out


# --- vocabulary --------------------------------------------------------------

@dataclass
class Term:
    kind: str                     # cuisine | area | tag | dish
    label: str                    # as shown: "Italian", "west village"
    n: int                        # places for a filter, mentions for text
    keys: frozenset = frozenset()  # the places a filter keeps; empty for text


@dataclass
class Vocabulary:
    """Everything one city's searches are matched against, built from the
    scoring views and kept per process (vocabulary())."""
    sub: str
    version: object
    terms: dict                   # kind -> {folded term: Term}
    names: dict                   # name_key -> entity_key
    labels: dict                  # entity_key -> display name
    boroughs: list
    built: float = field(default_factory=time.monotonic)
    checked: float = field(default_factory=time.monotonic)

    def lookup(self, phrase, kinds):
        """The first of `kinds` that knows `phrase` (already folded)."""
        for kind in kinds:
            for v in _variants(phrase):
                t = self.terms[kind].get(v)
                if t is not None:
                    return t
        return None

    def compact(self):
        """What the browser matches against: [label, n] rows by kind."""
        def rows(kind, limit):
            ts = sorted(self.terms[kind].values(), key=lambda t: (-t.n, t.label))
            return [[t.label, t.n] for t in ts[:limit]]
        return {"cuisines": rows("cuisine", 200), "areas": rows("area", 600),
                "dishes": rows("dish", 1500), "tags": rows("tag", 1500)}


def build_vocabulary(conn, sub, version):
    from .routers.ledger import display_name
    places = queries.vocab_places(conn, sub, fetch_all)
    known = {p["entity_key"] for p in places}

    # Names: the most talked-about place wins a spelling two places share.
    names, labels = {}, {}
    for p in sorted(places, key=lambda p: (-p["people"], p["entity_key"])):
        labels[p["entity_key"]] = display_name(p["official_name"], p["entity_key"])
        for spelling in [p["entity_key"], p["official_name"], *p["aliases"]]:
            k = name_key(spelling)
            if k:
                names.setdefault(k, p["entity_key"])

    # Cuisines: the city's label, plus places commenters tagged with it.
    cuisine_keys, cuisine_label = {}, {}
    for p in places:
        if p["cuisine"] and fold(p["cuisine"]):
            f = fold(p["cuisine"])
            cuisine_label.setdefault(f, p["cuisine"])
            cuisine_keys.setdefault(f, set()).add(p["entity_key"])
    lowered = {label.lower() for label in cuisine_label.values()}
    people = {p["entity_key"]: p["people"] for p in places}
    for r in queries.vocab_cuisine_tags(conn, sub, lowered, CUISINE_TAG_MIN, fetch_all):
        f = fold(r["term"])
        if (f in cuisine_keys and r["entity_key"] in known
                and r["n"] >= CUISINE_TAG_SHARE * people[r["entity_key"]]):
            cuisine_keys[f].add(r["entity_key"])
    cuisines = {f: Term("cuisine", cuisine_label[f], len(keys), frozenset(keys))
                for f, keys in cuisine_keys.items()}

    # Areas: boroughs from the official record, neighbourhoods from what
    # commenters wrote. A place mentioned once "near soho" is not in SoHo,
    # hence the share.
    area_keys, area_label, boroughs = {}, {}, set()
    for p in places:
        for b in p["boroughs"] or []:
            if fold(b):
                boroughs.add(b)
                area_label.setdefault(fold(b), b)
                area_keys.setdefault(fold(b), set()).add(p["entity_key"])
    hinted, total = {}, {}
    rows = [r for r in queries.vocab_areas(conn, sub, fetch_all)
            if r["entity_key"] in known and fold(r["term"])]
    for r in rows:
        hinted[r["entity_key"]] = hinted.get(r["entity_key"], 0) + r["n"]
        total[fold(r["term"])] = total.get(fold(r["term"]), 0) + r["n"]
    for r in rows:
        f = fold(r["term"])
        if total[f] >= AREA_MIN and r["n"] / hinted[r["entity_key"]] >= AREA_SHARE:
            area_label.setdefault(f, r["term"])
            area_keys.setdefault(f, set()).add(r["entity_key"])
    areas = {f: Term("area", area_label[f], len(keys), frozenset(keys))
             for f, keys in area_keys.items()}

    # Dishes and descriptors are text to search for, not filters. One that
    # is also a cuisine or an area is that instead.
    text = {"tag": {}, "dish": {}}
    for r in queries.vocab_terms(conn, sub, TERM_MIN, fetch_all):
        f = fold(r["term"])
        if not f or f in cuisines or f in areas or f in FILLER:
            continue
        seen = text[r["kind"]].get(f)
        if seen is None:
            text[r["kind"]][f] = Term(r["kind"], r["term"], r["n"])
        else:
            seen.n += r["n"]
    for f in list(text["dish"]):
        if f in text["tag"]:
            text["tag"][f].n += text["dish"].pop(f).n

    return Vocabulary(sub=sub, version=version,
                      terms={"cuisine": cuisines, "area": areas, **text},
                      names=names, labels=labels, boroughs=sorted(boroughs))


# How long a request waits for another request's build of the same city's
# vocabulary. A waiter holds no connection (the search routes take none), so
# this can outlast one statement; past it the answer is 503, try again.
VOCAB_WAIT = 20.0
# One entry per city, never expiring here: a vocabulary is replaced in the
# background (_refresh), not dropped. The cache is what makes the first build
# one computation that every request for that city waits on and receives,
# result or failure alike, with no lock held while its queries run, so one
# city's build never blocks another's search (app/rankcache.py).
_VOCAB = RankCache(float("inf"), 64, VOCAB_WAIT,
                   timeout_error=lambda: psycopg2.errors.QueryCanceled(
                       "waited too long for the search vocabulary"))
_refreshing = set()
_refreshing_lock = threading.Lock()      # guards the set only; never held over a query


def _load(sub):
    with connection() as conn:
        version = queries.facets_version(conn, fetch_value)
        return build_vocabulary(conn, sub, version)


def _refresh(sub, old):
    """Runs on its own thread: rebuild when the scoring views took in new
    mentions or the copy is old, otherwise just note that it was checked."""
    try:
        with connection() as conn:
            version = queries.facets_version(conn, fetch_value)
        if version != old.version or time.monotonic() - old.built > VOCAB_MAX_AGE:
            _VOCAB.put(sub, _load(sub))
        else:
            old.checked = time.monotonic()
    except Exception as e:
        log.warning("search vocabulary refresh for %s failed: %s: %s", sub, type(e).__name__, e)
        old.checked = time.monotonic()      # try again in VOCAB_CHECK
    finally:
        with _refreshing_lock:
            _refreshing.discard(sub)


def vocabulary(sub):
    """The city's vocabulary. The first request builds it (several scans of
    the city's mentions) and every request that arrives meanwhile waits for
    that one build and gets what it got, its failure included, instead of
    queueing to run the scans again. After that a stale copy is served while
    a thread replaces it, so no later search waits on those scans."""
    v = _VOCAB.get(sub, lambda: _load(sub))
    if time.monotonic() - v.checked > VOCAB_CHECK:
        with _refreshing_lock:
            start = sub not in _refreshing
            _refreshing.add(sub)
        if start:
            threading.Thread(target=_refresh, args=(sub, v), daemon=True).start()
    return v


def forget():
    """Drop every cache in this module. For tests, which swap databases
    under a running process."""
    _VOCAB.clear()
    _RETRIEVED.clear()
    _parses.clear()
    _embed.cache_clear()
    for w in (REQUESTS, MODEL_CALLS, MODEL_CALLS_ALL):
        w.clear()


# --- understand --------------------------------------------------------------

@dataclass
class Filter:
    kind: str                     # cuisine | area | restaurant
    label: str
    keys: frozenset


@dataclass
class Parsed:
    """A query, understood: what to filter on, what to leave out, and what
    is left to match against the meaning of comments."""
    search_text: str = ""
    include: list = field(default_factory=list)
    exclude: list = field(default_factory=list)
    ignored: list = field(default_factory=list)   # exclusions that named nothing known
    no_data: list = field(default_factory=list)
    hard: bool = False
    # vocabulary: explained without a model. model / cache: the model's
    # reading, new or kept. unparsed: mode=fast with words left over and a
    # model to ask, so the whole query is the text until mode=full reads it.
    # fallback: the model was needed and not had.
    source: str = "vocabulary"
    needs_model: bool = False

    def as_json(self):
        def fs(xs):
            return [{"type": f.kind, "value": f.label} for f in xs]
        return {"search_text": self.search_text, "include": fs(self.include),
                "exclude": fs(self.exclude), "ignored": self.ignored,
                "no_data": self.no_data, "hard": self.hard}


def segment(query, vocab):
    """Explain `query` from the vocabulary alone: (Parsed, leftover words).

    Longest phrase first, so "west village" is an area and not a leftover
    "west". A filler word alone is skipped; inside a known phrase ("salt and
    pepper shrimp") it is part of the phrase. Words nothing explains are
    returned for the caller to decide on.
    """
    words = fold(query).split()
    parts, leftover, i = [], [], 0          # parts: (words, Term | None | "filler")
    while i < len(words):
        for size in range(min(MAX_WORDS, len(words) - i), 0, -1):
            phrase = " ".join(words[i:i + size])
            if size == 1 and phrase in FILLER:
                parts.append((phrase, "filler"))
                break
            term = vocab.lookup(phrase, ("cuisine", "area") + TEXT_KINDS)
            if term is not None:
                parts.append((phrase, term))
                break
        else:
            size = 1
            parts.append((words[i], None))
            leftover.append(words[i])
        i += size

    generic = any(isinstance(t, Term) for _, t in parts)
    if leftover and not generic:
        # Nothing but unknown words: a restaurant's name, if it is one. With
        # a known word in it ("thai diner") the query stays a description;
        # the box's own name matches already offer the place.
        key = vocab.names.get(name_key(query))
        if key is not None:
            return Parsed(include=[Filter("restaurant", vocab.labels.get(key, key),
                                          frozenset([key]))]), []

    include, text = [], []
    for phrase, term in parts:
        if isinstance(term, Term) and term.kind in FILTER_KINDS:
            include.append(Filter(term.kind, term.label, term.keys))
        else:
            text.append((phrase, term == "filler"))
    # Filler inside the phrase reads naturally to the embedding ("good for
    # groups"); at either end it is only noise.
    while text and text[0][1]:
        text.pop(0)
    while text and text[-1][1]:
        text.pop()
    return Parsed(search_text=" ".join(p for p, _ in text), include=include), leftover


def _resolve(kind, value, vocab):
    """The Filter a name from the model stands for, or None. The declared
    kind is tried first, then the others, because "Chinatown" called a
    cuisine is still an area. Exact first; then a near spelling of the
    declared kind only, so a typo resolves and a guess does not."""
    order = (kind,) + tuple(k for k in FILTER_KINDS if k != kind)
    for k in order:
        if k == "restaurant":
            key = vocab.names.get(name_key(value))
            if key is not None:
                return Filter(k, vocab.labels.get(key, key), frozenset([key]))
        else:
            t = vocab.lookup(fold(value), (k,))
            if t is not None:
                return Filter(k, t.label, t.keys)
    if kind == "restaurant":
        want = name_key(value)
        pool = [n for n in vocab.names if n[:1] == want[:1] and abs(len(n) - len(want)) <= 2]
        near = difflib.get_close_matches(want, pool, n=1, cutoff=0.88) if want else []
        if near:
            key = vocab.names[near[0]]
            return Filter(kind, vocab.labels.get(key, key), frozenset([key]))
    else:
        near = difflib.get_close_matches(fold(value), list(vocab.terms[kind]), n=1, cutoff=0.88)
        if near:
            t = vocab.terms[kind][near[0]]
            return Filter(kind, t.label, t.keys)
    return None


def resolve(answer, vocab, query, source):
    """The model's answer (parse.clean's shape) as a Parsed.

    A wanted thing that names nothing known joins the search text: "ramen"
    called a cuisine still finds ramen by meaning. An unwanted thing that
    names nothing known cannot be excluded, and is reported rather than
    dropped in silence.
    """
    p = Parsed(search_text=answer["search_text"], no_data=list(answer["no_data"]),
               hard=answer["hard"], source=source)
    for f in answer["include"]:
        hit = _resolve(f["type"], f["value"], vocab)
        if hit is not None:
            p.include.append(hit)
        elif fold(f["value"]) not in fold(p.search_text):
            p.search_text = f"{p.search_text} {f['value']}".strip()
    for f in answer["exclude"]:
        hit = _resolve(f["type"], f["value"], vocab)
        if hit is not None:
            p.exclude.append(hit)
        else:
            p.ignored.append(f["value"])
    if not (p.search_text or p.include or p.exclude):
        p.search_text = query       # an empty reading of a non-empty query
    return p


class Window:
    """At most `limit` events per `seconds` for each key, per process. With
    two workers a caller gets up to twice that, which is still a ceiling."""

    def __init__(self, limit, seconds):
        self.limit, self.seconds = limit, seconds
        self._hits = {}
        self._lock = threading.Lock()

    def allow(self, key):
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > 10_000:        # a scan of addresses: start over
                self._hits.clear()
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] > self.seconds:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def clear(self):
        with self._lock:
            self._hits.clear()


# Searches per address, and model calls per address and in all. The last is
# the spending limit: past it every new query falls back to plain text until
# the hour moves on. Kept parses never count.                             TUNE
REQUESTS = Window(int(os.environ.get("SEARCH_RATE_PER_MIN", "40")), 60)
MODEL_CALLS = Window(int(os.environ.get("SEARCH_PARSE_PER_MIN", "10")), 60)
MODEL_CALLS_ALL = Window(int(os.environ.get("SEARCH_PARSE_PER_HOUR", "1000")), 3600)

_parses = OrderedDict()             # (sub, query, model, prompt_hash) -> answer
_parses_lock = threading.Lock()
PARSES_KEPT = 2000


def _remember(key, answer):
    with _parses_lock:
        _parses[key] = answer
        _parses.move_to_end(key)
        while len(_parses) > PARSES_KEPT:
            _parses.popitem(last=False)


def _kept(key):
    """A parse from memory, else from search_parses, else None. A missing
    table or an unreadable row reads as "not kept": the cache is a saving,
    never a requirement."""
    with _parses_lock:
        if key in _parses:
            _parses.move_to_end(key)
            return _parses[key]
    try:
        with connection() as conn:
            row = queries.search_parse_get(conn, *key, fetch_value)
        answer = model_parse.clean(row) if row is not None else None
    except (psycopg2.Error, model_parse.ParseFailed):
        return None
    if answer is not None:
        _remember(key, answer)
    return answer


def _keep(key, answer):
    _remember(key, answer)
    try:
        with connection() as conn:
            queries.search_parse_put(conn, *key, answer)
    except psycopg2.Error as e:
        # A read-only session (the local run, CLAUDE.md) or a database
        # without the table: the answer still serves this process.
        log.debug("search parse not stored: %s", type(e).__name__)


def understand(sub, query, mode, vocab, caller=None):
    """What `query` means. mode=fast never waits on a model; mode=full asks
    one when the vocabulary leaves words unexplained.

    Both modes use a reading that was already kept, and mode=fast only says
    `needs_model` when there is a model to ask, so a second pass is made
    only when it can change the answer: a repeated query, and any query on a
    deployment without the key, is one request.
    """
    parsed, leftover = segment(query, vocab)
    if not leftover:
        return parsed
    # No filters from a half-understood query: "not italian" must not show
    # only Italian places while the model is still reading it. The whole
    # query is the text, and run() tells the reader it was matched as typed.
    whole = Parsed(search_text=" ".join(query.split()), source="fallback")
    system = model_parse.system_prompt(
        sub, [t.label for t in vocab.terms["cuisine"].values()], vocab.boroughs)
    key = (sub, normalize(query), model_parse.MODEL, model_parse.prompt_hash(system))
    answer = _kept(key)
    if answer is not None:
        return resolve(answer, vocab, query, "cache")
    if not model_parse.api_key():
        return whole
    if mode == "fast":
        whole.source, whole.needs_model = "unparsed", True
        return whole
    if not (MODEL_CALLS.allow(caller) and MODEL_CALLS_ALL.allow("all")):
        return whole
    try:
        answer = model_parse.ask(system, normalize(query))
    except model_parse.ParseUnavailable:
        return whole
    except model_parse.ParseFailed as e:
        log.warning("search parse failed: %s", e)
        return whole
    _keep(key, answer)
    return resolve(answer, vocab, query, "model")


# --- retrieve ----------------------------------------------------------------

@functools.lru_cache(maxsize=1024)
def _embed(text):
    """The query vector as a pgvector literal. Kept per process: popular
    searches repeat, and the fast and full passes of one search usually
    embed the same words. A failure raises and is not kept."""
    return embedding.to_pgvector(embedding.embed_query(text))


# Reasons the semantic half cannot run that are about this deployment and
# not the query: no embeddings table (a database without pgvector), or a
# pgvector too old to know the scan setting.
_NO_VECTORS = (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedObject,
               psycopg2.errors.UndefinedFunction, psycopg2.errors.InvalidParameterValue)

NO_DATA_WORDS = {"price": "prices", "hours": "opening hours",
                 "reservations": "reservations or availability",
                 "party_size": "what size of group a place takes",
                 "diet": "allergies or dietary needs"}

# Said whenever the words were matched without having been read (source
# unparsed or fallback): a list for "not italian" that leads with Italian
# places must not pass for an answer to it.
AS_TYPED = ("These words were matched as typed, without being read for what they "
            "mean, so a word like “not” or “without” leaves nothing out.")

# How long one retrieval is kept and shared. The fast and full passes of one
# search often ask for the same thing (the model was not had, or read the
# query as the vocabulary did), and so do the many people typing "date
# night": the second asker gets the first one's rows instead of another
# embedding call and another vector scan. Derived and short-lived, like the
# ledger's rankings (queries.LEDGER_CACHE).                              TUNE
RETRIEVED_TTL = 60.0
RETRIEVED_ENTRIES = 128
RETRIEVED_WAIT = 15.0
_RETRIEVED = RankCache(RETRIEVED_TTL, RETRIEVED_ENTRIES, RETRIEVED_WAIT,
                       timeout_error=lambda: psycopg2.errors.QueryCanceled(
                           "waited too long for another request's search"))


class _NoMeaning(Exception):
    """Matching by meaning cannot run for this search. `why` is city (only
    the home city's comments are embedded), vectors (this database has
    none), provider (the embedding call failed) or database (the vector
    query failed or timed out); the last two may work a moment later."""

    def __init__(self, why):
        super().__init__(why)
        self.why = why


def _filters(parsed):
    """(include, exclude, show_chains) as queries.py takes them, in tuples
    so they can key a cache. Filters of one kind are alternatives ("italian
    or french"); different kinds must all hold ("italian" and "in
    brooklyn")."""
    by_kind = {}
    for f in parsed.include:
        by_kind.setdefault(f.kind, set()).update(f.keys)
    exclude = set()
    for f in parsed.exclude:
        exclude |= f.keys
    named = "restaurant" in by_kind
    return (tuple(tuple(sorted(by_kind[k])) for k in sorted(by_kind)),
            tuple(sorted(exclude)), named)


def _semantic(sub, text, include, exclude, named, limit):
    """Nearest comments, grouped by place and ranked by how many different
    people wrote one: (ranked, total). Every place carries the mention of
    each comment it counts, nearest first, so its number can be opened in
    full. Raises _NoMeaning when the semantic half cannot run here."""
    if sub != subreddits.HOME:
        raise _NoMeaning("city")
    try:
        vec = _embed(text)
    except (embedding.EmbedError, ValueError) as e:
        log.warning("search embedding failed: %s: %s", type(e).__name__, str(e)[:200])
        raise _NoMeaning("provider") from None
    try:
        # The connection is taken after the embedding call, so a slow
        # provider holds none.
        with connection() as conn, transaction(conn):
            rows = queries.semantic_matches(conn, sub, vec, NEAREST, MIN_SIMILARITY,
                                            include, exclude, named, fetch_all)
    except _NO_VECTORS as e:
        log.warning("search has no vectors to read: %s", type(e).__name__)
        raise _NoMeaning("vectors") from None
    except psycopg2.Error as e:
        # A statement timeout on a cold index, a dropped connection: the
        # words can still be matched as text, which is an answer, where a
        # 503 is none. The pool being busy (PoolTimeout) is not caught: the
        # fallback would need a connection too.
        log.warning("search vector query failed: %s: %s", type(e).__name__, str(e).strip()[:200])
        raise _NoMeaning("database") from None

    places = {}
    for r in rows:
        g = places.setdefault(r["entity_key"], {"people": set(), "best": 0.0, "by_comment": {}})
        g["people"].add(r["person"])
        g["best"] = max(g["best"], r["similarity"])
        # One piece of evidence per comment, however many spellings of the
        # place it used.
        seen = g["by_comment"].get(r["comment_id"])
        if seen is None or r["mention_id"] < seen[1]:
            g["by_comment"][r["comment_id"]] = (r["similarity"], r["mention_id"])
    ranked = sorted(places.items(), key=lambda kv: (-len(kv[1]["people"]), -kv[1]["best"], kv[0]))
    top = [{"entity_key": k, "people": len(g["people"]), "best_similarity": round(g["best"], 4),
            "mention_ids": [m for _, m in sorted(g["by_comment"].values(),
                                                 key=lambda sm: (-sm[0], sm[1]))]}
           for k, g in ranked[:limit]]
    return top, len(ranked)


def text_words(text):
    """The words of `text` to look for as typed when it cannot be matched by
    meaning: lower case, punctuation at either end dropped, filler left out,
    each once. Accents and inner apostrophes stay, because the comments'
    own words have them."""
    out = []
    for w in text.lower().split():
        w = w.strip(".,;:!?\"“”()[]")
        if w and w not in FILLER and w not in out:
            out.append(w)
    return out


def _retrieve(sub, text, include, exclude, named, limit):
    """The ranked places for one retrieval, with the comments first shown
    for each. Shared between requests through _RETRIEVED, so nothing here
    may be changed by a caller."""
    from .routers.ledger import display_name
    semantic, ranked_by, why = "none", "people", None
    top, total = None, 0
    if text:
        try:
            top, total = _semantic(sub, text, include, exclude, named, limit)
            semantic, ranked_by = "ok", "matching_people"
        except _NoMeaning as e:
            semantic, why = "unavailable", e.why

    with connection() as conn:
        words = text_words(text) if semantic == "unavailable" else []
        if words:
            # The words still filter the list, as the ledger's topic match
            # does in every city: places by how many different people used
            # all of them about the place.
            rows = queries.text_matches(conn, sub, words, include, exclude, named, limit, fetch_all)
            top = [{"entity_key": r["entity_key"], "people": r["people"],
                    "best_similarity": None, "mention_ids": r["mention_ids"]} for r in rows]
            total = rows[0]["total"] if rows else 0
            semantic, ranked_by = "text", "matching_people"
        if top is None:
            rows, total = queries.search_board(conn, sub, include, exclude, named, limit,
                                               fetch_all, fetch_value)
            # The board's count is everyone who brought the place up, and
            # the row opens the place, where all of those comments are.
            top = [{"entity_key": r["entity_key"], "people": r["people"],
                    "best_similarity": None, "mention_ids": None} for r in rows]
            evidence = queries.board_evidence(conn, sub, [t["entity_key"] for t in top],
                                              EVIDENCE_PER_PLACE, fetch_all)
        else:
            evidence = queries.search_evidence(
                conn, sub, [m for t in top for m in t["mention_ids"][:EVIDENCE_PER_PLACE]], fetch_all)
        keys = [t["entity_key"] for t in top]
        info = {r["entity_key"]: r for r in queries.search_places(conn, sub, keys, fetch_all)}
        hoods = {r["entity_key"]: r["name"]
                 for r in queries.top_neighborhoods(conn, sub, keys, fetch_all)}

    by_place = {}
    for e in evidence:
        by_place.setdefault(e["entity_key"], {})[e["mention_id"]] = e
    items = []
    for t in top:
        k, i = t["entity_key"], info.get(t["entity_key"], {})
        mine = by_place.get(k, {})
        comments = ([mine[m] for m in t["mention_ids"][:EVIDENCE_PER_PLACE] if m in mine]
                    if t["mention_ids"] is not None
                    else sorted(mine.values(), key=lambda e: e["rn"]))
        items.append({"entity_key": k, "name": display_name(i.get("official_name"), k),
                      "cuisine": i.get("cuisine"), "borough": i.get("borough"),
                      "neighborhood": hoods.get(k), "people": t["people"],
                      "total_people": i.get("total_people"),
                      "best_similarity": t["best_similarity"],
                      "mention_ids": t["mention_ids"], "comments": comments})
    return {"semantic": semantic, "ranked_by": ranked_by, "total": total,
            "items": items, "why": why}


def retrieve(sub, parsed, limit):
    """The places for a Parsed query, each with its count and its comments,
    and the sentences that say how far the answer can be trusted."""
    include, exclude, named = _filters(parsed)
    key = (sub, parsed.search_text, include, exclude, named, limit)
    found = _RETRIEVED.get(key, lambda: _retrieve(sub, parsed.search_text, include, exclude,
                                                  named, limit))
    why = found["why"]
    if why in ("provider", "database"):
        # Whoever was waiting on this shares it; the next search tries the
        # provider or the index again rather than living with a hiccup for
        # a minute.
        _RETRIEVED.discard(key)
    out = {k: v for k, v in found.items() if k != "why"}
    semantic, items = out["semantic"], out["items"]

    notes = []
    if parsed.source in ("unparsed", "fallback") and semantic in ("ok", "text"):
        notes.append(AS_TYPED)
    if why is not None:
        missing = ("Matching by meaning is not available for this city yet" if why == "city"
                   else "Matching by meaning is not available right now")
        if semantic == "text":
            notes.append(missing + ", so these are the places whose comments use the words searched for.")
        else:
            notes.append(missing + ", so this is the most talked-about places"
                         + (" for the filters shown." if parsed.include or parsed.exclude else "."))
    for x in parsed.ignored:
        notes.append(f"Could not find “{x}” to leave out.")
    if parsed.no_data:
        words = [NO_DATA_WORDS[x] for x in parsed.no_data]
        notes.append("This site has no data on " + " or ".join(words)
                     + ". Results are only what commenters happened to say.")
    if parsed.hard:
        notes.append("This is more of a question than a search. These are the closest "
                     "matches, not an answer.")
    if semantic == "ok" and not items:
        notes.append("No comments match that closely enough.")
    elif semantic == "text" and not items:
        notes.append("No comments use those words.")
    elif not items:
        notes.append("No places match those filters.")
    out["notes"] = notes
    return out


def comments(sub, mention_ids):
    """The comments behind a result's count that the search itself did not
    load, in the order asked for. Read through mention_weights, so only the
    city's live mentions answer, whatever ids are sent."""
    with connection() as conn:
        rows = {r["mention_id"]: r for r in queries.search_evidence(conn, sub, mention_ids, fetch_all)}
    return [rows[m] for m in dict.fromkeys(mention_ids) if m in rows]


def run(sub, query, mode, limit, caller=None):
    """One search, start to finish. Holds no database connection while it
    waits on the model or the embedding provider."""
    started = time.monotonic()
    vocab = vocabulary(sub)
    parsed = understand(sub, query, mode, vocab, caller)
    out = retrieve(sub, parsed, limit)
    out.update(query=query, mode=mode, source=parsed.source,
               needs_model=parsed.needs_model, parse=parsed.as_json())
    if parsed.needs_model:
        # A provisional answer: the browser asks again in full at once, and
        # that request is the row for this search. Logging both counted
        # every such search twice.
        return out
    ms = int((time.monotonic() - started) * 1000)
    try:
        with connection() as conn:
            queries.search_log_put(conn, sub, normalize(query), mode, parsed.source,
                                   out["parse"], len(out["items"]), ms)
    except psycopg2.Error as e:
        # As _keep: a read-only session or no table. A search is never
        # failed for not being logged.
        log.debug("search not logged: %s", type(e).__name__)
    return out
