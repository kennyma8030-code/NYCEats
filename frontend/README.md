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

FastAPI serves `frontend/dist` at `/` when it exists, so after a build the
whole site runs from `uvicorn` alone.

## Deploy

`frontend/dist` is not committed, so the web service has to build it on every
deploy. Three Railway services build from this repo and only the web one needs
Node, so the build step lives in files only that service reads:

- `railpack.web.json` adds Node and runs `npm ci && npm run build` after the
  Python build. The web service reads it because it has the variable
  `RAILPACK_CONFIG_FILE=railpack.web.json`.
- `railway.web.json` puts the web service on the Railpack builder. It is only
  needed while Railway still reads `railway.json`, which otherwise builds
  every service with Nixpacks; the web service's config file path is set to
  `/railway.web.json`. Railway stops reading these files on 2026-12-01 and
  uses the service's own settings, which say the same thing, so it can be
  deleted after that.

The poller and the extract runner set neither, so their builds stay
Python-only.

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
