-- This file runs on every poller and backfill boot, inside one transaction
-- (db.init), while the web app reads the same tables. So nothing here may
-- wait long for a lock: an older worker sitting "idle in transaction" holds
-- one on comments, and DDL queued behind it would in turn queue every board
-- read behind itself. Waits are capped at 5 s (db.init sets the same before
-- it runs this, and retries the whole file). Transaction-local, so it never
-- outlives the boot, and only if the caller set no cap of its own. By hand,
-- run the file as one transaction too, or this line covers only itself:
--   psql "$DATABASE_URL" -1 -f schema.sql
select set_config('lock_timeout', '5s', true) where current_setting('lock_timeout') = '0';

-- Statements on comments, threads and mentions below are checked in the
-- catalog first. "add column if not exists" and "create index if not
-- exists" both take their lock before they notice there is nothing to do,
-- and ADD COLUMN's is ACCESS EXCLUSIVE, so unguarded they would block the
-- board on every boot. Guarded, a boot of a current database locks none of
-- them. (create table if not exists is checked before any lock is taken.)
create table if not exists threads (
  id            text primary key,          -- t3_1wi6dmw
  subreddit     text not null,
  title         text not null,
  selftext      text,
  author        text,
  created_utc   timestamptz not null,
  score         int,
  upvote_ratio  real,
  num_comments  int,
  retrieved_on  timestamptz,
  first_seen_at timestamptz not null default now()
);

create table if not exists comments (
  id                text primary key,      -- t1_pa811pu
  thread_id         text not null references threads(id),
  parent_id         text not null,         -- raw: t3_... or t1_...
  parent_comment_id text,                  -- null if top-level. no FK: parents arrive late
  root_comment_id   text,
  depth             int,
  author            text,
  body              text not null,
  permalink         text not null,
  created_utc       timestamptz not null,
  retrieved_on      timestamptz,
  score             int,
  controversiality  int,
  score_settled     boolean not null default false,
  was_deleted_later boolean not null default false,
  first_seen_at     timestamptz not null default now()
);

do $$
begin
  if to_regclass('comments_thread_idx') is null then
    create index comments_thread_idx on comments(thread_id);
  end if;
  if to_regclass('comments_parent_idx') is null then
    create index comments_parent_idx on comments(parent_comment_id);
  end if;
  if to_regclass('comments_root_idx') is null then
    create index comments_root_idx on comments(root_comment_id);
  end if;
  if to_regclass('comments_created_idx') is null then
    create index comments_created_idx on comments(created_utc);
  end if;
  if to_regclass('comments_unsettled_idx') is null then
    create index comments_unsettled_idx on comments(created_utc) where not score_settled;
  end if;
end $$;

-- Backfilled comments were inserted unsettled, so scoring ignored their real
-- archive scores (avg 5.2) and weighed all 604k at 1.0. Anything first seen
-- 36h+ after posting arrived with a final score. Idempotent. Looked for
-- first, through the unsettled index, so a boot with nothing to fix only
-- reads comments and never takes the row-exclusive lock an UPDATE does.
do $$
begin
  if exists (select 1 from comments
             where not score_settled
               and first_seen_at > created_utc + interval '36 hours') then
    update comments set score_settled = true
    where not score_settled
      and first_seen_at > created_utc + interval '36 hours';
  end if;
end $$;

-- Several cities share these tables (see subreddits.py), so every reader
-- filters on subreddit first. threads always had it; comments gets a copy
-- because the corpus-wide counts in scoring.sql read comments with no join,
-- and a comment never changes thread, so the copy cannot drift.
--
-- The default is not a guess: every comment stored before this column
-- existed came from r/FoodNYC, and so does every comment written by code that
-- predates it -- which keeps an older poller sharing this database inserting
-- instead of failing NOT NULL. New code always passes it explicitly.
--
-- The column is catalog-only (a constant default), but ADD COLUMN still needs
-- ACCESS EXCLUSIVE once. The two indexes are built under a SHARE lock, which
-- blocks writes while they build; to avoid even that, create them by hand
-- first with CREATE INDEX CONCURRENTLY (docs/handoffs/subreddit-poller.md) and
-- this finds them and skips.
do $$
begin
  if not exists (select 1 from pg_attribute
                 where attrelid = 'comments'::regclass and attname = 'subreddit'
                   and not attisdropped) then
    alter table comments add column if not exists subreddit text not null default 'FoodNYC';
  end if;
  if to_regclass('comments_sub_created_idx') is null then
    create index comments_sub_created_idx on comments(subreddit, created_utc);
  end if;
  if to_regclass('threads_sub_created_idx') is null then
    create index threads_sub_created_idx on threads(subreddit, created_utc);
  end if;
