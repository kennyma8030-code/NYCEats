-- ===========================================================================
-- NYCEats scoring.
--
-- Everything is computed at query time from `mentions` + the raw corpus.
-- Mentions are read through `live_mentions` (extract_v6_schema.sql), which
-- holds the one extraction the board counts: the old prompts' rows or v6's,
-- per extraction_settings. Both live in mentions side by side.
-- There is no stored score, no decay job, no window maintenance: a score is a
-- cache, and this file is how the cache is rebuilt.
--
-- Layout:
--   scoring_params        tunable constants, in one place
--   mention_weights       per-mention volume + sentiment weights
--   entity_volume         decayed, share-normalised attention
--   momentum_windows      subreddit activity per momentum window
--   entity_momentum_all   momentum in sigma, one row per (entity, window)
--   entity_momentum       the shortest window that actually fires
--   entity_longevity      undecayed presence (no weights at all)
--   aspect_scores         per (entity, aspect), shrunk toward the city mean
--   entity_confidence     distinct authors
--   entity_leaderboard    one row per entity, every axis above
--   rating_params         the rating's window, floors and badge percentiles
--   rating_mentions       what each in-window mention says, after the exclusions
--   place_voices          each person's latest stated opinion per place (rating)
--   place_recommenders    each person's latest stated-or-endorse word (volume)
--   place_category_voices each person's latest stated level per place and category
--   entity_rating         % positive, Wilson bound, recommenders, badge
--   entity_category_rating the same rating per category
--   <final select>        the leaderboard, incl. the chain-filter hook
--
-- Every constant worth arguing about is marked -- TUNE.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 0. Tunables. One view so a change lands in one place instead of six.
-- ---------------------------------------------------------------------------
create or replace view scoring_params as
select
  180.0::float8 as half_life_days,       -- TUNE  volume + aspect decay half-life
  365           as baseline_days,        -- TUNE  momentum baseline window
  1.0::float8   as momentum_pseudo,      -- TUNE  k in expected = share*N + k
  3.0::float8   as momentum_sigma,       -- TUNE  display threshold, in sigma
  3.0::float8   as aspect_pseudo,        -- TUNE  shrinkage toward the city mean
  3             as min_mentions,          -- TUNE  leaderboard floor
  -- Off. A hand review of the 2,547 names with 5+ mentions found about 1 in 6
  -- fuzzy merges wrong ("emp" -> EMPIRE, "angel" -> BLUE ANGEL), and no
  -- threshold separates them. Every merge worth having is now an
  -- alias_overrides row; word_similarity tops out at 1.0, so this never fires.
  1.01::float8  as alias_min_score,       -- TUNE  word_similarity to merge
  -- Not a tunable: the one city this board ranks. Other cities share the
  -- comments table (subreddits.py), and every read of "the subreddit" below
  -- filters on this first. Must match subreddits.HOME, which this file
  -- cannot import. Last on purpose -- create or replace view may only add
  -- columns at the end.
  'FoodNYC'::text as subreddit;


-- ---------------------------------------------------------------------------
-- 0.5 Identity. Which typed names are the same restaurant.
--
--    Without this the board ranks SPELLINGS: "katz", "katzs" and "katzs deli"
--    are three rows sharing one delicatessen, and "los tacos" splits ten ways.
--    481 of 5,637 rows duplicate another row.
--
--    Materialised on purpose. This is the one place identity is DECIDED, so it
--    has to be something you can read, sort and correct -- delete the row that
--    merges "otto" into ZERO OTTO NOVE and it stays split. A lateral
--    word_similarity recomputed inside every query is none of those things.
--
--    resolved_key is a name_key, the same shape as entity_key, so downstream
--    joins against restaurants(name_key) keep working untouched. A name that
--    matches nothing resolves to itself: this only ever merges, never drops.
--      refresh materialized view entity_alias;
-- ---------------------------------------------------------------------------
do $$
begin
  if exists (select 1 from pg_matviews where matviewname = 'entity_alias') then
    drop materialized view entity_alias cascade;
  elsif exists (select 1 from pg_views where viewname = 'entity_alias') then
    drop view entity_alias cascade;
  end if;
end $$;
create materialized view entity_alias as
with keys as (select distinct entity_key from live_mentions),
matched as (
  select k.entity_key,
         x.name_key  as exact_key,
         fz.name_key as fuzzy_key,
         fz.score    as fuzzy_score
  from keys k
  left join restaurants x on x.name_key = k.entity_key
  left join lateral (
    -- word_similarity, not similarity: people shorten names, and plain trigram
    -- punishes the length difference. "katz" scores 0.20 against "katzs
    -- delicatessen" and 0.80 under word_similarity.
    select r.name_key, word_similarity(k.entity_key, r.name_key) as score
    from restaurants r
    where k.entity_key <% r.name_key
    -- Shortest wins ties: food halls are licensed under one combined name that
    -- contains -- and so perfectly matches -- every tenant inside it.
    order by score desc, length(r.name_key) asc
    limit 1
  ) fz on x.name_key is null
)
select
  m.entity_key,
  -- The override wins outright. It is the only judgement here a person made.
  coalesce(o.resolved_key,
           m.exact_key,
           case when m.fuzzy_score >= p.alias_min_score then m.fuzzy_key end,
           m.entity_key)                   as resolved_key,
  case when o.resolved_key is not null          then 'manual'
       when m.exact_key is not null             then 'exact'
       when m.fuzzy_score >= p.alias_min_score  then 'fuzzy'
       else                                          'self' end as method,
  round(m.fuzzy_score::numeric, 2)         as score
