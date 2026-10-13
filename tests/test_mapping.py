import numpy as np
import pytest

from pain_factory import MODEL, Factory, axis, near
from pipeline import mapping
from pipeline.embed import from_blob, normalize


@pytest.fixture
def f(tmp_path):
    return Factory(tmp_path)


T = mapping.ASSIGN_THRESHOLD  # tests derive their geometry from the tunable constants


def group(f, base, authors, cos=0.985, **kw):
    """Pains tightly around axis `base` (pairwise cosine ~cos**2), one per author."""
    return [f.pain(near(base, next(f.spare), cos), author=a, **kw) for a in authors]


def run(f):
    return mapping.map_run(f.conn, f.embedder)


def members(f, problem_id):
    return {r[0] for r in f.conn.execute(
        "SELECT pain_id FROM problem_member WHERE problem_id = ?", (problem_id,))}


def problems(f):
    return [r[0] for r in f.conn.execute("SELECT id FROM problem ORDER BY id")]


def test_centroid_assignment_respects_threshold(f):
    pid = f.problem(axis(0))
    above = f.pain(near(0, 5, T + 0.02))
    below = f.pain(near(0, 6, T - 0.05))
    r = run(f)
    assert r.assigned_centroid == 1
    row = f.conn.execute("SELECT * FROM problem_member WHERE pain_id = ?", (above,)).fetchone()
    assert (row["problem_id"], row["assigned_by"], row["assigned_run_id"]) == (pid, "centroid", r.run_id)
    assert row["similarity"] == pytest.approx(T + 0.02, abs=1e-5)
    assert f.conn.execute("SELECT 1 FROM problem_member WHERE pain_id = ?", (below,)).fetchone() is None
    assert r.pool_size_after == 1
    # The centroid now follows its only member.
    c = from_blob(f.conn.execute("SELECT centroid FROM problem WHERE id = ?", (pid,)).fetchone()[0])
    assert c @ near(0, 5, T + 0.02) == pytest.approx(1, abs=1e-5)


def test_cluster_becomes_problem_only_with_three_distinct_authors(f):
    a = group(f, 0, ["a", "b", "c"])
    group(f, 1, ["d", "d", "e"])                   # two people: stays in the pool
    nulls = group(f, 2, [None, None, None])        # authorless items each count
    f.pain(axis(3), author="z")                    # noise
    r = run(f)
    assert r.new_problems == 2 and r.assigned_cluster == 6
    assert r.pool_size_after == 4
    by_members = {frozenset(members(f, p)): p for p in problems(f)}
    assert set(by_members) == {frozenset(a), frozenset(nulls)}
    p = f.conn.execute("SELECT * FROM problem WHERE id = ?", (by_members[frozenset(a)],)).fetchone()
    assert p["title_source"] == "auto" and p["title"].startswith("problem ")
    assert p["statement"] is None and p["centroid_model"] == MODEL
    kinds = {r[0] for r in f.conn.execute("SELECT assigned_by FROM problem_member")}
    assert kinds == {"cluster"}


def test_loose_cluster_is_trimmed_or_rejected(f):
    group(f, 0, ["a", "b", "c", "d"], cos=0.90)   # pairwise 0.81: below cohesion
    assert 0.90 ** 2 < mapping.CLUSTER_MIN_COHESION
    r = run(f)
    assert r.new_problems == 0 and r.pool_size_after == 4
    # A tight trio keeps its members while a straggler goes back to the pool.
    vecs = np.vstack([near(1, 50, 0.98), near(1, 51, 0.98), near(1, 52, 0.98), near(1, 53, 0.80)])
    assert list(mapping._trim(vecs, np.arange(4))) == [0, 1, 2]


def test_problem_title_is_member_nearest_centroid(f):
    pains = [f.pain(near(0, 30, 0.995), author="a"),   # nearest the group's centre
             f.pain(near(0, 31, 0.975), author="b"),
             f.pain(near(0, 32, 0.975), author="c")]
    run(f)
    title = f.conn.execute("SELECT title FROM problem").fetchone()[0]
    expected = f.conn.execute("SELECT problem FROM pain WHERE id = ?", (pains[0],)).fetchone()[0]
    assert title == expected


def test_ids_stay_stable_across_runs(f):
    first = group(f, 0, ["a", "b", "c"])
    run(f)
    [pid] = problems(f)
    later = group(f, 0, ["d", "e"])
    r2 = run(f)
    assert problems(f) == [pid]
    assert r2.new_problems == 0 and r2.assigned_centroid == 2
    assert members(f, pid) == set(first) | set(later)
    snap = f.conn.execute("SELECT * FROM snapshot WHERE run_id = ?", (r2.run_id,)).fetchone()
    assert (snap["problem_id"], snap["mentions"], snap["new_mentions"]) == (pid, 5, 2)


