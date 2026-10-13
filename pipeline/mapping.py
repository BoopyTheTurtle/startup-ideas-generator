"""Stage 3: map pains onto stable canonical problems.

One mapping run (a `run` row of kind 'map'):

1. Embed pains that lack a vector (unless the caller already did).
2. Assign each unassigned pain to the nearest non-merged problem centroid when cosine
   similarity reaches ASSIGN_THRESHOLD.
3. Cluster the remaining pool (this run's leftovers plus every earlier run's) with
   HDBSCAN. A cohesive cluster whose centroid already clears ASSIGN_THRESHOLD against an
   existing problem folds into it; otherwise it becomes a new problem when it has at
   least MIN_AUTHORS distinct authors.
4. Recompute the centroid of every problem that gained members, then give the rest of
   the pool one more centroid pass (so pains matching a problem born this run join now).
5. Queue near-duplicate problem pairs for Edgar's merge decision.
6. Write one snapshot row per non-merged problem and log metrics.

Identity matters more than the algorithm (docs/research/04): problems persist across
runs, members never move except by an explicit merge, and nothing is deleted.

The thresholds below are calibrated guesses for multilingual-e5-small; stage 8 tunes
them against labelled pairs.
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass

import numpy as np

from pipeline import runs
from pipeline.embed import ACTIVE_PAIN_SQL, DEFAULT_MODEL, Embedder, embed_pending, from_blob, normalize, to_blob

# --- Tunable by stage 8 -------------------------------------------------------------
# SPEC and report 04 start at 0.88 (assign) and 0.80-0.88 (merge band), values borrowed
# from a project that used another embedding model. multilingual-e5 crowds cosines into
# 0.7-1.0 (its model card, FAQ 3): on 266 real pains (2026-10-13) the median pair scored
# 0.81 and every pain scored >= 0.88 against the corpus mean. At 0.88, two runs put 260
# of the 266 pains into 14 mostly unrelated problems and queued all 91 problem pairs for
# merging. The values below kept only same-problem groups on that sample. Members never
# move without a merge, so a false join costs more than a false split (the merge queue
# repairs splits). Retune on labelled pairs once the eval set has them.
ASSIGN_THRESHOLD = 0.94     # cosine to a centroid needed to join an existing problem
MERGE_LOW = 0.91            # problem pairs at or above this cosine enter the merge queue
CLUSTER_MIN_COHESION = 0.93  # mean pairwise cosine a pool cluster needs; looser ones are trimmed
MIN_CLUSTER_SIZE = 3        # HDBSCAN min_cluster_size
MIN_SAMPLES = 2             # HDBSCAN min_samples (lower = fewer pains labelled noise)
MIN_AUTHORS = 3             # distinct authors a cluster needs to become a problem
# --------------------------------------------------------------------------------------

# Pains in effect, with what snapshots and the author rule need. An item without an
# author hash counts as its own author ("item:<id>"), so citizens' feedback still counts.
_PAIN_INFO_SQL = f"""
    SELECT a.id AS pain_id, a.problem, a.quote, r.id AS raw_item_id, r.source, r.country,
           COALESCE(r.author_hash, 'item:' || r.id) AS author_key
    FROM ({ACTIVE_PAIN_SQL}) a
    JOIN extraction x ON x.id = a.extraction_id
    JOIN raw_item r ON r.id = x.raw_item_id
