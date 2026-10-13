"""Stage 3: map pains onto stable canonical problems.

One mapping run (a `run` row of kind 'map'):

1. Embed active pains that lack a vector (unless the caller already did). A pain is
   active when it belongs to its item's extraction under the current extract prompt, or
   to its latest extraction (pipeline.embed.ACTIVE_PAIN_SQL).
2. Read everything else in one read snapshot, compute the run in memory, and write the
   result in one short transaction, so HDBSCAN never holds the write lock.
3. Carry membership across re-extraction: an unassigned pain whose item had a superseded
   pain in a problem joins that problem (assigned_by 'carried', keeping the original
   assigned_run_id), so re-extraction neither moves members nor counts as new mentions.
4. Assign each remaining unassigned pain to the nearest non-merged problem centroid when
   cosine similarity reaches ASSIGN_THRESHOLD.
5. Cluster the remaining pool (this run's leftovers plus every earlier run's) with
   HDBSCAN. A cohesive cluster whose centroid already clears ASSIGN_THRESHOLD against an
   existing problem folds into it; otherwise it becomes a new problem when it has at
   least MIN_AUTHORS distinct authors.
6. A centroid is the mean of its problem's active members, so problems that gained or
   lost members move. Then the pool gets one more centroid pass (so pains matching a
   problem born this run join now).
7. Queue near-duplicate problem pairs for Edgar's merge decision.
8. Write one snapshot row per non-merged problem and log metrics.

Identity matters more than the algorithm (docs/research/04): problems persist across
runs, members never move except by an explicit merge, and nothing is deleted.

The thresholds below are calibrated guesses for multilingual-e5-small; stage 8 tunes
them against labelled pairs.
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass, field

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
    SELECT a.id AS pain_id, a.idx, a.problem, a.quote, r.id AS raw_item_id, r.source, r.country,
           COALESCE(r.author_hash, 'item:' || r.id) AS author_key
    FROM ({ACTIVE_PAIN_SQL}) a
    JOIN extraction x ON x.id = a.extraction_id
    JOIN raw_item r ON r.id = x.raw_item_id
"""


@dataclass
class MapResult:
    run_id: int
    embedded: int = 0
    carried: int = 0
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

