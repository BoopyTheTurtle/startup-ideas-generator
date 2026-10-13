import json
import sqlite3
import time

import pytest

from pipeline import db, runs
from pipeline.extract import PROMPT_FILE, extract, scrub
from pipeline.llm import LLMError, LLMResult
from pipeline.text import find_quote, plain_text

LONG = "I spend three hours every Friday copying invoices from email into Excel by hand."


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.migrate(c)
    return c


def add_item(conn, sid, body, source="forums", retain=1):
    with runs.run(conn, "collect") as run_id, conn:
        return conn.execute(
            "INSERT INTO raw_item (source, source_id, body, content_hash, license, tos_class,"
            " run_id, retain_text) VALUES (?, ?, ?, ?, 'x', 'clean', ?, ?)",
            (source, sid, body, sid, run_id, retain)).lastrowid


def problem(quote, **kw):
    p = {"job": "pay suppliers", "problem": "invoices must be copied by hand",
         "who": "small business owner", "workaround": "Excel", "cost_cue": "3 hours a week",
         "intensity": 3, "evidence_level": "E2", "quote": quote,
         "paraphrase": "They copy invoices by hand weekly."}
    p.update(kw)
    return p


class Fake:
    name = "fake"

    def __init__(self, answer, fail=False):
        self.answer, self.fail, self.calls = answer, fail, []

    def run(self, system, user, schema, model):
        payload = json.loads(user)
        self.calls.append(payload)
        if self.fail:
            raise LLMError("boom")
        return LLMResult({"items": [self.answer(i) for i in payload]}, "fake-model", 0.01)


def test_plain_text_and_quote_offsets():
    text = plain_text("<p>I spend   three hours</p><p>every Friday.</p>")
    assert text == "I spend three hours\n\nevery Friday."  # paragraphs stay apart
    start, end = find_quote(text, "three hours every friday")
    assert text[start:end] == "three hours\n\nevery Friday"
    assert find_quote(text, "four hours every Friday") is None


def test_short_items_are_rule_filtered_without_llm(conn):
    add_item(conn, "a", "too short")
    fake = Fake(lambda i: {"id": i["id"], "is_pain": False, "problems": []})
    stats = extract(conn, fake)
    assert fake.calls == [] and stats["rule_filtered"] == 1
    row = conn.execute("SELECT model, is_pain FROM extraction").fetchone()
    assert tuple(row) == ("rule", 0)


def test_verbatim_quote_stored_with_offsets(conn):
    iid = add_item(conn, "a", f"<p>{LONG}</p>")
    fake = Fake(lambda i: {"id": i["id"], "is_pain": True,
                           "problems": [problem("copying invoices from email into Excel")]})
    extract(conn, fake)
    p = conn.execute("SELECT * FROM pain").fetchone()
    assert p["quote_kind"] == "verbatim" and p["quote"] == "copying invoices from email into Excel"
    assert LONG[p["quote_start"]:p["quote_end"]] == p["quote"]
    e = conn.execute("SELECT * FROM extraction WHERE raw_item_id = ?", (iid,)).fetchone()
    assert e["is_pain"] == 1 and e["model"] == "fake-model"


def test_ungrounded_quote_is_dropped_and_counted(conn):
    add_item(conn, "a", LONG)
    fake = Fake(lambda i: {"id": i["id"], "is_pain": True,
                           "problems": [problem("they hate their accountant")]})
    stats = extract(conn, fake)
    assert conn.execute("SELECT COUNT(*) FROM pain").fetchone()[0] == 0
    assert stats["quote_miss"] == 1
    assert conn.execute("SELECT note FROM extraction").fetchone()[0] == "quote_miss"


def test_no_retain_items_store_paraphrase_and_get_scrubbed(conn):
    add_item(conn, "a", LONG, retain=0)
    fake = Fake(lambda i: {"id": i["id"], "is_pain": True,
                           "problems": [problem("copying invoices from email into Excel")]})
    extract(conn, fake)
    p = conn.execute("SELECT quote, quote_kind, quote_start FROM pain").fetchone()
    assert tuple(p) == ("They copy invoices by hand weekly.", "paraphrase", None)
    assert scrub(conn) == 1
    r = conn.execute("SELECT body, text_discarded_at FROM raw_item").fetchone()
    assert r["body"] == "" and r["text_discarded_at"]


def test_no_retain_items_go_first(conn):
    add_item(conn, "keep", LONG)
    add_item(conn, "drop", LONG + " Also by fax.", retain=0)
    fake = Fake(lambda i: {"id": i["id"], "is_pain": False, "problems": []})
    extract(conn, fake, max_items=1)
    assert fake.calls[0][0]["text"].endswith("by fax.")


