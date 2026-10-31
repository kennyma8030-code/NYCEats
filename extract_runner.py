"""The daily thread-mode extraction run, for a Railway cron service of its own.

    python extract_runner.py

Started by railway.extract.json in a dedicated service, never by the NYCEats
service (its railway.json starts the poller, and a second poller must never
run). Railway's API no longer lets a service point at another config file,
so the service is deployed with `railway up` from a staging copy of the repo
whose railway.json has been replaced by railway.extract.json. Like every
pipeline script it writes to DATABASE_URL, so it is started on purpose;
nothing redeploys it on a push to main (watchPatterns name only its own
config, should the service ever be linked to the repo).

What it runs, in one extract_v6.py invocation sharing one cap and ceiling:
the redo of comments cut at 1,500 characters first when
EXTRACT_REDO_CUT_BEFORE is set, then every thread with anything not yet
extracted whose post is old enough and on or after its subreddit's floor:

    extract_v6.py --mode thread --effort medium --newest-first --batch
                  --max-usd $EXTRACT_RUN_USD --ceiling-usd $EXTRACT_CEILING_USD
                  --subreddit $EXTRACT_SUBREDDITS --since $EXTRACT_SINCE
                  --min-post-age ${EXTRACT_MIN_POST_AGE_HOURS}h
                  [--redo-cut-before $EXTRACT_REDO_CUT_BEFORE] --lock-wait $EXTRACT_LOCK_WAIT

The selection is by state, not by a window (extract_v6.thread_candidates):
a day Railway was down, a run the cap stopped, or one that failed leaves its
threads due, and the next run takes them, newest first. A thread younger than
the minimum age is not touched at all, so a new thread is read once, whole,
after its first two days of comments; comments that come later go out on
their own (numbered, under the post and their quoted ancestors) in a later
run.

Daily, as a Railway cron job: the service's Settings > Cron Schedule, or
"cronSchedule" under "deploy" in railway.extract.json, which has it at
"0 9 * * *" (09:00 UTC, early morning in New York, after the night's
threads cross 48 hours). Railway starts the command on the schedule and
expects it to exit; if the previous run is still going when the next is due,
Railway skips the new one rather than start a second. The run waits for its
own batches to end (usually minutes, at most the API's 24 hours) and exits.
If it dies with batches in flight, the next run re-attaches and collects
them before it builds anything (extract_v6 settles 'pending-' submissions,
then re-attaches every submitted batch; their items carry the batch id, so
they are not due and cannot be sent twice). The v6 advisory lock keeps it
and the poller's v6 pass (if on) from running at once; it waits
EXTRACT_LOCK_WAIT for the lock.

Environment (recommended values for the daily job in brackets):
  DATABASE_URL               the database (production)
  EXTRACT_ANTHROPIC_API_KEY  extraction's own key, and no other
  EXTRACT_RUN_USD            required: the cap on one attempt, in dollars. A
                             restart is a new attempt with a new cap [1]. A
                             chunk's worst case is held until its batch is
                             collected (about $0.01 a chunk), so the cap also
                             bounds how much is in flight at once; a day's
                             r/FoodNYC is well under it
  EXTRACT_CEILING_USD        required: the binding total across restarts, on
                             all v6 spend ever, recorded plus in flight;
                             extract_v6.py reads it too. For "spend $N more",
                             set it to the spend on record plus N [the
                             overall budget: spend on record plus what the
                             daily job may spend in all]
  EXTRACT_SINCE              required: the floor on a post's date, one ISO
                             date for every subreddit, SUB=DATE pairs (one for
                             each subreddit taken, SUB=all for no floor), or
                             "all" for none [FoodNYC=2025-06-01]. Required so
                             an unattended run never wanders into the years
                             of r/FoodNYC history left unextracted on purpose
  EXTRACT_SUBREDDITS         optional: comma-separated subreddits (default
                             FoodNYC, subreddits.HOME) [FoodNYC]. The prompt
                             is written for New York; see SPEC.md before
                             adding another city
  EXTRACT_MIN_POST_AGE_HOURS optional: how old a post must be before its
                             thread is touched (default 48) [48]
  EXTRACT_REDO_CUT_BEFORE    optional: an ISO time after the last extraction
                             with the old cut (the deploy of MEMBER_CHARS)
                             [set until the redo is done, then unset]
  EXTRACT_LOCK_WAIT          optional: seconds to wait for the poller's v6
                             pass to let go of the lock (default 900)
  EXTRACT_TRIPWIRE_SEEN      optional: ids of batches whose overrun a person
                             has looked at (comma-separated); until then a
                             run logs NOT STARTING and exits 0, so it is not
                             restarted (room_left)

It refuses to start unless both caps and EXTRACT_SINCE are set, the run's
cap is no more than the ceiling, and the subreddits, floors and age parse.
When the run's cap is more than what the ceiling leaves above recorded
spend, the cap is cut to that and both numbers are logged, so a restart
after a crash resumes with what is left and the ceiling stays
the binding total. Batches still in flight are not taken off the cap here:
the run re-attaches them and holds them against its cap itself, and the
ceiling check inside extract_v6 counts them once. With less than MIN_ROOM
above recorded spend and nothing in flight to collect, it does nothing and
exits 0 ("CEILING REACHED").

Recorded spend is what extraction_state and the batch ledger hold
(extract_v6.spend_on_record). `extract_v6.py --reset-hash` deletes items'
cost along with their rows, so it loosens the ceiling by what they cost:
lower the ceiling to match after a reset.

Exit status, for restartPolicyType ON_FAILURE: 0 when the run finished,
stopped at its cap or at the ceiling, or a spend tripwire fired (a restart
would do no good; the log says which, the tripwire loudly). On a daily
cron a cap stop is a normal end: what is left is the next day's. Anything
else (the API stopping the run, a dropped database, a refused start) is a
failure, and Railway may restart it a few times; the ceiling bounds what
any number of restarts can spend. After a tripwire, the next day's run
finds the overrun on record, does nothing and exits 0, loudly (room_left).
"""

