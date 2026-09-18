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

create index if not exists comments_thread_idx      on comments(thread_id);
create index if not exists comments_parent_idx      on comments(parent_comment_id);
create index if not exists comments_root_idx        on comments(root_comment_id);
create index if not exists comments_created_idx     on comments(created_utc);
create index if not exists comments_unsettled_idx   on comments(created_utc) where not score_settled;

create table if not exists backfill_progress (
  kind       text primary key,       -- 'posts' | 'comments'
  cursor_utc bigint not null,        -- last created_utc successfully stored
  updated_at timestamptz not null default now()
);

-- extraction state on the raw corpus. A timestamp + prompt hash rather than a
-- boolean, so a prompt v2 re-run is a query rather than a migration.
alter table comments add column if not exists extracted_at   timestamptz;
alter table comments add column if not exists extracted_with text;
alter table comments add column if not exists extract_error  text;
create index if not exists comments_unextracted_idx
  on comments(thread_id) where extracted_at is null and extract_error is null;

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

create index if not exists mentions_entity_idx  on mentions(entity_key);
create index if not exists mentions_comment_idx on mentions(comment_id);
create index if not exists mentions_desc_idx    on mentions using gin(descriptors);

-- Extraction commits mentions and then marks the comment done; a crash between
-- the two would duplicate on re-run. Making the pair unique lets the retry be
-- idempotent, same as every other writer in this codebase.
create unique index if not exists mentions_unique_idx
  on mentions(comment_id, restaurant_raw, prompt_hash);
