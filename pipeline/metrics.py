"""Metric registry for stage 8 (SPEC, "What it measures").

A Metric is a pure function of the database and the working-set labels: the same state
gives the same numbers. That is what lets the mutation tests (pipeline.mutations) apply a
known fault to a scratch copy and check that the number moves. Metrics here are computed
by `pipeline reassess` once a week and logged to the `metric` table; per-run metrics that
the stages already log (extraction costs, collector uptime) stay where they are.

Every metric registered here needs at least one mutation in pipeline.mutations: a test in
tests/test_mutations.py fails when one has none. Later stages register theirs the same
way (SPEC, "Throughout").

Judgment-layer metrics (scorer variance, judge spread) arrive with Phase 5, and trend
false alarms need the eight weeks of snapshots the SPEC asks for.
"""

import re
import sqlite3
from dataclasses import dataclass
from typing import Callable

from pipeline import evals
from pipeline.text import find_quote, plain_text

# subject -> value; the empty subject means "overall".
Values = dict[str, float]

STALE_DAYS = 8                       # a default-on collector with no success this long is stale
COST_WINDOW_DAYS = 7
EVAL_MIN_EXTRACTED = 50              # a source with this many extractions ...
EVAL_MIN_LABELED = 10                # ... needs this many working labels
# Placeholder targets for the coverage gap (SPEC: US, EEA, and UK are all required).
TARGET_SHARE = {"US": 0.2, "UK": 0.2, "EEA": 0.2}
EEA = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
       "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS", "LI", "NO", "EU"}

# Phrases that mark a "problem" as a requested product, not an obstacle (SPEC principle 1).
SOLUTION_RE = re.compile(
    r"\b(i|we|someone|somebody|they)\s+(need|needs|want|wants|wish|should (build|make|create))\b[^.]{0,40}"
    r"\b(an?|the)\s+(app|tool|plugin|extension|website|platform|service|software|bot)\b"
    r"|\b(there should be|there ought to be|build me|someone should (build|make|create))\b"
    r"|\b(an?|the)\s+(app|tool|plugin|extension|platform)\s+(that|which|to)\b",
    re.IGNORECASE)


@dataclass(frozen=True)
class Metric:
    layer: str
    name: str
    compute: Callable[[sqlite3.Connection], Values]
    doc: str = ""

    @property
    def key(self) -> str:
        return f"{self.layer}.{self.name}"


REGISTRY: list[Metric] = []


def metric(layer: str, name: str):
    def wrap(fn: Callable[[sqlite3.Connection], Values]):
        REGISTRY.append(Metric(layer, name, fn, (fn.__doc__ or "").strip()))
        return fn
    return wrap


def region(country: str | None) -> str:
    if country == "US":
        return "US"
    if country in ("GB", "UK"):
        return "UK"
    if country in EEA:
        return "EEA"
    return "other"


# An item's active extraction: the current prompt's, else its latest (as ACTIVE_PAIN_SQL).
ACTIVE_EXTRACTION_SQL = """
    SELECT x.* FROM extraction x WHERE x.id = COALESCE(
        (SELECT x2.id FROM extraction x2 WHERE x2.raw_item_id = x.raw_item_id
            AND x2.prompt_id = (SELECT pr.id FROM prompt pr WHERE pr.name = 'extract'
                                 AND pr.version = current_extract_version())),
        (SELECT MAX(x2.id) FROM extraction x2 WHERE x2.raw_item_id = x.raw_item_id))
"""

# Active pains with their item: one row per pain.
ACTIVE_PAIN_ITEM_SQL = """
    SELECT p.id AS pain_id, p.problem, p.quote, p.quote_kind, r.id AS item_id, r.source, r.country,
           r.body, r.text_discarded_at, r.author_hash
      FROM pain p JOIN (%s) x ON x.id = p.extraction_id
      JOIN raw_item r ON r.id = x.raw_item_id
     WHERE x.is_pain = 1
""" % ACTIVE_EXTRACTION_SQL


