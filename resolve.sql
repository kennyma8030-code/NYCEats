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

create or replace view mention_resolution as
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
    -- TUNE. At 0.6 an invented "tonys pizzeria supreme" matched a real
    -- "TONYS PIZZERIA" and would have merged into its score silently.
    when fuzzy.score >= 0.75                   then 'fuzzy'
    when count(distinct c.author) >= 3         then 'unlisted'   -- corroborated
    else                                            'unverified' -- 1-2 people, no match
  end as status

from mentions m
join comments c on c.id = m.comment_id
left join restaurants r_exact on r_exact.name_key = m.entity_key
left join lateral (
  select r.name, similarity(r.name_key, m.entity_key) as score
  from restaurants r
  where r.name_key % m.entity_key          -- uses the trgm index
  order by score desc
  limit 1
) fuzzy on r_exact.name is null

group by m.entity_key, r_exact.name, r_exact.cuisine, r_exact.is_chain,
         fuzzy.name, fuzzy.score;