end $$;

create table if not exists backfill_progress (
  kind       text primary key,       -- 'posts' | 'comments'
  cursor_utc bigint not null,        -- last created_utc successfully stored
  updated_at timestamptz not null default now()
);

-- backfill_progress has one cursor per kind, which is one subreddit's worth.
-- This is the same thing keyed per subreddit. A new table rather than a new
-- primary key on the old one: older code sharing this database writes
-- `on conflict (kind)`, and changing that key under it would break its
-- every page. backfill_progress is now read once, below, and can be dropped
-- when nothing older is left running.
create table if not exists backfill_cursors (
  subreddit  text not null,
  kind       text not null,          -- 'posts' | 'comments'
  cursor_utc bigint not null,        -- last created_utc successfully stored
  updated_at timestamptz not null default now(),
  primary key (subreddit, kind)
);

-- Carry r/FoodNYC's progress over, so the first boot resumes where the old
-- cursor stopped instead of re-sweeping twelve years. Only fills a gap: once
-- the row exists, the new code owns it.
insert into backfill_cursors (subreddit, kind, cursor_utc, updated_at)
select 'FoodNYC', kind, cursor_utc, updated_at from backfill_progress
on conflict (subreddit, kind) do nothing;

-- extraction state on the raw corpus. A timestamp + prompt hash rather than a
-- boolean, so a prompt v2 re-run is a query rather than a migration.
do $$
begin
  if (select count(*) from pg_attribute
      where attrelid = 'comments'::regclass and not attisdropped
        and attname in ('extracted_at', 'extracted_with', 'extract_error')) < 3 then
    alter table comments
      add column if not exists extracted_at   timestamptz,
      add column if not exists extracted_with text,
      add column if not exists extract_error  text;
  end if;
end $$;
-- Partial on HOME as well, because only HOME is ever extracted: the other
-- cities' millions of comments are never-extracted forever and would
-- otherwise fill an index meant to hold only the backlog. The literal must
-- match subreddits.HOME (tests/test_home_literal.py checks it), and stays a
-- literal because a partial index cannot read scoring_params. A database
-- built before this has the old predicate under the same name, and "if not
-- exists" would keep it, so that one is dropped first -- once; after that the
-- check finds the new definition and does nothing.
do $$
begin
  if exists (select 1 from pg_indexes
             where indexname = 'comments_unextracted_idx'
               and indexdef not like '%subreddit = ''FoodNYC''%') then
    drop index comments_unextracted_idx;
  end if;
  if to_regclass('comments_unextracted_idx') is null then
    create index comments_unextracted_idx
      on comments(thread_id)
      where subreddit = 'FoodNYC' and extracted_at is null and extract_error is null;
  end if;
end $$;

-- append-only source of truth for everything downstream.
create table if not exists mentions (
  id             bigserial primary key,
  comment_id     text not null references comments(id),
  restaurant_raw text not null,           -- verbatim, never modified
  entity_key     text not null,           -- normalized placeholder until resolution
  entity_id      bigint,                  -- filled in later; no FK yet
  neighborhood_hint text,
  dishes         jsonb,
  descriptors    jsonb,
  aspects        jsonb,                   -- {food,value,service,atmosphere,wait} each -1..1 or null
  expensiveness  real,                    -- fact, no valence
  is_firsthand   boolean,
  is_negated     boolean not null default false,
  model_version  text not null,
  prompt_hash    text not null,
  created_at     timestamptz not null default now()
);

do $$
begin
  if to_regclass('mentions_entity_idx') is null then
    create index mentions_entity_idx on mentions(entity_key);
  end if;
  if to_regclass('mentions_comment_idx') is null then
    create index mentions_comment_idx on mentions(comment_id);
  end if;
  if to_regclass('mentions_desc_idx') is null then
    create index mentions_desc_idx on mentions using gin(descriptors);
  end if;
end $$;

