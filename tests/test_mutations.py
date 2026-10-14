import pytest

from pipeline import embed, evals, metrics, mutations
from pipeline.metrics import Metric
from tests.pain_factory import Factory, axis


@pytest.fixture
def f(tmp_path, monkeypatch):
    monkeypatch.setattr(evals, "EVALS_DIR", tmp_path / "evals")
    monkeypatch.setattr(embed, "current_extract_version", lambda: "v1")
    return Factory(tmp_path)


def test_every_metric_has_a_mutation():
    assert mutations.uncovered_metrics() == []


def test_mutation_names_are_unique():
    names = [m.name for m in mutations.MUTATIONS]
    assert len(names) == len(set(names))


def test_all_caught_on_an_empty_database(f):
    assert [r for r in mutations.run_all(f.conn) if not r.caught] == []


def test_all_caught_on_a_populated_database(f):
    p = f.problem(axis(0))
    for i in range(8):
        pid = f.pain(axis(0), author=f"a{i}", source="hn", country="US" if i % 2 else "DE")
        with f.conn:
            f.conn.execute("INSERT INTO problem_member (pain_id, problem_id, similarity, assigned_run_id,"
                           " assigned_by) VALUES (?, ?, 0.95, ?, 'centroid')", (pid, p, f.extract_run))
    assert [r for r in mutations.run_all(f.conn) if not r.caught] == []


def test_live_database_and_labels_are_untouched(f, tmp_path):
    f.pain(axis(0))
    tables = ("raw_item", "extraction", "pain", "problem", "run", "metric", "decision")
    before = {t: f.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    mutations.run_all(f.conn)
    after = {t: f.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    assert before == after
    assert not (tmp_path / "evals" / "working" / "labels.jsonl").exists()


def test_a_broken_metric_is_reported_missed(f, monkeypatch):
    i = next(i for i, m in enumerate(metrics.REGISTRY) if m.key == "extraction.backlog_items")
    broken = list(metrics.REGISTRY)
    broken[i] = Metric("extraction", "backlog_items", lambda c: {"": 0.0}, "stuck")
    monkeypatch.setattr(metrics, "REGISTRY", broken)
    missed = [r for r in mutations.run_all(f.conn) if not r.caught]
    assert [(r.name, r.expect.metric) for r in missed] == [("extraction_backlog", "extraction.backlog_items")]
