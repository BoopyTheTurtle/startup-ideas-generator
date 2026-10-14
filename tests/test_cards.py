import json
import sqlite3
import subprocess
from datetime import datetime, timezone

import pytest

from pipeline import cards, db, runs
from pipeline.cards import CardError, classify_paths


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.migrate(c)
    with runs.run(c, "extract") as run_id:
        runs.log_metric(c, run_id, "extraction", "quote_miss_rate", 0.2)
    return c


def card(**over):
    d = {"kind": "extraction", "touches": "system", "title": "Cut quote misses",
         "observation": "quote_miss_rate is 0.2", "evidence": [
             {"metric": "extraction.quote_miss_rate", "subject": "", "value": 0.2, "run_id": 1}],
         "hypothesis": "offsets drift", "change": "match on normalized text",
         "expected_effect": "miss rate halves", "expected_metric": "extraction.quote_miss_rate",
         "expected_direction": "down", "risk": "low", "size": "S", "value": 4}
    d.update(over)
    return d


def decide(conn, card_id, status="approved"):
    """Edgar's approval: the app writes this; tests do the same SQL."""
    with conn:
        conn.execute("UPDATE improvement_card SET status = ?, decided_at = '2026-10-14T00:00:00Z'"
                     " WHERE id = ?", (status, card_id))


# --- proposing ---------------------------------------------------------------------------

def test_add_card_stores_rank_and_event(conn):
    cid = cards.add_card(conn, card(size="M", value=4))
    row = cards.get_card(conn, cid)
    assert row["status"] == "proposed" and row["rank_score"] == 2.0
    assert conn.execute("SELECT event FROM card_event WHERE card_id = ?", (cid,)).fetchone()[0] == "proposed"


@pytest.mark.parametrize("over,msg", [
    ({"touches": "both"}, "never both"),
    ({"kind": "nope"}, "kind"),
    ({"size": "XL"}, "size"),
    ({"value": 9}, "value"),
    ({"expected_metric": "extraction.nope"}, "not a logged"),
    ({"expected_direction": None}, "go together"),
    ({"evidence": []}, "evidence"),
    ({"risk": "  "}, "risk"),
])
def test_add_card_rejects_bad_input(conn, over, msg):
    with pytest.raises(CardError, match=msg):
        cards.add_card(conn, card(**over))


def test_one_open_card_per_key(conn):
    cards.add_card(conn, card())
    with pytest.raises(CardError, match="open card"):
        cards.add_card(conn, card(title="Same thing again"))


def test_rejected_key_cools_down(conn):
    cid = cards.add_card(conn, card())
    decide(conn, cid, "rejected")
    with pytest.raises(CardError, match="rejected"):
        cards.add_card(conn, card())
    later = datetime(2099, 1, 1, tzinfo=timezone.utc)
    assert cards.add_card(conn, card(), now=later)


def test_weekly_proposal_cap(conn):
    for i in range(cards.MAX_PROPOSALS_PER_WEEK):
        cards.add_card(conn, card(dedupe_key=f"k{i}"))
    with pytest.raises(CardError, match="proposed this week"):
        cards.add_card(conn, card(dedupe_key="k-extra"))
    # system-made cards (revert, broken instrument) are not capped
    assert cards.add_card(conn, card(dedupe_key="k-sys"), proposed_by="system")


# --- the status trigger -------------------------------------------------------------------

def test_trigger_blocks_illegal_moves(conn):
    cid = cards.add_card(conn, card())
    for bad in ("building", "built", "ready", "merged", "reverted"):
        with pytest.raises(sqlite3.IntegrityError, match="illegal"):
            with conn:
                conn.execute("UPDATE improvement_card SET status = ? WHERE id = ?", (bad, cid))


def test_trigger_requires_approval_decision(conn):
    cid = cards.add_card(conn, card())
    with conn:
        conn.execute("UPDATE improvement_card SET status = 'approved' WHERE id = ?", (cid,))
    with pytest.raises(sqlite3.IntegrityError, match="never approved"):
        with conn:
            conn.execute("UPDATE improvement_card SET status = 'building' WHERE id = ?", (cid,))


