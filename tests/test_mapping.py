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


# --- Re-extraction keeps identity ---------------------------------------------------

def reextract(f, pain_id, vec, prompt_id, idx=None):
    """A new extraction of pain_id's item under prompt_id, with one pain embedded as vec."""
    row = f.conn.execute("SELECT x.raw_item_id, p.idx FROM pain p JOIN extraction x"
                         " ON x.id = p.extraction_id WHERE p.id = ?", (pain_id,)).fetchone()
    x = f.conn.execute("SELECT id FROM extraction WHERE raw_item_id = ? AND prompt_id = ?",
                       (row[0], prompt_id)).fetchone()
    x = x[0] if x else f.extraction(row[0], prompt_id)
    return f.pain(vec, extraction_id=x, idx=row[1] if idx is None else idx)


def member_row(f, pain_id):
    return f.conn.execute("SELECT * FROM problem_member WHERE pain_id = ?", (pain_id,)).fetchone()


def test_reextraction_carries_members_without_new_mentions(f):
    old = group(f, 0, ["a", "b", "c"])
    r1 = run(f)
    [pid] = problems(f)
    v2 = f.new_prompt("v2")
    # The new prompt words every pain differently: alone, these would found a new problem.
    new = [reextract(f, p, near(1, next(f.spare), 0.985), v2) for p in old]
    r2 = run(f)
    assert problems(f) == [pid]                          # no duplicate problem
    assert r2.carried == 3 and r2.new_problems == r2.assigned_cluster == 0
    for p in new:
        row = member_row(f, p)
        assert (row["problem_id"], row["assigned_by"], row["assigned_run_id"]) == (pid, "carried", r1.run_id)
    assert members(f, pid) == set(old) | set(new)         # history stays
    snap = f.conn.execute("SELECT * FROM snapshot WHERE run_id = ?", (r2.run_id,)).fetchone()
    assert (snap["mentions"], snap["distinct_authors"], snap["new_mentions"]) == (3, 3, 0)
    # The problem lost its old members and gained the new: its centroid follows.
    c = from_blob(f.conn.execute("SELECT centroid FROM problem WHERE id = ?", (pid,)).fetchone()[0])
    texts = [f"{x[0]} — {x[1]}" for x in f.conn.execute(
        f"SELECT problem, who FROM pain WHERE id IN ({','.join('?' * len(new))})", new)]
    expected = normalize(np.vstack([f.embedder.vectors[t] for t in texts]).mean(axis=0))
    assert np.allclose(c, expected, atol=1e-5)
    m = {x["name"]: x["value"] for x in f.conn.execute(
        "SELECT name, value FROM metric WHERE run_id = ? AND layer = 'mapping'", (r2.run_id,))}
    assert m["pains_carried"] == 3
    # A third run changes nothing.
    r3 = run(f)
    assert r3.carried == 0 and problems(f) == [pid]


def test_partial_reextraction_keeps_counts(f):
    old = group(f, 0, ["a", "b", "c"])
    run(f)
    [pid] = problems(f)
    reextract(f, old[0], near(0, next(f.spare), 0.985), f.new_prompt("v2"))
    r2 = run(f)
    snap = f.conn.execute("SELECT * FROM snapshot WHERE run_id = ?", (r2.run_id,)).fetchone()
    assert (snap["problem_id"], snap["mentions"], snap["new_mentions"]) == (pid, 3, 0)


def test_carry_matches_by_idx_then_similarity(f):
    # Item X holds two problems: idx 0 joins the axis-0 group, idx 1 the axis-1 group.
    x = f.extraction(f.item("x"))
    x0 = f.pain(near(0, next(f.spare), 0.985), extraction_id=x, idx=0)
    x1 = f.pain(near(1, next(f.spare), 0.985), extraction_id=x, idx=1)
    group(f, 0, ["a", "b"])
    group(f, 1, ["c", "d"])
    run(f)
    p0, p1 = member_row(f, x0)["problem_id"], member_row(f, x1)["problem_id"]
    assert p0 != p1
    # v2 keeps both problems in the same order, worded far from either group.
    v2 = f.new_prompt("v2")
    n0 = reextract(f, x0, axis(20), v2)
    n1 = reextract(f, x1, axis(21), v2)
    run(f)
    assert member_row(f, n0)["problem_id"] == p0 and member_row(f, n1)["problem_id"] == p1
    # v3 finds a single problem and puts it at idx 2: no idx matches, so similarity to
    # v2's pains (axes 20 and 21) decides.
    v3 = f.new_prompt("v3")
    n = reextract(f, x1, near(21, 20, 0.9), v3, idx=2)
    r = run(f)
    assert r.carried == 1 and member_row(f, n)["problem_id"] == p1