import os
import sys

import anthropic_v6 as AV
import db
import extract_v6 as X

RUN_ENV = "EXTRACT_RUN_USD"
REDO_ENV = "EXTRACT_REDO_CUT_BEFORE"
WAIT_ENV = "EXTRACT_LOCK_WAIT"
LOCK_WAIT = 900
SINCE_ENV = "EXTRACT_SINCE"
SUBS_ENV = "EXTRACT_SUBREDDITS"
AGE_ENV = "EXTRACT_MIN_POST_AGE_HOURS"
SEEN_ENV = "EXTRACT_TRIPWIRE_SEEN"
# A thread is first read once its post is two days old: by then nearly all
# of its comments are in, so it goes out whole, in few chunks.
MIN_POST_AGE_HOURS = 48
# Below this much room under the ceiling a run is not started: no chunk's
# worst case would fit, and a start would only read the database and stop.
MIN_ROOM = 0.05
# extract_v6.main's statuses that end the job for good: done (0), work left
# for another run because the cap or the scope stopped it (3), and a
# tripwire (TRIPPED). A restart repeats none of them usefully.
FINAL = {0: "finished", 3: "stopped at its cap (or by --scope) with work left for the next run",
         X.TRIPPED: "STOPPED BY A SPEND TRIPWIRE"}


def _dollars(name, raw):
    if raw is None or not raw.strip():
        raise SystemExit(f"{name} is not set: an unattended run needs both {RUN_ENV} and {X.CEILING_ENV}")
    try:
        v = float(raw)
    except ValueError:
        raise SystemExit(f"{name} must be a number of dollars, not {raw!r}")
    if not v > 0 or v == float("inf"):
        raise SystemExit(f"{name} must be above zero, not {raw!r}")
    return v


def plan(env):
    """(run cap, ceiling) from the environment, or SystemExit."""
    run = _dollars(RUN_ENV, env.get(RUN_ENV))
    ceiling = _dollars(X.CEILING_ENV, env.get(X.CEILING_ENV))
    if run > ceiling:
        raise SystemExit(f"{RUN_ENV} ${run:.2f} is more than {X.CEILING_ENV} ${ceiling:.2f}")
    return run, ceiling


def selection(env):
    """The extract_v6 arguments that choose the threads, from the
    environment, checked here (with extract_v6's own parsers) so a typo
    refuses the start instead of failing after the lock wait, or SystemExit."""
    raw = env.get(SINCE_ENV)
    if raw is None or not raw.strip():
        raise SystemExit(f"{SINCE_ENV} is not set: an unattended run needs a floor on a post's date "
                         "(an ISO date, SUB=DATE pairs, or 'all' for none)")
    subs = X.parse_subreddits(env.get(SUBS_ENV))
    X.parse_floors(raw, subs)
    age = (env.get(AGE_ENV) or "").strip() or str(MIN_POST_AGE_HOURS)
    try:
        hours = float(age)
    except ValueError:
        raise SystemExit(f"{AGE_ENV} must be a number of hours, not {age!r}")
    X.parse_age(f"{hours!r}h")
    return ["--subreddit", ",".join(subs), "--since", raw.strip(), "--min-post-age", f"{hours:g}h"]


