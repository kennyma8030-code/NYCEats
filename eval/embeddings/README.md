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
$PY pool.py --scope full --depth 20 --tag comments        # pools + first-pass batches
$PY pool.py --scope threads --depth 5 --tag threads
#   judges grade data/judging/<tag>/batch_NNN.md per GUIDELINES.md into out_batch_NNN.jsonl
$PY merge_judgments.py --tag comments   # first pass -> judgments_comments.jsonl
$PY pool.py --fullbody comments         # pairs whose comment the first pass cut at 3,000 chars
$PY pool.py --rejudge comments          # blind 10% consistency pass (salted ids, own directory)
$PY pool.py --rejudge threads
#   judges grade data/judging/<tag>_{fullbody,rejudge}/*.md (see "Judging" below)
$PY merge_judgments.py --tag comments   # full-text grades replace truncated ones; -> agreement_comments.json
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

Pairs are pooled TREC-style: the union of every system's top 20 per query for
comments, top 5 for threads. They are written to batches with opaque pair ids,
no system names, and shuffled order. Each batch was graded by a separate Claude
(Opus) subagent given only `GUIDELINES.md` and the batch file, at most three at
a time.

Every pass after the first is blind to the earlier ones:
- **Salted ids.** Its pair ids are salted with the pass name, so they don't
  match the first pass's.
- **Separate files.** Its batches live in their own directory, and its id keys
  sit under `data/judging_keys/`.
- **Locked first pass.** While it was judged, the first-pass directories, the
  keys, the committed grade files and the corpus text were `chmod 000`, so a
  judge could not read them even by accident.

`agreement_<tag>.json` has two parts. `blind` is that pass's agreement with
the first pass. `legacy_not_blind` is the earlier re-judge, whose ids matched
the first pass and whose outputs shared its directory.

`merge_judgments.py` exits non-zero and writes nothing if any batch of any pass
has missing, unknown or malformed pairs.

## Spend accounting

Every attempt that may have been billed (a timeout, a dropped connection, a
5xx, a 200 without vectors) is written to the ledger at its pessimistic
estimate and marked `possibly_billed`. A clean 4xx rejection is not billed and
is not retried. The earlier runs predate this, so their unrecorded retries
show up only in OpenRouter's own usage counter (see RESULTS.md, Spend).

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