def recompute_centroid(conn: sqlite3.Connection, problem_id: int, model: str) -> bool:
    """Set a problem's centroid to the renormalized mean of its active members' vectors.

    Leaves the centroid alone when no member has a vector for `model`.
    """
    rows = conn.execute(
        f"SELECT e.vec FROM problem_member m JOIN ({ACTIVE_PAIN_SQL}) a ON a.id = m.pain_id"
        " JOIN embedding e ON e.pain_id = m.pain_id AND e.model = ?"
        " WHERE m.problem_id = ? ORDER BY m.pain_id", (model, problem_id),
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


# --- Read: one snapshot of what the run needs ----------------------------------------

@dataclass
class _Pred:
    """A superseded pain that was a problem member; its item's new pain inherits it."""
    pain_id: int
    extraction_id: int
    idx: int
    problem_id: int             # alias-resolved
    assigned_run_id: int
    similarity: float
    vec: np.ndarray | None      # None when it has no vector for this run's model


@dataclass
class _Inputs:
    model: str
    ids: list[int]                       # active pains with a vector for the model
    X: np.ndarray                        # their vectors; row i belongs to ids[i]
    idx: list[int]                       # each pain's position within its item
    item: list[int]                      # raw item id
    author: list[str]
    text: list[str]                      # problem sentence, a new problem's first title
    target: list[int | None]             # problem it belongs to; None while in the pool
    stored: dict[int, tuple[bytes | None, str | None]]  # non-merged problem: centroid, model
    preds: dict[int, list[_Pred]] = field(default_factory=dict)  # raw item: superseded members


def _read(conn: sqlite3.Connection, model: str) -> _Inputs:
    """Load the run's inputs inside one read transaction (WAL readers block no writer)."""
    conn.execute("BEGIN")
    try:
        rows = conn.execute(
            f"SELECT i.pain_id, i.idx, i.raw_item_id, i.author_key, i.problem, e.vec, m.problem_id"
            f" FROM ({_PAIN_INFO_SQL}) i"
            " JOIN embedding e ON e.pain_id = i.pain_id AND e.model = ?"
            " LEFT JOIN problem_member m ON m.pain_id = i.pain_id"
            " ORDER BY i.pain_id", (model,),
        ).fetchall()
        stored = {r["id"]: (r["centroid"], r["centroid_model"]) for r in conn.execute(
            "SELECT id, centroid, centroid_model FROM problem WHERE status != 'merged'")}
        inp = _Inputs(
            model=model, ids=[r["pain_id"] for r in rows],
            X=(np.vstack([from_blob(r["vec"]) for r in rows]) if rows
               else np.zeros((0, 0), dtype=np.float32)),
            idx=[r["idx"] for r in rows], item=[r["raw_item_id"] for r in rows],
            author=[r["author_key"] for r in rows], text=[r["problem"] for r in rows],
            target=[r["problem_id"] for r in rows], stored=stored,
        )
        pool_items = {it for it, t in zip(inp.item, inp.target) if t is None}
        if pool_items:
            # Superseded member pains of items with a pain in the pool. Per item, only the
            # latest extraction that had members counts.
            for r in conn.execute(
                    "SELECT p.id, p.idx, p.extraction_id, x.raw_item_id, m.problem_id,"
                    " m.assigned_run_id, m.similarity, e.vec"
                    " FROM problem_member m JOIN pain p ON p.id = m.pain_id"
                    " JOIN extraction x ON x.id = p.extraction_id"
                    " LEFT JOIN embedding e ON e.pain_id = p.id AND e.model = ?"
                    f" WHERE p.id NOT IN (SELECT id FROM ({ACTIVE_PAIN_SQL}))"
                    " ORDER BY x.raw_item_id, p.extraction_id DESC, p.idx", (model,)):
                if r["raw_item_id"] not in pool_items:
                    continue
                group = inp.preds.setdefault(r["raw_item_id"], [])
                if group and group[0].extraction_id != r["extraction_id"]:
                    continue  # an older extraction of the same item
                group.append(_Pred(
                    r["id"], r["extraction_id"], r["idx"], resolve(conn, r["problem_id"]),
                    r["assigned_run_id"], r["similarity"],
                    from_blob(r["vec"]) if r["vec"] is not None else None))
        return inp
    finally:
        conn.rollback()  # ends the read transaction; nothing was written


# --- Compute: the whole run in memory -------------------------------------------------

@dataclass
class _Plan:
    # (pain_id, problem, similarity, assigned_run_id or None for this run, assigned_by).
    # A problem id below zero stands for a problem this run creates.
    members: list[tuple[int, int, float, int | None, str]] = field(default_factory=list)
    new: dict[int, str] = field(default_factory=dict)            # placeholder id: title
    centroids: dict[int, np.ndarray] = field(default_factory=dict)


def _match(rows: list[int], preds: list[_Pred], inp: _Inputs) -> list[tuple[int, _Pred]]:
    """Pair an item's new pains with its superseded member pains, one to one.

    Equal idx first; the rest by highest cosine similarity (pairs lacking a vector last).
    """
    rows, preds = list(rows), list(preds)
    pairs = []
    for p in list(preds):
        r = next((r for r in rows if inp.idx[r] == p.idx), None)
        if r is not None:
            pairs.append((r, p))
            rows.remove(r)
            preds.remove(p)
    ranked = sorted(
        (-float(inp.X[r] @ p.vec) if p.vec is not None else 2.0, inp.idx[r], p.idx, r, k)
        for r in rows for k, p in enumerate(preds))
    used_rows, used_preds = set(), set()
    for *_, r, k in ranked:
        if r not in used_rows and k not in used_preds:
            pairs.append((r, preds[k]))
            used_rows.add(r)
            used_preds.add(k)
    return pairs


def _plan(inp: _Inputs, res: MapResult) -> _Plan:
    plan = _Plan()
    target = list(inp.target)
    rows_of: dict[int, list[int]] = {}
    for i, t in enumerate(target):
        if t is not None:
            rows_of.setdefault(t, []).append(i)
    C = plan.centroids  # problem -> current centroid; only problems with one take part

    def refresh(t: int) -> None:
        if (t < 0 or t in inp.stored) and rows_of.get(t):
            C[t] = normalize(inp.X[rows_of[t]].mean(axis=0))

    def join(i: int, t: int, sim: float, run: int | None, by: str) -> None:
        target[i] = t
        rows_of.setdefault(t, []).append(i)
        plan.members.append((inp.ids[i], t, float(sim), run, by))

    def ordered() -> list[int]:  # existing problems by id, then this run's in birth order
        return sorted(C, key=lambda t: (t < 0, abs(t)))

    def assign_pass() -> set[int]:
        pids, todo = ordered(), [i for i, t in enumerate(target) if t is None]
        if not pids or not todo:
            return set()
        sims = inp.X[todo] @ np.vstack([C[p] for p in pids]).T
        best = sims.argmax(axis=1)
        best_sim = sims[np.arange(len(todo)), best]
        hits = np.flatnonzero(best_sim >= ASSIGN_THRESHOLD)
        for k in hits:
            join(todo[k], pids[best[k]], best_sim[k], None, "centroid")
        res.assigned_centroid += len(hits)
        return {pids[best[k]] for k in hits}

    # Centroids follow the active members, so a problem whose members were superseded
    # moves too. A problem with no active member vector keeps its stored centroid.
    for pid, (blob, model) in inp.stored.items():
        if rows_of.get(pid):
            refresh(pid)
        elif blob is not None and model == inp.model:
            C[pid] = from_blob(blob)

    # a. Carry membership across re-extraction.
    by_item: dict[int, list[int]] = {}
    for i, t in enumerate(target):
        if t is None and inp.item[i] in inp.preds:
            by_item.setdefault(inp.item[i], []).append(i)
    carried: set[int] = set()
    for item, rows in by_item.items():
        for i, pred in _match(rows, inp.preds[item], inp):
            if pred.problem_id not in inp.stored:
                continue
            sim = float(inp.X[i] @ C[pred.problem_id]) if pred.problem_id in C else pred.similarity
            join(i, pred.problem_id, sim, pred.assigned_run_id, "carried")
            carried.add(pred.problem_id)
            res.carried += 1
    for t in carried:
        refresh(t)

    # b. Nearest centroid.
    gained = assign_pass()
    for t in gained:
        refresh(t)

    # c. Cluster the pool; cohesive clusters fold into a problem or found a new one.
    pids = ordered()
    M = np.vstack([C[p] for p in pids]) if pids else None
    where = [i for i, t in enumerate(target) if t is None]
    P = inp.X[where] if where else np.zeros((0, 0), dtype=np.float32)
    for idx in _candidate_groups(P):
        res.clusters_found += 1
        idx = _trim(P, idx)  # loose members go back to the pool
        if len(idx) < MIN_CLUSTER_SIZE:
            res.clusters_rejected += 1
            continue
        centroid = normalize(P[idx].mean(axis=0))
        rows = [where[k] for k in idx]
        t, sims = None, P[idx] @ centroid
        if M is not None:  # the cluster as a whole may match a problem no single member reached
            to_existing = M @ centroid
            j = int(to_existing.argmax())
            if to_existing[j] >= ASSIGN_THRESHOLD:
                t, sims = pids[j], P[idx] @ M[j]
                res.clusters_folded += 1
        if t is None:
            if len({inp.author[r] for r in rows}) < MIN_AUTHORS:
                res.clusters_rejected += 1
                continue
            t = -(len(plan.new) + 1)
            plan.new[t] = inp.text[rows[int(sims.argmax())]]  # until the curator renames it
            C[t] = centroid
            res.new_problems += 1
        for r, s in zip(rows, sims):
            join(r, t, s, None, "cluster")
        gained.add(t)
        res.assigned_cluster += len(rows)

    # d. Centroids follow their members. Then one more centroid pass, so pool pains that
    # match a problem born this run join it now rather than at the next run.
    for t in gained:
        refresh(t)
    for t in assign_pass():
        refresh(t)
    res.pool_size_after = sum(t is None for t in target)
    return plan


# --- Write: one short transaction ------------------------------------------------------

def _write(conn: sqlite3.Connection, run_id: int, inp: _Inputs, plan: _Plan,
           res: MapResult) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        real: dict[int, int] = {}
        for t, title in plan.new.items():
            real[t] = conn.execute(
                "INSERT INTO problem (title, title_source, centroid, centroid_model, created_run_id)"
                " VALUES (?, 'auto', ?, ?, ?)",
                (title, to_blob(plan.centroids[t]), inp.model, run_id)).lastrowid
        conn.executemany(
            "INSERT INTO problem_member (pain_id, problem_id, similarity, assigned_run_id, assigned_by)"
            " VALUES (?, ?, ?, ?, ?)",
            [(p, real.get(t, t), s, run_id if r is None else r, by)
             for p, t, s, r, by in plan.members])
        for t, c in plan.centroids.items():
            if t > 0 and inp.stored[t] != (to_blob(c), inp.model):
                conn.execute(
                    "UPDATE problem SET centroid = ?, centroid_model = ?,"
                    " updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                    (to_blob(c), inp.model, t))
        final = sorted(((real.get(t, t), c) for t, c in plan.centroids.items()), key=lambda x: x[0])
        _queue_merges(conn, run_id, [p for p, _ in final],
                      np.vstack([c for _, c in final]) if final else np.zeros((0, 0)))
        res.merge_candidates_open = conn.execute(
            "SELECT COUNT(*) FROM merge_candidate WHERE status = 'open'").fetchone()[0]
        res.problems_total = _snapshot(conn, run_id)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


# --- The run --------------------------------------------------------------------------

def map_run(conn: sqlite3.Connection, embedder: Embedder | None = None,
            model: str | None = None) -> MapResult:
    """Run one mapping pass. With an embedder, embed missing vectors first."""
    model = embedder.model_id if embedder else (model or DEFAULT_MODEL)
    with runs.run(conn, "map") as run_id:
        res = MapResult(run_id)
        if embedder is not None:
            res.embedded = embed_pending(conn, embedder)
        inp = _read(conn, model)
        plan = _plan(inp, res)            # HDBSCAN runs here, outside any transaction
        _write(conn, run_id, inp, plan, res)  # every mapping write lands together, or none
        _log_metrics(conn, run_id, res)
    return res


def _queue_merges(conn: sqlite3.Connection, run_id: int, pids: list[int], C: np.ndarray) -> None:
    """Upsert open merge candidates for close problem pairs; drop stale open ones.

    `pids` must ascend (a_id < b_id); row i of C is the centroid of pids[i]. Pairs at or
    above ASSIGN_THRESHOLD are queued too: they arise when centroids drift together or
    two clusters form in one run, and they are the likeliest duplicates. Decided pairs
    (merged, rejected) are never reopened.
    """
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
    """Per non-merged problem: mentions, distinct authors, sources, countries, new mentions.

    Every count covers ACTIVE member pains only (ACTIVE_PAIN_SQL): a pain superseded by
    re-extraction drops out, and its carried successor takes its place. `mentions` is the
    number of active members; `new_mentions` those assigned in `run_id` (carried members
    keep their original run, so re-extraction never shows up as new demand).
    """
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
    """One row per non-merged problem; mentions = active member pains (see problem_stats)."""
    stats = problem_stats(conn, run_id)
    conn.executemany(
        "INSERT OR REPLACE INTO snapshot (run_id, problem_id, mentions, distinct_authors,"
        " sources, countries, new_mentions) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(run_id, pid, s["mentions"], s["distinct_authors"], s["sources"], s["countries"],
          s["new_mentions"]) for pid, s in stats.items()],
    )
    return len(stats)


def _log_metrics(conn: sqlite3.Connection, run_id: int, res: MapResult) -> None:
    for name in ("pains_carried", "pains_assigned_centroid", "pains_assigned_cluster",
                 "pool_size_after", "new_problems", "merge_candidates_open", "problems_total",
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
    print(f"map run {r.run_id}: embedded {r.embedded}, carried {r.carried} across re-extraction,"
          f" assigned {r.assigned_centroid} by centroid"
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
