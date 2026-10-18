"""TREC-style pooling and blind judging batches.

    python pool.py --scope full --depth 20 --tag comments        # first pass
    python pool.py --scope threads --depth 5 --tag threads
    python pool.py --rejudge comments                            # blind consistency pass
    python pool.py --fullbody comments                           # re-judge long comments in full

For each query, the pool is the union of the top `depth` documents from every
system run (dense, truncated, BM25, hybrids). Each (query, document) pair gets
an opaque pair_id, and pairs are written to judging batches with no system
information. Pairs are grouped by query (the judge reads the query and its
intent once per block) but shuffled within the block, and the blocks themselves
are shuffled, so position says nothing about which system found a document or
how highly.

Every pass after the first is blind to the passes before it:
- its pair ids are salted with the pass name, so they cannot be matched to the
  first pass's ids;
- its batches go to their own directory, data/judging/<tag>_<pass>/, which
  holds nothing but that pass's batch files and the judges' outputs;
- its id -> (query, doc) keys go to data/judging_keys/<tag>_<pass>/, outside
  any directory a judge is pointed at.
(The first pass, run before this rule existed, keeps its keys beside its
batches; nothing had been judged before it, so there was nothing to leak.)

`--rejudge` draws a seeded 10% of the frozen pool for a consistency pass.
`--fullbody` re-issues every judged pair whose comment is longer than the
3,000 characters the first pass showed; those grades replace the first pass's.

Outputs:
  pools_<tag>.json                                 committed: {qid: [doc ids]} (no text)
  data/judging/<tag>/batch_NNN.md (+ .keys.json)  first pass
  data/judging/<tag>_rejudge/rj_NNN.md            blind consistency pass
  data/judging/<tag>_fullbody/batch_NNN.md        full-text re-judge of long comments
  data/judging_keys/<tag>_<pass>/*.keys.json       pair_id -> [qid, doc_id]
"""

import argparse
import hashlib
import json
import random
from collections import defaultdict

from common import DATA, HERE, read_jsonl

SEED = 1017
REJUDGE_SEED = 20261018
FIRST_PASS_BODY_CHARS = 3000  # what the first pass showed; later passes show everything
KEYS = DATA / "judging_keys"


def pair_id(qid, doc, salt=""):
    return hashlib.sha1(f"{salt}|{qid}|{doc}".encode() if salt else f"{qid}|{doc}".encode()).hexdigest()[:10]


def render(batch, queries, docs, kind, salt="", body_chars=None):
    out = [f"# Judging batch ({len(batch)} pairs)\n",
           "Grade each pair 0/1/2 with the `opposite` flag, per GUIDELINES.md.\n"]
    byq = defaultdict(list)
    order = []
    for qid, doc in batch:
        if qid not in byq:
            order.append(qid)
        byq[qid].append(doc)
    for qid in order:
        q = queries[qid]
        out.append(f"\n## Query: \"{q['text']}\"\nIntent: {q['intent']}\n")
        for doc in byq[qid]:
            d = docs[doc]
            pid = pair_id(qid, doc, salt)
            if kind == "threads":
                body = (d["selftext"] or "(no text)")[:body_chars]
                out.append(f"### pair {pid}\nThread title: {d['title']}\nPost text: {body}\n")
            else:
                body = d["body"][:body_chars]
                out.append(f"### pair {pid}\nThread title: {d['title']}\nComment: {body}\n")
    return "\n".join(out)


