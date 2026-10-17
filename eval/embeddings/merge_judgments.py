"""Check judge output for completeness and merge it into the committed files.

    python merge_judgments.py --tag comments

Reads data/judging/<tag>/{batch,rj}_NNN.keys.json and the judges'
out_{batch,rj}_NNN.jsonl, maps opaque pair ids back to (qid, doc_id), and
writes:
  judgments_<tag>.jsonl     first-pass grades (what metrics.py scores)
  rejudgments_<tag>.jsonl   the independent ~10% second pass
and prints any batch with missing or malformed pairs, plus judge agreement.
"""

import argparse
import json
from collections import Counter

from common import DATA, HERE


def load(outdir, prefix):
    got, problems = {}, []
    for keys in sorted(outdir.glob(f"{prefix}_*.keys.json")):
        n = keys.name.split(".")[0]
        km = json.loads(keys.read_text())
        out = outdir / f"out_{n}.jsonl"
        if not out.exists():
            problems.append(f"{n}: no output")
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
                problems.append(f"{n}: bad line {line[:80]} ({e})")
        missing = set(km) - set(seen)
        extra = set(seen) - set(km)
        if missing or extra:
            problems.append(f"{n}: {len(missing)} missing, {len(extra)} unknown ids")
        for pid, v in seen.items():
            if pid in km:
                qid, doc = km[pid]
                got[(qid, doc)] = v
    return got, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="comments")
    a = ap.parse_args()
    outdir = DATA / "judging" / a.tag
    first, p1 = load(outdir, "batch")
    second, p2 = load(outdir, "rj")
    for p in p1 + p2:
        print("PROBLEM", p)
    with open(HERE / f"judgments_{a.tag}.jsonl", "w") as f:
        for (q, d), v in sorted(first.items()):
            f.write(json.dumps({"qid": q, "doc_id": d, **v}) + "\n")
    with open(HERE / f"rejudgments_{a.tag}.jsonl", "w") as f:
        for (q, d), v in sorted(second.items()):
            f.write(json.dumps({"qid": q, "doc_id": d, **v}) + "\n")
    print(f"first pass {len(first)} pairs, grades {dict(Counter(v['grade'] for v in first.values()))}, "
          f"opposite {sum(v['opposite'] for v in first.values())}")
    both = [k for k in second if k in first]
    if both:
        exact = sum(first[k]["grade"] == second[k]["grade"] for k in both) / len(both)
        binary = sum((first[k]["grade"] >= 1) == (second[k]["grade"] >= 1) for k in both) / len(both)
        within1 = sum(abs(first[k]["grade"] - second[k]["grade"]) <= 1 for k in both) / len(both)
        # Cohen's kappa on the 3-way grade.
        n = len(both)
        pa = exact
        c1 = Counter(first[k]["grade"] for k in both)
        c2 = Counter(second[k]["grade"] for k in both)
        pe = sum(c1[g] * c2[g] for g in (0, 1, 2)) / (n * n)
        kappa = (pa - pe) / (1 - pe) if pe < 1 else 1.0
        cb1 = Counter(first[k]["grade"] >= 1 for k in both)
        cb2 = Counter(second[k]["grade"] >= 1 for k in both)
        pbe = sum(cb1[g] * cb2[g] for g in (True, False)) / (n * n)
        kb = (binary - pbe) / (1 - pbe) if pbe < 1 else 1.0
        conf = Counter((first[k]["grade"], second[k]["grade"]) for k in both)
        res = {"pairs": n, "exact": exact, "kappa_3way": kappa, "binary_rel": binary,
               "kappa_binary": kb, "within_1": within1,
               "confusion_first_second": {f"{a}->{b}": c for (a, b), c in sorted(conf.items())}}
        print(json.dumps(res, indent=1))
        (HERE / f"agreement_{a.tag}.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
