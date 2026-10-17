"""Build the benchmark corpus from production, read-only.

Eligible comments are the ones search would index: at least one row in
`mentions`, body not [deleted] or [removed]. Each is tagged with strata
(period, length, cuisine, borough, price, occasion, sentiment, form, style,
dish talk, thread type) using stored fields and text heuristics. The tags only
steer sampling and reporting; the embedded text is exactly thread title +
comment body, as the search plan specifies.

Two tiers, so a budget stop still leaves a usable comparison:
  core  -- a stratified sample that over-represents rare strata
  full  -- every other eligible comment, embedded only after every model has
           finished the core

Outputs (data/ is gitignored; the id list and strata table are committed):
  data/corpus.jsonl    one row per comment: text, tags, tier, mentions
  data/threads.jsonl   the threads those comments belong to
  corpus_ids.txt.gz    the frozen comment ids and tiers, for reproducibility
  CORPUS.md            strata counts for the core and the full corpus
"""

import argparse
import gzip
import random
import re
from collections import Counter, defaultdict

from common import DATA, HERE, connect_readonly, write_jsonl
from openrouter import count_tokens

SEED = 20261017
THREAD_SELFTEXT_CHARS = 1500  # ~350 tokens; selftext is long-tailed

OCCASION = {
    "date": r"\b(date night|date spot|a date|first date|romantic|anniversary|dates?)\b",
    "group": r"\b(big group|large group|group of \d+|groups?|party of|birthday|bachelorette|family style|private room)\b",
    "solo": r"\b(solo|alone|by myself|at the bar|bar seat|counter seat|eat alone)\b",
    "brunch": r"\b(brunch|bottomless|mimosas?)\b",
    "late_night": r"\b(late night|late-night|open late|after midnight|\d ?am\b|after the bars|drunk food)\b",
}
SLANG = r"\b(slaps?|bussin|fire|goated|mid|lowkey|highkey|ngl|tbh|imo|legit|bomb|banger|elite|no cap|hits different|chefs? kiss|smash|bangin|lit|dope|sus|vibes?)\b"
MISSPELL = r"\b(restaraunt|resturant|restuarant|resteraunt|definately|definatly|reccomend|recomend|reccommend|expresso|carbonera|delish|delicous|delicious+s|sandwhich|sandwitch|tommorow|alot|gonna|wanna|tho|thru|u r|ur|ppl|pls|plz|bc|cuz|def\b)"
QUESTION_REC = r"(any (recs|recommendations|suggestions|ideas)|recommend(ations)?\??$|looking for|where (can|should|do) (i|we|you)|what('s| is) (the|a) (best|good)|suggestions)"


def length_bucket(n):
    if n < 60:
        return "1_one-liner(<60ch)"
    if n < 200:
        return "2_short(60-199)"
    if n < 600:
        return "3_medium(200-599)"
    return "4_long(600+)"


def period(dt):
    y = dt.year
    if y < 2025:
        return f"{y}"
    return f"{y}-H{1 if dt.month <= 6 else 2}"


def thread_type(title, selftext):
    t = (title or "").lower()
    if re.search(r"\b(rant|unpopular opinion|overrated|worst|disappoint|why (is|are|does|do)|annoy|scam|tourist trap)", t):
        return "rant/opinion"
    if re.search(r"\b(open(ed|ing|s)?|clos(ed|ing|es|ure)|coming soon|new location|announc|news|now open|shutter)", t):
        return "news/openings"
    if re.search(r"\b(review|tried|went to|visited|report|thoughts on|my (meal|dinner|experience)|just (ate|had))", t):
        return "review/report"
    if "?" in t or re.search(r"\b(recs?|recommend|suggest|looking for|where|best|help|ideas|need)\b", t):
        return "rec request"
    return "other"


def sentiment(ms):
    if any(m["is_negated"] for m in ms):
        return "negated"
    vals = []
    for m in ms:
        a = m.get("aspects") or {}
        if isinstance(a, dict):
            vals += [v for v in a.values() if isinstance(v, (int, float))]
    if not vals:
        return "neutral/unknown"
    if min(vals) < -0.2 and max(vals) > 0.2:
        return "mixed"
    avg = sum(vals) / len(vals)
    if avg >= 0.6:
        return "rave"
    if avg <= -0.2:
        return "negative"
    return "mild positive" if avg > 0.1 else "mixed"


