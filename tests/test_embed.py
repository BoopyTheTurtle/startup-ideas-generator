import numpy as np
import pytest

from pain_factory import DIM, MODEL, Factory, axis, near
from pipeline import embed


@pytest.fixture
def f(tmp_path):
    return Factory(tmp_path)


def test_embeds_missing_pains_once_in_batches(f):
    ids = [f.pain(near(0, 10 + i, 0.9)) for i in range(5)]
    assert embed.embed_pending(f.conn, f.embedder, batch_size=2) == 5
    assert [len(c) for c in f.embedder.calls] == [2, 2, 1]
    assert embed.embed_pending(f.conn, f.embedder) == 0
    rows = f.conn.execute("SELECT * FROM embedding ORDER BY pain_id").fetchall()
    assert [r["pain_id"] for r in rows] == ids
    assert all(r["model"] == MODEL and r["dim"] == DIM and len(r["vec"]) == DIM * 4 for r in rows)


def test_text_is_problem_dash_who(f):
    f.pain(axis(0))
    embed.embed_pending(f.conn, f.embedder)
    p = f.conn.execute("SELECT problem, who FROM pain").fetchone()
    assert f.embedder.calls == [[f"{p['problem']} — {p['who']}"]]


def test_vectors_stored_normalized_float32_le(f):
    pid = f.pain(np.array([3.0, 4.0] + [0.0] * (DIM - 2), dtype=np.float32))
    embed.embed_pending(f.conn, f.embedder)
    blob = f.conn.execute("SELECT vec FROM embedding WHERE pain_id = ?", (pid,)).fetchone()[0]
    assert np.frombuffer(blob, dtype="<f4")[:2] == pytest.approx([0.6, 0.8])
    assert embed.from_blob(embed.to_blob(np.array([1.5], dtype=np.float32)))[0] == 1.5


def test_model_change_reembeds(f):
    f.pain(axis(0))
    embed.embed_pending(f.conn, f.embedder)

    class Other(type(f.embedder)):
        model_id = "fake/other"

    other = Other()
    other.vectors = f.embedder.vectors
    assert embed.embed_pending(f.conn, other) == 1
    assert f.conn.execute("SELECT model FROM embedding").fetchone()[0] == "fake/other"


def test_superseded_extractions_are_skipped(f):
    item = f.item()
    f.pain(axis(0), extraction_id=f.extraction(item))
    new = f.pain(axis(1), extraction_id=f.extraction(item, f.new_prompt("v2")))
    assert embed.embed_pending(f.conn, f.embedder) == 1
    assert [r[0] for r in f.conn.execute("SELECT pain_id FROM embedding")] == [new]


def test_e5_uses_query_prefix_without_loading_a_model():
    class Model:
        def encode(self, texts, **kw):
            self.texts, self.kw = texts, kw
            return np.ones((len(texts), 384), dtype=np.float32)

    e = embed.E5Embedder()
    e._model = Model()
    out = e.embed(["a — b"])
    assert e._model.texts == ["query: a — b"]
    assert e._model.kw["normalize_embeddings"] is True
    assert out.shape == (1, 384) and out.dtype == np.float32


def test_current_prompt_beats_newer_extractions(f, monkeypatch):
    item = f.item()
    old = f.pain(axis(0), extraction_id=f.extraction(item))      # prompt v1
    f.pain(axis(1), extraction_id=f.extraction(item, f.new_prompt("v2")))
    monkeypatch.setattr(embed, "current_extract_version", lambda: "v1")
    assert embed.embed_pending(f.conn, f.embedder) == 1
    assert [r[0] for r in f.conn.execute("SELECT pain_id FROM embedding")] == [old]


def test_current_extract_version_matches_prompt_row(f):
    from pipeline.extract import prompt_row
    _, version, _ = prompt_row(f.conn)
    assert embed.current_extract_version() == version
    # And the SQL function every db.connect connection carries agrees.
    assert f.conn.execute("SELECT current_extract_version()").fetchone()[0] == version
