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

import os
from contextlib import asynccontextmanager

import psycopg2
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import close_pool, open_pool
from .routers import admin, public, restaurants

DESCRIPTION = """
A read API over r/FoodNYC.

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.exception_handler(psycopg2.Error)
def database_error(request: Request, exc: psycopg2.Error):
    """Report a database failure as one, rather than as a blank 500.

    The most likely cause by far is a missing scoring layer on a fresh
    database, so say so instead of leaking a relation-does-not-exist trace.
    """
    message = str(getattr(exc, "pgerror", None) or exc).strip()
    hint = ("run `python refresh.py --apply` to build the scoring views"
            if "does not exist" in message else None)
    return JSONResponse(status_code=500,
                        content={"error": "database error",
                                 "detail": message, "hint": hint})


app.include_router(public.router)
app.include_router(restaurants.router)
app.include_router(admin.router)

# Mounted LAST and at the root, so it only catches paths no API route claimed.
# html=True serves static/index.html at /.
if os.path.isdir("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
