"""Every SQL statement the API runs.

Kept apart from the routers so the shape of a query is reviewable next to the
views it reads, and so nothing that builds SQL is mixed in with HTTP handling.

Three rules hold throughout:

  * Values are ALWAYS bound parameters. The only strings interpolated into SQL
    are looked up in a whitelist dict first (ORDER BY cannot take a parameter),
    so nothing a caller types reaches the statement.
  * Anything keyed on an entity reaches its evidence through `entity_alias`.
    l.entity_key is a RESOLVED key; mentions are keyed on what people actually
    typed. Joining them directly silently drops every merged spelling.
  * A place is (subreddit, entity_key): every city collected is scored in the
    same views (scoring.sql), so every function here takes `sub`, the
    subreddit whose board the request is about, right after the connection,
    and every read of a scoring view filters on it. A name alone would
    answer with another city's place of the same name. A mention has no
    subreddit of its own; it is its comment's, which is why PLACE_MENTIONS
    joins comments.

Evidence is read from `live_mentions`, not `mentions`. Two extractions write
into mentions side by side (the old prompts and v6), and live_mentions is the
one the board counts, chosen by extraction_settings (extract_v6_schema.sql).
Reading mentions directly would show both. Joins on a mention id that came
from mention_weights or mention_v2 may use mentions: those ids are already
live ones.
"""

import time

from psycopg2.errors import QueryCanceled, UndefinedColumn, UndefinedTable
from psycopg2.extras import Json

import embedding
import refresh

from . import dishes as dish_groups
from .models import (ASPECTS, CATEGORY_VOICE_FILTERS, DEFAULT_SORT, OVERALL_BOARDS,
                     RATING_CATEGORIES, SORTS, V2_SORTS, VOICE_FILTERS)
from .rankcache import RankCache

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

# entity_leaderboard_v2 has every column above under the same name, then these.
V2_COLUMNS = """,
    l.recent_people, l.recent_reach, l.opinion_people, l.strong_neg_people,
    l.strong_neg_share, l.top_neg_score, l.flagged, l.sentiment, l.trend_pct,
    l.rank_score
"""

BOARDS = {"v1": "entity_leaderboard", "v2": "entity_leaderboard_v2"}


def like_escape(text):
    """`text` with LIKE's own wildcards escaped, so a search for "100%" or
    "a_b" means those characters and not "anything"."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_pattern(text):
    """`text` as an escaped contains-pattern. Every LIKE on caller input goes
    through this or like_escape."""
    return "%" + like_escape(text) + "%"


def _columns(algo):
    return BOARD_COLUMNS + (V2_COLUMNS if algo == "v2" else "")


# Places mentioned under a topic: in a thread whose title names it, or with it
# among the commenter's descriptors or dishes. mention_weights carries the
# RESOLVED key, so merged spellings count. v2 also needs each person's recency;
# v1 has no notion of it and takes every mention ever made.
TOPIC_TEXT_MATCH = """(t.title ilike %(topic)s
             or m.descriptors::text ilike %(topic)s
             or m.dishes::text ilike %(topic)s)"""

# The live mentions of the places of one city, each with its comment and the
# alias row that says which place it is. A typed name is only a place within
# its subreddit, so the alias is joined on the comment's.
PLACE_MENTIONS = """
        from live_mentions m
        join comments c on c.id = m.comment_id
        join entity_alias al on al.subreddit = c.subreddit and al.entity_key = m.entity_key
"""

TOPIC_HITS = """
    topic_hits as (
      select w.entity_key, v.person, max(v.w_recency) as w
      from mention_weights w
      join mention_v2 v on v.mention_id = w.mention_id
      join threads    t on t.id = w.thread_id
      join mentions   m on m.id = w.mention_id
      where w.subreddit = %(sub)s
        and {text_match}
        and (%(algo)s = 'v1' or v.w_recency > 0)
      group by 1, 2
    ),
    topic as (
      -- A place whose city cuisine label matches is in the topic with all of
      -- its recent reach: a French restaurant named in a steak thread is
      -- still French.
      select l.entity_key,
             coalesce(h.people, 0) as topic_people,
             greatest(coalesce(h.reach, 0),
                      case when l.cuisine ilike %(topic)s
                           then {cuisine_reach} else 0 end) as topic_reach
      from {board} l
      left join (select entity_key, count(*) as people, sum(w) as reach
                 from topic_hits group by 1) h on h.entity_key = l.entity_key
      where l.subreddit = %(sub)s
        and (h.entity_key is not null or l.cuisine ilike %(topic)s)
    )
"""

# Resolution status for a resolved entity: the strongest status among the
# spellings that merged into it. A lateral rather than a column on the
# materialized view, so scoring.sql stays independent of resolve.sql.
RESOLUTION_LATERAL = """
    left join lateral (
      select res.status, res.fuzzy_match, res.fuzzy_score
      from entity_alias al
      join mention_resolution res on res.subreddit = al.subreddit
                                 and res.entity_key = al.entity_key
      where al.subreddit = l.subreddit and al.resolved_key = l.entity_key
      order by case res.status when 'exact'    then 1
                               when 'fuzzy'    then 2
                               when 'unlisted' then 3
                               else                 4 end
      limit 1
    ) res on true
"""


def _board_filters(sub, f):
    """Translate validated query params into (where_sql, params).

    `f` is a LeaderboardQuery; every field has already been range-checked by
    Pydantic, so this only has to decide which predicates apply. The city is
    always one of them.
    """
    where, params = ["l.subreddit = %s"], [sub]

    if f.search:
        # Both the typed key and the city's display name, so searching
        # "delicatessen" finds katzs whether or not anyone typed it that way.
        where.append("(l.entity_key ilike %s or l.official_name ilike %s)")
        params += [like_pattern(f.search)] * 2
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
        where.append(f"""exists (
            select 1 {PLACE_MENTIONS}
            where al.subreddit = l.subreddit and al.resolved_key = l.entity_key
              and jsonb_typeof(m.descriptors) = 'array'
              and m.descriptors ? %s
        )""")
        params.append(f.descriptor)

    return " where " + " and ".join(where), params


def _named(where, params):
    """_board_filters speaks positional %s; the topic CTE needs named
    parameters. Rename in order so both can share one statement."""
    named = {}
    for i, v in enumerate(params):
        where = where.replace("%s", f"%(p{i})s", 1)
        named[f"p{i}"] = v
    return where, named


def leaderboard_page(conn, sub, f, fetch_all, fetch_value):
    """One page of the board, plus the unpaginated total.

    The count runs against the same predicates so a client can page without
    guessing how many rows exist. Both statements read a materialized table of
    a few thousand rows, so two queries is cheaper than one with a window
    function over the whole set.

    `algo` picks the table; everything else is shared. A v2-only sort under
    v1 falls back to v1's default rather than erroring, so a client can flip
    the switch without also having to reset its sort.
    """
    algo = f.algo
    board = BOARDS[algo]
    sort = f.sort or DEFAULT_SORT[algo]
    if algo == "v1" and sort in V2_SORTS:
        sort = DEFAULT_SORT["v1"]
    order = SORTS[sort]

    where, params = _named(*_board_filters(sub, f))
    cte, join, extra = "", "", ""
    if f.topic:
        params.update(topic=like_pattern(f.topic), algo=algo, sub=sub)
        cuisine_reach = "l.recent_reach" if algo == "v2" else "1"
        cte = "with " + TOPIC_HITS.format(board=board, cuisine_reach=cuisine_reach,
                                          text_match=TOPIC_TEXT_MATCH)
        join = "join topic tp on tp.entity_key = l.entity_key"
        if algo == "v2":
            # Within a topic, rank by reach WITHIN it, not overall reach:
            # Peter Luger is loud everywhere and should not top "omakase".
            extra = """, tp.topic_people,
                tp.topic_reach * (1.0 + l.sentiment) / 2.0
                  * (case when l.flagged
                          then (select flag_penalty from scoring_v2_params)
                          else 1.0 end) as topic_rank"""
            if f.sort is None:
                order = "topic_rank desc nulls last"
        else:
            extra = ", tp.topic_people"

    # The count does NOT get the lateral unless the caller filtered on status.
    # count(*) has no LIMIT to stop at, so joining it would resolve the status
    # of every one of the ~8,000 entities to return a single number -- measured
    # at 2.8s per request, against 3ms for the page itself. The page query
    # keeps the lateral because `status` is part of the response, but there it
    # runs for one page of rows, not the whole board.
    count_join = RESOLUTION_LATERAL if f.status else ""
    total = fetch_value(
        conn, f"{cte} select count(*) from {board} l {join} {count_join} {where}",
        params, default=0)

    rows = fetch_all(conn, f"""
        {cte}
        select {_columns(algo)}, res.status, res.fuzzy_match, res.fuzzy_score {extra}
        from {board} l
        {join}
        {RESOLUTION_LATERAL}
        {where}
        order by {order}, l.entity_key
        limit %(limit)s offset %(offset)s
    """, dict(params, limit=f.limit, offset=f.offset))
    return rows, total


def board_row(conn, sub, entity_key, fetch_one, algo="v1"):
    return fetch_one(conn, f"""
        select {_columns(algo)}, res.status, res.fuzzy_match, res.fuzzy_score
        from {BOARDS[algo]} l
        {RESOLUTION_LATERAL}
        where l.subreddit = %s and l.entity_key = %s
    """, (sub, entity_key))


def aspect_detail(conn, sub, entity_key, fetch_all, algo="v1"):
    """Per-aspect workings: what the mentions said, and what it was shrunk to."""
    table = "aspect_scores_v2" if algo == "v2" else "aspect_scores"
    return fetch_all(conn, f"""
        select aspect, n_obs, aspect_weight, raw_mean, city_mean, aspect_score
        from {table}
        where subreddit = %s and entity_key = %s
        order by array_position(
            array['food','value','service','atmosphere','wait'], aspect)
    """, (sub, entity_key))


def momentum_windows(conn, sub, entity_key, fetch_all):
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
        where ma.subreddit = %s and ma.entity_key = %s
        order by ma.window_days
    """, (sub, entity_key))


