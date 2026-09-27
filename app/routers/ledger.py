"""The ledger: what r/FoodNYC is talking about over a rolling window.

This is what the React frontend's list is built on. It is a different
question from /api/leaderboard, which ranks on decayed, all-time axes: here
the window is explicit ("the last 30 days") and every count is a plain number
of mentions a reader can check against the comments.
"""

import math
import string
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import queries
from ..db import fetch_all, get_conn
from ..models import ASPECTS, Ledger, LedgerCategory, LedgerItem, LedgerNeed

router = APIRouter()

WINDOWS = (7, 14, 30, 90, 180, 365)


def bucket_days(window):
    """Daily points up to a month, weekly beyond, so a series is 7-53 points."""
    return 1 if window <= 30 else 7


def display_name(official, entity_key):
    """The city lists names in capitals (KATZ'S DELICATESSEN). capwords, not
    str.title(), because title() capitalises after apostrophes: Katz'S."""
    if not official:
        return string.capwords(entity_key)
    return string.capwords(official.lower()) if official.isupper() else official


@router.get("/api/ledger", response_model=Ledger, summary="Ranked over a window")
def ledger(
    category: LedgerCategory = "trending",
    window: Annotated[int, Query(description="Days: 7, 14, 30, 90, 180 or 365")] = 7,
    cuisine: Annotated[Optional[str], Query(max_length=100)] = None,
    borough: Annotated[Optional[str], Query(max_length=40)] = None,
    need: Annotated[list[LedgerNeed], Query(
        description="Keep only places rated well for this; repeatable")] = [],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    conn=Depends(get_conn),
):
    """Restaurants ranked for one category over the last `window` days.

    * **trending** -- more mentions than the window before, ranked by how far
      above it they are relative to its size.
    * **top** -- most mentions in the window.
    * **gems** -- well liked, but mentioned no more than the median place.

    Chains and closed places are left out. Aspect scores are all-time; only
    the counts and series are windowed.
    """
    if window not in WINDOWS:
        raise HTTPException(status_code=422,
                            detail=f"window must be one of {', '.join(map(str, WINDOWS))}")
    bucket = bucket_days(window)
    needs = list(dict.fromkeys(need))       # repeated ?need=value is one filter

    rows = queries.ledger_items(conn, category, window, cuisine, borough,
                                needs, limit, fetch_all)
    keys = [r["entity_key"] for r in rows]

    n = math.ceil(window / bucket)
    series = {k: ([0] * n, [0] * n) for k in keys}
    for s in queries.ledger_series(conn, keys, window, bucket, fetch_all):
        # min() because the oldest bucket of a window that is not a whole
        # number of weeks is short, and floating-point age can land on n.
        idx = min(s["idx"], n - 1)
        cur, prev = series[s["entity_key"]]
        # Buckets count back from now; the series runs oldest first.
        (cur if s["is_current"] else prev)[n - 1 - idx] += s["n"]
    hoods = {h["entity_key"]: h["name"]
             for h in queries.top_neighborhoods(conn, keys, fetch_all)}

    items = []
    for r in rows:
        cur, prev = r["current"], r["previous"]
        items.append(LedgerItem(
            entity_key=r["entity_key"],
            name=display_name(r["official_name"], r["entity_key"]),
            cuisine=r["cuisine"],
            borough=(r["boroughs"] or [None])[0],
            boroughs=r["boroughs"],
            neighborhood=hoods.get(r["entity_key"]),
            current=cur,
            previous=prev,
            change_pct=round((cur - prev) / prev * 100) if prev else None,
            series=series[r["entity_key"]][0],
            previous_series=series[r["entity_key"]][1],
            total_mentions=r["raw_mentions"] or 0,
            distinct_authors=r["distinct_authors"],
            aspects={a: r[a] for a in ASPECTS},
            sentiment=r["sentiment"],
        ))
    return Ledger(category=category, window_days=window, bucket_days=bucket,
                  total=rows[0]["total"] if rows else 0, items=items)