-- Extraction commits mentions and then marks the comment done; a crash between
-- the two would duplicate on re-run. Making the pair unique lets the retry be
-- idempotent, same as every other writer in this codebase.
-- Keyed on entity_key, not restaurant_raw: the model emits the same place
-- several times in one comment with different apostrophes ("l'industrie",
-- "l’industrie", "L'industrie"), and those are distinct raw strings. The
-- normalized key is what makes them one mention.
do $$
begin
  if to_regclass('mentions_unique_idx') is null then
    create unique index mentions_unique_idx on mentions(comment_id, entity_key, prompt_hash);
  end if;
end $$;

-- Trigram matching for the restaurant list. Needed before its index; a fresh
-- Railway database has no extensions enabled.
create extension if not exists pg_trgm;

-- Real NYC restaurants, from the health department's inspection data.
-- One row per NAME, not per licence: locations collapse, so a place with
-- three branches is one restaurant with three addresses.
create table if not exists restaurants (
  id             bigserial primary key,
  name           text not null,          -- display form, as the city lists it
  name_key       text not null unique,   -- normalized, matches mentions.entity_key
  cuisine        text,
  boroughs       text[],
  location_count int not null default 1,
  addresses      jsonb,
  is_chain       boolean not null default false,
  closed         boolean not null default false,
  last_seen      date                    -- most recent inspection on record
);

create index if not exists restaurants_key_idx  on restaurants(name_key);
create index if not exists restaurants_trgm_idx on restaurants using gin (name_key gin_trgm_ops);


-- ---------------------------------------------------------------------------
-- Manual identity decisions. entity_alias PROPOSES a merge; this DECIDES it.
--
-- A materialized view cannot be edited, so corrections need somewhere real to
-- live. Set resolved_key equal to entity_key to mean "never merge this one":
-- word_similarity scores "cote" against "cote wine bar" at a confident 1.00
-- and is simply wrong, and no threshold distinguishes that from "katzs"
-- against "katzs delicatessen", which is right for the same reason.
-- ---------------------------------------------------------------------------
create table if not exists alias_overrides (
  entity_key   text primary key,
  resolved_key text not null,
  note         text,
  created_at   timestamptz not null default now()
);


-- ---------------------------------------------------------------------------
-- Names that are not restaurants: Whole Foods, Zabar's, Chelsea Market, and
-- junk keys like "it" and "this place". Their mentions still exist; they are
-- only kept off the leaderboard. Keyed on the RESOLVED name, which is why each
-- also has an alias_overrides row pinning it to itself.
-- ---------------------------------------------------------------------------
create table if not exists excluded_entities (
  entity_key   text primary key,
  note         text,
  created_at   timestamptz not null default now()
);


-- ---------------------------------------------------------------------------
-- Cached restaurant imagery.
--
-- The row is the cache, not an in-process dict: uvicorn forks a process per
-- worker, so an in-memory cache would be resolved N times, expire at N
-- different moments, and answer differently depending on which process took
-- the request.
--
-- `source_ref` keeps the match auditable -- a Wikidata QID, so a wrong photo
-- can be traced to the entity that produced it rather than just replaced.
-- `locked` is the same idea as alias_overrides: once a person says a picture
-- is right, no later sweep gets to overwrite it.
--
-- status: 'found' (url is set) | 'none' (looked, found nothing -- cached so a
-- miss is not re-fetched on every page load).
-- ---------------------------------------------------------------------------
create table if not exists restaurant_images (
  entity_key   text primary key,
  status       text not null default 'none',
  source       text,
  source_ref   text,
  url          text,
  attribution  text,
  license      text,
  source_url   text,
  locked       boolean not null default false,
  fetched_at   timestamptz not null default now()
);

create index if not exists restaurant_images_stale_idx
  on restaurant_images(fetched_at) where not locked;


