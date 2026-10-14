"""Mutation tests for the metrics (SPEC, "Mutation tests").

Each mutation builds a small synthetic fixture, records the metrics that should notice a
known fault, injects the fault, and measures again. A metric that does not move the right
way is broken, and `pipeline reassess` opens an 'instrument' card for it.

Everything runs on a scratch copy of the database inside a transaction that rolls back,
and the working-set label file is swapped for an empty temporary directory, so the live
database and Edgar's labels are never touched. The synthetic rows use source names that
start with `mut_` and never outlive their transaction.

A metric with no mutation fails tests/test_mutations.py; each new stage registers both.
"""

import json
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from pipeline import db, embed, evals, runs
from pipeline.metrics import REGISTRY, compute_all

MIN_DELTA = 1e-6


@dataclass(frozen=True)
class Expect:
    metric: str                  # 'layer.name'
    direction: str               # 'up' or 'down'
    subject: str = ""


@dataclass(frozen=True)
class Mutation:
    name: str
    description: str
    expects: tuple[Expect, ...]
    inject: Callable[["Fx"], None]
    setup: Callable[["Fx"], None] | None = None


@dataclass
class Result:
    name: str
    expect: Expect
    baseline: float
    mutated: float
    caught: bool
    detail: str = ""


# --- Fixture builder ----------------------------------------------------------------------

class Fx:
    """Inserts synthetic rows into the scratch database."""

    def __init__(self, conn: sqlite3.Connection, labels_dir: Path):
        self.conn, self.labels_dir, self.n = conn, labels_dir, 0
        self.run_id = conn.execute("INSERT INTO run (kind, status, note) VALUES"
                                   " ('mutation', 'ok', 'synthetic')").lastrowid
        version = embed.current_extract_version()
        row = conn.execute("SELECT id FROM prompt WHERE name = 'extract' AND version = ?",
                           (version,)).fetchone()
        self.prompt_id = row[0] if row else conn.execute(
            "INSERT INTO prompt (name, version, text) VALUES ('extract', ?, 'synthetic')",
            (version,)).lastrowid

    def item(self, source: str, country: str = "GB", author: str | None = "a0",
             body: str = "The add-on keeps opening new tabs after every update and I cannot stop it.") -> int:
        self.n += 1
        return self.conn.execute(
            "INSERT INTO raw_item (source, source_id, author_hash, body, country, content_hash,"
            " license, tos_class, run_id) VALUES (?, ?, ?, ?, ?, ?, 'test', 'clean', ?)",
            (source, f"mut{self.n}", author, body, country, f"mut{self.n}", self.run_id)).lastrowid

    def extraction(self, item_id: int, is_pain: int = 1) -> int:
        return self.conn.execute(
            "INSERT INTO extraction (raw_item_id, run_id, prompt_id, model, is_pain)"
            " VALUES (?, ?, ?, 'mutation', ?)", (item_id, self.run_id, self.prompt_id, is_pain)).lastrowid

    def pain(self, extraction_id: int, problem: str = "Unwanted tabs open after add-on updates",
             quote: str = "keeps opening new tabs after every update", kind: str = "verbatim") -> int:
        return self.conn.execute(
            "INSERT INTO pain (extraction_id, idx, job, problem, who, intensity, evidence_level,"
            " quote, quote_kind) VALUES (?, 0, 'browse', ?, 'user', 3, 'E1', ?, ?)",
            (extraction_id, problem, quote, kind)).lastrowid

    def pained_item(self, source: str, country: str = "GB", author: str | None = "a0", **pain) -> int:
        """A pain-bearing item; returns the pain id."""
        return self.pain(self.extraction(self.item(source, country, author)), **pain)

    def problem(self, axis: int, status: str = "new", run_id: int | None = None) -> int:
        row = self.conn.execute("SELECT length(centroid) FROM problem WHERE centroid IS NOT NULL"
                                " AND centroid_model != 'mutation' LIMIT 1").fetchone()
        vec = np.zeros(row[0] // 4 if row else embed.DEFAULT_DIM, dtype=np.float32)
        vec[axis] = 1
        return self.conn.execute(
            "INSERT INTO problem (title, status, centroid, centroid_model, created_run_id)"
            " VALUES (?, ?, ?, 'mutation', ?)",
            (f"synthetic {axis}", status, embed.to_blob(vec), run_id or self.run_id)).lastrowid

    def member(self, pain_id: int, problem_id: int) -> None:
        self.conn.execute(
            "INSERT INTO problem_member (pain_id, problem_id, similarity, assigned_run_id, assigned_by)"
            " VALUES (?, ?, 0.95, ?, 'centroid')", (pain_id, problem_id, self.run_id))

    def label(self, item_id: int, source: str, label: str) -> None:
        path = self.labels_dir / "working" / "labels.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"raw_item_id": item_id, "source": source, "source_id": str(item_id),
                                "label": label, "note": "", "labeled_at": "2026-01-01T00:00:00Z"}) + "\n")


