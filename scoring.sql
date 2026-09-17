-- Scoring. Everything is computed at query time from `mentions`.
-- There is no stored score, no decay job, no window maintenance.
-- Tune by editing the constants marked TUNE.

-- ---------------------------------------------------------------------------
-- Per-mention weight: correlation discounts applied before anything is counted
-- ---------------------------------------------------------------------------
create or replace view mention_weights as
with base as (
  select m.id,
         m.entity_key,
         c.created_utc,
         c.author,
         c.score,
         -- A thread whose own title/selftext names the place is ONE attention
         -- event: the mentions were prompted, not volunteered.
         (t.title || ' ' || coalesce(t.selftext, '')) ~* m.entity_key as prompted,
         count(*) over (partition by m.entity_key, c.root_comment_id) as in_chain,
         count(*) over (partition by m.entity_key, c.thread_id)       as in_thread,
         row_number() over (partition by m.entity_key, c.author
                            order by c.created_utc)                   as author_nth
  from mentions m
  join comments c on c.id = m.comment_id
  join threads  t on t.id = c.thread_id
)
select id, entity_key, created_utc, score, prompted,
       -- volume weight: prompted mentions collapse across the whole thread,
       -- volunteered ones only across their own reply chain
       (case when prompted then 1.0 / sqrt(in_thread)
             else              1.0 / sqrt(in_chain) end)
       * (case when author_nth = 1 then 1.0        -- TUNE author cap
               when author_nth = 2 then 0.5
               else                    0.0 end) as w_volume,
       -- sentiment weight: NOT discounted for being prompted. A thread asking
       -- about one place still yields real, independent opinions.
       (1.0 / sqrt(in_chain))
       * (1 + ln(1 + greatest(score, 0)))       as w_sentiment
from base;


-- ---------------------------------------------------------------------------
-- Volume + momentum, normalised by how busy the subreddit was.
-- Without that division, every restaurant looks like it is rising, because
-- r/FoodNYC grew ~46x between 2019 and 2025.
-- ---------------------------------------------------------------------------
with totals as (
  select count(*) filter (where created_utc > now() - interval '90 days')  as recent_all,
         count(*) filter (where created_utc > now() - interval '365 days') as base_all
  from comments
),
agg as (
  select entity_key,
         -- decayed volume, half-life 180d  TUNE
         sum(w_volume * power(2, -extract(epoch from (now() - created_utc))/86400/180)) as volume,
         sum(w_volume) filter (where created_utc > now() - interval '90 days')  as recent,
         sum(w_volume) filter (where created_utc > now() - interval '365 days') as baseline,
         count(*) as raw_mentions,
         min(created_utc) as first_seen,
         count(distinct date_trunc('month', created_utc)) as months_active
  from mention_weights
  group by entity_key
)
select a.entity_key,
       round(a.volume::numeric, 2) as volume,
       a.raw_mentions,
       a.months_active,
       -- expected recent count if nothing changed, scaled by subreddit activity
       round((a.baseline * t.recent_all / nullif(t.base_all, 0))::numeric, 2) as expected,
       -- momentum in standard deviations; >= 3 is worth showing  TUNE
       round(((a.recent - a.baseline * t.recent_all / nullif(t.base_all, 0))
              / nullif(sqrt(a.baseline * t.recent_all / nullif(t.base_all, 0)), 0))::numeric, 2)
         as momentum_sigma
from agg a cross join totals t
where a.raw_mentions >= 3
order by a.volume desc
limit 50;
