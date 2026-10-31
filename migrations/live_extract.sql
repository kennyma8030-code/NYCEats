-- The columns the live-extract branch reads, applied by hand BEFORE the web
-- app or the poller is deployed with it:
--
--   psql "$DATABASE_URL" -f migrations/live_extract.sql
--
-- The web app's feed names threads.was_deleted_later outright, so a web
-- deploy that lands before the column exists fails the feed. schema.sql has
-- the same ALTER, guarded the same way, so the poller's boot finds the
-- columns and goes on to what only it does: marking the posts collected
-- live up to the deploy to settle (once, behind a marker), and building
-- threads_unsettled_idx.
--
-- The ALTER only touches the catalog (constant defaults), but takes an
-- ACCESS EXCLUSIVE lock on threads for that moment. lock_timeout, for the
-- session, makes it give up after 5 s rather than queue the board behind an
-- old transaction; nothing is then changed, and the file can be run again.
-- Guarded, so running it twice changes nothing.
--
-- score_settled defaults to true and stays so: today's poller and backfill,
-- running until the deploy, insert posts without it, and those are settled
-- by the default; the new boot marks the live ones among them to settle.
-- The new db.insert_threads always says which a post is.

set lock_timeout = '5s';

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
