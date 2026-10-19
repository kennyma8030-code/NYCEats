"""Make it obvious whether the database tests ran.

They skip quietly without a throwaway Postgres (see tests/pgtest.py), and a
green run with half the suite skipped reads like a full pass. So the header
and the final summary both say which it was.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pgtest  # noqa: E402


def pytest_report_header(config):
    if pgtest.URL:
        return f"database tests: ON against {pgtest.URL}"
    return f"database tests: OFF -- {pgtest.SKIP_REASON}"


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not pgtest.URL:
        terminalreporter.write_sep("!", pgtest.SKIP_REASON, yellow=True)