"""


@dataclass
class MapResult:
    run_id: int
    embedded: int = 0
    assigned_centroid: int = 0
    assigned_cluster: int = 0
    clusters_found: int = 0
    clusters_folded: int = 0
    clusters_rejected: int = 0
    new_problems: int = 0
    pool_size_after: int = 0
    merge_candidates_open: int = 0
    problems_total: int = 0


# --- Vectors --------------------------------------------------------------------------

def _centroids(conn: sqlite3.Connection, model: str) -> tuple[list[int], np.ndarray]:
    rows = conn.execute(
        "SELECT id, centroid FROM problem WHERE status != 'merged' AND centroid IS NOT NULL"
        " AND centroid_model = ? ORDER BY id", (model,),
    ).fetchall()
    if not rows:
        return [], np.zeros((0, 0), dtype=np.float32)
    return [r["id"] for r in rows], np.vstack([from_blob(r["centroid"]) for r in rows])


def _unassigned(conn: sqlite3.Connection, model: str) -> tuple[list[int], np.ndarray]:
    rows = conn.execute(
        f"SELECT a.id, e.vec FROM ({ACTIVE_PAIN_SQL}) a"
        " JOIN embedding e ON e.pain_id = a.id AND e.model = ?"
        " LEFT JOIN problem_member m ON m.pain_id = a.id"
        " WHERE m.pain_id IS NULL ORDER BY a.id", (model,),
    ).fetchall()
    if not rows:
        return [], np.zeros((0, 0), dtype=np.float32)
    return [r["id"] for r in rows], np.vstack([from_blob(r["vec"]) for r in rows])


def recompute_centroid(conn: sqlite3.Connection, problem_id: int, model: str) -> bool:
    """Set a problem's centroid to the renormalized mean of its active members' vectors.

    Leaves the centroid alone when no member has a vector for `model`.
    """
    rows = conn.execute(
        f"SELECT e.vec FROM problem_member m JOIN ({ACTIVE_PAIN_SQL}) a ON a.id = m.pain_id"
        " JOIN embedding e ON e.pain_id = m.pain_id AND e.model = ?"
        " WHERE m.problem_id = ?", (model, problem_id),
    ).fetchall()
    if not rows:
        return False
    centroid = normalize(np.vstack([from_blob(r["vec"]) for r in rows]).mean(axis=0))
    conn.execute(
        "UPDATE problem SET centroid = ?, centroid_model = ?,"
        " updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
        (to_blob(centroid), model, problem_id),
    )
    return True


def _refresh_stale_centroids(conn: sqlite3.Connection, model: str) -> None:
    """Problems whose centroid came from another model (or none) get one from this model."""
    stale = conn.execute(
        "SELECT id FROM problem WHERE status != 'merged'"
        " AND (centroid IS NULL OR centroid_model IS NOT ?)", (model,),
    ).fetchall()
    for r in stale:
        recompute_centroid(conn, r["id"], model)


def _candidate_groups(vectors: np.ndarray) -> list[np.ndarray]:
    """Index arrays of candidate clusters in the pool.

    HDBSCAN on unit vectors: euclidean distance orders pairs exactly as cosine does.
    'leaf' selection keeps the finest clusters; 'eom' merged most of a real 61-pain pool
    into one loose blob, because e5 similarities crowd into 0.75-0.95. UMAP is left out:
    it adds a heavy dependency (numba), and the cohesion trim guards quality instead.
    Leaf selection never returns the whole pool as one cluster, so a pool in which
    HDBSCAN finds nothing is offered whole, and the cohesion trim decides.
    """
    if len(vectors) < MIN_CLUSTER_SIZE:
        return []
    from sklearn.cluster import HDBSCAN
    labels = HDBSCAN(
        min_cluster_size=MIN_CLUSTER_SIZE, min_samples=MIN_SAMPLES, metric="euclidean",
        cluster_selection_method="leaf", copy=True,
    ).fit(vectors).labels_
    groups = [np.flatnonzero(labels == lab) for lab in sorted(set(labels.tolist()) - {-1})]
    return groups or [np.arange(len(vectors))]


def _trim(vectors: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Drop the least typical member until mean pairwise cosine reaches CLUSTER_MIN_COHESION.

    Returns the surviving indices in their original order (possibly fewer than
    MIN_CLUSTER_SIZE, which the caller rejects).
    """
    idx = np.asarray(idx)
    while len(idx) >= MIN_CLUSTER_SIZE:
        V = vectors[idx]
        n = len(idx)
        to_others = (V @ V.sum(axis=0) - 1) / (n - 1)  # each member's mean cosine to the rest
        if to_others.mean() >= CLUSTER_MIN_COHESION:
            break
        idx = np.delete(idx, int(to_others.argmin()))
    return idx


def _insert_members(conn, run_id: int, problem_id: int, pain_ids, sims, by: str) -> None:
    conn.executemany(
        "INSERT INTO problem_member (pain_id, problem_id, similarity, assigned_run_id, assigned_by)"
        " VALUES (?, ?, ?, ?, ?)",
        [(int(p), problem_id, float(s), run_id, by) for p, s in zip(pain_ids, sims)],
    )


# --- The run --------------------------------------------------------------------------

def map_run(conn: sqlite3.Connection, embedder: Embedder | None = None,
            model: str | None = None) -> MapResult:
    """Run one mapping pass. With an embedder, embed missing vectors first."""
    model = embedder.model_id if embedder else (model or DEFAULT_MODEL)
    with runs.run(conn, "map") as run_id:
        res = MapResult(run_id)
        if embedder is not None:
            res.embedded = embed_pending(conn, embedder)
        with conn:  # every mapping write lands together, or not at all
            _map(conn, run_id, model, res)
        _log_metrics(conn, run_id, res)
    return res