from matched m
cross join scoring_params p
left join alias_overrides o on o.entity_key = m.entity_key;

create unique index if not exists entity_alias_pk on entity_alias(entity_key);
create index if not exists entity_alias_resolved_idx on entity_alias(resolved_key);


-- ---------------------------------------------------------------------------
-- 1. Per-mention weights.
--
--    volume    = correlation_discount * author_cap
--    sentiment = chain_discount * upvote_factor
-- ---------------------------------------------------------------------------
-- Materialised: every downstream view reads it, and entity_momentum reads it
-- once per window. Recomputing the window functions and the prompted-check
-- four times over made the leaderboard take minutes.
--   refresh materialized view concurrently mention_weights;
-- Neither DROP form no-ops against the other kind -- each errors outright,
-- which aborts the whole script under ON_ERROR_STOP. So drop whichever is
-- actually there.
do $$
begin
  if exists (select 1 from pg_matviews where matviewname = 'mention_weights') then
    drop materialized view mention_weights cascade;
  elsif exists (select 1 from pg_views where viewname = 'mention_weights') then
    drop view mention_weights cascade;
  end if;
end $$;
create materialized view mention_weights as
with base as (
  select
    m.id            as mention_id,
    m.comment_id,
    -- The resolved key IS entity_key from here down, so every window
    -- function, group by and downstream view merges with no further
    -- edit. in_chain and author_nth especially must see "katz" and
    -- "katzs" as one restaurant or their discounts miss.
    coalesce(a.resolved_key, m.entity_key) as entity_key,
    m.entity_key    as typed_key,
    m.aspects,
    m.is_negated,
    m.is_firsthand,
    c.thread_id,
    c.created_utc,
    c.author,
    c.score,
    c.score_settled,

    -- A top-level comment starts its own chain; fill_tree leaves root_comment_id
    -- null until a late parent lands, and null must not merge every orphan in the
    -- subreddit into one giant pseudo-chain.
    coalesce(c.root_comment_id, c.id) as chain_id,

    -- Did the thread itself name the place? Both sides are flattened to
    -- lowercase alphanumerics because entity_key is normalized and the title is
    -- not -- and because entity_key is data, so it must never reach a regex.
    strpos(
      ' ' || regexp_replace(lower(t.title || ' ' || coalesce(t.selftext, '')),
                            '[^a-z0-9]+', ' ', 'g') || ' ',
      ' ' || m.entity_key || ' '
    ) > 0 as prompted

  from live_mentions m
  join comments c on c.id = m.comment_id
  join threads  t on t.id = c.thread_id
  left join entity_alias a on a.entity_key = m.entity_key
  -- Extraction only reads HOME, so today this removes nothing. It is here so
  -- that extracting a second city cannot quietly fold it into this board.
  where c.subreddit = (select subreddit from scoring_params)
),
counted as (
  select
    b.*,
    count(*) over (partition by b.entity_key, b.chain_id)  as in_chain,
    count(*) over (partition by b.entity_key, b.thread_id) as in_thread,
    -- '[deleted]' is a tombstone shared by ~9,700 comments, not a person.
    -- Partitioning on it literally would zero the weight of all but two
    -- deleted mentions across the whole corpus, so each gets its own bucket.
    row_number() over (partition by b.entity_key,
                                    coalesce(nullif(b.author, '[deleted]'), b.comment_id)
                       order by b.created_utc, b.mention_id) as author_nth
  from base b
)
select
  mention_id,
  comment_id,
  entity_key,
  typed_key,
  thread_id,
  chain_id,
  author,
  created_utc,
  score,
  score_settled,
  aspects,
  is_negated,
  is_firsthand,
  prompted,
  in_chain,
  in_thread,
  author_nth,

  -- VOLUME -----------------------------------------------------------------
  -- Prompted mentions collapse across the whole thread: 16 mentions of a place
  -- in a thread *about* that place is one attention event, however many chains
  -- it spread over. Volunteered mentions collapse only within their own chain:
  -- 16 top-level mentions in a thread about something else is 16 events.
  (case when prompted then 1.0 / sqrt(in_thread)
        else               1.0 / sqrt(in_chain) end)
  -- One person repeating themselves is not more evidence.
  * (case when author_nth = 1 then 1.0        -- TUNE author cap ladder
          when author_nth = 2 then 0.5
          else                    0.0 end)
  as w_volume,
  -- A negated mention ("do not go to X") still spends the subreddit's attention,
  -- so it keeps its volume weight; only its sentiment flips. See aspect_scores.

  -- SENTIMENT --------------------------------------------------------------
  -- Deliberately NOT discounted for being prompted: a thread asking about one
  -- place still collects real, independent opinions about it.
  (1.0 / sqrt(in_chain))
  -- greatest(score, 1), not greatest(score, 0): score 1 means nobody voted,
  -- which is most of the corpus, and must weigh exactly 1.0 -- ln(1) = 0.
  -- Unsettled comments have not been re-fetched at 36h yet, so their score is
  -- still the posting default and carries no information.
  * (case when score_settled then 1.0 + ln(greatest(score, 1)::float8)
          else                    1.0 end)
  as w_sentiment

from counted;

create unique index if not exists mention_weights_pk  on mention_weights(mention_id);
create index if not exists mention_weights_entity_idx on mention_weights(entity_key);
create index if not exists mention_weights_time_idx   on mention_weights(created_utc);


