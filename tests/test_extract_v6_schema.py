"""schema.sql and extract_v6_schema.sql carry the same v6 block; keep them so.

A text check that runs anywhere. test_extract_v6_db.py applies both to a real
Postgres when one is available.
"""

import os
import re
import unittest

from fakes import ROOT

BEGIN, END = "-- v6-extraction-schema:begin\n", "-- v6-extraction-schema:end\n"


def block(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        text = f.read()
    return text[text.index(BEGIN):text.index(END) + len(END)]


class SchemaCopies(unittest.TestCase):
    def test_same_block_in_both_files(self):
        self.assertEqual(block("schema.sql"), block("extract_v6_schema.sql"))

    def test_block_is_last_in_schema_sql(self):
        # It alters mentions and reads threads, so it must run after both exist.
        with open(os.path.join(ROOT, "schema.sql"), encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.rstrip("\n").endswith(END.rstrip("\n")))
        self.assertLess(text.index("create table if not exists mentions"), text.index(BEGIN))

    def test_every_change_is_guarded(self):
        # It runs on every boot of the poller, against production.
        sql = re.sub(r"--[^\n]*", "", block("extract_v6_schema.sql")).lower()
        for m in re.finditer(r"\bcreate (unique index|index|table|view|or replace view)\b([^;]*)", sql):
            # A table may use IF NOT EXISTS. Anything else sits inside a
            # catalog check that skips it (and its lock) once it exists: CREATE
            # INDEX IF NOT EXISTS takes its SHARE lock before it looks. CREATE
            # OR REPLACE only behind a check of the current definition, or it
            # takes an exclusive lock on every boot.
            before = sql[max(0, m.start() - 250):m.start()]
            if m.group(1) == "table":
                guarded = m.group(2).lstrip().startswith("if not exists")
            elif m.group(1) == "or replace view":
                guarded = re.search(r"is null\s+or\s+position\([^;]*pg_get_viewdef[^;]*\)\s*=\s*0\s+then\s*$",
                                    before) is not None
            else:
                guarded = re.search(r"to_regclass\('[a-z_]+'\) is null then\s*(begin\s*)?$", before) is not None
            self.assertTrue(guarded, m.group(0)[:80])
        self.assertIn("set_config('lock_timeout', '5s', true)", sql)
        self.assertNotRegex(sql, r"drop (table|view|index|constraint|column)")
        self.assertNotRegex(sql, r"\bupdate\b|\bdelete\b|\btruncate\b")
        self.assertIn("on conflict do nothing", sql)


if __name__ == "__main__":
    unittest.main()