def _assign_to_centroids(conn, run_id: int, model: str, ids: list[int], X: np.ndarray,
                         pool: np.ndarray, gained: set[int]) -> int:
    """Assign pool pains whose nearest centroid clears ASSIGN_THRESHOLD; update `pool`."""
    pids, C = _centroids(conn, model)
    todo = np.flatnonzero(pool)
    if not pids or not len(todo):
        return 0
    sims = X[todo] @ C.T
    best = sims.argmax(axis=1)
    best_sim = sims[np.arange(len(todo)), best]
    hits = np.flatnonzero(best_sim >= ASSIGN_THRESHOLD)
    for k in hits:
        pid = pids[best[k]]
        _insert_members(conn, run_id, pid, [ids[todo[k]]], [best_sim[k]], "centroid")
        gained.add(pid)
        pool[todo[k]] = False
    return len(hits)


def _map(conn: sqlite3.Connection, run_id: int, model: str, res: MapResult) -> None:
    _refresh_stale_centroids(conn, model)
    ids, X = _unassigned(conn, model)
    pool = np.ones(len(ids), dtype=bool)  # True while a pain is unassigned
    gained: set[int] = set()

    # a. Nearest centroid.
    res.assigned_centroid = _assign_to_centroids(conn, run_id, model, ids, X, pool, gained)

    # b, c. Cluster the pool; cohesive clusters fold into a problem or found a new one.
    pids, C = _centroids(conn, model)
    where = np.flatnonzero(pool)
    P = X[where] if len(where) else np.zeros((0, 0), dtype=np.float32)
    pool_ids = [ids[i] for i in where]
    authors, texts = {}, {}
    if pool_ids:
        marks = ",".join("?" * len(pool_ids))
        for r in conn.execute(f"SELECT * FROM ({_PAIN_INFO_SQL}) WHERE pain_id IN ({marks})", pool_ids):
            authors[r["pain_id"]], texts[r["pain_id"]] = r["author_key"], r["problem"]
    for idx in _candidate_groups(P):
        res.clusters_found += 1
        idx = _trim(P, idx)  # loose members go back to the pool
        if len(idx) < MIN_CLUSTER_SIZE:
            res.clusters_rejected += 1
            continue
        centroid = normalize(P[idx].mean(axis=0))
        members = [pool_ids[i] for i in idx]
        target, sims = None, P[idx] @ centroid
        if pids:  # the cluster as a whole may match a problem that no single member reached
            to_existing = C @ centroid
            j = int(to_existing.argmax())
            if to_existing[j] >= ASSIGN_THRESHOLD:
                target, sims = pids[j], P[idx] @ C[j]
                res.clusters_folded += 1
        if target is None:
            if len({authors[p] for p in members}) < MIN_AUTHORS:
                res.clusters_rejected += 1
                continue
            title = texts[members[int(sims.argmax())]]  # until the curator renames it
            target = conn.execute(
                "INSERT INTO problem (title, title_source, centroid, centroid_model, created_run_id)"
                " VALUES (?, 'auto', ?, ?, ?)", (title, to_blob(centroid), model, run_id),
            ).lastrowid
            res.new_problems += 1
        _insert_members(conn, run_id, target, members, sims, "cluster")
        gained.add(target)
        pool[where[idx]] = False
        res.assigned_cluster += len(members)

    # d. Centroids follow their members. Then one more centroid pass, so pool pains that
    # match a problem born this run join it now rather than at the next run.
    for pid in sorted(gained):
        recompute_centroid(conn, pid, model)
    late: set[int] = set()
    res.assigned_centroid += _assign_to_centroids(conn, run_id, model, ids, X, pool, late)
    for pid in sorted(late):
        recompute_centroid(conn, pid, model)

    res.pool_size_after = int(pool.sum())
    _queue_merges(conn, run_id, model)
    res.merge_candidates_open = conn.execute(
        "SELECT COUNT(*) FROM merge_candidate WHERE status = 'open'").fetchone()[0]
    res.problems_total = _snapshot(conn, run_id)