def test_failed_batch_and_missing_items_are_retried_next_run(conn):
    add_item(conn, "a", LONG)
    add_item(conn, "b", LONG + " Twice.")
    stats = extract(conn, Fake(None, fail=True))
    assert stats["llm_failures"] == 3 and stats["llm_items_failed"] == 2  # batch + both halves
    assert conn.execute("SELECT COUNT(*) FROM extraction").fetchone()[0] == 0
    only_first = Fake(lambda i: {"id": i["id"], "is_pain": False, "problems": []})
    only_first.answer = lambda i: ({"id": i["id"], "is_pain": False, "problems": []}
                                   if not i["text"].endswith("Twice.") else {"id": -1})
    stats = extract(conn, only_first)
    assert stats["items_missing"] == 1
    assert conn.execute("SELECT COUNT(*) FROM extraction").fetchone()[0] == 1


def test_prompt_version_registered_and_items_not_reextracted(conn):
    add_item(conn, "a", LONG)
    fake = Fake(lambda i: {"id": i["id"], "is_pain": False, "problems": []})
    v1 = extract(conn, fake)["prompt_version"]
    extract(conn, fake)
    assert len(fake.calls) == 1
    assert conn.execute("SELECT version FROM prompt").fetchone()[0] == v1


def test_prompt_change_reextracts_only_on_request(conn, tmp_path, monkeypatch):
    add_item(conn, "a", LONG)
    fake = Fake(lambda i: {"id": i["id"], "is_pain": False, "problems": []})
    extract(conn, fake)
    new_prompt = tmp_path / "extract.md"
    new_prompt.write_text(PROMPT_FILE.read_text(encoding="utf-8") + "\n- New rule.\n",
                          encoding="utf-8")
    monkeypatch.setattr("pipeline.extract.PROMPT_FILE", new_prompt)
    extract(conn, fake)
    assert len(fake.calls) == 1  # a prompt edit alone re-extracts nothing
    extract(conn, fake, reextract=True)
    assert len(fake.calls) == 2
    assert conn.execute("SELECT COUNT(DISTINCT prompt_id) FROM extraction").fetchone()[0] == 2


def test_no_retain_fields_that_copy_the_source_are_rejected(conn):
    fr = "Je passe trois heures chaque vendredi à recopier les factures à la main, c'est épuisant."
    add_item(conn, "a", fr, retain=0)
    quote = "trois heures chaque vendredi à recopier les factures"
    fake = Fake(lambda i: {"id": i["id"], "is_pain": True, "problems": [
        problem(quote, paraphrase=quote),                                   # copied: dropped
        problem(quote, workaround="recopier les factures à la main",        # copied: nulled
                cost_cue="trois heures chaque vendredi"),
    ]})
    stats = extract(conn, fake)
    assert stats["copied_text"] == 1 and stats["problems_kept"] == 1
    p = conn.execute("SELECT workaround, cost_cue, quote_kind FROM pain").fetchone()
    assert tuple(p) == (None, None, "paraphrase")
    assert "copied_text" in conn.execute("SELECT note FROM extraction").fetchone()[0]


def test_retained_items_may_reuse_source_words(conn):
    add_item(conn, "a", LONG)
    quote = "copying invoices from email into Excel"
    extract(conn, Fake(lambda i: {"id": i["id"], "is_pain": True,
                                  "problems": [problem(quote, workaround="copying invoices by hand")]}))
    assert conn.execute("SELECT workaround FROM pain").fetchone()[0] == "copying invoices by hand"


