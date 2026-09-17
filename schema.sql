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
