-- Place summaries (summarize.py): a few sentences per restaurant on what
-- its city's food subreddit says about it, written by Claude Haiku 5.5 from
-- its comments.
--
--   psql "$DATABASE_URL" -f summary_schema.sql
--
-- Apply it by hand once, or let the poller's next boot do it: schema.sql
-- carries the same block (tests/test_summary_schema.py keeps the two
-- identical). The tables are CREATE TABLE IF NOT EXISTS, which checks the
-- catalog before it takes any lock; a column added after a table's first
-- version is added behind a catalog check of its own, so re-applying the
-- file upgrades an older table, and a second run and every boot after the
-- first take no lock at all. Nothing here touches an existing table but
-- these. The lock_timeout caps the one ALTER's wait.
set lock_timeout = '5s';
--
-- These are caches and a ledger, never truth. Only `mentions` and the raw
-- tables are truth; every summary can be dropped and written again from the
-- comments. That is why they live in a table of their own, not as a column
-- on anything that holds evidence.
-- place-summaries-schema:begin
-- One row per place, keyed by its subreddit and the RESOLVED name
-- (entity_alias.resolved_key), so every spelling of a place shares one
-- summary and another city's place of the same name has its own. A row is
-- written when a place first qualifies, and again when it has collected enough new
-- discussion or the prompt or model changed. A place that qualifies with
-- nothing to send gets a row with no summary, so it waits for new comments
-- like any other. A failed attempt keeps the last good summary and counts
-- attempts; a place that keeps failing (summarize.MAX_ATTEMPTS) is parked
-- for SUMMARY_PARK_HOURS after its last failure (failed_at), or until
-- `summarize.py --retry-errors`.
--   mention_count    qualifying comments in the window when it was written
--   last_mention_at  when the newest of those comments was written
--   seen_comment_ids the ids of all of them (not only the ones sent): a
--                    qualifying comment not in it is new to the summary
--                    (summarize.py says why ids and not a time)
--   input_comments   comments the model was given, and their characters
--   written_at       when it was last written, with a summary or with
--                    nothing to send; null until then
create table if not exists place_summaries (
  subreddit        text not null default 'FoodNYC',
  resolved_key     text not null,
  summary          text,
  model            text,
  prompt_hash      text,
  mention_count    int,
  last_mention_at  timestamptz,
  seen_comment_ids text[],
  input_comments   int,
  input_chars      int,
  written_at       timestamptz,
  cost_usd         numeric(12, 8),
  usage            jsonb,
  attempts         int not null default 0,   -- failures since the last summary was written
  error            text,
  failed_at        timestamptz,
  updated_at       timestamptz not null default now(),
  primary key (subreddit, resolved_key)
);
-- Columns that came after the table's first version. Nullable with no
-- default, so the ALTER only touches the catalog; checked there first, so a
-- table that has them takes no lock. A row from a first-version table has
-- no seen set, so every qualifying comment reads as new to it and it is
-- written once more, which is all it needs.
do $$
begin
  perform set_config('lock_timeout', '5s', true);
  if not exists (select 1 from information_schema.columns
                 where table_schema = current_schema() and table_name = 'place_summaries'
                   and column_name = 'seen_comment_ids') then
    alter table place_summaries add column if not exists seen_comment_ids text[];
  end if;
end $$;
-- A summary belongs to one city's place (a place is subreddit and name,
-- scoring.sql). Rows from before the column are New York's, which is what
-- the default says; the literal must match subreddits.HOME
-- (tests/test_home_literal.py). A constant default only touches the
-- catalog, and the new key is built over a few thousand rows, behind the
-- same catalog check, so a table that has the column takes no lock.
do $$
begin
  perform set_config('lock_timeout', '5s', true);
  if not exists (select 1 from information_schema.columns
                 where table_schema = current_schema() and table_name = 'place_summaries'
                   and column_name = 'subreddit') then
    alter table place_summaries add column if not exists subreddit text not null default 'FoodNYC';
    alter table place_summaries drop constraint place_summaries_pkey;
    alter table place_summaries add primary key (subreddit, resolved_key);
  end if;
end $$;
-- Every paid call, kept apart from the summaries so that rewriting or
-- dropping a summary never forgets what it cost: the per-pass cap and the
-- lifetime ceiling (SUMMARY_RUN_USD, SUMMARY_CEILING_USD) are checked
-- against the sum of this table. outcome is 'written', the code of an
-- answer that could not be used (charged all the same), or 'unseen' for an
-- attempt that may have been billed with no answer (a timeout), charged its
-- worst case, or 'unstored' for an answer paid for that a pass which failed
-- part way could not store. A call's row is committed before its summary is.
create table if not exists summary_calls (
  id           bigserial primary key,
  subreddit    text not null default 'FoodNYC',
  resolved_key text not null,
  model        text not null,
  prompt_hash  text not null,
  outcome      text not null,
  cost_usd     numeric(12, 8) not null,
  usage        jsonb,
  called_at    timestamptz not null default now()
);
-- Whose place a call was for. The caps are still checked against the whole
-- table: one ceiling for every city. Calls from before the column are New
-- York's.
do $$
begin
  perform set_config('lock_timeout', '5s', true);
  if not exists (select 1 from information_schema.columns
                 where table_schema = current_schema() and table_name = 'summary_calls'
                   and column_name = 'subreddit') then
    alter table summary_calls add column if not exists subreddit text not null default 'FoodNYC';
  end if;
end $$;
-- When the poller's summary step last ran, so it runs at most once every
-- SUMMARY_EVERY_HOURS across restarts. One row, written by the step, for
-- every city: a run walks them all.
create table if not exists summary_state (
  only_row     boolean primary key default true check (only_row),
  last_pass_at timestamptz
);
-- place-summaries-schema:end
