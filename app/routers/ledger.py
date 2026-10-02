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
from fastapi.responses import JSONResponse

from .. import queries
from ..db import fetch_all, get_conn
from ..models import ASPECTS, Algo, Ledger, LedgerCategory, LedgerFlaw, LedgerItem, LedgerNeed

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
    flaw: Annotated[list[LedgerFlaw], Query(
        description="Keep only places among the worst tenth for this; repeatable")] = [],
    topic: Annotated[Optional[str], Query(max_length=80, description=(
        "A category -- 'omakase', 'tasting menu', 'french'. Only mentions in a "
        "thread titled with it, tagged with it as a descriptor or dish, or of a "
        "place the city files under it, are counted"))] = None,
    algo: Annotated[Algo, Query(description=(
        "v1: scoring.sql. v2: scoring_v2.sql -- top ranks by people x sentiment, "
        "negatives count double, flagged places rank at half, gems excludes "
        "flagged places"))] = "v1",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    conn=Depends(get_conn),
):
    """Restaurants ranked for one category over the last `window` days.

    * **trending** -- more mentions than the window before, ranked by how far
      above it they are relative to its size.
    * **top** -- most mentions in the window.
    * **gems** -- well liked, but mentioned no more than the median place.

    `need` and `flaw` are opposite filters. A need is a fixed bar ("value at
    least 0.2"); a flaw is relative -- the bottom 10% of scored places for
    that aspect -- because the scores are not symmetric. Food scores cluster
    high (median 0.37, only a handful below zero), so "below zero" would
    leave almost nothing, while nearly every wait score is negative.

    Chains and closed places are left out. Aspect scores are all-time; only
    the counts and series are windowed.
    """
    if window not in WINDOWS:
        raise HTTPException(status_code=422,
                            detail=f"window must be one of {', '.join(map(str, WINDOWS))}")
    bucket = bucket_days(window)
    needs = list(dict.fromkeys(need))       # repeated ?need=value is one filter
    flaws = list(dict.fromkeys(flaw))
    if set(needs) & set(flaws):
        raise HTTPException(status_code=422,
                            detail="an aspect cannot be both a need and a flaw")

    rows = queries.ledger_items(conn, category, window, cuisine, borough,
                                needs, flaws, limit, fetch_all,
                                algo=algo, topic=(topic or "").strip() or None)
    return Ledger(category=category, window_days=window, bucket_days=bucket,
                  total=rows[0]["total"] if rows else 0,
                  items=_build_items(conn, rows, window, bucket))


@router.get("/api/ledger/entity", response_model=LedgerItem,
            summary="One restaurant as a ledger row")
def ledger_entity(
    key: Annotated[str, Query(min_length=1, max_length=200, description="Resolved entity key")],
    window: Annotated[int, Query(description="Days: 7, 14, 30, 90, 180 or 365")] = 7,
    algo: Algo = "v1",
    conn=Depends(get_conn),
):
    """The row /api/ledger would return for this restaurant, whether or not it
    ranks. Search lands on places far off any list, and the detail view needs
    the same windowed counts and series either way.

    Unlike the ranked list this does not drop chains or closed places: someone
    who searched for one asked for it by name.
    """
    if window not in WINDOWS:
        raise HTTPException(status_code=422,
                            detail=f"window must be one of {', '.join(map(str, WINDOWS))}")
    rows = queries.ledger_one(conn, key, window, fetch_all, algo)
    if not rows:
        raise HTTPException(status_code=404, detail=f"no entity {key!r} on the leaderboard")
    return _build_items(conn, rows, window, bucket_days(window))[0]


@router.get("/api/names", summary="Every searchable name")
def names(
    min_mentions: Annotated[int, Query(ge=1, le=1000)] = 2,
    conn=Depends(get_conn),
):
    """Every restaurant with at least `min_mentions`, for matching in the browser.

    Sent whole rather than queried per keystroke: at this size one download
    beats a round trip per letter, and the client ranks without waiting on the
    network. Rows are compact arrays, because the client holds all of them:

        [key, name, cuisine, borough, mentions, aliases, flags]

    * `name` is null when it is just the key in title case (most of them).
    * `aliases` are the other spellings people typed that resolve here, so
      "katz" finds Katz's Delicatessen; null when there are none.
    * `flags` is a bitmask: 1 chain, 2 closed.

    The default floor of 2 drops ~13k names typed exactly once -- mostly
    one-off spellings -- and halves the payload. The list only changes when
    the scoring views refresh (~30 min), so a short cache is safe. Because
    browsers keep it, the client asks for `?v=<format>`: change the row shape
    and bump that, or a cached copy of the old shape gets parsed as the new.
    """
    rows = []
    for r in queries.all_names(conn, min_mentions, fetch_all):
        name = display_name(r["official_name"], r["entity_key"])
        rows.append([r["entity_key"],
                     None if name == string.capwords(r["entity_key"]) else name,
                     r["cuisine"], r["borough"], r["raw_mentions"] or 0,
                     r["aliases"] or None,
                     (1 if r["is_chain"] else 0) | (2 if r["closed"] else 0)])
    return JSONResponse(rows, headers={"Cache-Control": "public, max-age=300"})


def _build_items(conn, rows, window, bucket):
    """Ledger rows -> LedgerItems: windowed series and top neighborhood added."""
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
            people=r.get("people"),
            flagged=r.get("flagged"),
            strong_neg_people=r.get("strong_neg_people"),
            strong_neg_share=r.get("strong_neg_share"),
        ))
    return items
