"""Build round 1 of the v4 extraction eval. Read-only against the database.

    EVAL_DB_URL=postgresql://... python eval/v4/build_round1.py

Writes eval/v4/items.jsonl (plus items_single.jsonl / items_thread.jsonl for
run.py) and eval/v4/design.json. Nothing from production's stored extraction
reaches the items: it only decides which heuristics a comment matches.
See eval/v4/README.md for the design and every heuristic.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import corpus  # noqa: E402
import design as D  # noqa: E402

SEED = "nyceats-eval-v4-r1"
ROUND = 1

SPEC = {
    # Thread mode: about 250 comments, 30% of them drawn at random. Budgets
    # sit below the target because the last chunk a stratum takes overshoots.
    "thread": {"random_comments": 65,
               "strata_comments": {"chunk_misattached": 35, "chunk_parent_outside": 30,
                                   "chunk_title_names_place": 35, "chunk_failure_dense": 35}},
    # Comment mode: 60 random + 140 targeted new comments, plus 50 v1 gold items.
    "comment": {"random": 60,
                "strata": {"dish_complaint": 14, "price_complaint": 14, "neg_wording_nonneg_score": 14,
                           "deep_chain_context_gap": 12, "reply_ancestor_named": 18,
                           "short_opinion_reply": 14, "avoid_or_strong_negative": 12,
                           "question_or_unvisited": 12, "stuck_default_with_opinion": 12,
                           "zero_mentions_suspicious": 10, "long_list": 8}},
    "overlap_v1": 50,
}


def pick_overlap(cp, k):
    """k v1 single-comment gold items, in hashed order, that are still eligible."""
    path = os.path.join(corpus.EVAL, "items.jsonl")
    with open(path, encoding="utf-8") as f:
        v1 = [json.loads(l) for l in f]
    cands = [(it["comment_id"], it["item_id"]) for it in v1
             if it["kind"] == "comment" and it["comment_id"] in cp.tags]
    cands.sort(key=lambda x: D.h(SEED, "overlap", x[0]))
    return cands[:k]


def main():
    cp = corpus.cached_corpus()
    overlap = pick_overlap(cp, SPEC["overlap_v1"])
    overlap_ids = {c for c, _ in overlap}
    # Thread chunks first, so single comments can avoid them: one comment
    # labeled in two items would give two conflicting references.
    chunks, stratum_t, d_t = D.draw_threads(cp, SPEC["thread"], SEED,
                                            cp.old_ids | overlap_ids, cp.old_threads)
    in_chunks = {c for key, _ in chunks for c in cp.chunks[key]["comment_ids"]}
    singles, stratum_c, d_c = D.draw_comments(cp, SPEC["comment"], SEED,
                                              cp.old_ids | overlap_ids | in_chunks)
    design = {"thread": d_t, "comment": d_c}
    conn = corpus.connect()
    items, mismatches = D.build_items(conn, cp, singles, chunks, stratum_c, stratum_t, design,
                                      ROUND, SEED, overlap)
    conn.close()
    D.assign_splits(items, SEED)
    meta = D.summarize(cp, items, design, mismatches, ROUND, SEED, SPEC)
    D.write_round(HERE, items, meta)
    print(json.dumps(meta["counts"], indent=1))
    if mismatches:
        print(f"WARNING: {len(mismatches)} chunk(s) ordered differently in the DB than in the corpus")


if __name__ == "__main__":
    main()
