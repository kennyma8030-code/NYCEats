"""How far Claude's v6 labels agree with themselves, in v6's own terms. No
database, no model.

    python eval/v4/label_agreement.py              # after labels.py export of both passes

compare_v4.py scores labels through score.py, which reads the adapted
7-point shape. This reads the v6 mention each label keeps under "v6" and
compares two label sets field by field:

  self_consistency:<pass>   the duplicate copy (rep 1) of each
                            self-consistency packet against its primary copy
  same_input_vs_full        the same_input labels against the full_context
                            labels, every comment: what the model's input
                            lacks, measured on Claude

For each comparison: mention agreement (places matched by score.py's keying:
normalize_entity, alias overrides, then the fuzzy rule with street words),
whether a comment has any mention at all, and on matched mentions the
overall verdict (null or not, sign, exact level), the five aspects, opinion,
experience, avoid, named_in and whether the mention is negative. The
same_input-vs-full_context comparison is also broken down by mode, stratum,
heuristic tag and reply depth, with the comments that differ listed, so the
kinds of comment that need context stand out.

Writes results/label_agreement.json and .md.
"""

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import score as S  # noqa: E402

ASPECTS = ("taste", "value", "service", "atmosphere", "wait")
SIGN = {"very_positive": 1, "positive": 1, "neutral": 0, "negative": -1, "very_negative": -1}
FIELDS = ("opinion", "experience", "avoid", "named_in", "timeframe", "status", "trend")


def labels(pass_name, rep, alias):
    """{comment_id: [v6 mention with _key]} for one pass and copy."""
    out = {}
    for r in S.load_jsonl(os.path.join(HERE, "labels", pass_name + ".run.jsonl")):
        if r["rep"] != rep:
            continue
        for cid, ms in r["mentions_by_comment"].items():
            keyed, seen = [], set()
            for m in ms:
                v = m.get("v6")
                if not isinstance(v, dict):
                    raise SystemExit(f"{pass_name}: a label without its v6 mention; re-export with labels.py")
                k = S.street_norm(S.model_key(m, alias))
                if k and k not in seen:
                    seen.add(k)
                    keyed.append(dict(v, _key=k))
            out[cid] = keyed
    return out


def match(a, b):
    pairs, used = [], set()
    for how in ("exact", "fuzzy"):
        for x in a:
            if any(x is p[0] for p in pairs):
                continue
            for j, y in enumerate(b):
                if j in used:
                    continue
                if (x["_key"] == y["_key"]) if how == "exact" else S.fuzzy(x["_key"], y["_key"]):
                    pairs.append((x, y))
                    used.add(j)
                    break
    return pairs


def negative(m):
    return (SIGN.get(m.get("overall")) == -1 or m.get("avoid")
            or any(SIGN.get((m.get("aspects") or {}).get(a)) == -1 for a in ASPECTS)
            or any(SIGN.get(d.get("level")) == -1 or d.get("avoid") for d in m.get("dishes") or []))


class Tally:
    def __init__(self):
        self.c = collections.Counter()

    def add(self, a, b):
        """a, b: one comment's mentions in each label set."""
        c = self.c
        c["comments"] += 1
        c["comment_presence_agree"] += bool(a) == bool(b)
        pairs = match(a, b)
        c["mentions_a"] += len(a)
        c["mentions_b"] += len(b)
        c["matched"] += len(pairs)
        c["comment_same_places"] += len(pairs) == len(a) == len(b)
        differs = not (len(pairs) == len(a) == len(b))
        for x, y in pairs:
            ox, oy = x.get("overall"), y.get("overall")
            c["overall_presence_agree"] += (ox is None) == (oy is None)
            if ox is not None and oy is not None:
                c["overall_both"] += 1
                c["overall_sign_agree"] += SIGN[ox] == SIGN[oy]
                c["overall_exact_agree"] += ox == oy
                differs |= SIGN[ox] != SIGN[oy]
            elif (ox is None) != (oy is None):
                differs = True
            c["negative_a"] += bool(negative(x))
            c["negative_b"] += bool(negative(y))
            c["negative_both"] += bool(negative(x) and negative(y))
            differs |= bool(negative(x)) != bool(negative(y))
            for asp in ASPECTS:
                vx, vy = (x.get("aspects") or {}).get(asp), (y.get("aspects") or {}).get(asp)
                c[f"{asp}_presence_agree"] += (vx is None) == (vy is None)
                c[f"{asp}_set_either"] += vx is not None or vy is not None
                c[f"{asp}_set_both"] += vx is not None and vy is not None
                if vx is not None and vy is not None:
                    c[f"{asp}_sign_agree"] += SIGN[vx] == SIGN[vy]
                    c[f"{asp}_exact_agree"] += vx == vy
            for f in FIELDS:
                c[f"{f}_agree"] += x.get(f) == y.get(f)
        c["comments_differ"] += differs
        return differs

    def summary(self):
        c = self.c
        r = lambda n, d: round(n / d, 3) if d else None  # noqa: E731
        out = {
            "comments": c["comments"],
            "comment_presence_agreement": r(c["comment_presence_agree"], c["comments"]),
            "comments_same_places": r(c["comment_same_places"], c["comments"]),
            "comments_materially_different": r(c["comments_differ"], c["comments"]),
            "mentions": [c["mentions_a"], c["mentions_b"]],
            "mention_agreement_f1": r(2 * c["matched"], c["mentions_a"] + c["mentions_b"]),
            "matched": c["matched"],
            "overall_presence_agreement": r(c["overall_presence_agree"], c["matched"]),
            "overall_sign_agreement": r(c["overall_sign_agree"], c["overall_both"]),
            "overall_exact_agreement": r(c["overall_exact_agree"], c["overall_both"]),
            "negative_agreement_f1": r(2 * c["negative_both"], c["negative_a"] + c["negative_b"]),
            "negatives": [c["negative_a"], c["negative_b"]],
        }
        for asp in ASPECTS:
            out[f"{asp}"] = {"presence": r(c[f"{asp}_presence_agree"], c["matched"]),
                             "set_either": c[f"{asp}_set_either"],
                             "both_set_of_either": r(c[f"{asp}_set_both"], c[f"{asp}_set_either"]),
                             "sign": r(c[f"{asp}_sign_agree"], c[f"{asp}_set_both"]),
                             "exact": r(c[f"{asp}_exact_agree"], c[f"{asp}_set_both"])}
        for f in FIELDS:
            out[f"{f}_agreement"] = r(c[f"{f}_agree"], c["matched"])
        return out


