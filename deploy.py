"""Switch the Railway worker between polling only and polling + inference.

    python deploy.py status                 what the worker is set to do
    python deploy.py poll                   collect comments only
    python deploy.py poll+extract           collect, extract new ones, refresh the board
    python deploy.py poll+extract --days 2 --limit 500 --workers 8
    python deploy.py poll+extract --dry-run say what would change

The worker's start command never changes (railway.json: `python poller.py`).
The mode is carried by service variables that poller.py reads as defaults,
so switching is a variable change plus one redeploy, not a config edit.

poll+extract copies the extraction provider from the local .env -- the URL,
the model, and the key that URL needs -- so production calls the same model
this machine does. The key goes over stdin, never on a command line.

Railway builds from origin/main. Until the poller change is merged there,
setting POLL_EXTRACT does nothing; this says so rather than pretend.
"""

import argparse
import os
import shutil
import subprocess
import sys

import extract       # imports db, which loads .env; reads the provider config

SERVICE = "NYCEats"
MODE_VARS = ("POLL_EXTRACT", "POLL_EXTRACT_DAYS", "POLL_EXTRACT_LIMIT",
             "POLL_EXTRACT_WORKERS", "LLM_API_URL", "LLM_MODEL")


def railway(*args, stdin=None, capture=True):
    exe = shutil.which("railway")
    if not exe:
        raise SystemExit("railway CLI not found -- npm i -g @railway/cli, then railway login")
    r = subprocess.run([exe, *args], input=stdin, text=True,
                       capture_output=capture)
    if r.returncode:
        raise SystemExit(f"railway {' '.join(args[:2])} failed:\n{r.stderr or r.stdout}")
    return r.stdout


def remote_vars(service):
    out = railway("variable", "list", "--service", service, "--kv")
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def main_has_poller_change():
    """True if origin/main's poller.py knows about POLL_EXTRACT."""
    subprocess.run(["git", "fetch", "-q", "origin", "main"], capture_output=True)
    r = subprocess.run(["git", "show", "origin/main:poller.py"],
                       capture_output=True, text=True)
    return r.returncode == 0 and "POLL_EXTRACT" in r.stdout


def status(service):
    v = remote_vars(service)
    on = v.get("POLL_EXTRACT", "0") not in ("", "0", "false", "no")
    print(f"{service}: {'poll + extract' if on else 'poll only'}")
    if on:
        url = v.get("LLM_API_URL", extract.API_URL)
        key = "OPENROUTER_API_KEY" if "openrouter" in url else "DEEPSEEK_API_KEY"
        print(f"  model    {v.get('LLM_MODEL', extract.MODEL)} via {url}")
        print(f"  key      {key} {'set' if v.get(key) else 'MISSING -- the worker will not boot'}")
        print(f"  window   last {v.get('POLL_EXTRACT_DAYS', '3')} days, "
              f"<= {v.get('POLL_EXTRACT_LIMIT', '1000')} per 30-min cycle, "
              f"{v.get('POLL_EXTRACT_WORKERS', '8')} workers")
    if not main_has_poller_change():
        print("\n  note: origin/main's poller.py predates POLL_EXTRACT, so the running "
              "worker ignores it.\n        Merge this branch to main for the mode to take effect.")


def apply(service, want, dry_run):
    """Set the variables, then redeploy once rather than once per variable."""
    plain = {k: v for k, v in want.items() if k != extract.API_KEY_VAR}
    for k, v in plain.items():
        print(f"  {k}={v}")
    if extract.API_KEY_VAR in want:
        print(f"  {extract.API_KEY_VAR}=<from local .env>")
    if dry_run:
        print("\ndry run -- nothing changed")
        return

    railway("variable", "set", *[f"{k}={v}" for k, v in plain.items()],
            "--service", service, "--skip-deploys")
    if extract.API_KEY_VAR in want:
        railway("variable", "set", extract.API_KEY_VAR, "--stdin",
                "--service", service, "--skip-deploys", stdin=want[extract.API_KEY_VAR])
    railway("redeploy", "--service", service, "--yes")
    print(f"\nredeploying {service}; watch it boot with: railway logs --service {service}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("mode", choices=("status", "poll", "poll+extract"))
    ap.add_argument("--service", default=SERVICE)
    ap.add_argument("--days", type=int, default=3,
                    help="only extract comments younger than this (default 3)")
    ap.add_argument("--limit", type=int, default=1000,
                    help="max extractions per 30-minute cycle (default 1000)")
    ap.add_argument("--workers", type=int, default=8,
                    help="concurrent model calls (default 8)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.mode == "status":
        return status(args.service)

    if args.mode == "poll":
        print(f"{args.service} -> poll only")
        return apply(args.service, {"POLL_EXTRACT": "0"}, args.dry_run)

    key = os.environ.get(extract.API_KEY_VAR)
    if not key:
        raise SystemExit(f"{extract.API_KEY_VAR} is not in the local .env, "
                         f"so there is nothing to give the worker for {extract.API_URL}")
    if not main_has_poller_change():
        print("warning: origin/main's poller.py predates POLL_EXTRACT. The variables "
              "will be set,\n         but inference starts only once this branch is "
              "merged and deployed.\n", file=sys.stderr)
    print(f"{args.service} -> poll + extract ({extract.MODEL})")
    apply(args.service, {
        "POLL_EXTRACT": "1",
        "POLL_EXTRACT_DAYS": str(args.days),
        "POLL_EXTRACT_LIMIT": str(args.limit),
        "POLL_EXTRACT_WORKERS": str(args.workers),
        "LLM_API_URL": extract.API_URL,
        "LLM_MODEL": extract.MODEL,
        extract.API_KEY_VAR: key,
    }, args.dry_run)


if __name__ == "__main__":
    main()
