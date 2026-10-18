"""Check judge output for completeness and merge it into the committed files.

    python merge_judgments.py --tag comments

Reads each pass's batch keys and the judges' out_*.jsonl, maps opaque pair ids
back to (qid, doc_id), and writes:
  judgments_<tag>.jsonl     first-pass grades, with the full-text re-judge of
                            long comments (data/judging/<tag>_fullbody/)
                            replacing the truncated originals -- what
                            metrics.py scores
  rejudgments_<tag>.jsonl   the blind consistency pass (data/judging/<tag>_rejudge/)
  agreement_<tag>.json      agreement of the blind pass with the first pass,
                            beside the earlier, not-blind re-judge for comparison

If any batch of any pass has missing, unknown or malformed pairs, it prints
the problems, writes nothing, and exits non-zero: a partial merge would score
the missing pairs as non-relevant without anyone noticing.
"""

import argparse
import json
import sys
from collections import Counter

from common import DATA, HERE

KEYS = DATA / "judging_keys"


def load(outdir, prefix, keysdir=None):
    """Grades for every batch of one pass. Keys live beside the batches for
    the first pass and under data/judging_keys/ for later, blind passes."""
    got, problems = {}, []
    if not outdir.exists():
        return got, problems
    keysdir = keysdir if keysdir and keysdir.exists() else outdir
    for keys in sorted(keysdir.glob(f"{prefix}_*.keys.json")):
        n = keys.name.split(".")[0]
        km = json.loads(keys.read_text())
        out = outdir / f"out_{n}.jsonl"
        if not out.exists():
            problems.append(f"{outdir.name}/{n}: no output")
            continue
        seen = {}
        for line in out.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                pid = str(r["pair_id"])
                g = int(r["grade"])
                assert g in (0, 1, 2)
                seen[pid] = {"grade": g, "opposite": bool(r.get("opposite")) and g == 0}
            except Exception as e:
                problems.append(f"{outdir.name}/{n}: bad line {line[:80]} ({e})")
        missing = set(km) - set(seen)
        extra = set(seen) - set(km)
        if missing or extra:
            problems.append(f"{outdir.name}/{n}: {len(missing)} missing, {len(extra)} unknown ids")
        for pid, v in seen.items():
            if pid in km:
                qid, doc = km[pid]
                got[(qid, doc)] = v
    return got, problems


def agreement(first, second):
    both = [k for k in second if k in first]
    if not both:
        return None
    n = len(both)
    exact = sum(first[k]["grade"] == second[k]["grade"] for k in both) / n
    binary = sum((first[k]["grade"] >= 1) == (second[k]["grade"] >= 1) for k in both) / n
    within1 = sum(abs(first[k]["grade"] - second[k]["grade"]) <= 1 for k in both) / n
    c1 = Counter(first[k]["grade"] for k in both)
    c2 = Counter(second[k]["grade"] for k in both)
    pe = sum(c1[g] * c2[g] for g in (0, 1, 2)) / (n * n)
    kappa = (exact - pe) / (1 - pe) if pe < 1 else 1.0
    cb1 = Counter(first[k]["grade"] >= 1 for k in both)
    cb2 = Counter(second[k]["grade"] >= 1 for k in both)
    pbe = sum(cb1[g] * cb2[g] for g in (True, False)) / (n * n)
    kb = (binary - pbe) / (1 - pbe) if pbe < 1 else 1.0
    conf = Counter((first[k]["grade"], second[k]["grade"]) for k in both)
    return {"pairs": n, "exact": exact, "kappa_3way": kappa, "binary_rel": binary,
            "kappa_binary": kb, "within_1": within1,
            "confusion_first_second": {f"{a}->{b}": c for (a, b), c in sorted(conf.items())}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="comments")
    a = ap.parse_args()
    root = DATA / "judging"
    first, p1 = load(root / a.tag, "batch")
    full, p2 = load(root / f"{a.tag}_fullbody", "batch", KEYS / f"{a.tag}_fullbody")
    blind, p3 = load(root / f"{a.tag}_rejudge", "rj", KEYS / f"{a.tag}_rejudge")
    legacy, p4 = load(root / a.tag, "rj")  # the earlier, not-blind re-judge
    problems = p1 + p2 + p3 + p4
    if problems:
        for p in problems:
            print("PROBLEM", p, file=sys.stderr)
        sys.exit(f"{len(problems)} batch problem(s); nothing written")

    unknown = set(full) - set(first)
    if unknown:
        sys.exit(f"{len(unknown)} full-text grades for pairs the first pass never judged; nothing written")
    changed = {k: (first[k]["grade"], v["grade"]) for k, v in full.items() if first[k]["grade"] != v["grade"]}
    raw_first = dict(first)
    first.update(full)

    with open(HERE / f"judgments_{a.tag}.jsonl", "w") as f:
        for (q, d), v in sorted(first.items()):
            f.write(json.dumps({"qid": q, "doc_id": d, **v,
                                **({"source": "fullbody"} if (q, d) in full else {})}) + "\n")
    with open(HERE / f"rejudgments_{a.tag}.jsonl", "w") as f:
        for (q, d), v in sorted(blind.items()):
            f.write(json.dumps({"qid": q, "doc_id": d, **v}) + "\n")
    print(f"first pass {len(first)} pairs, grades {dict(Counter(v['grade'] for v in first.values()))}, "
          f"opposite {sum(v['opposite'] for v in first.values())}")
    if full:
        print(f"full-text re-judge: {len(full)} pairs, {len(changed)} grade(s) changed: {changed}")

    res = {"blind": agreement(first, blind),
           # Compared against the grades the legacy pass actually re-judged
           # (before any full-text replacement), as it was reported.
           "legacy_not_blind": agreement(raw_first, legacy),
           "fullbody_changes": {f"{q}|{d}": f"{o}->{n}" for (q, d), (o, n) in changed.items()}}
    print(json.dumps(res, indent=1))
    (HERE / f"agreement_{a.tag}.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