-- ---------------------------------------------------------------------------
-- 2. Volume: decayed, then divided by the subreddit's own decayed activity.
--
--    r/FoodNYC went from 4,828 comments in 2019 to 222,590 in 2025. Undivided,
--    every restaurant on earth "is rising". The denominator carries the same
--    decay as the numerator so the ratio is a share of attention, not a mix of
--    two different time windows.
-- ---------------------------------------------------------------------------
create or replace view entity_volume as
with decayed_corpus as (
  select sum(power(2.0,
               -extract(epoch from (now() - c.created_utc)) / 86400.0 / p.half_life_days))
         as total
  from comments c cross join scoring_params p
  where c.subreddit = p.subreddit
),
per_entity as (
  select w.entity_key,
         sum(w.w_volume
             * power(2.0,
                 -extract(epoch from (now() - w.created_utc)) / 86400.0 / p.half_life_days))
         as decayed_volume,
         count(*) as raw_mentions
  from mention_weights w cross join scoring_params p
  group by w.entity_key
)
select e.entity_key,
       e.decayed_volume,
       e.raw_mentions,
       -- share of all decayed subreddit attention; tiny by construction
       e.decayed_volume / nullif(d.total, 0) as volume_share
from per_entity e cross join decayed_corpus d;


-- ---------------------------------------------------------------------------
-- 3. Momentum, in standard deviations.
--
--    expected = baseline_share * recent_total_comments + k
--    momentum = (recent - expected) / sqrt(expected)
--
--    k = 1.0 is a pseudo-count, and it is REQUIRED: without it a restaurant with
--    a zero baseline divides by zero instead of being scorable. Measured at
--    k = 1.0:  0->2 = 1.0 (quiet)   0->3 = 2.0 (quiet)   0->5 = 4.0 (fires)
--              0->20 = 19.0         200->220 = 1.3 (quiet)  200->260 = 4.2 (fires)
--
--    Four windows, each against the same 365d baseline. A busy restaurant clears
--    3 sigma on 14 days; a quiet one needs 180 and gets a slower, honest answer.
--    The baseline window contains the recent window, which drags the estimate
--    toward "no change" -- conservative in the direction we want.
-- ---------------------------------------------------------------------------
-- Materialised: four rows, but each is a count over 750k comments, and
-- entity_momentum_all cross-joins this -- so as a plain view the corpus counts
-- were being re-evaluated per entity. That alone took the leaderboard from
-- seconds to minutes.
--   refresh materialized view momentum_windows;
do $$
begin
  if exists (select 1 from pg_matviews where matviewname = 'momentum_windows') then
    drop materialized view momentum_windows cascade;
  elsif exists (select 1 from pg_views where viewname = 'momentum_windows') then
    drop view momentum_windows cascade;
  end if;
end $$;
create materialized view momentum_windows as
select w.window_days,
       (select count(*) from comments c cross join scoring_params p
         where c.subreddit = p.subreddit
           and c.created_utc > now() - make_interval(days => w.window_days))
         as recent_comments,
       (select count(*) from comments c cross join scoring_params p
         where c.subreddit = p.subreddit
           and c.created_utc > now() - make_interval(days => p.baseline_days))
         as baseline_comments
from (values (14), (30), (90), (180)) as w(window_days);   -- TUNE window ladder


create or replace view entity_momentum_all as
with baseline as (
  select w.entity_key,
         sum(w.w_volume) as baseline_volume
  from mention_weights w cross join scoring_params p
  where w.created_utc > now() - make_interval(days => p.baseline_days)
  group by w.entity_key
),
recent as (
  select w.entity_key,
         mw.window_days,
         sum(w.w_volume) filter (
           where w.created_utc > now() - make_interval(days => mw.window_days)
         ) as recent_volume
  from mention_weights w
  cross join momentum_windows mw
  group by w.entity_key, mw.window_days
)
select r.entity_key,
       r.window_days,
       coalesce(r.recent_volume, 0)   as recent_volume,
       coalesce(b.baseline_volume, 0) as baseline_volume,
       mw.recent_comments,
       -- baseline rate, re-expressed at the recent window's subreddit activity
       (coalesce(b.baseline_volume, 0) / nullif(mw.baseline_comments, 0))
         * mw.recent_comments + p.momentum_pseudo as expected,
       (coalesce(r.recent_volume, 0)
        - ((coalesce(b.baseline_volume, 0) / nullif(mw.baseline_comments, 0))
           * mw.recent_comments + p.momentum_pseudo))
       / sqrt((coalesce(b.baseline_volume, 0) / nullif(mw.baseline_comments, 0))
              * mw.recent_comments + p.momentum_pseudo) as sigma
from recent r
join momentum_windows mw on mw.window_days = r.window_days
left join baseline b on b.entity_key = r.entity_key
cross join scoring_params p
-- A window with no subreddit activity at all has nothing to say; saying nothing
-- beats fabricating a sigma out of an empty denominator.
where mw.recent_comments > 0;


-- The reported number: shortest window that clears the threshold. If nothing
-- clears, fall back to the widest window -- the most data, the least noise --
-- and let momentum_fired say it did not fire.
create or replace view entity_momentum as
select distinct on (entity_key)
       entity_key,
       window_days as momentum_window_days,
       sigma       as momentum_sigma,
       recent_volume,
       expected,
       sigma >= (select momentum_sigma from scoring_params) as momentum_fired
