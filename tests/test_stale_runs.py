"""A killed process leaves its run row at 'running'; the next writer, holding the lock, fails it."""

import pytest

from pipeline import db, runs
from pipeline.__main__ import main


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("SIG_DB", str(tmp_path / "t.db"))
    c = db.connect()
    db.migrate(c)
    return c


def test_sweep_fails_running_rows_only(conn):
    with runs.run(conn, "collect"):
        pass
    with conn:
        conn.execute("INSERT INTO run (kind, note) VALUES ('extract', 'batch 1')")
        conn.execute("INSERT INTO run (kind) VALUES ('map')")
    assert runs.sweep_stale(conn) == 2
    rows = {r["kind"]: r for r in conn.execute("SELECT * FROM run")}
    assert rows["collect"]["status"] == "ok"
    assert rows["extract"]["status"] == "failed" and rows["extract"]["finished_at"]
    assert rows["extract"]["note"] == "batch 1; killed before finishing"
    assert rows["map"]["note"] == "killed before finishing"
    assert runs.sweep_stale(conn) == 0


def test_a_writing_command_sweeps_before_it_runs(conn, capsys):
    with conn:
        conn.execute("INSERT INTO run (kind) VALUES ('collect')")
    assert main(["smoke"]) == 0
    assert "marked 1 run(s)" in capsys.readouterr().err
    statuses = [r["status"] for r in conn.execute("SELECT status FROM run ORDER BY id")]
    assert statuses == ["failed", "ok"]


def test_read_only_commands_leave_running_rows_alone(conn):
    with conn:
        conn.execute("INSERT INTO run (kind) VALUES ('collect')")
    assert main(["status"]) == 0
    assert conn.execute("SELECT status FROM run").fetchone()[0] == "running"
