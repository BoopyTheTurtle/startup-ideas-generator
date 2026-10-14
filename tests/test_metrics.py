import pytest

from pipeline import embed, evals, metrics
from pipeline.metrics import SOLUTION_RE, compute_all, region
from tests.pain_factory import Factory, axis


@pytest.fixture
def f(tmp_path, monkeypatch):
    monkeypatch.setattr(evals, "EVALS_DIR", tmp_path / "evals")
    monkeypatch.setattr(embed, "current_extract_version", lambda: "v1")
    return Factory(tmp_path)


def value(f, key, subject=""):
    layer, name = key.split(".")
    return compute_all(f.conn, only={key}).get((layer, name, subject))


def test_regions():
    assert [region(c) for c in ("US", "GB", "DE", "EU", "BR", None)] == ["US", "UK", "EEA", "EEA", "other", "other"]


@pytest.mark.parametrize("text,leak", [
    ("I need an app that tracks my invoices", True),
    ("someone should build a tool for this", True),
    ("There should be a way to export contacts", True),
    ("Add-on updates open unwanted tabs", False),
    ("Invoices take hours to reconcile by hand", False),
    ("I need to reconcile invoices every month", False),
])
def test_solution_regex(text, leak):
    assert bool(SOLUTION_RE.search(text)) is leak


def test_empty_database_gives_no_nan(tmp_path, monkeypatch):
    monkeypatch.setattr(evals, "EVALS_DIR", tmp_path / "evals")
    f = Factory(tmp_path)
    vals = compute_all(f.conn)
    assert all(v == v for v in vals.values())
    assert vals.get(("extraction", "backlog_items", "")) == 0.0


def test_pain_yield(f):
    for _ in range(3):
        f.pain(axis(0), source="hn", author=None)
    f.extraction(f.item(source="hn"))
    assert value(f, "sources.pain_yield_per_100", "hn") == 100.0
    f.conn.execute("UPDATE extraction SET is_pain = 0 WHERE id = 1")
    assert round(value(f, "sources.pain_yield_per_100", "hn"), 1) == 75.0


def test_active_extraction_prefers_current_prompt(f):
    item = f.item(source="hn")
    f.extraction(item, f.prompt)                      # prompt v1 (current): pain
    old = f.new_prompt("v0")
    ex = f.extraction(item, old)
    f.conn.execute("UPDATE extraction SET is_pain = 0 WHERE id = ?", (ex,))
    assert value(f, "sources.pain_yield_per_100", "hn") == 100.0


def test_duplicate_rate_ignores_pairs_kept_apart(f):
    a, b = f.problem(axis(0)), f.problem(axis(0))
    assert value(f, "mapping.duplicate_rate") == 1.0
    with f.conn:
        f.conn.execute("INSERT INTO merge_candidate (a_id, b_id, similarity, run_id, status)"
                       " VALUES (?, ?, 0.99, ?, 'rejected')", (a, b, f.collect_run))
    assert value(f, "mapping.duplicate_rate") == 0.0


def test_quote_ungrounded(f):
    item = f.item()
    f.conn.execute("UPDATE raw_item SET body = 'the add-on keeps opening tabs every single update' WHERE id = ?",
                   (item,))
    ex = f.extraction(item)
    pid = f.pain(axis(0), extraction_id=ex)
    f.conn.execute("UPDATE pain SET quote = 'keeps opening tabs every single update' WHERE id = ?", (pid,))
    assert value(f, "extraction.quote_ungrounded_rate") == 0.0
    f.conn.execute("UPDATE pain SET quote = 'an invented sentence that is not there' WHERE id = ?", (pid,))
    assert value(f, "extraction.quote_ungrounded_rate") == 1.0


def test_registry_keys_are_unique_and_documented():
    keys = [m.key for m in metrics.REGISTRY]
    assert len(keys) == len(set(keys))
    assert all(m.doc for m in metrics.REGISTRY)