from entity_momentum_all
order by entity_key,
         (sigma >= (select momentum_sigma from scoring_params)) desc,
         case when sigma >= (select momentum_sigma from scoring_params)
              then window_days else -window_days end;


-- ---------------------------------------------------------------------------
-- 4. Longevity. Undecayed and weight-free on purpose: this axis asks whether a
--    place has been *present* for years, not how loudly it was discussed.
--
--    Months and gaps are grouped once and joined, not looked up per entity.
--    The correlated subqueries this used to run rescanned every entity's
--    months for each of ~28k entities, which made building entity_leaderboard
--    take two minutes on production; grouped, it is seconds, same rows.
-- ---------------------------------------------------------------------------
create or replace view entity_longevity as
with active_months as (
  select coalesce(a.resolved_key, m.entity_key) as entity_key,
         extract(year from c.created_utc)::int * 12
           + extract(month from c.created_utc)::int as month_idx
  from live_mentions m
  join comments c on c.id = m.comment_id
  left join entity_alias a on a.entity_key = m.entity_key
  group by 1, 2
),
gaps as (
  select entity_key,
         month_idx - lag(month_idx) over (partition by entity_key
                                          order by month_idx) as step
  from active_months
),
months as (
  -- One row per active month, so count(*) is months active. step counts
  -- consecutive months as 1, so silence = step - 1; max() skips the first
  -- month's null step, and an entity seen in one month has no gap at all.
  select entity_key,
         count(*)          as months_active,
         max(step) - 1     as longest_gap
  from gaps
  group by entity_key
),
totals as (
  -- Resolved here too. active_months is keyed on the resolved name, so a
  -- totals row keyed on the typed one joins to nothing and every merged
  -- entity reports NULL months_active.
  select coalesce(a.resolved_key, m.entity_key) as entity_key,
         min(c.created_utc) as first_seen,
         max(c.created_utc) as last_seen,
         count(*)           as total_mentions
  from live_mentions m
  join comments c on c.id = m.comment_id
  left join entity_alias a on a.entity_key = m.entity_key
  group by 1
)
select t.entity_key,
       t.first_seen,
       t.last_seen,
       t.total_mentions,
       coalesce(mo.months_active, 0) as months_active,
       coalesce(mo.longest_gap, 0)   as longest_gap_months
from totals t
left join months mo on mo.entity_key = t.entity_key;