def test_pool_carries_over_and_clusters_later(f):
    early = group(f, 0, ["a", "b"])
    r1 = run(f)
    assert r1.new_problems == 0 and r1.pool_size_after == 2
    late = group(f, 0, ["c"])
    r2 = run(f)
    assert r2.new_problems == 1
    [pid] = problems(f)
    assert members(f, pid) == set(early) | set(late)


def test_cluster_matching_existing_problem_folds_into_it(f):
    # Each pain sits below the threshold to the seeded centroid, but their mean clears it.
    pid = f.problem(axis(0))
    a, b = T - 0.01, 0.30                  # a shared lean on axis 1 keeps the trio tight
    u = np.sqrt(1 - a ** 2 - b ** 2)
    assert a ** 2 + b ** 2 >= mapping.CLUSTER_MIN_COHESION                  # cohesive
    assert a / np.sqrt(a ** 2 + b ** 2 + u ** 2 / 3) >= T                   # mean clears T
    pains = [f.pain(a * axis(0) + b * axis(1) + u * axis(next(f.spare)), author=x)
             for x in ["a", "b", "c"]]
    r = run(f)
    assert r.assigned_centroid == 0 and r.clusters_folded == 1 and r.new_problems == 0
    assert members(f, pid) == set(pains)


def test_merge_moves_members_and_alias_resolves(f):
    a = group(f, 0, ["a", "b", "c"])
    b = group(f, 1, ["d", "e", "f"])
    run(f)
    by_members = {frozenset(members(f, p)): p for p in problems(f)}
    keep, drop = by_members[frozenset(a)], by_members[frozenset(b)]
    assert mapping.merge(f.conn, keep, drop, "duplicate") == keep
    assert members(f, keep) == set(a) | set(b) and members(f, drop) == set()
    row = f.conn.execute("SELECT status, merged_into FROM problem WHERE id = ?", (drop,)).fetchone()
    assert tuple(row) == ("merged", keep)
    assert mapping.resolve(f.conn, drop) == keep and mapping.resolve(f.conn, keep) == keep
    d = f.conn.execute("SELECT * FROM decision").fetchone()
    assert (d["problem_id"], d["action"], d["reason"]) == (keep, "merge", "duplicate")
    # The kept centroid is the mean of all six members.
    vecs = np.vstack([f.embedder.vectors[t] for t in
                      [r[0] + " — " + r[1] for r in f.conn.execute("SELECT problem, who FROM pain")]])
    c = from_blob(f.conn.execute("SELECT centroid FROM problem WHERE id = ?", (keep,)).fetchone()[0])
    assert np.allclose(c, normalize(vecs.mean(axis=0)), atol=1e-5)
    with pytest.raises(ValueError):
        mapping.merge(f.conn, keep, drop, "again")
    # Chains resolve: fold the kept problem into a third, and the old id follows.
    third = f.problem(axis(9))
    mapping.merge(f.conn, third, keep, "duplicate")
    assert mapping.resolve(f.conn, drop) == third
    # Merging into a merged id lands in its survivor.
    other = group(f, 4, ["g", "h", "i"])
    run(f)
    newest = max(problems(f))
    assert members(f, newest) == set(other)
    assert mapping.merge(f.conn, drop, newest, "duplicate") == third


def test_merge_candidates_band(f):
    p1 = f.problem(axis(0))
    in_band, above = mapping.MERGE_LOW + 0.01, T + 0.02
    p2 = f.problem(near(0, 1, in_band))  # in the band with p1
    p3 = f.problem(near(0, 2, 0.70))     # too far from everyone
    p4 = f.problem(near(0, 3, above))    # above the band with p1: still a likely duplicate
    assert in_band * above < mapping.MERGE_LOW  # p2 and p4 stay apart
    with f.conn:
        f.conn.execute("INSERT INTO merge_candidate (a_id, b_id, similarity, run_id)"
                       " VALUES (?, ?, 0.95, ?)", (p2, p3, f.collect_run))  # stale
    r = run(f)
    rows = {(x["a_id"], x["b_id"]): x for x in f.conn.execute("SELECT * FROM merge_candidate")}
    assert set(rows) == {(p1, p2), (p1, p4)}
    assert rows[(p1, p2)]["similarity"] == pytest.approx(in_band, abs=1e-5)
    assert rows[(p1, p2)]["status"] == "open" and rows[(p1, p2)]["run_id"] == r.run_id
    assert r.merge_candidates_open == 2
    # A decided pair is never reopened.
    with f.conn:
        f.conn.execute("UPDATE merge_candidate SET status = 'rejected' WHERE a_id = ? AND b_id = ?", (p1, p2))
    r2 = run(f)
    assert f.conn.execute("SELECT status, run_id FROM merge_candidate WHERE a_id = ? AND b_id = ?",
                          (p1, p2)).fetchone()[0] == "rejected"
    assert r2.merge_candidates_open == 1
    # Merging closes the pair.
    mapping.merge(f.conn, p1, p4, "duplicate")
    assert f.conn.execute("SELECT status FROM merge_candidate WHERE a_id = ? AND b_id = ?",
                          (p1, p4)).fetchone()[0] == "merged"


