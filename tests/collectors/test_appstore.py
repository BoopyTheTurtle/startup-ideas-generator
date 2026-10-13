"""Replay tests for the App Store collector. Re-record with:
SIG_HTTP=record uv run pytest tests/collectors/test_appstore.py

Apple's terms forbid republishing its content, so the recorded fixtures are gitignored
and the replay tests skip on a fresh clone. The fake-HTTP tests always run.
"""

import json
import os
import re

import pytest

from pipeline.collectors.appstore import AppStore
from pipeline.collectors.base import SchemaDrift, State
from pipeline.http import FIXTURES as ALL_FIXTURES, Http, Response

# A small fixed plan so recorded request URLs match on replay.
COUNTRIES = ["ie", "fr"]
GENRES = {"6015": "Finance"}
FIXTURES = ALL_FIXTURES / "appstore"


def collector(max_items=20):
    return AppStore(max_items=max_items, countries=COUNTRIES, genres=GENRES,
                    apps_per_genre=1, chart_depth=3)


def fetch(max_items=20, values=None):
    mode = os.environ.get("SIG_HTTP", "replay")
    if mode == "replay" and not any(FIXTURES.glob("*.json")):
        pytest.skip("App Store fixtures are local-only; record them to run this test")
    http = Http("appstore", min_interval=0, mode=os.environ.get("SIG_HTTP", "replay"))
    state = State(values or {"rotation": "0"})
    try:
        return list(collector(max_items).fetch(http, state)), state
    finally:
        http.close()


def test_items_have_required_fields():
    items, _ = fetch()
    assert items
    for it in items:
        assert re.fullmatch(r"(ie|fr):\d+:\d+", it.source_id)
        assert it.url.startswith("https://apps.apple.com/") and "?" not in it.url
        assert it.body.strip() and it.author and it.title is not None
        assert it.created_at.endswith("+00:00") and it.lang is None
        assert it.country in {"IE", "FR"}
        assert it.source_id.startswith(it.country.lower() + ":")
        assert 1 <= it.metrics["rating"] <= 3 and "vote_sum" in it.metrics
        assert set(it.extra) == {"app_id", "app_name", "genre", "app_version"}
        assert it.extra["genre"] == "Finance"


def test_no_duplicate_ids_cap_respected_and_spread():
    items, _ = fetch(max_items=20)
    ids = [it.source_id for it in items]
    assert len(ids) == len(set(ids)) and len(ids) <= 20
    assert {it.country for it in items} == {"IE", "FR"}


def test_cursor_stops_paging_and_rotation_advances():
    _, state = fetch()
    assert state.get("rotation") == "1"
    cursors = {k: v for k, v in state.values.items() if k.startswith("since:")}
    assert len(cursors) == 2
    # A second run from the saved cursors (same rotation) finds nothing new.
    again, state2 = fetch(values={**cursors, "rotation": "0"})
    assert again == []
    assert {k: state2.get(k) for k in cursors} == cursors


class FakeHttp:
    """Serves a chart with one app, then the given review feed for every page."""

    def __init__(self, review_feed):
        self.review_feed = review_feed

    def check_robots(self, url):
        pass

    def get(self, url, params=None, headers=None):
        if "topfreeapplications" in url:
            feed = {"feed": {"entry": [{
                "id": {"label": "https://apps.apple.com/gb/app/x/id1?uo=2",
                       "attributes": {"im:id": "1"}},
                "im:name": {"label": "X"}}]}}
        else:
            feed = self.review_feed
        return Response(url, 200, "text/javascript", json.dumps(feed))


REVIEW = {
    "author": {"uri": {"label": "https://itunes.apple.com/gb/reviews/id9"},
               "name": {"label": "a"}},
    "updated": {"label": "2026-10-11T08:26:26-07:00"}, "im:rating": {"label": "2"},
    "im:version": {"label": "1.0"}, "id": {"label": "5"}, "title": {"label": "Bad"},
    "content": {"label": "It crashes"},
}


def run_fake(review_feed, countries=("gb",)):
    c = AppStore(max_items=10, countries=list(countries), genres={"6000": "Business"},
                 apps_per_genre=1, chart_depth=1)
    return list(c.fetch(FakeHttp(review_feed), State({})))


def test_single_entry_object_is_accepted():
    items = run_fake({"feed": {"entry": REVIEW}})  # a bare object, not a list
    assert [it.source_id for it in items] == ["gb:1:5"]
    assert items[0].created_at == "2026-10-11T15:26:26+00:00"


def test_missing_review_field_is_schema_drift():
    broken = {k: v for k, v in REVIEW.items() if k != "content"}
    with pytest.raises(SchemaDrift):
        run_fake({"feed": {"entry": [broken]}})


def test_wrong_storefront_is_schema_drift():
    with pytest.raises(SchemaDrift):
        run_fake({"feed": {"entry": [REVIEW]}}, countries=("de",))


def test_every_feed_empty_is_schema_drift():
    with pytest.raises(SchemaDrift):
        run_fake({"feed": {}}, countries=("gb", "de", "fr"))
