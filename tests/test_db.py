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


def test_failed_migration_rolls_back_and_reruns(tmp_path, monkeypatch):
    mig = tmp_path / "migrations"
    mig.mkdir()
    (mig / "001_a.sql").write_text("CREATE TABLE a (x INTEGER);\n", encoding="utf-8")
    bad = mig / "002_b.sql"
    bad.write_text("ALTER TABLE a ADD COLUMN y INTEGER;\nCREATE TABLE b (z);\n"
                   "INSERT INTO nowhere VALUES (1);\n", encoding="utf-8")
    monkeypatch.setattr(db, "MIGRATIONS", mig)
    c = db.connect(tmp_path / "m.db")
    with pytest.raises(Exception, match="nowhere"):
        db.migrate(c)
    assert not c.in_transaction
    # 001 landed; nothing of 002 did.
    assert [r[0] for r in c.execute("SELECT name FROM schema_migration")] == ["001_a.sql"]
    assert [r[1] for r in c.execute("PRAGMA table_info(a)")] == ["x"]
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name = 'b'").fetchone() is None
    # Fixed, it reruns cleanly.
    bad.write_text("ALTER TABLE a ADD COLUMN y INTEGER;\nCREATE TABLE b (z);\n", encoding="utf-8")
    assert db.migrate(c) == ["002_b.sql"]
    assert [r[1] for r in c.execute("PRAGMA table_info(a)")] == ["x", "y"]


def test_004_widens_assigned_by_and_keeps_rows(tmp_path, monkeypatch):
    import shutil
    real, mig = db.MIGRATIONS, tmp_path / "migrations"
    mig.mkdir()
    for f in sorted(real.glob("*.sql")):
        if f.name < "004":
            shutil.copy(f, mig / f.name)
    monkeypatch.setattr(db, "MIGRATIONS", mig)
    c = db.connect(tmp_path / "m.db")
    db.migrate(c)
    with c:
        run_id = c.execute("INSERT INTO run (kind) VALUES ('map')").lastrowid
        c.execute("INSERT INTO raw_item (source, source_id, body, content_hash, license, tos_class,"
                  " run_id) VALUES ('hn', '1', 'b', 'h', 't', 'clean', ?)", (run_id,))
        c.execute("INSERT INTO prompt (name, version, text) VALUES ('extract', 'v', 't')")
        c.execute("INSERT INTO extraction (raw_item_id, run_id, prompt_id, model, is_pain)"
                  " VALUES (1, ?, 1, 'm', 1)", (run_id,))
        c.execute("INSERT INTO pain (extraction_id, idx, job, problem, who, intensity,"
                  " evidence_level, quote, quote_kind) VALUES (1, 0, 'j', 'p', 'w', 3, 'E1', 'q',"
                  " 'verbatim')")
        c.execute("INSERT INTO problem (title, created_run_id) VALUES ('t', ?)", (run_id,))
        c.execute("INSERT INTO problem_member VALUES (1, 1, 0.97, ?, 'cluster')", (run_id,))
    shutil.copy(real / "004_carried_members.sql", mig)
    assert db.migrate(c) == ["004_carried_members.sql"]
    assert [tuple(r) for r in c.execute("SELECT * FROM problem_member")] == [(1, 1, 0.97, run_id, "cluster")]
    with c:
        c.execute("UPDATE problem_member SET assigned_by = 'carried'")
    with pytest.raises(Exception, match="CHECK"), c:
        c.execute("UPDATE problem_member SET assigned_by = 'bogus'")
    assert c.execute("SELECT 1 FROM sqlite_master WHERE type = 'index'"
                     " AND name = 'problem_member_problem'").fetchone()
    assert c.execute("PRAGMA foreign_key_check").fetchall() == []
