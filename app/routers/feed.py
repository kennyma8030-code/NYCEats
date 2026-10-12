"""The live feed: every r/FoodNYC post and comment, newest first, as it arrives.

Restaurant pages show the comments behind one place; this is the whole
subreddit in time order, which is what the poller's ~30-minute runs feed.
"""

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import queries
from ..db import fetch_all, get_conn
from ..models import Feed, FeedItem, FeedPlace
from .ledger import display_name

router = APIRouter()


def parse_cursor(cursor):
    """A cursor is "<created_utc ISO>|<id>", as handed out on each item."""
    try:
        when, item_id = cursor.rsplit("|", 1)
        return datetime.fromisoformat(when), item_id
    except ValueError:
        raise HTTPException(status_code=422, detail=f"bad cursor {cursor!r}")


@router.get("/api/feed", response_model=Feed, summary="Every post and comment, newest first")
def feed(
    q: Annotated[Optional[str], Query(max_length=100,
        description="Only posts and comments whose text contains this")] = None,
    places_only: Annotated[bool, Query(
        description="Only comments that mention a restaurant (leaves out posts)")] = False,
    before: Annotated[Optional[str], Query(max_length=120,
        description="An item's cursor: items older than it (the next page)")] = None,
    after: Annotated[Optional[str], Query(max_length=120,
        description="An item's cursor: items newer than it (what arrived since)")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
    conn=Depends(get_conn),
):
    """Posts and comments newest first, comments with the restaurants they mention.

    Pages by cursor, not offset: new items land at the top while someone
    reads, and an offset would then repeat the ones they have already seen.
    `permalink` is null for a comment since deleted from Reddit, as on the
    restaurant endpoints.
    """
    if before and after:
        raise HTTPException(status_code=422, detail="pass before or after, not both")
    rows = queries.feed_items(conn, (q or "").strip() or None, places_only,
                              parse_cursor(before) if before else None,
                              parse_cursor(after) if after else None,
                              limit, fetch_all)
    return Feed(items=[
        FeedItem(
            kind=r["kind"],
            id=r["id"],
            cursor=f"{r['created_utc'].isoformat()}|{r['id']}",
            author=r["author"],
            score=r["score"],
            created_utc=r["created_utc"],
            body=r["body"],
            permalink=r["permalink"],
            was_deleted_later=r["was_deleted_later"],
            title=r["title"],
            num_comments=r["num_comments"],
            places=[FeedPlace(key=p["key"], name=display_name(p["official_name"], p["key"]))
                    for p in r["places"]],
        )
        for r in rows
    ])
