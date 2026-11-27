"""A short-lived, bounded, per-process cache of computed rankings.

A list is read a page at a time, and every page of the ledger used to re-run
the whole window aggregation over a city's mentions only to keep 50 rows of
it: a reader scrolling two thousand places cost forty full recomputations.
The ranking is the same for every page of one list, so it is computed once
and the pages are cut from it.

This is a cache of derived data, never a store of it: an entry is rebuilt
from the database whenever it is missing or old, and losing one costs only
the query that rebuilds it. Each uvicorn worker keeps its own (the Procfile
runs two), so two pages of one list served by different workers can come
from rankings computed up to the TTL apart; the client already tolerates a
list that moves while it is read (frontend/src/lib/paging.ts).

Sync endpoints run in a threadpool, so the entries sit behind a lock. That
lock is never held while a ranking is computed, or one slow list would stall
every other request. Instead a computation in progress is shared: the first
request for a key runs it, and every request for the same key that arrives
meanwhile waits for that one result -- its value or its exception -- rather
than running the query again (a stampede on the production database). A
waiter gives up after `wait` seconds, because it holds a pooled connection
while it waits.
"""

import threading
import time
from collections import OrderedDict


class _Flight:
    """One computation in progress, and what it ended with."""

    def __init__(self):
        self.done = threading.Event()
        self.value = None
        self.error = None


class RankCache:
    """get(key, compute) returns the value cached under `key`, or the result
    of one compute() shared by every caller that asked while it ran, cached
    for `ttl` seconds. At most `max_entries` are kept; the least recently
    used goes first, after anything expired. A caller that waits longer than
    `wait` for another's computation gets timeout_error() raised instead."""

    def __init__(self, ttl, max_entries, wait, timeout_error=TimeoutError, clock=time.monotonic):
        self.ttl = ttl
        self.max_entries = max_entries
        self.wait = wait
        self.timeout_error = timeout_error
        self.clock = clock
        self._lock = threading.Lock()
        self._entries = OrderedDict()      # key -> (computed_at, value), LRU last
        self._flights = {}                 # key -> _Flight while it is computed

    def get(self, key, compute):
        with self._lock:
            hit = self._fresh(key)
            if hit is not None:
                return hit[1]
            flight = self._flights.get(key)
            leader = flight is None
            if leader:
                flight = self._flights[key] = _Flight()
        if not leader:
            if not flight.done.wait(self.wait):
                raise self.timeout_error()
            if flight.error is not None:
                raise flight.error
            return flight.value
        try:
            flight.value = compute()
        except BaseException as e:
            flight.error = e
            raise
        finally:
            # Under one lock with the store, so a request arriving after this
            # finds either the entry or, after a failure, no flight, and then
            # starts a computation of its own: a failure is never cached.
            with self._lock:
                if flight.error is None:
                    self._entries[key] = (self.clock(), flight.value)
                    self._entries.move_to_end(key)
                    self._evict()
                del self._flights[key]
            flight.done.set()
        return flight.value

    def peek(self, key):
        """The cached value for `key`, or None: never computes."""
        with self._lock:
            hit = self._fresh(key)
            return None if hit is None else hit[1]

    def put(self, key, value):
        """Store a value computed elsewhere, as if get() had just computed
        it: for a caller that replaces an entry in the background while the
        old one is still being served (search's vocabulary)."""
        with self._lock:
            self._entries[key] = (self.clock(), value)
            self._entries.move_to_end(key)
            self._evict()

    def discard(self, key):
        """Forget `key`, for a value that was worth sharing with the requests
        waiting on it and is not worth serving to later ones."""
        with self._lock:
            self._entries.pop(key, None)

    def _fresh(self, key):
        """The (computed_at, value) cached for `key` if it has not expired,
        else None. Call with self._lock held."""
        hit = self._entries.get(key)
        if hit is None:
            return None
        if self.clock() - hit[0] >= self.ttl:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return hit

    def _evict(self):
        """Drop expired entries, then the least recently used beyond the
        bound. Call with self._lock held."""
        now = self.clock()
        for k in [k for k, (at, _) in self._entries.items() if now - at >= self.ttl]:
            del self._entries[k]
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def clear(self):
        with self._lock:
            self._entries.clear()

    def __len__(self):
        with self._lock:
            return len(self._entries)
