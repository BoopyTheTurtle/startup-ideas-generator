"""Replay tests for the Stack Exchange collector. Re-record with:
SIG_HTTP=record uv run pytest tests/collectors/test_stackexchange.py

The recorded fetch runs once per module (one request per site) to spare the API's
anonymous quota of ~300 requests a day.
"""

import json
import os

import pytest

from pipeline.collectors.base import SchemaDrift, State
from pipeline.collectors.stackexchange import SITES, StackExchange
from pipeline.http import Http, Response

# Fixed cursor so recorded request params match on replay.
SINCE = "1791244800"  # 2026-10-06
MAX_ITEMS = 30        # two questions per site


@pytest.fixture(scope="module")
def recorded():
    http = Http("stackexchange", min_interval=0, mode=os.environ.get("SIG_HTTP", "replay"))
    state = State({f"fromdate:{site}": SINCE for site in SITES})
    try:
        return list(StackExchange(max_items=MAX_ITEMS).fetch(http, state)), state
    finally:
        http.close()


def test_items_have_required_fields(recorded):
    items, _ = recorded
    assert items
    for it in items:
        site, qid = it.source_id.split(":")
        assert site in SITES and qid.isdigit()
        assert it.body.strip() and it.title and it.url.startswith("https://")
        assert it.created_at >= "2026-10-06" and it.lang == "en"
        assert set(it.metrics) == {"score", "answer_count", "view_count", "is_answered"}
        assert it.extra["site"] == site and isinstance(it.extra["tags"], list)


def test_no_duplicate_ids_and_cap_respected(recorded):
    items, _ = recorded
    ids = [it.source_id for it in items]
    assert len(ids) == len(set(ids)) and len(ids) <= MAX_ITEMS
    per_site = MAX_ITEMS // len(SITES)
    for site in SITES:
        assert sum(it.extra["site"] == site for it in items) <= per_site


def test_cursors_advance(recorded):
    items, state = recorded
    for site in {it.extra["site"] for it in items}:
        assert int(state.get(f"fromdate:{site}")) > int(SINCE)
    assert state.get("stopped") == ""


class FakeHttp:
    """Serves canned API responses in order, so quota logic runs without the network."""

    mode = "replay"

    def __init__(self, bodies, status=200):
        self.bodies, self.status, self.calls = list(bodies), status, []

    def get(self, url, params=None, headers=None):
        self.calls.append(params)
        return Response(url, self.status, "application/json", json.dumps(self.bodies.pop(0)))


def question(qid, created=1791300000):
    return {"question_id": qid, "title": "Can&#39;t sync", "body": "<p>help</p>",
            "link": f"https://example.stackexchange.com/q/{qid}", "creation_date": created,
            "score": 1, "answer_count": 0, "view_count": 5, "is_answered": False,
            "tags": ["sync"], "owner": {"user_id": 7}}


def test_stops_cleanly_when_quota_low():
    page = {"items": [question(1)], "has_more": False, "quota_remaining": 3}
    http = FakeHttp([page])
    state = State({})
    items = list(StackExchange(max_items=30).fetch(http, state))
    assert len(http.calls) == 1 and len(items) == 1
    assert items[0].title == "Can't sync" and items[0].author == "7"
    assert state.get(f"fromdate:{SITES[0]}") == "1791300001"
    assert state.get("quota_remaining") == "3" and "quota_remaining" in state.get("stopped")


def test_stops_cleanly_on_throttle_violation():
    err = {"error_id": 502, "error_name": "throttle_violation",
           "error_message": "too many requests from this IP"}
    http = FakeHttp([err], status=400)
    state = State({f"fromdate:{SITES[0]}": SINCE})
    assert list(StackExchange(max_items=30).fetch(http, state)) == []
    assert state.get(f"fromdate:{SITES[0]}") == SINCE
    assert "throttle_violation" in state.get("stopped")


def test_schema_drift_fails_loudly():
    http = FakeHttp([{"items": [], "quota_remaining": 100}])  # no has_more
    with pytest.raises(SchemaDrift):
        list(StackExchange(max_items=30).fetch(http, State({})))
