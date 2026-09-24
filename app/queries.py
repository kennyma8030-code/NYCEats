"""Every SQL statement the API runs.

Kept apart from the routers so the shape of a query is reviewable next to the
views it reads, and so nothing that builds SQL is mixed in with HTTP handling.

Two rules hold throughout:

  * Values are ALWAYS bound parameters. The only strings interpolated into SQL
    are looked up in a whitelist dict first (ORDER BY cannot take a parameter),
    so nothing a caller types reaches the statement.
  * Anything keyed on an entity reaches its evidence through `entity_alias`.
    l.entity_key is a RESOLVED key; mentions are keyed on what people actually
    typed. Joining them directly silently drops every merged spelling.
"""

from .models import ASPECTS, SORTS

# The columns the leaderboard exposes. Listed rather than `l.*` so a change to
# the materialized view cannot quietly alter the API's response shape.
BOARD_COLUMNS = """
    l.entity_key, l.raw_mentions, l.decayed_volume, l.volume_share,
    l.distinct_authors, l.firsthand_mentions, l.negated_mentions,
    l.momentum_sigma, l.momentum_window_days, l.momentum_fired,
    l.first_seen, l.last_seen, l.months_active, l.longest_gap_months,
    l.food, l.value, l.service, l.atmosphere, l.wait,
    l.official_name, l.cuisine, l.boroughs, l.is_chain, l.closed,
    l.location_count
"""

# Resolution status for a resolved entity: the strongest status among the
# spellings that merged into it. A lateral rather than a column on the
# materialized view, so scoring.sql stays independent of resolve.sql.
RESOLUTION_LATERAL = """
    left join lateral (
      select res.status, res.fuzzy_match, res.fuzzy_score
      from entity_alias al
      join mention_resolution res on res.entity_key = al.entity_key
      where al.resolved_key = l.entity_key
      order by case res.status when 'exact'    then 1
                               when 'fuzzy'    then 2
                               when 'unlisted' then 3
                               else                 4 end
      limit 1
    ) res on true
"""


def _board_filters(f):
    """Translate validated query params into (where_sql, params).

    `f` is a LeaderboardQuery; every field has already been range-checked by
    Pydantic, so this only has to decide which predicates apply.
    """
    where, params = [], []

    if f.search:
        # Both the typed key and the city's display name, so searching
        # "delicatessen" finds katzs whether or not anyone typed it that way.
        where.append("(l.entity_key ilike %s or l.official_name ilike %s)")
        params += [f"%{f.search}%", f"%{f.search}%"]
    if f.cuisine:
        where.append("l.cuisine = %s")
        params.append(f.cuisine)
    if f.borough:
        where.append("%s = any(l.boroughs)")
        params.append(f.borough)
    if f.status:
        where.append("res.status = %s")
        params.append(f.status)
    if f.hide_chains:
        where.append("coalesce(l.is_chain, false) = false")
    if not f.include_closed:
        where.append("coalesce(l.closed, false) = false")
    if f.rising:
        where.append("coalesce(l.momentum_fired, false)")
    if f.min_mentions is not None:
        where.append("l.raw_mentions >= %s")
        params.append(f.min_mentions)
    if f.min_authors is not None:
        where.append("coalesce(l.distinct_authors, 0) >= %s")
        params.append(f.min_authors)

    for aspect in ASPECTS:
        v = getattr(f, f"min_{aspect}", None)
        if v is not None:
            # Aspect name comes from the module constant, never the caller.
            # NULL is excluded by the comparison itself: an unmeasured aspect
            # must not pass a threshold test by looking average.
            where.append(f"l.{aspect} >= %s")
            params.append(v)

    if f.descriptor:
        # `?` is jsonb key-exists, and rides mentions_desc_idx (schema.sql).
        # Reached through entity_alias because descriptors hang off the typed
        # spelling, not the resolved one.
        where.append("""exists (
            select 1 from mentions m
            join entity_alias al on al.entity_key = m.entity_key
            where al.resolved_key = l.entity_key
              and jsonb_typeof(m.descriptors) = 'array'
              and m.descriptors ? %s
        )""")
        params.append(f.descriptor)

    return (" where " + " and ".join(where) if where else ""), params


