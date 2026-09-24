-- ===========================================================================
-- Name resolution status. Read-only: nothing here drops a mention.
--
-- A name missing from the city's list is NOT evidence it is fake. It may have
-- opened since the last inspection, be a truck, sit outside the five boroughs,
-- or be a nickname nobody licenses under ("Luger"). So the join reports, it
-- does not filter.
--
-- What separates a hallucination from an unlisted real place is corroboration:
-- an invented name appears once, from one person. A real one gets repeated.
-- ===========================================================================

-- Materialised. Every leaderboard row reaches this through a lateral to
-- report how confidently its name matched, and as a plain view that meant
-- recomputing a word_similarity lateral over 8,769 keys per request --
-- measured at ~2s for the view, which a 50-row page paid fifty times.
--
-- Same reasoning as entity_alias and mention_weights: it is derived, it is
-- expensive, and it is read far more often than the mentions under it change.
--   refresh materialized view concurrently mention_resolution;
do $$
begin
  if exists (select 1 from pg_matviews where matviewname = 'mention_resolution') then
    drop materialized view mention_resolution cascade;
  elsif exists (select 1 from pg_views where viewname = 'mention_resolution') then
    drop view mention_resolution cascade;
  end if;
end $$;
create materialized view mention_resolution as
select
  m.entity_key,
  count(*)                          as mentions,
  count(distinct c.author)
    filter (where c.author <> '[deleted]')  as distinct_authors,
  count(distinct c.thread_id)       as threads,

  r_exact.name                      as exact_match,
  r_exact.cuisine,
  r_exact.is_chain,

  -- best trigram candidate when nothing matches exactly
  fuzzy.name                        as fuzzy_match,
  round(fuzzy.score::numeric, 2)    as fuzzy_score,

  case
    when r_exact.name is not null              then 'exact'
    -- TUNE. 0.75 sits in the gap measured on real extractions: correct
    -- matches scored 0.80+, incorrect ones 0.60 and below.
    when fuzzy.score >= 0.75                   then 'fuzzy'
    when count(distinct c.author) >= 3         then 'unlisted'   -- corroborated
    else                                            'unverified' -- 1-2 people, no match
  end as status

from mentions m
join comments c on c.id = m.comment_id
left join restaurants r_exact on r_exact.name_key = m.entity_key
left join lateral (
  -- word_similarity, not similarity. Plain trigram penalises length
  -- differences, so "katz" scored 0.20 against "katzs delicatessen" and 0.16
  -- against the unrelated "katou restaurant" -- no threshold separates those.
  -- word_similarity asks how well the key matches SOME WORD RUN inside the
  -- official name, which is exactly how people shorten restaurant names.
  -- Measured: correct matches land 0.80-1.00, wrong ones 0.45-0.60.
  select r.name, word_similarity(m.entity_key, r.name_key) as score
  from restaurants r
  where m.entity_key <% r.name_key         -- uses the trgm GIN index
  -- Shortest name wins ties. Food halls are licensed under one combined name
  -- ("WOK TO WALK, LOS TACOS HERMANOS, POKE BOWL, ..."), which scores a
  -- perfect 1.00 for any tenant it contains and would otherwise beat the
  -- actual restaurant.
  order by score desc, length(r.name_key) asc
  limit 1
) fuzzy on r_exact.name is null

group by m.entity_key, r_exact.name, r_exact.cuisine, r_exact.is_chain,
         fuzzy.name, fuzzy.score;

-- Unique index is required for REFRESH ... CONCURRENTLY, and is what turns
-- the leaderboard's per-row lateral into an index lookup.
create unique index if not exists mention_resolution_pk
  on mention_resolution(entity_key);
create index if not exists mention_resolution_status_idx
  on mention_resolution(status);
