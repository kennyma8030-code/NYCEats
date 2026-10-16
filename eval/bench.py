"""Benchmark models x prompts x modes on the eval sets in one command.

    python eval/bench.py --model haiku-5.5 --prompt "file:eval/prompts/v5_{mode}.py,current" \
        --modes comment,thread --sets v1,v2 --repeat 3
    python eval/bench.py --model haiku-5.5,deepseek-v4-flash --prompt current --dry-run
    python eval/bench.py --score-only --model haiku-5.5 --prompt current     # no calls, just the table

For every model x prompt x mode it makes the calls that are missing from the
run file (run.py's cache, so an interrupted bench resumes and --repeat only
adds repetitions), then scores every run with score_v5 and writes ONE
comparison table to eval/results/<date>__bench__<name>.md and .csv, next to
the baselines: deepseek-v4-flash on the current prompt ("revised") and on the
prompts production ran ("original"), and production's stored output.

`{mode}` in a prompt spec is replaced by comment or thread, so one spec names
both v5 files. A run file serves both sets: v1 and v2 share comments, and a
call already made for one is not made again for the other.

Before any live call it prints an estimated cost from OpenRouter's price list
(or Anthropic's, on that API), and refuses to start above --max-cost unless
--yes is given. A refused key stops the whole bench at the first call.

The table compares rows on the comments EVERY row covered (score_v5's `only`),
because a baseline that ran on fewer comments would otherwise be compared on
different ones. Each new run also gets its own full report on everything it
covered.
"""

import argparse
import csv
import datetime
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import providers  # noqa: E402
import run as R  # noqa: E402
import score as S  # noqa: E402
import score_v5 as SV  # noqa: E402

PROMPT_NAMES = {"1d5bac550078": "original", "ca5439be83b3": "original",
                "0d75b20b5f83": "revised", "5b02ac883c80": "revised",
                "3a6940dd5cc1": "rubric_v1", "bd4467215908": "rubric_v1"}
BASELINES = [  # (label, mode, path), all deepseek-v4-flash or production's stored output
    ("deepseek-v4-flash / revised (current)", "comment", "runs/deepseek_deepseek-v4-flash__0d75b20b5f83__comment.jsonl"),
    ("deepseek-v4-flash / original (production's prompt)", "comment", "runs/deepseek_deepseek-v4-flash__1d5bac550078__comment.jsonl"),
    ("deepseek-v4-flash / revised (current)", "thread", "runs/deepseek_deepseek-v4-flash__5b02ac883c80__thread.jsonl"),
    ("deepseek-v4-flash / original (production's prompt)", "thread", "runs/deepseek_deepseek-v4-flash__ca5439be83b3__thread.jsonl"),
]
STORED = {"v1": "baseline/production__stored__all.jsonl", "v2": "baseline/production__stored__v2.jsonl"}
CHARS_PER_TOKEN = 3.5
# Output tokens per call when the model has no earlier run to learn from.
# Deliberately high: reasoning models spend most of their output thinking.
DEFAULT_OUT = {"comment": 700, "thread": 7000}
TABLE = ["drop_rate", "mention_recall", "negative_mention_recall", "value_complaint_recall",
         "dish_negative_recall", "sign_accuracy", "levels_used", "mention_precision",
         "reference_only_recall", "reference_only_precision", "bare_endorsement_recall",
         "bare_endorsement_precision", "is_negated_recall", "experience_acc", "price_exact_acc",
         "dishes_disliked_recall", "dishes_liked_recall", "judgment_question_acc"]
HEALTH = ["refused_inputs", "parse_failure_rate", "repairs_per_100_mentions", "bad_id_rate", "cost_per_1k_comments",
          "latency_p50", "cache_read_share"]


def prompt_label(spec, ph):
    if ph in PROMPT_NAMES:
        return PROMPT_NAMES[ph]
    if spec.startswith("file:"):
        base = os.path.basename(spec[5:]).removesuffix(".py")
        for suffix in ("_comment", "_thread"):
            base = base.removesuffix(suffix)
        return base
    return spec


GOLD_OVERRIDE = {}


