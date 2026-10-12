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
