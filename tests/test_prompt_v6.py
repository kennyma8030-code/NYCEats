"""Production's v6 prompt is the benchmarked round 4, byte for byte. No database, no network.

prompts_v6/ holds copies of the benchmark branch's files. These tests pin
their hashes, and, where the extraction-v6 branch is in this repository,
compare them with it directly, so a silent edit to either side fails here.
They also render a set of hand-built comment records with production's
renderer and the benchmark's and compare the bytes.
"""

import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

from fakes import ROOT

import prompt_v6

BRANCH = "extraction-v6"
# sha256 of each vendored file as committed on extraction-v6 (round 4).
PINNED = {
    "v6_common.py": "34d3f022ec6d05f475095ba8c0a92b5cb3306c2909ca4068deb5735833a5fb82",
    "v6_comment.py": "03f99234d259754da1bf07a315cf83e1d6b74bc5ef3df5649189dc05a4f0c5e1",
    "v6_schema.json": "e43496c297abadcf0c75f9c2562aa95ae3e3fe5e3f229dd156a3a9b7482382ba",
    "v6_adapter.py": "eed7001389d866356ea4825af7149b8d45fb69bf4a936272b0f3258d30dfe99d",
}
ON_BRANCH = {"v6_common.py": "eval/prompts/v6_common.py", "v6_comment.py": "eval/prompts/v6_comment.py",
             "v6_schema.json": "eval/prompts/v6_schema.json", "v6_adapter.py": "eval/v6_adapter.py"}


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def branch_file(path):
    """The file's bytes on the benchmark branch, or None when the branch is not here."""
    r = subprocess.run(["git", "-C", ROOT, "show", f"{BRANCH}:{path}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def benchmark_module():
    """eval/prompts/v6_comment.py as the benchmark ran it: loaded from the branch
    when it is here, else from the vendored copy (whose bytes are pinned above)."""
    blobs = {n: branch_file(p) for n, p in ON_BRANCH.items() if n != "v6_adapter.py"}
    d = tempfile.mkdtemp()
    for n, b in blobs.items():
        src = b if b is not None else open(os.path.join(ROOT, "prompts_v6", n), "rb").read()
        with open(os.path.join(d, n), "wb") as f:
            f.write(src)
    spec = importlib.util.spec_from_file_location("bench_v6_comment", os.path.join(d, "v6_comment.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Hashes(unittest.TestCase):
    def test_prompt_hashes_are_round_four(self):
        self.assertEqual(prompt_v6.PROMPT_HASH, "979dcd6b9267")
        self.assertEqual(prompt_v6.PROMPT_HASH_POST, "436d834d7edd")
        for text, h in ((prompt_v6.SYSTEM_PROMPT, prompt_v6.PROMPT_HASH),
                        (prompt_v6.SYSTEM_PROMPT_POST, prompt_v6.PROMPT_HASH_POST)):
            self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], h)

    def test_vendored_files_are_pinned(self):
        for name, want in PINNED.items():
            self.assertEqual(sha(os.path.join(ROOT, "prompts_v6", name)), want, name)

    def test_vendored_files_match_the_branch(self):
        found = 0
        for name, path in ON_BRANCH.items():
            blob = branch_file(path)
            if blob is None:
                continue
            found += 1
            with open(os.path.join(ROOT, "prompts_v6", name), "rb") as f:
                self.assertEqual(f.read(), blob, f"prompts_v6/{name} differs from {BRANCH}:{path}")
        if not found:
            self.skipTest(f"branch {BRANCH} is not in this repository; the pinned hashes still apply")

    def test_schema_equals_the_branch(self):
        blob = branch_file(ON_BRANCH["v6_schema.json"])
        if blob is None:
            self.skipTest(f"branch {BRANCH} is not in this repository")
        self.assertEqual(prompt_v6.SCHEMA, json.loads(blob))

    def test_settings_are_the_benchmarks(self):
        self.assertEqual((prompt_v6.MODEL, prompt_v6.EFFORT, prompt_v6.MAX_TOKENS),
                         ("claude-haiku-5-5", "medium", 16000))


def rec(body, author="me", ancestors=(), total=None, title="Best dumplings?", selftext="Looking for spots.",
        thread_author="op"):
    chain = list(ancestors)
    return {"call_key": "comment:t1_x", "comment_id": "t1_x", "thread_id": "t3_x", "author": author,
            "body": body, "title": title, "selftext": selftext, "thread_author": thread_author,
            "ancestors": chain, "ancestors_total": len(chain) if total is None else total}


def anc(i, author="someone", body=None, state="ok"):
    return {"id": f"t1_a{i}", "author": author, "body": body if body is not None else f"ancestor {i}",
            "state": state}


RECORDS = [
    rec("keens"),
    rec("+1"),
    rec("Golden Lotus, obviously", selftext=None),
    rec("x", selftext="[removed]"),
    rec("long post", selftext="word " * 600, title="  A   title\nwith  breaks  "),
    rec("I wrote this post", author="op"),
    rec("> they said Copperline is mid\n> second line\n\nhard disagree, it's great\n>trailing quote"),
    rec("reply", ancestors=[anc(1, author="op"), anc(2, author="me"), anc(3)]),
    rec("reply to deleted", ancestors=[anc(1, state="deleted", body=None)]),
    rec("reply to missing", ancestors=[{"id": "t1_gone", "author": None, "body": None, "state": "missing"},
                                       anc(2)]),
    rec("deep", ancestors=[anc(i) for i in range(1, 7)], total=9),
    rec("long parent", ancestors=[anc(1, body="grandparent " * 60), anc(2, body="parent " * 400)]),
    rec("[deleted] author", author="[deleted]", thread_author="[deleted]"),
    rec("unicode 南翔 🥟 très", ancestors=[anc(1, body="line one\r\nline\ttwo")]),
]


class Rendering(unittest.TestCase):
    def test_comment_rendering_matches_the_benchmark(self):
        bench = benchmark_module()
        for r in RECORDS:
            self.assertEqual(prompt_v6.build_user_message(r), bench.build_user_message(r), r["body"])
        self.assertEqual(prompt_v6.SYSTEM_PROMPT, bench.SYSTEM_PROMPT)
        self.assertEqual(prompt_v6.SYSTEM_PROMPT_POST, bench.SYSTEM_PROMPT_POST)

    def test_input_format(self):
        m = prompt_v6.build_user_message(RECORDS[7])
        self.assertIn('<post_title>Best dumplings?</post_title>', m)
        self.assertIn("[1] OP: ancestor 1", m)
        self.assertIn("[2] you, earlier: ancestor 2", m)
        self.assertIn("[3] another user: ancestor 3", m)
        self.assertTrue(m.endswith("<comment_to_extract>\nreply\n</comment_to_extract>"))
        self.assertIn('author="you"', prompt_v6.build_user_message(RECORDS[5]))
        self.assertIn("(4 earlier comments not shown)", prompt_v6.build_user_message(RECORDS[10]))
        self.assertIn("(a deleted comment)", prompt_v6.build_user_message(RECORDS[8]))
        self.assertIn("(a comment that is not available)", prompt_v6.build_user_message(RECORDS[9]))
        self.assertIn("<quote>they said Copperline is mid second line</quote>",
                      prompt_v6.build_user_message(RECORDS[6]))
        body = prompt_v6.build_user_message(RECORDS[4]).split("<post_body>")[1].split("</post_body>")[0]
        self.assertEqual(len(body), 1200 - 1 + 4)       # cut at 1,200, trailing space stripped, " ..."

    def test_post_mode(self):
        bench = benchmark_module()
        for title, body in (("Is PlaceAlpha worth it?", "Thinking of going " * 400), ("Title only", None),
                            ("Removed", "[removed]")):
            self.assertEqual(prompt_v6.render("post", (title, body, "op"))[1], bench.build_post_message(title, body))
        system, user, h = prompt_v6.render("post", ("Is PlaceAlpha worth it?", "Going Friday", "op"))
        self.assertEqual((system, h), (prompt_v6.SYSTEM_PROMPT_POST, "436d834d7edd"))
        self.assertEqual(user, "<post_title>Is PlaceAlpha worth it?</post_title>\n<post_body>Going Friday</post_body>")


if __name__ == "__main__":
    unittest.main()