# --- Sources ----------------------------------------------------------------------------

@metric("sources", "pain_yield_per_100")
def pain_yield(conn) -> Values:
    """Pain-bearing items per 100 raw items with an active extraction, by source."""
    rows = conn.execute(
        f"SELECT r.source, 100.0 * SUM(x.is_pain) / COUNT(*) AS v FROM ({ACTIVE_EXTRACTION_SQL}) x"
        " JOIN raw_item r ON r.id = x.raw_item_id GROUP BY r.source").fetchall()
    return {r["source"]: r["v"] for r in rows}


@metric("sources", "distinct_authors")
def distinct_authors(conn) -> Values:
    """Distinct authors of pain-bearing items, by source (items without an author skipped)."""
    rows = conn.execute(
        f"SELECT source, COUNT(DISTINCT author_hash) AS v FROM ({ACTIVE_PAIN_ITEM_SQL})"
        " WHERE author_hash IS NOT NULL GROUP BY source").fetchall()
    return {r["source"]: r["v"] for r in rows}


@metric("sources", "problem_overlap")
def problem_overlap(conn) -> Values:
    """Share of a source's live problems that another source also feeds, by source."""
    rows = conn.execute(
        f"SELECT m.problem_id, i.source FROM problem_member m JOIN ({ACTIVE_PAIN_ITEM_SQL}) i"
        " ON i.pain_id = m.pain_id JOIN problem p ON p.id = m.problem_id AND p.status != 'merged'"
        " GROUP BY m.problem_id, i.source").fetchall()
    by_problem: dict[int, set[str]] = {}
    for r in rows:
        by_problem.setdefault(r["problem_id"], set()).add(r["source"])
    totals: dict[str, list[int]] = {}
    for sources in by_problem.values():
        for s in sources:
            t = totals.setdefault(s, [0, 0])
            t[0] += 1
            t[1] += len(sources) > 1
    return {s: shared / n for s, (n, shared) in totals.items()}


def _default_on() -> set[str]:
    from pipeline.collect import discover
    return {n for n, c in discover().items() if c.default_on and c.tos_class != "restricted"}


def _stale_days(conn) -> Values:
    rows = conn.execute(
        "SELECT source, COALESCE(julianday('now') - julianday(last_success_at), 9999) AS d"
        " FROM collector_health").fetchall()
    on = _default_on()
    return {r["source"]: r["d"] for r in rows if r["source"] in on}


@metric("sources", "collector_days_since_ok")
def collector_days_since_ok(conn) -> Values:
    """Days since each default-on collector last succeeded (9999 = never)."""
    return _stale_days(conn)


@metric("sources", "collectors_stale")
def collectors_stale(conn) -> Values:
    """Default-on collectors with no success in STALE_DAYS."""
    return {"": float(sum(d > STALE_DAYS for d in _stale_days(conn).values()))}


@metric("sources", "llm_cost_usd_7d")
def llm_cost(conn) -> Values:
    """API-equivalent LLM cost logged by any stage in the last seven days."""
    v = conn.execute(
        "SELECT COALESCE(SUM(value), 0) FROM metric WHERE name LIKE '%cost_usd'"
        " AND julianday('now') - julianday(recorded_at) <= ?", (COST_WINDOW_DAYS,)).fetchone()[0]
    return {"": float(v)}


# --- Coverage ---------------------------------------------------------------------------

def _region_counts(conn) -> dict[str, int]:
    counts = {r: 0 for r in (*TARGET_SHARE, "other")}
    for r in conn.execute(f"SELECT country, COUNT(*) AS n FROM ({ACTIVE_PAIN_ITEM_SQL}) GROUP BY country"):
        counts[region(r["country"])] += r["n"]
    return counts


@metric("coverage", "region_share")
def region_share(conn) -> Values:
    """Share of active pains from the US, the EEA, the UK, and elsewhere."""
    counts = _region_counts(conn)
    total = sum(counts.values())
    return {k: v / total for k, v in counts.items()} if total else {}