def _queue_merges(conn: sqlite3.Connection, run_id: int, model: str) -> None:
    """Upsert open merge candidates for close problem pairs; drop stale open ones.

    Pairs at or above ASSIGN_THRESHOLD are queued too: they arise when centroids drift
    together or two clusters form in one run, and they are the likeliest duplicates.
    Decided pairs (merged, rejected) are never reopened.
    """
    pids, C = _centroids(conn, model)
    current: set[tuple[int, int]] = set()
    for start in range(0, len(pids), 1000):  # blocks keep the similarity matrix small
        block = C[start:start + 1000] @ C.T
        for bi, j in zip(*np.nonzero(block >= MERGE_LOW)):
            i = start + int(bi)
            if i >= j:
                continue
            a, b = pids[i], pids[int(j)]
            current.add((a, b))
            conn.execute(
                "INSERT INTO merge_candidate (a_id, b_id, similarity, run_id) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (a_id, b_id) DO UPDATE SET similarity = excluded.similarity,"
                " run_id = excluded.run_id WHERE merge_candidate.status = 'open'",
                (a, b, float(block[bi, j]), run_id),
            )
    stale = [(r["a_id"], r["b_id"]) for r in
             conn.execute("SELECT a_id, b_id FROM merge_candidate WHERE status = 'open'")
             if (r["a_id"], r["b_id"]) not in current]
    conn.executemany("DELETE FROM merge_candidate WHERE a_id = ? AND b_id = ?", stale)


def problem_stats(conn: sqlite3.Connection, run_id: int | None = None) -> dict[int, dict]:
    """Per non-merged problem: mentions, distinct authors, sources, countries, new mentions."""
    stats = {r["id"]: dict(mentions=0, distinct_authors=0, sources=0, countries=0, new_mentions=0)
             for r in conn.execute("SELECT id FROM problem WHERE status != 'merged'")}
    rows = conn.execute(
        "SELECT m.problem_id, COUNT(*) AS mentions,"
        " COUNT(DISTINCT i.author_key) AS distinct_authors,"
        " COUNT(DISTINCT i.source) AS sources, COUNT(DISTINCT i.country) AS countries,"
        " SUM(m.assigned_run_id IS ?) AS new_mentions"
        f" FROM problem_member m JOIN ({_PAIN_INFO_SQL}) i ON i.pain_id = m.pain_id"
        " GROUP BY m.problem_id", (run_id,),
    ).fetchall()
    for r in rows:
        if r["problem_id"] in stats:
            stats[r["problem_id"]] = {k: r[k] for k in
                                      ("mentions", "distinct_authors", "sources", "countries", "new_mentions")}
    return stats


def _snapshot(conn: sqlite3.Connection, run_id: int) -> int:
    stats = problem_stats(conn, run_id)
    conn.executemany(
        "INSERT OR REPLACE INTO snapshot (run_id, problem_id, mentions, distinct_authors,"
        " sources, countries, new_mentions) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(run_id, pid, s["mentions"], s["distinct_authors"], s["sources"], s["countries"],
          s["new_mentions"]) for pid, s in stats.items()],
    )
    return len(stats)


def _log_metrics(conn: sqlite3.Connection, run_id: int, res: MapResult) -> None:
    for name in ("pains_assigned_centroid", "pains_assigned_cluster", "pool_size_after",
                 "new_problems", "merge_candidates_open", "problems_total",
                 "clusters_found", "clusters_folded", "clusters_rejected"):
        runs.log_metric(conn, run_id, "mapping", name, getattr(res, name.replace("pains_", "")))
    runs.log_metric(conn, run_id, "mapping", "pains_embedded", res.embedded)
    # Coverage: how many live problems each source and country contributes to.
    for col, name in (("source", "problems_with_source"), ("country", "problems_with_country")):
        rows = conn.execute(
            f"SELECT i.{col} AS k, COUNT(DISTINCT m.problem_id) AS n FROM problem_member m"
            f" JOIN ({_PAIN_INFO_SQL}) i ON i.pain_id = m.pain_id"
            " JOIN problem p ON p.id = m.problem_id AND p.status != 'merged'"
            f" WHERE i.{col} IS NOT NULL GROUP BY i.{col}").fetchall()
        for r in rows:
            runs.log_metric(conn, run_id, "coverage", name, r["n"], subject=r["k"])


# --- Merges and aliases ---------------------------------------------------------------

def resolve(conn: sqlite3.Connection, problem_id: int) -> int:
    """Follow merge aliases to the problem an id now lives in."""
    seen = {problem_id}
    while True:
        row = conn.execute("SELECT new_id FROM problem_alias WHERE old_id = ?", (problem_id,)).fetchone()
        if row is None:
            return problem_id
        problem_id = row["new_id"]
        if problem_id in seen:
            raise RuntimeError(f"alias cycle at problem {problem_id}")
        seen.add(problem_id)