def set_paths(name):
    st = SV.SETS[name]
    return GOLD_OVERRIDE.get(name, st["gold"]), st["items"], st["stats"]


def plan_run(model, api, spec, mode, sets, args, opts):
    pmod, _ = R.load_prompt(spec.replace("{mode}", mode), mode)
    system = pmod.SYSTEM_PROMPT
    ph = R.prompt_hash(system)
    jobs = {}
    for name in sets:
        _, items_path, _ = set_paths(name)
        for j in R.build_jobs(R.load_items(items_path), mode, pmod, custom=spec.startswith("file:")):
            if j["call_key"] in jobs:
                jobs[j["call_key"]]["item_ids"] += [i for i in j["item_ids"] if i not in jobs[j["call_key"]]["item_ids"]]
            else:
                jobs[j["call_key"]] = j
    jobs = list(jobs.values())
    if args.limit:
        jobs = jobs[:args.limit]
    out = R.run_path(model, ph, mode, R.config_tag(opts, args.tag))
    done = R.cached_calls(out)
    todo = [(j, rep) for rep in range(args.repeat) for j in jobs if (j["call_key"], rep) not in done]
    return {"model": model, "api": api, "spec": spec, "mode": mode, "system": system, "ph": ph,
            "label": f"{model} / {prompt_label(spec.replace('{mode}', mode), ph)} ({ph})",
            "jobs": jobs, "todo": todo,
            "out": out, "cached": len(done)}


def learned_tokens(model, mode):
    """Mean (prompt, completion) tokens per call from this model's earlier
    runs in this mode, if any."""
    slug = model.replace("/", "_").replace(":", "_")
    pt, ct = [], []
    runs_dir = os.path.join(HERE, "runs")
    for name in os.listdir(runs_dir) if os.path.isdir(runs_dir) else []:
        if name.startswith(slug + "__") and f"__{mode}" in name:
            for r in S.load_jsonl(os.path.join(runs_dir, name)):
                u = r.get("usage") or {}
                if not r.get("error") and u.get("completion_tokens"):
                    pt.append(u.get("prompt_tokens") or 0)
                    ct.append(u["completion_tokens"])
    return (statistics.fmean(pt), statistics.fmean(ct)) if ct else (None, None)


def estimate(plan, cat):
    """Rough dollars for a plan's missing calls. The system prompt is billed
    once as a cache write and then as cache reads where the provider caches
    it, in full otherwise."""
    p = providers.prices(plan["api"], plan["model"], cat)
    if p is None or not plan["todo"]:
        return None if p is None else 0.0, None
    pin, pout, pread, pwrite = p
    _, learned_out = learned_tokens(plan["model"], plan["mode"])
    out_tok = learned_out or DEFAULT_OUT[plan["mode"]]
    sys_tok = len(plan["system"]) / CHARS_PER_TOKEN
    total = 0.0
    cached = R.caches_prompt(plan["api"], plan["model"])
    for i, (j, _) in enumerate(plan["todo"]):
        user_tok = len(j["user"]) / CHARS_PER_TOKEN
        sys_cost = sys_tok * ((pwrite if i == 0 else pread) if cached else pin)
        total += sys_cost + user_tok * pin + out_tok * pout
    return total, out_tok


def score_set(gold, items, stats, rows, args, alias, excluded):
    """rows: [(label, mode, Run)]. Returns per mode (n common comments, rows)."""
    gold_cids = {g["comment_id"] for g in gold}
    tables = {}
    for mode in ("comment", "thread"):
        mrows = [(label, run) for label, m, run in rows if m in (mode, "stored")]
        if not any(m == mode for _, m, _ in rows):
            continue
        # Every rep of every row is scored on the same comments: those that
        # all of them covered.
        common = set(gold_cids)
        for _, run in mrows:
            common &= run.covered_all_reps()
        out = []
        for label, run in mrows:
            per_rep, flips = SV.evaluate(gold, items, run, alias, excluded, args.drop_chains, stats, only=common)
            out.append((label, run, per_rep, flips))
        tables[mode] = (len(common), out)
    return tables


