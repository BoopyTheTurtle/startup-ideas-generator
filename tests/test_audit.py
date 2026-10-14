import json

import pytest

from pipeline import audit, embed, evals
from tests.pain_factory import Factory


@pytest.fixture
def f(tmp_path, monkeypatch):
    monkeypatch.setattr(evals, "EVALS_DIR", tmp_path / "evals")
    monkeypatch.setattr(embed, "current_extract_version", lambda: "v1")
    return Factory(tmp_path)


def write_labels(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(
        json.dumps({"raw_item_id": i, "source": s, "source_id": str(i), "label": lab,
                    "note": "", "labeled_at": "x"}) + "\n" for i, s, lab in rows), encoding="utf-8")


def seed(f):
    items = []
    for n in range(40):
        item = f.item(source="hn" if n % 2 else "wordpress")
        f.extraction(item)
        items.append(item)
    return items


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_draw_splits_pools_and_skips_the_held_out_items(f):
    items = seed(f)
    write_labels(evals.labels_path("working"),
                 [(i, "hn", "pain" if i % 3 else "not_pain") for i in items[:20]])
    held_out = items[20:30]
    write_labels(evals.labels_path("heldout"), [(i, "hn", "pain") for i in held_out])
    r = audit.draw(f.conn, "2026-10")
    sample = read(audit.blind_dir("2026-10") / "sample.json")
    ids = [x["raw_item_id"] for x in sample["items"]]
    assert (r["drift"], r["model"], len(ids), len(set(ids))) == (10, 10, 20, 20)
    assert not set(ids) & set(held_out)
    assert "pool" not in json.dumps(sample)              # the app's file says nothing about pools
    pools = read(audit.blind_dir("2026-10") / "key.json")["pools"]
    assert sorted(pools.values()).count("drift") == 10
    with pytest.raises(SystemExit, match="exists"):
        audit.draw(f.conn, "2026-10")


def test_score_measures_drift_and_model_agreement(f):
    items = seed(f)
    write_labels(evals.labels_path("working"), [(i, "hn", "pain") for i in items[:20]])
    audit.draw(f.conn, "2026-10")
    d = audit.blind_dir("2026-10")
    sample, pools = read(d / "sample.json"), read(d / "key.json")["pools"]
    rows, flipped = [], False
    for x in sample["items"]:
        i = x["raw_item_id"]
        label = "pain"                                    # the model says pain on every item
        if pools[str(i)] == "drift" and not flipped:
            label, flipped = "not_pain", True             # one drift item now disagrees with its old label
        rows.append((i, x["source"], label))
    write_labels(d / "labels.jsonl", rows)
    out = audit.score(f.conn, "2026-10")
    assert out["drift"] == [9, 10] and out["model"] == [10, 10]
    row = f.conn.execute("SELECT value FROM metric WHERE name = 'audit_label_drift_agreement'").fetchone()
    assert row[0] == 0.9
