# Embedding retrieval benchmark

Picks the embedding model for semantic search over r/FoodNYC comments. Five
OpenRouter models, plus local BM25 and BM25 hybrids, are run over the same
frozen queries against the comments search would actually index, then scored
against blind, pooled relevance judgments. Results and the recommendation are
in [RESULTS.md](RESULTS.md).

## What is committed and what is not

Committed: the code, `queries.jsonl` (frozen before any retrieval, in its own
commit), `GUIDELINES.md` (judging rules, same commit), `CORPUS.md` (strata
counts), `corpus_ids.txt.gz` (the frozen comment ids and tiers), the pools,
judgments, re-judgments and agreement, `latency.json`, `SPEND.md`, and the
results tables.

Not committed (`data/`, gitignored): comment text, the embedding cache,
vector matrices, runs, judging batches and the spend ledger. Credentials are
never copied: the OpenRouter key is read from `/Users/kenny/NYCEats/.env` and
the production `DATABASE_URL` from `.claude/worktrees/backend/.env`, at runtime.

## Safety

- The database connection is forced read-only at the server
  (`default_transaction_read_only=on`) and in the session. Nothing here
  writes to Postgres; vectors live on local disk only.
- Every API call goes through `openrouter.py`: cache first, then a
  pessimistic cost reservation (cl100k tokens x 1.3 x catalog price) checked
  against a **$4.50 cap** before the request is sent, then the actual cost
  from the response's `usage.cost` appended to `data/ledger.jsonl`. The ledger
  is shared across processes under a file lock, so parallel per-model runs
  are capped jointly.
- Only the embeddings endpoint is called.

## Rerun

```sh
cd eval/embeddings
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
PY=.venv/bin/python

$PY build_corpus.py                 # read-only pull from production -> data/corpus.jsonl, data/threads.jsonl
$PY probe_inputs.py                 # which query/document settings OpenRouter passes through (<1 cent)
$PY probe_inputs2.py
$PY run_embed.py --dry-run          # projected cost per model and stage; no calls
$PY run_embed.py --stage queries
$PY run_embed.py --parallel core full threads   # models in parallel, barrier between stages
$PY retrieve.py --scope full        # dense, @1024 truncations, BM25, RRF hybrids -> data/runs/
$PY retrieve.py --scope threads
$PY pool.py --scope full --depth 20 --tag comments        # pools + blind batches + 10% re-judge batches
$PY pool.py --scope threads --depth 5 --tag threads
#   judges grade data/judging/<tag>/{batch,rj}_NNN.md per GUIDELINES.md
#   into out_{batch,rj}_NNN.jsonl (see "Judging" below)
$PY merge_judgments.py --tag comments   # -> judgments_*.jsonl, rejudgments_*.jsonl, agreement_*.json
$PY merge_judgments.py --tag threads
$PY metrics.py --scope full --tag comments      # -> RESULTS_TABLES_comments.md
$PY metrics.py --scope threads --tag threads    # -> RESULTS_TABLES_threads.md (@5 metrics lead)
$PY depth50.py sample               # 150 unjudged top-50 comments per system -> blind batches
#   judges grade data/judging/comments_d50/batch_NNN.md
$PY merge_judgments.py --tag comments_d50
$PY depth50.py estimate             # -> DEPTH50.md, recall@50 corrected for pool depth
$PY measure_latency.py
$PY spend.py --write
```

Rerunning after a first run costs nothing: every embedding is cached under
(model, request settings, sha256 of the exact input). Note that
`build_corpus.py` re-reads production, which keeps growing; to reproduce this
exact corpus, filter its output to `corpus_ids.txt.gz`.

## Judging

Pairs are pooled TREC-style (union of every system's top 20 per query) and
written to batches with opaque pair ids, no system names, and shuffled order.
Each batch was graded by a separate Claude (Opus) subagent given only
`GUIDELINES.md` and the batch file. A seeded 10% sample was re-shuffled into
different batches and graded again by different subagents; agreement is in
`agreement_comments.json`.

## Files

| file | role |
|---|---|
| `common.py` | paths, credential loading, read-only DB connection |
| `openrouter.py` | embeddings client, cache, ledger and cap |
| `configs.py` | per-model query/document handling, and why |
| `build_corpus.py` | eligible comments, strata tags, stratified core sample |
| `queries_src.py` / `queries.jsonl` | the frozen queries, categories, holdout flags |
| `run_embed.py` | budget-ordered embedding runs, dry run |
| `retrieve.py` | dense, truncated, BM25 and RRF hybrid runs |
| `pool.py` | pools and blind judging batches |
| `merge_judgments.py` | completeness checks, merged judgments, agreement |
| `metrics.py` | nDCG/recall/MRR/P@k, bootstrap CIs, head-to-heads, categories, negation, restaurant view |
| `depth50.py` | sampled judging of unjudged top-50 comments; recall@50 corrected for pool depth |
| `measure_latency.py` | live single-query embedding latency |
| `spend.py` | ledger summary |
