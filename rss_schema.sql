-- RSS fallback tables. Written by rss.py, read by nothing.
--
-- Reddit's Atom feed carries five things per comment and no more: an id, an
-- author, a body, a timestamp, and the post it sits under. No score, no
-- parent, no depth. These tables hold exactly that and do not pretend
-- otherwise -- they are a second record in case Arctic Shift stops, not a
-- second pipeline. Nothing downstream reads them on purpose.
--
-- Kept apart from threads/comments so the real corpus never ends up holding
-- rows with a NULL score that only a comment on a table meaning "this one
-- came from RSS" could explain.

create table if not exists rss_threads (
  id         text primary key,         -- t3_1wkw8ju
  title      text,
  permalink  text,
  first_seen timestamptz not null default now()
);

create table if not exists rss_comments (
  id          text primary key,        -- t1_paudm96
  thread_id   text not null references rss_threads(id),
  author      text,
  body        text not null,
  created_utc timestamptz not null,
  permalink   text,
  first_seen  timestamptz not null default now()
);

-- "what did the feed see, newest first" is the only query this is for.
create index if not exists rss_comments_created_idx
  on rss_comments (created_utc desc);
create index if not exists rss_comments_thread_idx
  on rss_comments (thread_id);