def price(ms):
    xs = [m["expensiveness"] for m in ms if m.get("expensiveness") is not None]
    if not xs:
        return "unstated"
    x = max(xs)
    return "cheap" if x < 0.34 else ("mid" if x < 0.67 else "expensive")


def fetch():
    conn = connect_readonly()
    cur = conn.cursor(name="eligible")  # server-side cursor: ~100k rows
    cur.itersize = 5000
    cur.execute("""
        select c.id, c.thread_id, c.author, c.body, c.created_utc, c.score,
               c.was_deleted_later, c.depth, t.title
        from comments c join threads t on t.id = c.thread_id
        where exists (select 1 from mentions m where m.comment_id = c.id)
          and c.body not in ('[deleted]', '[removed]')
        order by c.id""")
    comments = list(cur)
    cur.close()
    cur = conn.cursor(name="mentions")
    cur.itersize = 10000
    cur.execute("""
        select m.comment_id, m.entity_key, coalesce(a.resolved_key, m.entity_key),
               m.is_negated, m.dishes, m.descriptors, m.aspects, m.expensiveness,
               m.neighborhood_hint, r.cuisine, r.boroughs,
               exists (select 1 from excluded_entities x
                       where x.entity_key = coalesce(a.resolved_key, m.entity_key))
        from mentions m
        left join entity_alias a on a.entity_key = m.entity_key
        left join restaurants r on r.name_key = coalesce(a.resolved_key, m.entity_key)""")
    ments = defaultdict(list)
    for (cid, ek, rk, neg, dishes, desc, aspects, exp, hood, cuisine, boros, excl) in cur:
        ments[cid].append({"entity_key": ek, "resolved_key": rk, "is_negated": bool(neg),
                           "dishes": dishes if isinstance(dishes, list) else [],
                           "descriptors": desc if isinstance(desc, list) else [],
                           "aspects": aspects if isinstance(aspects, dict) else {},
                           "expensiveness": exp, "neighborhood_hint": hood,
                           "cuisine": cuisine, "boroughs": boros or [], "excluded": bool(excl)})
    cur.close()
    cur = conn.cursor()
    tids = sorted({c[1] for c in comments})
    cur.execute("select id, title, selftext from threads where id = any(%s)", (tids,))
    threads = {r[0]: {"id": r[0], "title": r[1] or "", "selftext": r[2] or ""} for r in cur}
    conn.close()
    return comments, ments, threads


def tags_for(c, ms, thread):
    cid, tid, author, body, created, score, deleted, depth, title = c
    low = (title + " \n " + body).lower()
    blow = body.lower()
    cuisines = Counter(m["cuisine"] for m in ms if m["cuisine"])
    boros = Counter(b for m in ms for b in m["boroughs"])
    occ = [k for k, rx in OCCASION.items() if re.search(rx, low)]
    form = []
    if "?" in body:
        form.append("question")
    if re.search(QUESTION_REC, blow):
        form.append("rec request")
    n_places = len({m["resolved_key"] for m in ms})
    if n_places >= 3 or len(re.findall(r"(^|\n)\s*([-*•]|\d+[.)])\s", body)) >= 3:
        form.append("list of places")
    style = []
    if re.search(SLANG, blow):
        style.append("slang")
    if re.search(MISSPELL, blow):
        style.append("misspelling/informal")
    return {
        "period": period(created),
        "length": length_bucket(len(body)),
        "cuisine": cuisines.most_common(1)[0][0] if cuisines else "unmatched",
        "borough": boros.most_common(1)[0][0] if boros else "unmatched",
        "price": price(ms),
        "occasion": occ or ["none"],
        "sentiment": sentiment(ms),
        "form": form or ["statement"],
        "style": style or ["plain"],
        "dish": "dish-specific" if any(m["dishes"] for m in ms) else "no dish",
        "thread_type": thread_type(title, thread["selftext"]),
        "n_places": "1" if n_places == 1 else ("2" if n_places == 2 else "3+"),
    }


def strata(tags):
    for dim, v in tags.items():
        for x in (v if isinstance(v, list) else [v]):
            yield (dim, x)