def leaderboard_page(conn, f, fetch_all, fetch_value):
    """One page of the board, plus the unpaginated total.

    The count runs against the same predicates so a client can page without
    guessing how many rows exist. Both statements read a materialized table of
    a few thousand rows, so two queries is cheaper than one with a window
    function over the whole set.
    """
    where, params = _board_filters(f)

    # The count does NOT get the lateral unless the caller filtered on status.
    # count(*) has no LIMIT to stop at, so joining it would resolve the status
    # of every one of the ~8,000 entities to return a single number -- measured
    # at 2.8s per request, against 3ms for the page itself. The page query
    # keeps the lateral because `status` is part of the response, but there it
    # runs for one page of rows, not the whole board.
    count_join = RESOLUTION_LATERAL if f.status else ""
    total = fetch_value(
        conn, f"select count(*) from entity_leaderboard l {count_join} {where}",
        params, default=0)

    rows = fetch_all(conn, f"""
        select {BOARD_COLUMNS}, res.status, res.fuzzy_match, res.fuzzy_score
        from entity_leaderboard l
        {RESOLUTION_LATERAL}
        {where}
        order by {SORTS[f.sort]}, l.entity_key
        limit %s offset %s
    """, params + [f.limit, f.offset])
    return rows, total


def board_row(conn, entity_key, fetch_one):
    return fetch_one(conn, f"""
        select {BOARD_COLUMNS}, res.status, res.fuzzy_match, res.fuzzy_score
        from entity_leaderboard l
        {RESOLUTION_LATERAL}
        where l.entity_key = %s
    """, (entity_key,))


def aspect_detail(conn, entity_key, fetch_all):
    """Per-aspect workings: what the mentions said, and what it was shrunk to."""
    return fetch_all(conn, """
        select aspect, n_obs, aspect_weight, raw_mean, city_mean, aspect_score
        from aspect_scores
        where entity_key = %s
        order by array_position(
            array['food','value','service','atmosphere','wait'], aspect)
    """, (entity_key,))


def momentum_windows(conn, entity_key, fetch_all):
    """All four windows, not just the one that fired.

    entity_momentum reports the shortest window clearing the threshold; this
    shows the whole ladder, which is what makes a 'rising' badge auditable.
    """
    return fetch_all(conn, """
        select ma.window_days,
               ma.sigma,
               ma.recent_volume,
               ma.baseline_volume,
               ma.expected,
               ma.sigma >= p.momentum_sigma as fired
        from entity_momentum_all ma
        cross join scoring_params p
        where ma.entity_key = %s
        order by ma.window_days
    """, (entity_key,))


def spellings(conn, entity_key, fetch_all):
    """Which typed names merged into this entity, and by what method."""
    return fetch_all(conn, """
        select a.entity_key, a.method, a.score,
               (select count(*) from mentions m where m.entity_key = a.entity_key)
                 as mentions
        from entity_alias a
        where a.resolved_key = %s
        order by mentions desc, a.entity_key
    """, (entity_key,))


def official_record(conn, entity_key, fetch_one):
    return fetch_one(conn, """
        select name, name_key, cuisine, boroughs, location_count,
               addresses, is_chain, closed, last_seen
        from restaurants
        where name_key = %s
    """, (entity_key,))


def _jsonb_top(conn, entity_key, column, fetch_all, limit=15):
    """Top values from a jsonb array column on mentions.

    column is a module-level literal, never caller input. The array-type guard
    matters: a model that emitted a bare string instead of a list would
    otherwise abort the whole query.
    """
    return fetch_all(conn, f"""
        select v as name, count(*) as n
        from mentions m
        join entity_alias al on al.entity_key = m.entity_key
        cross join lateral jsonb_array_elements_text(m.{column}) v
        where al.resolved_key = %s
          and jsonb_typeof(m.{column}) = 'array'
        group by 1
        order by 2 desc, 1
        limit %s
    """, (entity_key, limit))