def test_scrub_blanks_title_keeps_url_and_logs_metrics(conn):
    extracted = add_item(conn, "a", LONG, retain=0)
    stale = add_item(conn, "b", LONG + " Old.", retain=0)
    kept = add_item(conn, "c", LONG)
    with conn:
        conn.execute("UPDATE raw_item SET title = 'Secret title', url = 'https://x/' || id")
        conn.execute("UPDATE raw_item SET fetched_at = '2020-01-01T00:00:00Z' WHERE id = ?", (stale,))
    extract(conn, Fake(lambda i: {"id": i["id"], "is_pain": False, "problems": []}), max_items=1)
    assert scrub(conn) == 2
    rows = {r["id"]: r for r in conn.execute("SELECT * FROM raw_item")}
    for i in (extracted, stale):
        assert rows[i]["body"] == "" and rows[i]["title"] is None
        assert rows[i]["url"] == f"https://x/{i}" and rows[i]["text_discarded_at"]
    assert rows[kept]["title"] == "Secret title" and rows[kept]["body"] == LONG
    run = conn.execute("SELECT id, status FROM run WHERE kind = 'scrub'").fetchone()
    assert run["status"] == "ok"
    metrics = dict(conn.execute("SELECT name, value FROM metric WHERE run_id = ?", (run["id"],)))
    assert metrics == {"scrubbed": 2, "scrubbed_unextracted": 1}
    assert scrub(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM run WHERE kind = 'scrub'").fetchone()[0] == 1


def test_scrub_finishes_items_scrubbed_before_titles_were_blanked(conn):
    iid = add_item(conn, "a", "", retain=0)
    with conn:
        conn.execute("UPDATE raw_item SET title = 'Old title', text_discarded_at = '2026-10-01'"
                     " WHERE id = ?", (iid,))
    assert scrub(conn) == 1
    r = conn.execute("SELECT title, text_discarded_at FROM raw_item").fetchone()
    assert tuple(r) == (None, "2026-10-01")


def test_errors_for_no_retain_batches_are_redacted(conn, capsys):
    add_item(conn, "a", LONG, retain=0)

    class Leaky(Fake):
        def run(self, system, user, schema, model):
            raise LLMError("claude error: " + json.loads(user)[0]["text"], exit_code=1)

    stats = extract(conn, Leaky(None))
    out = capsys.readouterr().out
    assert stats["llm_failures"] == 1 and "LLMError" in out and "exit 1" in out
    assert "invoices" not in out


def test_failed_batch_is_split_and_retried_once(conn):
    ids = [add_item(conn, f"i{n}", LONG + f" Item {n}.") for n in range(4)]
    bad = ids[0]

    class Picky(Fake):
        def run(self, system, user, schema, model):
            payload = json.loads(user)
            self.calls.append([i["id"] for i in payload])
            if any(i["id"] == bad for i in payload):
                raise LLMError("bad item")
            return LLMResult({"items": [{"id": i["id"], "is_pain": False, "problems": []}
                                        for i in payload]}, "m", 0.0)

    fake = Picky(None)
    stats = extract(conn, fake, batch_size=4, workers=1)
    assert len(fake.calls) == 3  # the batch, then each half once; no further splitting
    assert stats["llm_failures"] == 2 and stats["llm_items_failed"] == 2
    assert stats["items_extracted"] == 2


def test_single_item_batch_is_not_split(conn):
    add_item(conn, "a", LONG)
    fake = Fake(None, fail=True)
    stats = extract(conn, fake)
    assert len(fake.calls) == 1 and stats["llm_items_failed"] == 1


def test_non_object_data_counts_as_llm_failure(conn):
    add_item(conn, "a", LONG)

    class Weird(Fake):
        def run(self, system, user, schema, model):
            return LLMResult(["not", "a", "dict"], "m", 0.0)  # type: ignore[arg-type]

    stats = extract(conn, Weird(None))
    assert stats["llm_failures"] == 1 and stats["llm_items_failed"] == 1


def test_unexpected_error_stops_work_records_metrics_and_raises(conn):
    for n in range(6):
        add_item(conn, f"i{n}", LONG + f" Item {n}.")

    class Broken(Fake):
        def run(self, system, user, schema, model):
            self.calls.append(user)
            time.sleep(0.2)
            raise RuntimeError("bug")

    fake = Broken(None)
    with pytest.raises(RuntimeError, match="bug"):
        extract(conn, fake, batch_size=1, workers=1)
    assert len(fake.calls) < 6  # pending batches were cancelled
    run = conn.execute("SELECT id, status FROM run WHERE kind = 'extract'").fetchone()
    assert run["status"] == "failed"
    metrics = dict(conn.execute("SELECT name, value FROM metric WHERE run_id = ?", (run["id"],)))
    assert metrics["aborted"] == 1 and metrics["llm_failures"] >= 1


def test_database_error_while_storing_stops_and_raises(conn, monkeypatch):
    add_item(conn, "a", LONG)

    def locked(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("pipeline.extract._store_answers", locked)
    with pytest.raises(sqlite3.OperationalError):
        extract(conn, Fake(lambda i: {"id": i["id"], "is_pain": False, "problems": []}))
    run = conn.execute("SELECT id, status FROM run WHERE kind = 'extract'").fetchone()
    assert run["status"] == "failed"
    assert conn.execute("SELECT value FROM metric WHERE run_id = ? AND name = 'aborted'",
                        (run["id"],)).fetchone()[0] == 1


def test_bad_fields_are_dropped(conn):
    add_item(conn, "a", LONG)
    fake = Fake(lambda i: {"id": i["id"], "is_pain": True, "problems": [
        problem("copying invoices from email into Excel", intensity=9),
        problem("copying invoices from email into Excel", evidence_level="E4"),
        problem("copying invoices from email into Excel", who=""),
    ]})
    stats = extract(conn, fake)
    assert stats["problems_dropped"] == 3 and stats["problems_kept"] == 0