def merge(conn: sqlite3.Connection, keep_id: int, drop_id: int, reason: str) -> int:
    """Fold problem drop_id into keep_id. Returns the id kept (after alias resolution)."""
    keep = resolve(conn, keep_id)
    rows = {r["id"]: r for r in conn.execute(
        "SELECT id, status, centroid_model FROM problem WHERE id IN (?, ?)", (keep, drop_id))}
    if keep not in rows or drop_id not in rows:
        raise ValueError(f"unknown problem: {keep if keep not in rows else drop_id}")
    if keep == drop_id:
        raise ValueError("cannot merge a problem into itself")
    if rows[drop_id]["status"] == "merged":
        raise ValueError(f"problem {drop_id} is already merged into {resolve(conn, drop_id)}")
    model = rows[keep]["centroid_model"] or rows[drop_id]["centroid_model"] or DEFAULT_MODEL
    a, b = sorted((keep, drop_id))
    with conn:
        conn.execute("UPDATE problem_member SET problem_id = ? WHERE problem_id = ?", (keep, drop_id))
        conn.execute(
            "UPDATE problem SET status = 'merged', merged_into = ?,"
            " updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?", (keep, drop_id))
        conn.execute("UPDATE problem_alias SET new_id = ? WHERE new_id = ?", (keep, drop_id))
        conn.execute("INSERT INTO problem_alias (old_id, new_id, reason) VALUES (?, ?, ?)",
                     (drop_id, keep, reason))
        recompute_centroid(conn, keep, model)
        conn.execute("UPDATE merge_candidate SET status = 'merged' WHERE a_id = ? AND b_id = ?", (a, b))
        conn.execute("DELETE FROM merge_candidate WHERE status = 'open' AND (a_id = ? OR b_id = ?)",
                     (drop_id, drop_id))
        conn.execute("INSERT INTO decision (problem_id, action, reason, note) VALUES (?, 'merge', ?, ?)",
                     (keep, reason, f"merged problem {drop_id} into {keep}"))
    return keep


# --- CLI ------------------------------------------------------------------------------

def cmd_map(args) -> int:
    from pipeline import db
    from pipeline.embed import E5Embedder
    conn = db.connect()
    db.migrate(conn)
    r = map_run(conn, embedder=None if args.no_embed else E5Embedder())
    print(f"map run {r.run_id}: embedded {r.embedded}, assigned {r.assigned_centroid} by centroid"
          f" + {r.assigned_cluster} by cluster; {r.new_problems} new problems"
          f" ({r.clusters_found} clusters, {r.clusters_folded} folded, {r.clusters_rejected} rejected);"
          f" pool {r.pool_size_after}; {r.problems_total} problems; {r.merge_candidates_open} merge candidates open")
    return 0


def _one_line(text: str | None, width: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= width else text[:width - 1] + "…"


def cmd_problems(args) -> int:
    from pipeline import db
    conn = db.connect()
    db.migrate(conn)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # quotes come in many scripts
    stats = problem_stats(conn)
    titles = {r["id"]: r for r in conn.execute("SELECT id, title, status FROM problem")}
    top = sorted(stats, key=lambda p: (-stats[p]["distinct_authors"], -stats[p]["mentions"], p))
    print(f"{'id':>5} {'authors':>7} {'members':>7} {'srcs':>4}  title / sample quote")
    for pid in top[:args.limit]:
        s = stats[pid]
        quote = conn.execute(
            f"SELECT i.quote FROM problem_member m JOIN ({_PAIN_INFO_SQL}) i ON i.pain_id = m.pain_id"
            " WHERE m.problem_id = ? ORDER BY m.similarity DESC LIMIT 1", (pid,)).fetchone()
        print(f"{pid:>5} {s['distinct_authors']:>7} {s['mentions']:>7} {s['sources']:>4}  "
              f"{_one_line(titles[pid]['title'], 90)} [{titles[pid]['status']}]")
        if quote:
            print(f"{'':>27}\"{_one_line(quote['quote'], 100)}\"")
    return 0


def cmd_merge(args) -> int:
    from pipeline import db
    conn = db.connect()
    db.migrate(conn)
    try:
        keep = merge(conn, args.keep, args.drop, args.reason)
    except ValueError as e:
        print(f"merge refused: {e}")
        return 1
    print(f"merged problem {args.drop} into {keep}")
    return 0


def register_cli(sub) -> None:
    m = sub.add_parser("map", help="assign pains to problems, cluster the pool, snapshot (stage 3)")
    m.add_argument("--no-embed", action="store_true", help="skip embedding new pains first")
    m.set_defaults(fn=cmd_map)
    p = sub.add_parser("problems", help="list top problems by distinct authors")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(fn=cmd_problems)
    g = sub.add_parser("merge", help="merge problem DROP into KEEP")
    g.add_argument("keep", type=int)
    g.add_argument("drop", type=int)
    g.add_argument("--reason", required=True, help="reason code or short note")
    g.set_defaults(fn=cmd_merge)