@metric("coverage", "region_gap")
def region_gap(conn) -> Values:
    """How far each required region's share of active pains sits below its target."""
    share = region_share(conn)
    return {r: max(0.0, t - share.get(r, 0.0)) for r, t in TARGET_SHARE.items()} if share else {}


def _labeled_by_source(conn) -> dict[str, int]:
    labels = evals.load_labels(evals.labels_path("working"))
    out: dict[str, int] = {}
    for item_id, rec in labels.items():
        if rec["label"] != "unsure":
            out[rec.get("source") or "?"] = out.get(rec.get("source") or "?", 0) + 1
    return out


@metric("coverage", "eval_labeled")
def eval_labeled(conn) -> Values:
    """Working-set labels per source (unsure excluded)."""
    return {k: float(v) for k, v in _labeled_by_source(conn).items()}


@metric("coverage", "eval_gap_sources")
def eval_gap_sources(conn) -> Values:
    """Sources with plenty of extractions but too few working labels to trust their scores."""
    labeled = _labeled_by_source(conn)
    rows = conn.execute(
        f"SELECT r.source, COUNT(*) AS n FROM ({ACTIVE_EXTRACTION_SQL}) x"
        " JOIN raw_item r ON r.id = x.raw_item_id GROUP BY r.source").fetchall()
    return {"": float(sum(r["n"] >= EVAL_MIN_EXTRACTED and labeled.get(r["source"], 0) < EVAL_MIN_LABELED
                          for r in rows))}


# --- Extraction -------------------------------------------------------------------------

def _working_confusion(conn):
    prompt_id, version = evals.current_prompt(conn)
    labels = evals.load_labels(evals.labels_path("working"))
    if prompt_id is None or not labels:
        return None
    return evals.evaluate(conn, labels, prompt_id, "working", version).overall


def _score(name: str):
    def compute(conn) -> Values:
        c = _working_confusion(conn)
        v = getattr(c, name) if c else None
        return {"": v} if v is not None else {}
    compute.__doc__ = f"Working-set {name} of the current extraction prompt, recomputed from the labels."
    return compute


for _name in ("precision", "recall", "f1"):
    REGISTRY.append(Metric("extraction", f"working_{_name}", _score(_name),
                           f"Working-set {_name} of the current prompt, recomputed from the labels."))


@metric("extraction", "quote_ungrounded_rate")
def quote_ungrounded(conn) -> Values:
    """Share of active verbatim quotes missing from their item's text (fabricated evidence)."""
    checked = missing = 0
    for r in conn.execute(ACTIVE_PAIN_ITEM_SQL):
        if r["quote_kind"] != "verbatim" or r["text_discarded_at"] is not None or not r["body"]:
            continue
        checked += 1
        missing += find_quote(plain_text(r["body"]), r["quote"]) is None
    return {"": missing / checked} if checked else {}


@metric("extraction", "solution_leak_rate")
def solution_leak(conn) -> Values:
    """Share of active pains whose problem text asks for a product (a solution, not a problem)."""
    rows = conn.execute(f"SELECT problem FROM ({ACTIVE_PAIN_ITEM_SQL})").fetchall()
    return {"": sum(bool(SOLUTION_RE.search(r["problem"])) for r in rows) / len(rows)} if rows else {}


@metric("extraction", "backlog_items")
def backlog(conn) -> Values:
    """Raw items with text still present and no extraction yet."""
    n = conn.execute("SELECT COUNT(*) FROM raw_item r WHERE r.text_discarded_at IS NULL AND NOT EXISTS"
                     " (SELECT 1 FROM extraction x WHERE x.raw_item_id = r.id)").fetchone()[0]
    return {"": float(n)}


# --- Mapping ----------------------------------------------------------------------------