-- ---------------------------------------------------------------------------
-- Embedding caches for semantic search (embed.py, embed_schema.sql).
--
-- Same tables as embed_schema.sql, which explains them; that file is the
-- migration to apply by hand. They are repeated here so a fresh database
-- gets them like everything else, and guarded because this file runs on
-- every poller and backfill boot: a Postgres without pgvector (a laptop,
-- the stale local copy) must still boot, and simply has no embeddings.
-- tests/test_embed_schema.py keeps the two copies identical.
-- mentions_created_idx is the embedding window's (embed_schema.sql says
-- why); a lock timeout on it skips only the index, not the tables. On the
-- boot that first builds it, its SHARE lock on mentions (no writes) lasts
-- until this whole file's transaction commits, not just the build.
-- The HNSW index is deliberately absent: it is built after the backlog
-- (`python embed.py --build-index`).
-- ---------------------------------------------------------------------------
-- Any failure inside is caught, not just a missing extension: no privilege,
-- a pgvector older than 0.7 (no halfvec), a name clash. The block's work is
-- rolled back as one, the notice says why, and the rest of this file and
-- the boot carry on. embed.py then reports the tables as missing. A lock
-- timeout is the exception: it is a busy moment, not a broken setup, so it
-- goes up to db.init, which retries the whole file, rather than leaving
-- semantic search off until some later boot.
do $$
begin
  if not exists (select 1 from pg_available_extensions where name = 'vector') then
    raise notice 'pgvector is not installed on this server; skipping embedding tables';
    return;
  end if;

  create extension if not exists vector;

  create table if not exists comment_embeddings (
    comment_id  text not null references comments(id),
    model       text not null,
    input_hash  text not null,
    embedding   halfvec(1024) not null,
    embedded_at timestamptz not null default now(),
    primary key (comment_id, model)
  );

  create table if not exists thread_embeddings (
    thread_id   text not null references threads(id),
    model       text not null,
    input_hash  text not null,
    embedding   halfvec(1024) not null,
    embedded_at timestamptz not null default now(),
    primary key (thread_id, model)
  );

  create table if not exists embedding_errors (
    kind       text not null,
    item_id    text not null,
    model      text not null,
    input_hash text not null,
    error      text not null,
    failures   int not null default 1,
    failed_at  timestamptz not null default now(),
    primary key (kind, item_id, model)
  );

  if to_regclass('mentions_created_idx') is null then
    declare
      lt text := current_setting('lock_timeout');
    begin
      perform set_config('lock_timeout', '5s', true);
      create index mentions_created_idx on mentions (created_at);
      perform set_config('lock_timeout', lt, true);
    exception when lock_not_available then
      raise notice 'mentions_created_idx skipped (lock wait over 5s): the embed window scans mentions until a later boot builds it';
    end;
  end if;
exception
  when lock_not_available then
    raise;
  when others then
    raise notice 'embedding tables skipped (% %): semantic search is off until this is fixed',
      sqlstate, sqlerrm;
end $$;


-- ---------------------------------------------------------------------------
-- v6 extraction storage (extract_v6.py, extract_v6_schema.sql).
--
-- Same block as extract_v6_schema.sql, which explains it; that file is the
-- migration to apply by hand before the code that reads it is deployed. It
-- is repeated here so a fresh database gets it on boot, and every statement
-- is guarded so the boots after the first take no lock on mentions.
-- tests/test_extract_v6_schema.py keeps the two copies identical.
-- ---------------------------------------------------------------------------
-- v6-extraction-schema:begin
do $$
begin
  -- Transaction-local, so on the poller's boot (where this block runs inside
  -- db.init's one transaction, last) it ends with the boot's commit and never
  -- leaks into the poller's session. A timeout there rolls the whole file
  -- back, and db.init retries it after a pause (db.with_lock_retry).
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
-- Checked in the catalog first, like the other indexes: CREATE INDEX IF NOT
-- EXISTS takes a SHARE lock on extraction_state before it notices the index is
-- there, and behind a run's open write that wait hits lock_timeout and fails
-- the poller's boot.
do $$
begin
  perform set_config('lock_timeout', '5s', true);
  if to_regclass('extraction_state_batch_idx') is null then
    create index extraction_state_batch_idx
      on extraction_state(batch_id) where batch_id is not null;
  end if;
end $$;

-- The poller's v6 window is on first_seen_at, when a comment reached this
-- database, so a comment that arrives days after it was written (a backfill,
-- a re-read thread) is still extracted. This index serves that window, which
-- would otherwise read every comment on every pass. Building it reads
-- comments once under a SHARE lock (seconds), which holds up the poller's
-- inserts but no reads; checked in the catalog first, so it happens once. On
-- first_seen_at alone, so this file does not need comments.subreddit, which
-- the deploy adds. It is only an optimisation: a lock timeout skips it with a
-- notice (the window scans comments until a later run or boot builds it)
-- instead of failing the boot. On a boot its SHARE lock lasts until the whole
-- schema transaction commits.
do $$
begin
  perform set_config('lock_timeout', '5s', true);
  if to_regclass('comments_first_seen_idx') is null then
    begin
      create index comments_first_seen_idx on comments(first_seen_at);
    exception when lock_not_available then
      raise notice 'comments_first_seen_idx skipped (lock wait over 5s): the poller''s v6 window scans comments until a later boot builds it';
    end;
  end if;