# --- The mutations ------------------------------------------------------------------------

def _dead_collector_setup(fx: Fx) -> None:
    fx.conn.execute(
        "INSERT INTO collector_health (source, last_attempt_at, last_success_at, last_status)"
        " VALUES ('hn', datetime('now'), strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'ok')"
        " ON CONFLICT (source) DO UPDATE SET last_success_at = excluded.last_success_at,"
        " consecutive_failures = 0")


def _dead_collector(fx: Fx) -> None:
    fx.conn.execute("UPDATE collector_health SET last_success_at = strftime('%Y-%m-%dT%H:%M:%fZ',"
                    "'now','-30 days'), last_status = 'failed', consecutive_failures = 5 WHERE source = 'hn'")


def _two_problems(fx: Fx) -> None:
    fx.problem(0)
    fx.problem(1)


def _duplicate_problem(fx: Fx) -> None:
    fx.problem(0)   # same centroid as the first synthetic problem


def _solution_setup(fx: Fx) -> None:
    for _ in range(3):
        fx.pained_item("mut_sol")


def _solution_as_problem(fx: Fx) -> None:
    for _ in range(3):
        fx.pained_item("mut_sol", problem="I need an app that tracks my invoices and sends reminders")


def _fabricated_setup(fx: Fx) -> None:
    for _ in range(3):
        fx.pained_item("mut_fab")


def _fabricated_demand(fx: Fx) -> None:
    for _ in range(3):
        fx.pained_item("mut_fab", quote="Customers pay me 500 euros a month for exactly this")


def _labels_setup(fx: Fx) -> None:
    for i in range(10):
        pain = i < 5
        item = fx.item("mut_lab", author=f"l{i}")
        ex = fx.extraction(item, int(pain))
        if pain:
            fx.pain(ex)
        fx.label(item, "mut_lab", "pain" if pain else "not_pain")


def _labels_flipped(fx: Fx) -> None:
    fx.conn.execute("UPDATE extraction SET is_pain = 1 - is_pain WHERE raw_item_id IN"
                    " (SELECT id FROM raw_item WHERE source = 'mut_lab')")


def _pool_setup(fx: Fx) -> None:
    p = fx.problem(0)
    for i in range(20):
        fx.member(fx.pained_item("mut_pool", author=f"p{i}"), p)


def _pool_flood(fx: Fx) -> None:
    for i in range(100):
        fx.pained_item("mut_pool", author=f"q{i}")


def _silent_setup(fx: Fx) -> None:
    for i in range(10):
        fx.extraction(fx.item("mut_silent", author=f"s{i}"), 1)


def _source_goes_silent(fx: Fx) -> None:
    fx.conn.execute("UPDATE extraction SET is_pain = 0 WHERE raw_item_id IN"
                    " (SELECT id FROM raw_item WHERE source = 'mut_silent')")


