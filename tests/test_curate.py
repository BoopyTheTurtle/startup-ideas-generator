import pytest

from pipeline import db, runs
from pipeline.curate import curate
from pipeline.llm import LLMResult


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.migrate(c)
    return c


def add_problem(conn, title, source="auto"):
    with runs.run(conn, "map") as run_id, conn:
        return conn.execute(
            "INSERT INTO problem (title, created_run_id, title_source) VALUES (?, ?, ?)",
            (title, run_id, source)).lastrowid


class Fake:
    name = "fake"

    def __init__(self, coherent=True):
        self.coherent, self.calls = coherent, 0

    def run(self, system, user, schema, model):
        import json
        self.calls += 1
        ids = [p["id"] for p in json.loads(user)]
        return LLMResult({"problems": [{"id": i, "title": f"Title {i}", "statement": "S.",
                                        "coherent": self.coherent} for i in ids]}, model, 0.0)


def test_names_auto_titles_only(conn):
    auto = add_problem(conn, "raw sentence")
    human = add_problem(conn, "Edgar's title", source="human")
    stats = curate(conn, Fake())
    assert stats["named"] == 1
    rows = dict(conn.execute("SELECT id, title FROM problem").fetchall())
    assert rows[auto] == f"Title {auto}" and rows[human] == "Edgar's title"
    assert curate(conn, Fake())["named"] == 0  # already curated


def test_incoherent_problems_are_flagged(conn):
    add_problem(conn, "mixed bag")
    stats = curate(conn, Fake(coherent=False))
    assert stats["incoherent"] == 1
    assert "split or archive" in conn.execute("SELECT statement FROM problem").fetchone()[0]