def top_dishes(conn, entity_key, fetch_all):
    return _jsonb_top(conn, entity_key, "dishes", fetch_all)


def top_descriptors(conn, entity_key, fetch_all):
    return _jsonb_top(conn, entity_key, "descriptors", fetch_all)


def neighborhoods(conn, entity_key, fetch_all):
    return fetch_all(conn, """
        select m.neighborhood_hint as name, count(*) as n
        from mentions m
        join entity_alias al on al.entity_key = m.entity_key
        where al.resolved_key = %s and m.neighborhood_hint is not null
        group by 1
        order by 2 desc
        limit 10
    """, (entity_key,))


MENTION_SORTS = {
    "recent": "c.created_utc desc",
    "oldest": "c.created_utc asc",
    "score":  "c.score desc nulls last",
}


def mentions_page(conn, entity_key, q, fetch_all, fetch_value):
    """The evidence behind a score.

    permalink is returned as NULL when the comment is gone from Reddit rather
    than left for the client to suppress. SPEC.md calls click-through
    non-negotiable, and the other half of that promise is never linking
    something that 404s -- which is only kept if the API keeps it.
    """
    where = ["al.resolved_key = %s"]
    params = [entity_key]

    if q.negated is not None:
        where.append("m.is_negated = %s")
        params.append(q.negated)
    if q.firsthand is not None:
        where.append("m.is_firsthand = %s")
        params.append(q.firsthand)
    if q.aspect:
        # Aspect is whitelisted by the route's Literal, and still bound rather
        # than interpolated. 'number' excludes JSON null, so "mentioned the
        # wait" and "wait was mixed" stay distinguishable.
        where.append("jsonb_typeof(m.aspects -> %s) = 'number'")
        params.append(q.aspect)
    if not q.include_deleted:
        where.append("c.was_deleted_later = false")

    base = f"""
        from mentions m
        join comments c on c.id = m.comment_id
        join threads  t on t.id = c.thread_id
        join entity_alias al on al.entity_key = m.entity_key
        where {" and ".join(where)}
    """

    total = fetch_value(conn, f"select count(*) {base}", params, default=0)
    rows = fetch_all(conn, f"""
        select m.id as mention_id, m.comment_id, m.restaurant_raw,
               m.entity_key as typed_key, m.aspects, m.dishes, m.descriptors,
               m.expensiveness, m.is_firsthand, m.is_negated,
               m.neighborhood_hint,
               c.author, c.score, c.controversiality, c.created_utc, c.body,
               case when c.was_deleted_later then null else c.permalink end
                 as permalink,
               c.was_deleted_later,
               t.id as thread_id, t.title as thread_title
        {base}
        order by {MENTION_SORTS[q.sort]}, m.id
        limit %s offset %s
    """, params + [q.limit, q.offset])
    return rows, total


def search(conn, q, limit, fetch_all):
    """Typeahead. Deliberately does not touch the scoring views.

    Prefix match first, then trigram similarity, so typing "katz" ranks katzs
    above an incidental substring match elsewhere.
    """
    return fetch_all(conn, """
        select l.entity_key, coalesce(l.official_name, l.entity_key) as display_name,
               l.raw_mentions, l.cuisine
        from entity_leaderboard l
        where l.entity_key ilike %s or l.official_name ilike %s
        order by (l.entity_key ilike %s) desc,
                 similarity(l.entity_key, %s) desc,
                 l.raw_mentions desc nulls last
        limit %s
    """, (f"%{q}%", f"%{q}%", f"{q}%", q, limit))


