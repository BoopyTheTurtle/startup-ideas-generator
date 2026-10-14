import json
import sqlite3

import pytest

from pipeline import themes
from pipeline.llm import LLMError, LLMResult
from pipeline.themes import list_themes, prompt_version, themes_run
from pipeline.embed import normalize
from tests.pain_factory import Factory, axis


@pytest.fixture
def f(tmp_path):
    return Factory(tmp_path)


def group(f, topic, n=6, authors=None):
    """n pains on one topic; authors[i % len] each (None = an item without author).

    Topics pair up under broad subjects (0 and 1 under axis 40, 2 and 3 under axis 41, ...),
    as real topics do. Mean-centring needs that structure: with mutually orthogonal topics
    it makes them antipodal, and an unrelated pain sits closer to every topic than the
    topics sit to each other, so HDBSCAN pulls it into a cluster.
    """
    authors = authors if authors is not None else [f"a{topic}-{i}" for i in range(n)]
    return [f.pain(normalize(axis(40 + topic // 2) + 0.7 * axis(topic) + 0.35 * axis(next(f.spare))),
                   author=authors[i % len(authors)]) for i in range(n)]


def noise(f, n=4):
    """Pains unrelated to anything (at most 4 here, below HDBSCAN's min_cluster_size)."""
    return [f.pain(axis(next(f.spare)), author=f"noise{i}") for i in range(n)]


class Fake:
    name = "fake"

    def __init__(self, fail=False):
        self.fail, self.payloads = fail, []

    def run(self, system, user, schema, model):
        payload = json.loads(user)
        self.payloads.append(payload)
        if self.fail:
            raise LLMError("boom")
        return LLMResult({"themes": [{"id": t["id"], "title": f"Named {t['id']}", "statement": "S."}
                                     for t in payload]}, model, 0.01)


def theme_rows(f, run_id):
    rows = f.conn.execute("SELECT * FROM theme WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
    return [dict(r) | {"members": {m[0] for m in f.conn.execute(
        "SELECT pain_id FROM theme_member WHERE theme_id = ?", (r["id"],))}} for r in rows]


def metrics(f, run_id):
    return {r["name"]: r["value"] for r in f.conn.execute(
        "SELECT name, value FROM metric WHERE run_id = ?", (run_id,))}


def test_themes_need_three_authors_and_noise_belongs_to_none(f):
    a = group(f, 0)
    no_author = group(f, 1, authors=[None])          # each item counts as its own author
    c = group(f, 2)
    two_authors = group(f, 3, authors=["x", "y"])
    lone = noise(f)
    res = themes_run(f.conn, embedder=f.embedder, name=False)
    assert res.embedded == len(a + no_author + c + two_authors + lone)
    rows = theme_rows(f, res.run_id)
    assert sorted(map(sorted, (r["members"] for r in rows))) == sorted([a, no_author, c])
    for r in rows:
        assert r["size"] == 6 and r["distinct_authors"] == 6
        assert r["sources"] == 1 and r["countries"] == 1
        assert 0 < r["cohesion"] <= 1
        assert r["title_source"] == "auto" and r["carried_from"] is None and r["statement"] is None
        assert r["title"].startswith("problem ")
    m = metrics(f, res.run_id)
    assert m["themes_total"] == 3 and m["pains_in_themes"] == 18
    assert m["pains_noise"] == len(two_authors + lone)
    assert "theme_llm_cost_usd" not in m  # no naming, no LLM metric
    status = f.conn.execute("SELECT status FROM run WHERE id = ?", (res.run_id,)).fetchone()[0]
    assert status == "ok"


def test_naming_titles_auto_themes_and_registers_prompt(f):
    group(f, 0)
    group(f, 1)
    fake = Fake()
    res = themes_run(f.conn, embedder=f.embedder, runtime=fake)
    assert len(fake.payloads) == 1 and len(fake.payloads[0]) == 2
    assert all(len(t["reports"]) == 6 and {"job", "problem", "who"} == set(t["reports"][0])
               for t in fake.payloads[0])
    rows = theme_rows(f, res.run_id)
    assert {r["title_source"] for r in rows} == {"curator"}
    assert {r["title"] for r in rows} == {"Named 1", "Named 2"} and rows[0]["statement"] == "S."
    version = prompt_version()
    assert f.conn.execute("SELECT COUNT(*) FROM prompt WHERE name = 'themes' AND version = ?",
                          (version,)).fetchone()[0] == 1
    assert version in f.conn.execute("SELECT note FROM run WHERE id = ?", (res.run_id,)).fetchone()[0]
    m = metrics(f, res.run_id)
    assert m["themes_named"] == 2 and m["theme_llm_cost_usd"] == pytest.approx(0.01)


def test_carry_keeps_names_and_only_new_themes_are_named(f):
    a = group(f, 0)
    b = group(f, 1)
    first = themes_run(f.conn, embedder=f.embedder, runtime=Fake())
    old = {frozenset(r["members"]): r for r in theme_rows(f, first.run_id)}
    a += group(f, 0, n=7)       # A's items: 6 old of 13 -> Jaccard 0.46, below CARRY_JACCARD
    b += group(f, 1, n=2)       # B: 6 of 8 -> 0.75, carried
    c = group(f, 2)             # new topic
    fake = Fake()
    second = themes_run(f.conn, embedder=f.embedder, runtime=fake)
    rows = {frozenset(r["members"]): r for r in theme_rows(f, second.run_id)}
    assert set(rows) == {frozenset(a), frozenset(b), frozenset(c)}
    prev_b = old[frozenset(b[:6])]
    assert rows[frozenset(b)]["title_source"] == "carried"
    assert rows[frozenset(b)]["carried_from"] == prev_b["id"]
    assert (rows[frozenset(b)]["title"], rows[frozenset(b)]["statement"]) == (prev_b["title"], "S.")
    for members in (a, c):
        assert rows[frozenset(members)]["title_source"] == "curator"
        assert rows[frozenset(members)]["carried_from"] is None
    sent = {r["problem"] for t in fake.payloads[0] for r in t["reports"]}
    texts = dict(f.conn.execute("SELECT id, problem FROM pain").fetchall())
    assert len(fake.payloads[0]) == 2 and not sent & {texts[p] for p in b}
    assert metrics(f, second.run_id)["themes_carried"] == 1


def theme_of(f, run_id, members):
    return next(r for r in theme_rows(f, run_id) if r["members"] == set(members))


def test_carried_names_chain_and_unnamed_themes_are_not_carried(f):
    a = group(f, 0)
    group(f, 1)
    themes_run(f.conn, embedder=f.embedder, name=False)
    r2 = themes_run(f.conn, embedder=f.embedder, name=False)
    assert theme_of(f, r2.run_id, a)["title_source"] == "auto"  # placeholder titles don't carry
    r3, r4, r5 = (themes_run(f.conn, embedder=f.embedder, runtime=Fake()) for _ in range(3))
    t3, t4, t5 = (theme_of(f, r.run_id, a) for r in (r3, r4, r5))
    assert t3["title_source"] == "curator"
    assert (t4["title_source"], t4["carried_from"], t4["title"]) == ("carried", t3["id"], t3["title"])
    assert (t5["title_source"], t5["carried_from"], t5["title"]) == ("carried", t4["id"], t3["title"])


def test_carry_skips_failed_runs(f):
    a = group(f, 0)
    group(f, 1)
    r1 = themes_run(f.conn, embedder=f.embedder, runtime=Fake())
    with f.conn:  # a later run that failed after writing must not be the carry source
        bad = f.conn.execute("INSERT INTO run (kind, status) VALUES ('themes', 'failed')").lastrowid
        f.conn.execute("INSERT INTO theme (run_id, title, title_source, size, distinct_authors,"
                       " sources, countries) VALUES (?, 'stale', 'curator', 1, 1, 1, 1)", (bad,))
    r2 = themes_run(f.conn, embedder=f.embedder, runtime=Fake())
    assert theme_of(f, r2.run_id, a)["carried_from"] == theme_of(f, r1.run_id, a)["id"]


def test_a_run_never_modifies_earlier_runs(f):
    group(f, 0)
    group(f, 1)
    first = themes_run(f.conn, embedder=f.embedder, runtime=Fake())
    before = theme_rows(f, first.run_id)
    group(f, 0, n=7)
    group(f, 2)
    themes_run(f.conn, embedder=f.embedder, runtime=Fake())
    themes_run(f.conn, embedder=f.embedder, name=False)
    assert theme_rows(f, first.run_id) == before


def test_all_rows_are_written_in_one_transaction(f):
    group(f, 0)
    group(f, 1)
    group(f, 2)
    statements = []
    f.conn.set_trace_callback(statements.append)
    themes_run(f.conn, embedder=f.embedder, runtime=Fake())
    f.conn.set_trace_callback(None)
    inserts = [i for i, s in enumerate(statements) if s.lstrip().startswith("INSERT INTO theme")]
    assert sum(statements[i].startswith("INSERT INTO theme ") for i in inserts) == 3
    begin = max(i for i, s in enumerate(statements[:inserts[0]]) if s.startswith("BEGIN"))
    assert statements[begin] == "BEGIN IMMEDIATE"
    end = next(i for i, s in enumerate(statements) if i > begin and s in ("COMMIT", "ROLLBACK"))
    assert statements[end] == "COMMIT" and inserts[-1] < end


def test_failed_write_leaves_no_rows_and_fails_the_run(f, monkeypatch):
    group(f, 0)
    group(f, 1)
    plan = themes._plan

    def broken(inp):
        out = plan(inp)
        out[-1].title = None  # NOT NULL: the second insert fails after the first succeeded
        return out

    monkeypatch.setattr(themes, "_plan", broken)
    with pytest.raises(sqlite3.IntegrityError):
        themes_run(f.conn, embedder=f.embedder, name=False)
    assert f.conn.execute("SELECT COUNT(*) FROM theme").fetchone()[0] == 0
    assert f.conn.execute("SELECT COUNT(*) FROM theme_member").fetchone()[0] == 0
    assert f.conn.execute("SELECT status FROM run WHERE kind = 'themes'").fetchone()[0] == "failed"


def test_naming_failure_keeps_auto_titles(f):
    group(f, 0)
    group(f, 1)
    res = themes_run(f.conn, embedder=f.embedder, runtime=Fake(fail=True))
    assert {r["title_source"] for r in theme_rows(f, res.run_id)} == {"auto"}
    m = metrics(f, res.run_id)
    assert m["theme_llm_failures"] == 1 and m["themes_named"] == 0


def test_naming_respects_the_limit(f):
    for base in range(3):
        group(f, base)
    fake = Fake()
    res = themes_run(f.conn, embedder=f.embedder, runtime=fake, name_limit=2)
    assert len(fake.payloads[0]) == 2
    assert sorted(r["title_source"] for r in theme_rows(f, res.run_id)) == ["auto", "curator", "curator"]


def test_too_few_pains_gives_an_empty_ok_run(f):
    noise(f, 3)
    res = themes_run(f.conn, embedder=f.embedder, runtime=Fake())
    assert res.themes_total == 0 and res.pains_noise == 3
    assert list_themes(f.conn) == []


def test_list_themes_shows_latest_run_with_top_problem(f):
    a = group(f, 0)
    group(f, 1)
    themes_run(f.conn, embedder=f.embedder, name=False)
    latest = themes_run(f.conn, embedder=f.embedder, runtime=Fake())
    pid = f.problem(axis(0), title="Seeded problem")
    with f.conn:
        f.conn.executemany(
            "INSERT INTO problem_member (pain_id, problem_id, similarity, assigned_run_id, assigned_by)"
            " VALUES (?, ?, 0.95, ?, 'centroid')", [(p, pid, f.extract_run) for p in a[:3]])
    rows = list_themes(f.conn)
    assert {r["run_id"] for r in rows} == {latest.run_id} and len(rows) == 2
    by_problem = {r["top_problem"]["title"] if r["top_problem"] else None: r for r in rows}
    assert by_problem["Seeded problem"]["top_problem"]["n"] == 3
    assert all(r["sample"].startswith("problem ") for r in rows)
