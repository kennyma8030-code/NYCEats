-- Embedding cache tables. Standalone migration: apply once, by hand, before
-- the first `python embed.py` run.
--
--   psql "$DATABASE_URL" -f embed_schema.sql
--
-- schema.sql carries the same tables inside a guarded block, so a fresh
-- database (or the next poller boot) gets them too; this file is the
-- explicit, fail-loudly version. Every statement is "if not exists", so
-- applying it twice is harmless. tests/test_embed_schema.py checks the two
-- copies have not drifted.
--
-- These are caches, never truth. Only `mentions` and the raw tables are
-- truth; every row here can be dropped and rebuilt by re-running embed.py.
-- That is why the vectors live in their own tables rather than as columns on
-- `comments`.
--
-- The HNSW index is NOT here. It is built after the backlog has loaded
-- (`python embed.py --build-index`): building it first would make every one
-- of ~140k inserts pay for graph maintenance.

begin;

create extension if not exists vector;

-- One vector per comment per model. Search groups by restaurant when it
-- reads, through mentions, never here.
-- `model` is embedding.MODEL_KEY: the model slug, the dims it was cut to,
-- and the endpoint tag and quantization it was pinned to. Vectors are only
-- comparable within one value, so a model or endpoint swap is new rows
-- beside the old, not a migration.
-- `input_hash` is sha256 of the exact text embedded; when the text changes
-- (an edited comment, a changed formatter) the row is due again.
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

-- Inputs the provider refused or returned an unusable vector for. Kept out
-- of the truth tables, keyed like the vectors, and skipped only while the
-- text is unchanged, so an edit or a new model retries it on its own.
-- `python embed.py --retry-errors` clears them.
create table if not exists embedding_errors (
  kind       text not null,          -- 'comment' | 'thread'
  item_id    text not null,
  model      text not null,
  input_hash text not null,
  error      text not null,
  failures   int not null default 1,
  failed_at  timestamptz not null default now(),
  primary key (kind, item_id, model)
);

-- The poller's embedding window is on when a comment's mention was stored,
-- not when the comment was written, so a comment whose first mention comes
-- late (a v6 backfill, an extraction retry) is still embedded. This index
-- keeps that window a range read instead of a scan of mentions on every
-- page. mentions.created_at is the insert time (its default; no writer sets
-- it). Guarded by a catalog check, so once it exists neither this file nor
-- a boot takes a lock on mentions for it; the first build blocks writes to
-- mentions for well under a second (149k rows), and gives up after 5s
-- waiting for its lock. In schema.sql a timeout skips only the index.
do $$
begin
  if to_regclass('mentions_created_idx') is null then
    declare
      lt text := current_setting('lock_timeout');
    begin
      perform set_config('lock_timeout', '5s', true);
      create index mentions_created_idx on mentions (created_at);
      perform set_config('lock_timeout', lt, true);
    end;
  end if;
end $$;

commit;
