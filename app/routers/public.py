"""The read endpoints: board, search, facets, corpus stats, health."""

import threading
import time

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query

import subreddits

from .. import queries
from ..city import Sub
from ..db import connection, fetch_all, fetch_one, fetch_value, get_conn
from ..models import (Algo, City, Facets, Health, LeaderboardQuery, LeaderboardRow,
                      Page, SearchHit, SortKey, Stats)

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
    topic: Annotated[Optional[str], Query(max_length=80,
        description="A category: 'omakase', 'tasting menu', 'french'. Matches "
                    "thread titles, descriptors, dishes and cuisine")] = None,
    algo: Annotated[Algo, Query(
        description="v1: decayed attention (scoring.sql). v2: recent people, "
                    "negatives weighted 2x, standout-negative flag (scoring_v2.sql)")] = "v1",
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
    sort: Annotated[Optional[SortKey], Query(
        description="Defaults to volume under v1 and rank under v2")] = None,
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
        descriptor=descriptor, topic=topic, algo=algo, hide_chains=hide_chains,
        include_closed=include_closed, rising=rising,
        min_mentions=min_mentions, min_authors=min_authors,
        min_food=min_food, min_value=min_value, min_service=min_service,
        min_atmosphere=min_atmosphere, min_wait=min_wait,
        sort=sort, limit=limit, offset=offset)


@router.get("/api/leaderboard", response_model=Page[LeaderboardRow],
            summary="Ranked entities")
def leaderboard(sub: Sub, f: Annotated[LeaderboardQuery, Depends(leaderboard_query)],
                conn=Depends(get_conn)):
    """One city's restaurants ranked by one axis, filtered by the rest.

    Note what this measures: how the subreddit *talks about* a place, not how good
    it is. Only the aspect columns carry an opinion; the others measure
    attention. There is no composite score and no stored rank -- position
    exists only relative to the filters you sent.

    The filters select rows; they do not recompute the scores. volume_share is
    normalised against the whole subreddit and aspect scores are shrunk toward
    a citywide mean, so a food score of 0.42 means 0.42 against all of its
    city, not 0.42 among the rows you filtered to.
    """
    rows, total = queries.leaderboard_page(conn, sub, f, fetch_all, fetch_value)
    return Page(items=rows, total=total, limit=f.limit, offset=f.offset)


@router.get("/api/search", response_model=list[SearchHit], summary="Typeahead")
def search(sub: Sub,
           q: Annotated[str, Query(min_length=1, max_length=100)],
           limit: Annotated[int, Query(ge=1, le=25)] = 10,
           conn=Depends(get_conn)):
    """Name lookup only. Deliberately touches no scoring view, so it stays
    fast enough to run on every keystroke."""
    return queries.search(conn, sub, q, limit, fetch_all)


# Each city's last facets answer and the facets_version it was computed at,
# by subreddit. Per process, which is fine: each worker pays the scan once
# per refresh and city.
_facets_cache = {}
_facets_lock = threading.Lock()
# A refresh that only re-resolved identities (an alias edit) can move the
# cuisine counts without moving facets_version, so nothing is kept longer
# than this either.
FACETS_MAX_AGE = 1800


def _cached_facets(sub, version):
    c = _facets_cache.get(sub)
    if (c is not None and c["version"] == version
            and time.monotonic() - c["at"] <= FACETS_MAX_AGE):
        return c["value"]
    return None


@router.get("/api/facets", response_model=Facets, summary="Filter values")
def facets(sub: Sub):
    """Values for one city's filter controls, drawn from what is actually present.

    `descriptors` is the commenters' own open vocabulary -- the prompt asks
    for their words, not a fixed list -- so this reports what the model
    produced rather than what we expected.

    Counting it scans every mention, and every page load asks, so the answer
    is kept until the scoring layer next takes in new mentions. The lock
    makes a burst after a refresh do the scan once rather than once each;
    a request that finds the answer current never waits on it.

    Connections are taken here rather than through get_conn, so a request
    queued on the lock holds none: a burst waiting on one scan must not
    drain the pool for every other page.
    """
    with connection() as conn:
        hit = _cached_facets(sub, queries.facets_version(conn, fetch_value))
    if hit is not None:
        return hit
    with _facets_lock:
        with connection() as conn:
            # Read again under the lock: the request ahead may have just
            # computed it, or a refresh may have moved the version since.
            version = queries.facets_version(conn, fetch_value)
            hit = _cached_facets(sub, version)
            if hit is None:
                hit = Facets(**queries.facets(conn, sub, fetch_all))
                _facets_cache[sub] = {"version": version, "at": time.monotonic(), "value": hit}
        return hit


@router.get("/api/stats", response_model=Stats, summary="Corpus counters")
def stats(sub: Sub, conn=Depends(get_conn)):
    return Stats(**queries.stats(conn, sub, fetch_one))


@router.get("/api/cities", response_model=list[City], summary="The cities with a board")
def cities(conn=Depends(get_conn)):
    """Every subreddit that has a board, r/FoodNYC first, then by size.

    A city is collected long before it is scored, and has a board only once
    its comments have been extracted, so this is read from the board itself
    and not from the list of subreddits collected. Pass `subreddit` to any
    other route as `?subreddit=`.
    """
    rows = {r["subreddit"]: r["places"] for r in queries.cities(conn, fetch_all)}
    known = [s for s in subreddits.SUBREDDITS if s in rows]
    known.sort(key=lambda s: (s != subreddits.HOME, -rows[s]))
    return [City(subreddit=s, name=subreddits.city(s).name, short=subreddits.city(s).short,
                 home=s == subreddits.HOME, places=rows[s]) for s in known]


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
