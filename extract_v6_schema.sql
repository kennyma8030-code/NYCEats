-- v6 extraction storage: the v6 columns on mentions, post mentions, the v6
-- cursor, the batch ledger, and the one switch that says which mentions the
-- board reads.
--
--   psql "$DATABASE_URL" -f extract_v6_schema.sql
--
-- Apply it by hand, once, before deploying the code that reads it. schema.sql
-- carries the same block (tests/test_extract_v6_schema.py keeps the two
-- identical), so a fresh database gets it on boot like everything else, and a
-- deploy that skipped this step would apply it on the poller's first boot.
-- It is idempotent: each change is guarded by a catalog check, so a second
-- run, and every boot after the first, alters nothing and takes no lock on
-- mentions or on live_mentions (only catalog reads and the one-row insert
-- into extraction_settings).
--
-- The first run does take locks: an ACCESS EXCLUSIVE lock on mentions for the
-- ALTERs (catalog-only, so brief once granted) and a SHARE lock while the
-- partial index is built. Waiting for them behind a long query would stall
-- the app's reads queued behind it, so the waits are capped by
-- lock_timeout = 5s: if it fires, the whole step rolls back (the ALTERs are
-- one statement), nothing is half-applied, and you simply run it again,
-- ideally at a quiet moment.
set lock_timeout = '5s';
--
-- What changes for the live site: nothing. Old rows keep every new column
-- null, extraction_settings starts at 'legacy', and live_mentions in legacy
-- mode is exactly the rows the board counts today.
--
-- Why columns AND raw: the columns are what scoring and the API read, so they
-- are typed and checked. `raw` keeps each mention exactly as the model
-- returned it, and extraction_state.output keeps the model's whole answer for
-- every item, mentions or not, so a field nobody has a column for yet is never
-- lost and a column can be re-derived without paying for a re-run.
--
-- Levels are small integers so they sort and count directly:
--   -2 extreme_knock, -1 knock, 0 mixed, 1 praise, 2 superlative_praise.
-- NULL means the text said nothing; 0 means it gave a middling verdict.
-- price_level uses the same range: -2 very_cheap .. 2 very_expensive.
--
-- A v6 row also fills the legacy columns (aspects, expensiveness,
-- is_firsthand, is_negated, dishes, descriptors, restaurant_raw = name,
-- neighborhood_hint = location) through prompts_v6/v6_adapter.py, so
-- scoring.sql and the app read v6 rows without being rewritten.
-- v6-extraction-schema:begin
do $$
begin
  -- Transaction-local, so on the poller's boot (where this block runs inside
  -- db.init's one transaction, last) it ends with the boot's commit and never
  -- leaks into the poller's session. A timeout there fails the boot, and
  -- Railway's restart policy retries it.
  perform set_config('lock_timeout', '5s', true);
  if not exists (select 1 from information_schema.columns
                 where table_schema = current_schema() and table_name = 'mentions'
                   and column_name = 'schema_version') then
    -- One statement, so the columns arrive together or not at all. Nullable
    -- with no default, so it only touches the catalog.
    alter table mentions
      add column if not exists schema_version   smallint,  -- 6 for rows the v6 prompt wrote
      add column if not exists raw              jsonb,     -- this mention exactly as the model returned it
      add column if not exists kind             text,      -- restaurant, bar, ... grocery, brand, venue, company, other
      add column if not exists named_in         text,      -- 'comment' | 'context' (name copied from the thread)
      add column if not exists experience       text,      -- 'firsthand' | 'secondhand' | 'none'
      add column if not exists opinion          text,      -- 'none' | 'endorse' | 'stated'
      add column if not exists overall_level    smallint,
      add column if not exists taste_level      smallint,
      add column if not exists value_level      smallint,
      add column if not exists service_level    smallint,
      add column if not exists atmosphere_level smallint,
      add column if not exists wait_level       smallint,
      add column if not exists avoid            boolean,   -- "skip it", told to readers
      add column if not exists dish_opinions    jsonb,     -- [{dish, level -2..2 or null, avoid}]
      add column if not exists notes            jsonb,     -- [{about, text}]
      add column if not exists tags             jsonb,     -- ["sichuan", "date night", ...]
      add column if not exists price_level      smallint,  -- a price word only, never a dollar figure
      add column if not exists timeframe        text,      -- 'current' | 'past'
      add column if not exists trend            text,      -- 'declined' | 'improved'
      add column if not exists status           text,      -- 'closed' | 'moved' | 'opened'
      -- chains.txt at write time. v6 keeps chain mentions instead of
      -- deleting them, and this says which ones the old writer would have
      -- dropped, so the board can keep leaving them out.
      add column if not exists is_chain         boolean,
      -- Mentions from an original post (v6 post mode) name the post here
      -- and leave comment_id null. Comment mentions leave this null.
      add column if not exists thread_id        text references threads(id);
  end if;

  if exists (select 1 from pg_attribute
             where attrelid = 'mentions'::regclass and attname = 'comment_id' and attnotnull) then
    alter table mentions alter column comment_id drop not null;
  end if;

  -- NOT VALID: every existing row is null and passes anyway, and this skips
  -- a full-table scan under lock. They are still enforced on every new row.
  if not exists (select 1 from pg_constraint
                 where conrelid = 'mentions'::regclass and conname = 'mentions_v6_chk') then
    alter table mentions add constraint mentions_v6_chk check (
          named_in   in ('comment', 'context')
      and experience in ('firsthand', 'secondhand', 'none')
      and opinion    in ('none', 'endorse', 'stated')
      and timeframe  in ('current', 'past')
      and trend      in ('declined', 'improved')
      and status     in ('closed', 'moved', 'opened')
      and overall_level    between -2 and 2 and taste_level      between -2 and 2
      and value_level      between -2 and 2 and service_level    between -2 and 2
      and atmosphere_level between -2 and 2 and wait_level       between -2 and 2
      and price_level      between -2 and 2) not valid;
  end if;
  -- Exactly one of comment_id and thread_id names where the mention came from.
  if not exists (select 1 from pg_constraint
                 where conrelid = 'mentions'::regclass and conname = 'mentions_source_chk') then
    alter table mentions add constraint mentions_source_chk
      check ((comment_id is null) <> (thread_id is null)) not valid;
  end if;
