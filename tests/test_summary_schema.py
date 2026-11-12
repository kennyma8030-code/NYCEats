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
        # It runs on every boot of the poller, against production: CREATE
        # TABLE IF NOT EXISTS (checked in the catalog before any lock), and
        # nothing that indexes, rewrites or alters a table but its own,
        # behind a catalog check.
        sql = re.sub(r"--[^\n]*", "", block("summary_schema.sql")).lower()
        tables = re.findall(r"create table if not exists (\w+)", sql)
        self.assertEqual(tables, ["place_summaries", "summary_calls", "summary_state"])
        self.assertEqual(len(re.findall(r"\bcreate\b", sql)), 3)
        self.assertNotRegex(sql, r"\bindex\b|\bupdate\b|\bdelete\b|\binsert\b|references")
        alters = re.findall(r"alter table (\w+) add column if not exists (\w+)", sql)
        self.assertEqual(alters, [("place_summaries", "seen_comment_ids"), ("place_summaries", "subreddit"),
                                  ("summary_calls", "subreddit")])
        # each ALTER sits behind a catalog check for the very column it adds
        for table, col in alters:
            self.assertRegex(sql, rf"if not exists \(select 1 from information_schema\.columns[^;]*"
                                  rf"table_name = '{table}'[^;]*column_name = '{col}'\) then\s*alter table {table}")
        # The one change that is not a new column: the key grows a city, once,
        # in the same guarded block as the column it is keyed by, so a table
        # that has the column never reaches it.
        rekey = (r"alter table place_summaries add column if not exists subreddit [^;]*;\s*"
                 r"alter table place_summaries drop constraint place_summaries_pkey;\s*"
                 r"alter table place_summaries add primary key \(subreddit, resolved_key\);\s*end if;")
        self.assertRegex(sql, rekey)
        self.assertEqual(len(re.findall(r"\bdrop\b", sql)), 1)
        self.assertEqual(len(re.findall(r"\balter\b", sql)), 5)
        self.assertIn("set_config('lock_timeout', '5s', true)", sql)

    def test_every_later_column_is_in_the_upgrade(self):
        # A column added after the first version (423c941) must also be in a
        # guarded ALTER, or re-applying the file would not upgrade an old table.
        first = {"resolved_key", "summary", "model", "prompt_hash", "mention_count", "last_mention_at",
                 "input_comments", "input_chars", "written_at", "cost_usd", "usage", "attempts", "error",
                 "failed_at", "updated_at"}
        sql = re.sub(r"--[^\n]*", "", block("summary_schema.sql"))
        body = re.search(r"create table if not exists place_summaries \((.*?)\n\);", sql, re.S).group(1)
        cols = {line.split()[0] for line in body.strip().splitlines()} - {"primary"}    # the key's own line
        added = {c for _, c in re.findall(r"alter table (\w+) add column if not exists (\w+)", sql)}
        self.assertEqual(cols - first, added)

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
