"""schema.sql and summary_schema.sql carry the same place-summary tables; keep them so.

A text check that runs anywhere. test_summarize_db.py applies schema.sql to a
real Postgres when one is available.
"""

import os
import re
import unittest

from fakes import ROOT

BEGIN, END = "-- place-summaries-schema:begin\n", "-- place-summaries-schema:end\n"


def block(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        text = f.read()
    return text[text.index(BEGIN):text.index(END) + len(END)]


class SchemaCopies(unittest.TestCase):
    def test_same_block_in_both_files(self):
        self.assertEqual(block("schema.sql"), block("summary_schema.sql"))

    def test_only_new_tables_and_no_lock_on_anything_else(self):
        # It runs on every boot of the poller, against production: two
        # CREATE TABLE IF NOT EXISTS (checked in the catalog before any
        # lock) and nothing that alters, indexes or rewrites a table.
        sql = re.sub(r"--[^\n]*", "", block("summary_schema.sql")).lower()
        tables = re.findall(r"create table if not exists (\w+)", sql)
        self.assertEqual(tables, ["place_summaries", "summary_calls"])
        self.assertNotRegex(sql, r"\balter\b|\bindex\b|\bdrop\b|\bupdate\b|\bdelete\b|\binsert\b|references")
        self.assertEqual(len(re.findall(r"\bcreate\b", sql)), 2)

    def test_standalone_file_caps_lock_waits(self):
        with open(os.path.join(ROOT, "summary_schema.sql"), encoding="utf-8") as f:
            self.assertIn("set lock_timeout = '5s';", f.read())

    def test_v6_block_stays_last(self):
        # test_extract_v6_schema requires the v6 block to end schema.sql.
        with open(os.path.join(ROOT, "schema.sql"), encoding="utf-8") as f:
            text = f.read()
        self.assertLess(text.index(END), text.index("-- v6-extraction-schema:begin"))


if __name__ == "__main__":
    unittest.main()
