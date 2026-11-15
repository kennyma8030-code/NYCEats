# NYCEats frontend

React + Vite + TypeScript.

```sh
npm install
npm run dev        # http://localhost:5173, proxies /api to uvicorn on :8000
```

Run the API alongside it from the repo root:

```sh
uvicorn app.main:app --reload
```

```sh
npm run build      # type-checks, then writes frontend/dist
```

FastAPI serves `frontend/dist` at `/`, so after a build the whole site runs
from `uvicorn` alone. There is no other page: without a build the API still
works, and `/` answers 503 with a line saying the frontend is not built, which
the boot log repeats.

## Deploy

`frontend/dist` is not committed, so the web service has to build it on every
deploy. Three Railway services build from this repo and only the web one needs
Node, so the build step lives in files only that service reads:

- `railpack.web.json` is the web service's Railpack config. Railpack sees
  `requirements.txt` and plans a Python image; this file adds Node to the
  build and appends the React build to the Python provider's own `build`
  step (the `"..."` keeps that step's commands), whose `/app` is what ships,
  so `frontend/dist` is in the image. `node_modules` is removed afterwards
  because nothing at runtime reads it. The web service reads the file because
  it has the variable `RAILPACK_CONFIG_FILE=railpack.web.json`. It is plain
  JSON with no comments, which is why the explanation is here.
- `railway.web.json` puts the web service on the Railpack builder, with the
  start command, a health check on `/healthz` and the restart policy it has
  today. It is only needed while Railway still reads `railway.json`, which
  otherwise builds every service with Nixpacks; the web service's config file
  path is set to `/railway.web.json`. Railway stops reading these files on
  2026-12-01 and uses the service's own settings from then on, so anything
  here that should outlive that date, the health check in particular, has to
  be set on the service as well. The file can be deleted after that.

The poller and the extract runner set neither, so their builds stay
Python-only. If the build step does not run, the deploy still comes up and the
API works, but `/` answers the 503 above instead of the site.

## Layout

```
src/
  api/          fetch wrappers and response types
  hooks/        data hooks (ledger, facets, restaurant, comments)
  state/        filter state, synced to the URL query string
  lib/          formatting and labels
  styles/       tokens (light/dark) and global rules
  components/
    rail/       brand, category, period, filters
    ledger/     ranked list, rows, sparklines
    detail/     right-hand panel: analytics column + comment column
```
