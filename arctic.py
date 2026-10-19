"""Thin client for the Arctic Shift API."""

import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://arctic-shift.photon-reddit.com/api"
UA = {"User-Agent": "foodnyc-tracker/0.1 (personal project)"}

# Arctic Shift caps limit at 100 on every search endpoint.
PAGE = 100


class ArcticError(RuntimeError):
    pass


def _get(path, params, attempt=0):
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:
        # 429 = rate limited, 422 = server-side query timeout. Both are worth retrying.
        if e.code in (422, 429, 500, 502, 503) and attempt < 5:
            wait = 5 * (2 ** attempt)
            print(f"    http {e.code}, retrying in {wait}s")
            time.sleep(wait)
            return _get(path, params, attempt + 1)
        raise
    except (OSError, http.client.HTTPException) as e:
        # Covers URLError, timeouts, and RemoteDisconnected / connection resets.
        # Over thousands of requests the server will drop a connection sooner
        # or later; that is transient and must not end the run.
        if attempt < 7:
            wait = min(5 * (2 ** attempt), 120)
            print(f"    {type(e).__name__}: {e}, retrying in {wait}s")
            time.sleep(wait)
            return _get(path, params, attempt + 1)
        raise

    # Errors come back as HTTP 200/422 with {"data": null, "error": "..."}
    if payload.get("error"):
        if attempt < 5:
            wait = 5 * (2 ** attempt)
            print(f"    api error '{payload['error']}', retrying in {wait}s")
            time.sleep(wait)
            return _get(path, params, attempt + 1)
        raise ArcticError(payload["error"])
    return payload["data"] or []


def newest_comments(subreddit, limit=PAGE, before=None):
    """Newest first. `before` (unix seconds) pages further back in time."""
    params = {"subreddit": subreddit, "limit": limit, "sort": "desc"}
    if before is not None:
        params["before"] = before
    return _get("comments/search", params)


def posts_by_id(bare_ids):
    """bare_ids: ids WITHOUT the t3_ prefix."""
    out = []
    ids = list(bare_ids)
    for i in range(0, len(ids), 50):
        out += _get("posts/ids", {"ids": ",".join(ids[i:i + 50])})
    return out


def comments_by_id(bare_ids):
    """bare_ids: ids WITHOUT the t1_ prefix."""
    out = []
    ids = list(bare_ids)
    for i in range(0, len(ids), 50):
        out += _get("comments/ids", {"ids": ",".join(ids[i:i + 50])})
    return out


def forward(fetch, start, pause=0.0):
    """Page forward through created_utc from `start` (inclusive), each item once.

    fetch(after) returns one page, oldest first, of items created strictly
    after `after`, or from the very first item when `after` is None. A
    `start` of None asks for that: Arctic answers HTTP 400 ("'after' must be
    a valid date") to a small number like 0 or -1, so an open start must
    leave the parameter out, never send 0.

    Yields (fresh, page) per page: the items not yielded before, and the
    page as fetched, whose newest is where a caller's cursor goes.

    `after` is exclusive, so asking for after = the page's newest would skip
    every item posted in that same second that did not fit on the page.
    Each request asks for after = newest - 1 instead, and the items already
    seen in that second are dropped. A page with nothing new means the end:
    unless it is a full page of one second already seen, which can only be
    more than a page of items in one second; those beyond the first page
    cannot be reached by time and are skipped, loudly.
    """
    after, boundary = (None if start is None else start - 1), set()
    while True:
        page = fetch(after)
        if not page:
            return
        # boundary holds every id seen in second after + 1, the only second
        # a new page can share with what came before.
        fresh = [x for x in page if x["id"] not in boundary]
        newest = max(x["created_utc"] for x in page)
        if not fresh:
            if len(page) < PAGE:
                return
            print(f"    more than {PAGE} items at {newest}; skipping the rest of that second")
            after, boundary = newest, set()
            continue
        yield fresh, page
        at_newest = {x["id"] for x in page if x["created_utc"] == newest}
        # Still in the same second as last time (the whole page sat in it):
        # what earlier pages saw there counts too.
        same_second = after is not None and newest == after + 1
        boundary = boundary | at_newest if same_second else at_newest
        after = newest - 1
        if pause:
            time.sleep(pause)


def all_thread_comments(bare_link_id, pause=1.0):
    """Every comment in one thread, paginated forward through created_utc."""
    out = {}

    def fetch(after):
        params = {"link_id": bare_link_id, "limit": PAGE, "sort": "asc"}
        if after is not None:
            params["after"] = after
        return _get("comments/search", params)
    # A short page is the last one here: one thread is never sparse enough
    # for the archive to return fewer than it has.
    for fresh, page in forward(fetch, None, pause):
        for c in fresh:
            out[c["id"]] = c
        if len(page) < PAGE:
            break
    return list(out.values())


def search_page(kind, subreddit, after=None, before=None, limit=PAGE):
    """One page of posts or comments for a subreddit, oldest first.

    kind: "posts" | "comments"
    after/before: unix seconds or YYYY-MM-DD
    """
    params = {"subreddit": subreddit, "limit": limit, "sort": "asc"}
    if after is not None:
        params["after"] = after
    if before is not None:
        params["before"] = before
    return _get(f"{kind}/search", params)