def facets(conn, fetch_all):
    cuisines = fetch_all(conn, """
        select cuisine as name, count(*) as n
        from entity_leaderboard
        where cuisine is not null
        group by 1 order by 2 desc, 1 limit 40
    """)
    boroughs = fetch_all(conn, """
        select b as name, count(*) as n
        from entity_leaderboard l, unnest(l.boroughs) b
        group by 1 order by 2 desc, 1
    """)
    statuses = fetch_all(conn, """
        select status as name, count(*) as n
        from mention_resolution group by 1 order by 2 desc, 1
    """)
    # The vocabulary is open by design (the prompt says so), so this reports
    # what the model actually produced rather than a fixed list. A full scan of
    # mentions; fine at this size, and the obvious thing to materialize if the
    # corpus grows an order of magnitude.
    descriptors = fetch_all(conn, """
        select v as name, count(*) as n
        from mentions m
        cross join lateral jsonb_array_elements_text(m.descriptors) v
        where jsonb_typeof(m.descriptors) = 'array' and v is not null
        group by 1 having count(*) >= 3
        order by 2 desc, 1 limit 60
    """)
    return {"cuisines": cuisines, "boroughs": boroughs,
            "statuses": statuses, "descriptors": descriptors}


def stats(conn, fetch_one):
    return fetch_one(conn, """
        select (select count(*) from mentions)                        as mentions,
               (select count(distinct resolved_key) from entity_alias) as entities,
               (select count(*) from comments)                        as comments,
               (select count(*) from comments
                 where extracted_at is not null)                      as extracted,
               (select count(*) from threads)                         as threads,
               (select string_agg(distinct model_version, ', ')
                  from mentions)                                      as models,
               (select max(created_utc) from comments)                as newest_comment
    """)


def view_health(conn, fetch_all):
    """Which materialized views exist and hold data.

    A view that has never been populated is the difference between an empty
    leaderboard and a broken one, and the API should be able to say which.
    """
    rows = fetch_all(conn, """
        select matviewname as name, ispopulated
        from pg_matviews
        where matviewname in ('entity_alias', 'mention_weights',
                              'momentum_windows', 'entity_leaderboard')
    """)
    return {r["name"]: bool(r["ispopulated"]) for r in rows}


def unresolved(conn, limit, offset, fetch_all, fetch_value):
    """The identity correction queue, worst-first.

    Ordered by mention count because a wrong merge on a place with 200
    mentions costs 200 rows of evidence and one on one with 3 costs 3. Fuzzy
    matches are included: they are the ones a threshold guessed at, which is
    exactly what a person is needed to confirm.
    """
    base = """
        from mention_resolution res
        left join alias_overrides o on o.entity_key = res.entity_key
        where o.entity_key is null
          and res.status in ('unverified', 'unlisted', 'fuzzy')
    """
    total = fetch_value(conn, f"select count(*) {base}", (), default=0)
    rows = fetch_all(conn, f"""
        select res.entity_key, res.mentions, res.distinct_authors, res.threads,
               res.status, res.fuzzy_match, res.fuzzy_score
        {base}
        order by res.mentions desc, res.entity_key
        limit %s offset %s
    """, (limit, offset))
    return rows, total


def upsert_alias(conn, entity_key, resolved_key, note, fetch_one):
    return fetch_one(conn, """
        insert into alias_overrides (entity_key, resolved_key, note)
        values (%s, %s, %s)
        on conflict (entity_key) do update
          set resolved_key = excluded.resolved_key,
              note         = excluded.note,
              created_at   = now()
        returning entity_key, resolved_key, note, created_at
    """, (entity_key, resolved_key, note))


def delete_alias(conn, entity_key, fetch_value):
    return fetch_value(conn, """
        delete from alias_overrides where entity_key = %s returning entity_key
    """, (entity_key,))


def list_aliases(conn, limit, offset, fetch_all, fetch_value):
    total = fetch_value(conn, "select count(*) from alias_overrides", (), default=0)
    rows = fetch_all(conn, """
        select entity_key, resolved_key, note, created_at
        from alias_overrides
        order by created_at desc
        limit %s offset %s
    """, (limit, offset))
    return rows, total


def entity_exists(conn, entity_key, fetch_value):
    return fetch_value(conn,
                       "select 1 from entity_leaderboard where entity_key = %s",
                       (entity_key,)) is not None