def command(env, cap, ceiling, chosen=None):
    """The extract_v6 argv for a run capped at `cap`; `chosen` is selection(env), when already made."""
    argv = ["--mode", "thread", "--effort", "medium", "--newest-first", "--batch",
            "--max-usd", repr(cap), "--ceiling-usd", repr(ceiling)] + (chosen or selection(env)) \
        + ["--lock-wait", env.get(WAIT_ENV) or str(LOCK_WAIT)]
    redo = (env.get(REDO_ENV) or "").strip()
    if redo:
        argv += ["--redo-cut-before", redo]
    return argv


class Overrun(Exception):
    """A batch cost more than was held for it and nobody has said they looked
    (room_left). Final, like the tripwire that stopped that run: a restart
    would refuse again, so main() exits 0 and says so loudly."""


def overruns(cur, seen=()):
    """Collected v6 batches that cost more than was held for them, other than
    the ids in `seen`: what the tripwire stopped an earlier run for."""
    cur.execute("""select id from extract_batches
                   where version = %s and status = 'collected' and cost_usd > hold_usd + %s
                     and not id = any(%s) order by collected_at""", (X.VERSION, X.TRIP_EPS, list(seen)))
    return [r[0] for r in cur.fetchall()]


def room_left(ceiling, connect=None, seen=()):
    """(what the ceiling leaves above recorded spend, worst case of batches
    in flight), from the database now, as extract_v6's Ceiling counts them. Logged.

    Raises Overrun while a batch's overrun is on record and not
    acknowledged in EXTRACT_TRIPWIRE_SEEN (`seen`). A tripped run exits 0
    so the restart policy leaves it alone, but the cron starts a new one the
    next day; this is what keeps it stopped until a person has looked."""
    conn = (connect or db.connect)()
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            recorded, inflight = X.spend_on_record(cur)
            over = overruns(cur, seen)
    finally:
        conn.close()
    if over:
        raise Overrun(over)
    print(f"ceiling ${ceiling:.2f}: ${recorded:.4f} recorded, ${inflight:.4f} held for batches in flight, "
          f"${ceiling - recorded - inflight:.4f} of room for new work")
    return ceiling - recorded, inflight


def main(env=None, connect=None, run_extract=None):
    env = os.environ if env is None else env
    run, ceiling = plan(env)
    chosen = selection(env)
    try:
        AV.check_prices()
    except AV.PriceMissing as e:
        raise SystemExit(str(e))
    seen = [s.strip() for s in (env.get(SEEN_ENV) or "").split(",") if s.strip()]
    try:
        free, inflight = room_left(ceiling, connect, seen)
    except Overrun as e:
        ids = ", ".join(e.args[0])
        print(f"\n!!!!!!!! NOT STARTING: batch(es) {ids} cost more than was held for them, and a spend tripwire "
              f"stopped that run. A person must look first, then add the id(s) to {SEEN_ENV}. Exiting 0 so "
              "it is not restarted. !!!!!!!!\n", flush=True)
        return 0
    if free < MIN_ROOM and not inflight:
        print(f"\nCEILING REACHED: ${free:.4f} left under {X.CEILING_ENV} ${ceiling:.2f}; nothing to run. "
              "Raise the ceiling to go on.", flush=True)
        return 0
    # With batches in flight the run goes ahead even with no room, to
    # collect them; the ceiling inside keeps it from sending anything new.
    cap = min(run, max(free, MIN_ROOM))
    if cap < run:
        # A restart after a crash, or a run started with spend already on
        # record: it gets what is left, and the ceiling stays the total.
        print(f"\n!!!!!!!! {RUN_ENV} ${run:.2f} is more than the ${free:.4f} {X.CEILING_ENV} ${ceiling:.2f} "
              f"leaves above recorded spend: this run's cap is cut to ${cap:.4f} !!!!!!!!\n", flush=True)
    argv = command(env, cap, ceiling, chosen)
    print("extract_v6.py " + " ".join(argv), flush=True)
    code = (run_extract or X.main)(argv) or 0
    if code in FINAL:
        line = f"extraction run {FINAL[code]} (extract_v6 exit {code}); exiting 0 so it is not restarted"
        print(("\n!!!!!!!! " + line + " !!!!!!!!") if code == X.TRIPPED else line, flush=True)
        return 0
    print(f"extraction run failed (extract_v6 exit {code})", flush=True)
    return code


if __name__ == "__main__":
    # Railway reads stdout as it comes; Python would hold a pipe's output back.
    sys.stdout.reconfigure(line_buffering=True)
    sys.exit(main())
