import json

import pytest

from pipeline import db, embed, evals
from pipeline.__main__ import main


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SIG_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(evals, "EVALS_DIR", tmp_path / "evals")
    monkeypatch.setattr(embed, "current_extract_version", lambda: "v2")
    c = db.connect(tmp_path / "t.db")
    db.migrate(c)
    with c:
        c.execute("INSERT INTO run (id, kind, status) VALUES (1, 'collect', 'ok')")
        c.execute("INSERT INTO prompt (id, name, version, text) VALUES (1, 'extract', 'v1', 'old')")
        c.execute("INSERT INTO prompt (id, name, version, text) VALUES (2, 'extract', 'v2', 'new')")
    return c


def add_item(c, item_id, source, body="I waste two hours every week on invoices.", pred=None,
             prompt_id=2, quote=None):
    with c:
        c.execute(
            "INSERT INTO raw_item (id, source, source_id, title, body, content_hash, license,"
            " tos_class, run_id) VALUES (?, ?, ?, ?, ?, 'h', 'test', 'clean', 1)",
            (item_id, source, f"s{item_id}", f"title {item_id}", body))
        if pred is not None:
            eid = c.execute(
                "INSERT INTO extraction (raw_item_id, run_id, prompt_id, model, is_pain)"
                " VALUES (?, 1, ?, 'm', ?)", (item_id, prompt_id, int(pred))).lastrowid
            if quote is not None:
                c.execute(
                    "INSERT INTO pain (extraction_id, idx, job, problem, who, intensity,"
                    " evidence_level, quote, quote_kind) VALUES (?, 0, 'j', 'p', 'w', 3, 'E1', ?,"
                    " 'verbatim')", (eid, quote))


