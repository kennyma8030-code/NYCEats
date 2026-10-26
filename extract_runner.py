"""An unattended thread-mode extraction run, for a Railway service of its own.

    python extract_runner.py

Started by railway.extract.json in a dedicated service, never by the NYCEats
service (its railway.json starts the poller, and a second poller must never
run). Railway's API no longer lets a service point at another config file,
so the service is deployed with `railway up` from a staging copy of the repo
whose railway.json has been replaced by railway.extract.json. Like every
pipeline script it writes to DATABASE_URL, so it is started on purpose, one
run at a time; nothing redeploys it on a push to main (watchPatterns name
only its own config, should the service ever be linked to the repo).

What it runs, in one extract_v6.py invocation sharing one cap and ceiling:
the redo of comments cut at 1,500 characters first when
EXTRACT_REDO_CUT_BEFORE is set, then the backlog:

    extract_v6.py --mode thread --effort medium --newest-first --batch
                  --max-usd $EXTRACT_RUN_USD --ceiling-usd $EXTRACT_CEILING_USD
                  [--redo-cut-before $EXTRACT_REDO_CUT_BEFORE] --lock-wait $EXTRACT_LOCK_WAIT

Environment:
  DATABASE_URL               the database (production)
  EXTRACT_ANTHROPIC_API_KEY  extraction's own key, and no other
  EXTRACT_RUN_USD            required: the cap on one attempt, in dollars. A
                             restart is a new attempt with a new cap
  EXTRACT_CEILING_USD        required: the binding total across restarts, on
                             all v6 spend ever, recorded plus in flight;
                             extract_v6.py reads it too. For "spend $N more",
                             set it to the spend on record plus N
  EXTRACT_REDO_CUT_BEFORE    optional: an ISO time after the last extraction
                             with the old cut (the deploy of MEMBER_CHARS)
  EXTRACT_LOCK_WAIT          optional: seconds to wait for the poller's v6
                             pass to let go of the lock (default 900)

It refuses to start unless both caps are set and the run's cap is no more
than the ceiling. When the run's cap is more than what the ceiling leaves
above recorded spend, the cap is cut to that and both numbers are logged,
so a restart after a crash resumes with what is left and the ceiling stays
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
would do no good; the log says which, the tripwire loudly). Anything else
(the API stopping the run, a dropped database, a refused start) is a
failure, and Railway may restart it a few times; the ceiling bounds what
any number of restarts can spend.
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
# Below this much room under the ceiling a run is not started: no chunk's
# worst case would fit, and a start would only read the database and stop.
MIN_ROOM = 0.05
# extract_v6.main's statuses that end the job for good: done (0), work left
# for another run because the cap or the scope stopped it (3), and a
# tripwire (TRIPPED). A restart repeats none of them usefully.
FINAL = {0: "finished", 3: "stopped at its cap (or by --scope) with work left for another run",
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


def command(env, cap, ceiling):
    """The extract_v6 argv for a run capped at `cap`."""
    argv = ["--mode", "thread", "--effort", "medium", "--newest-first", "--batch",
            "--max-usd", repr(cap), "--ceiling-usd", repr(ceiling), "--lock-wait", env.get(WAIT_ENV) or str(LOCK_WAIT)]
    redo = (env.get(REDO_ENV) or "").strip()
    if redo:
        argv += ["--redo-cut-before", redo]
    return argv


def room_left(ceiling, connect=None):
    """(what the ceiling leaves above recorded spend, worst case of batches
    in flight), from the database now, as extract_v6's Ceiling counts them. Logged."""
    c = X.Ceiling(ceiling, connect or db.connect)
    try:
        recorded, inflight = c.read()
    finally:
        c.close()
    print(f"ceiling ${ceiling:.2f}: ${recorded:.4f} recorded, ${inflight:.4f} held for batches in flight, "
          f"${ceiling - recorded - inflight:.4f} of room for new work")
    return ceiling - recorded, inflight


def main(env=None, connect=None, run_extract=None):
    env = os.environ if env is None else env
    run, ceiling = plan(env)
    try:
        AV.check_prices()
    except AV.PriceMissing as e:
        raise SystemExit(str(e))
    free, inflight = room_left(ceiling, connect)
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
    argv = command(env, cap, ceiling)
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