def test_trigger_merge_needs_approval_and_heldout(conn):
    cid = cards.add_card(conn, card())
    decide(conn, cid)
    with conn:
        conn.execute("UPDATE improvement_card SET status = 'building' WHERE id = ?", (cid,))
        conn.execute("UPDATE improvement_card SET status = 'built' WHERE id = ?", (cid,))
    with pytest.raises(sqlite3.IntegrityError, match="verdict"):
        with conn:
            conn.execute("UPDATE improvement_card SET status = 'ready' WHERE id = ?", (cid,))
    assert cards.review(conn, cid, "approve", "looks right") == "ready"
    for sql in ("", "merge_approved_at = '2026-10-15T00:00:00Z'"):
        with pytest.raises(sqlite3.IntegrityError, match="merge needs"):
            with conn:
                if sql:
                    conn.execute(f"UPDATE improvement_card SET {sql} WHERE id = ?", (cid,))
                conn.execute("UPDATE improvement_card SET status = 'merged' WHERE id = ?", (cid,))
    with conn:  # approval given, held-out check still pending
        conn.execute("UPDATE improvement_card SET merge_approved_at = 'x', heldout_check = 'pending'"
                     " WHERE id = ?", (cid,))
    with pytest.raises(sqlite3.IntegrityError, match="merge needs"):
        with conn:
            conn.execute("UPDATE improvement_card SET status = 'merged' WHERE id = ?", (cid,))
    with conn:
        conn.execute("UPDATE improvement_card SET heldout_check = 'pass' WHERE id = ?", (cid,))
        conn.execute("UPDATE improvement_card SET status = 'merged' WHERE id = ?", (cid,))


def test_review_changes_sends_card_back(conn):
    cid = cards.add_card(conn, card())
    decide(conn, cid)
    with conn:
        conn.execute("UPDATE improvement_card SET status = 'building' WHERE id = ?", (cid,))
        conn.execute("UPDATE improvement_card SET status = 'built' WHERE id = ?", (cid,))
    assert cards.review(conn, cid, "changes", "missing test") == "building"
    with pytest.raises(CardError, match="built card"):
        cards.review(conn, cid, "approve", "x")


# --- path classes -------------------------------------------------------------------------

def test_classify_paths():
    c = classify_paths(["pipeline/mapping.py", "pipeline/evals.py", "pipeline/cards.py",
                        "evals/heldout/labels.jsonl", "pipeline/prompts/extract.md", "web/src/app/label/page.tsx"])
    assert c["system"] == ["pipeline/mapping.py", "pipeline/prompts/extract.md"]
    assert c["eval"] == ["pipeline/evals.py", "evals/heldout/labels.jsonl", "web/src/app/label/page.tsx"]
    assert c["protected"] == ["pipeline/cards.py"] and c["heldout"] == ["evals/heldout/labels.jsonl"]
    assert c["extraction"] == ["pipeline/prompts/extract.md"]


# --- a real build in a scratch repo ---------------------------------------------------------

def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, conn, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "dev")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    (root / "pipeline").mkdir()
    (root / "pipeline" / "mapping.py").write_text("X = 1\n")
    (root / "pipeline" / "evals.py").write_text("Y = 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-m", "init")
    monkeypatch.setattr(db, "ROOT", root)
    monkeypatch.setattr("pipeline.embed.current_extract_version", lambda: "v0")
    return root


def building_card(conn, repo, now=None, **over):
    cid = cards.add_card(conn, card(**over))
    decide(conn, cid)
    path = cards.start_build(conn, cid, now=now)
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "t")
    return cid, path


def commit_file(path, rel, text):
    (path / rel).write_text(text)
    git(path, "add", "-A")
    git(path, "commit", "-m", f"edit {rel}")


def test_start_requires_approval(conn, repo):
    cid = cards.add_card(conn, card())
    with pytest.raises(CardError, match="only an approved"):
        cards.start_build(conn, cid)


def test_two_builds_per_week(conn, repo):
    now = datetime(2026, 10, 14, tzinfo=timezone.utc)
    for i in range(2):
        cid = cards.add_card(conn, card(dedupe_key=f"k{i}"))
        decide(conn, cid)
        cards.start_build(conn, cid, now=now)
    cid = cards.add_card(conn, card(dedupe_key="k3"))
    decide(conn, cid)
    with pytest.raises(CardError, match="builds already started"):
        cards.start_build(conn, cid, now=now)
    nxt = datetime(2026, 10, 21, tzinfo=timezone.utc)
    cards.start_build(conn, cid, now=nxt)
    # a revert card is never blocked by the cap
    rid = cards.add_card(conn, card(kind="revert", dedupe_key="revert:1"), proposed_by="system")
    decide(conn, rid)
    cards.start_build(conn, rid, now=now)


def test_verify_passes_a_system_change(conn, repo):
    cid, path = building_card(conn, repo)
    commit_file(path, "pipeline/mapping.py", "X = 2\n")
    res = cards.verify(conn, cid, run_tests=False)
    assert res["ok"], res["problems"]
    row = cards.get_card(conn, cid)
    assert row["status"] == "built" and row["needs_heldout"] == 0 and row["heldout_check"] == "not_needed"
    assert row["head_sha"] == git(path, "rev-parse", "HEAD")


