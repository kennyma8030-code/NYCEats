-- The columns the live-extract branch reads, applied by hand BEFORE the web
-- app or the poller is deployed with it:
--
--   psql "$DATABASE_URL" -1 -f migrations/live_extract.sql
--
-- The web app names these columns outright (the feed reads
-- threads.was_deleted_later, the evidence lists comments.edited_at and
-- original_body), so a web deploy that lands before they exist fails those
-- queries. schema.sql adds the same columns on the poller's boot, guarded the
-- same way, so after this file the boot finds them and does nothing more
-- than build threads_unsettled_idx.
--
-- Every ALTER only touches the catalog (nullable columns, or a constant
-- default), though each takes an ACCESS EXCLUSIVE lock for that moment;
-- lock_timeout keeps one from queueing the board behind an old transaction.
-- If it times out, nothing is applied (run it as one transaction, -1) and it
-- can be run again. Running it twice changes nothing.
--
-- The one UPDATE marks the threads the poller collected live (first seen
-- before their score could settle) as still to settle, so the new settle
-- pass reads their final numbers; the backfill's history arrived settled.
-- It runs only in the transaction that adds the column, and is safe before
-- the deploy: today's code neither reads nor writes threads.score_settled.
-- Its threshold is db.SETTLE_HOURS (40); applied here, without db.init
-- setting nyceats.settle_hours, it is 40.
select set_config('lock_timeout', '5s', true);

do $$
begin
  if not exists (select 1 from pg_attribute
                 where attrelid = 'threads'::regclass and attname = 'score_settled'
                   and not attisdropped) then
    alter table threads
      add column if not exists score_settled     boolean not null default true,
      add column if not exists was_deleted_later boolean not null default false,
      add column if not exists original_selftext text;
    alter table threads alter column score_settled set default false;
    update threads set score_settled = false
    where first_seen_at < created_utc + make_interval(
      secs => coalesce(nullif(current_setting('nyceats.settle_hours', true), '')::float8, 40) * 3600);
  end if;
end $$;

do $$
begin
  if (select count(*) from pg_attribute
      where attrelid = 'comments'::regclass and not attisdropped
        and attname in ('original_body', 'edited_at')) < 2 then
    alter table comments
      add column if not exists original_body text,
      add column if not exists edited_at     timestamptz;
  end if;
end $$;

do $$
begin
  if to_regclass('extraction_state') is not null
     and not exists (select 1 from information_schema.columns
                     where table_schema = current_schema() and table_name = 'extraction_state'
                       and column_name = 'text_md5') then
    alter table extraction_state add column if not exists text_md5 text;
  end if;
end $$;
