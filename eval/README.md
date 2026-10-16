# Extraction eval

This is a gold-standard set for benchmarking the mention extractor, across
models, prompts and modes. It was labeled by reading the comments directly,
never by an LLM.

## Layout

Each eval set has its own folder holding its items, gold, labels and the
script that built it, so a set can be read without the rest. Everything else
is either harness code, shared data, prompts, docs or output.

```
eval/
  README.md  STATUS.md   this index, and what is done and what is next
  bench.py               benchmark models x prompts x modes in one command
  run.py                 run one model x prompt x mode over a set, caching to runs/
  score.py               score runs against the v1 gold (and the library the others import)
  score_v5.py            score any run (v5 or old schema) against the v5 gold
  _paths.py              where eval/ lives; every script imports it to find lib/ and the other modules
  lib/                   modules the entry points import: providers.py, schema_v5.py,
                         budget.py (the $6-per-key spend cap and its ledger)
  tools/                 one-off tools: export_stored, adjudicate, compare, reparse,
                         report, selftest_v5 (offline checks of the v5 harness),
                         selftest_budget (offline checks of the spend cap)
  .spend/                the spend ledger, one file per key (gitignored)
  prompts/               extraction prompts run.py loads: v5_*.py, rubric_v1_*.py,
                         v3_prompt.md, and check_v5.py, which validates v5's examples
  data/                  alias_overrides.json and excluded_entities.json, production's
                         lists, used to key and filter mentions in every set
  v1/                    the headline set: items.jsonl, gold.jsonl, gold_v5.jsonl,
                         labels/ (the blind labels), build_items.py, sampling.md,
                         gold_changes.md, and packet.py for blind labeling packets
  v2/                    the diagnostic set: taxonomy.md, items, gold, gold_v5.jsonl,
                         builder, top-up miner and top-up labels
  v4/                    a separate, self-contained protocol with its own README,
                         selftest and rounds; see v4/README.md
  gold_v5/               how v1 and v2 gold became v5 gold: convert_gold_v5.py,
                         the hand decisions in overrides.py and threads.py, and audits
  docs/                  schema_v5.md (the v5 contract), gold_rules.md (how the gold was
                         labeled, what each field means), scoring.md (what score.py reports)
  runs/                  run files: <model>__<prompthash>__<mode>.jsonl (never rename or edit)
  results/               scored output: <date>__<run>.md/.csv and comparison tables
  baseline/              the ORIGINAL extraction as run files, its scores and disagreements
```

The entry points stay at the top so the commands you type often are short.
`runs/` stays where it is because resume logic reads run files by name.
`gold_v5/` is separate from the sets because it reads both v1 and v2 and
writes each set's `gold_v5.jsonl` back into that set's own folder.

**No eval comment may ever be used as a prompt example.** Doing so silently
inflates every later score.

## Benchmark any model

`bench.py` runs every model × prompt × mode you name, on v1 and v2, and makes
only the calls missing from the run files, so interrupted runs resume. It
then writes one comparison table to `results/<date>__bench__<name>.md`. The
table puts the new runs next to the baselines: deepseek-v4-flash on the
current and original prompts, and production's stored output. Each new run
also gets a full report. Scoring uses `score_v5.py`, so old-prompt runs and
v5 runs are judged by the same rules (`docs/schema_v5.md`).

```bash
# Haiku 5.5, v5 prompts against the current ones, both modes, both sets, 3 reps
python eval/bench.py --model haiku-5.5 --prompt "file:eval/prompts/v5_{mode}.py,current" \
    --modes comment,thread --sets v1,v2 --repeat 3

python eval/bench.py --model haiku-5.5 --prompt "file:eval/prompts/v5_{mode}.py" --dry-run   # plan + cost estimate
python eval/bench.py --model haiku-5.5,gemini-3.8-flash --prompt current --limit 5 --yes      # smoke test
python eval/bench.py --score-only                                                             # baselines only
python eval/score_v5.py eval/runs/<run>.jsonl [--set v2]                                      # one run, full report
python eval/bench.py --budget --model haiku-5.5                                               # spend so far, what's left
python eval/bench.py --budget-set-spent 1.23 --model haiku-5.5                                # copy in the console figure
python eval/tools/selftest_v5.py                                                                    # offline checks
python eval/tools/selftest_budget.py                                                                # spend-cap checks
```

- **Spend cap.** No command spends more than $6 on one key
  (`HARD_CAP_USD` in `lib/budget.py`; `--cap` or `EVAL_BUDGET_CAP_USD` may
  lower it for a run, never raise it, and `--yes` never lifts it).
  - **The ledger:** an Anthropic key has no usage endpoint, so what has been
    spent is kept in `eval/.spend/<hash of the key>.json`, rewritten after
    every call, counting failed attempts that may still have billed. It only
    sees spend from this harness on this machine. Seed or correct it from the
    Anthropic console with `--budget-set-spent`; lowering it needs `--yes`.
    Nothing resets it, and an unreadable ledger stops the run.
  - **Before a run:** the bench prints the expected cost and a pessimistic
    one (every input byte counted as a token, every answer at `max_tokens`),
    and refuses when the pessimistic cost is above what's left. `--partial`
    runs anyway in spend order: rows as given, comment before thread, v1
    before v2, one rep of everything before the next. The cap stops it.
  - **During a run:** each call's worst case is reserved before it is sent,
    so parallel calls can't overshoot. When the next call doesn't fit, the
    calls in flight finish, everything is written, and the command exits
    non-zero. Re-running it later resumes without repeating a paid call.
  - **max_tokens** is always sent: 8,000 in comment mode and 16,000 in
    thread mode by default, about 3-4x the largest gold answer, leaving room
    for Haiku 5.5's default thinking, which counts inside it.