def test_prompt_revert_uses_current_prompt_pains(f, monkeypatch):
    from pipeline import embed
    monkeypatch.setattr(embed, "current_extract_version", lambda: "v1")
    old = group(f, 0, ["a", "b", "c"])
    run(f)
    [pid] = problems(f)
    v2 = f.new_prompt("v2")
    new = [reextract(f, p, near(1, next(f.spare), 0.985), v2) for p in old]
    # v1 is still the current prompt: its pains stay active, v2's wait.
    r = run(f)
    assert r.embedded == 0 and r.carried == 0 and r.pool_size_after == 0
    assert all(member_row(f, p) is None for p in new)
    # Switch to v2: its pains become active and carry.
    monkeypatch.setattr(embed, "current_extract_version", lambda: "v2")
    r = run(f)
    assert r.embedded == 3 and r.carried == 3 and problems(f) == [pid]
    # Revert to v1 although v2's extractions are newer: v1's pains count again.
    monkeypatch.setattr(embed, "current_extract_version", lambda: "v1")
    active = {x[0] for x in f.conn.execute(f"SELECT id FROM ({embed.ACTIVE_PAIN_SQL})")}
    assert active == set(old)
    r = run(f)
    assert r.carried == r.assigned_centroid == r.assigned_cluster == 0 and problems(f) == [pid]
    snap = f.conn.execute("SELECT * FROM snapshot WHERE run_id = ?", (r.run_id,)).fetchone()
    assert (snap["mentions"], snap["new_mentions"]) == (3, 0)
    c = from_blob(f.conn.execute("SELECT centroid FROM problem WHERE id = ?", (pid,)).fetchone()[0])
    assert c @ axis(0) > 0.95                             # back on the v1 pains


def test_clustering_runs_outside_the_write_transaction(f, monkeypatch, tmp_path):
    from pipeline import db
    group(f, 0, ["a", "b", "c"])
    other = db.connect(tmp_path / "t.db")
    other.execute("PRAGMA busy_timeout = 0")
    seen = []
    real = mapping._candidate_groups

    def spy(vectors):
        seen.append(f.conn.in_transaction)
        with other:  # another process can write while HDBSCAN runs
            other.execute("INSERT INTO run (kind) VALUES ('smoke')")
        return real(vectors)

    monkeypatch.setattr(mapping, "_candidate_groups", spy)
    r = run(f)
    assert seen == [False] and r.new_problems == 1


# --- Active prompt state, merge steering (Phase 3 review) -----------------------------

def test_map_publishes_the_active_extract_prompt(f, monkeypatch):
    from pipeline import db, embed
    group(f, 0, ["a", "b", "c"])
    run(f)
    # The factory's prompt is not today's file: map registers today's and publishes it.
    pid = f.conn.execute("SELECT id FROM prompt WHERE name = 'extract' AND version = ?",
                         (embed.current_extract_version(),)).fetchone()[0]
    assert pid != f.prompt
    assert db.get_state(f.conn, db.ACTIVE_EXTRACT_PROMPT_ID) == str(pid)
    monkeypatch.setattr(embed, "current_extract_version", lambda: "v1")
    run(f)
    assert db.get_state(f.conn, db.ACTIVE_EXTRACT_PROMPT_ID) == str(f.prompt)


def two_problems(f):
    group(f, 0, ["a", "b", "c"])
    group(f, 1, ["d", "e", "f"])
    run(f)
    return problems(f)


def set_status(f, pid, status):
    with f.conn:
        f.conn.execute("UPDATE problem SET status = ? WHERE id = ?", (status, pid))