end $$;

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
-- A v6 row is live only while its comment's extraction_state row carries the
-- same prompt hash: after a prompt fix, rows of the old hash can never be
-- counted beside the new ones, even before `extract_v6.py --reset-hash`
-- deletes them. The legacy branch is unchanged.
-- Created when missing, and replaced once where the first version (without
-- the hash check) is in place; a definition that already checks the hash is
-- left alone. Replacing a view takes an exclusive lock on it, which every
-- board read would queue behind on every boot, hence the check and the
-- lock_timeout. To change its definition later, change the check with it,
-- then `python refresh.py`.
do $$
begin
  perform set_config('lock_timeout', '5s', true);
  if to_regclass('live_mentions') is null
     or position('extraction_state' in pg_get_viewdef(to_regclass('live_mentions'))) = 0 then
    create or replace view live_mentions as
    select m.*
    from mentions m
    where case (select read_version from extraction_settings)
            when 'v6' then m.schema_version = 6
                       and m.comment_id is not null
                       and coalesce(m.kind, '') not in ('grocery', 'brand', 'venue', 'company', 'other')
                       and not coalesce(m.is_chain, false)
                       and exists (select 1 from extraction_state s
                                   where s.item_id = m.comment_id and s.version = 'v6'
                                     and s.prompt_hash = m.prompt_hash)
            else m.schema_version is null
          end;
  end if;
end $$;
-- Thread mode (extract_v6.py --mode thread) sends a post and up to about 25
-- of its comments as one request. Every item still gets its own
-- extraction_state row; this table keeps what the request itself was: which
-- items it numbered, which comments it quoted as context, the model's whole
-- answer (so a mention's attribution can be checked against it later), the
-- usage, the cost and the batch it went in. members is in bracket order: the
-- thread id first when the post was item [0] (post_item), then the comments
-- as numbered. It is also the retry queue: a chunk that fails is split in
-- half and the halves wait here as 'queued' until a run sends them; a half
-- that fails too is 'failed' with fallback set, and its items go out one at a
-- time in comment and post mode instead (each item's own extraction_state row
-- says so, by carrying that mode's prompt hash, until it is settled). A chunk
-- a batch did not answer for another reason (expired, an API error) is
-- 'queued' again as it was. A queued chunk with nothing left due is retired as
-- 'dropped'. A new table, so creating it takes no lock anything else waits on.
create table if not exists extract_chunks (
  id           text primary key,          -- 'ch-' + 32 hex digits; the batch request's custom_id
  version      text not null,
  thread_id    text not null,
  prompt_hash  text not null,
  effort       text not null,
  post_item    boolean not null default false,
  members      text[] not null,
  context_ids  text[] not null default '{}',
  generation   smallint not null default 0,   -- 0 as chunked, 1 a half of a chunk that failed
  split_from   text,
  status       text not null default 'queued'
               check (status in ('queued', 'batched', 'done', 'failed', 'dropped')),
  fallback     boolean not null default false,  -- its failure sent its items out alone
  attempts     int  not null default 0,          -- times it was sent
  batch_id     text,
  error        text,
  bad_ids      int,                        -- mentions dropped because their id names no item
  output       jsonb,                      -- the model's whole answer
  usage        jsonb,
  cost_usd     numeric(12, 8),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  finished_at  timestamptz
);
-- Checked in the catalog first, like every index in this file: CREATE INDEX
-- IF NOT EXISTS takes its SHARE lock before it notices the index is there.
do $$
begin
  perform set_config('lock_timeout', '5s', true);
  if to_regclass('extract_chunks_batch_idx') is null then
    create index extract_chunks_batch_idx on extract_chunks(batch_id) where batch_id is not null;
  end if;
  if to_regclass('extract_chunks_open_idx') is null then
    create index extract_chunks_open_idx on extract_chunks(thread_id) where status = 'queued';
  end if;
end $$;
-- v6-extraction-schema:end
