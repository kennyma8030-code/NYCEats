"""Run every system over the frozen queries and save ranked lists.

    python retrieve.py --scope full        # or core
    python retrieve.py --scope threads

Systems:
  <model>            dense cosine at native dims
  <model>@1024       the same vectors truncated to 1024 and renormalised
                     (equal to asking the API for 1024 dims; see configs.py)
  bm25               Okapi BM25 over the same title+body text, computed locally
  <model>+bm25       reciprocal rank fusion of the dense top-100 and BM25 top-100,
                     k=60, fixed in advance (the standard constant; not tuned)

Output: data/runs/<scope>/<system>.json  {qid: [[doc_id, score], ...top 100]}
"""

import argparse
import json
import math
import re
from collections import Counter, defaultdict

import numpy as np

from common import DATA, HERE, read_jsonl
from configs import dense_systems

DEPTH = 100
RRF_K = 60

STOP = set("""a an the and or but if of to in on at for with without from by about as is are was
were be been being it its this that these those i me my we our you your he she they them their
there here what which who whom where when why how do does did done have has had having not no
so than too very can could should would will just also any some all more most other such only
own same s t don isnt arent wasnt any get got go going im ive id youre theyre thats whats one
really like place places spot spots good great best""".split())


def tokenize(text):
    """Lowercase word tokens, apostrophes folded ("isn't" -> "isnt"), stopwords
    dropped, and a light plural strip so "dumplings" meets "dumpling". The
    stopword list includes generic praise words ("good", "best", "place")
    because nearly every comment in a food subreddit has them; leaving them in
    lets BM25 match on them alone."""
    text = text.lower().replace("’", "'").replace("'", "")
    out = []
    for w in re.findall(r"[a-z0-9]+", text):
        if w in STOP or len(w) < 2:
            continue
        if len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


class BM25:
    def __init__(self, docs, k1=1.2, b=0.75):
        self.k1, self.b = k1, b
        self.N = len(docs)
        self.dl = np.zeros(self.N, dtype=np.float32)
        post = defaultdict(lambda: ([], []))
        for i, d in enumerate(docs):
            toks = tokenize(d)
            self.dl[i] = len(toks)
            for t, tf in Counter(toks).items():
                post[t][0].append(i)
                post[t][1].append(tf)
        self.avgdl = float(self.dl.mean()) or 1.0
        self.post = {t: (np.array(ix, dtype=np.int32), np.array(tf, dtype=np.float32))
                     for t, (ix, tf) in post.items()}

    def scores(self, query):
        s = np.zeros(self.N, dtype=np.float32)
        norm = self.k1 * (1 - self.b + self.b * self.dl / self.avgdl)
        for t in set(tokenize(query)):
            if t not in self.post:
                continue
            ix, tf = self.post[t]
            idf = math.log(1 + (self.N - len(ix) + 0.5) / (len(ix) + 0.5))
            s[ix] += idf * tf * (self.k1 + 1) / (tf + norm[ix])
        return s


def topk(scores, k):
    k = min(k, len(scores))
    idx = np.argpartition(-scores, k - 1)[:k]
    return idx[np.argsort(-scores[idx], kind="stable")]


def dense_rank(qmat, dmat, dims):
    q = qmat[:, :dims].astype(np.float32)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    # Chunk over documents so a 97k x 4096 float32 copy never exists at once.
    chunk = 20000
    allscores = np.zeros((len(q), dmat.shape[0]), dtype=np.float32)
    for s in range(0, dmat.shape[0], chunk):
        d = dmat[s:s + chunk, :dims].astype(np.float32)
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        allscores[:, s:s + chunk] = q @ d.T
    return allscores


def rrf(*ranked_lists):
    fused = defaultdict(float)
    for lst in ranked_lists:
        for r, (doc, _) in enumerate(lst):
            fused[doc] += 1.0 / (RRF_K + r + 1)
    return sorted(fused.items(), key=lambda kv: -kv[1])[:DEPTH]


def load_docs(scope):
    if scope == "threads":
        rows = read_jsonl(DATA / "threads.jsonl")
        return rows, [f"{r['title']}\n\n{r['selftext']}" for r in rows], "threads"
    rows = read_jsonl(DATA / "corpus.jsonl")
    idx = [i for i, r in enumerate(rows) if scope == "full" or r["tier"] == "core"]
    rows = [rows[i] for i in idx]
    return rows, [f"{r['title']}\n\n{r['body']}" for r in rows], scope


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["core", "full", "threads"], default="full")
    a = ap.parse_args()
    queries = read_jsonl(HERE / "queries.jsonl")
    rows, texts, scope = load_docs(a.scope)
    ids = [r["id"] for r in rows]
    out = DATA / "runs" / scope
    out.mkdir(parents=True, exist_ok=True)

    bm = BM25(texts)
    runs = {"bm25": {}}
    for q in queries:
        s = bm.scores(q["text"])
        runs["bm25"][q["qid"]] = [[ids[i], float(s[i])] for i in topk(s, DEPTH) if s[i] > 0]

    full_rows = None
    for name, m, dims in dense_systems():
        stage = "threads" if scope == "threads" else ("core" if scope == "core" else "full")
        path = DATA / "vecs" / f"{m.name}__{stage}.npy"
        if not path.exists() and stage == "core":
            # A full matrix contains the core rows; slice it rather than re-embed.
            fp = DATA / "vecs" / f"{m.name}__full.npy"
            if fp.exists():
                if full_rows is None:
                    full_rows = [r["tier"] == "core" for r in read_jsonl(DATA / "corpus.jsonl")]
                path = fp
        if not path.exists():
            print(f"skip {name}: no {path.name}")
            continue
        dmat = np.load(path, mmap_mode="r")
        if path.name.endswith("__full.npy") and stage == "core":
            dmat = np.asarray(dmat)[np.array(full_rows)]
        qmat = np.load(DATA / "vecs" / f"{m.name}__queries.npy")
        assert dmat.shape[0] == len(ids), (name, dmat.shape, len(ids))
        S = dense_rank(qmat, dmat, dims)
        runs[name] = {}
        for qi, q in enumerate(queries):
            runs[name][q["qid"]] = [[ids[i], float(S[qi, i])] for i in topk(S[qi], DEPTH)]
        if "@" not in name:
            runs[name + "+bm25"] = {q["qid"]: [[d, s] for d, s in rrf(runs[name][q["qid"]], runs["bm25"][q["qid"]])]
                                    for q in queries}
        print(f"{scope}: {name} done")

    for name, r in runs.items():
        (out / f"{name}.json").write_text(json.dumps(r))
    print(f"wrote {len(runs)} runs to {out}")


if __name__ == "__main__":
    main()
