-- Place summaries (summarize.py): a few sentences per restaurant on what
-- r/FoodNYC says about it, written by Claude Haiku 5.5 from its comments.
--
--   psql "$DATABASE_URL" -f summary_schema.sql
--
-- Apply it by hand once, or let the poller's next boot do it: schema.sql
-- carries the same block (tests/test_summary_schema.py keeps the two
-- identical). Both statements are CREATE TABLE IF NOT EXISTS, which checks
-- the catalog before it takes any lock, so a second run and every boot after
-- the first do nothing, and even the first touches no existing table. The
-- lock_timeout is there in case that ever changes.
set lock_timeout = '5s';
--
-- These are caches and a ledger, never truth. Only `mentions` and the raw
-- tables are truth; every summary can be dropped and written again from the
-- comments. That is why they live in a table of their own, not as a column
-- on anything that holds evidence.
-- place-summaries-schema:begin
-- One row per place, keyed by the RESOLVED name (entity_alias.resolved_key),
-- so every spelling of a place shares one summary. A row is written when a
-- place first qualifies, and again when it has collected enough new
-- discussion or the prompt or model changed. A failed attempt keeps the last
-- good summary and counts attempts; a place that keeps failing is parked
-- (summarize.MAX_ATTEMPTS) until `summarize.py --retry-errors`.
--   mention_count    qualifying comments in the window when it was written
--   last_mention_at  when the newest of those comments was written
--   seen_through     when the newest of their mentions was stored
--                    (mentions.created_at): the watermark "x new mentions"
--                    counts from, so a mention extracted late still counts
--                    as new (summarize.py says why)
--   input_comments   comments the model was given, and their characters
create table if not exists place_summaries (
  resolved_key    text primary key,
  summary         text,
  model           text,
  prompt_hash     text,
  mention_count   int,
  last_mention_at timestamptz,
  seen_through    timestamptz,
  input_comments  int,
  input_chars     int,
  written_at      timestamptz,
  cost_usd        numeric(12, 8),
  usage           jsonb,
  attempts        int not null default 0,   -- failures since the last summary was written
  error           text,
  failed_at       timestamptz,
  updated_at      timestamptz not null default now()
);
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
  resolved_key text not null,
  model        text not null,
  prompt_hash  text not null,
  outcome      text not null,
  cost_usd     numeric(12, 8) not null,
  usage        jsonb,
  called_at    timestamptz not null default now()
);
-- place-summaries-schema:end
