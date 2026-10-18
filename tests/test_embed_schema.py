"""schema.sql and embed_schema.sql carry the same embedding tables; keep them so.

A text check that runs anywhere. test_embed_db.py also compares the two on a
real Postgres, column by column, when one is available.
"""

import os
import re
import unittest

from fakes import ROOT

import embedding as E


def tables(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        sql = re.sub(r"--[^\n]*", "", f.read())
    out = {}
    for m in re.finditer(r"create table if not exists (\w+) \((.*?)\n\s*\);", sql, re.S):
        if m.group(1) in ("comment_embeddings", "thread_embeddings", "embedding_errors"):
            out[m.group(1)] = " ".join(m.group(2).split())
    return out


class SchemaCopies(unittest.TestCase):
    def test_same_tables_in_both_files(self):
        a, b = tables("schema.sql"), tables("embed_schema.sql")
        self.assertEqual(set(a), {"comment_embeddings", "thread_embeddings", "embedding_errors"})
        self.assertEqual(a, b)

    def test_column_dims_match_the_client(self):
        for name in ("comment_embeddings", "thread_embeddings"):
            self.assertIn(f"halfvec({E.DIMS})", tables("embed_schema.sql")[name])

    def test_no_hnsw_index_in_the_boot_schema(self):
        # Built after the backlog, by `embed.py --build-index`, never on boot.
        for path in ("schema.sql", "embed_schema.sql"):
            with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                self.assertNotIn("using hnsw", re.sub(r"--[^\n]*", "", f.read()))


if __name__ == "__main__":
    unittest.main()
