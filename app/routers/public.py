"""The read endpoints: board, search, facets, corpus stats, health."""

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query

from .. import queries
from ..db import fetch_all, fetch_one, fetch_value, get_conn
from ..models import (Facets, Health, LeaderboardQuery, LeaderboardRow, Page,
                      SearchHit, SortKey, Stats)

router = APIRouter()


def leaderboard_query(
    search: Annotated[Optional[str], Query(max_length=100,
        description="Substring of the typed name or the city's official name")] = None,
    cuisine: Annotated[Optional[str], Query(max_length=100)] = None,
    borough: Annotated[Optional[str], Query(max_length=40)] = None,
    status: Annotated[Optional[Literal["exact", "fuzzy", "unlisted", "unverified"]],
        Query(description="How confidently the name matched the city's list")] = None,
    descriptor: Annotated[Optional[str], Query(max_length=80,
        description="A commenter's own word, e.g. 'hole in the wall', 'cash only'")] = None,
    hide_chains: bool = True,
    include_closed: bool = False,
    rising: Annotated[bool, Query(description="Only entities whose momentum fired")] = False,
    min_mentions: Annotated[Optional[int], Query(ge=0, le=100_000)] = None,
    min_authors: Annotated[Optional[int], Query(ge=0, le=100_000)] = None,
    min_food: Annotated[Optional[float], Query(ge=-1, le=1)] = None,
    min_value: Annotated[Optional[float], Query(ge=-1, le=1)] = None,
    min_service: Annotated[Optional[float], Query(ge=-1, le=1)] = None,
    min_atmosphere: Annotated[Optional[float], Query(ge=-1, le=1)] = None,
    min_wait: Annotated[Optional[float], Query(ge=-1, le=1)] = None,
    sort: SortKey = "volume",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeaderboardQuery:
    """Query params as one validated object.

    Written out rather than taken as a Pydantic model dependency so the
    parameter names, bounds and descriptions land in /docs, and so this works
    on any FastAPI version.
    """
    return LeaderboardQuery(
        search=search, cuisine=cuisine, borough=borough, status=status,
        descriptor=descriptor, hide_chains=hide_chains,
        include_closed=include_closed, rising=rising,
        min_mentions=min_mentions, min_authors=min_authors,
        min_food=min_food, min_value=min_value, min_service=min_service,
        min_atmosphere=min_atmosphere, min_wait=min_wait,
        sort=sort, limit=limit, offset=offset)


@router.get("/api/leaderboard", response_model=Page[LeaderboardRow],
            summary="Ranked entities")
def leaderboard(f: Annotated[LeaderboardQuery, Depends(leaderboard_query)],
                conn=Depends(get_conn)):
    """Restaurants ranked by one axis, filtered by the rest.

    Note what this measures: how r/FoodNYC *talks about* a place, not how good
    it is. Only the aspect columns carry an opinion; the others measure
    attention. There is no composite score and no stored rank -- position
    exists only relative to the filters you sent.

    The filters select rows; they do not recompute the scores. volume_share is
    normalised against the whole subreddit and aspect scores are shrunk toward
    a citywide mean, so a food score of 0.42 means 0.42 against all of NYC,
    not 0.42 among the rows you filtered to.
    """
    rows, total = queries.leaderboard_page(conn, f, fetch_all, fetch_value)
    return Page(items=rows, total=total, limit=f.limit, offset=f.offset)


@router.get("/api/search", response_model=list[SearchHit], summary="Typeahead")
def search(q: Annotated[str, Query(min_length=1, max_length=100)],
           limit: Annotated[int, Query(ge=1, le=25)] = 10,
           conn=Depends(get_conn)):
    """Name lookup only. Deliberately touches no scoring view, so it stays
    fast enough to run on every keystroke."""
    return queries.search(conn, q, limit, fetch_all)


@router.get("/api/facets", response_model=Facets, summary="Filter values")
def facets(conn=Depends(get_conn)):
    """Values for the filter controls, drawn from what is actually present.

    `descriptors` is the commenters' own open vocabulary -- the prompt asks
    for their words, not a fixed list -- so this reports what the model
    produced rather than what we expected.
    """
    return Facets(**queries.facets(conn, fetch_all))


@router.get("/api/stats", response_model=Stats, summary="Corpus counters")
def stats(conn=Depends(get_conn)):
    return Stats(**queries.stats(conn, fetch_one))


@router.get("/healthz", response_model=Health, summary="Liveness and readiness")
def healthz(conn=Depends(get_conn)):
    """Readiness, not just liveness.

    A populated materialized view is the difference between an empty
    leaderboard and a broken one, so the check reports which views exist and
    hold data rather than only whether Postgres answered.
    """
    views = queries.view_health(conn, fetch_all)
    ready = views.get("entity_leaderboard", False)
    rows = (fetch_value(conn, "select count(*) from entity_leaderboard", (), default=0)
            if ready else None)
    return Health(
        status="ok" if ready else "degraded",
        database=True,
        views_populated=views,
        leaderboard_rows=rows,
        detail=None if ready else "entity_leaderboard is missing or unpopulated -- "
                                  "run python refresh.py --apply",
    )
