"""Write endpoints: the identity correction queue, and a refresh trigger.

This router exists because nothing in the codebase could write to
`alias_overrides`. schema.sql creates it, scoring.sql reads it, and until now
the only way to put a row in it was psql by hand -- so the "somewhere real for
corrections to live" the schema comment promises did not actually exist.

Guarded by a shared secret in the X-Admin-Token header. If ADMIN_TOKEN is
unset the whole router answers 503 rather than running unauthenticated:
defaulting an editable surface to open is how a personal project becomes
someone else's.
"""

import os
import threading

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from typing import Annotated, Optional

from .. import queries
from ..db import connection, fetch_all, fetch_one, fetch_value, get_conn
from ..models import AliasIn, AliasOut, JobAccepted, Page, UnresolvedRow

router = APIRouter(prefix="/api/admin")

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")

# One refresh at a time. Two concurrent REFRESH MATERIALIZED VIEW runs would
# queue on the same locks and double the time everything is stale.
_refreshing = threading.Lock()


def require_token(x_admin_token: Annotated[Optional[str], Header()] = None):
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="admin endpoints are disabled (ADMIN_TOKEN is not set)")
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="bad or missing X-Admin-Token")


@router.get("/unresolved", response_model=Page[UnresolvedRow],
            dependencies=[Depends(require_token)],
            summary="Identity decisions waiting on a person")
def unresolved(limit: int = 50, offset: int = 0, conn=Depends(get_conn)):
    """Names a threshold guessed at, worst-first.

    Ordered by mention count because a wrong merge on a place with 200
    mentions misfiles 200 pieces of evidence and one on a place with 3
    misfiles 3. Fuzzy matches are included on purpose -- those are precisely
    the ones word_similarity decided without a human.
    """
    rows, total = queries.unresolved(conn, limit, offset, fetch_all, fetch_value)
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.get("/aliases", response_model=Page[AliasOut],
            dependencies=[Depends(require_token)],
            summary="Decisions already made")
def list_aliases(limit: int = 100, offset: int = 0, conn=Depends(get_conn)):
    rows, total = queries.list_aliases(conn, limit, offset, fetch_all, fetch_value)
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.post("/aliases", response_model=AliasOut, status_code=201,
             dependencies=[Depends(require_token)],
             summary="Merge two spellings, or pin one apart")
def upsert_alias(body: AliasIn, conn=Depends(get_conn)):
    """Record a human decision about identity.

    Set resolved_key equal to entity_key to mean "never merge this one".
    That is not a no-op: word_similarity scores "cote" against "cote wine bar"
    at a confident 1.00 and is simply wrong, and no threshold separates that
    from "katzs" against "katzs delicatessen", which is right for the same
    reason. Only a person can tell them apart, and this is where they say so.

    The override wins outright over both the exact and the fuzzy match
    (scoring.sql, entity_alias). It takes effect on the next refresh, not
    immediately -- entity_alias is materialized.
    """
    row = queries.upsert_alias(conn, body.entity_key.strip(),
                               body.resolved_key.strip(), body.note, fetch_one)
    return AliasOut(**row)


@router.delete("/aliases/{entity_key}", status_code=204,
               dependencies=[Depends(require_token)],
               summary="Undo a decision")
def delete_alias(entity_key: str, conn=Depends(get_conn)):
    if queries.delete_alias(conn, entity_key, fetch_value) is None:
        raise HTTPException(status_code=404, detail=f"no override for {entity_key!r}")
    return None


def _run_refresh():
    """Own connection, not a pooled one: a full refresh takes minutes and must
    not hold a slot the request path needs."""
    try:
        import refresh
        with connection() as conn:
            refresh.refresh_views(conn, verbose=True)
    except Exception as e:
        print(f"[admin] refresh failed: {type(e).__name__}: {e}", flush=True)
    finally:
        _refreshing.release()


@router.post("/refresh", response_model=JobAccepted, status_code=202,
             dependencies=[Depends(require_token)],
             summary="Rebuild the materialized scoring layer")
def refresh_views(background: BackgroundTasks):
    """Recompute entity_alias, mention_weights, momentum_windows and
    entity_leaderboard, in that order.

    The order is not optional: mention_weights reads entity_alias and the
    board reads all three, so refreshing out of order scores current mentions
    against a previous run's identities. refresh.py owns that ordering and
    this reuses it rather than restating it.
    """
    if not _refreshing.acquire(blocking=False):
        return JobAccepted(job="refresh", started=False,
                           detail="a refresh is already running")
    background.add_task(_run_refresh)
    return JobAccepted(job="refresh", started=True,
                       detail="running in the background; poll /healthz")