def test_snapshot_numbers(f):
    group(f, 0, ["a", "a"], source="hn", country="GB")
    group(f, 0, ["b"], source="hn", country=None)
    group(f, 0, [None, None], source="govuk", country="US")
    f.pain(axis(5), author="x")  # unassigned
    r = run(f)
    [pid] = problems(f)
    s = f.conn.execute("SELECT * FROM snapshot WHERE run_id = ?", (r.run_id,)).fetchone()
    assert (s["problem_id"], s["mentions"], s["distinct_authors"], s["sources"],
            s["countries"], s["new_mentions"]) == (pid, 5, 4, 2, 2, 5)


def test_rerun_is_idempotent(f):
    group(f, 0, ["a", "b", "c"])
    group(f, 1, ["d", "d"])
    r1 = run(f)
    before = f.conn.execute("SELECT pain_id, problem_id, assigned_run_id FROM problem_member"
                            " ORDER BY pain_id").fetchall()
    r2 = run(f)
    after = f.conn.execute("SELECT pain_id, problem_id, assigned_run_id FROM problem_member"
                           " ORDER BY pain_id").fetchall()
    assert [tuple(x) for x in before] == [tuple(x) for x in after]
    assert r2.new_problems == r2.assigned_centroid == r2.assigned_cluster == 0
    assert r2.embedded == 0 and r2.pool_size_after == r1.pool_size_after == 2
    for rid in (r1.run_id, r2.run_id):
        assert f.conn.execute("SELECT COUNT(*) FROM snapshot WHERE run_id = ?", (rid,)).fetchone()[0] == 1
    assert f.conn.execute("SELECT new_mentions FROM snapshot WHERE run_id = ?",
                          (r2.run_id,)).fetchone()[0] == 0
    # Snapshotting the same run twice replaces rather than duplicates.
    with f.conn:
        mapping._snapshot(f.conn, r2.run_id)
    assert f.conn.execute("SELECT COUNT(*) FROM snapshot WHERE run_id = ?", (r2.run_id,)).fetchone()[0] == 1


def test_superseded_pains_are_not_mapped(f):
    item = f.item("a")
    old = f.pain(near(0, 40, 0.97), extraction_id=f.extraction(item))
    new_x = f.extraction(item, f.new_prompt("v2"))
    new = f.pain(near(0, 41, 0.97), extraction_id=new_x)
    group(f, 0, ["b", "c"])
    run(f)
    [pid] = problems(f)
    assert new in members(f, pid) and old not in members(f, pid)
    assert f.conn.execute("SELECT 1 FROM embedding WHERE pain_id = ?", (old,)).fetchone() is None


def test_metrics_logged(f):
    group(f, 0, ["a", "b", "c"], source="hn", country="GB")
    r = run(f)
    m = {(x["layer"], x["name"], x["subject"]): x["value"] for x in
         f.conn.execute("SELECT * FROM metric WHERE run_id = ?", (r.run_id,))}
    assert m[("mapping", "pains_assigned_cluster", "")] == 3
    assert m[("mapping", "new_problems", "")] == 1
    assert m[("mapping", "problems_total", "")] == 1
    assert m[("mapping", "pool_size_after", "")] == 0
    assert m[("mapping", "merge_candidates_open", "")] == 0
    assert m[("mapping", "pains_assigned_centroid", "")] == 0
    assert m[("coverage", "problems_with_source", "hn")] == 1
    assert m[("coverage", "problems_with_country", "GB")] == 1
    status = f.conn.execute("SELECT kind, status FROM run WHERE id = ?", (r.run_id,)).fetchone()
    assert tuple(status) == ("map", "ok")
