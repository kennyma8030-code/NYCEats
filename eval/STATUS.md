# Status (2026-10-03)

## Done

- **Sampling** (`build_items.py`, `items.jsonl`, `sampling.md`): 395 single
  comments (295 risk-targeted across 9 groups, 100 random) and 17 whole
  threads (374 comments), with comment- and thread-mode inputs rendered by
  the repo's own builders. The source is the local dev snapshot
  (localhost:5433, data through 2026-09-26), not production; see
  sampling.md.
- **Gold, first 50 single comments** (`gold.jsonl`, source
  `labels/batch01.py`): c0001–c0050, five from each draw group. That is 80
  mentions, 29 comments with at least one required mention, and 21 with
  none. Labeling was blind.
- **Scaffolds:**
  - `run.py`: model × prompt (current / git rev / file) × mode, cached,
    resumable, with repeats, cost, latency and JSON validity. Dry-run tested
    in both modes.
  - `score.py`: all metrics in README "Scoring", with per-group,
    reweighted, model-error vs context-gap and repeat-flip breakdowns.
    `--self-test` passes, and it was run end-to-end on a synthetic quantized
    run.
  - `export_stored.py`: production output to a run file. Not run, to keep
    labeling blind.
  - `packet.py`: blind labeling packets.

## Not done / blocked

- **No production DB access:** `DATABASE_URL` is unset. The items come from
  the local snapshot, and comment ids match production. To build against
  production, set `DATABASE_URL` or `EVAL_DB_URL`. Outbound access to
  `*.proxy.rlwy.net` is needed from cloud runners.
- **No model runs:** `OPENROUTER_API_KEY` is unset. openrouter.ai was
  reachable (HTTP 200 on /api/v1/models). Only dry runs were done.
- `alias_overrides.json` has the snapshot's 3 rows; production may have more.

## Next

1. The owner reviews the rules and the open questions (in the run report),
   especially closed places, reference-only names, bars and groceries, and
   is_negated for self-skips.
2. Apply any rule changes to `labels/batch01.py` and re-run it.
3. Label c0051–c0395 in batches (`labels/batch02.py`, ...), then the 17
   threads (one label line per comment).
4. With a key: `run.py` the production prompts (`--prompt git:0ea62ff~1`)
   in both modes with 3 reps, and score.
5. Once labeling is complete: `export_stored.py`, score the original
   extraction, re-read disagreements, then build v2 (README "v2").
