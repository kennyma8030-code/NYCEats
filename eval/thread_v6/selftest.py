"""The thread-mode harness end to end, offline: no API key, no money, no database.

    python eval/thread_v6/selftest.py

1. Every slice chunks with production's chunker, every graded item lands in a
   sent chunk, and plan.py's caps sum to at most $5.
2. eval/run.py --threads runs a small slice through the Message Batches path
   against tests/fake_anthropic.py (a local stand-in server), under a ledger
   cap. The fake answers each chunk with round 4's comment-mode medium output
   for every numbered comment, under its bracket number.
3. review.py scores that run against round 4's finals: since each target's
   output is round 4's own, it must be judged right exactly where round 4's
   was. Then packets, synthetic judges that agree with every output shown,
   check and score, all in a temporary directory.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
ROOT = os.path.dirname(EVAL)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tests"))
import chunked as TC  # noqa: E402
import fake_anthropic as F  # noqa: E402
import plan  # noqa: E402
import review as RV  # noqa: E402


def check_slices():
    for fn in sorted(os.listdir(os.path.join(HERE, "slices"))):
        if not fn.endswith(".threads.jsonl"):
            continue
        path = os.path.join(HERE, "slices", fn)
        threads = TC.load_slice(path)
        jobs = TC.jobs(path)
        graded = {i for j in jobs for i in j["item_ids"]}
        want = set()
        for th in threads:
            if th["targets"] is None:
                want |= {c["comment_id"] for c in th["comments"] if not TC.T.is_gone(c.get("body"))}
            else:
                want |= {c for c in th["targets"]
                         if not TC.T.is_gone(next(x["body"] for x in th["comments"] if x["comment_id"] == c))}
        missing = {i for i in want if not i.startswith("t3_")} - graded
        assert not missing, (fn, sorted(missing)[:5])
        assert all(len(j["covers"]) - j["chunk"]["post_item"] <= TC.T.MAX_COMMENTS for j in jobs), fn
        print(f"  {fn}: {len(jobs)} chunks, {len(graded)} graded items, all present")
    assert sum(r[-1] for r in plan.RUNS) <= plan.CEILING + 1e-9


def fake_run(tmp):
    """A 12-target fresh slice through run.py's batch path, against the fake server."""
    fresh = TC.load_slice(os.path.join(HERE, "slices", "fresh.threads.jsonl"))
    small = os.path.join(tmp, "small.threads.jsonl")
    with open(small, "w", encoding="utf-8") as f:
        for th in fresh[:12]:
            f.write(json.dumps(th, ensure_ascii=False) + "\n")
    r4 = RV.J4.raw_outputs(RV.R4_MED)
    answers = {}
    for j in TC.jobs(small):
        ms = []
        for n, i in j["id_map"].items():
            ms += [dict(m, id=n) for m in r4.get(i, [])]
        answers[j["user"]] = ms

    def answer(p):
        return F.ok(answers[p["messages"][0]["content"]])
    key = os.path.join(tmp, "key.env")
    with open(key, "w") as f:
        f.write("ANTHROPIC_API_KEY=fake\n")
    with F.FakeAnthropic(answer) as api:
        cmd = [sys.executable, os.path.join(EVAL, "run.py"), "--api", "anthropic", "--model", "claude-haiku-5-5",
               "--mode", "thread", "--schema", "--cache", "--threads", small, "--reasoning", "medium",
               "--max-tokens", "32000", "--batch", "--budget-file", os.path.join(tmp, "ledger.json"),
               "--budget", "0.05", "--poll-seconds", "0", "--tag", "fresh-selftest", "--runs-dir",
               os.path.join(tmp, "runs"), "--key-file", key, "--anthropic-base-url", api.base_url]
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        assert out.returncode == 0, out.stdout + out.stderr
        sent = api.batch_requests
    assert sent and all(r["params"]["output_config"]["effort"] == "medium" for r in sent)
    assert all(r["params"]["max_tokens"] == 32000 for r in sent)
    assert all(r["params"]["system"][0]["text"] == TC.SYSTEM_PROMPT for r in sent)
    ledger = json.load(open(os.path.join(tmp, "ledger.json"), encoding="utf-8"))
    assert ledger["spent"] <= 0.05, ledger
    run = os.path.join(tmp, "runs", os.listdir(os.path.join(tmp, "runs"))[0])
    run = run if run.endswith(".jsonl") else run.rsplit(".batches.json", 1)[0]
    print(f"  run.py: {len(sent)} chunk request(s) through the fake batch API, ledger ${ledger['spent']:.4f} of $0.05")
    return run, small