def item_index():
    out = {}
    for it in S.load_jsonl(os.path.join(HERE, "items.jsonl")):
        if it["kind"] == "comment":
            out[it["comment_id"]] = (it, set(it["tags"]), it["context"]["depth"])
        else:
            for c in it["comments"]:
                out[c["comment_id"]] = (it, set(it["tags"]) | set(c["tags"]), c["depth"])
    return out


def short(ms):
    return [f"{m['name']}:{m.get('overall') or '-'}" + (":avoid" if m.get("avoid") else "") for m in ms]


def compare(a, b, idx, by_group=False):
    total, groups, diffs = Tally(), collections.defaultdict(Tally), []
    for cid in sorted(set(a) & set(b)):
        differs = total.add(a[cid], b[cid])
        it, tags, depth = idx[cid]
        if by_group:
            keys = [f"mode:{it['mode']}", f"stratum:{it['stratum']}", f"draw:{it['draw']}",
                    "depth:top-level" if depth == 0 else ("depth:reply" if depth == 1 else "depth:reply 2+")]
            keys += [f"tag:{t}" for t in tags]
            for k in keys:
                groups[k].add(a[cid], b[cid])
        if differs:
            diffs.append({"comment_id": cid, "item_id": it["item_id"], "stratum": it["stratum"],
                          "a": short(a[cid]), "b": short(b[cid])})
    out = {"all": total.summary()}
    if by_group:
        out["groups"] = {k: v.summary() for k, v in sorted(groups.items())}
        out["differing_comments"] = diffs
    return out


def main():
    alias = S.load_map("alias_overrides.json")
    idx = item_index()
    res = {}
    for p in ("same_input", "full_context"):
        res[f"self_consistency:{p}"] = compare(labels(p, 0, alias), labels(p, 1, alias), idx)
    res["same_input_vs_full"] = compare(labels("full_context", 0, alias), labels("same_input", 0, alias), idx,
                                        by_group=True)
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    with open(os.path.join(HERE, "results", "label_agreement.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)

    keys = ("comments", "comment_presence_agreement", "mention_agreement_f1", "overall_presence_agreement",
            "overall_sign_agreement", "overall_exact_agreement", "negative_agreement_f1",
            "comments_materially_different")
    lines = ["# Claude's v6 labels: agreement with themselves", "",
             "a = primary copy (self-consistency) or full_context (same_input_vs_full); b = the other.", "",
             "| comparison | " + " | ".join(keys) + " |", "|---" * (len(keys) + 1) + "|"]
    for name, r in res.items():
        lines.append(f"| {name} | " + " | ".join(str(r["all"][k]) for k in keys) + " |")
    lines += ["", "## Aspects on matched mentions (presence / sign / exact)", "",
              "| comparison | " + " | ".join(ASPECTS) + " |", "|---" * (len(ASPECTS) + 1) + "|"]
    for name, r in res.items():
        lines.append(f"| {name} | " + " | ".join(
            f"{r['all'][a]['presence']} / {r['all'][a]['sign']} / {r['all'][a]['exact']} (n={r['all'][a]['set_either']})"
            for a in ASPECTS) + " |")
    g = res["same_input_vs_full"]["groups"]
    lines += ["", "## same_input vs full_context by group (most different first)", "",
              "| group | comments | materially different | mention F1 | overall sign | negative F1 |",
              "|---|---|---|---|---|---|"]
    for k, v in sorted(g.items(), key=lambda kv: -(kv[1]["comments_materially_different"] or 0)):
        if v["comments"] >= 5:
            lines.append(f"| {k} | {v['comments']} | {v['comments_materially_different']} | "
                         f"{v['mention_agreement_f1']} | {v['overall_sign_agreement']} | {v['negative_agreement_f1']} |")
    lines += ["", "## Comments that differ (full_context -> same_input)", ""]
    for d in res["same_input_vs_full"]["differing_comments"]:
        lines.append(f"- {d['item_id']} {d['comment_id']} ({d['stratum']}): {d['a']} -> {d['b']}")
    with open(os.path.join(HERE, "results", "label_agreement.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    for name, r in res.items():
        print(name, json.dumps({k: r["all"][k] for k in keys}))


if __name__ == "__main__":
    main()