def _region_setup(fx: Fx) -> None:
    total = fx.conn.execute("SELECT COUNT(*) FROM pain").fetchone()[0]
    for i in range(total // 2 + 6):          # enough UK pains for a share above its target
        fx.pained_item("mut_region", country="GB", author=f"r{i}")


def _region_loss(fx: Fx) -> None:
    fx.conn.execute("UPDATE raw_item SET country = 'US' WHERE country = 'GB'")


def _backlog(fx: Fx) -> None:
    for i in range(50):
        fx.item("mut_backlog", author=f"b{i}")


def _queue_setup(fx: Fx) -> None:
    _two_problems(fx)


def _queue_flood(fx: Fx) -> None:
    a, b = [r[0] for r in fx.conn.execute(
        "SELECT id FROM problem WHERE centroid_model = 'mutation' ORDER BY id LIMIT 2")]
    fx.conn.execute("INSERT INTO merge_candidate (a_id, b_id, similarity, run_id) VALUES (?, ?, 0.95, ?)",
                    (a, b, fx.run_id))


def _cost_spike(fx: Fx) -> None:
    fx.conn.execute("INSERT INTO metric (run_id, layer, name, subject, value) VALUES (?, 'extraction',"
                    " 'llm_cost_usd', '', 25)", (fx.run_id,))


def _eval_gap(fx: Fx) -> None:
    for i in range(60):
        fx.extraction(fx.item("mut_big", author=f"g{i}"), 1)


def _overlap_setup(fx: Fx) -> None:
    p = fx.problem(0)
    for i in range(3):
        fx.member(fx.pained_item("mut_a", author=f"o{i}"), p)


def _overlap(fx: Fx) -> None:
    p = fx.conn.execute("SELECT id FROM problem WHERE centroid_model = 'mutation'").fetchone()[0]
    fx.member(fx.pained_item("mut_b", author="ob"), p)


def _decisions(fx: Fx) -> None:
    for _ in range(3):
        fx.conn.execute("INSERT INTO decision (action, reason) VALUES ('archive', 'duplicate')")


def _turnover_setup(fx: Fx) -> None:
    old = fx.conn.execute("INSERT INTO run (kind, status) VALUES ('map', 'ok')").lastrowid
    for i in range(10):
        fx.problem(i, run_id=old)
    fx.conn.execute("INSERT INTO run (kind, status) VALUES ('map', 'ok')")   # latest map run: no new problems


def _turnover(fx: Fx) -> None:
    latest = fx.conn.execute("SELECT MAX(id) FROM run WHERE kind = 'map'").fetchone()[0]
    for i in range(20, 40):
        fx.problem(i, run_id=latest)


def _merges(fx: Fx) -> None:
    keep = fx.problem(0)
    for old in range(900001, 900006):
        fx.conn.execute("INSERT INTO problem_alias (old_id, new_id, reason) VALUES (?, ?, 'test')", (old, keep))


def _authors_setup(fx: Fx) -> None:
    fx.pained_item("mut_auth", author="x0")


def _authors(fx: Fx) -> None:
    for i in range(1, 5):
        fx.pained_item("mut_auth", author=f"x{i}")


def _eval_labeled(fx: Fx) -> None:
    for i in range(8):
        fx.label(900000 + i, "mut_lbl", "pain")


MUTATIONS: list[Mutation] = [
    Mutation("dead_collector", "a default-on collector stops succeeding",
             (Expect("sources.collectors_stale", "up"), Expect("sources.collector_days_since_ok", "up", "hn")),
             _dead_collector, _dead_collector_setup),
    Mutation("duplicate_problem", "a second problem with the same centroid",
             (Expect("mapping.duplicate_rate", "up"),), _duplicate_problem, _two_problems),
    Mutation("solution_as_problem", "pains that ask for an app instead of describing an obstacle",
             (Expect("extraction.solution_leak_rate", "up"),), _solution_as_problem, _solution_setup),
    Mutation("fabricated_demand", "verbatim quotes that the item never contained",
             (Expect("extraction.quote_ungrounded_rate", "up"),), _fabricated_demand, _fabricated_setup),
    Mutation("labels_flipped", "extraction verdicts invert on labeled items",
             (Expect("extraction.working_precision", "down"), Expect("extraction.working_recall", "down"),
              Expect("extraction.working_f1", "down")), _labels_flipped, _labels_setup),
    Mutation("pool_flood", "many pains join no problem",
             (Expect("mapping.pool_share", "up"),), _pool_flood, _pool_setup),
    Mutation("source_goes_silent", "a source's items stop yielding pains",
             (Expect("sources.pain_yield_per_100", "down", "mut_silent"),), _source_goes_silent, _silent_setup),
    Mutation("region_lost", "UK items disappear from coverage",
             (Expect("coverage.region_gap", "up", "UK"), Expect("coverage.region_share", "down", "UK")),
             _region_loss, _region_setup),
    Mutation("extraction_backlog", "items pile up without extraction",
             (Expect("extraction.backlog_items", "up"),), _backlog),
    Mutation("merge_queue_flood", "a near-duplicate pair waits for Edgar",
             (Expect("mapping.merge_queue_open", "up"),), _queue_flood, _queue_setup),
    Mutation("cost_spike", "an LLM stage reports a large cost",
             (Expect("sources.llm_cost_usd_7d", "up"),), _cost_spike),
    Mutation("unlabeled_source", "a source grows large with no working labels",
             (Expect("coverage.eval_gap_sources", "up"),), _eval_gap),
    Mutation("source_overlap", "a second source starts feeding the first one's problem",
             (Expect("sources.problem_overlap", "up", "mut_a"),), _overlap, _overlap_setup),
    Mutation("kill_reasons", "steering decisions pile up under one reason",
             (Expect("methodology.decision_reason_count", "up", "duplicate"),), _decisions),
    Mutation("problem_turnover", "the latest map run creates many problems",
             (Expect("mapping.problem_turnover", "up"),), _turnover, _turnover_setup),
    Mutation("merge_wave", "problems get merged away",
             (Expect("mapping.merge_rate", "up"),), _merges),
    Mutation("author_growth", "new distinct authors join a source",
             (Expect("sources.distinct_authors", "up", "mut_auth"),), _authors, _authors_setup),
    Mutation("labels_added", "Edgar labels a source",
             (Expect("coverage.eval_labeled", "up", "mut_lbl"),), _eval_labeled),
]


def uncovered_metrics() -> list[str]:
    """Registered metrics that no mutation expects to react."""
    covered = {e.metric for m in MUTATIONS for e in m.expects}
    return [m.key for m in REGISTRY if m.key not in covered]


# --- The harness --------------------------------------------------------------------------

@contextmanager
def _labels_in(path: Path):
    old = evals.EVALS_DIR
    evals.EVALS_DIR = path
    try:
        yield
    finally:
        evals.EVALS_DIR = old


def _read(conn: sqlite3.Connection, e: Expect) -> float:
    layer, name = e.metric.split(".", 1)
    return compute_all(conn, only={e.metric}).get((layer, name, e.subject), 0.0)


def run_mutation(scratch: sqlite3.Connection, m: Mutation, labels_dir: Path) -> list[Result]:
    """Run one mutation inside a transaction that always rolls back."""
    scratch.execute("BEGIN")
    try:
        with _labels_in(labels_dir):
            fx = Fx(scratch, labels_dir)
            if m.setup:
                m.setup(fx)
            before = [_read(scratch, e) for e in m.expects]
            m.inject(fx)
            after = [_read(scratch, e) for e in m.expects]
    finally:
        scratch.execute("ROLLBACK")
        label_file = labels_dir / "working" / "labels.jsonl"
        label_file.unlink(missing_ok=True)
    out = []
    for e, b, a in zip(m.expects, before, after):
        moved = a - b if e.direction == "up" else b - a
        out.append(Result(m.name, e, b, a, moved > MIN_DELTA,
                          "" if moved > MIN_DELTA else f"expected {e.direction}, moved {a - b:+.6g}"))
    return out


def run_all(conn: sqlite3.Connection, mutations: list[Mutation] | None = None) -> list[Result]:
    """Copy the database, run every mutation on the copy, and return the results."""
    results: list[Result] = []
    with tempfile.TemporaryDirectory() as tmp:
        scratch_path = Path(tmp) / "scratch.db"
        scratch = db.connect(scratch_path)
        scratch.isolation_level = None            # we manage the transaction
        conn.backup(scratch)
        try:
            for m in mutations or MUTATIONS:
                results += run_mutation(scratch, m, Path(tmp) / "labels")
        finally:
            scratch.close()
    return results


def record(conn: sqlite3.Connection, run_id: int, results: list[Result]) -> None:
    with conn:
        conn.executemany(
            "INSERT INTO mutation (run_id, name, metric, subject, direction, baseline, mutated, caught, detail)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(run_id, r.name, r.expect.metric, r.expect.subject, r.expect.direction, r.baseline,
              r.mutated, int(r.caught), r.detail) for r in results])
    runs.log_metric(conn, run_id, "methodology", "mutations_missed", sum(not r.caught for r in results))
    runs.log_metric(conn, run_id, "methodology", "mutations_run", len(results))
