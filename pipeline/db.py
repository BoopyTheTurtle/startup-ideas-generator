"""SQLite connection and migrations.

The database lives at data/ideas.db unless SIG_DB points elsewhere. WAL mode lets the
Next.js app read while the pipeline writes.
"""

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def db_path() -> Path:
    return Path(os.environ.get("SIG_DB", ROOT / "data" / "ideas.db"))


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply numbered .sql files in migrations/ that have not run yet."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migration ("
        " name TEXT PRIMARY KEY,"
        " applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))"
    )
    done = {r["name"] for r in conn.execute("SELECT name FROM schema_migration")}
    applied = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name in done:
            continue
        with conn:
            conn.executescript(f.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migration (name) VALUES (?)", (f.name,))
        applied.append(f.name)
    return applied
