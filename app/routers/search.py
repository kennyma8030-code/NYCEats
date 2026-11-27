"""Search: the vocabulary the browser matches against, and the query itself.

The work is in app/search.py. Neither route takes a connection through
get_conn: a search waits on an embedding provider and sometimes a model, and
must hold no database connection while it does.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .. import search
from ..city import Sub
from ..models import Mention, SearchResponse

router = APIRouter()


def caller(request: Request):
    """Whose search this is, for the rate limits only; never stored.

    Behind Railway's edge the socket's peer is the proxy, so the address is
    read from the headers the edge sets. The LAST X-Forwarded-For entry is
    the one the edge itself appended; anything before it is whatever the
    client sent and cannot be trusted to tell callers apart.
    """
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


@router.get("/api/search/vocabulary", summary="Words search understands without a model")
def vocabulary(sub: Sub):
    """One city's cuisines, areas, dishes and descriptors as `[label, n]`
    rows, most used first, for matching in the browser as /api/names is.

    `n` is places for a cuisine or an area (they filter) and mentions for a
    dish or a descriptor (they are searched for by meaning). Changes only
    when the scoring views refresh, so a short cache is safe.
    """
    return JSONResponse(search.vocabulary(sub).compact(),
                        headers={"Cache-Control": "public, max-age=300"})


@router.get("/api/search/query", response_model=SearchResponse, summary="Search by meaning")
def query(
    request: Request,
    sub: Sub,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    mode: Annotated[Literal["fast", "full"], Query(description=(
        "fast: understood from the vocabulary alone, never waits on a model; "
        "`needs_model` says when full would read it better. full: a model reads "
        "what the vocabulary could not (kept after the first time)"))] = "full",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    """Places for a typed query, each with the people count it is ranked by
    and the comments behind it.

    Cuisines, areas and named restaurants in the query filter; whatever is
    left is matched against the meaning of comments, and places rank by how
    many different people wrote a matching one (`ranked_by:
    matching_people`). With nothing left to match, the rank is everyone who
    brought the place up (`people`). Comments that knock a place never count
    toward it. `parse` shows how the query was read.

    Where the text cannot be matched by meaning (`semantic: text`) its words
    are matched in thread titles, dishes and descriptors instead. A
    `mode=fast` answer with `needs_model` is provisional and is not logged;
    the `mode=full` request that follows it is the search.
    """
    if not q.strip():
        raise HTTPException(status_code=422, detail="q is empty")
    who = caller(request)
    if not search.REQUESTS.allow(who):
        raise HTTPException(status_code=429, detail="too many searches: wait a minute",
                            headers={"Retry-After": "60"})
    return search.run(sub, q.strip(), mode, limit, who)


@router.get("/api/search/comments", response_model=list[Mention],
            summary="The rest of the comments a search result counts")
def comments(
    sub: Sub,
    ids: Annotated[list[int], Query(min_length=1, max_length=50, description=(
        "mention ids from a result's `mention_ids`, at most 50 a request"))],
):
    """A result shows its first few comments and names all of them in
    `mention_ids`; this returns the others, in the order asked for, so the
    count a place is ranked by can be read in full. A deleted comment comes
    back without its permalink, as everywhere."""
    return search.comments(sub, ids)
