-- ===========================================================================
-- Scoring v2: ranked the way the subreddit is actually used.
--
-- You search a category, read the last year or two of threads, and shortlist
-- places that many different people mention recently -- then drop any of them
-- with a few standout bad experiences, because one "got sick" outweighs five
-- "great"s. v1 (scoring.sql) is untouched and stays selectable: the API takes
-- ?algo=v1|v2 and reads entity_leaderboard or entity_leaderboard_v2.
--
-- Differences from v1:
--   recency    full weight for a year, fading to nothing at three. v1's 180-day
--              half-life never actually lets a 2019 thread go.
--   volume     distinct PEOPLE in the last two years, not decayed mentions.
--   sentiment  negatives weigh 2x; a bare name in a list (food 0.3 and
--              nothing else) counts as volume but carries no opinion.
--   upvotes    1 + ln(score) as in v1, but a downvoted comment gets half weight.
--   flag       a large share of recent opinion is a strongly bad firsthand
--              experience. A share, not a count: every busy place collects a
--              few, and flagging on a count flagged 36% of them.
--   rank       recent reach x sentiment, halved when flagged.
--
-- Reads mention_weights, entity_alias and entity_leaderboard from scoring.sql,
-- so it is applied after it (refresh.SQL_FILES) and refreshed after it
-- (refresh.VIEWS). scoring.sql drops those with CASCADE, which takes these
-- views with them; re-running this file puts them back.
-- ===========================================================================

create or replace view scoring_v2_params as
select
  365            as full_weight_days,    -- TUNE  mentions this recent count fully
  1095           as zero_weight_days,    -- TUNE  ...fading linearly to 0 here
  730            as recent_days,         -- TUNE  "recent" for people + flags
  180            as trend_days,          -- TUNE  trend = this window vs the one before
  2.0::float8    as neg_weight,          -- TUNE  a negative opinion counts this many times
  3.0::float8    as aspect_pseudo,       -- TUNE  shrinkage toward the city mean
  0.5::float8    as downvoted_weight,    -- TUNE  score <= 0: the sub disagreed
  -0.6::float8   as strong_neg,          -- TUNE  this or worse is a standout negative
  2              as flag_min_people,     -- TUNE  at least this many people with one...
  0.25::float8   as flag_min_share,      -- TUNE  ...making up this share of recent opinion
  0.5::float8    as flag_penalty;        -- TUNE  rank multiplier when flagged


-- ---------------------------------------------------------------------------
-- 1. Per mention: recency, agreement, and one opinion number.
--
--    Materialised: the leaderboard and every topic search read it, and the
--    jsonb unpacking per row is the expensive part.
--      refresh materialized view concurrently mention_v2;
-- ---------------------------------------------------------------------------
do $$
begin
  if exists (select 1 from pg_matviews where matviewname = 'mention_v2') then
    drop materialized view mention_v2 cascade;
  end if;
end $$;
create materialized view mention_v2 as
select
  w.mention_id,
  w.comment_id,
  w.entity_key,
  w.thread_id,
  w.created_utc,
  w.score,
  w.is_firsthand,
  w.is_negated,
  w.aspects,
  -- '[deleted]' is a shared tombstone, not one person; see mention_weights.
  coalesce(nullif(w.author, '[deleted]'), w.comment_id) as person,

  greatest(0.0, least(1.0,
    (p.zero_weight_days - extract(epoch from (now() - w.created_utc)) / 86400.0)
    / (p.zero_weight_days - p.full_weight_days)))      as w_recency,
  extract(epoch from (now() - w.created_utc)) / 86400.0 as age_days,

  (1.0 / sqrt(w.in_chain))
  * (case when not w.score_settled then 1.0
          when w.score <= 0        then p.downvoted_weight
          else                          1.0 + ln(w.score::float8) end) as w_agree,

  -- A name dropped in a list with nothing said about it. It is evidence the
  -- place is talked about, not of what anyone thinks of it.
  (not w.is_negated and o.n_aspects = 1 and o.only_food_03)        as bare,

  -- The mention's opinion: the mean of the aspects it scored. An avoid
  -- instruction with no aspect attached is still a clear negative.
  case when o.n_aspects > 0 then o.opinion
       when w.is_negated    then p.strong_neg end                  as opinion,
  case when o.n_aspects > 0 then o.worst
       when w.is_negated    then p.strong_neg end                  as worst
