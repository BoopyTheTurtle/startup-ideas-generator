"""Build pains directly in a test database, and embed them with fixed vectors.

Tests never download a model: FakeEmbedder looks each "problem — who" text up in a dict.
"""

import itertools

import numpy as np

from pipeline import db
from pipeline.embed import pain_text

DIM = 128
MODEL = "fake/fixed-vectors"


def axis(i: int) -> np.ndarray:
    v = np.zeros(DIM, dtype=np.float32)
    v[i] = 1
    return v


def near(base: int, other: int, cos: float) -> np.ndarray:
    """A unit vector with cosine `cos` to axis `base`, leaning toward axis `other`.

    Two vectors near the same base with distinct `other` axes have cosine cos1 * cos2.
    """
    return (cos * axis(base) + np.sqrt(1 - cos ** 2) * axis(other)).astype(np.float32)


class FakeEmbedder:
    model_id = MODEL
    dim = DIM

    def __init__(self):
        self.vectors: dict[str, np.ndarray] = {}
        self.calls: list[list[str]] = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return np.vstack([self.vectors[t] for t in texts])


class Factory:
    """Inserts raw items, extractions, and pains; registers each pain's vector."""

    def __init__(self, tmp_path):
        self.conn = db.connect(tmp_path / "t.db")
        db.migrate(self.conn)
        self.embedder = FakeEmbedder()
        with self.conn:
            self.collect_run = self.conn.execute("INSERT INTO run (kind) VALUES ('collect')").lastrowid
            self.extract_run = self.conn.execute("INSERT INTO run (kind) VALUES ('extract')").lastrowid
            self.prompt = self.conn.execute(
                "INSERT INTO prompt (name, version, text) VALUES ('extract', 'v1', 'x')").lastrowid
        self.n = 0
        self.p = 0
        self.spare = itertools.count(60)  # axes 60.. give each pain its own spread

    def new_prompt(self, version: str) -> int:
        with self.conn:
            return self.conn.execute(
                "INSERT INTO prompt (name, version, text) VALUES ('extract', ?, 'y')",
                (version,)).lastrowid

    def item(self, author: str | None = "alice", source: str = "hn", country: str | None = "GB") -> int:
        self.n += 1
        with self.conn:
            return self.conn.execute(
                "INSERT INTO raw_item (source, source_id, author_hash, body, country, content_hash,"
                " license, tos_class, run_id) VALUES (?, ?, ?, 'body', ?, ?, 'test', 'clean', ?)",
                (source, str(self.n), author, country, f"h{self.n}", self.collect_run)).lastrowid

    def extraction(self, item_id: int, prompt_id: int | None = None) -> int:
        with self.conn:
            return self.conn.execute(
                "INSERT INTO extraction (raw_item_id, run_id, prompt_id, model, is_pain)"
                " VALUES (?, ?, ?, 'test-model', 1)",
                (item_id, self.extract_run, prompt_id or self.prompt)).lastrowid

    def pain(self, vec: np.ndarray, author: str | None = "alice", source: str = "hn",
             country: str | None = "GB", extraction_id: int | None = None, idx: int = 0) -> int:
        """One pain on a fresh item (or an existing extraction), embedded as `vec`."""
        if extraction_id is None:
            extraction_id = self.extraction(self.item(author, source, country))
        self.p += 1
        problem, who = f"problem {self.p}", f"who {self.p}"
        with self.conn:
            pid = self.conn.execute(
                "INSERT INTO pain (extraction_id, idx, job, problem, who, intensity, evidence_level,"
                " quote, quote_kind) VALUES (?, ?, 'job', ?, ?, 3, 'E1', ?, 'verbatim')",
                (extraction_id, idx, problem, who, f"quote for {problem}")).lastrowid
        self.embedder.vectors[pain_text(problem, who)] = np.asarray(vec, dtype=np.float32)
        return pid

    def problem(self, centroid: np.ndarray, title: str = "seeded") -> int:
        """A problem with a centroid and no members, as an earlier run might leave it."""
        from pipeline.embed import to_blob
        with self.conn:
            return self.conn.execute(
                "INSERT INTO problem (title, centroid, centroid_model, created_run_id) VALUES (?, ?, ?, ?)",
                (title, to_blob(centroid), MODEL, self.collect_run)).lastrowid
