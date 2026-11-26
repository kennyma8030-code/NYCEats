"""A short-lived, bounded, per-process cache of computed rankings.

A list is read a page at a time, and every page of the ledger used to re-run
the whole window aggregation over a city's mentions only to keep 50 rows of
it: a reader scrolling two thousand places cost forty full recomputations.
The ranking is the same for every page of one list, so it is computed once
and the pages are cut from it.

This is a cache of derived data, never a store of it: an entry is rebuilt
from the database whenever it is missing or old, and losing one costs only
the query that rebuilds it. Each uvicorn worker keeps its own.

Sync endpoints run in a threadpool, so the entries sit behind a lock. That
lock is never held while a ranking is computed, or one slow list would stall
every other request; instead each key gets its own lock for the length of
its computation, so concurrent requests for the same list wait for the one
query rather than each running it (a stampede on the production database).
"""

import threading
import time
from collections import OrderedDict


class RankCache:
    """get(key, compute) returns the value cached under `key`, or calls
    compute() once, caches what it returns for `ttl` seconds and returns
    that. At most `max_entries` are kept; the least recently used goes
    first, after anything expired."""

    def __init__(self, ttl, max_entries, clock=time.monotonic):
        self.ttl = ttl
        self.max_entries = max_entries
        self.clock = clock
        # Turned off by tests that need every request to see the database
        # as it is now. compute() then runs on every call.
        self.enabled = True
        self._lock = threading.Lock()
        self._entries = OrderedDict()      # key -> (computed_at, value), LRU last
        self._computing = {}               # key -> lock held while computing it

    def _fresh(self, key):
        """The cached value for `key` if it has not expired, else None.
        Call with self._lock held."""
        hit = self._entries.get(key)
        if hit is None:
            return None
        if self.clock() - hit[0] >= self.ttl:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return hit

    def get(self, key, compute):
        if not self.enabled:
            return compute()
        with self._lock:
            hit = self._fresh(key)
            if hit is not None:
                return hit[1]
            key_lock = self._computing.setdefault(key, threading.Lock())
        with key_lock:
            # Whoever held the key lock before us may have just cached it.
            with self._lock:
                hit = self._fresh(key)
                if hit is not None:
                    return hit[1]
            try:
                value = compute()
                with self._lock:
                    self._entries[key] = (self.clock(), value)
                    self._entries.move_to_end(key)
                    self._evict()
                return value
            finally:
                # Waiters still hold this lock object and find the entry once
                # they get it; a request arriving later finds the entry first.
                # If compute() raised, each waiter runs it again in turn.
                with self._lock:
                    if self._computing.get(key) is key_lock:
                        del self._computing[key]

    def _evict(self):
        """Drop expired entries, then the least recently used beyond the
        bound. Call with self._lock held."""
        now = self.clock()
        for k in [k for k, (at, _) in self._entries.items() if now - at >= self.ttl]:
            del self._entries[k]
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def forget(self, key):
        """Drop one entry, so the next get() computes it afresh."""
        with self._lock:
            self._entries.pop(key, None)

    def clear(self):
        with self._lock:
            self._entries.clear()

    def __len__(self):
        with self._lock:
            return len(self._entries)
