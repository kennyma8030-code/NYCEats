"""Render eval/results/comparison.json as a standalone HTML report.

    python eval/report.py [out.html]

Every number on the page comes from comparison.json; nothing is typed in.
"""

import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
C = json.load(open(os.path.join(HERE, "results", "comparison.json"), encoding="utf-8"))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "results", "report.html")

PROMPT_NAME = {"original": "original prompt", "revised": "Oct 2 prompt", "rubric_v1": "rubric_v1 prompt"}
COLS = [  # key, header, higher_is_better, kind
    ("drop_rate", "Comments dropped", False, "pct"),
    ("mention_recall", "Places caught", True, "pct"),
    ("negative_mention_recall", "Negatives caught", True, "pct"),
    ("value_complaint_recall", "“Overpriced” caught", True, "pct"),
    ("dish_negative_recall", "Dish negatives caught", True, "pct"),
    ("mention_precision", "Precision", True, "pct"),
]
WEAK = {  # weakness -> (metric that measures it, plain name)
    "dropped_nameless_reply": ("mention_recall", "Reply judges a place without naming it"),
    "missed_negative": ("negative_mention_recall", "Negative opinion missed"),
    "negative_softened_to_positive": ("negative_mention_recall", "Negative read as positive"),
    "softened_negative": ("negative_mention_recall", "Complaint scored milder than written"),
    "missed_value_complaint": ("value_complaint_recall", "“Overpriced” missed"),
    "missed_dish_negative": ("dish_negative_recall", "“Skip the X” missed"),
    "dropped_in_list": ("mention_recall", "Place in a long list dropped"),
    "dropped_reference_mention": ("mention_recall", "Question / “haven't been” mention dropped"),
    "negation_scope": ("negative_mention_recall", "“Avoid these:” not applied to every name"),
    "wrong_target": ("mention_recall", "Opinion attached to the wrong place"),
    "context_gap": ("mention_recall", "Needs context the mode doesn't show"),
}


def esc(s):
    return html.escape(str(s))


def label(row):
    if "file" not in row:
        return "Production today", "stored output (DeepSeek v4-flash, mostly thread mode)"
    m = C["runs"][row["file"]]
    return m["model"].split("/", 1)[1], PROMPT_NAME.get(m["prompt"], m["prompt"])


def scope(metrics, prefer):
    for s in prefer:
        if metrics.get(s):
            return metrics[s]
    return {}


def fmt(v, kind="pct"):
    if v is None or v == "n/a":
        return "—"
    if kind == "pct":
        return f"{v * 100:.0f}%"
    if kind == "usd":
        return f"${v:.2f}"
    return str(v)


def cell_class(vals, v, hib):
    """Best and worst in a column, for highlighting."""
    nums = [x for x in vals if isinstance(x, (int, float))]
    if not isinstance(v, (int, float)) or len(nums) < 2:
        return ""
    best = max(nums) if hib else min(nums)
    worst = min(nums) if hib else max(nums)
    return "best" if v == best else "worst" if v == worst else ""


def composite(o):
    """The owner's priorities, equally weighted: keep comments, catch places, catch negatives, catch value complaints."""
    parts = [1 - (o.get("drop_rate") or 0), o.get("mention_recall"), o.get("negative_mention_recall"),
             o.get("value_complaint_recall")]
    parts = [p for p in parts if isinstance(p, (int, float))]
    return sum(parts) / len(parts) if parts else None