def check_review(run, tmp):
    finals, skips, _ = RV.r4_finals()
    got = RV.by_item(RV.run_chunks(run))
    r4 = RV.J4.raw_outputs(RV.R4_MED)
    n = 0
    for cid in RV.fresh_targets():
        if cid in got and ("fresh-med", cid) in finals:
            n += 1
            mine = RV.B4.equal_to_finals(got[cid][1], finals[("fresh-med", cid)])
            theirs = RV.B4.equal_to_finals(RV.B4.shown_form(r4[cid]), finals[("fresh-med", cid)])
            assert mine == theirs, cid
    print(f"  provisional: {n} targets judged exactly as round 4 judged the same output")
    RV.cmd_cost(type("A", (), {"runs": [run]})())
    # Packets, agreeable judges, check, score: in a temporary copy of the review folder.
    saved = (RV.SEALED, RV.OUT, RV.PACKETS, RV.JUDGMENTS)
    RV.OUT = os.path.join(tmp, "review")
    RV.PACKETS, RV.JUDGMENTS = os.path.join(RV.OUT, "packets"), os.path.join(RV.OUT, "judgments")
    RV.SEALED = os.path.join(tmp, ".sealed")
    shutil.copytree(os.path.join(saved[0], "r4"), os.path.join(RV.SEALED, "r4"))
    try:
        rel = os.path.relpath(run, EVAL)
        RV.cmd_packets(type("A", (), {"runs": [os.path.join(EVAL, rel)], "sample_chunks": 3})())
        for fn in os.listdir(RV.PACKETS):
            if fn.endswith(".json"):
                d = json.load(open(os.path.join(RV.PACKETS, fn), encoding="utf-8"))
                with open(os.path.join(RV.JUDGMENTS, d["packet"] + ".jsonl"), "w", encoding="utf-8") as f:
                    for it in d["items"]:
                        own = [{k: v for k, v in m.items() if k != "id"} for m in it["shown"]]
                        f.write(json.dumps({"item_id": it["item_id"], "comment_id": it["comment_id"],
                                            "own_read": own, "compare": [], "missed": [], "notes_grade": [],
                                            "rule_questions": [], "overall_item_ok": True}) + "\n")
        assert RV.cmd_check(None) == 0
        RV.cmd_score(None)
        rep = json.load(open(os.path.join(RV.OUT, "report.json"), encoding="utf-8"))
        assert rep["judged"] == rep["expected"] and not rep["problems"], rep["problems"][:3]
    finally:
        RV.SEALED, RV.OUT, RV.PACKETS, RV.JUDGMENTS = saved


def check_rubric():
    """RUBRIC_THREAD.md quotes the thread prompt's sections word for word."""
    import re
    text = open(os.path.join(HERE, "RUBRIC_THREAD.md"), encoding="utf-8").read()
    quoted = text.split("<!-- thread prompt sections: begin -->\n```text\n")[1].split("\n```\n<!--")[0]
    s = TC.SYSTEM_PROMPT
    want = "\n\n".join(re.search(rf"<{t}>\n.*?\n</{t}>", s, re.S).group(0)
                       for t in ("input", "post_item", "thread_example"))
    assert quoted == want, "RUBRIC_THREAD.md's quoted sections differ from prompts_v6/v6_thread.py"
    print("  RUBRIC_THREAD.md quotes the prompt exactly")


def check_gold(tmp):
    """score_gold.py reads a thread-slice run's coverage: an all-empty run on v1 covers every gold
    comment of the 17 threads that is still in the database, and finds nothing."""
    path = os.path.join(tmp, "empty_v1.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for j in TC.jobs(os.path.join(HERE, "slices", "v1.threads.jsonl")):
            f.write(json.dumps({"call_key": j["call_key"], "rep": 0, "item_ids": j["item_ids"], "mode": "thread",
                                "raw": '{"mentions": []}', "json_ok": True, "mentions_by_comment": {},
                                "covers": j["covers"], "chunk": j["chunk"], "usage": {}}) + "\n")
    out = subprocess.run([sys.executable, os.path.join(HERE, "score_gold.py"), "v1", path],
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    line = [x for x in out.stdout.splitlines() if x.startswith("| empty_v1")][0]
    cells = [c.strip() for c in line.strip("|").split("|")]
    assert int(cells[1]) > 300 and cells[3] == "0.000", line
    print(f"  score_gold: {cells[1]} v1 gold comments covered by the chunks")


def main():
    if not os.path.exists(os.path.join(RV.SEALED, "r4", ".sealed", "key.json")):
        RV.cmd_finals(None)
    print("rubric:")
    check_rubric()
    print("slices:")
    check_slices()
    tmp = tempfile.mkdtemp()
    try:
        print("harness:")
        run, _ = fake_run(tmp)
        print("review:")
        check_review(run, tmp)
        check_gold(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ok")


if __name__ == "__main__":
    main()
