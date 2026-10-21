"""Run bookkeeping and metric logging."""

import sqlite3
import subprocess
from contextlib import contextmanager

from pipeline.db import ROOT


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


@contextmanager
def run(conn: sqlite3.Connection, kind: str, note: str | None = None):
    """Record a run; mark it ok or failed when the block exits."""
    with conn:
        run_id = conn.execute(
            "INSERT INTO run (kind, git_sha, note) VALUES (?, ?, ?)",
            (kind, _git_sha(), note),
        ).lastrowid
    try:
        yield run_id
    except BaseException:
        with conn:
            conn.execute(
                "UPDATE run SET status = 'failed', finished_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')"
                " WHERE id = ?", (run_id,),
            )
        raise
    with conn:
        conn.execute(
            "UPDATE run SET status = 'ok', finished_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')"
            " WHERE id = ?", (run_id,),
        )


def sweep_stale(conn: sqlite3.Connection) -> int:
    """Mark runs left 'running' as failed and return how many.

    Call only while holding the pipeline lock. Every command that creates runs holds that
    lock, so no other writer can be alive and a 'running' row belongs to a process that was
    killed (closed console, logoff, power loss) before it could record the outcome.
    """
    with conn:
        return conn.execute(
            "UPDATE run SET status = 'failed',"
            " finished_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),"
            " note = COALESCE(note || '; ', '') || 'killed before finishing'"
            " WHERE status = 'running'"
        ).rowcount


def log_metric(conn: sqlite3.Connection, run_id: int, layer: str, name: str,
               value: float, subject: str = "") -> None:
    with conn:
        conn.execute(
            "INSERT INTO metric (run_id, layer, name, subject, value) VALUES (?, ?, ?, ?, ?)",
            (run_id, layer, name, subject, value),
        )
