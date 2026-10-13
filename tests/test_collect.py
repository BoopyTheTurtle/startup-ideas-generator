from collections.abc import Iterator

import pytest

from pipeline import collect as collect_mod
from pipeline import db
from pipeline.collectors import discover
from pipeline.collectors.base import Collector, Item, SchemaDrift, State, require
from pipeline.http import Http


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("SIG_DB", str(tmp_path / "t.db"))
    c = db.connect(tmp_path / "t.db")
    db.migrate(c)
    return c


class Fake(Collector):
    name = "fake"
    license = "test"
    tos_class = "clean"
    regions = ["GLOBAL"]
    min_interval = 0
    items: list[Item] = []
    fail_after: int | None = None

    def fetch(self, http: Http, state: State) -> Iterator[Item]:
        for i, item in enumerate(self.items):
            if self.fail_after is not None and i == self.fail_after:
                raise SchemaDrift("shape changed")
            yield item
        state.set("cursor", str(len(self.items)))


def run(conn, cls, max_items=500):
    from pipeline import runs
    with runs.run(conn, "collect") as run_id:
        return collect_mod.run_collector(conn, run_id, cls, max_items, http_mode="replay")


def items(n, author="alice"):
    return [Item(source_id=str(i), body=f"post {i}", author=author, country="GB", lang="en")
            for i in range(n)]


def test_stores_items_and_hashes_authors(conn):
    Fake.items, Fake.fail_after = items(3), None
    r = run(conn, Fake)
    assert (r.status, r.fetched, r.new) == ("ok", 3, 3)
    rows = conn.execute("SELECT author_hash, license, tos_class FROM raw_item").fetchall()
    assert len(rows) == 3
    assert all(row["author_hash"] and row["author_hash"] != "alice" for row in rows)
    assert len({row["author_hash"] for row in rows}) == 1


def test_dedups_and_saves_state_on_success(conn):
    Fake.items, Fake.fail_after = items(3), None
    run(conn, Fake)
    r = run(conn, Fake)
    assert r.new == 0
    assert conn.execute("SELECT COUNT(*) FROM raw_item").fetchone()[0] == 3
    assert conn.execute(
        "SELECT value FROM collector_state WHERE source='fake' AND key='cursor'"
    ).fetchone()[0] == "3"


def test_schema_drift_keeps_items_but_not_cursor(conn):
    Fake.items, Fake.fail_after = items(5), 2
    r = run(conn, Fake)
    assert r.status == "schema_drift"
    assert conn.execute("SELECT COUNT(*) FROM raw_item").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM collector_state").fetchone()[0] == 0
    h = conn.execute("SELECT * FROM collector_health WHERE source='fake'").fetchone()
    assert h["last_status"] == "schema_drift" and h["consecutive_failures"] == 1
    assert h["last_success_at"] is None


def test_failures_count_up_then_reset(conn):
    Fake.items, Fake.fail_after = items(2), 0
    run(conn, Fake)
    run(conn, Fake)
    h = conn.execute("SELECT consecutive_failures FROM collector_health").fetchone()
    assert h[0] == 2
    Fake.fail_after = None
    run(conn, Fake)
    h = conn.execute("SELECT consecutive_failures, last_success_at FROM collector_health").fetchone()
    assert h[0] == 0 and h[1]


def test_max_items_caps_run(conn):
    Fake.items, Fake.fail_after = items(10), None
    assert run(conn, Fake, max_items=4).fetched == 4


def test_logs_source_and_coverage_metrics(conn):
    Fake.items, Fake.fail_after = items(3), None
    run(conn, Fake)
    names = {(r["layer"], r["name"], r["subject"]) for r in conn.execute("SELECT * FROM metric")}
    assert ("sources", "items_new", "fake") in names
    assert ("coverage", "items_new_by_country", "fake:GB") in names


def test_require_detects_drift():
    with pytest.raises(SchemaDrift):
        require({"a": 1}, ["a", "b"], "x")


def test_discover_finds_real_collectors():
    found = discover()
    assert "hn" in found
    for name, cls in found.items():
        assert cls.tos_class in ("clean", "gray", "restricted"), name
        assert cls.license and cls.regions, name