def write_batches(pairs, size, prefix, outdir, queries, docs, kind, rng,
                  salt="", keysdir=None, body_chars=None):
    byq = defaultdict(list)
    for qid, doc in pairs:
        byq[qid].append(doc)
    blocks = []
    for qid, ds in byq.items():
        ds = ds[:]
        rng.shuffle(ds)
        # Split very large pools so one batch is never a single query's 150 docs.
        for i in range(0, len(ds), size // 2):
            blocks.append([(qid, d) for d in ds[i:i + size // 2]])
    rng.shuffle(blocks)
    batches, cur = [], []
    for b in blocks:
        if cur and len(cur) + len(b) > size:
            batches.append(cur)
            cur = []
        cur += b
    if cur:
        batches.append(cur)
    keysdir = keysdir or outdir
    keysdir.mkdir(parents=True, exist_ok=True)
    for n, b in enumerate(batches):
        (outdir / f"{prefix}_{n:03d}.md").write_text(render(b, queries, docs, kind, salt, body_chars))
        (keysdir / f"{prefix}_{n:03d}.keys.json").write_text(
            json.dumps({pair_id(q, d, salt): [q, d] for q, d in b}))
    return len(batches)


def _load(tag):
    queries = {q["qid"]: q for q in read_jsonl(HERE / "queries.jsonl")}
    kind = "threads" if tag.startswith("threads") else "comments"
    src = DATA / ("threads.jsonl" if kind == "threads" else "corpus.jsonl")
    docs = {r["id"]: r for r in read_jsonl(src)}
    return queries, kind, docs


def _fresh_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    for f in path.glob("*"):
        f.unlink()
    return path


def later_pass(tag, name, pairs, prefix, size, rng, queries, kind, docs):
    salt = f"{tag}:{name}"
    outdir = _fresh_dir(DATA / "judging" / f"{tag}_{name}")
    keysdir = _fresh_dir(KEYS / f"{tag}_{name}")
    n = write_batches(pairs, size, prefix, outdir, queries, docs, kind, rng,
                      salt=salt, keysdir=keysdir, body_chars=None)
    print(f"{len(pairs)} pairs in {n} batches -> {outdir} (keys in {keysdir})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="full")
    ap.add_argument("--depth", type=int, default=20)
    ap.add_argument("--tag", default="comments")
    ap.add_argument("--batch", type=int, default=240)
    ap.add_argument("--rejudge-share", type=float, default=0.10)
    ap.add_argument("--rejudge", metavar="TAG", help="write a blind consistency pass for TAG")
    ap.add_argument("--fullbody", metavar="TAG", help="re-judge TAG's pairs on comments over 3,000 chars")
    a = ap.parse_args()

    if a.rejudge:
        queries, kind, docs = _load(a.rejudge)
        pools = json.loads((HERE / f"pools_{a.rejudge}.json").read_text())["pools"]
        pairs = sorted((q, d) for q, ds in pools.items() for d in ds)
        rng = random.Random(REJUDGE_SEED)
        sample = rng.sample(pairs, round(len(pairs) * a.rejudge_share))
        later_pass(a.rejudge, "rejudge", sample, "rj", a.batch, rng, queries, kind, docs)
        return

    if a.fullbody:
        queries, kind, docs = _load(a.fullbody)
        judged = [(r["qid"], r["doc_id"]) for r in read_jsonl(HERE / f"judgments_{a.fullbody}.jsonl")]
        long_pairs = sorted(p for p in judged if len(docs[p[1]]["body"]) > FIRST_PASS_BODY_CHARS)
        n_docs = len({d for _, d in long_pairs})
        print(f"{n_docs} comments over {FIRST_PASS_BODY_CHARS} chars in {len(long_pairs)} judged pairs")
        if long_pairs:
            later_pass(a.fullbody, "fullbody", long_pairs, "batch", a.batch,
                       random.Random(REJUDGE_SEED), queries, kind, docs)
        return

    rng = random.Random(SEED)
    queries, kind, docs = _load("threads" if a.scope == "threads" else "comments")
    pool = defaultdict(set)
    rundir = DATA / "runs" / a.scope
    systems = sorted(p.stem for p in rundir.glob("*.json"))
    for s in systems:
        run = json.loads((rundir / f"{s}.json").read_text())
        for qid, lst in run.items():
            pool[qid].update(d for d, _ in lst[:a.depth])
    pools = {qid: sorted(pool[qid]) for qid in sorted(pool)}
    (HERE / f"pools_{a.tag}.json").write_text(json.dumps(
        {"depth": a.depth, "systems": systems, "pools": pools}, indent=0))
    pairs = [(q, d) for q, ds in pools.items() for d in ds]
    print(f"{len(systems)} systems, {len(pairs)} pairs, "
          f"mean pool {len(pairs) / len(pools):.1f}/query")
    outdir = DATA / "judging" / a.tag
    outdir.mkdir(parents=True, exist_ok=True)
    n = write_batches(pairs, a.batch, "batch", outdir, queries, docs, kind, rng,
                      body_chars=FIRST_PASS_BODY_CHARS)
    print(f"{n} first-pass batches in {outdir}; run --rejudge {a.tag} for the consistency pass")


if __name__ == "__main__":
    main()