def stratified(rows, n_core, floor):
    """Greedy quota sampling. Every stratum gets at least min(size, floor)
    members, rarest strata first so they are not crowded out, then the rest
    of the core is filled at random. Rare strata are deliberately
    over-represented: a corpus that is 70% one-sentence raves would hide the
    differences this benchmark is for."""
    rng = random.Random(SEED)
    order = list(range(len(rows)))
    rng.shuffle(order)
    members = defaultdict(list)
    for i in order:
        for s in strata(rows[i]["tags"]):
            members[s].append(i)
    chosen = set()
    have = Counter()
    for s in sorted(members, key=lambda s: len(members[s])):
        want = min(len(members[s]), floor)
        for i in members[s]:
            if have[s] >= want:
                break
            if i in chosen:
                continue
            chosen.add(i)
            for s2 in strata(rows[i]["tags"]):
                have[s2] += 1
    for i in order:
        if len(chosen) >= n_core:
            break
        chosen.add(i)
    return chosen


def table(rows, title):
    out = [f"### {title} ({len(rows):,} comments)\n"]
    by = defaultdict(Counter)
    for r in rows:
        for dim, x in strata(r["tags"]):
            by[dim][x] += 1
    for dim, cnt in by.items():
        out.append(f"**{dim}**: " + ", ".join(f"{k} {v:,}" for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])) + "\n")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", type=int, default=25000)
    ap.add_argument("--floor", type=int, default=600)
    args = ap.parse_args()

    comments, ments, threads = fetch()
    print(f"{len(comments)} eligible comments, {len(threads)} threads")
    rows = []
    for c in comments:
        cid, tid, author, body, created, score, deleted, depth, title = c
        ms = ments[cid]
        rows.append({
            "id": cid, "thread_id": tid, "author": author,
            "created_utc": created.isoformat(), "score": score,
            "was_deleted_later": bool(deleted), "depth": depth,
            "title": title or "", "body": body,
            "tokens": count_tokens((title or "") + "\n\n" + body),
            "tags": tags_for(c, ms, threads[tid]),
            "mentions": [{k: m[k] for k in ("resolved_key", "is_negated", "excluded", "cuisine")} for m in ms],
        })
    core = stratified(rows, args.core, args.floor)
    for i, r in enumerate(rows):
        r["tier"] = "core" if i in core else "full"
    write_jsonl(DATA / "corpus.jsonl", rows)

    used = {r["thread_id"] for r in rows}
    trows = []
    for tid in sorted(used):
        t = threads[tid]
        st = t["selftext"]
        if st in ("[deleted]", "[removed]"):
            st = ""
        st = st[:THREAD_SELFTEXT_CHARS]
        trows.append({"id": tid, "title": t["title"], "selftext": st,
                      "tokens": count_tokens(t["title"] + "\n\n" + st)})
    core_threads = {rows[i]["thread_id"] for i in core}
    for t in trows:
        t["tier"] = "core" if t["id"] in core_threads else "full"
    write_jsonl(DATA / "threads.jsonl", trows)

    with gzip.open(HERE / "corpus_ids.txt.gz", "wt") as f:
        for r in rows:
            f.write(f"{r['id']}\t{r['tier']}\n")

    core_rows = [r for r in rows if r["tier"] == "core"]
    tok = lambda rs: sum(r["tokens"] for r in rs)
    md = ["# Corpus composition\n",
          "Generated by `build_corpus.py`. Eligible = at least one `mentions` row and body not "
          "`[deleted]`/`[removed]`. Tags are heuristics used only for sampling and reporting; "
          "the embedded text is always thread title + comment body. A comment can carry several "
          "occasion/form/style tags, so those rows sum to more than the total.\n",
          f"- Eligible comments: {len(rows):,} ({tok(rows):,} cl100k tokens as title+body)",
          f"- Core (stratified, embedded first): {len(core_rows):,} ({tok(core_rows):,} tokens), "
          f"floor {args.floor} per stratum, seed {SEED}",
          f"- Threads: {len(trows):,} ({sum(t['tokens'] for t in trows):,} tokens, selftext cut at "
          f"{THREAD_SELFTEXT_CHARS} chars); core threads {sum(t['tier']=='core' for t in trows):,}\n",
          table(core_rows, "Core"), table(rows, "Full eligible population")]
    (HERE / "CORPUS.md").write_text("\n".join(md))
    print("\n".join(md[:6]))


if __name__ == "__main__":
    main()
