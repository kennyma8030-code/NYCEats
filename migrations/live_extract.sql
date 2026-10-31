-- The columns the live-extract branch reads, applied by hand BEFORE the web
-- app or the poller is deployed with it, NOT as one transaction:
--
--   psql "$DATABASE_URL" -f migrations/live_extract.sql
--
-- The web app's feed names threads.was_deleted_later outright, so a web
-- deploy that lands before the column exists fails the feed. schema.sql
-- does the same on the poller's boot, guarded the same way, so after this
-- file the boot only builds threads_unsettled_idx.
--
-- Each statement below commits on its own (psql without -1), so the ACCESS
-- EXCLUSIVE lock the ALTER takes on threads, for the moment it touches the
-- catalog, is not held across the update. lock_timeout is for the session:
-- a statement that cannot get its lock in 5 s fails without waiting longer,
-- leaves nothing half done, and the file can be run again. Every statement
-- is guarded, so running it twice changes nothing.

set lock_timeout = '5s';

-- 1. The columns. Constant defaults, so this only touches the catalog.
-- score_settled defaults to true and stays so: today's poller and backfill,
-- still running until the deploy, go on inserting the backfill's history,
-- which arrived with final numbers, and the new db.insert_threads always
-- says which a post is.
do $$
begin
  if (select count(*) from pg_attribute
      where attrelid = 'threads'::regclass and not attisdropped
        and attname in ('score_settled', 'was_deleted_later')) < 2 then
    alter table threads
      add column if not exists score_settled     boolean not null default true,
      add column if not exists was_deleted_later boolean not null default false;
  end if;
end $$;

-- 2. Once, in a transaction of its own: the posts the poller collected live,
-- first seen less than SETTLE_HOURS (40) after they were posted, are marked
-- to settle, so the new settle pass reads their final score, upvote_ratio
-- and num_comments. The column's comment records that it was done (the
-- boot's schema.sql checks the same), so neither this file run again nor a
-- later boot marks them twice. It locks only the rows it changes, one per
-- post collected live since the poller started (a few thousand at most), for
-- the milliseconds it takes, and today's code neither reads nor writes them.
do $$
begin
  if position('(live-extract)' in coalesce(col_description('threads'::regclass,
       (select attnum from pg_attribute where attrelid = 'threads'::regclass and attname = 'score_settled')), ''))
     = 0 then
    update threads set score_settled = false
    where score_settled and first_seen_at < created_utc + make_interval(
      secs => coalesce(nullif(current_setting('nyceats.settle_hours', true), '')::float8, 40) * 3600);
    comment on column threads.score_settled is
      'Final score read by the settle re-read. Posts stored before it existed were marked once (live-extract).';
  end if;
end $$;
