"""Thin client for the Arctic Shift API."""

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
    except urllib.error.URLError as e:
        if attempt < 5:
            wait = 5 * (2 ** attempt)
            print(f"    {e.reason}, retrying in {wait}s")
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


def newest_comments(subreddit, limit=PAGE):
    return _get("comments/search",
                {"subreddit": subreddit, "limit": limit, "sort": "desc"})


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


def all_thread_comments(bare_link_id, pause=1.0):
    """Every comment in one thread, paginated forward through created_utc."""
    out, after = {}, None
    while True:
        params = {"link_id": bare_link_id, "limit": PAGE, "sort": "asc"}
        if after is not None:
            params["after"] = after
        page = _get("comments/search", params)
        fresh = [c for c in page if c["id"] not in out]
        for c in page:
            out[c["id"]] = c
        # Short page = last page. No new ids = we're stuck on a timestamp tie.
        if len(page) < PAGE or not fresh:
            break
        after = max(c["created_utc"] for c in page)
        time.sleep(pause)
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
