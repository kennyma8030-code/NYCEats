-- v6 extraction: columns for the evidence the v6 prompt returns.
--
-- DRAFT. NOT APPLIED. DATABASE_URL is production; the orchestrator applies
-- this, once, with the owner's go-ahead, and only together with a writer
-- that fills it (db.insert_mentions writes a fixed column list today).
--
-- Why columns AND raw: the columns are what scoring and the API read, so they
-- are typed and checked. `raw` keeps the mention exactly as the model returned
-- it, so a field nobody has a column for yet (notes, tags, whatever v7 adds)
-- is never lost, and a column can be re-derived without paying for a re-run.
-- Both are evidence about one comment; neither is a score. Every score stays a
-- rebuildable cache, so nothing derived (chain flags, entity matches,
-- weights) goes here.
--
-- Old rows keep every new column null. A row's prompt_hash says which prompt
-- wrote it, and schema_version = 6 says the new columns are filled.
--
-- Levels are stored as small integers so they sort and count directly:
--   -2 very_negative, -1 negative, 0 neutral, 1 positive, 2 very_positive.
-- NULL means the comment said nothing; 0 means it gave a middling verdict.
-- price_level uses the same range: -2 very_cheap .. 2 very_expensive.
--
-- Until scoring is rewritten for v6, the writer should ALSO fill the legacy
-- columns from the same output (aspects, expensiveness, is_firsthand,
-- is_negated, dishes, descriptors), using the mapping in eval/v6_adapter.py,
-- so scoring.sql and app/queries.py keep working on v6 rows. `restaurant_raw`
-- holds v6 `name` and `neighborhood_hint` holds `location`.
--
-- Adding nullable columns without defaults only touches the catalog, so this
-- is quick on the full table. The checks are NOT VALID: every existing row is
-- null and passes anyway, and this skips a full-table scan under lock. They
-- are still enforced on every new row. Dropped and re-added, so the file can
-- be run twice.

begin;

alter table mentions
  add column if not exists schema_version   smallint,  -- 6 for rows written by the v6 prompt
  add column if not exists raw              jsonb,     -- this mention exactly as the model returned it
  add column if not exists named_in         text,      -- 'comment' | 'context' (name copied from parent/post)
  add column if not exists experience       text,      -- 'firsthand' | 'secondhand' | 'none'
  add column if not exists opinion          text,      -- 'none' | 'endorse' | 'stated'
  add column if not exists overall_level    smallint,
  add column if not exists taste_level      smallint,
  add column if not exists value_level      smallint,
  add column if not exists service_level    smallint,
  add column if not exists atmosphere_level smallint,
  add column if not exists wait_level       smallint,
  add column if not exists complaints       text[],    -- taste, price, portion, service, wait, ...
  add column if not exists dish_opinions    jsonb,     -- [{dish, level -2..2 or null, avoid}]
  add column if not exists price_level      smallint,  -- stated in words only, never from a dollar figure
  add column if not exists timeframe        text,      -- 'current' | 'past'
  add column if not exists trend            text,      -- 'declined' | 'improved'
  add column if not exists status           text,      -- 'closed' | 'moved' | 'opened'
  add column if not exists notes            jsonb;     -- [{about, text, level -2..2 or null, dish}]

-- `dishes` stays a list of names and `descriptors` keeps its GIN index; v6
-- tags go into `descriptors` (plus "closed" for a closed place), which is
-- what the search already reads.

alter table mentions
  drop constraint if exists mentions_named_in_chk,
  drop constraint if exists mentions_experience_chk,
  drop constraint if exists mentions_opinion_chk,
  drop constraint if exists mentions_timeframe_chk,
  drop constraint if exists mentions_trend_chk,
  drop constraint if exists mentions_status_chk,
  drop constraint if exists mentions_levels_chk,
  drop constraint if exists mentions_complaints_chk;

alter table mentions
  add constraint mentions_named_in_chk   check (named_in   in ('comment', 'context')) not valid,
  add constraint mentions_experience_chk check (experience in ('firsthand', 'secondhand', 'none')) not valid,
  add constraint mentions_opinion_chk    check (opinion    in ('none', 'endorse', 'stated')) not valid,
  add constraint mentions_timeframe_chk  check (timeframe  in ('current', 'past')) not valid,
  add constraint mentions_trend_chk      check (trend      in ('declined', 'improved')) not valid,
  add constraint mentions_status_chk     check (status     in ('closed', 'moved', 'opened')) not valid,
  add constraint mentions_levels_chk     check (
        overall_level    between -2 and 2 and taste_level      between -2 and 2
    and value_level      between -2 and 2 and service_level    between -2 and 2
    and atmosphere_level between -2 and 2 and wait_level       between -2 and 2
    and price_level      between -2 and 2) not valid,
  add constraint mentions_complaints_chk check (complaints <@ array[
        'taste', 'price', 'portion', 'service', 'wait', 'atmosphere', 'hype',
        'hygiene', 'consistency', 'availability', 'other']::text[]) not valid;

commit;

-- Optional, run separately (CREATE INDEX CONCURRENTLY cannot run inside a
-- transaction, and a plain CREATE INDEX blocks the poller's writes):
--   create index concurrently if not exists mentions_complaints_idx on mentions using gin (complaints);
--   create index concurrently if not exists mentions_v6_idx on mentions (entity_key) where schema_version = 6;
