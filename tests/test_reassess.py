import json

import pytest

from pipeline import cards, embed, evals, metrics, reassess, runs
from pipeline.metrics import Metric
from tests.pain_factory import Factory


@pytest.fixture
def f(tmp_path, monkeypatch):
    monkeypatch.setattr(evals, "EVALS_DIR", tmp_path / "evals")
    monkeypatch.setattr(embed, "current_extract_version", lambda: "v1")
    monkeypatch.setattr(reassess, "DIGEST_DIR", tmp_path / "digests")
    return Factory(tmp_path)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_reassess_logs_metrics_mutations_and_digest(f):
    r = reassess.reassess(f.conn)
    assert r["missed"] == 0 and r["mutations"] > 15
    n = f.conn.execute("SELECT COUNT(*) FROM metric WHERE run_id = ?", (r["run_id"],)).fetchone()[0]
    assert n > 0
    assert f.conn.execute("SELECT COUNT(*) FROM mutation WHERE run_id = ?",
                          (r["run_id"],)).fetchone()[0] == r["mutations"]
    assert {"data", "metrics", "mutations", "cards", "recent_decisions"} <= set(read(r["digest"]))


def test_digest_shows_previous_values(f):
    reassess.reassess(f.conn, with_mutations=False)
    f.item(source="hn")
    second = reassess.reassess(f.conn, with_mutations=False)
    backlog = next(m for m in read(second["digest"])["metrics"] if m["metric"] == "extraction.backlog_items")
    assert (backlog["previous"], backlog["value"]) == (0.0, 1.0)


def test_missed_mutation_opens_one_instrument_card(f, monkeypatch):
    i = next(i for i, m in enumerate(metrics.REGISTRY) if m.key == "mapping.merge_queue_open")
    broken = list(metrics.REGISTRY)
    broken[i] = Metric("mapping", "merge_queue_open", lambda c: {"": 0.0}, "stuck")
    monkeypatch.setattr(metrics, "REGISTRY", broken)
    first = reassess.reassess(f.conn)
    assert len(first["opened"]["instrument"]) == 1
    card = cards.get_card(f.conn, first["opened"]["instrument"][0])
    assert (card["kind"], card["touches"], card["proposed_by"]) == ("instrument", "eval", "system")
    assert reassess.reassess(f.conn)["opened"]["instrument"] == []   # same open card, no duplicate


def merged_card(f, direction="down", value=0.2):
    with f.conn:
        f.conn.execute("INSERT INTO metric (run_id, layer, name, subject, value) VALUES (?, 'extraction',"
                       " 'backlog_items', '', 1)", (f.collect_run,))
    cid = cards.add_card(f.conn, {
        "kind": "extraction", "touches": "system", "title": "Cut quote misses",
        "observation": "o", "evidence": [{"metric": "extraction.backlog_items", "value": 1}],
        "hypothesis": "h", "change": "c", "expected_effect": "e",
        "expected_metric": "extraction.backlog_items", "expected_direction": direction,
        "risk": "r", "size": "S", "value": 3})
    with f.conn:
        f.conn.execute("DROP TRIGGER improvement_card_transition")
        f.conn.execute("UPDATE improvement_card SET status = 'merged', merged_at = strftime('%Y-%m-%dT%H:%M:%fZ','now','-1 day'),"
                       " merged_sha = 'abc', baseline_json = ? WHERE id = ?",
                       (json.dumps({"metric": "extraction.backlog_items", "subject": "", "value": value,
                                    "run_id": 1, "direction": direction}), cid))
    return cid


def log(f, v):
    with runs.run(f.conn, "reassess") as rid:
        runs.log_metric(f.conn, rid, "extraction", "backlog_items", v)


def test_regression_opens_revert_card(f):
    cid = merged_card(f, "down", 10.0)
    log(f, 9.5)                                    # barely moved, right way
    assert reassess.open_revert_cards(f.conn) == []
    log(f, 40.0)                                   # one bad reading is not enough
    assert reassess.open_revert_cards(f.conn) == []
    log(f, 41.0)                                   # two in a row
    [rid] = reassess.open_revert_cards(f.conn)
    revert = cards.get_card(f.conn, rid)
    assert revert["kind"] == "revert" and revert["reverts_card_id"] == cid
    assert revert["touches"] == "system"
    assert reassess.open_revert_cards(f.conn) == []            # one revert card per merged card


def test_improvement_opens_no_revert_card(f):
    merged_card(f, "up", 10.0)
    log(f, 30.0)
    log(f, 31.0)
    assert reassess.open_revert_cards(f.conn) == []