end $$;

-- Post mentions need the idempotence key mentions_unique_idx gives comments
-- (its comment_id is null for them, and nulls never conflict). The partial
-- index is empty until post mode runs, but building it reads mentions once,
-- under a SHARE lock. Checked in the catalog first, because CREATE INDEX IF
-- NOT EXISTS takes that lock before it notices the index is there.
do $$
begin
  perform set_config('lock_timeout', '5s', true);
  if to_regclass('mentions_post_unique_idx') is null then
    create unique index mentions_post_unique_idx
      on mentions(thread_id, entity_key, prompt_hash) where comment_id is null;
  end if;
end $$;

-- The v6 cursor, one row per item (a t1_ comment or a t3_ post) and version.
-- Its own table rather than comments.extracted_at: that column is the old
-- extractor's cursor, and both run side by side until the switch, so neither
-- may skip what the other has done. A row with nothing set is queued (a retry
-- owed); batch_id set means it is in a submitted batch; extracted_at set means
-- done; extract_error set means it failed twice and waits for --retry-errors.
create table if not exists extraction_state (
  item_id       text not null,          -- t1_... or t3_...
  version       text not null,          -- 'v6'
  kind          text not null check (kind in ('comment', 'post')),
  prompt_hash   text,
  model         text,
  batch_id      text,
  attempts      int  not null default 0,
  extracted_at  timestamptz,
  extract_error text,
  output        jsonb,                  -- the model's whole answer: {"mentions": [...]}
  usage         jsonb,                  -- token counts as Anthropic reported them
  cost_usd      numeric(12, 8),
  updated_at    timestamptz not null default now(),
  primary key (item_id, version)
);
create index if not exists extraction_state_batch_idx
  on extraction_state(batch_id) where batch_id is not null;

-- Every Message Batch extract_v6.py submits, so a re-run re-attaches to the
-- ones in flight instead of paying for them twice. hold_usd is the batch's
-- worst case, counted against the spend cap until the batch is collected.
-- An id starting 'pending-' means a submission whose outcome is unknown (the
-- process died, or the API timed out or answered 5xx after it may have
-- accepted the batch); the next run matches it against the API's batch list,
-- or see extract_v6.py --resolve-pending. 'lost' is a batch the API answers
-- 404 for (past retention, or another key): no longer re-attached, its items
-- held back until --drop-batch.
create table if not exists extract_batches (
  id           text primary key,
  version      text not null,
  requests     int  not null,
  hold_usd     numeric(12, 6) not null,
  cost_usd     numeric(12, 8),
  status       text not null default 'pending'
               check (status in ('pending', 'submitted', 'collected', 'lost')),
  created_at   timestamptz not null default now(),
  submitted_at timestamptz,
  collected_at timestamptz
);

-- The switch: which extraction the board reads. One row. 'legacy' is every
-- row the old prompts wrote (schema_version null), which is the board as it
-- is today; 'v6' is the v6 rows. Flipping it is `extract_v6.py --read v6`,
-- which updates this row and refreshes the scoring views in one go.
create table if not exists extraction_settings (
  only_row     boolean primary key default true check (only_row),
  read_version text not null default 'legacy' check (read_version in ('legacy', 'v6')),
  updated_at   timestamptz not null default now()
);
insert into extraction_settings default values on conflict do nothing;

-- What scoring.sql, resolve.sql and the API read instead of mentions. In v6
-- mode it leaves out what the old board never had: kinds the counts exclude
-- (groceries, brands, venues, companies, other), chains.txt names, and post
-- mentions, which scoring cannot place yet (it joins every mention to a
-- comment for its author and date). Those rows are still in mentions.
-- Created only when missing: replacing a view takes an exclusive lock on it,
-- which every board read would queue behind on every boot. To change its
-- definition later, run the `create or replace view` by hand (with
-- lock_timeout set), then `python refresh.py`.
do $$
begin
  if to_regclass('live_mentions') is null then
    create view live_mentions as
    select m.*
    from mentions m
    where case (select read_version from extraction_settings)
            when 'v6' then m.schema_version = 6
                       and m.comment_id is not null
                       and coalesce(m.kind, '') not in ('grocery', 'brand', 'venue', 'company', 'other')
                       and not coalesce(m.is_chain, false)
            else m.schema_version is null
          end;
  end if;
end $$;
-- v6-extraction-schema:end