@metric("mapping", "pool_share")
def pool_share(conn) -> Values:
    """Share of active pains that belong to no problem."""
    row = conn.execute(
        f"SELECT COUNT(*) AS n, SUM(m.pain_id IS NULL) AS pooled FROM ({ACTIVE_PAIN_ITEM_SQL}) i"
        " LEFT JOIN problem_member m ON m.pain_id = i.pain_id").fetchone()
    return {"": row["pooled"] / row["n"]} if row["n"] else {}


@metric("mapping", "merge_queue_open")
def merge_queue(conn) -> Values:
    """Open merge candidates awaiting Edgar."""
    return {"": float(conn.execute("SELECT COUNT(*) FROM merge_candidate WHERE status = 'open'").fetchone()[0])}


@metric("mapping", "duplicate_rate")
def duplicate_rate(conn) -> Values:
    """Share of live problems with a near-twin (centroid cosine at the merge floor) Edgar has not kept apart."""
    import numpy as np
    from pipeline.embed import from_blob
    from pipeline.mapping import MERGE_LOW
    rows = conn.execute("SELECT id, centroid FROM problem WHERE status != 'merged'"
                        " AND centroid IS NOT NULL ORDER BY id").fetchall()
    if len(rows) < 2:
        return {"": 0.0} if rows else {}
    # Centroids from different embedding models (different sizes) are never compared.
    by_dim: dict[int, list[tuple[int, np.ndarray]]] = {}
    for r in rows:
        v = from_blob(r["centroid"])
        by_dim.setdefault(len(v), []).append((r["id"], v))
    kept_apart = {(r[0], r[1]) for r in conn.execute(
        "SELECT a_id, b_id FROM merge_candidate WHERE status = 'rejected'")}
    twins: set[int] = set()
    for group in by_dim.values():
        ids = [g[0] for g in group]
        X = np.vstack([g[1] for g in group])
        X /= np.linalg.norm(X, axis=1, keepdims=True).clip(1e-9)
        sim = X @ X.T
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if sim[i, j] >= MERGE_LOW and (ids[i], ids[j]) not in kept_apart:
                    twins.update((ids[i], ids[j]))
    return {"": len(twins) / len(rows)}


@metric("mapping", "problem_turnover")
def problem_turnover(conn) -> Values:
    """Share of live problems created by the latest map run (week-to-week churn)."""
    run = conn.execute("SELECT id FROM run WHERE kind = 'map' AND status = 'ok' ORDER BY id DESC LIMIT 1").fetchone()
    live = conn.execute("SELECT COUNT(*) FROM problem WHERE status != 'merged'").fetchone()[0]
    if run is None or not live:
        return {}
    new = conn.execute("SELECT COUNT(*) FROM problem WHERE status != 'merged' AND created_run_id = ?",
                       (run["id"],)).fetchone()[0]
    return {"": new / live}


@metric("mapping", "merge_rate")
def merge_rate(conn) -> Values:
    """Problems merged away, as a share of all problems ever made."""
    merged = conn.execute("SELECT COUNT(*) FROM problem_alias").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM problem").fetchone()[0]
    return {"": merged / total} if total else {}


# --- Methodology ------------------------------------------------------------------------

@metric("methodology", "decision_reason_count")
def decision_reasons(conn) -> Values:
    """Steering decisions by reason code (the kill-reason distribution)."""
    return {r["reason"]: float(r["n"]) for r in conn.execute(
        "SELECT reason, COUNT(*) AS n FROM decision WHERE reason IS NOT NULL GROUP BY reason")}


# --- Running them -----------------------------------------------------------------------

def compute_all(conn: sqlite3.Connection, only: set[str] | None = None) -> dict[tuple[str, str, str], float]:
    """{(layer, name, subject): value} for every registered metric (or those named in `only`)."""
    out = {}
    for m in REGISTRY:
        if only is not None and m.key not in only:
            continue
        for subject, value in m.compute(conn).items():
            if value is not None:
                out[(m.layer, m.name, subject)] = float(value)
    return out
