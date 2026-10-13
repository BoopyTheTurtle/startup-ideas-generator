"""Replay tests for the UK Parliament petitions collector. Re-record with:
SIG_HTTP=record uv run pytest tests/collectors/test_uk_petitions.py
"""

import os

import pytest

from pipeline.collectors import uk_petitions
from pipeline.collectors.base import SchemaDrift, State
from pipeline.collectors.uk_petitions import UkPetitions
from pipeline.http import Http, Response

# Fixed cursors so recorded request params match on replay. Each listing needs one page.
OPEN_SINCE = "2026-10-11T00:00:00+00:00"
REJECTED_SINCE = "2026-10-05T00:00:00+00:00"
LAG_DAYS = 10  # horizon 2026-09-25, inside page 1 of the rejected listing


@pytest.fixture(autouse=True)
def short_lag(monkeypatch):
    monkeypatch.setattr(uk_petitions, "REJECTION_LAG_DAYS", LAG_DAYS)


def fetch(max_items=200, take=None):
    http = Http("uk_petitions", min_interval=0, mode=os.environ.get("SIG_HTTP", "replay"))
    state = State({"open_since": OPEN_SINCE, "rejected_since": REJECTED_SINCE})
    try:
        gen = UkPetitions(max_items=max_items).fetch(http, state)
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
        assert it.source_id.isdigit() and it.body.strip() and it.title
        assert it.url == f"https://petition.parliament.uk/petitions/{it.source_id}"
        assert it.created_at.endswith("+00:00") and it.lang == "en" and it.country == "GB"
        assert it.author is None
        assert "signature_count" in it.metrics
        assert it.extra["government_response"] in (0, 1) and it.extra["debate"] in (0, 1)


def test_open_and_rejected_both_collected():
    items, _ = fetch()
    states = {it.extra["state"] for it in items}
    assert {"open", "rejected"} <= states
    for it in items:
        if it.extra["state"] == "rejected":
            assert it.extra["rejection_code"]
        else:
            assert "rejection_code" not in it.extra
            assert it.created_at > OPEN_SINCE


def test_no_duplicate_ids_and_cap_respected():
    items, _ = fetch(max_items=10)
    ids = [it.source_id for it in items]
    assert len(ids) == len(set(ids)) and len(ids) <= 10
    assert {it.extra["state"] for it in items} == {"open", "rejected"}  # budget is split


def test_cursors_advance():
    _, state = fetch()
    assert state.get("open_since") > OPEN_SINCE
    assert state.get("rejected_since") > REJECTED_SINCE


def test_cut_short_run_resumes_at_last_item():
    items, state = fetch(take=3)
    assert len(items) == 3
    assert state.get("open_since") == items[-1].created_at  # oldest first, cursor = last
    assert state.get("rejected_since") == REJECTED_SINCE  # rejected stream not reached


class _Stub:
    def get(self, url, params=None, headers=None):
        return Response(url, 200, "application/json", '{"data": [{"id": 1}], "links": {}}')

    def check_robots(self, url):
        pass


def test_schema_drift_raises():
    with pytest.raises(SchemaDrift):
        list(UkPetitions().fetch(_Stub(), State({"open_since": OPEN_SINCE,
                                                 "rejected_since": REJECTED_SINCE})))
