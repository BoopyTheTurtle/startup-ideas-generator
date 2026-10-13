"""Stage 3a: embed pains locally for mapping.

Each pain is embedded as "problem — who" (English fields, so one vector space serves every
source language). Vectors are L2-normalized float32, stored little-endian in `embedding`
with the model id and dimension. The table keeps one vector per pain; switching models
re-embeds and overwrites.

The default model is intfloat/multilingual-e5-small on CPU. Its model card asks for the
"query: " prefix on both sides of symmetric tasks (similarity, clustering), so every text
gets it. The model downloads once into the Hugging Face cache (~/.cache/huggingface,
outside the repo; override with HF_HOME).
"""

from __future__ import annotations

import sqlite3
from typing import Protocol

import numpy as np

DEFAULT_MODEL = "intfloat/multilingual-e5-small"
DEFAULT_DIM = 384
BATCH_SIZE = 64

# A raw item can be re-extracted under a new prompt version. Only the pains of its latest
# extraction count; older ones stay stored (history) but are neither embedded nor mapped.
ACTIVE_PAIN_SQL = """
    SELECT p.* FROM pain p
    JOIN extraction x ON x.id = p.extraction_id
    WHERE x.id = (SELECT MAX(x2.id) FROM extraction x2 WHERE x2.raw_item_id = x.raw_item_id)
"""


class Embedder(Protocol):
    model_id: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float32 array of L2-normalized vectors."""
        ...


class E5Embedder:
    """multilingual-e5 through sentence-transformers. Loads the model on first use."""

    def __init__(self, model_id: str = DEFAULT_MODEL, dim: int = DEFAULT_DIM,
                 prefix: str = "query: ", batch_size: int = BATCH_SIZE):
        self.model_id, self.dim, self.prefix, self.batch_size = model_id, dim, prefix, batch_size
        self._model = None

    def embed(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_id, device="cpu")
        vecs = self._model.encode([self.prefix + t for t in texts], batch_size=self.batch_size,
                                  normalize_embeddings=True, convert_to_numpy=True,
                                  show_progress_bar=False)
        vecs = np.asarray(vecs, dtype=np.float32)
        if vecs.shape[1] != self.dim:
            raise ValueError(f"{self.model_id} returned dim {vecs.shape[1]}, expected {self.dim}")
        return vecs


def pain_text(problem: str, who: str) -> str:
    return f"{problem.strip()} — {who.strip()}"


def to_blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype="<f4").tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype="<f4").astype(np.float32)


def normalize(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)


def pending(conn: sqlite3.Connection, model_id: str) -> list[sqlite3.Row]:
    """Active pains with no embedding, or one from another model."""
    return conn.execute(
        f"SELECT a.id, a.problem, a.who FROM ({ACTIVE_PAIN_SQL}) a"
        " LEFT JOIN embedding e ON e.pain_id = a.id"
        " WHERE e.pain_id IS NULL OR e.model != ? ORDER BY a.id", (model_id,),
    ).fetchall()


def embed_pending(conn: sqlite3.Connection, embedder: Embedder,
                  batch_size: int = BATCH_SIZE) -> int:
    """Embed every active pain that lacks a vector for this model. Returns the count."""
    rows = pending(conn, embedder.model_id)
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        vecs = normalize(embedder.embed([pain_text(r["problem"], r["who"]) for r in batch]))
        with conn:
            conn.executemany(
                "INSERT OR REPLACE INTO embedding (pain_id, model, dim, vec) VALUES (?, ?, ?, ?)",
                [(r["id"], embedder.model_id, embedder.dim, to_blob(v)) for r, v in zip(batch, vecs)],
            )
    return len(rows)


def cmd_embed(args) -> int:
    from pipeline import db
    conn = db.connect()
    db.migrate(conn)
    n = embed_pending(conn, E5Embedder(), batch_size=args.batch_size)
    print(f"embedded {n} pains with {DEFAULT_MODEL}")
    return 0


def register_cli(sub) -> None:
    e = sub.add_parser("embed", help="embed pains that lack a vector (stage 3)")
    e.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    e.set_defaults(fn=cmd_embed)
