"""Replay tests for the GOV.UK consultations and CMA cases collector. Re-record with:
SIG_HTTP=record uv run pytest tests/collectors/test_govuk.py
"""

import json
import os

import pytest

from pipeline.collectors.base import SchemaDrift, State
from pipeline.collectors.govuk import GovUk
from pipeline.http import Http, Response

# Fixed cursors so recorded request params match on replay.
CURSORS = {
    "consultations_since": "2026-10-11T00:00:00+00:00", "consultations_last_id": "",
    "cma_since": "2026-10-08T00:00:00+00:00", "cma_last_id": "",
}


def fetch(max_items=200, take=None):
    http = Http("govuk", min_interval=0, mode=os.environ.get("SIG_HTTP", "replay"))
    state = State(CURSORS)
    try:
        gen = GovUk(max_items=max_items).fetch(http, state)
        items = []
        for it in gen:
            items.append(it)
            if take and len(items) >= take:
                gen.close()  # what the runner does when it hits max_items
                break
        return items, state
    finally:
        http.close()


def test_items_have_required_fields():
    items, _ = fetch()
    assert items
    for it in items:
        assert it.source_id and it.body.strip() and it.title
        assert it.url.startswith("https://www.gov.uk/")
        assert it.created_at.endswith("+00:00") and it.country == "GB" and it.lang == "en"
        assert it.author and it.metrics == {} and it.extra["html"] is True
        assert it.extra["organisations"]
        assert "ways_to_respond" not in it.extra and "@" not in json.dumps(it.extra)


def test_both_streams_and_type_fields():
    items, _ = fetch()
    types = {it.extra["document_type"] for it in items}
    assert "cma_case" in types and types & {"open_consultation", "closed_consultation",
                                             "consultation_outcome"}
    for it in items:
        if it.extra["document_type"] == "cma_case":
            assert it.url.startswith("https://www.gov.uk/cma-cases/")
            assert it.extra["case_type"] and it.extra["case_state"]
            assert it.created_at > CURSORS["cma_since"]
        else:
            assert it.extra["closing_date"].endswith("+00:00")
            assert it.created_at > CURSORS["consultations_since"]


def test_no_duplicate_ids_and_cap_respected():
    items, _ = fetch(max_items=6)
    ids = [it.source_id for it in items]
    assert len(ids) == len(set(ids)) and len(ids) <= 6
    assert len({it.extra["document_type"] == "cma_case" for it in items}) == 2  # budget split


def test_cursors_advance():
    _, state = fetch()
    assert state.get("consultations_since") > CURSORS["consultations_since"]
    assert state.get("cma_since") > CURSORS["cma_since"]
    assert state.get("consultations_last_id") and state.get("cma_last_id")


def test_cut_short_run_resumes_at_last_item():
    items, state = fetch(take=2)
    assert len(items) == 2 and items[0].created_at <= items[1].created_at  # oldest first
    assert state.get("consultations_since") == items[-1].created_at
    assert state.get("consultations_last_id") == items[-1].source_id.split(":")[0]
    assert state.get("cma_since") == CURSORS["cma_since"]  # cma stream not reached


class _Stub:
    """Search returns `results`; content returns `doc` for every path."""

    def __init__(self, results, doc):
        self.results, self.doc, self.paths = results, doc, []

    def get(self, url, params=None, headers=None):
        if url.endswith("search.json"):
            body = {"results": self.results if "filter_format" not in params else [],
                    "total": len(self.results)}
        else:
            self.paths.append(url)
            body = self.doc
        return Response(url, 200, "application/json", json.dumps(body))


def _result(cid, ts="2026-10-12T09:00:00Z"):
    return {"content_id": cid, "link": f"/government/consultations/{cid}", "title": cid,
            "public_timestamp": ts, "content_store_document_type": "open_consultation",
            "organisations": [{"slug": "hm-treasury", "title": "HM Treasury"}]}


DOC = {"content_id": "x", "base_path": "/government/consultations/x", "title": "T",
       "document_type": "open_consultation", "locale": "en", "description": "D",
       "details": {"body": "<p>B</p>", "closing_date": "2026-11-10T23:59:00.000+00:00"},
       "links": {}}


def test_timestamp_ties_survive_a_budget_cut():
    results = [_result("b"), _result("a"), _result("c")]  # same timestamp
    state = State(CURSORS)
    first = list(GovUk(max_items=2).fetch(_Stub(results, DOC), state))
    assert [it.source_id for it in first] == ["a:open_consultation", "b:open_consultation"]
    second = list(GovUk(max_items=2).fetch(_Stub(results, DOC), state))
    assert [it.source_id for it in second] == ["c:open_consultation"]


def test_schema_drift_on_naive_timestamp():
    with pytest.raises(SchemaDrift):
        list(GovUk().fetch(_Stub([_result("a", ts="2026-10-12T09:00:00")], DOC),
                           State(CURSORS)))


def test_schema_drift_on_missing_keys():
    with pytest.raises(SchemaDrift):
        list(GovUk().fetch(_Stub([{"content_id": "a"}], DOC), State(CURSORS)))


def test_each_consultation_stage_is_a_separate_item():
    state = State(CURSORS)
    opened = list(GovUk(max_items=5).fetch(_Stub([_result("a")], DOC), state))
    outcome_doc = {**DOC, "document_type": "consultation_outcome"}
    later = _result("a")
    later["public_timestamp"] = "2026-12-01T09:00:00.000+00:00"
    outcome = list(GovUk(max_items=5).fetch(_Stub([later], outcome_doc), state))
    assert [it.source_id for it in opened + outcome] == [
        "a:open_consultation", "a:consultation_outcome"]