def test_verify_rejects_mixed_protected_and_dirty(conn, repo):
    cid, path = building_card(conn, repo)
    (path / "pipeline" / "mapping.py").write_text("X = 3\n")
    with pytest.raises(CardError, match="uncommitted"):
        cards.verify(conn, cid, run_tests=False)
    git(path, "add", "-A")
    git(path, "commit", "-m", "m")
    commit_file(path, "pipeline/evals.py", "Y = 2\n")
    res = cards.verify(conn, cid, run_tests=False)
    assert not res["ok"] and any("both the system and its evaluation" in p for p in res["problems"])
    assert cards.get_card(conn, cid)["status"] == "building"
    commit_file(path, "pipeline/cards.py", "# tamper\n")
    res = cards.verify(conn, cid, run_tests=False)
    assert any("protected" in p for p in res["problems"])


def test_verify_wrong_touches_class(conn, repo):
    cid, path = building_card(conn, repo, touches="eval", kind="labeling", expected_metric=None,
                              expected_direction=None)
    commit_file(path, "pipeline/mapping.py", "X = 2\n")
    res = cards.verify(conn, cid, run_tests=False)
    assert any("says it touches the evaluation" in p for p in res["problems"])


def test_extraction_change_needs_eval_diff(conn, repo, monkeypatch):
    cid, path = building_card(conn, repo)
    (path / "pipeline" / "prompts").mkdir()
    commit_file(path, "pipeline/prompts/extract.md", "new prompt\n")
    monkeypatch.setattr(cards, "_worktree_prompt_version", lambda p: "v1")

    def f1(version, value):
        with conn:
            conn.execute("INSERT INTO metric (run_id, layer, name, subject, value)"
                         " VALUES (1, 'extraction', 'eval_f1', ?, ?)", (f"working:{version}", value))

    res = cards.verify(conn, cid, run_tests=False)
    assert any("no working-set eval for the base" in p for p in res["problems"])
    f1("v0", 0.60)
    res = cards.verify(conn, cid, run_tests=False)
    assert any("candidate prompt" in p for p in res["problems"])
    f1("v1", 0.50)
    assert any("regressed" in p for p in cards.verify(conn, cid, run_tests=False)["problems"])
    f1("v1", 0.62)
    res = cards.verify(conn, cid, run_tests=False)
    assert res["ok"] and res["needs_heldout"]
    row = cards.get_card(conn, cid)
    assert row["status"] == "built" and row["heldout_check"] == "pending"


def test_full_cycle_merge(conn, repo, monkeypatch):
    cid, path = building_card(conn, repo)
    commit_file(path, "pipeline/mapping.py", "X = 2\n")
    assert cards.verify(conn, cid, run_tests=False)["ok"]
    cards.review(conn, cid, "approve", "fine")
    with pytest.raises(CardError, match="Edgar has not approved the merge"):
        cards.merge(conn, cid)
    with conn:
        conn.execute("UPDATE improvement_card SET merge_approved_at = '2026-10-15T00:00:00Z' WHERE id = ?",
                     (cid,))
    # skip the test run inside merge: the scratch repo has no suite
    real_run = subprocess.run

    def fake_run(cmd, *a, **k):
        if cmd[:3] == ["uv", "run", "pytest"]:
            return subprocess.CompletedProcess(cmd, 0, "ok", "")
        return real_run(cmd, *a, **k)
    monkeypatch.setattr(cards.subprocess, "run", fake_run)
    sha = cards.merge(conn, cid)
    assert git(repo, "rev-parse", "HEAD") == sha
    assert (repo / "pipeline" / "mapping.py").read_text() == "X = 2\n"
    row = cards.get_card(conn, cid)
    assert row["status"] == "merged" and row["merged_sha"] == sha
    assert json.loads(row["baseline_json"])["value"] == 0.2


def test_head_moved_after_review_blocks_merge(conn, repo, monkeypatch):
    cid, path = building_card(conn, repo)
    commit_file(path, "pipeline/mapping.py", "X = 2\n")
    cards.verify(conn, cid, run_tests=False)
    cards.review(conn, cid, "approve", "fine")
    with conn:
        conn.execute("UPDATE improvement_card SET merge_approved_at = 'x' WHERE id = ?", (cid,))
    commit_file(path, "pipeline/mapping.py", "X = 99\n")
    with pytest.raises(CardError, match="branch moved"):
        cards.merge(conn, cid)