def spellings(conn, sub, entity_key, fetch_all):
    """Which typed names merged into this entity, and by what method."""
    return fetch_all(conn, """
        select a.entity_key, a.method, a.score,
               (select count(*) from live_mentions m
                  join comments c on c.id = m.comment_id
                 where m.entity_key = a.entity_key and c.subreddit = a.subreddit)
                 as mentions
        from entity_alias a
        where a.subreddit = %s and a.resolved_key = %s
        order by mentions desc, a.entity_key
    """, (sub, entity_key))


_summary_ready = {"at": None, "ready": False}


def forget_summary_ready():
    _summary_ready.update(at=None)


def summary_ready(conn, fetch_value):
    """Whether place_summaries exists with its per-city key, cached with the
    rating views' TTLs so a database without it does not run a failing
    statement on every card load. A table from before summaries were keyed by
    subreddit counts as absent: its rows cannot be read for one city, and the
    poller's next boot upgrades it (summary_schema.sql)."""
    now = time.monotonic()
    at, ready = _summary_ready["at"], _summary_ready["ready"]
    if at is not None and now - at < RATING_READY_TTL[ready]:
        return ready
    ready = bool(fetch_value(conn, """
        select exists (select 1 from pg_attribute
                       where attrelid = to_regclass('place_summaries')
                         and attname = 'subreddit' and not attisdropped)
    """, default=False))
    _summary_ready.update(at=now, ready=ready)
    return ready


def place_summary(conn, sub, entity_key, fetch_one, fetch_value):
    """The AI-written summary of what the sub says about a place, or None.
    A summary is keyed by subreddit and resolved name, so another city's place
    of the same name is never shown here. Only about a hundred busy places
    have one, so None is the normal answer; it is also the answer when
    place_summaries does not exist (an old or local database). comment_count
    is input_comments, the comments the model was actually sent. The table's
    bookkeeping columns are left unread on purpose."""
    if not summary_ready(conn, fetch_value):
        return None
    try:
        return fetch_one(conn, """
            select summary as text, input_comments as comment_count, written_at
            from place_summaries
            where subreddit = %s and resolved_key = %s and summary is not null
        """, (sub, entity_key))
    except (UndefinedTable, UndefinedColumn):
        # Dropped since the check: roll back so the connection stays usable.
        conn.rollback()
        forget_summary_ready()
        return None


def official_record(conn, sub, entity_key, fetch_one):
    """The city's own record of the place, from its city's list (`places`,
    scoring.sql). `boroughs` is the list's areas, under the name the board
    reads them by."""
    return fetch_one(conn, """
        select name, name_key, cuisine, areas as boroughs, location_count,
               addresses, is_chain, closed, last_seen
        from places
        where subreddit = %s and name_key = %s
    """, (sub, entity_key))


def _jsonb_top(conn, sub, entity_key, column, fetch_all, limit=15):
    """Top values from a jsonb array column on mentions.

    column is a module-level literal, never caller input. The array-type guard
    matters: a model that emitted a bare string instead of a list would
    otherwise abort the whole query.
    """
    return fetch_all(conn, f"""
        select v as name, count(*) as n
        {PLACE_MENTIONS}
        cross join lateral jsonb_array_elements_text(m.{column}) v
        where al.subreddit = %s and al.resolved_key = %s
          and jsonb_typeof(m.{column}) = 'array'
        group by 1
        order by 2 desc, 1
        limit %s
    """, (sub, entity_key, limit))


def top_dishes(conn, sub, entity_key, fetch_all, limit=15):
    """Dishes by distinct mentions, with names that are one dish merged and
    filler dropped (dishes.py). Grouped in Python because the merge is a
    lookup, and a place has at most a few hundred mentions with dishes."""
    rows = fetch_all(conn, f"""
        select m.dishes
        {PLACE_MENTIONS}
        where al.subreddit = %s and al.resolved_key = %s
          and jsonb_typeof(m.dishes) = 'array'
    """, (sub, entity_key))
    return dish_groups.top([r["dishes"] for r in rows], sub, entity_key, limit)


def top_descriptors(conn, sub, entity_key, fetch_all):
    return _jsonb_top(conn, sub, entity_key, "descriptors", fetch_all)


def neighborhoods(conn, sub, entity_key, fetch_all):
    return fetch_all(conn, f"""
        select m.neighborhood_hint as name, count(*) as n
        {PLACE_MENTIONS}
        where al.subreddit = %s and al.resolved_key = %s
          and m.neighborhood_hint is not null
        group by 1
        order by 2 desc
        limit 10
    """, (sub, entity_key))


def permalink_sql(alias):
    """The permalink of `alias`'s row, or NULL once it was deleted from Reddit.

    SPEC.md makes click-through non-negotiable, and the other half of that
    promise is never linking something that 404s. Written once, here, so no
    query can return a link without the rule.
    """
    return f"case when {alias}.was_deleted_later then null else {alias}.permalink end"


# What every mention-returning query selects, in the shape models.Mention
# reads. Needs `m` (mentions), `c` (comments) and `t` (threads) in scope.
#
# The jsonb columns are typed here rather than trusted: two legacy rows store
# descriptors as a bare string, and each of those turned a whole restaurant's
# comment list into a 500. A value of the wrong shape reads as absent.
MENTION_COLUMNS = f"""
    m.id as mention_id, m.comment_id, m.restaurant_raw,
    m.entity_key as typed_key,
    case when jsonb_typeof(m.aspects) = 'object' then m.aspects end as aspects,
    case when jsonb_typeof(m.dishes) = 'array' then m.dishes end as dishes,
    case when jsonb_typeof(m.descriptors) = 'array' then m.descriptors end as descriptors,
    m.expensiveness, m.is_firsthand, m.is_negated,
    m.neighborhood_hint,
    c.author, c.score, c.controversiality, c.created_utc, c.body,
    {permalink_sql("c")} as permalink,
    c.was_deleted_later,
    t.id as thread_id, t.title as thread_title
"""


MENTION_SORTS = {
    "recent": "c.created_utc desc",
    "oldest": "c.created_utc asc",
    "score":  "c.score desc nulls last",
}