from mention_weights w
cross join scoring_v2_params p
cross join lateral (
  select count(*)                                                    as n_aspects,
         avg(case when w.is_negated then -abs(x.v) else x.v end)     as opinion,
         min(case when w.is_negated then -abs(x.v) else x.v end)     as worst,
         coalesce(bool_and(x.k = 'food' and abs(x.v - 0.3) < 1e-9), false) as only_food_03
  from (
    select a.key as k, (a.value #>> '{}')::float8 as v
    from jsonb_each(case when jsonb_typeof(w.aspects) = 'object'
                         then w.aspects else '{}'::jsonb end) a
    where a.key in ('food', 'value', 'service', 'atmosphere', 'wait')
      and jsonb_typeof(a.value) = 'number'
  ) x
) o;

create unique index if not exists mention_v2_pk         on mention_v2(mention_id);
create index if not exists mention_v2_entity_idx        on mention_v2(entity_key);
create index if not exists mention_v2_thread_idx        on mention_v2(thread_id);


-- ---------------------------------------------------------------------------
-- 2. Aspect scores. Same shape as v1's aspect_scores, so a detail page can
--    show either; different weights.
-- ---------------------------------------------------------------------------
create or replace view aspect_scores_v2 as
with obs as (
  select m.entity_key,
         a.key as aspect,
         case when m.is_negated then -abs((a.value #>> '{}')::float8)
              else                    (a.value #>> '{}')::float8 end as val,
         m.w_agree * m.w_recency as w
  from mention_v2 m
  cross join lateral jsonb_each(case when jsonb_typeof(m.aspects) = 'object'
                                     then m.aspects else '{}'::jsonb end) a
  where not m.bare
    and m.w_recency > 0
    and a.key in ('food', 'value', 'service', 'atmosphere', 'wait')
    and jsonb_typeof(a.value) = 'number'
),
weighted as (
  select o.entity_key, o.aspect, o.val,
         o.w * (case when o.val < 0 then p.neg_weight else 1.0 end) as w
  from obs o cross join scoring_v2_params p
),
per_entity as (
  select entity_key, aspect,
         sum(w * val) as s, sum(w) as w, count(*) as n_obs
  from weighted group by 1, 2
),
city as (
  select aspect, sum(s) / nullif(sum(w), 0) as city_mean
  from per_entity group by 1
)
select e.entity_key, e.aspect, e.n_obs,
       e.w as aspect_weight,
       e.s / nullif(e.w, 0) as raw_mean,
       c.city_mean,
       (e.s + p.aspect_pseudo * c.city_mean) / (e.w + p.aspect_pseudo) as aspect_score
from per_entity e
join city c on c.aspect = e.aspect
cross join scoring_v2_params p;


-- ---------------------------------------------------------------------------
-- 3. The leaderboard. Every v1 column under the same name (aspects replaced
--    by v2's), so the API reads either table with one column list, plus the
--    v2 columns after them.
--      refresh materialized view concurrently entity_leaderboard_v2;
-- ---------------------------------------------------------------------------
do $$
begin
  if exists (select 1 from pg_matviews where matviewname = 'entity_leaderboard_v2') then
    drop materialized view entity_leaderboard_v2 cascade;
  end if;
end $$;
create materialized view entity_leaderboard_v2 as
with people as (
  -- One row per (place, person): their most recent mention decides how
  -- recent their voice is, and any strong negative of theirs counts once.
  select m.entity_key, m.person,
         max(m.w_recency)                                    as w_recency,
         min(m.age_days)                                     as newest_age,
         bool_or(not m.bare and m.opinion is not null)        as has_opinion,
         bool_or(m.is_firsthand and m.worst <= p.strong_neg)  as strong_neg,
         max(m.score) filter (where m.is_firsthand and m.worst <= p.strong_neg)
                                                             as neg_score,
         -- How much this person's voice counts, for the flag's share: their
         -- loudest (most upvoted) opinion, and their loudest strong negative.
         max(m.w_agree) filter (where not m.bare and m.opinion is not null) as op_w,
         max(m.w_agree) filter (where m.is_firsthand and m.worst <= p.strong_neg)
                                                             as neg_w
  from mention_v2 m cross join scoring_v2_params p
  where m.age_days <= p.recent_days
  group by m.entity_key, m.person
),
reach as (
  select pe.entity_key,
         count(*)                                             as recent_people,
         sum(pe.w_recency)                                    as recent_reach,
         count(*) filter (where pe.has_opinion)               as opinion_people,
         count(*) filter (where pe.strong_neg)                as strong_neg_people,
         max(pe.neg_score)                                    as top_neg_score,
         sum(pe.neg_w) / nullif(sum(pe.op_w), 0)              as strong_neg_share,
         count(*) filter (where pe.newest_age <= p.trend_days) as trend_now,
         count(*) filter (where pe.newest_age >  p.trend_days
                            and pe.newest_age <= 2 * p.trend_days) as trend_before
  from people pe cross join scoring_v2_params p
  group by pe.entity_key
),
opinion as (
  select m.entity_key,
         sum(m.opinion * m.w_agree * m.w_recency
             * (case when m.opinion < 0 then p.neg_weight else 1.0 end)) as s,
         sum(m.w_agree * m.w_recency
             * (case when m.opinion < 0 then p.neg_weight else 1.0 end)) as w
  from mention_v2 m cross join scoring_v2_params p
  where not m.bare and m.opinion is not null and m.w_recency > 0
  group by m.entity_key
),
city as (select sum(s) / nullif(sum(w), 0) as mean from opinion),
aspects as (
  select entity_key,
         max(aspect_score) filter (where aspect = 'food')       as food,
         max(aspect_score) filter (where aspect = 'value')      as value,
         max(aspect_score) filter (where aspect = 'service')    as service,
         max(aspect_score) filter (where aspect = 'atmosphere') as atmosphere,
         max(aspect_score) filter (where aspect = 'wait')       as wait
  from aspect_scores_v2 group by entity_key
),
scored as (
  select l.entity_key,
         coalesce(r.recent_people, 0)     as recent_people,
         coalesce(r.recent_reach, 0)      as recent_reach,
         coalesce(r.opinion_people, 0)    as opinion_people,
         coalesce(r.strong_neg_people, 0) as strong_neg_people,
         r.top_neg_score,
         coalesce(r.strong_neg_share, 0)  as strong_neg_share,
         r.trend_now, r.trend_before,
         -- Shrunk like the aspects: two raves are not a consensus.
         (coalesce(o.s, 0) + p.aspect_pseudo * c.mean)
           / (coalesce(o.w, 0) + p.aspect_pseudo)            as sentiment,
         coalesce(r.strong_neg_people, 0) >= p.flag_min_people
           and coalesce(r.strong_neg_share, 0) >= p.flag_min_share as flagged
  from entity_leaderboard l
  left join reach   r on r.entity_key = l.entity_key
  left join opinion o on o.entity_key = l.entity_key
  cross join city c
  cross join scoring_v2_params p
)
select l.entity_key, l.raw_mentions, l.decayed_volume, l.volume_share,
       l.distinct_authors, l.firsthand_mentions, l.negated_mentions,
       l.momentum_sigma, l.momentum_window_days, l.momentum_fired,
       l.first_seen, l.last_seen, l.months_active, l.longest_gap_months,
       a.food, a.value, a.service, a.atmosphere, a.wait,
       l.official_name, l.cuisine, l.boroughs, l.is_chain, l.closed,
       l.location_count,

       s.recent_people, s.recent_reach, s.opinion_people,
       s.strong_neg_people, s.strong_neg_share, s.top_neg_score, s.flagged,
       s.sentiment,
       -- People in the last trend window against the one before, as a percent.
       -- NULL rather than infinite when nobody spoke in the earlier window.
       case when s.trend_before > 0
            then round(100.0 * (s.trend_now - s.trend_before) / s.trend_before)
       end::int                                              as trend_pct,
       s.recent_reach * (1.0 + s.sentiment) / 2.0
         * (case when s.flagged then p.flag_penalty else 1.0 end) as rank_score
from scored s
join entity_leaderboard l on l.entity_key = s.entity_key
left join aspects a on a.entity_key = s.entity_key
cross join scoring_v2_params p;

create unique index if not exists entity_leaderboard_v2_pk
  on entity_leaderboard_v2(entity_key);
create index if not exists entity_leaderboard_v2_rank_idx
  on entity_leaderboard_v2(rank_score desc nulls last);
