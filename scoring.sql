-- ===========================================================================
-- NYCEats scoring.
--
-- Everything is computed at query time from `mentions` + the raw corpus.
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
  3             as min_mentions;         -- TUNE  leaderboard floor


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
    m.entity_key,
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

  from mentions m
  join comments c on c.id = m.comment_id
  join threads  t on t.id = c.thread_id
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
       (select count(*) from comments c
         where c.created_utc > now() - make_interval(days => w.window_days))
         as recent_comments,
       (select count(*) from comments c cross join scoring_params p
         where c.created_utc > now() - make_interval(days => p.baseline_days))
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
-- ---------------------------------------------------------------------------
create or replace view entity_longevity as
with active_months as (
  select m.entity_key,
         extract(year from c.created_utc)::int * 12
           + extract(month from c.created_utc)::int as month_idx
  from mentions m
  join comments c on c.id = m.comment_id
  group by 1, 2
),
gaps as (
  select entity_key,
         month_idx - lag(month_idx) over (partition by entity_key
                                          order by month_idx) as step
  from active_months
),
totals as (
  select m.entity_key,
         min(c.created_utc) as first_seen,
         max(c.created_utc) as last_seen,
         count(*)           as total_mentions
  from mentions m
  join comments c on c.id = m.comment_id
  group by 1
)
select t.entity_key,
       t.first_seen,
       t.last_seen,
       t.total_mentions,
       (select count(*) from active_months a where a.entity_key = t.entity_key)
         as months_active,
       -- step counts consecutive months as 1, so silence = step - 1.
       coalesce((select max(g.step) - 1 from gaps g
                  where g.entity_key = t.entity_key and g.step is not null), 0)
         as longest_gap_months
from totals t;


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
select m.entity_key,
       count(distinct c.author) filter (where c.author is not null
                                          and c.author <> '[deleted]')
         as distinct_authors,
       count(*) filter (where m.is_firsthand) as firsthand_mentions,
       count(*) filter (where m.is_negated)   as negated_mentions
from mentions m
join comments c on c.id = m.comment_id
group by m.entity_key;


-- ---------------------------------------------------------------------------
-- 7. Leaderboard.
--
--    Rank by whichever column the caller wants; there is deliberately no single
--    composite score. Aspect columns are NULL when the aspect was never
--    observed -- absent and neutral (0.0) are different answers.
-- ---------------------------------------------------------------------------
create or replace view entity_leaderboard as
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
       max(a.aspect_score) filter (where a.aspect = 'food')       as food,
       max(a.aspect_score) filter (where a.aspect = 'value')      as value,
       max(a.aspect_score) filter (where a.aspect = 'service')    as service,
       max(a.aspect_score) filter (where a.aspect = 'atmosphere') as atmosphere,
       max(a.aspect_score) filter (where a.aspect = 'wait')       as wait
from entity_volume v
left join entity_confidence cf on cf.entity_key = v.entity_key
left join entity_momentum  mo on mo.entity_key = v.entity_key
left join entity_longevity lg on lg.entity_key = v.entity_key
left join aspect_scores     a on  a.entity_key = v.entity_key
group by v.entity_key, v.raw_mentions, v.decayed_volume, v.volume_share,
         cf.distinct_authors, cf.firsthand_mentions, cf.negated_mentions,
         mo.momentum_sigma, mo.momentum_window_days, mo.momentum_fired,
         lg.first_seen, lg.last_seen, lg.months_active, lg.longest_gap_months;


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