def mentions_page(conn, sub, entity_key, q, fetch_all, fetch_value):
    """The evidence behind a score.

    permalink is returned as NULL when the comment is gone from Reddit rather
    than left for the client to suppress. SPEC.md calls click-through
    non-negotiable, and the other half of that promise is never linking
    something that 404s -- which is only kept if the API keeps it.
    """
    where = ["al.subreddit = %s", "al.resolved_key = %s"]
    params = [sub, entity_key]

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
        {PLACE_MENTIONS}
        join threads  t on t.id = c.thread_id
        where {" and ".join(where)}
    """

    total = fetch_value(conn, f"select count(*) {base}", params, default=0)
    rows = fetch_all(conn, f"""
        select {MENTION_COLUMNS}
        {base}
        order by {MENTION_SORTS[q.sort]}, m.id
        limit %s offset %s
    """, params + [q.limit, q.offset])
    return rows, total


def feed_items(conn, sub, q, places_only, before, after, limit, fetch_all):
    """One subreddit's posts and comments together, newest first, optionally only those
    containing `q`. Comments carry the places they mention, in the order they
    mention them; posts carry none (extraction reads comments only), so
    `places_only` leaves posts out.

    `before` / `after` are (created_utc, id) pairs: id breaks ties between
    items posted in the same second (t1_ comments and t3_ posts never collide).
    `after` returns the `limit` items immediately after the cursor, not the
    newest `limit`: a reader catching up must not skip what came in between.
    They still come back newest first, so a full page means "ask again".
    A text search has no index; it walks comments_created_idx backwards, which
    is ~0.1s for a common word and ~1s for one that is in nothing. Posts are
    few enough (~43k) to scan.
    """
    # The feed is one city's, and the tables hold every city. Filtered first,
    # where comments_sub_created_idx can walk one city's comments in order.
    c_where = ["c.subreddit = %(sub)s", "c.body not in ('[deleted]', '[removed]')"]
    t_where = ["t.subreddit = %(sub)s"]
    params = {"limit": limit, "sub": sub}
    if q:
        c_where.append("c.body ilike %(q)s")
        t_where.append("(t.title ilike %(q)s or t.selftext ilike %(q)s)")
        params["q"] = like_pattern(q)
    if places_only:
        c_where.append("exists (select 1 from live_mentions m where m.comment_id = c.id)")
    for cursor, op, name in ((before, "<", "b"), (after, ">", "a")):
        if cursor:
            c_where.append(f"(c.created_utc, c.id) {op} (%({name}_at)s, %({name}_id)s)")
            t_where.append(f"(t.created_utc, t.id) {op} (%({name}_at)s, %({name}_id)s)")
            params[f"{name}_at"], params[f"{name}_id"] = cursor
    # Walk away from the cursor: `before` down from it, `after` up from it.
    d = "asc" if after else "desc"
    posts = "" if places_only else f"""
          union all
          (select 'post', t.id, t.id, t.author, t.score, t.created_utc,
                  case when t.selftext in ('[deleted]', '[removed]') then '' else coalesce(t.selftext, '') end,
                  '/r/' || t.subreddit || '/comments/' || substr(t.id, 4) || '/', t.was_deleted_later
           from threads t
           where {" and ".join(t_where)}
           order by t.created_utc {d}, t.id {d}
           limit %(limit)s)"""
    return fetch_all(conn, f"""
        with page as (
          select * from (
            (select 'comment' as kind, c.id, c.thread_id, c.author, c.score, c.created_utc,
                    c.body, c.permalink, c.was_deleted_later
             from comments c
             where {" and ".join(c_where)}
             order by c.created_utc {d}, c.id {d}
             limit %(limit)s){posts}
          ) u
          order by created_utc {d}, id {d}
          limit %(limit)s
        )
        select p.kind, p.id, p.author, p.score, p.created_utc, p.body,
               {permalink_sql("p")} as permalink,
               p.was_deleted_later, t.title,
               case when p.kind = 'post' then
                 greatest(t.num_comments, (select count(*) from comments x where x.thread_id = t.id))
               end as num_comments,
               coalesce(pl.places, '[]'::json) as places
        from page p
        join threads t on t.id = p.thread_id
        left join lateral (
          select json_agg(json_build_object('key', x.key, 'official_name', x.official_name)
                          order by x.first) as places
          from (
            select al.resolved_key as key, min(m.id) as first, max(l.official_name) as official_name
            from live_mentions m
            join entity_alias al on al.subreddit = %(sub)s and al.entity_key = m.entity_key
            join entity_leaderboard l on l.subreddit = al.subreddit
                                     and l.entity_key = al.resolved_key
            where m.comment_id = p.id
            group by al.resolved_key
          ) x
        ) pl on true
        order by p.created_utc desc, p.id desc
    """, params)


def standout_negatives(conn, sub, entity_key, limit, fetch_all):
    """The comments behind a v2 flag: recent, firsthand, strongly negative,
    harshest and most upvoted first. Same shape as mentions_page so the UI renders both alike."""
    return fetch_all(conn, f"""
        select {MENTION_COLUMNS}
        from mention_v2 v
        join mentions m on m.id = v.mention_id
        join comments c on c.id = v.comment_id
        join threads  t on t.id = v.thread_id
        cross join scoring_v2_params p
        where v.subreddit = %s and v.entity_key = %s
          and v.age_days <= p.recent_days
          and v.is_firsthand
          and v.worst <= p.strong_neg
        -- Harshest and most agreed-with first: worst is <= -0.6 here, so the
        -- product is most negative for a severe complaint the sub upvoted.
        order by v.worst * v.w_agree asc, c.created_utc desc
        limit %s
    """, (sub, entity_key, limit))


def search(conn, sub, q, limit, fetch_all):
    """Typeahead. Deliberately does not touch the scoring views.

    Prefix match first, then trigram similarity, so typing "katz" ranks katzs
    above an incidental substring match elsewhere.
    """
    return fetch_all(conn, """
        select l.entity_key, coalesce(l.official_name, l.entity_key) as display_name,
               l.raw_mentions, l.cuisine
        from entity_leaderboard l
        where l.subreddit = %s
          and (l.entity_key ilike %s or l.official_name ilike %s)
        order by (l.entity_key ilike %s) desc,
                 similarity(l.entity_key, %s) desc,
                 l.raw_mentions desc nulls last
        limit %s
    """, (sub, like_pattern(q), like_pattern(q), like_escape(q) + "%", q, limit))


def facets_version(conn, fetch_value):
    """A cheap fingerprint of what facets() and the ledger's rankings read,
    so a result can be kept until a refresh changes it.

    The newest mention the scoring layer has weighed moves on every refresh
    that brought in new evidence, and is an index lookup (mention_weights_pk)
    rather than the full scan of mentions that the descriptor counts cost.
    One number for every city: a refresh rebuilds them all together.
    """
    return fetch_value(conn, "select max(mention_id) from mention_weights")


def facets(conn, sub, fetch_all):
    cuisines = fetch_all(conn, """
        select cuisine as name, count(*) as n
        from entity_leaderboard
        where subreddit = %s and cuisine is not null
        group by 1 order by 2 desc, 1 limit 40
    """, (sub,))
    # The parts of the city its places are in: the five boroughs in New York,
    # and as many as 80 cities and districts elsewhere, so the most common.
    boroughs = fetch_all(conn, """
        select b as name, count(*) as n
        from entity_leaderboard l, unnest(l.boroughs) b
        where l.subreddit = %s
        group by 1 order by 2 desc, 1 limit 40
    """, (sub,))
    statuses = fetch_all(conn, """
        select status as name, count(*) as n
        from mention_resolution
        where subreddit = %s
        group by 1 order by 2 desc, 1
    """, (sub,))
    # The vocabulary is open by design (the prompt says so), so this reports
    # what the model actually produced rather than a fixed list. A full scan of
    # the city's mentions, so the router keeps the result until facets_version
    # moves.
    descriptors = fetch_all(conn, """
        select v as name, count(*) as n
        from mention_weights w
        join mentions m on m.id = w.mention_id
        cross join lateral jsonb_array_elements_text(m.descriptors) v
        where w.subreddit = %s
          and jsonb_typeof(m.descriptors) = 'array' and v is not null
        group by 1 having count(*) >= 3
        order by 2 desc, 1 limit 60
    """, (sub,))
    return {"cuisines": cuisines, "boroughs": boroughs,
            "statuses": statuses, "descriptors": descriptors}


def stats(conn, sub, fetch_one):
    """Corpus counts for one city; the other cities collected beside it are
    not what these numbers describe. Mentions and models are read live, not
    from the scoring layer, so a switch of extraction shows at once; a
    mention's city is its comment's."""
    return fetch_one(conn, """
        select (select count(*) from live_mentions m
                  join comments c on c.id = m.comment_id
                 where c.subreddit = %(sub)s)                         as mentions,
               (select count(distinct resolved_key) from entity_alias
                 where subreddit = %(sub)s)                           as entities,
               (select count(*) from comments
                 where subreddit = %(sub)s)                           as comments,
               -- Each extraction keeps its own cursor (extract_v6_schema.sql),
               -- so "extracted" follows the one the board is reading.
               (select case (select read_version from extraction_settings)
                         when 'v6' then
                           (select count(*) from extraction_state s
                              join comments c on c.id = s.item_id
                             where s.version = 'v6' and s.extracted_at is not null
                               and c.subreddit = %(sub)s)
                         else
                           (select count(*) from comments
                             where subreddit = %(sub)s
                               and extracted_at is not null)
                       end)                                           as extracted,
               (select count(*) from threads
                 where subreddit = %(sub)s)                           as threads,
               (select string_agg(distinct m.model_version, ', ')
                  from live_mentions m
                  join comments c on c.id = m.comment_id
                 where c.subreddit = %(sub)s)                         as models,
               (select max(created_utc) from comments
                 where subreddit = %(sub)s)                           as newest_comment
    """, {"sub": sub})


def view_health(conn, fetch_all):
    """Which materialized views exist and hold data.

    A view that has never been populated is the difference between an empty
    leaderboard and a broken one, and the API should be able to say which.
    The list is refresh.VIEWS, the one refresh.py rebuilds, so a view added
    there is reported here without anyone remembering to; a missing one
    reads as False rather than vanishing from the answer.
    """
    names = [name for name, _ in refresh.VIEWS]
    rows = fetch_all(conn, """
        select matviewname as name, ispopulated
        from pg_matviews
        where schemaname = current_schema() and matviewname = any(%s)
    """, (names,))
    populated = {r["name"]: bool(r["ispopulated"]) for r in rows}
    return {name: populated.get(name, False) for name in names}


def unresolved(conn, sub, limit, offset, fetch_all, fetch_value):
    """The identity correction queue, worst-first.

    Ordered by mention count because a wrong merge on a place with 200
    mentions costs 200 rows of evidence and one on one with 3 costs 3. Fuzzy
    matches are included: they are the ones a threshold guessed at, which is
    exactly what a person is needed to confirm.
    """
    base = """
        from mention_resolution res
        left join alias_overrides o on o.subreddit = res.subreddit
                                   and o.entity_key = res.entity_key
        where res.subreddit = %s
          and o.entity_key is null
          and res.status in ('unverified', 'unlisted', 'fuzzy')
    """
    total = fetch_value(conn, f"select count(*) {base}", (sub,), default=0)
    rows = fetch_all(conn, f"""
        select res.entity_key, res.mentions, res.distinct_authors, res.threads,
               res.status, res.fuzzy_match, res.fuzzy_score
        {base}
        order by res.mentions desc, res.entity_key
        limit %s offset %s
    """, (sub, limit, offset))
    return rows, total


def upsert_alias(conn, sub, entity_key, resolved_key, note, fetch_one):
    return fetch_one(conn, """
        insert into alias_overrides (subreddit, entity_key, resolved_key, note)
        values (%s, %s, %s, %s)
        on conflict (subreddit, entity_key) do update
          set resolved_key = excluded.resolved_key,
              note         = excluded.note,
              created_at   = now()
        returning subreddit, entity_key, resolved_key, note, created_at
    """, (sub, entity_key, resolved_key, note))


def delete_alias(conn, sub, entity_key, fetch_value):
    return fetch_value(conn, """
        delete from alias_overrides where subreddit = %s and entity_key = %s
        returning entity_key
    """, (sub, entity_key))


def list_aliases(conn, sub, limit, offset, fetch_all, fetch_value):
    total = fetch_value(conn, "select count(*) from alias_overrides where subreddit = %s",
                        (sub,), default=0)
    rows = fetch_all(conn, """
        select subreddit, entity_key, resolved_key, note, created_at
        from alias_overrides
        where subreddit = %s
        order by created_at desc
        limit %s offset %s
    """, (sub, limit, offset))
    return rows, total


def entity_exists(conn, sub, entity_key, fetch_value):
    return fetch_value(conn,
                       "select 1 from entity_leaderboard where subreddit = %s and entity_key = %s",
                       (sub, entity_key)) is not None


def cities(conn, fetch_all):
    """The subreddits that have a board, with how many places each holds."""
    return fetch_all(conn, """
        select subreddit, count(*) as places
        from entity_leaderboard
        group by subreddit
    """)


# ---------------------------------------------------------------------------
# The ledger: rankings over a rolling window, for the React frontend.
#
# Counts are raw mentions (one row of mention_weights each), not decayed
# volume: the ledger shows "84 mentions in the last 30 days", and a decayed
# figure would be a number nobody can check against the comments.
# ---------------------------------------------------------------------------

# "Known for" filters: keep a place only if people rate that aspect at least
# this well. The column name is interpolated, so these keys are the whitelist.
LEDGER_NEEDS = {"value": 0.2, "atmosphere": 0.3, "service": 0.2, "wait": -0.1}

# A flaw is the bottom slice of scored places for an aspect, measured live.
LEDGER_FLAW_SHARE = 0.10                                     # TUNE

# Per-category ranking as (where_sql, rank_sql), both written against the
# `pool` CTE in ledger_ranking, and both module literals -- never caller input.
LEDGER_CATEGORIES = {
    "top":      ("current > 0",
                 "current"),
    # Loved, but talked about no more than the median place this window.
    # raw_mentions >= 3 so a single glowing comment is not a gem.
    "gems":     ("sentiment >= 0.25 and current >= 1 and current <= median.m"
                 " and raw_mentions >= 3",                    # TUNE gem thresholds
                 "sentiment"),
}


# The same categories under scoring v2 (scoring_v2.sql). `people` is distinct
# commenters in the window, `sentiment` is v2's (negatives 2x, bare name-drops
# ignored) and a flagged place -- a big share of recent opinion is a bad
# firsthand experience -- ranks at flag_penalty.
_FLAG_PENALTY = ("(case when flagged then (select flag_penalty from scoring_v2_params)"
                 " else 1.0 end)")
LEDGER_CATEGORIES_V2 = {
    "top":      ("current > 0",
                 f"people * (1.0 + coalesce(sentiment, 0)) / 2.0 * {_FLAG_PENALTY}"),
    "gems":     (LEDGER_CATEGORIES["gems"][0] + " and not coalesce(flagged, false)",
                 "sentiment"),
}

def _ledger_select(algo):
    """The per-place columns that differ by algorithm."""
    if algo == "v2":
        return """l.sentiment, l.flagged, l.strong_neg_people, l.strong_neg_share,
                  l.recent_people"""
    return """(select avg(x) from unnest(array[l.food, l.value, l.service,
                                                l.atmosphere, l.wait]) x) as sentiment,
              null::boolean as flagged, null::int as strong_neg_people,
              null::float8 as strong_neg_share, null::int as recent_people"""


def _ledger_columns(algo):
    """A ledger row's leaderboard columns, over `l`: everything but the
    windowed counts. One list for the ranking's pool and the page's rows, so
    a page cut from a cached ranking has the columns the ranking had."""
    return f"""l.official_name, l.cuisine, l.boroughs,
               l.raw_mentions, l.distinct_authors,
               l.food, l.value, l.service, l.atmosphere, l.wait,
               {_ledger_select(algo)}"""


# A topic narrows what is COUNTED, not just which rows show: "omakase" over a
# month means mentions in omakase threads or tagged omakase, so Keens' two
# passing omakase mentions do not ride its steakhouse volume to the top. A
# place the city files under that cuisine counts in full.
TOPIC_JOIN = """
    join threads t on t.id = v.thread_id
    join mentions m on m.id = v.mention_id
    left join places rt on rt.subreddit = v.subreddit and rt.name_key = v.entity_key
