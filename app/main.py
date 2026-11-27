"""The FastAPI application.

    uvicorn app.main:app --reload          local
    uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2   Railway

One uvicorn worker is one OS process, each with its own connection pool, so
`--workers N` means N * DB_POOL_MAX connections against Postgres. At this
traffic the bottleneck is the database, not the server: two workers is plenty,
and the thing that actually made the board fast was materializing
entity_leaderboard, not adding processes.

Endpoints are sync `def` throughout. Starlette runs them in its anyio
threadpool and psycopg2 releases the GIL inside libpq, so requests genuinely
overlap. Do not convert one to `async def` without also moving it off
psycopg2 -- a blocking call on the event loop stalls every request in the
process.
"""

import logging
import os
from contextlib import asynccontextmanager

import psycopg2
import psycopg2.errors
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .db import PoolTimeout, close_pool, open_pool
from .routers import admin, extraction, feed, ledger, public, restaurants, search

# uvicorn configures this logger, so a line here lands in the Railway log.
log = logging.getLogger("uvicorn.error")

DESCRIPTION = """
A read API over city food subreddits: r/FoodNYC, and every other city
that has a board (`/api/cities`). Every route takes `?subreddit=` and
answers for r/FoodNYC without it. A restaurant is a name within a city.

Every number here measures **how the subreddit talks about a restaurant**, not
how good it is. Only the aspect scores carry an opinion; volume, momentum and
longevity measure attention. There is deliberately no composite score: rank by
whichever axis you want, and everything else is a filter or a badge.

Every score clicks through to the comments that produced it, at
`/api/restaurants/{entity_key}/mentions`.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail at boot rather than on the first request, so a bad DATABASE_URL is
    # a crashed deploy instead of a site that 500s under load.
    open_pool()
    yield
    close_pool()


app = FastAPI(
    title="NYCEats API",
    description=DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
)

# Wide open by default because the API is read-only and public; the admin
# router has its own token. Narrow it with CORS_ORIGINS when a real frontend
# gets a domain.
# /api/names ships every restaurant to the browser; its repeated keys gzip
# to a fraction of their size. Small responses are left alone.
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.exception_handler(PoolTimeout)
def pool_timeout(request: Request, exc: PoolTimeout):
    """Every connection stayed busy for the whole wait: a burst, not a fault.

    503 with Retry-After rather than a 500, because the request was fine and
    the same one a second later will very likely succeed.
    """
    return JSONResponse(status_code=503, headers={"Retry-After": "1"},
                        content={"error": "busy",
                                 "detail": "the server is busy; try again shortly"})


@app.exception_handler(psycopg2.Error)
def database_error(request: Request, exc: psycopg2.Error):
    """Report a database failure as one, rather than as a blank 500.

    The detail goes to the log, not the client: Postgres error text names
    tables, columns and sometimes values, and this API is anonymous. The
    most likely cause by far is a missing scoring layer on a fresh database,
    so that one gets a hint, keyed on the error class rather than its text.
    """
    message = str(getattr(exc, "pgerror", None) or exc).strip()
    log.error("database error on %s %s: %s: %s", request.method, request.url.path,
              type(exc).__name__, message)
    if isinstance(exc, psycopg2.errors.QueryCanceled):
        # statement_timeout (app/db.py) fired: too slow, not broken.
        return JSONResponse(status_code=503, headers={"Retry-After": "5"},
                            content={"error": "database timeout",
                                     "detail": "the query took too long"})
    missing = isinstance(exc, (psycopg2.errors.UndefinedTable,
                               psycopg2.errors.UndefinedObject,
                               psycopg2.errors.UndefinedColumn))
    hint = "run `python refresh.py --apply` to build the scoring views" if missing else None
    return JSONResponse(status_code=500,
                        content={"error": "database error",
                                 "detail": "the database could not answer this request",
                                 "hint": hint})


app.include_router(public.router)
app.include_router(ledger.router)
app.include_router(feed.router)
app.include_router(search.router)
app.include_router(extraction.router)
app.include_router(restaurants.router)
app.include_router(admin.router)

# Registered LAST and at the root, so it only catches paths no API route
# claimed. html=True serves index.html at /. The React build (cd frontend &&
# npm run build) is the only UI, and it is not committed, so a deploy has to
# build it (frontend/README.md, "Deploy").
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_MISSING = ("The frontend is not built: frontend/dist does not exist. "
                    "Run `npm run build` in frontend/, or check that the deploy's "
                    "build step ran. The API is unaffected; see /docs.")


def frontend_dir(root: str = REPO_ROOT) -> str:
    """Where the build lands, found from this file rather than from the
    working directory, so uvicorn started from anywhere sees the same one."""
    return os.path.join(root, "frontend", "dist")


def serve_frontend(app: FastAPI, directory: str) -> bool:
    """Serve the built React app at /, or say plainly that there is none.

    A missing build is reported in the boot log and at every page path,
    rather than left as a bare 404: a deploy whose Node step did not run
    would otherwise look like a site that lost its page for no reason. It
    does not stop the boot, because the API is useful without the page. It
    is a warning rather than an error because it is also the ordinary state
    of local work behind the Vite dev server, which never builds one.
    """
    if os.path.isdir(directory):
        app.mount("/", StaticFiles(directory=directory, html=True), name="frontend")
        return True
    log.warning(FRONTEND_MISSING)

    # A catch-all, so /index.html, /assets/... and /favicon.ico say the same
    # thing as /. Routes match in the order they were added and this is added
    # last, so the API and the docs pages are never shadowed. An unknown /api
    # path stays a 404, as it is when the build is mounted here instead.
    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def frontend_missing(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        return PlainTextResponse(FRONTEND_MISSING, status_code=503)

    return False


serve_frontend(app, frontend_dir())
