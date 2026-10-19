"""'FoodNYC' is spelled in SQL that cannot import subreddits.HOME. Every copy
must agree with it, or one reader quietly starts counting the wrong city."""

import os
import re
import unittest

from fakes import ROOT

import db
import subreddits


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def code(sql):
    """The SQL without its comments, so prose about r/FoodNYC is not counted."""
    return re.sub(r"--[^\n]*", "", sql)


class HomeLiteral(unittest.TestCase):
    def test_home_is_one_of_the_polled(self):
        self.assertEqual(subreddits.SUBREDDITS[0], subreddits.HOME)

    def test_scoring_params(self):
        self.assertRegex(code(read("scoring.sql")),
                         rf"'{subreddits.HOME}'::text\s+as\s+subreddit\s*;")

    def test_schema_default_seed_and_index(self):
        sql = code(read("schema.sql"))
        self.assertIn(f"subreddit text not null default '{subreddits.HOME}'", sql)
        self.assertIn(f"select '{subreddits.HOME}', kind, cursor_utc", sql)
        self.assertIn(f"where subreddit = '{subreddits.HOME}' and extracted_at is null", sql)

    def test_no_other_city_literal_in_sql(self):
        # Any quoted subreddit name in the SQL must be HOME's.
        names = "|".join(map(re.escape, subreddits.SUBREDDITS))
        for name in ("schema.sql", "scoring.sql", "scoring_v2.sql", "resolve.sql"):
            found = set(re.findall(rf"'({names})'", code(read(name)), flags=re.I))
            self.assertLessEqual(found, {subreddits.HOME}, name)

    def test_clear_cursors_uses_home(self):
        import inspect
        src = inspect.getsource(db.clear_cursors)
        self.assertIn("subreddits.HOME", src)
        self.assertNotIn("'FoodNYC'", src)
        self.assertNotIn('"FoodNYC"', src)


if __name__ == "__main__":
    unittest.main()
