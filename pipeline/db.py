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
    from pipeline.embed import register_sql_functions  # lazy: embed imports numpy
    register_sql_functions(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply numbered .sql files in migrations/ that have not run yet.

    Each file runs in one transaction together with its schema_migration row, so a
    failing file leaves no partial change and can be fixed and rerun. SQLite DDL is
    transactional; a migration must therefore not contain BEGIN, COMMIT, or PRAGMAs that
    are no-ops inside a transaction (foreign_keys, journal_mode).
    """
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
        name = f.name.replace("'", "''")
        script = (f"BEGIN IMMEDIATE;\n{f.read_text(encoding='utf-8')}\n;\n"
                  f"INSERT INTO schema_migration (name) VALUES ('{name}');\nCOMMIT;")
        try:
            conn.executescript(script)
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            raise
        applied.append(f.name)
    return applied


# --- pipeline_state: facts the pipeline publishes for the app (migration 006) ----------

# prompt.id (as text) of the extract prompt pipeline/prompts/extract.md hashes to now.
ACTIVE_EXTRACT_PROMPT_ID = "active_extract_prompt_id"


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert one pipeline_state row. Runs in the caller's transaction; commits nothing."""
    conn.execute(
        "INSERT INTO pipeline_state (key, value) VALUES (?, ?)"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value,"
        " updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')", (key, str(value)))


def get_state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM pipeline_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None