-- ---------------------------------------------------------------------------
-- 5. Aspect scores, per (entity_key, aspect).
--
--    jsonb_each + a numeric type check, not aspects->>'food': a missing aspect
--    and a JSON null must both stay ABSENT. Coercing them to 0 would make
--    "nobody mentioned the service" indistinguishable from "the service was
--    mixed", which is the one thing the spec says must never happen.
-- ---------------------------------------------------------------------------
create or replace view aspect_observations as
select w.entity_key,
       a.key as aspect,
       -- A negated mention is negative regardless of the sign the model wrote;
       -- -abs() is idempotent, so a model that already encoded the negation is
       -- not flipped back to positive.
       case when w.is_negated then -abs((a.value #>> '{}')::float8)
            else                    (a.value #>> '{}')::float8 end as val,
       w.w_sentiment
       * power(2.0,
           -extract(epoch from (now() - w.created_utc)) / 86400.0 / p.half_life_days)
       as w_decayed
from mention_weights w
cross join scoring_params p
cross join lateral jsonb_each(coalesce(w.aspects, '{}'::jsonb)) as a(key, value)
where a.key in ('food', 'value', 'service', 'atmosphere', 'wait')  -- TUNE aspect set
  and jsonb_typeof(a.value) = 'number';


create or replace view aspect_scores as
with per_entity as (
  select entity_key,
         aspect,
         sum(w_decayed * val) as s,
         sum(w_decayed)       as w,
         count(*)             as n_obs
  from aspect_observations
  group by 1, 2
),
city as (
  -- One prior per aspect: NYC rates food higher than it rates wait times.
  select aspect,
         sum(s) / nullif(sum(w), 0) as city_mean
  from per_entity
  group by 1
)
select e.entity_key,
       e.aspect,
       e.n_obs,
       e.w as aspect_weight,
       e.s / nullif(e.w, 0) as raw_mean,
       c.city_mean,
       -- Shrink toward the city mean with pseudo-count 3: two glowing comments
       -- should not outrank a place with thirty.
       (e.s + p.aspect_pseudo * c.city_mean) / (e.w + p.aspect_pseudo)
         as aspect_score
from per_entity e
join city c on c.aspect = e.aspect
cross join scoring_params p;


-- ---------------------------------------------------------------------------
-- 6. Confidence. Volume cannot tell one enthusiast from a consensus; this can,
--    so it is surfaced on the leaderboard rather than folded into a score.
-- ---------------------------------------------------------------------------
create or replace view entity_confidence as
select coalesce(a.resolved_key, m.entity_key) as entity_key,
       count(distinct c.author) filter (where c.author is not null
                                          and c.author <> '[deleted]')
         as distinct_authors,
       count(*) filter (where m.is_firsthand) as firsthand_mentions,
       count(*) filter (where m.is_negated)   as negated_mentions
from live_mentions m
join comments c on c.id = m.comment_id
left join entity_alias a on a.entity_key = m.entity_key
group by 1;


-- ---------------------------------------------------------------------------
-- 7. Leaderboard.
--
--    Rank by whichever column the caller wants; there is deliberately no single
--    composite score. Aspect columns are NULL when the aspect was never
--    observed -- absent and neutral (0.0) are different answers.
-- ---------------------------------------------------------------------------
--    Materialised, and this is the one that mattered most. As a plain view,
--    every request re-ran entity_volume -- whose decayed_corpus CTE is a
--    sum(power(2.0, ...)) across all 750k comments -- plus entity_longevity's
--    per-entity work, before a single filter was applied.
--
--    It cannot be response-cached instead: a leaderboard is (sort x filters),
--    and search x cuisine x borough x status x five aspect thresholds x
--    thirteen sorts has no meaningful hit rate. So the SUBSTRATE is cached --
--    one row per entity, a few thousand rows -- and any filter and sort over
--    it is then a scan of something tiny.
--      refresh materialized view concurrently entity_leaderboard;
do $$
begin
  if exists (select 1 from pg_matviews where matviewname = 'entity_leaderboard') then
    drop materialized view entity_leaderboard cascade;
  elsif exists (select 1 from pg_views where viewname = 'entity_leaderboard') then
    drop view entity_leaderboard cascade;
  end if;
end $$;
create materialized view entity_leaderboard as
with aspects as (
  -- Pivoted here rather than joined per request. max() over a filter is a
  -- pivot, not an aggregate over duplicates: aspect_scores holds at most one
  -- row per (entity, aspect).
  select entity_key,
         max(aspect_score) filter (where aspect = 'food')       as food,
         max(aspect_score) filter (where aspect = 'value')      as value,
         max(aspect_score) filter (where aspect = 'service')    as service,
         max(aspect_score) filter (where aspect = 'atmosphere') as atmosphere,
         max(aspect_score) filter (where aspect = 'wait')       as wait
  from aspect_scores
  group by entity_key
)
select v.entity_key,
       v.raw_mentions,
       v.decayed_volume,
       v.volume_share,
       cf.distinct_authors,
       cf.firsthand_mentions,
       cf.negated_mentions,
       mo.momentum_sigma,
       mo.momentum_window_days,
       mo.momentum_fired,
       lg.first_seen,
       lg.last_seen,
       lg.months_active,
       lg.longest_gap_months,
       a.food,
       a.value,
       a.service,
       a.atmosphere,
       a.wait,
       -- The official record, folded in so filtering by cuisine or borough is
       -- a column test rather than a join per request. NULL when the typed
       -- name never matched the city's list, which is not evidence the place
       -- is fake -- see resolve.sql.
       r.name           as official_name,
       r.cuisine,
       r.boroughs,
       r.is_chain,
       r.closed,
       r.location_count
from entity_volume v
left join entity_confidence cf on cf.entity_key = v.entity_key
left join entity_momentum  mo on mo.entity_key = v.entity_key
left join entity_longevity lg on lg.entity_key = v.entity_key
left join aspects           a on  a.entity_key = v.entity_key
left join restaurants       r on  r.name_key   = v.entity_key
-- Grocery stores, markets and pronouns the model extracted as places.
where not exists (select 1 from excluded_entities x
                  where x.entity_key = v.entity_key);

-- Unique index is not optional: REFRESH ... CONCURRENTLY requires one, and
-- without it the refresh takes an AccessExclusiveLock and the API blocks.
create unique index if not exists entity_leaderboard_pk
  on entity_leaderboard(entity_key);
create index if not exists entity_leaderboard_volume_idx
  on entity_leaderboard(decayed_volume desc nulls last);
create index if not exists entity_leaderboard_momentum_idx
  on entity_leaderboard(momentum_sigma desc nulls last);
create index if not exists entity_leaderboard_mentions_idx
  on entity_leaderboard(raw_mentions desc nulls last);


-- ---------------------------------------------------------------------------
-- 8. The rating: how much of the sub likes a place, kept apart from how many
--    people bring it up.
--
--    Read off v6's columns (opinion, overall_level, avoid, timeframe, trend,
--    status, the category levels), so it needs live_mentions in v6 mode;
--    under 'legacy' those are null and nothing is rankable.
--
--    The audit behind it: 44.5% of v6's positive mentions are bare
--    recommendations, a name dropped in answer to a question with no judgment
--    (opinion = 'endorse'). Counted as praise they put the median place at
--    90% positive and 361 places at 100%. Over stated opinions only the board
--    is about 74.5% positive. So a bare endorse is volume, never rating: it
--    counts toward recommenders and cannot touch the rating, not even by
--    being someone's latest word.
--
--    One voice per person per place, their latest in the window, so a regular
--    who posts about a place weekly is still one person. Two passes pick it,
--    because the two axes ask different things: the rating takes each
--    person's latest STATED opinion (place_voices), the volume each person's
--    latest stated-or-endorse word (place_recommenders). A rating is a share,
--    and a share needs a floor (min_rated) and a lower bound (Wilson) before
--    it can be ranked: 3 for 3 is not better than 290 of 300.
--
--    Badges are cut at percentiles of the rankable places rather than fixed
--    numbers, so they keep meaning "the busiest tenth" and "the better half"
--    as the corpus grows. There is no composite score: each board ranks by
--    one of these and filters on the rest (queries.RATING_BOARDS).
--
--    The web app reads these views but does not build them. Apply this file
--    (refresh.py --apply, or the poller's boot) before deploying a web app
--    that serves /api/boards; until then the app reports rating: null.
-- ---------------------------------------------------------------------------
create or replace view rating_params as
select
  365            as window_days,         -- TUNE  voices this recent count
  1.28::float8   as z,                   -- TUNE  Wilson z (one-sided ~90%)
  10             as min_rated,           -- TUNE  rankable: stated non-neutral people
  8              as min_category_rated,  -- TUNE  the same, per category
  0.10::float8   as busy_pct,            -- TUNE  busy = recommenders in this top share
  0.50::float8   as share_pct,           -- TUNE  share_line = this percentile of lb
  0.85::float8   as gem_pct;             -- TUNE  gem_line = this percentile of lb, non-busy


-- The lower bound of the Wilson score interval for pos successes in n. NULL
-- for n = 0: no opinion is not a 0% rating.
create or replace function wilson_lower(pos float8, n float8, z float8)
returns float8 language sql immutable as $$
  select case when n > 0 then
    (pos / n + z * z / (2 * n)
     - z * sqrt((pos / n) * (1 - pos / n) / n + z * z / (4 * n * n)))
    / (1 + z * z / n)
  end
$$;


-- Every mention the rating may count, with what it says, one row each.
-- Materialised and refreshed once, before the three views that read it, so
-- the year-long join behind it runs once per refresh rather than three times.
-- One place for the exclusions, so the rating, the volume and the categories
-- cannot drift apart:
--
--   * the window, and AutoModerator, who is not a person. '[deleted]' is a
--     shared tombstone, so each deleted comment is its own person, as in
--     mention_weights.
--   * status 'closed': "RIP Florent" is nostalgia for a shut place, and those
--     comments were ranking it.
--
-- voice, tested in this order:
--   neg       avoid ("skip it"), whatever else the mention says. First, so a
--             warning never counts as a recommendation. Its level is made
--             negative (-1 unless the model said -2): an avoid on an endorse
--             or a 'none' mention can carry a positive or no level, and a
--             neg must never show one.
--   endorse   a bare recommendation (opinion = 'endorse'), whatever level
--             the model attached to it. Volume only.
--   pos       stated, overall level 1 or 2
--   neg       stated, overall level -1 or -2
--   neutral   stated, overall level 0
--   NULL      anything else: a fact, a question, a remark about the wait
--             alone. Not a voice, so it never hides an earlier one that was.
--
-- timeframe 'past' mostly marks a verdict on how a place used to be: in a
-- read of 60 production mentions with a level, 52 were historical ("I used
-- to love it", "it was great back in the day") and 8 were the commenter's
-- view now. The prompt's rule 9 says levels are what the commenter thinks
-- now, and where the text says the place changed, trend says which way. So
-- a past mention's level counts only when it points the way the place moved:
-- `past_sign` is -1 for trend 'declined' ("it was better before, now it's
-- mid"), +1 for 'improved', 0 for a past mention with no trend (nothing it
-- says counts), and NULL for a mention that is not past. The overall voice
-- and every category level are kept only when sign * past_sign is 1, or
-- past_sign is NULL: the one rule, applied to each level in turn. An avoid
-- is a neg whatever its timeframe: "used to be my spot, skip it now" warns
-- readers off today. The 8 in 60 present-day views tagged past without a
-- trend are lost: a known limit, with the prompt (GitHub issue #3).
--   refresh materialized view concurrently rating_mentions;
do $$
begin
  if exists (select 1 from pg_matviews where matviewname = 'rating_mentions') then
    drop materialized view rating_mentions cascade;
  elsif exists (select 1 from pg_views where viewname = 'rating_mentions') then
    drop view rating_mentions cascade;
  end if;
end $$;
create materialized view rating_mentions as
select v.*,
       -- A voice, after the past test (see above). An endorse reads as +1.
       case when v.avoid then v.said
            when coalesce(v.past_sign * case v.said when 'neg'     then -1
                                                    when 'neutral' then  0
                                                    else                 1 end, 1) = 1
            then v.said end                                 as voice
from (
  select w.entity_key,
         coalesce(nullif(w.author, '[deleted]'), w.comment_id) as person,
         w.mention_id,
         w.comment_id,
         w.created_utc,
         m.opinion,
         coalesce(m.avoid, false)                             as avoid,
         case when m.timeframe is distinct from 'past' then null
              when m.trend = 'declined'                then -1
              when m.trend = 'improved'                then  1
              else                                            0 end as past_sign,
         case when m.avoid                                      then 'neg'
              when m.opinion = 'endorse'                        then 'endorse'
              when m.opinion = 'stated' and m.overall_level > 0 then 'pos'
              when m.opinion = 'stated' and m.overall_level < 0 then 'neg'
              when m.opinion = 'stated' and m.overall_level = 0 then 'neutral'
         end                                                  as said,
         case when m.avoid then least(coalesce(m.overall_level, -1), -1)
              else m.overall_level end                        as level,
         m.taste_level, m.value_level, m.service_level, m.atmosphere_level, m.wait_level
  from mention_weights w
  join mentions m on m.id = w.mention_id      -- a live id: see queries.py
  cross join rating_params p
  where w.created_utc > now() - make_interval(days => p.window_days)
    and w.author is distinct from 'AutoModerator'
    and m.status is distinct from 'closed'
    and not exists (select 1 from excluded_entities x where x.entity_key = w.entity_key)
) v;

create unique index if not exists rating_mentions_pk on rating_mentions(mention_id);
create index if not exists rating_mentions_person_idx
  on rating_mentions(entity_key, person, created_utc desc);


-- The rating's voices: one row per (place, person), their latest STATED
-- opinion (pos, neg, neutral). A bare endorse is not a candidate, so a
-- person who praised a place and later only named it still counts as
-- praise. mention_id is kept so every count clicks through to exactly the
-- comments it counted (/api/restaurants/{key}/voices).
--   refresh materialized view concurrently place_voices;
do $$
begin
  if exists (select 1 from pg_matviews where matviewname = 'place_voices') then
    drop materialized view place_voices cascade;
  end if;
end $$;
create materialized view place_voices as
select distinct on (entity_key, person)
       entity_key, person, mention_id, comment_id, created_utc, voice, level
from rating_mentions
where voice in ('pos', 'neg', 'neutral')
order by entity_key, person, created_utc desc, mention_id desc;

create unique index if not exists place_voices_pk on place_voices(entity_key, person);


-- The volume's voices: one row per (place, person), their latest word that
-- is any voice at all, stated or endorse. Two mentions of one place in the
-- same comment (two spellings that resolve together) share created_utc; the
-- stated one wins there, because it says more than the name-drop beside it.
--
-- recommends: the latest word is a stated pos, or a bare endorse from
-- someone whose latest stated opinion is not a knock. A detractor who later
-- only names the place has not changed their mind, so is not a recommender;
-- a latest word that is an avoid is a neg, so never is. The latest stated
-- opinion is read from place_voices, which refresh.VIEWS refreshes first.
--   refresh materialized view concurrently place_recommenders;
do $$
begin
  if exists (select 1 from pg_matviews where matviewname = 'place_recommenders') then
    drop materialized view place_recommenders cascade;
  end if;
end $$;
create materialized view place_recommenders as
with latest as (
  select distinct on (entity_key, person)
         entity_key, person, mention_id, comment_id, created_utc, voice, level
  from rating_mentions
  where voice is not null
  order by entity_key, person, created_utc desc, (voice = 'endorse'), mention_id desc
)
select l.entity_key, l.person, l.mention_id, l.comment_id, l.created_utc, l.voice, l.level,
       l.voice = 'pos'
         or (l.voice = 'endorse' and s.voice is distinct from 'neg') as recommends
from latest l
left join place_voices s on s.entity_key = l.entity_key and s.person = l.person;

create unique index if not exists place_recommenders_pk
  on place_recommenders(entity_key, person);


-- One row per (place, category, person): their latest STATED level for that
-- category, by sign. A level on a bare endorse ("go for the dumplings") is
-- the same name-drop the overall rating leaves out, so it is left out here.
-- A past mention counts only when this level points the way the trend says
-- the place moved (see rating_mentions). The categories are v6's: taste (the
-- food), value, service, atmosphere, wait. A high wait rating means people
-- found the wait fine or worth it.
--   refresh materialized view concurrently place_category_voices;
do $$
begin
  if exists (select 1 from pg_matviews where matviewname = 'place_category_voices') then
    drop materialized view place_category_voices cascade;
  end if;
end $$;
create materialized view place_category_voices as
-- Qualified throughout: rating_mentions has a `level` of its own (overall).
select distinct on (r.entity_key, x.category, r.person)
       r.entity_key, x.category, r.person, r.mention_id, r.comment_id, r.created_utc,
       x.level,
       case when x.level > 0 then 'pos' when x.level < 0 then 'neg' else 'neutral' end as voice
from rating_mentions r
cross join lateral (values ('taste',      r.taste_level),
                           ('value',      r.value_level),
                           ('service',    r.service_level),
                           ('atmosphere', r.atmosphere_level),
                           ('wait',       r.wait_level)) as x(category, level)
where r.opinion = 'stated'
  and x.level is not null
  and coalesce(r.past_sign * sign(x.level), 1) = 1   -- the past test (rating_mentions)
order by r.entity_key, x.category, r.person, r.created_utc desc, r.mention_id desc;

create unique index if not exists place_category_voices_pk
  on place_category_voices(entity_key, category, person);


-- One row per place with any voice in the window.
--
--   pos, neg, neutral, superlative    from place_voices (latest stated)
--   pct_pos       pos / (pos + neg)
--   lb            Wilson lower bound of pct_pos at rating_params.z
--   (neg_share, 1 - pct_pos, is worked out by the API, not stored)
--   superlative   people whose latest stated level was 2: called it the best
--   recommenders  place_recommenders.recommends: the volume axis. Not
--                 pos + endorse: someone who praised it and later only named
--                 it is one pos and one recommender.
--   endorse       the recommenders whose latest word is a bare endorse
--   rankable      pos + neg >= min_rated
--
-- last_voice is the latest word from the volume pass, which every voice is a
-- candidate for. Built from a full join of the two passes all the same: a
-- refresh that stops between them must not cost a rated place its row.
--
-- The lines are worked out over rankable places the boards can show (not on
-- the city's chain list, not closed), and every rankable place is then badged
-- against them, so a chain opened by name still says where it stands.
--   busy_line     recommenders at the top busy_pct; busy = at or above it
--   share_line    lb at share_pct (the median)
--   gem_line      lb at gem_pct among rankable places that are not busy
--   badge         consensus        busy, lb >= share_line
--                 overhyped_mixed  busy, lb <  share_line
--                 hidden_gem       not busy, lb >= gem_line
--                 NULL             otherwise, and for every unrankable place
-- The lines repeat on every row so a card can say what its badge was cut at.
--   refresh materialized view concurrently entity_rating;
do $$
begin
  if exists (select 1 from pg_matviews where matviewname = 'entity_rating') then
    drop materialized view entity_rating cascade;
  end if;
end $$;
create materialized view entity_rating as
with rated as (
  select entity_key,
         count(*) filter (where voice = 'pos')                as pos,
         count(*) filter (where voice = 'neg')                as neg,
         count(*) filter (where voice = 'neutral')            as neutral,
         count(*) filter (where voice = 'pos' and level = 2)  as superlative
  from place_voices
  group by entity_key
),
volume as (
  select entity_key,
         count(*) filter (where recommends and voice = 'endorse') as endorse,
         count(*) filter (where recommends)                   as recommenders,
         max(created_utc)                                     as last_word
  from place_recommenders
  group by entity_key
),
counts as (
  select coalesce(r.entity_key, v.entity_key)     as entity_key,
         coalesce(r.pos, 0)          as pos,
         coalesce(r.neg, 0)          as neg,
         coalesce(r.neutral, 0)      as neutral,
         coalesce(r.superlative, 0)  as superlative,
         coalesce(v.endorse, 0)      as endorse,
         coalesce(v.recommenders, 0) as recommenders,
         v.last_word                 as last_voice
  from rated r
  full join volume v on v.entity_key = r.entity_key
),
scored as (
  select c.*,
         c.pos::float8 / nullif(c.pos + c.neg, 0)             as pct_pos,
         wilson_lower(c.pos, c.pos + c.neg, p.z)              as lb,
         c.pos + c.neg >= p.min_rated                         as rankable,
         coalesce(r.is_chain, false) or coalesce(r.closed, false) as off_board
  from counts c
  cross join rating_params p
  left join restaurants r on r.name_key = c.entity_key
),
lines as (
  -- percentile_disc, so busy_line is a count some place really has.
  select percentile_disc(1 - (select busy_pct from rating_params))
           within group (order by recommenders)               as busy_line,
         percentile_cont((select share_pct from rating_params))
           within group (order by lb)                         as share_line
  from scored
  where rankable and not off_board
),
gem as (
  select percentile_cont((select gem_pct from rating_params))
           within group (order by s.lb)                       as gem_line
  from scored s cross join lines l
  where s.rankable and not s.off_board and s.recommenders < l.busy_line
)
select s.entity_key,
       s.pos, s.neg, s.neutral, s.endorse, s.superlative,
       s.recommenders, s.pct_pos, s.lb,
       s.rankable,
       -- coalesce: with no rankable place at all the lines are NULL.
       coalesce(s.rankable and s.recommenders >= l.busy_line, false) as busy,
       case when not s.rankable                                then null
            when s.recommenders >= l.busy_line
                 and s.lb >= l.share_line                      then 'consensus'
            when s.recommenders >= l.busy_line                 then 'overhyped_mixed'
            when s.lb >= g.gem_line                            then 'hidden_gem'
       end                                                    as badge,
       s.last_voice,
       l.busy_line, l.share_line, g.gem_line
from scored s
cross join lines l
cross join gem g;

create unique index if not exists entity_rating_pk on entity_rating(entity_key);
create index if not exists entity_rating_lb_idx on entity_rating(lb desc nulls last);
create index if not exists entity_rating_recommenders_idx
  on entity_rating(recommenders desc);


-- The same rating per (place, category), from place_category_voices. Ranked
-- only once min_category_rated people said something non-neutral about that
-- category: the categories are sparser than the overall verdict.
--   refresh materialized view concurrently entity_category_rating;
do $$
begin
  if exists (select 1 from pg_matviews where matviewname = 'entity_category_rating') then
    drop materialized view entity_category_rating cascade;
  end if;
end $$;
create materialized view entity_category_rating as
with counts as (
  select entity_key, category,
         count(*) filter (where voice = 'pos')     as pos,
         count(*) filter (where voice = 'neg')     as neg,
         count(*) filter (where voice = 'neutral') as neutral
  from place_category_voices
  group by entity_key, category
)
select c.entity_key, c.category, c.pos, c.neg, c.neutral,
       c.pos::float8 / nullif(c.pos + c.neg, 0)  as pct_pos,
       wilson_lower(c.pos, c.pos + c.neg, p.z)   as lb,
       c.pos + c.neg >= p.min_category_rated     as rankable
from counts c
cross join rating_params p;

create unique index if not exists entity_category_rating_pk
  on entity_category_rating(entity_key, category);
create index if not exists entity_category_rating_lb_idx
  on entity_category_rating(category, lb desc nulls last) where rankable;


-- ===========================================================================
-- The query the application actually runs.
--
-- >>> CHAIN FILTER <<<
-- chains.txt holds 79 normalized names (dunkin, starbucks, ...). SQL cannot read
-- a file, so the APPLICATION passes the list as a single array parameter:
--
--     cur.execute(open('scoring.sql').read().split('-- @@LEADERBOARD@@')[1],
--                 (chains,))          # chains = ['dunkin', 'starbucks', ...]
--
-- and the predicate below becomes:
--
--     where entity_key <> all(%s)
--
-- The array literal here is the standalone default so this file runs as-is.
-- @@LEADERBOARD@@
-- ===========================================================================
select *
from entity_leaderboard
where entity_key <> all(array[]::text[])        -- <-- application substitutes %s
  and raw_mentions >= (select min_mentions from scoring_params)
order by volume_share desc nulls last
limit 50;
