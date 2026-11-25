# NYCEats frontend

React + Vite + TypeScript, with MapLibre GL for the map.

```sh
npm install
npm run dev        # http://localhost:5173, proxies /api to uvicorn on :8000
```

Run the API alongside it from the repo root:

```sh
uvicorn app.main:app --reload
```

When :8000 or :5173 is taken, name another API and another port:

```sh
API_PROXY=http://localhost:8010 npm run dev -- --port 5180
```

```sh
npm run typecheck
npm test           # node's own runner over tests/*.test.ts, no browser
```

```sh
npm run build      # type-checks, then writes frontend/dist
```

FastAPI serves `frontend/dist` at `/`, so after a build the whole site runs
from `uvicorn` alone. There is no other page: without a build the API still
works, and `/` and every other page path answer 503 with a line saying the
frontend is not built, which the boot log repeats as a warning.

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
Python-only.

A failed npm step fails the build, and Railway marks a deploy failed when the
health check does not answer 2xx in time; a failed deploy is not made the
active one. A build step that is skipped rather than failed is different:
`/healthz` reads the database and never looks at the page, so the deploy comes
up with a working API and the 503 above at every page path.

## The map

One MapLibre map sits fixed behind the whole app. Its style is written by
hand in `src/map/style.ts` over OpenFreeMap's public vector tiles, which need
no key; labels are drawn in Inter from the font files `@fontsource/inter`
ships. Its colours are the `--map-*` tokens in `src/styles/tokens.css`.

Coordinates come from the API (`location` on every list row, `locations` on a
restaurant), which serves them from the per-city files in `app/data/` (`app/geo.py`
lists them). They are written by `locations.py` at the repo root from each
city's public inspection data; re-run it to refresh. New York, Los Angeles,
Austin and Chicago have one. Every other city opens centred on the table in
`src/lib/cities.ts`, with a list and no pins.

## URLs

A bare URL is the landing page. A city is `?subreddit=FoodNYC`, plus `sort`
(`loved`, `talked`, `trending`, `gems`), `window`, `topic`, `cuisine`,
`borough`, `need`, `flaw` and `r` for an open restaurant
(`src/state/route.ts`). `dev=1` adds the per-comment "Extraction" link.

## Layout

```
src/
  brand.ts      the product name, in one place
  api/          fetch wrappers and response types
  hooks/        data hooks (ranking, wall, facets, restaurant, paging, route, hover preview)
  state/        the route in the URL, the current city, the ledger's filters
  lib/          sorts, wall, search, rating wording, city centres, formatting,
                the panels' widths (layout) and hover timing (hover)
  map/          the MapLibre view, its pins and its style
  styles/       tokens (one light theme) and global rules
  components/
    home/       landing page: hero over the wall, then the cities
    city/       a city's panel: search, sort, filters, the numbered list
    place/      one restaurant: its hover preview, the open panel, its comments
```
