"""Placeholder mentions, so the pipeline and UI can be exercised before the
LLM extraction has a key.

Matches comment text against the real NYC restaurant list instead of calling a
model. That gets real restaurants out of real comments -- enough to prove the
scoring and the frontend work -- but it has none of the things extraction is
actually for: no sentiment, no aspects, no negation, no dishes, no descriptors.

Everything it writes is tagged model_version='stringmatch', so:

    python extract.py --reset stringmatch

removes all of it when the real run happens.
"""

import argparse
import re
import time

import db

MODEL = "stringmatch"
PROMPT_HASH = "stringmatch"

# Single words that are real restaurant names but also ordinary English, so a
# bare match means nothing. The LLM handles these from context; we cannot.
AMBIGUOUS = {
    "the one", "delicious", "so good", "the restaurant", "something else",
    "the west", "home kitchen", "wonder", "betty", "angel", "lords", "best",
    "the kitchen", "kitchen", "food", "cafe", "bar", "market", "gourmet",
}


def load_names(conn, min_len=8):
    """Restaurant names worth matching on: long enough to be distinctive."""
    with conn.cursor() as cur:
        cur.execute("""
            select name, name_key, is_chain from restaurants
            where length(name_key) >= %s
        """, (min_len,))
        rows = cur.fetchall()

    names = {}
    for display, key, is_chain in rows:
        if key in AMBIGUOUS or is_chain:
            continue
        words = key.split()
        # Require either two words, or one long distinctive one. A single short
        # word produces far too many false hits to be useful.
        if len(words) < 2 and len(key) < 10:
            continue
        pattern = r"\b" + r"[\s'’\-]+".join(re.escape(w) for w in words) + r"\b"
        names[key] = (display, re.compile(pattern, re.IGNORECASE))
    return names


def scan(conn, names, since_months=6, limit=None):
    with conn.cursor() as cur:
        cur.execute("""
            select c.id, c.body from comments c
            where c.body not in ('[deleted]','[removed]')
              and length(c.body) > 15
              and c.created_utc >= now() - make_interval(months => %s)
            order by c.created_utc desc
            limit %s
        """, (since_months, limit))
        rows = cur.fetchall()

    found, scanned = 0, 0
    for comment_id, body in rows:
        scanned += 1
        hits = []
        for key, (display, rx) in names.items():
            m = rx.search(body)
            # Must be capitalised where it appears -- that is what separates the
            # restaurant "Delicious" from the adjective.
            if m and m.group(0)[0].isupper():
                hits.append({
                    "restaurant_raw": m.group(0),
                    "entity_key": key,
                    "neighborhood_hint": None,
                    "dishes": [], "descriptors": [],
                    # No sentiment: a string match cannot read an opinion.
                    "aspects": {"food": None, "value": None, "service": None,
                                "atmosphere": None, "wait": None},
                    "expensiveness": None,
                    "is_firsthand": None,
                    "is_negated": False,
                })
        if hits:
            found += db.insert_mentions(conn, comment_id, hits, MODEL, PROMPT_HASH)
        if scanned % 5000 == 0:
            print(f"  {scanned:,} comments scanned, {found:,} mentions", flush=True)
    return scanned, found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    conn = db.connect()
    names = load_names(conn)
    print(f"matching against {len(names):,} distinctive restaurant names")
    began = time.time()
    scanned, found = scan(conn, names, args.months, args.limit)
    print(f"\n{scanned:,} comments -> {found:,} mentions "
          f"({(time.time()-began)/60:.1f} min)")
    print("tagged model_version='stringmatch'; "
          "remove with: python extract.py --reset stringmatch")


if __name__ == "__main__":
    main()
