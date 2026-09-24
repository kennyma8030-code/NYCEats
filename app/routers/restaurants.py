"""One restaurant: its summary, its evidence, its picture.

`entity_key` is a path parameter and contains spaces ("katzs delicatessen",
"joe s pizza"), so callers URL-encode it. It is deliberately not slugified:
a slug would be a second name-to-identity mapping to keep in sync, which is
the exact problem entity_alias exists to solve.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from .. import images, queries
from ..db import fetch_all, fetch_one, fetch_value, get_conn
from ..models import (AspectDetail, ImageOut, Mention, MentionQuery,
                      MentionSort, MomentumWindow, Page, RestaurantDetail,
                      LeaderboardRow, Spelling)

router = APIRouter(prefix="/api/restaurants")

EntityKey = Annotated[str, Path(min_length=1, max_length=200,
                                description="Resolved entity key, URL-encoded")]


def _require_entity(conn, entity_key):
    row = queries.board_row(conn, entity_key, fetch_one)
    if row is None:
        # Distinguish "no such entity" from "an entity with no mentions": the
        # board only holds entities that have at least one weighted mention,
        # so a miss here really is unknown.
        raise HTTPException(status_code=404,
                            detail=f"no entity {entity_key!r} on the leaderboard")
    return row


@router.get("/{entity_key}", response_model=RestaurantDetail,
            summary="Everything about one restaurant")
def detail(entity_key: EntityKey, conn=Depends(get_conn)):
    """One round trip for a detail page.

    Includes the workings, not just the numbers: per-aspect raw_mean against
    the city_mean it was shrunk toward, every momentum window rather than only
    the one that fired, and which typed spellings merged into this identity
    and by what method. A score that cannot be interrogated is an assertion.
    """
    summary = _require_entity(conn, entity_key)
    official = queries.official_record(conn, entity_key, fetch_one) or {}
    return RestaurantDetail(
        entity_key=entity_key,
        summary=LeaderboardRow(**summary),
        aspects=[AspectDetail(**a) for a in
                 queries.aspect_detail(conn, entity_key, fetch_all)],
        momentum=[MomentumWindow(**m) for m in
                  queries.momentum_windows(conn, entity_key, fetch_all)],
        spellings=[Spelling(**s) for s in
                   queries.spellings(conn, entity_key, fetch_all)],
        addresses=official.get("addresses"),
        top_dishes=queries.top_dishes(conn, entity_key, fetch_all),
        top_descriptors=queries.top_descriptors(conn, entity_key, fetch_all),
        neighborhoods=queries.neighborhoods(conn, entity_key, fetch_all),
    )


@router.get("/{entity_key}/mentions", response_model=Page[Mention],
            summary="The comments behind the score")
def mentions(
    entity_key: EntityKey,
    aspect: Annotated[Optional[str], Query(
        description="Only mentions that scored this aspect")] = None,
    negated: Annotated[Optional[bool], Query(
        description="Only avoid-instructions, or only not")] = None,
    firsthand: Annotated[Optional[bool], Query(
        description="Only people who actually went")] = None,
    include_deleted: Annotated[bool, Query(
        description="Include comments since deleted from Reddit "
                    "(their permalink is always null)")] = True,
    sort: MentionSort = "recent",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    conn=Depends(get_conn),
):
    """The click-through SPEC.md calls non-negotiable.

    Returns evidence for every spelling that merged into this entity, not just
    the resolved one. `permalink` is null wherever the comment has been
    deleted from Reddit -- enforced here rather than left to the client,
    because a promise the API does not keep is not a promise.
    """
    if aspect is not None and aspect not in ("food", "value", "service",
                                             "atmosphere", "wait"):
        raise HTTPException(status_code=422, detail=f"unknown aspect {aspect!r}")

    _require_entity(conn, entity_key)
    q = MentionQuery(aspect=aspect, negated=negated, firsthand=firsthand,
                     include_deleted=include_deleted, sort=sort,
                     limit=limit, offset=offset)
    rows, total = queries.mentions_page(conn, entity_key, q, fetch_all, fetch_value)
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.get("/{entity_key}/image", response_model=ImageOut,
            summary="A picture of the place, if one exists")
def image(
    entity_key: EntityKey,
    refresh: Annotated[bool, Query(
        description="Re-run the provider chain, ignoring the cached result")] = False,
    conn=Depends(get_conn),
):
    """Lazily resolved, then cached in Postgres forever.

    Cached in a table rather than in memory because uvicorn runs one process
    per worker: an in-process cache would be resolved once per worker and
    answer differently depending on which one took the request.

    A miss is cached as deliberately as a hit, so a restaurant with no picture
    anywhere costs one lookup rather than one per page load. An upstream
    FAILURE is not: status 'error' means we could not find out, and the next
    request tries again. Callers that get 'none' or 'error' should fall back
    to /monogram.svg.
    """
    cached = images.get_cached(conn, entity_key, fetch_one)
    if cached and (cached["locked"] or not refresh):
        return ImageOut(**{k: v for k, v in cached.items() if k != "locked"})

    row = _require_entity(conn, entity_key)
    resolved, cacheable = images.resolve(
        entity_key, row.get("official_name") or entity_key)
    if not cacheable:
        # Leave whatever was there alone and say so, rather than recording a
        # bad minute as a permanent fact about this restaurant.
        return ImageOut(entity_key=entity_key, **{k: v for k, v in resolved.items()
                                                  if k != "entity_key"})

    stored = images.store(conn, entity_key, resolved, fetch_one)
    # store() skips locked rows, which returns nothing; the cached row stands.
    final = stored or cached or dict(resolved, entity_key=entity_key,
                                     fetched_at=None, locked=False)
    return ImageOut(**{k: v for k, v in final.items() if k != "locked"})


@router.get("/{entity_key}/monogram.svg", response_class=Response,
            summary="Deterministic initials tile")
def monogram(entity_key: EntityKey, conn=Depends(get_conn)):
    """The fallback when no photo exists.

    Not a stock food photo: a stranger's bowl of ramen under a real
    restaurant's name is a false claim about that restaurant. This says "no
    picture" honestly, costs no network call, and is stable -- the same place
    gets the same colour on every worker and every load.
    """
    row = queries.board_row(conn, entity_key, fetch_one) or {}
    svg = images.monogram_svg(entity_key, row.get("official_name"))
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})