def status(f, pid):
    return f.conn.execute("SELECT status FROM problem WHERE id = ?", (pid,)).fetchone()[0]


@pytest.mark.parametrize("keep_status, drop_status, expected, carried", [
    ("new", "promoted", "promoted", True),
    ("watching", "new", "watching", False),
    ("archived", "watching", "watching", True),
    ("promoted", "watching", "promoted", False),
    ("new", "archived", "new", False),
])
def test_merge_keeps_the_higher_status(f, keep_status, drop_status, expected, carried):
    keep, drop = two_problems(f)
    set_status(f, keep, keep_status)
    set_status(f, drop, drop_status)
    mapping.merge(f.conn, keep, drop, "duplicate")
    assert status(f, keep) == expected and status(f, drop) == "merged"
    note = f.conn.execute("SELECT note FROM decision").fetchone()[0]
    assert (f"status carried from #{drop}: {drop_status}" in note) == carried


def test_merge_stores_reason_code_and_note(f):
    keep, drop = two_problems(f)
    mapping.merge(f.conn, keep, drop, "same_problem", note="  both about invoices ")
    d = f.conn.execute("SELECT reason, note FROM decision").fetchone()
    assert d["reason"] == "same_problem"
    assert d["note"] == f"both about invoices; merged problem {drop} into {keep}"
    assert f.conn.execute("SELECT reason FROM problem_alias WHERE old_id = ?",
                          (drop,)).fetchone()[0] == "same_problem"


@pytest.mark.parametrize("closed", ["rejected", "merged"])
def test_merge_refuses_a_closed_candidate_unless_forced(f, closed):
    keep, drop = two_problems(f)
    with f.conn:
        f.conn.execute("DELETE FROM merge_candidate")
        f.conn.execute("INSERT INTO merge_candidate (a_id, b_id, similarity, run_id, status)"
                       " VALUES (?, ?, 0.92, ?, ?)", (min(keep, drop), max(keep, drop),
                                                      f.collect_run, closed))
    for k, d in ((keep, drop), (drop, keep)):  # either argument order
        with pytest.raises(ValueError, match=closed):
            mapping.merge(f.conn, k, d, "duplicate")
    assert status(f, drop) != "merged" and f.conn.execute(
        "SELECT COUNT(*) FROM decision").fetchone()[0] == 0
    assert mapping.merge(f.conn, keep, drop, "duplicate", force=True) == keep
    assert status(f, drop) == "merged"
    assert f.conn.execute("SELECT status FROM merge_candidate").fetchone()[0] == "merged"


def test_merge_with_an_open_candidate_closes_it(f):
    keep, drop = two_problems(f)
    with f.conn:
        f.conn.execute("DELETE FROM merge_candidate")
        f.conn.execute("INSERT INTO merge_candidate (a_id, b_id, similarity, run_id)"
                       " VALUES (?, ?, 0.92, ?)", (min(keep, drop), max(keep, drop), f.collect_run))
    mapping.merge(f.conn, keep, drop, "duplicate")
    assert f.conn.execute("SELECT status FROM merge_candidate").fetchone()[0] == "merged"


def test_merge_cli(f, tmp_path, monkeypatch, capsys):
    from pipeline.__main__ import main
    keep, drop = two_problems(f)
    third = f.problem(axis(9))
    with f.conn:
        f.conn.execute("DELETE FROM merge_candidate")
        f.conn.execute("INSERT INTO merge_candidate (a_id, b_id, similarity, run_id, status)"
                       " VALUES (?, ?, 0.92, ?, 'rejected')", (keep, third, f.collect_run))
    monkeypatch.setenv("SIG_DB", str(tmp_path / "t.db"))
    assert main(["merge", str(keep), str(drop), "--reason", "duplicate", "--note", "same"]) == 0
    d = f.conn.execute("SELECT reason, note FROM decision").fetchone()
    assert d["reason"] == "duplicate" and d["note"].startswith("same; ")
    assert main(["merge", str(keep), str(third), "--reason", "duplicate"]) == 1
    assert "--force" in capsys.readouterr().err
    assert main(["merge", str(keep), str(third), "--reason", "duplicate", "--force"]) == 0
    assert status(f, third) == "merged"