def mean_cell(per_rep, scope, metric):
    vals = [r[scope].get(metric) for r in per_rep if scope in r]
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        other = [r[scope].get(metric) for r in per_rep if scope in r]
        return other[0] if other else None, None
    return statistics.fmean(vals), (statistics.pstdev(vals) if len(vals) > 1 else None)


def write_tables(results, args):
    date = datetime.date.today().isoformat()
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"{date}__bench__{args.name}.md")
    csv_path = os.path.join(out_dir, f"{date}__bench__{args.name}.csv")
    lines = [f"# Bench {args.name}", "",
             "Rows are compared on the comments every row in the table covered. Scope is `reweighted` "
             "(the population estimate) where the set has strata, else `overall`. Values are the mean "
             "across reps; ± is the sd across reps. Old-schema rows are read through the adapter, so their "
             "reference_only numbers are derived (see eval/schema_v5.md).", ""]
    rows_csv = []
    for set_name, tables in results.items():
        for mode, (n_common, rows) in tables.items():
            lines += [f"## {set_name} / {mode} mode ({n_common} common comments)", ""]
            if not rows:
                continue
            # The population estimate covers single comments only, so a table
            # of whole-thread comments falls back to the plain overall scope.
            r0 = rows[0][2][0]
            scope = "reweighted" if (r0.get("reweighted") or {}).get("comments") else "overall"
            lines[-2] += f", scope {scope}"
            head =["row", "schema", "reps"] + TABLE + HEALTH
            lines += ["| " + " | ".join(head) + " |", "|---" * len(head) + "|"]
            for label, run, per_rep, flips in rows:
                h = SV.run_health(run)
                cells = [label, h["schema"], str(len(per_rep))]
                for m in TABLE:
                    v, sd = mean_cell(per_rep, scope, m)
                    cells.append(SV.fmt(v) + (f"±{sd:.3f}" if sd else ""))
                    rows_csv.append([set_name, mode, label, scope, m, v, sd])
                for m in HEALTH:
                    cells.append(SV.fmt(h[m]))
                    rows_csv.append([set_name, mode, label, "run", m, h[m], None])
                lines.append("| " + " | ".join(cells) + " |")
                if flips is not None:
                    rows_csv.append([set_name, mode, label, scope, "flip_rate", flips, None])
            lines.append("")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["set", "mode", "row", "scope", "metric", "mean", "sd"])
        w.writerows(rows_csv)
    return md_path, csv_path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="", help="comma list: aliases, Anthropic ids or OpenRouter slugs (none: baselines only)")
    ap.add_argument("--prompt", default="current", help="comma list of run.py prompt specs; {mode} is substituted")
    ap.add_argument("--modes", default="comment,thread")
    ap.add_argument("--sets", default="v1,v2")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--workers", type=int, default=8, help="parallel calls per run")
    ap.add_argument("--limit", type=int, help="at most N distinct calls per run (smoke tests)")
    ap.add_argument("--api", choices=["auto", "openrouter", "anthropic"], default="auto")
    ap.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--thinking", choices=["adaptive", "disabled", "between_tools"])
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int)
    ap.add_argument("--provider", help="comma list; pins OpenRouter routing")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--tag", default="")
    ap.add_argument("--max-cost", type=float, default=1.0, help="dollars; above this, live runs need --yes")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="plan and estimate only, no calls, no scoring")
    ap.add_argument("--score-only", action="store_true", help="no calls; score what the run files hold")
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--baseline", action="append", default=[], help="extra run file to include (label=path or path)")
    ap.add_argument("--drop-chains", action="store_true")
    ap.add_argument("--gold", action="append", default=[], help="SET=PATH, a gold file other than the default")
    ap.add_argument("--name", default=None, help="result file name (default: models and prompts)")
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    args = ap.parse_args()
    for g in args.gold:
        name, _, path = g.partition("=")
        GOLD_OVERRIDE[name] = path

    if hasattr(sys.stdout, "reconfigure"):   # comments carry curly quotes; a Windows console is cp1252
        sys.stdout.reconfigure(errors="replace")
    providers.load_env()
    models = [m.strip() for m in args.model.split(",") if m.strip()]
    specs = [p.strip() for p in args.prompt.split(",") if p.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    sets = [s.strip() for s in args.sets.split(",") if s.strip()]
    args.name = args.name or "_".join(m.replace("/", "-") for m in models) or "baselines"
    opts = {"temperature": args.temperature, "max_tokens": args.max_tokens, "provider": args.provider,
            "effort": args.effort, "thinking": args.thinking, "timeout": args.timeout}

    plans = []
    for model in models:
        api, model_id = providers.resolve(model, args.api)
        providers.check_opts(api, opts)
        for spec in specs:
            for mode in modes:
                plans.append(plan_run(model_id, api, spec, mode, sets, args, opts))

    cat = providers.catalog()
    total, unknown = 0.0, []
    print(f"{'run':70s} {'calls':>6s} {'cached':>6s} {'est $':>8s}")
    for p in plans:
        est, out_tok = estimate(p, cat)
        if est is None:
            unknown.append(p["label"])
        else:
            total += est
        print(f"{p['api'] + ':' + p['label'] + ' / ' + p['mode']:70.70s} {len(p['todo']):6d} {p['cached']:6d} "
              f"{('?' if est is None else f'{est:8.4f}'):>8s}")
    print(f"estimated total ${total:.4f}" + (f" (+ unknown price for {len(unknown)} runs)" if unknown else "")
          + " -- rough: output length is guessed from earlier runs or set high")

    live = [p for p in plans if p["todo"]]
    if args.dry_run:
        for p in live[:1]:
            j = p["todo"][0][0]
            print("=" * 80, f"\nfirst call of {p['label']} / {p['mode']}: {j['call_key']}\n{j['user'][:1200]}")
        return
    if live and not args.score_only:
        if (total > args.max_cost or unknown) and not args.yes:
            raise SystemExit(f"estimated ${total:.2f} is above --max-cost ${args.max_cost:.2f} "
                             f"(or a price is unknown); re-run with --yes to proceed")
        for p in live:
            providers.require_key(p["api"])
        for p in live:
            print(f"running {p['api']}:{p['label']} / {p['mode']}: {len(p['todo'])} calls -> {p['out']}")
            R.print_stats(R.execute(p["todo"], p["model"], p["system"], p["ph"], p["mode"], opts,
                                    p["api"], p["out"], args.workers))

    alias, excluded = S.load_map("alias_overrides.json"), S.load_map("excluded_entities.json")
    results = {}
    for name in sets:
        gold_path, items_path, stats = set_paths(name)
        if not os.path.exists(gold_path):
            print(f"skipping scoring on {name}: no v5 gold at {gold_path}", file=sys.stderr)
            continue
        items, gold = S.load_jsonl(items_path), S.load_jsonl(gold_path)
        rows = []
        for p in plans:
            if os.path.exists(p["out"]):
                run = SV.Run(p["out"], items)
                rows.append((p["label"], p["mode"], run))
                per_rep, flips = SV.evaluate(gold, items, run, alias, excluded, args.drop_chains, stats)
                md, _ = SV.report(run, per_rep, flips, args.out, f"__{name}")
                print(f"  full report: {md}")
        if not args.no_baseline:
            mine = {os.path.normcase(os.path.abspath(p["out"])) for p in plans}
            for label, mode, rel in BASELINES:
                path = os.path.join(HERE, rel)
                if os.path.normcase(os.path.abspath(path)) in mine:
                    continue
                if mode in modes and os.path.exists(path):
                    rows.append((label, mode, SV.Run(path, items)))
            stored = os.path.join(HERE, STORED[name])
            if os.path.exists(stored):
                rows.append(("production / stored output (mixed modes)", "stored", SV.Run(stored, items)))
        for extra in args.baseline:
            label, _, path = extra.rpartition("=")
            run = SV.Run(path, items)
            rows.append((label or os.path.basename(path), run.mode, run))
        results[name] = score_set(gold, items, stats, rows, args, alias, excluded)
    if results:
        md, cs = write_tables(results, args)
        print(f"comparison: {md}\n            {cs}")


if __name__ == "__main__":
    main()