def table(rows, prefer, with_cost=True):
    data = []
    for r in rows:
        o = scope(r["metrics"], prefer)
        name, sub = label(r)
        cost = C["runs"][r["file"]].get("cost_per_1k_comments") if "file" in r else None
        data.append((name, sub, o, cost))
    head = "".join(f"<th>{esc(h)}</th>" for _, h, _, _ in COLS)
    out = [f"<div class='tw'><table><thead><tr><th class='l'>Model</th>{head}"
           + ("<th>$ per 1,000 comments</th>" if with_cost else "") + "</tr></thead><tbody>"]
    for name, sub, o, cost in data:
        tds = []
        for key, _, hib, kind in COLS:
            vals = [d[2].get(key) for d in data]
            v = o.get(key)
            tds.append(f"<td class='{cell_class(vals, v, hib)}'>{fmt(v, kind)}</td>")
        if with_cost:
            tds.append(f"<td>{fmt(cost, 'usd') if cost else '—'}</td>")
        prod = " prod" if name == "Production today" else ""
        out.append(f"<tr class='r{prod}'><th class='l'><b>{esc(name)}</b><span>{esc(sub)}</span></th>{''.join(tds)}</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def hist_bar(hstr):
    """'-3:3 -2:52 ... +3:15' -> a 7-bar SVG of how often each level is used."""
    counts = {int(k): int(v) for k, v in (p.split(":") for p in (hstr or "").split())}
    total = sum(counts.values()) or 1
    w, h, gap = 22, 54, 6
    bars = []
    for i, lv in enumerate(range(-3, 4)):
        share = counts.get(lv, 0) / total
        bh = max(1.5, share * h) if counts.get(lv) else 0
        x = i * (w + gap)
        cls = "neg" if lv < 0 else "pos" if lv > 0 else "mid"
        bars.append(f"<rect class='{cls}' x='{x}' y='{h - bh:.1f}' width='{w}' height='{bh:.1f}' rx='2'/>"
                    f"<text x='{x + w / 2}' y='{h + 13}'>{lv:+d}</text>")
    return (f"<svg class='hist' viewBox='0 0 {7 * (w + gap) - gap} {h + 16}' role='img' "
            f"aria-label='Share of scores at each level from -3 to +3'>{''.join(bars)}</svg>")


# ---------------------------------------------------------------- content
cf, tf, v2 = C["panels"]["comment_full"], C["panels"]["thread_full"], C["panels"]["v2"]
RW, TH = ["reweighted", "overall"], ["threads", "overall"]
REC_C = "openai_gpt-6-luna__3a6940dd5cc1__comment.jsonl"        # recommendation, comment mode
REC_T = "openai_gpt-6-luna__bd4467215908__thread.jsonl"         # recommendation, thread mode
DS_ORIG_T = "deepseek_deepseek-v4-flash__ca5439be83b3__thread.jsonl"
DS_FIX_T = "deepseek_deepseek-v4-flash__5b02ac883c80__thread.jsonl"
DS_RUB_T = "deepseek_deepseek-v4-flash__bd4467215908__thread.jsonl"
DS_FIX_C = "deepseek_deepseek-v4-flash__0d75b20b5f83__comment.jsonl"
SONNET = "anthropic_claude-sonnet-5.5__3a6940dd5cc1__comment.jsonl"


def row(panel, file=None):
    rows = panel["rows"] if isinstance(panel, dict) else panel
    return next(r for r in rows if r.get("file") == file)


def cost(file):
    return C["runs"][file].get("cost_per_1k_comments")


prod_c, prod_t = scope(row(cf)["metrics"], RW), scope(row(tf)["metrics"], TH)
rec_c, rec_t = scope(row(cf, REC_C)["metrics"], RW), scope(row(tf, REC_T)["metrics"], TH)
fix_t, orig_t = scope(row(tf, DS_FIX_T)["metrics"], TH), scope(row(tf, DS_ORIG_T)["metrics"], TH)
fix_c = scope(row(cf, DS_FIX_C)["metrics"], RW)
son = next((p for p in C["panels"]["partial"] if p["file"] == SONNET), None)
son_o = scope(son["metrics"], ["overall"]) if son else {}
n_neg = scope(row(cf)["metrics"], ["overall"]).get("neg_mention_n")
n_vc = scope(row(cf)["metrics"], ["overall"]).get("vc_n")
spent = sum(m.get("cost_total", 0) for m in C["runs"].values())

kpis = [("Comments dropped", prod_c.get("drop_rate"), rec_c.get("drop_rate")),
        ("Places caught", prod_c.get("mention_recall"), rec_c.get("mention_recall")),
        ("Negatives caught", prod_c.get("negative_mention_recall"), rec_c.get("negative_mention_recall")),
        ("“Overpriced” caught", prod_c.get("value_complaint_recall"), rec_c.get("value_complaint_recall")),
        ("“Skip the X” caught", None, rec_c.get("dish_negative_recall"))]
kpi_html = "".join(f"<div class='kpi'><span class='k'>{esc(k)}</span><span class='v'><s>{fmt(a)}</s> → <b>{fmt(b)}</b></span></div>"
                   for k, a, b in kpis)

# the prompt effect: one model, the same 17 threads, three prompts
pe_rows = [("Production today", "stored output", prod_t, None),
           ("DeepSeek v4-flash", "original prompt, re-run", orig_t, cost(DS_ORIG_T)),
           ("DeepSeek v4-flash", "Oct 2 prompt", fix_t, cost(DS_FIX_T)),
           ("DeepSeek v4-flash", "rubric_v1 prompt", scope(row(tf, DS_RUB_T)["metrics"], TH), cost(DS_RUB_T))]
pe_html = "".join(
    f"<tr><th class='l'><b>{esc(a)}</b><span>{esc(b)}</span></th><td>{fmt(o.get('drop_rate'))}</td>"
    f"<td>{fmt(o.get('mention_recall'))}</td><td>{fmt(o.get('negative_mention_recall'))}</td>"
    f"<td>{fmt(c, 'usd') if c else '—'}</td></tr>" for a, b, o, c in pe_rows)

partial_rows = []
for p in sorted(C["panels"]["partial"], key=lambda p: -p["n_comments"]):
    o, b = scope(p["metrics"], ["overall"]), scope(p.get("baseline", {}), ["overall"])
    name, sub = label(p)

    def d(key):
        if not isinstance(o.get(key), (int, float)) or not isinstance(b.get(key), (int, float)):
            return ""
        diff = (o[key] - b[key]) * 100
        good = diff < 0 if key == "drop_rate" else diff > 0
        cls = "up" if good and abs(diff) >= 2 else "down" if not good and abs(diff) >= 2 else ""
        return f"<span class='{cls}'>{diff:+.0f}</span>"
    c = cost(p["file"])
    partial_rows.append(
        f"<tr><th class='l'><b>{esc(name)}</b><span>{esc(sub)}</span></th><td>{p['n_comments']}</td>"
        f"<td>{fmt(o.get('drop_rate'))} {d('drop_rate')}</td><td>{fmt(o.get('mention_recall'))} {d('mention_recall')}</td>"
        f"<td>{fmt(o.get('negative_mention_recall'))} {d('negative_mention_recall')}</td><td>{fmt(c, 'usd') if c else '—'}</td></tr>")

wcols = v2["rows"]
wrows = []
for w, (metric, plain) in WEAK.items():
    if not any(w in r["metrics"] for r in wcols):
        continue
    tds = []
    for r in wcols:
        v = (r["metrics"].get(w) or {}).get(metric)
        tds.append(f"<td class='heat' style='--h:{v:.3f}'>{fmt(v)}</td>" if isinstance(v, (int, float)) else "<td class='na'>—</td>")
    n = next(((r["metrics"].get(w) or {}).get("comments") for r in wcols if r["metrics"].get(w)), "")
    wrows.append(f"<tr><th class='l'><b>{esc(plain)}</b><span>{n} comments</span></th>{''.join(tds)}</tr>")
whead = "".join(f"<th><b>{esc(label(r)[0])}</b><span>{esc(label(r)[1])}</span></th>" for r in wcols)


def share_at(hstr, lv):
    counts = {int(k): int(v) for k, v in (p.split(":") for p in (hstr or "").split())}
    return counts.get(lv, 0) / (sum(counts.values()) or 1)


h_prod = scope(row(cf)["metrics"], ["overall"]).get("level_histogram")
h_rec = scope(row(cf, REC_C)["metrics"], ["overall"]).get("level_histogram")
per100k = lambda f: (cost(f) or 0) * 100

page = f"""<title>NYCEats Extraction Benchmark</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap">
<style>
:root {{
  --bg:#F6F7F5; --surface:#FFFFFF; --ink:#15171A; --mute:#5F646B; --faint:#9DA2A8; --line:#E3E4E0; --cell:#EEEFEC;
  --accent:#0A7C66; --accent-soft:#E2F2EC; --bad:#C2410C; --bad-soft:#FBEADF;
  --sans:"Geist", system-ui, -apple-system, "Segoe UI", sans-serif; --mono:"Geist Mono", ui-monospace, Menlo, monospace;
  --serif:"Newsreader", Georgia, "Times New Roman", serif;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  color-scheme:dark; --bg:#1C1B19; --surface:#242321; --ink:#EDECE8; --mute:#A6A39D; --faint:#6E6B66; --line:#34322F; --cell:#2B2A27;
  --accent:#3FCBA0; --accent-soft:#173A30; --bad:#F28A5B; --bad-soft:#3D2418 }} }}
:root[data-theme="dark"] {{
  color-scheme:dark; --bg:#1C1B19; --surface:#242321; --ink:#EDECE8; --mute:#A6A39D; --faint:#6E6B66; --line:#34322F; --cell:#2B2A27;
  --accent:#3FCBA0; --accent-soft:#173A30; --bad:#F28A5B; --bad-soft:#3D2418 }}
* {{ box-sizing:border-box }}
body {{ background:var(--bg); color:var(--ink); font:15px/1.55 var(--sans); padding-inline:clamp(16px, 4vw, 48px); -webkit-font-smoothing:antialiased }}
main {{ max-width:1080px; margin:0 auto; padding-block:40px 80px; display:grid; gap:56px }}
section {{ display:grid; gap:14px; min-width:0 }}
.eyebrow {{ font-family:var(--mono); font-size:11.5px; letter-spacing:.07em; text-transform:uppercase; color:var(--faint); margin:0 0 10px }}
h1 {{ font-family:var(--serif); font-weight:400; font-size:clamp(34px, 5vw, 54px); line-height:1.04; letter-spacing:-.025em; margin:0; text-wrap:balance; max-width:20ch }}
h1 em {{ font-style:normal; color:var(--accent) }}
h2 {{ font-family:var(--serif); font-weight:400; font-size:28px; letter-spacing:-.015em; line-height:1.15; margin:0; text-wrap:balance }}
p {{ margin:0; max-width:70ch }}
.lede {{ font-size:17px; color:var(--mute); margin-top:16px; max-width:66ch }}
.lede b {{ color:var(--ink); font-weight:600 }}
.sub {{ color:var(--mute) }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:1px; background:var(--line); border:1px solid var(--line); border-radius:12px; overflow:hidden; margin-top:28px }}
.kpi {{ background:var(--surface); padding:16px 18px; display:grid; gap:4px }}
.kpi .k {{ font-size:12.5px; color:var(--mute) }}
.kpi .v {{ font-family:var(--mono); font-size:21px; font-variant-numeric:tabular-nums; letter-spacing:-.02em; white-space:nowrap }}
.kpi s {{ color:var(--faint); text-decoration-thickness:1px }}
.kpi b {{ color:var(--accent); font-weight:500 }}
.tw {{ overflow-x:auto; border:1px solid var(--line); border-radius:12px; background:var(--surface) }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; font-size:14px }}
th, td {{ padding:10px 12px; text-align:right; border-bottom:1px solid var(--line); white-space:nowrap }}
thead th {{ font-size:11.5px; font-weight:500; color:var(--mute); vertical-align:bottom; white-space:normal; min-width:84px; line-height:1.3 }}
thead th span, th.l span {{ display:block; font-weight:400; color:var(--faint); font-size:12px }}
th.l {{ text-align:left; font-weight:400; min-width:200px }}
th.l b {{ font-weight:600 }}
tbody tr:last-child > * {{ border-bottom:0 }}
td {{ font-family:var(--mono); font-size:13.5px }}
td.best {{ color:var(--accent); font-weight:500; background:var(--accent-soft) }}
td.worst {{ color:var(--bad) }}
tr.prod th.l b::after {{ content:"today"; margin-left:8px; font:500 10.5px var(--mono); letter-spacing:.05em; text-transform:uppercase; color:var(--bad); background:var(--bad-soft); padding:2px 6px; border-radius:4px; vertical-align:2px }}
td.heat {{ background:color-mix(in oklab, var(--accent) calc(var(--h) * 45%), color-mix(in oklab, var(--bad) calc((1 - var(--h)) * 35%), var(--surface))) }}
td.na {{ color:var(--faint) }}
.up {{ color:var(--accent); font-size:12px }} .down {{ color:var(--bad); font-size:12px }}
.hists {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:24px }}
.hists figure {{ margin:0; display:grid; gap:8px; border:1px solid var(--line); border-radius:12px; background:var(--surface); padding:18px 20px }}
.hists figcaption {{ font-size:13.5px; color:var(--mute) }}
.hists figcaption b {{ color:var(--ink); font-weight:600 }}
svg.hist {{ width:100%; max-width:260px; height:auto; overflow:visible }}
svg.hist rect.neg {{ fill:var(--bad) }} svg.hist rect.pos {{ fill:var(--accent) }} svg.hist rect.mid {{ fill:var(--faint) }}
svg.hist text {{ font:10px var(--mono); fill:var(--faint); text-anchor:middle }}
.cols2 {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:24px }}
.box {{ border:1px solid var(--line); border-radius:12px; background:var(--surface); padding:20px 22px; display:grid; gap:10px; align-content:start }}
.box h3 {{ margin:0; font-size:15px; font-weight:600 }}
.box ol, .box ul {{ margin:0; padding-left:20px; display:grid; gap:8px; color:var(--mute) }}
.box li b {{ color:var(--ink); font-weight:600 }}
code {{ font-family:var(--mono); font-size:12.5px; background:var(--cell); padding:1px 5px; border-radius:4px }}
.note {{ font-size:13px; color:var(--faint) }}
</style>

<main>
<header>
  <p class="eyebrow">NYCEats · extraction benchmark · {C['gold']['comments']} hand-labeled r/FoodNYC comments</p>
  <h1>Fix the prompt, then switch to <em>GPT-6 Luna</em></h1>
  <p class="lede">Scored on what you use Reddit for: <b>how many people talk about a place</b> and <b>the negatives</b>. Today's extraction drops {fmt(prod_c.get('drop_rate'))} of comments that mention a restaurant, {fmt(prod_t.get('drop_rate'))} inside whole threads, where 88% of your data was extracted. It catches {fmt(prod_c.get('negative_mention_recall'))} of negative opinions.</p>
  <div class="kpis">{kpi_html}</div>
  <p class="note" style="margin-top:10px">Today → GPT-6 Luna with the rubric_v1 prompt. Single-comment mode, weighted to match real traffic. Today's prompt has no way to report dish-level complaints.</p>
</header>

<section>
  <h2>Most of the damage is the prompt</h2>
  <p class="sub">Same model, same 17 threads, three prompts. The original prompt is what loses replies like “v mid” under a named place. The Oct 2 prompt fixes most of it, but production has run it on only 371 comments.</p>
  <div class="tw"><table><thead><tr><th class="l">Configuration</th><th>Comments dropped</th><th>Places caught</th><th>Negatives caught</th><th>$ per 1,000 comments</th></tr></thead><tbody>{pe_html}</tbody></table></div>
</section>

<section>
  <h2>Every complete configuration, single comments</h2>
  <p class="sub">The {cf['n_comments']} comments every row finished, weighted to real traffic. Green is the best in each column. The sample holds {n_neg} negative opinions and only {n_vc} “overpriced” complaints, so read that column loosely.</p>
  {table(cf['rows'], RW)}
</section>

<section>
  <h2>Whole threads</h2>
  <p class="sub">Thread mode reads up to 25 comments per call, so it costs less per comment. {tf['n_comments']} comments across 17 complete threads.</p>
  {table(tf['rows'], TH)}
</section>

<section>
  <h2>Where today's extraction fails</h2>
  <p class="sub">Confirmed failures of today's extraction, grouped by cause. Each cell is the share that configuration gets right on those same comments.</p>
  <div class="tw"><table><thead><tr><th class="l">Failure</th>{whead}</tr></thead><tbody>{''.join(wrows)}</tbody></table></div>
</section>

<section>
  <h2>How the scores spread</h2>
  <p class="sub">Every aspect score, from −3 (never again) to +3 (best in the city).</p>
  <div class="hists">
    <figure>{hist_bar(h_prod)}<figcaption><b>Production today.</b> {fmt(share_at(h_prod, 1))} of scores sit at +1, the “named with nothing said” default.</figcaption></figure>
    <figure>{hist_bar(h_rec)}<figcaption><b>GPT-6 Luna, rubric_v1.</b> {fmt(share_at(h_rec, 1))} at +1; more opinions land at clear praise or clear complaint.</figcaption></figure>
  </div>
</section>

<section>
  <h2>Bigger models, partial runs</h2>
  <p class="sub">These stopped early when the API key hit its limit. Each is scored only on the comments it finished; the small number after a score is the difference in points from DeepSeek v4-flash with the same prompt on those same comments.</p>
  <div class="tw"><table><thead><tr><th class="l">Model</th><th>Comments</th><th>Comments dropped</th><th>Places caught</th><th>Negatives caught</th><th>$ per 1,000</th></tr></thead><tbody>{''.join(partial_rows)}</tbody></table></div>
</section>

<section class="cols2">
  <div class="box">
    <h3>What to do</h3>
    <ol>
      <li><b>Re-extract what's stored.</b> 88% of extracted comments went through the original thread prompt, which drops about half the comments in a thread. Re-running them is the largest single improvement to the board.</li>
      <li><b>Use GPT-6 Luna with rubric_v1.</b> It drops {fmt(rec_c.get('drop_rate'))} of comments one at a time and {fmt(rec_t.get('drop_rate'))} in threads, and catches {fmt(rec_t.get('dish_negative_recall'))} of “skip the X” complaints in threads. Thread mode costs about ${per100k(REC_T):.0f} per 100,000 comments.</li>
      <li><b>Cheapest acceptable option:</b> keep DeepSeek v4-flash and switch the backlog to the Oct 2 thread prompt, about ${per100k(DS_FIX_T):.0f} per 100,000 comments. It loses dish-level complaints and catches {fmt(fix_c.get('negative_mention_recall'))} of negatives one comment at a time.</li>
      <li><b>Check Luna's extra mentions.</b> Its precision is {fmt(rec_c.get('mention_precision'))} against {fmt(fix_c.get('mention_precision'))} for DeepSeek with the Oct 2 prompt; spot-check before trusting raw mention counts.</li>
      <li><b>Give backfills their own OpenRouter key</b> with its own limit, so a re-extraction can never block the live worker.</li>
    </ol>
  </div>
  <div class="box">
    <h3>How this was measured</h3>
    <ul>
      <li><b>{C['gold']['comments']} comments, {C['gold']['mentions']} mentions</b>, labeled blind from the full thread on a 7-level scale, then checked against today's output (23 label corrections).</li>
      <li>75% chosen for risk (nameless replies, avoid-lists, strong negatives, long lists, deep chains), 25% at random; single-comment scores are weighted back to real traffic.</li>
      <li>Every configuration gets the exact input production sends. Comparisons use only comments every row finished.</li>
      <li>Sonnet 5.5 caught {fmt(son_o.get('negative_mention_recall'))} of negatives on the {son['n_comments'] if son else 0} comments it finished. At about ${per100k(SONNET):.0f} per 100,000 comments it shows the ceiling rather than a candidate.</li>
      <li>Model calls cost ${spent:.2f}. The run shared production's OpenRouter key and exhausted its limit on Oct 4, which paused live extraction until credit was added.</li>
      <li>Everything is in <code>eval/</code> on branch <code>eval-extraction</code>; rerun with <code>run.py</code>, <code>compare.py</code>, <code>report.py</code>.</li>
    </ul>
  </div>
</section>
</main>
"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(page)
print(OUT)
