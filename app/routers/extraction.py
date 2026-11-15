"""What the extractor took from one comment or post, for inspection.

A debugging aid for the scoring work: the UI swaps a comment's text for this.
Only the v6 thread-mode prompt is shown, the extraction the scoring work is
built on; comment-mode and legacy rows are left out so they don't clutter the
view. It reads `mentions` directly, not `live_mentions`, so the rows show
whether or not the board counts them right now.

Each city's items are read with that city's own thread prompt, under its own
hash (prompt_v6.prompt_for), so the route takes `?subreddit=` like every
other (app/city.py) and shows the rows of that city's prompt.

The route is public, like the comments it sits beside, so it returns what
the extractor said of the item and not the pipeline's bookkeeping about the
call (queries.item_extraction).
"""

import functools
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from .. import queries
from ..city import Sub
from ..db import fetch_all, fetch_one, fetch_value, get_conn
from ..models import ExtractionGroup, ExtractionState, ExtractionView
from .ledger import display_name

router = APIRouter()

# Reddit ids are lowercase base36. The pattern keeps the path to what an item
# id can be; the query binds it as a parameter either way.
ItemId = Annotated[str, Path(pattern=r"^t[13]_[0-9a-z]{1,20}$",
                             description="A comment (t1_...) or post (t3_...) id")]

LABEL = "v6 thread mode"


@functools.lru_cache(maxsize=None)
def thread_hash(sub):
    """The hash of the city's v6 thread prompt, built on first use and kept.
    Built here and not when this module is imported: a prompt that cannot be
    built (prompt_v6 raises when a city's rewrite is incomplete) must fail
    this one debugging route, not stop the whole app from starting. A
    failure is not cached, so the next request tries again."""
    import prompt_v6
    return prompt_v6.thread_prompt(sub)[1]


def group_rows(rows):
    """The rows as the response's groups: one group, the thread prompt's, or
    none. The query reads one prompt's rows, so there is never a second."""
    if not rows:
        return []
    mentions = []
    for r in rows:
        m = {k: v for k, v in r.items() if k not in ("official_name", "prompt_hash", "created_at")}
        m["resolved_name"] = (display_name(r["official_name"], r["resolved_key"])
                              if r["resolved_key"] else None)
        mentions.append(m)
    return [ExtractionGroup(prompt_hash=rows[0]["prompt_hash"], label=LABEL,
                            created_at=max(r["created_at"] for r in rows), mentions=mentions)]


@router.get("/api/extractions/{item_id}", response_model=ExtractionView,
            summary="What the extractor took from one comment or post")
def extraction(item_id: ItemId, sub: Sub, conn=Depends(get_conn)):
    """The item's v6 thread-mode mention rows, as one group.

    `state` is the item's latest v6 read: null means it was never queued
    (or this database has no v6 extraction), `extracted_at` with no
    mentions means it was read and nothing was found, and `failed` means
    the read failed. `this_prompt` is false when that read was under
    another prompt than the one shown, so it says nothing about these rows.
    An item of another city than the one asked for has neither.
    """
    try:
        phash = thread_hash(sub)
    except Exception as e:
        raise HTTPException(status_code=503,
                            detail=f"the extraction prompt for r/{sub} could not be built: {e}")
    got = queries.item_extraction(conn, sub, item_id, phash, fetch_all, fetch_one, fetch_value)
    rows, state = got or ([], None)
    return ExtractionView(item_id=item_id, groups=group_rows(rows),
                          state=ExtractionState(**state) if state else None)
