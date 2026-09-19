"""A second, independent record of r/FoodNYC comments, from Reddit's own feed.

The whole pipeline rests on Arctic Shift. If it goes down, or rate-limits us,
or changes its API, comments stop arriving and there is no way to recover the
ones we were dark for -- the poller's cursor only walks forward over what the
archive still has.

Reddit's Atom feed needs no key, no OAuth and no third party. It carries the
newest 25 comments and nothing else: no score, no parent, no depth. That is
too thin to score or extract from, and this does not try. It writes to
rss_threads / rss_comments, and nothing reads those tables. It is insurance.

    python rss.py            -> poll every 5 minutes
    python rss.py --once     -> one cycle

Inside poller.py it runs as a daemon thread, so the fallback keeps collecting
through a long backfill -- which is exactly when the main path is not polling.
"""

import argparse
import html
import http.client
import os
import re
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

import db

SUBREDDIT = "FoodNYC"
INTERVAL = 5 * 60
LIMIT = 25              # the feed's own page size; asking for more changes nothing
UA = {"User-Agent": "foodnyc-tracker/0.1 (personal project)"}
NS = {"a": "http://www.w3.org/2005/Atom"}
SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rss_schema.sql")

# /r/FoodNYC/comments/1wkw8ju/some_slug/paudm96/ -> the post id and the slug,
# which is everything needed to rebuild the thread's own permalink.
_LINK = re.compile(r"/comments/([a-z0-9]+)/([^/]*)/")
_TAG = re.compile(r"<[^>]+>")
_COMMENT = re.compile(r"<!--.*?-->", re.S)


def feed_url(subreddit=SUBREDDIT, limit=LIMIT):
    return f"https://www.reddit.com/r/{subreddit}/comments/.rss?limit={limit}"


def fetch(subreddit=SUBREDDIT, limit=LIMIT, attempt=0):
    req = urllib.request.Request(feed_url(subreddit, limit), headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # Reddit answers 429 under load and 5xx when it feels like it. A
        # fallback that dies on the first bad minute is not a fallback.
        if (e.code == 429 or e.code >= 500) and attempt < 4:
            time.sleep(min(10 * (2 ** attempt), 120))
            return fetch(subreddit, limit, attempt + 1)
        raise
    except (OSError, http.client.HTTPException):
        if attempt < 4:
            time.sleep(min(10 * (2 ** attempt), 120))
            return fetch(subreddit, limit, attempt + 1)
        raise


def html_to_text(raw):
    """The feed gives HTML; the main corpus stores markdown. Neither is the
    other, so this stores readable text and says so in the schema.

    ElementTree has already unescaped the entities that wrapped the HTML, so
    what arrives here is real tags. One more unescape handles the commenter's
    own characters, which Reddit escaped a second time inside them.
    """
    s = _COMMENT.sub("", raw or "")                 # <!-- SC_OFF --> markers
    s = re.sub(r"(?i)</p\s*>", "\n\n", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = html.unescape(_TAG.sub("", s))
    return "\n".join(line.strip() for line in s.split("\n")).strip()


def parse(xml_text):
    """Atom entries -> comment dicts. Anything malformed is skipped, not guessed."""
    root = ET.fromstring(xml_text)
    out, seen = [], set()
    for e in root.findall("a:entry", NS):
        cid = (e.findtext("a:id", "", NS) or "").strip()
        if not cid.startswith("t1_") or cid in seen:
            continue

        link = e.find("a:link", NS)
        href = link.get("href", "") if link is not None else ""
        m = _LINK.search(href)
        if not m:
            continue
        post_id, slug = m.group(1), m.group(2)

        stamp = (e.findtext("a:updated", "", NS) or "").strip()
        if not stamp:
            continue

        author = (e.findtext("a:author/a:name", "", NS) or "").strip()
        if author.startswith("/u/"):
            author = author[3:]

        # "/u/azeet94 on Mariscos El Submarino - ...". Split on the author's own
        # prefix rather than " on ", which turns up inside real post titles.
        title = (e.findtext("a:title", "", NS) or "").strip()
        prefix = f"/u/{author} on "
        thread_title = title[len(prefix):] if title.startswith(prefix) else title

        body = html_to_text(e.findtext("a:content", "", NS))
        if not body:
            continue

        seen.add(cid)
        out.append({
            "id": cid,
            "thread_id": "t3_" + post_id,
            "thread_title": thread_title,
            "thread_permalink": f"https://www.reddit.com/r/{SUBREDDIT}/comments/{post_id}/{slug}/",
            "author": author or None,
            "body": body,
            "created_utc": datetime.fromisoformat(stamp),
            "permalink": href,
        })
    return out


def poll_once(conn):
    """One fetch, deduped on the way in. Returns (new threads, new comments)."""
    entries = parse(fetch())
    if not entries:
        return 0, 0
    # Threads first: rss_comments.thread_id has a foreign key. A dict keyed on
    # id collapses the 25 comments down to the handful of posts they sit under.
    threads = {e["thread_id"]: (e["thread_id"], e["thread_title"], e["thread_permalink"])
               for e in entries}
    t = db.insert_rss_threads(conn, list(threads.values()))
    c = db.insert_rss_comments(conn, entries)
    return t, c


def run_forever(interval=INTERVAL, verbose=False):
    """Own connection, own clock, own failures. Never raises to the caller.

    psycopg2 connections are not thread-safe, so this opens its own rather than
    sharing the poller's. A cycle that fails is logged and forgotten; the feed
    only holds 25 comments, so a missed cycle costs only what arrived in five
    minutes, and the next one picks the rest up.
    """
    conn = db.connect()
    db.init(conn, SCHEMA)
    while True:
        started = time.time()
        try:
            t, c = poll_once(conn)
            if c or verbose:
                print(f"[rss] +{c} comment(s), +{t} thread(s)", flush=True)
        except Exception as e:
            print(f"[rss] {type(e).__name__}: {e}", flush=True)
            try:
                conn.rollback()
            except Exception:
                conn = db.connect()          # the connection itself went
        time.sleep(max(0, interval - (time.time() - started)))


def start_background(interval=INTERVAL):
    """Start the fallback alongside something else. Daemon: it dies with its host."""
    thread = threading.Thread(target=run_forever, args=(interval,),
                              name="rss", daemon=True)
    thread.start()
    return thread


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="one cycle and exit")
    ap.add_argument("--interval", type=int, default=INTERVAL, metavar="SECONDS")
    args = ap.parse_args()

    conn = db.connect()
    db.init(conn, SCHEMA)
    if args.once:
        t, c = poll_once(conn)
        with conn.cursor() as cur:
            cur.execute("select count(*) from rss_comments")
            total = cur.fetchone()[0]
        print(f"+{c} comment(s), +{t} thread(s)   {total:,} in rss_comments")
        return

    print(f"polling {feed_url()} every {args.interval // 60} min")
    run_forever(args.interval, verbose=True)


if __name__ == "__main__":
    main()