"""
TOPIC_WHERE = f"""
    and ({TOPIC_TEXT_MATCH}
         or rt.cuisine ilike %(topic)s)
"""


def _people_sql(algo):
    """Distinct commenters in the window, v2 only: v1 has no use for it, and
    the count(distinct) is not free."""
    if algo != "v2":
        return "null::bigint as people"
    return ("count(distinct v.person) filter (where v.created_utc >"
            " now() - make_interval(days => %(window)s)) as people")


def window_counts_sql(where, algo="v1", topic=None, group=False):
    """Mentions in the window (`current`), in the window before it
    (`previous`) and, under v2, distinct people in the window -- the counts
    every ledger-shaped row carries. One statement for all three callers, so
    a list, a single place and a rating board count alike: `group` for
    every place of the city at once (ledger_ranking), else one place picked by
    `where`, as a lateral (ledger_one, board_items). Needs %(sub)s and
    %(window)s, and %(topic)s when `topic` is set."""
    return f"""
          select {"v.entity_key," if group else ""}
                 count(*) filter (where v.created_utc >  now() - make_interval(days => %(window)s)) as current,
                 count(*) filter (where v.created_utc <= now() - make_interval(days => %(window)s)) as previous,
                 {_people_sql(algo)}
          from mention_v2 v
          {TOPIC_JOIN if topic else ""}
          where v.subreddit = %(sub)s
            and {where}
            and v.created_utc > now() - make_interval(days => 2 * %(window)s)
            {TOPIC_WHERE if topic else ""}
          {"group by v.entity_key" if group else ""}"""


# How long one computed ranking serves the pages of its list. Ranking a list
# aggregates every mention of the city in the window (0.1 s to 1 s on the
# production database), and a reader scrolling to the end asks for a page
# every few seconds. The key carries facets_version, so a refresh that brings
# in new mentions starts every list afresh; the TTL bounds what that misses
# -- a refresh that only re-resolved names, and the window sliding forward
# with the clock -- to a minute.
LEDGER_CACHE_TTL = 60.0
# How many rankings one worker keeps. Only lists someone has scrolled past
# their first page are cached (ledger_page). An entry is (key, current,
# previous, people) per ranked place, about 140 bytes each: a filtered list
# is a few hundred places, the largest (r/FoodNYC over a year, unfiltered)
# ~23,000, 3.3 MB. So one worker holds at most ~53 MB of them, and the two
# web workers (Procfile) ~105 MB together, in the worst case; a typical
# worker a few MB, since few combinations come near that size.
LEDGER_CACHE_ENTRIES = 16
# How long a request waits for another request's ranking of the same list
# before giving up. It holds a pooled connection while it waits, so it gives
# up well before the 10 s statement timeout (app/db.py) would end a query of
# its own; a ranking normally takes under a second. It is answered as a
# timed-out query is: 503, try again.
LEDGER_CACHE_WAIT = 4.0
LEDGER_CACHE = RankCache(
    LEDGER_CACHE_TTL, LEDGER_CACHE_ENTRIES, LEDGER_CACHE_WAIT,
    timeout_error=lambda: QueryCanceled("waited too long for another request's ranking"))


def ledger_page(conn, sub, category, window, cuisine, borough, needs, flaws, limit,
                fetch_all, fetch_value, algo="v1", topic=None, offset=0):
    """One ranked page for (category, window, filters) and the number of
    places the whole list holds.

    Most lists are only ever read to their first page, so a first page is
    answered by the ranking statement with a LIMIT, as it always was, and
    nothing is kept. The first request past it ranks the whole list once and
    caches it (LEDGER_CACHE), and every later page -- the first one too,
    while the entry lasts -- is cut from that, with its rows read for its
    places alone. Counts on a page cut from the cache can lag the comments
    by up to LEDGER_CACHE_TTL.

    The cache key is exactly the arguments ledger_ranking is called with,
    plus facets_version, so nothing that changes the list can be left out of
    it. Needs and flaws are sorted for the key because their order does not
    change the list.
    """
    args = (sub, category, window, cuisine, borough, tuple(sorted(needs)), tuple(sorted(flaws)),
            algo, topic)
    key = (facets_version(conn, fetch_value),) + args
    ranked = LEDGER_CACHE.peek(key)
    if ranked is None and offset == 0:
        return ledger_first_page(conn, *args, fetch_all=fetch_all, limit=limit)
    if ranked is None:
        ranked = LEDGER_CACHE.get(key, lambda: ledger_ranking(conn, *args, fetch_all=fetch_all))
    # A place in a cached ranking can have left the board since (a refresh
    # that only re-resolved names merged it away). The client takes a short
    # page for the end of the list, so a page is topped up from the places
    # ranked after it, and is short only where the ranking runs out.
    rows, start = [], offset
    while len(rows) < limit and start < len(ranked):
        chunk = ranked[start:start + limit - len(rows)]
        rows += _ledger_rows(conn, sub, chunk, algo, fetch_all)
        start += len(chunk)
    return rows, len(ranked)


def _ledger_rows(conn, sub, ranked, algo, fetch_all):
    """Ledger rows for a slice of a ledger_ranking, in its order: its counts
    with each place's leaderboard columns. A place no longer on the board is
    left out."""
    if not ranked:
        return []
    found = {r["entity_key"]: r for r in fetch_all(conn, f"""
        select l.entity_key, {_ledger_columns(algo)}
        from {BOARDS[algo]} l
        where l.subreddit = %(sub)s and l.entity_key = any(%(keys)s)
    """, {"sub": sub, "keys": [r[0] for r in ranked]})}
    return [{"entity_key": key, "current": current, "previous": previous, "people": people,
             **found[key]}
            for key, current, previous, people in ranked if key in found]


def ledger_first_page(conn, sub, category, window, cuisine, borough, needs, flaws, algo, topic,
                      fetch_all, limit):
    """The first `limit` rows of one list, whole, and how many places the
    list holds: the ranking statement with a LIMIT, for a list nobody has
    scrolled."""
    sql, params = _ledger_statement(sub, category, window, cuisine, borough, needs, flaws,
                                    algo, topic, limit)
    rows = fetch_all(conn, sql, params)
    total = rows[0]["total"] if rows else 0
    return [{k: v for k, v in r.items() if k not in ("rank_value", "total")} for r in rows], total


def ledger_ranking(conn, sub, category, window, cuisine, borough, needs, flaws, algo, topic,
                   fetch_all):
    """Every place on one list, ranked, as (entity_key, current, previous,
    people) tuples: the windowed counts, which are what costs to compute.
    The leaderboard columns are read per page (_ledger_rows), so a cached
    ranking stays small."""
    sql, params = _ledger_statement(sub, category, window, cuisine, borough, needs, flaws,
                                    algo, topic)
    # Tuples, not dicts: a fraction of the memory, and immutable, so threads
    # reading the same cached ranking cannot change it under each other.
    return tuple((r["entity_key"], r["current"], r["previous"], r["people"])
                 for r in fetch_all(conn, sql, params))


def _ledger_statement(sub, category, window, cuisine, borough, needs, flaws, algo, topic,
                      limit=None):
    """The one ranking statement, as (sql, params): for a whole list, or
    with `limit` for its first page, every column and the list's size as
    `total`. One text for both, so a first page answered directly and a page
    cut from a cached ranking cannot rank differently.

    Aspect scores are the all-time shrunk scores from entity_leaderboard; only
    the counts are windowed. A week is too little evidence to score taste.
    """
    where_sql, rank_sql = (LEDGER_CATEGORIES_V2 if algo == "v2" else LEDGER_CATEGORIES)[category]
    board = BOARDS[algo]
    filters, params = [], {"sub": sub, "window": window}
    if topic:
        params["topic"] = like_pattern(topic)
    if cuisine:
        filters.append("l.cuisine = %(cuisine)s")
        params["cuisine"] = cuisine
    if borough:
        filters.append("%(borough)s = any(l.boroughs)")
        params["borough"] = borough
    for need in needs:
        # Key checked against the whitelist; the threshold is bound.
        filters.append(f"l.{need} >= %(need_{need})s")
        params[f"need_{need}"] = LEDGER_NEEDS[need]
    for flaw in flaws:
        # Whitelisted twice: the route's Literal and this check. Compared
        # against the live cut-off in the `cuts` CTE below.
        if flaw not in ASPECTS:
            raise ValueError(f"unknown aspect {flaw!r}")
        filters.append(f"l.{flaw} <= cuts.{flaw}")
    extra = "".join(f" and {f}" for f in filters)
    if flaws:
        params["flaw_share"] = LEDGER_FLAW_SHARE
    # Percentiles over every open, non-chain place with a real score --
    # percentile_cont skips nulls, so "nobody mentioned the wait" never counts
    # as a long one. One pass for all five; only built when a flaw asks.
    cuts_cte = """
        cuts as (
          select """ + ", ".join(
              f"percentile_cont(%(flaw_share)s) within group (order by {a}) as {a}"
              for a in ASPECTS) + """
          from """ + board + """
          where subreddit = %(sub)s
            and coalesce(is_chain, false) = false and coalesce(closed, false) = false
            and raw_mentions >= 3
        ),""" if flaws else ""
    cuts_join = "cross join cuts" if flaws else ""

    # A whole list returns only what a cached ranking keeps; a first page is
    # served as it stands, so it returns every column.
    if limit is None:
        columns, tail = "pool.entity_key, pool.current, pool.previous, pool.people", ""
    else:
        columns, tail = "pool.*, count(*) over () as total", "limit %(limit)s"
        params["limit"] = limit

    # mention_v2 is one row per mention_weights row, plus `person`, which the
    # v2 "top" ranking counts. Raw counts are the same under either algorithm;
    # people are only counted under v2.
    sql = f"""
        with counts as ({window_counts_sql("true", algo, topic, group=True)}
        ),
        -- Over every place mentioned this window, before filters, so a borough
        -- filter does not redefine what "not many people know" means.
        median as (
          select coalesce(percentile_disc(0.5) within group (order by current), 0) as m
          from counts where current > 0
        ),{cuts_cte}
        pool as (
          select c.entity_key, c.current::int as current, c.previous::int as previous,
                 c.people::int as people,
                 {_ledger_columns(algo)}
          from counts c
          join {board} l on l.subreddit = %(sub)s and l.entity_key = c.entity_key
          {cuts_join}
          where coalesce(l.is_chain, false) = false
            and coalesce(l.closed, false) = false
            {extra}
        )
        select {columns}, ({rank_sql})::float8 as rank_value
        from pool cross join median
        where {where_sql}
        order by rank_value desc, current desc, entity_key
        {tail}
    """
    return sql, params


def ledger_one(conn, sub, entity_key, window, fetch_all, algo="v1", topic=None):
    """ledger_page's row shape for a single entity, ranked or not.

    Zero counts are real answers here -- a place searched for by name may not
    have been mentioned this window -- so this starts from the leaderboard
    and left-joins the counts rather than starting from the counts. Under a
    `topic` it counts the same mentions ledger_ranking does, so a place opened
    from search shows the numbers it has in the list -- counted now, where a
    list page after the first carries counts from a cached ranking up to
    LEDGER_CACHE_TTL old, so the two can differ by what came in since.
    """
    params = {"sub": sub, "key": entity_key, "window": window}
    if topic:
        params["topic"] = like_pattern(topic)
    return fetch_all(conn, f"""
        select l.entity_key,
               coalesce(c.current, 0)::int  as current,
               coalesce(c.previous, 0)::int as previous,
               c.people::int as people,
               l.official_name, l.cuisine, l.boroughs,
               l.raw_mentions, l.distinct_authors,
               l.food, l.value, l.service, l.atmosphere, l.wait,
               {_ledger_select(algo)}
        from {BOARDS[algo]} l
        left join lateral ({window_counts_sql("v.entity_key = l.entity_key", algo, topic)}
        ) c on true
        where l.subreddit = %(sub)s and l.entity_key = %(key)s
    """, params)


def all_names(conn, sub, min_mentions, fetch_all):
    """Every leaderboard entity with the typed spellings that resolve to it.

    Only spellings that differ from the key itself are listed; the key is
    already searchable. Ordered by mentions so a client that truncates keeps
    the places people actually talk about.
    """
    return fetch_all(conn, """
        select l.entity_key, l.official_name, l.cuisine, l.boroughs[1] as borough,
               l.raw_mentions, l.is_chain, l.closed,
               coalesce(array_agg(a.entity_key order by a.entity_key)
                          filter (where a.entity_key <> l.entity_key), '{}') as aliases
        from entity_leaderboard l
        left join entity_alias a on a.subreddit = l.subreddit and a.resolved_key = l.entity_key
        where l.subreddit = %s and l.raw_mentions >= %s
        group by l.entity_key, l.official_name, l.cuisine, l.boroughs,
                 l.raw_mentions, l.is_chain, l.closed
        order by l.raw_mentions desc nulls last, l.entity_key
    """, (sub, min_mentions))


def ledger_series(conn, sub, keys, window, bucket, fetch_all, topic=None):
    """Mention counts per bucket, for the current and the previous window.

    Buckets count back from now inside each window separately, so the two
    series line up bucket for bucket even when the window is not a whole
    number of weeks. Under a `topic` only the mentions ledger_ranking counts are
    drawn, so the chart adds up to `current` and `previous` when both are
    counted at once. On a list page after the first they are not: the series
    is drawn now and the counts come from a cached ranking up to
    LEDGER_CACHE_TTL old, so they can differ by what came in since.
    """
    if not keys:
        return []
    params = {"sub": sub, "keys": list(keys), "window": window, "bucket": bucket}
    if topic:
        params["topic"] = like_pattern(topic)
    return fetch_all(conn, f"""
        select entity_key,
               age < %(window)s as is_current,
               floor((case when age < %(window)s then age else age - %(window)s end)
                     / %(bucket)s)::int as idx,
               count(*)::int as n
        from (
          select v.entity_key,
                 extract(epoch from (now() - v.created_utc)) / 86400.0 as age
          from mention_v2 v
          {TOPIC_JOIN if topic else ""}
          where v.subreddit = %(sub)s
            and v.entity_key = any(%(keys)s)
            and v.created_utc > now() - make_interval(days => 2 * %(window)s)
            {TOPIC_WHERE if topic else ""}
        ) s
        group by 1, 2, 3
    """, params)


# ---------------------------------------------------------------------------
# The rating (scoring.sql, section 8): stated opinions make the rating, bare
# recommendations only the volume, one voice per person over a fixed window.
# ---------------------------------------------------------------------------

# entity_rating's per-place columns, grouped by what a place with no overall
# voice reports for them (0, false, null), and entity_category_rating's.
# app/routers/ledger.build_rating reads these and passes them to Rating by
# name, so their order does not matter.
RATING_COUNTS = ("pos", "neg", "neutral", "endorse", "superlative", "recommenders")
RATING_FLAGS = ("rankable", "busy")
RATING_VALUES = ("pct_pos", "lb", "badge", "last_voice")
RATING_COLUMNS = RATING_COUNTS + RATING_VALUES + RATING_FLAGS
CATEGORY_RATING_COLUMNS = ("pos", "neg", "neutral", "pct_pos", "lb", "rankable")

# What the rating reads. The web app does not build these -- scoring.sql
# does, on the poller's boot or `refresh.py --apply` -- so a web app deployed
# first, or still running after a rollback dropped them, must not fail on
# its main list. rating_ready() looks them up and keeps the answer a while,
# so it costs one catalog read per worker now and then rather than one per
# request: a yes for 30 seconds, a no for 5, so a fresh apply is picked up
# almost at once. A query that finds them gone anyway forgets the answer
# (forget_rating_ready) and is served as if they were never there. The apply
# runs in another process, so it cannot clear this cache itself; the 5
# seconds are that.
RATING_VIEWS = ("rating_params", "rating_mentions", "place_voices", "place_recommenders",
                "place_category_voices", "entity_rating", "entity_category_rating")
RATING_READY_TTL = {True: 30.0, False: 5.0}
# What a rating query raises when its views are missing, or are an older
# build's without a column this code reads (place_recommenders.recommends).
RATING_MISSING = (UndefinedTable, UndefinedColumn)
_rating_ready = {"at": None, "ready": False}


def rating_ready(conn, fetch_value):
    """Whether every view the rating reads exists, cached (RATING_READY_TTL)."""
    now = time.monotonic()
    at, ready = _rating_ready["at"], _rating_ready["ready"]
    if at is not None and now - at < RATING_READY_TTL[ready]:
        return ready
    ready = bool(fetch_value(conn, """
        select bool_and(to_regclass(n) is not null) from unnest(%s::text[]) n
    """, (list(RATING_VIEWS),), default=False))
    _rating_ready.update(at=now, ready=ready)
    return ready


def forget_rating_ready():
    _rating_ready.update(at=None)


def ratings_for(conn, sub, keys, fetch_all, fetch_value, strict=False):
    """{entity_key: {"overall": entity_rating row or None, "categories": [...],
    "window_days": n}} for the places of `sub` among `keys` that have any rating, read
    for a whole page at once. Every rating the API shows comes through here,
    so this is the one place that degrades: {} when the rating views are not
    built, are an older build's (a column missing), or vanish under the
    query, and the callers show rating: null. `strict` raises instead, for a
    route that turns it into a 503 (app/routers/ledger.rating_only)."""
    if not keys or not rating_ready(conn, fetch_value):
        return {}
    keys = list(keys)
    try:
        # From rating_params, so the window comes back even when no key has
        # an overall row (a place with category voices only).
        overall = fetch_all(conn, f"""
            select p.window_days, er.entity_key, {", ".join(f"er.{c}" for c in RATING_COLUMNS)}
            from rating_params p
            left join entity_rating er on er.subreddit = %s and er.entity_key = any(%s)
        """, (sub, keys))
        categories = fetch_all(conn, f"""
            select entity_key, category, {", ".join(CATEGORY_RATING_COLUMNS)}
            from entity_category_rating
            where subreddit = %s and entity_key = any(%s)
        """, (sub, keys))
    except RATING_MISSING:
        if strict:
            raise
        conn.rollback()
        forget_rating_ready()
        return {}
    window = overall[0]["window_days"]
    out = {}

    def entry(key):
        return out.setdefault(key, {"overall": None, "categories": [], "window_days": window})
    for r in overall:
        if r["entity_key"] is not None:
            entry(r["entity_key"])["overall"] = r
    for c in categories:
        entry(c["entity_key"])["categories"].append(c)
    return out


def rating_lines(conn, sub, fetch_one):
    """The settings and this rebuild's cut-offs for one city. Every
    entity_rating row of a city holds the same lines, so any one will do;
    none at all means no rebuild yet, or no voice in that city."""
    return fetch_one(conn, """
        select p.window_days, p.z, p.min_rated, p.min_category_rated,
               p.busy_pct, p.share_pct, p.gem_pct,
               er.busy_line, er.share_line, er.gem_line
        from rating_params p
        left join lateral (select busy_line, share_line, gem_line
                           from entity_rating where subreddit = %s limit 1) er on true
    """, (sub,))


# Each overall board as (where_sql, order_sql) over `er` (entity_rating), and
# the category boards' over `cr` (entity_category_rating). Module literals,
# never caller input: ORDER BY cannot take a parameter. One value ranks each
# board; everything else is a filter.
RATING_BOARDS = {
    # Every place anyone has stated an opinion of, best liked first. It has
    # no floor of its own: lb is the Wilson lower bound, which already puts
    # 1 for 1 (0.38) far below 50 of 52 (0.91), so thin evidence sinks down
    # the list instead of being cut off it. lb is null only with no pos or neg.
    "top":     ("er.lb is not null",
                "er.lb desc nulls last, er.recommenders desc"),
    # Most recommended, among places liked at least as well as the median.
    "popular": ("er.rankable and er.lb >= er.share_line",
                "er.recommenders desc, er.lb desc nulls last"),
    "gems":    ("er.badge = 'hidden_gem'",
                "er.lb desc nulls last, er.recommenders desc"),
}
CATEGORY_BOARD = ("cr.rankable",
                  "cr.lb desc nulls last, cr.pos + cr.neg desc")
# The route's Literal is the whitelist; this keeps the SQL above in step with it.
assert set(RATING_BOARDS) == set(OVERALL_BOARDS), "RATING_BOARDS out of step with OverallBoard"


def board_items(conn, sub, board, window, cuisine, borough, limit, offset, fetch_all, fetch_value,
                rated=False):
    """One page of a rating board in the row shape ledger_page returns, and
    the number of places the board holds (right even for a page past the
    end). The rating itself is added per page by ratings_for, like any
    ledger row's.

    Chains and closed places are left out, as on the ledger. The rating is
    over rating_params.window_days whatever `window` is; `window` only sets
    the mention counts (current, previous) shown beside it. `rated` keeps
    only places with enough opinions to show a percentage, for a reader of
    Highest rated who shows nothing else (the landing page's three): the
    board itself holds thinner places, and one of those can sit above every
    rated place of a small city. They are counted
    for the page alone, after ranking, so a board costs one pass over a few
    thousand cached rows and one over the page's mentions. Raises one of
    RATING_MISSING when the rating views are missing or stale; the route
    turns that into a 503.
    """
    params = {"sub": sub, "window": window, "limit": limit, "offset": offset}
    if board in OVERALL_BOARDS:
        where_sql, order_sql = RATING_BOARDS[board]
        if rated:
            where_sql += " and er.rankable"
        source = """from entity_rating er
          join entity_leaderboard l on l.subreddit = er.subreddit
                                   and l.entity_key = er.entity_key"""
    elif board in RATING_CATEGORIES:
        where_sql, order_sql = CATEGORY_BOARD
        source = """from entity_category_rating cr
          join entity_leaderboard l on l.subreddit = cr.subreddit
                                   and l.entity_key = cr.entity_key"""
        where_sql += " and cr.category = %(category)s"
        params["category"] = board
    else:
        raise ValueError(f"unknown board {board!r}")
    filters = ["l.subreddit = %(sub)s", where_sql, "coalesce(l.is_chain, false) = false",
               "coalesce(l.closed, false) = false"]
    if cuisine:
        filters.append("l.cuisine = %(cuisine)s")
        params["cuisine"] = cuisine
    if borough:
        filters.append("%(borough)s = any(l.boroughs)")
        params["borough"] = borough
    base = f"{source} where {' and '.join(filters)}"

    total = fetch_value(conn, f"select count(*) {base}", params, default=0)
    rows = fetch_all(conn, f"""
        with page as (
          select l.entity_key, l.official_name, l.cuisine, l.boroughs,
                 l.raw_mentions, l.distinct_authors,
                 l.food, l.value, l.service, l.atmosphere, l.wait,
                 {_ledger_select("v1")},
                 row_number() over (order by {order_sql}, l.entity_key) as position
          {base}
          order by {order_sql}, l.entity_key
          limit %(limit)s offset %(offset)s
        )
        select page.*,
               coalesce(c.current, 0)::int  as current,
               coalesce(c.previous, 0)::int as previous,
               c.people::int                as people
        from page
        left join lateral ({window_counts_sql("v.entity_key = page.entity_key")}
        ) c on true
        order by page.position
    """, params)
    return rows, total


# Which voices /voices lists, as (view, SQL over `pv`). Module literals: the
# caller picks a key, never the text.
#   place_voices        each person's latest stated opinion: the rating
#   place_recommenders  each person's latest stated-or-endorse word: the
#                       volume, with `recommends` saying who counts
# So every list's total is the number on the card it opens from.
VOICE_SOURCES = {
    "pos":          ("place_voices", "pv.voice = 'pos'"),
    "neg":          ("place_voices", "pv.voice = 'neg'"),
    "neutral":      ("place_voices", "pv.voice = 'neutral'"),
    "opinions":     ("place_voices", "pv.voice in ('pos', 'neg')"),          # pos + neg
    "superlative":  ("place_voices", "pv.voice = 'pos' and pv.level = 2"),
    "endorse":      ("place_recommenders", "pv.voice = 'endorse' and pv.recommends"),
    "recommenders": ("place_recommenders", "pv.recommends"),
    "all":          ("place_recommenders", "true"),                          # every person
}
# A category's voices are stated levels only, so only these filters apply,
# with the same tests on place_category_voices' own voice column.
CATEGORY_VOICE_SOURCES = {v: VOICE_SOURCES[v][1] for v in CATEGORY_VOICE_FILTERS}
assert set(VOICE_SOURCES) == set(VOICE_FILTERS), "VOICE_SOURCES out of step with VoiceFilter"


def voices_page(conn, sub, entity_key, voice, category, sort, limit, offset,
                fetch_all, fetch_value):
    """The comments behind a rating: exactly the one mention per person that
    the count was made from, so a list's total is the number on the card.
    Permalinks of comments deleted from Reddit come back NULL (permalink_sql).
    Raises one of RATING_MISSING when the rating views are missing or stale."""
    if category is None:
        table, voice_sql = VOICE_SOURCES[voice]
    elif voice in CATEGORY_VOICE_SOURCES:
        table, voice_sql = "place_category_voices", CATEGORY_VOICE_SOURCES[voice]
    else:
        raise ValueError(f"voice {voice!r} does not apply to a category")
    where = ["pv.subreddit = %s", "pv.entity_key = %s", voice_sql]
    params = [sub, entity_key]
    if category:
        where.append("pv.category = %s")
        params.append(category)
    base = f"""
        from {table} pv
        join mentions m on m.id = pv.mention_id
        join comments c on c.id = pv.comment_id
        join threads  t on t.id = c.thread_id
        where {" and ".join(where)}
    """
    total = fetch_value(conn, f"select count(*) {base}", params, default=0)
    rows = fetch_all(conn, f"""
        select {MENTION_COLUMNS}, pv.voice, pv.level
        {base}
        order by {MENTION_SORTS[sort]}, m.id
        limit %s offset %s
    """, params + [limit, offset])
    return rows, total


def top_neighborhoods(conn, sub, keys, fetch_all):
    """The neighborhood commenters most often place each entity in."""
    if not keys:
        return []
    return fetch_all(conn, f"""
        select distinct on (al.resolved_key)
               al.resolved_key as entity_key, m.neighborhood_hint as name
        {PLACE_MENTIONS}
        where al.subreddit = %s and al.resolved_key = any(%s)
          and m.neighborhood_hint is not null
        group by al.resolved_key, m.neighborhood_hint
        order by al.resolved_key, count(*) desc, m.neighborhood_hint
    """, (sub, list(keys)))


_v6_ready = {"at": None, "ready": False}


def forget_v6_ready():
    _v6_ready.update(at=None)


def v6_ready(conn, fetch_value):
    """Whether the v6 extraction storage is here (extract_v6_schema.sql):
    extraction_state, and the v6 columns on mentions. Cached like
    summary_ready, so an old or local database without it does not run a
    failing statement each time someone opens an extraction."""
    now = time.monotonic()
    at, ready = _v6_ready["at"], _v6_ready["ready"]
    if at is not None and now - at < RATING_READY_TTL[ready]:
        return ready
    ready = bool(fetch_value(conn, """
        select to_regclass('extraction_state') is not null
           and exists (select 1 from pg_attribute
                       where attrelid = to_regclass('mentions')
                         and attname = 'overall_level' and not attisdropped)
    """, default=False))
    _v6_ready.update(at=now, ready=ready)
    return ready


def item_extraction(conn, sub, item_id, prompt_hash, fetch_all, fetch_one, fetch_value):
    """(the mention rows `prompt_hash` wrote for a comment (t1_) or post
    (t3_) of this city, what the extractor's cursor says of the item), or
    None when this database has no v6 extraction storage.

    An item id is Reddit's and names one comment or post in any city, so the
    item is checked to be the page's city's own before anything about it is
    shown, like every other read. A post's mentions carry thread_id and a
    null comment_id; the two kinds are read by separate statements, each on
    its own index, because one statement with an OR over both columns can
    use neither. Read from `mentions`, not `live_mentions`: this is for
    inspecting what the extraction said, live or not. The typed name is
    resolved within the city, where it is a place.

    The cursor row is the item's latest v6 read, under whichever prompt
    that was, so `this_prompt` says whether it is the read the rows are
    from: without it "read, found nothing" would be said of an item whose
    last read was another prompt's. A row with no prompt recorded is not
    this prompt's. `pending` is the row being in a submitted batch: putting
    an item in one sets the row's prompt to the batch's and leaves
    extracted_at as the earlier read left it (extract_v6._submit), so until
    the answer is stored that time belongs to a read this prompt may not
    have made, and it is not returned. Only these, when, and whether it
    failed are returned; the error text, cost, model and attempts are the
    pipeline's bookkeeping and stay out of a public response."""
    if not v6_ready(conn, fetch_value):
        return None
    if item_id.startswith("t3_"):
        table, mine = "threads", "m.thread_id = %(id)s and m.comment_id is null"
    else:
        table, mine = "comments", "m.comment_id = %(id)s"
    in_city = f"exists (select 1 from {table} i where i.id = %(id)s and i.subreddit = %(sub)s)"
    args = {"id": item_id, "sub": sub, "hash": prompt_hash}
    try:
        rows = fetch_all(conn, f"""
            select m.id as mention_id, m.restaurant_raw, m.entity_key,
                   r.resolved_key, r.official_name,
                   m.prompt_hash, m.created_at,
                   m.kind, m.named_in, m.experience, m.opinion, m.avoid,
                   m.overall_level, m.taste_level, m.value_level, m.service_level,
                   m.atmosphere_level, m.wait_level,
                   m.dish_opinions, m.notes, m.tags, m.price_level, m.timeframe,
                   m.trend, m.status, m.is_chain
            from mentions m
            left join lateral (
              select al.resolved_key, l.official_name
              from entity_alias al
              left join entity_leaderboard l
                on l.subreddit = al.subreddit and l.entity_key = al.resolved_key
              where al.subreddit = %(sub)s and al.entity_key = m.entity_key
              limit 1
            ) r on true
            where {mine}
              and m.prompt_hash = %(hash)s
              and {in_city}
            order by m.id
        """, args)
        state = fetch_one(conn, f"""
            select case when batch_id is null then extracted_at end as extracted_at,
                   extract_error is not null as failed,
                   coalesce(prompt_hash = %(hash)s, false) as this_prompt,
                   batch_id is not null as pending
            from extraction_state
            where item_id = %(id)s and version = 'v6'
              and {in_city}
        """, args)
    except RATING_MISSING:
        # Dropped since the check: roll back so the connection stays usable.
        conn.rollback()
        forget_v6_ready()
        return None
    return rows, state


# --- Search ------------------------------------------------------------------
#
# What app/search.py reads. A search has three kinds of statement: the
# vocabulary (what words the board can explain without a model), the
# retrieval (nearest comments to the query, or the board when there is no
# text to embed), and the two tables search writes to, neither of which is
# evidence: search_parses caches what a model made of a query, search_log
# says what was asked.

# The embedding model's key, as a literal in the statement and not a bound
# value: comment_embeddings' vector index is partial on exactly this literal,
# and the planner only proves a partial index applies from a constant
# (SPEC.md, "Embeddings"). It is a module constant, never caller input.
SEARCH_MODEL = embedding.MODEL_KEY
assert "'" not in SEARCH_MODEL and "%" not in SEARCH_MODEL, SEARCH_MODEL

# A comment that knocks a place does not count toward it in a search: "skip
# X, it is overrated" is near "best X" in meaning and must not rank X.
# is_negated and avoid say "do not go"; a stated opinion below zero says the
# commenter went and did not like it.
SEARCH_KNOCK = ("(w.is_negated or coalesce(m.avoid, false)"
                " or (m.opinion = 'stated' and coalesce(m.overall_level, 0) < 0))")


def vocab_places(conn, sub, fetch_all):
    """Every place on the city's board with what search filters on, and the
    typed spellings that resolve to it."""
    return fetch_all(conn, """
        select l.entity_key, l.official_name, l.cuisine, l.boroughs,
               coalesce(l.distinct_authors, 0) as people,
               coalesce(l.is_chain, false) as is_chain, coalesce(l.closed, false) as closed,
               coalesce(array_agg(a.entity_key) filter (where a.entity_key <> l.entity_key),
                        '{}') as aliases
        from entity_leaderboard l
        left join entity_alias a on a.subreddit = l.subreddit and a.resolved_key = l.entity_key
        where l.subreddit = %s
        group by l.entity_key, l.official_name, l.cuisine, l.boroughs,
                 l.distinct_authors, l.is_chain, l.closed
    """, (sub,))


def vocab_terms(conn, sub, min_n, fetch_all):
    """The dishes and descriptors commenters used at least `min_n` times, in
    lower case: (kind, term, n) with kind 'dish' or 'tag'. Two scans of the
    city's mentions, so the caller keeps the result (search.vocabulary)."""
    return fetch_all(conn, """
        select 'dish' as kind, lower(v) as term, count(*) as n
        from mention_weights w
        join mentions m on m.id = w.mention_id
        cross join lateral jsonb_array_elements_text(m.dishes) v
        where w.subreddit = %(sub)s and jsonb_typeof(m.dishes) = 'array' and v is not null
        group by 2 having count(*) >= %(min_n)s
        union all
        select 'tag', lower(v), count(*)
        from mention_weights w
        join mentions m on m.id = w.mention_id
        cross join lateral jsonb_array_elements_text(m.descriptors) v
        where w.subreddit = %(sub)s and jsonb_typeof(m.descriptors) = 'array' and v is not null
        group by 2 having count(*) >= %(min_n)s
    """, {"sub": sub, "min_n": min_n})


def vocab_areas(conn, sub, fetch_all):
    """(entity_key, term, n): how many of a place's mentions put it in each
    neighbourhood, in the commenters' own words, lower case."""
    return fetch_all(conn, """
        select w.entity_key, lower(m.neighborhood_hint) as term, count(*) as n
        from mention_weights w
        join mentions m on m.id = w.mention_id
        where w.subreddit = %s and m.neighborhood_hint is not null
        group by 1, 2
    """, (sub,))


def vocab_cuisine_tags(conn, sub, terms, min_n, fetch_all):
    """(entity_key, term, n): how many different people tagged each place
    with one of the cuisine words `terms`, where at least `min_n` did. The
    city's own cuisine label is missing for three places in four, so the
    tags fill it in. People, not mentions, so `n` compares with the place's
    distinct_authors."""
    if not terms:
        return []
    return fetch_all(conn, """
        select w.entity_key, lower(v) as term,
               count(distinct coalesce(nullif(w.author, '[deleted]'), w.comment_id)) as n
        from mention_weights w
        join mentions m on m.id = w.mention_id
        cross join lateral jsonb_array_elements_text(m.descriptors) v
        where w.subreddit = %s and jsonb_typeof(m.descriptors) = 'array'
          and lower(v) = any(%s)
        group by 1, 2
        having count(distinct coalesce(nullif(w.author, '[deleted]'), w.comment_id)) >= %s
    """, (sub, list(terms), min_n))


def _search_place_filters(include, exclude, show_chains, params):
    """The SQL that keeps a place `l` in a search, for both retrievals.

    `include` is a list of key lists, one per kind of filter (every kind must
    hold, so each is its own ANY); `exclude` is one list. Closed places never
    show; chains only when the search names a place."""
    where = ["not coalesce(l.closed, false)",
             "not exists (select 1 from excluded_entities x"
             " where x.subreddit = l.subreddit and x.entity_key = l.entity_key)"]
    if not show_chains:
        where.append("not coalesce(l.is_chain, false)")
    for i, keys in enumerate(include):
        params[f"inc{i}"] = list(keys)
        where.append(f"l.entity_key = any(%(inc{i})s)")
    if exclude:
        params["exc"] = list(exclude)
        where.append("not (l.entity_key = any(%(exc)s))")
    return " and ".join(where)


def semantic_matches(conn, sub, vec, k, min_similarity, include, exclude, show_chains, fetch_all):
    """The mentions in the `k` comments nearest the query vector `vec` (a
    pgvector literal): (entity_key, mention_id, comment_id, person,
    similarity), after the cutoff, the knocks and the place filters.

    Must run inside db.transaction: the SET LOCAL only lasts that long. It
    lets the index keep scanning when the filters below drop most of what it
    found first (SPEC.md, "Embeddings"); without the index it does nothing.

    The nearest comments are taken before any filter, so a narrow filter can
    leave few of the `k`: the caller says so rather than pretending the count
    is of every comment. A person is the author, or the comment itself when
    the account is gone, so two deleted accounts are not one voice.
    """
    params = {"sub": sub, "vec": vec, "k": k, "min": min_similarity}
    places = _search_place_filters(include, exclude, show_chains, params)
    with conn.cursor() as cur:
        cur.execute("set local hnsw.iterative_scan = relaxed_order")
    return fetch_all(conn, f"""
        with near as materialized (
            select e.comment_id, e.embedding <=> %(vec)s::halfvec({embedding.DIMS}) as distance
            from comment_embeddings e
            where e.model = '{SEARCH_MODEL}'
            order by 2
            limit %(k)s
        )
        select w.entity_key, w.mention_id, w.comment_id,
               coalesce(nullif(w.author, '[deleted]'), w.comment_id) as person,
               1 - n.distance as similarity
        from near n
        join mentions m on m.comment_id = n.comment_id
        join mention_weights w on w.mention_id = m.id
        join entity_leaderboard l on l.subreddit = w.subreddit and l.entity_key = w.entity_key
        where w.subreddit = %(sub)s
          and 1 - n.distance >= %(min)s
          and not {SEARCH_KNOCK}
          and {places}
    """, params)


def text_matches(conn, sub, words, include, exclude, show_chains, limit, fetch_all):
    """A search whose text cannot be matched by meaning (a city without
    vectors, a provider or an index that did not answer): the places whose
    comments use every one of `words`, by how many different people did.

    A word matches a mention the way the ledger's topic does (TOPIC_TEXT_MATCH):
    in the thread's title or among the commenter's dishes or descriptors.
    Knocks are left out and a person is counted as in semantic_matches.
    Returns (entity_key, people, mention_ids, total): one mention per comment
    counted, most upvoted first, so the count can be opened in full, and the
    number of places before `limit` on every row. No index serves this; it is
    one scan of the city's mentions, as a topic is.
    """
    params = {"sub": sub, "limit": limit}
    places = _search_place_filters(include, exclude, show_chains, params)
    each = []
    for i, word in enumerate(words):
        params[f"w{i}"] = like_pattern(word)
        each.append(TOPIC_TEXT_MATCH.replace("%(topic)s", f"%(w{i})s"))
    return fetch_all(conn, f"""
        with hits as (
            select distinct on (w.entity_key, w.comment_id)
                   w.entity_key, w.mention_id,
                   coalesce(nullif(w.author, '[deleted]'), w.comment_id) as person,
                   c.score, c.created_utc
            from mention_weights w
            join mentions m on m.id = w.mention_id
            join comments c on c.id = w.comment_id
            join threads t on t.id = w.thread_id
            join entity_leaderboard l on l.subreddit = w.subreddit and l.entity_key = w.entity_key
            where w.subreddit = %(sub)s
              and {" and ".join(each)}
              and not {SEARCH_KNOCK}
              and {places}
            order by w.entity_key, w.comment_id, w.mention_id
        )
        select entity_key, count(distinct person)::int as people,
               array_agg(mention_id order by score desc nulls last, created_utc desc,
                                             mention_id) as mention_ids,
               (count(*) over ())::int as total
        from hits
        group by entity_key
        order by 2 desc, entity_key
        limit %(limit)s
    """, params)


def search_board(conn, sub, include, exclude, show_chains, limit, fetch_all, fetch_value):
    """A search with nothing to embed ("italian in brooklyn"): the filtered
    board by how many people brought each place up. Returns (rows, total)."""
    params = {"sub": sub, "limit": limit}
    places = _search_place_filters(include, exclude, show_chains, params)
    total = fetch_value(conn, f"""
        select count(*) from entity_leaderboard l
        where l.subreddit = %(sub)s and {places}
    """, params, default=0)
    rows = fetch_all(conn, f"""
        select l.entity_key, coalesce(l.distinct_authors, 0) as people
        from entity_leaderboard l
        where l.subreddit = %(sub)s and {places}
        order by l.distinct_authors desc nulls last, l.entity_key
        limit %(limit)s
    """, params)
    return rows, total


def search_places(conn, sub, keys, fetch_all):
    """What a result row shows about each place."""
    if not keys:
        return []
    return fetch_all(conn, """
        select l.entity_key, l.official_name, l.cuisine, l.boroughs[1] as borough,
               coalesce(l.distinct_authors, 0) as total_people
        from entity_leaderboard l
        where l.subreddit = %s and l.entity_key = any(%s)
    """, (sub, list(keys)))


def search_evidence(conn, sub, mention_ids, fetch_all):
    """The comments behind a result, in models.Mention's shape, with the
    resolved place each belongs to."""
    if not mention_ids:
        return []
    return fetch_all(conn, f"""
        select w.entity_key, {MENTION_COLUMNS}
        from mention_weights w
        join mentions m on m.id = w.mention_id
        join comments c on c.id = m.comment_id
        join threads t on t.id = c.thread_id
        where w.subreddit = %s and w.mention_id = any(%s)
    """, (sub, list(mention_ids)))


def board_evidence(conn, sub, keys, per_place, fetch_all):
    """The `per_place` most upvoted comments that do not knock each place,
    for a search that ranked by the board and so has no nearest comments."""
    if not keys:
        return []
    return fetch_all(conn, f"""
        select * from (
            select w.entity_key, {MENTION_COLUMNS},
                   row_number() over (partition by w.entity_key
                                      order by c.score desc nulls last, c.created_utc desc,
                                               m.id) as rn
            from mention_weights w
            join mentions m on m.id = w.mention_id
            join comments c on c.id = m.comment_id
            join threads t on t.id = c.thread_id
            where w.subreddit = %s and w.entity_key = any(%s)
              and not {SEARCH_KNOCK}
        ) x where rn <= %s
    """, (sub, list(keys), per_place))


def search_parse_get(conn, sub, query, model, prompt_hash, fetch_value):
    """What the model made of this query before, or None. Keyed on the model
    and the prompt, so changing either asks again instead of serving an
    answer to a different question."""
    return fetch_value(conn, """
        select parse from search_parses
        where subreddit = %s and query = %s and model = %s and prompt_hash = %s
    """, (sub, query, model, prompt_hash))


def search_parse_put(conn, sub, query, model, prompt_hash, parse):
    with conn.cursor() as cur:
        cur.execute("""
            insert into search_parses (subreddit, query, model, prompt_hash, parse)
            values (%s, %s, %s, %s, %s)
            on conflict (subreddit, query, model, prompt_hash) do nothing
        """, (sub, query, model, prompt_hash, Json(parse)))


def search_log_put(conn, sub, query, mode, source, parse, results, ms):
    with conn.cursor() as cur:
        cur.execute("""
            insert into search_log (subreddit, query, mode, source, parse, results, ms)
            values (%s, %s, %s, %s, %s, %s, %s)
        """, (sub, query, mode, source, Json(parse), results, ms))