def write_labels(set_name, rows, blank_lines=False):
    path = evals.labels_path(set_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for item_id, label in rows:
        lines.append(json.dumps({"raw_item_id": item_id, "source": "x", "source_id": str(item_id),
                                 "label": label, "note": "", "labeled_at": "2026-10-13T00:00:00Z"}))
        if blank_lines:
            lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_confusion_math():
    c = evals.Confusion(tp=6, fp=2, fn=3, tn=9)
    assert c.n == 20
    assert c.precision == pytest.approx(0.75)
    assert c.recall == pytest.approx(6 / 9)
    assert c.f1 == pytest.approx(2 * 0.75 * (6 / 9) / (0.75 + 6 / 9))
    assert c.accuracy == pytest.approx(15 / 20)
    empty = evals.Confusion(tn=4)
    assert empty.precision is None and empty.recall is None and empty.f1 is None
    assert empty.accuracy == 1.0


def test_load_labels_override_and_blank_lines(tmp_path, env):
    write_labels("working", [(1, "pain"), (2, "not_pain"), (1, "not_pain")], blank_lines=True)
    labels = evals.load_labels(evals.labels_path("working"))
    assert {k: v["label"] for k, v in labels.items()} == {1: "not_pain", 2: "not_pain"}
    assert evals.load_labels(evals.labels_path("heldout")) == {}


def test_load_labels_rejects_bad_label(env):
    write_labels("working", [(1, "maybe")])
    with pytest.raises(ValueError, match="line 1"):
        evals.load_labels(evals.labels_path("working"))


def test_evaluate_counts_and_ignores_unsure(env):
    add_item(env, 1, "hn", pred=True)        # tp
    add_item(env, 2, "hn", pred=True)        # fp
    add_item(env, 3, "govuk", pred=False)    # fn
    add_item(env, 4, "govuk", pred=False)    # tn
    add_item(env, 5, "govuk", pred=True)     # unsure: ignored
    add_item(env, 6, "hn")                   # no extraction: missing
    add_item(env, 7, "hn", pred=False, prompt_id=1)  # only an old-prompt extraction: missing
    labels = {1: "pain", 2: "not_pain", 3: "pain", 4: "not_pain", 5: "unsure", 6: "pain",
              7: "pain"}
    res = evals.evaluate(env, {k: {"label": v} for k, v in labels.items()}, 2, "working", "v2")
    o = res.overall
    assert (o.tp, o.fp, o.fn, o.tn) == (1, 1, 1, 1)
    assert res.unsure == 1 and res.missing == 2
    assert res.by_source["hn"].n == 2 and res.by_source["govuk"].n == 2
    assert {e[0] for e in res.errors} == {2, 3}


def test_quote_share(env):
    add_item(env, 1, "hn", body="<p>I waste two hours every week on invoices.</p>", pred=True,
             quote="two hours every week")
    add_item(env, 2, "hn", pred=True, quote="this sentence is not in the text")
    labels = {1: {"label": "pain"}, 2: {"label": "pain"}}
    res = evals.evaluate(env, labels, 2, "working", "v2")
    assert (res.quotes_found, res.quotes_checked) == (1, 2)
    assert res.quote_share == 0.5


def test_eval_working_logs_metrics_and_breakdown(env, capsys):
    add_item(env, 1, "hn", pred=True)
    add_item(env, 2, "govuk", pred=False)
    write_labels("working", [(1, "pain"), (2, "pain")])
    assert main(["eval"]) == 0
    out = capsys.readouterr().out
    assert "precision 1.000" in out and "recall 0.500" in out
    assert "govuk" in out and "disagreements" in out
    run = env.execute("SELECT id, kind, status FROM run WHERE kind = 'eval'").fetchone()
    assert run["status"] == "ok"
    subjects = {r["subject"] for r in env.execute(
        "SELECT subject FROM metric WHERE run_id = ? AND name = 'eval_n'", (run["id"],))}
    assert subjects == {"working:v2", "working:v2:hn", "working:v2:govuk"}


def test_eval_prompt_version_flag(env, capsys):
    add_item(env, 1, "hn", pred=False, prompt_id=1)
    write_labels("working", [(1, "not_pain")])
    assert main(["eval", "--prompt-version", "v1"]) == 0
    assert "accuracy 1.000" in capsys.readouterr().out
    assert main(["eval", "--prompt-version", "nope"]) == 1


def test_eval_heldout_prints_aggregates_only_and_writes_no_rows(env, capsys):
    add_item(env, 1, "hn", pred=True)
    add_item(env, 2, "govuk", pred=True)
    write_labels("heldout", [(1, "pain"), (2, "not_pain")])
    runs_before = env.execute("SELECT COUNT(*) FROM run").fetchone()[0]
    assert main(["eval", "--set", "heldout"]) == 0
    out = capsys.readouterr().out
    assert "precision 0.500" in out
    assert "hn" not in out and "govuk" not in out and "title" not in out
    assert "disagreements" not in out
    assert env.execute("SELECT COUNT(*) FROM run").fetchone()[0] == runs_before
    assert env.execute("SELECT COUNT(*) FROM metric").fetchone()[0] == 0
    # Aggregates go to the gitignored results file only (tmp here), appended.
    assert main(["eval", "--set", "heldout"]) == 0
    lines = (evals.EVALS_DIR / "heldout" / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert rec["prompt_version"] == "v2" and rec["precision"] == 0.5 and rec["tp"] == 1
    assert not set(rec) & {"by_source", "errors", "hn", "govuk"}


def test_eval_defaults_to_current_prompt_not_newest(env, monkeypatch, capsys):
    add_item(env, 1, "hn", pred=False, prompt_id=1)
    write_labels("working", [(1, "not_pain")])
    monkeypatch.setattr(embed, "current_extract_version", lambda: "v1")  # v2 is newer
    assert main(["eval"]) == 0
    assert "prompt v1" in capsys.readouterr().out
    monkeypatch.setattr(embed, "current_extract_version", lambda: "v9")  # never extracted
    assert main(["eval"]) == 1
    assert "v9 (current)" in capsys.readouterr().out


def test_eval_status(env, capsys):
    add_item(env, 1, "hn", pred=True)
    add_item(env, 2, "govuk")
    write_labels("working", [(1, "pain"), (2, "not_pain"), (3, "unsure")])
    assert main(["eval-status"]) == 0
    out = capsys.readouterr().out
    assert "working: 3 labeled  (pain 1, not_pain 1, unsure 1); 1 lack an extraction" in out
    assert "heldout: 0 labeled" in out


def test_consistency_agreement_and_kappa():
    from pipeline.evals import consistency
    rec = lambda label, source="wordpress": {"label": label, "source": source}  # noqa: E731
    first = {1: rec("pain"), 2: rec("not_pain"), 3: rec("pain"), 4: rec("not_pain"),
             5: rec("pain", "hn"), 6: rec("unsure")}
    second = {1: rec("pain"), 2: rec("pain"), 3: rec("pain"), 4: rec("not_pain"),
              5: rec("not_pain", "hn"), 6: rec("pain")}
    res = consistency(first, second)
    assert res["review"]["n"] == 4 and res["review"]["agreement"] == 0.75
    assert res["control"]["n"] == 1 and res["control"]["agreement"] == 0.0
    assert res["all"]["n"] == 5  # the unsure item is left out
    assert round(res["review"]["kappa"], 2) == 0.5
    assert {f[0] for f in res["flips"]} == {2, 5}
