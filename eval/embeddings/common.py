"""Shared paths, credentials and the read-only database connection.

Credentials are read from the files where they already live, at runtime, and
never copied into this worktree: the OpenRouter key from the repo root's .env,
the production DATABASE_URL from the backend worktree's .env. Everything this
benchmark produces that is large or derived from private data (corpus text,
vectors, the embedding cache, the spend ledger) goes under data/, which is
gitignored.
"""

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)

ROOT_ENV = Path("/Users/kenny/NYCEats/.env")
DB_ENV = Path("/Users/kenny/NYCEats/.claude/worktrees/backend/.env")


def _read_env(path, key):
    """Return one variable from a .env file without touching os.environ, so
    the value is never inherited by a child process or printed by accident."""
    value = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                value = v.strip().strip('"').strip("'")
    if not value:
        raise SystemExit(f"{key} not found in {path}")
    return value


def openrouter_key():
    return os.environ.get("OPENROUTER_API_KEY") or _read_env(ROOT_ENV, "OPENROUTER_API_KEY")


def connect_readonly():
    """Production is the only database with current data, so this benchmark
    reads it, but every session is forced read-only at the server so no bug
    here can write to it."""
    import psycopg2

    url = _read_env(DB_ENV, "DATABASE_URL")
    conn = psycopg2.connect(url, options="-c default_transaction_read_only=on")
    conn.set_session(readonly=True)
    return conn


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)