- **Models.** Use an alias (`haiku-5.5`, `sonnet-5.5`, `deepseek-v4-flash`,
  … see `lib/providers.py`'s `ALIASES`), an Anthropic id (`claude-haiku-5-5`) or any
  OpenRouter slug.
  - **Provider choice:** Claude models go to Anthropic's API when
    `ANTHROPIC_API_KEY` is set (it needs `pip install anthropic`), and
    through OpenRouter otherwise. `--api` forces one.
  - **Keys:** read from the environment, or from `.env` in this checkout or
    in the main checkout.
- **Cost.** The system prompt is marked for caching on Claude models, and
  the first call of a run goes alone so later calls read the cache instead
  of all writing it. Before any live call, the bench prints an estimated
  cost and asks for `--yes` above `--max-cost` (default $1). That is a
  confirmation only; the spend cap above is separate.
- **Refused key.** A 401 or 402, a 403 that names the key (spend limit,
  credit), or Anthropic's out-of-credit error stops the whole bench at once.
  Nothing is written for the refused call, so a re-run after topping up
  resumes cleanly.
- **Refused input.** Any other 403, such as OpenRouter moderation flagging
  one comment, becomes a single error row. Resume does not retry it. It
  scores as a dropped comment and is counted as `refused_inputs`.
- **Settings in the file name.** `--effort` and `--thinking` change the
  output, so they become part of the run file name.
  - `--thinking` is only sent on Anthropic's API and is refused on
    OpenRouter, where `--effort` is the control.
  - Current Claude models reject `temperature`, on either provider, so it is
    only sent where the model accepts it.
- **Common-comment comparison.** The table compares rows only on the
  comments every row covered.
  - **Complete reps only:** a rep counts only if it covers everything that
    row's rep 0 covered. Shorter reps (an interrupted `--repeat`) are left
    out and shown as "reps used k of n", so they can't shrink everyone's
    comments.
  - **Short rep 0:** if a row's rep 0 is itself short (a call it tried never
    settled, or a planned call was never made), the row stays and is flagged
    "rep 0 partial".
  - **Cost per 1k comments** is counted over the set's own calls.
  - **Before v5 gold exists**, pass `--gold v1=PATH --gold v2=PATH`.

## Running

```bash
# 0. (done) sample, using a read-only DB url; rebuild gold from v1/labels/ (+ adjudication patches)
EVAL_DB_URL=postgresql://... python eval/v1/build_items.py
python eval/v1/labels/build_gold.py

# 1. run a model (OpenRouter). Resumable; --repeat adds repetitions.
export OPENROUTER_API_KEY=...
python eval/run.py --model deepseek/deepseek-v4-flash --mode thread --prompt git:0ea62ff~1
python eval/run.py --model some/model --mode comment --prompt file:eval/prompts/rubric_v1_comment.py --repeat 3
python eval/run.py --model some/model --mode thread --dry-run --limit 3      # no API call
python eval/run.py --model some/model --mode comment --items eval/v2/items.jsonl --tag v2

# 2. score on v1 (the headline). --drop-chains mirrors production's chain filter.
python eval/score.py eval/runs/<model>__<prompthash>__<mode>.jsonl
python eval/score.py eval/runs/*.jsonl --drop-chains

# 3. score on v2 (diagnostic: one column per weakness, plus split_dev / split_test)
python eval/score.py eval/runs/<run>.jsonl --gold eval/v2/gold.jsonl --items eval/v2/items.jsonl --stats '' --tag __v2

# the ORIGINAL extraction (already exported and scored in eval/baseline/)
EVAL_DB_URL=... python eval/tools/export_stored.py
EVAL_DB_URL=... python eval/tools/export_stored.py --items eval/v2/items.jsonl --name production__stored__v2
python eval/score.py eval/baseline/production__stored__all.jsonl --drop-chains --out eval/baseline/results

python eval/score.py --self-test          # gold scored against itself must be perfect
```

`--prompt git:0ea62ff~1` gives the prompts production actually ran:
`1d5bac550078` (comment) and `ca5439be83b3` (thread). `current` gives
`0d75b20b5f83` / `5b02ac883c80`. Run files are named
`<model>__<prompthash>__<mode>.jsonl`.

## Sets

**v2** is the diagnostic set. It is built; see `v2/taxonomy.md`. It has 481 comments across 18 weaknesses, each
with at least 25 items: 244 confirmed failures of the original model plus
237 blind-labeled top-ups. The split is fixed: dev 246, test 235. v2 is
diagnostic only, because it leans toward the original model's failures, so
the headline comparison stays on **v1, reweighted**. Never use a v1 or v2
comment as a prompt example.

**v1** is 395 single comments and 17 whole threads (374 comments), with the
exact model input for both modes. Its gold is 769 comments and 825 mentions.
`v1/sampling.md` says how the items were chosen. The gold's own labeling rules
are in `docs/gold_rules.md`, and what the scorer reports is in `docs/scoring.md`.
**v4** is described in `v4/README.md`.
