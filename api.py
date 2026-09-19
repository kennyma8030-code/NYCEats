"""Small read-only JSON API over the scoring views, plus the static UI.

Standard library only -- psycopg2 is the project's single dependency and this
does not add a second. If it grows past a few endpoints, move it to FastAPI.

    python api.py            -> http://localhost:8000
"""

import json
import os
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

import db

PORT = int(os.environ.get("PORT", 8000))


def rows_to_dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def jsonable(o):
    """Dates, Decimals and arrays out of psycopg2 are not JSON by default."""
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return float(o) if hasattr(o, "as_tuple") else str(o)


def leaderboard(conn, q):
    """Ranked entities. Every filter is optional and composes with the rest."""
    where, params = [], []

    if q.get("search"):
        where.append("l.entity_key ilike %s")
        params.append(f"%{q['search'][0]}%")
    if q.get("cuisine"):
        where.append("r.cuisine = %s")
        params.append(q["cuisine"][0])
    if q.get("borough"):
        where.append("%s = any(r.boroughs)")
        params.append(q["borough"][0])
    if q.get("status"):
        where.append("res.status = %s")
        params.append(q["status"][0])
    if q.get("hide_chains", ["1"])[0] == "1":
        where.append("coalesce(r.is_chain, false) = false")
    if q.get("min_mentions"):
        where.append("l.raw_mentions >= %s")
        params.append(int(q["min_mentions"][0]))
    if q.get("min_authors"):
        where.append("res.distinct_authors >= %s")
        params.append(int(q["min_authors"][0]))
    if q.get("rising", ["0"])[0] == "1":
        where.append("l.momentum_fired")
    # Aspect filters: only entities that actually have a score for it.
    for aspect in ("food", "value", "service", "atmosphere", "wait"):
        v = q.get(f"min_{aspect}")
        if v:
            where.append(f"l.{aspect} >= %s")
            params.append(float(v[0]))

    sort = q.get("sort", ["volume"])[0]
    order = {
        "volume":    "l.decayed_volume desc nulls last",
        "momentum":  "l.momentum_sigma desc nulls last",
        "mentions":  "l.raw_mentions desc",
        "authors":   "res.distinct_authors desc nulls last",
        "longevity": "l.months_active desc nulls last",
        "food":      "l.food desc nulls last",
        "value":     "l.value desc nulls last",
    }.get(sort, "l.decayed_volume desc nulls last")

    sql = f"""
        select l.*, r.name as official_name, r.cuisine, r.boroughs,
               r.is_chain, r.location_count,
               res.status, res.distinct_authors, res.fuzzy_match, res.fuzzy_score
        from entity_leaderboard l
        left join restaurants r on r.name_key = l.entity_key
        left join mention_resolution res on res.entity_key = l.entity_key
        {"where " + " and ".join(where) if where else ""}
        order by {order}
        limit %s
    """
    params.append(int(q.get("limit", ["100"])[0]))
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return rows_to_dicts(cur)


def mentions(conn, q):
    """The comments behind a score. This is the non-negotiable click-through."""
    with conn.cursor() as cur:
        cur.execute("""
            select m.restaurant_raw, m.aspects, m.descriptors, m.dishes,
                   m.is_firsthand, m.is_negated,
                   c.author, c.score, c.created_utc, c.body,
                   c.permalink, c.was_deleted_later,
                   t.title as thread_title
            from mentions m
            join comments c on c.id = m.comment_id
            join threads t on t.id = c.thread_id
            where m.entity_key = %s
            order by c.created_utc desc
            limit 200
        """, (q["entity"][0],))
        return rows_to_dicts(cur)


def facets(conn, _q):
    """Values for the filter dropdowns, drawn from what is actually present."""
    out = {}
    with conn.cursor() as cur:
        cur.execute("""
            select r.cuisine, count(*) from entity_leaderboard l
            join restaurants r on r.name_key = l.entity_key
            where r.cuisine is not null group by 1 order by 2 desc limit 40
        """)
        out["cuisines"] = [{"name": a, "n": b} for a, b in cur.fetchall()]
        cur.execute("""
            select b, count(*) from entity_leaderboard l
            join restaurants r on r.name_key = l.entity_key,
                 unnest(r.boroughs) b
            group by 1 order by 2 desc
        """)
        out["boroughs"] = [{"name": a, "n": b} for a, b in cur.fetchall()]
        cur.execute("select status, count(*) from mention_resolution group by 1")
        out["statuses"] = [{"name": a, "n": b} for a, b in cur.fetchall()]
        cur.execute("""
            select (select count(*) from mentions),
                   (select count(distinct entity_key) from mentions),
                   (select count(*) from comments),
                   (select count(*) from comments where extracted_at is not null),
                   (select coalesce(string_agg(distinct model_version, ', '), 'none')
                      from mentions)
        """)
        m, e, c, x, mv = cur.fetchone()
        out["stats"] = {"mentions": m, "entities": e, "comments": c,
                        "extracted": x, "models": mv}
    return out


ROUTES = {"/api/leaderboard": leaderboard, "/api/mentions": mentions,
          "/api/facets": facets}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory="static", **kw)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        fn = ROUTES.get(parsed.path)
        if not fn:
            return super().do_GET()
        try:
            conn = db.connect()
            data = fn(conn, urllib.parse.parse_qs(parsed.query))
            conn.close()
            body = json.dumps(data, default=jsonable).encode()
            self.send_response(200)
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass          # the default logs every asset request; too noisy


if __name__ == "__main__":
    print(f"http://localhost:{PORT}")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
