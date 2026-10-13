import json

import pytest

from pipeline import db, runs
from pipeline.extract import extract, scrub
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
    assert stats["llm_failures"] == 1
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


def test_bad_fields_are_dropped(conn):
    add_item(conn, "a", LONG)
    fake = Fake(lambda i: {"id": i["id"], "is_pain": True, "problems": [
        problem("copying invoices from email into Excel", intensity=9),
        problem("copying invoices from email into Excel", evidence_level="E4"),
        problem("copying invoices from email into Excel", who=""),
    ]})
    stats = extract(conn, fake)
    assert stats["problems_dropped"] == 3 and stats["problems_kept"] == 0
