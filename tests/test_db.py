import pytest

from pipeline import db, runs


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    db.migrate(c)
    return c


def test_migrate_is_idempotent(conn):
    assert db.migrate(conn) == []


def test_wal_mode(conn):
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_run_records_ok_and_metric(conn):
    with runs.run(conn, "smoke") as run_id:
        runs.log_metric(conn, run_id, "sources", "items", 3, subject="hn")
    row = conn.execute("SELECT status, finished_at FROM run WHERE id = ?", (run_id,)).fetchone()
    assert row["status"] == "ok" and row["finished_at"]
    m = conn.execute("SELECT * FROM metric WHERE run_id = ?", (run_id,)).fetchone()
    assert (m["layer"], m["name"], m["subject"], m["value"]) == ("sources", "items", "hn", 3)


def test_run_records_failure(conn):
    with pytest.raises(RuntimeError):
        with runs.run(conn, "smoke"):
            raise RuntimeError("boom")
    assert conn.execute("SELECT status FROM run").fetchone()["status"] == "failed"
