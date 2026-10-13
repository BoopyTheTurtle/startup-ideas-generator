"""Replay tests for the Firefox Add-ons collector. Re-record with:
SIG_HTTP=record uv run pytest tests/collectors/test_firefox_addons.py

Ratings belong to their authors, so the recorded fixtures may be kept local (gitignored);
the replay tests then skip on a fresh clone. The fake-HTTP tests always run.
"""

import json
import os
from datetime import datetime, timezone

import pytest

from pipeline.collectors.base import SchemaDrift, State
from pipeline.collectors.firefox_addons import FirefoxAddons
from pipeline.http import FIXTURES as ALL_FIXTURES, Http, Response

# A small fixed plan so recorded request params match on replay: the top add-on of two
# categories (rotation 0), 20 ratings a page, cursors and clock pinned.
CATEGORIES = ["shopping", "tabs"]
NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)
CURSOR = "2026-08-01T00:00:00+00:00|0"
ADDON_IDS = ["950733", "782160"]  # wikibuy-for-firefox, multi-account-containers
FIXTURES = ALL_FIXTURES / "firefox_addons"


def start_state():
    return {"rotation": "0", **{f"since:{a}": CURSOR for a in ADDON_IDS}}


def collector(max_items=60):
    return FirefoxAddons(max_items=max_items, categories=CATEGORIES, pool_depth=4,
                         addons_per_category=1, page_size=20, now=NOW)


def fetch(max_items=60, values=None, take=None):
    mode = os.environ.get("SIG_HTTP", "replay")
    if mode == "replay" and not any(FIXTURES.glob("*.json")):
        pytest.skip("Firefox Add-ons fixtures are local-only; record them to run this test")
    http = Http("firefox_addons", min_interval=0, mode=mode)
    state = State(values or start_state())
    try:
        gen = collector(max_items).fetch(http, state)
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
        assert it.url == ("https://addons.mozilla.org/en-US/firefox/addon/"
                          f"{it.extra['addon_slug']}/reviews/{it.source_id}/")
        assert it.author and it.author.isdigit()  # numeric user id, never a name
        assert it.created_at.endswith("+00:00") and it.created_at > CURSOR[:25]
        assert it.lang is None and it.country is None
        assert 1 <= it.metrics["score"] <= 3
        assert set(it.extra) == {"addon_id", "addon_slug", "addon_users", "category",
                                 "addon_version", "has_developer_reply"}
        assert str(it.extra["addon_id"]) in ADDON_IDS
        assert it.extra["category"] in CATEGORIES


def test_no_duplicate_ids_cap_respected_and_spread():
    items, _ = fetch(max_items=10)
    ids = [it.source_id for it in items]
    assert len(ids) == len(set(ids)) and len(ids) <= 10
    assert {str(it.extra["addon_id"]) for it in items} == set(ADDON_IDS)


def test_cursors_advance_and_rerun_finds_nothing():
    items, state = fetch()
    assert state.get("rotation") == "1"
    cursors = {k: state.get(k) for k in start_state() if k.startswith("since:")}
    assert all(v > CURSOR for v in cursors.values())
    # A second run from the saved cursors (same rotation) finds nothing new.
    again, state2 = fetch(values={**cursors, "rotation": "0"})
    assert again == []
    assert {k: state2.get(k) for k in cursors} == cursors


def test_cut_short_run_resumes_at_last_item():
    items, state = fetch(take=3)
    assert len(items) == 3
    last = items[-1]
    key = f"since:{last.extra['addon_id']}"
    assert state.get(key) == f"{last.created_at}|{last.source_id}"  # oldest first
    # The rerun yields only what the cut-short run did not.
    rest, _ = fetch(values={**{k: v for k, v in state.values.items()}, "rotation": "0"})
    seen = {it.source_id for it in items}
    full, _ = fetch()
    assert {it.source_id for it in rest} == {it.source_id for it in full} - seen


class FakeHttp:
    """Serves one add-on per category search, then the given ratings page."""

    def __init__(self, ratings, results=True, name=None):
        self.ratings = ratings
        self.results = results
        self.name = name or {"en-US": "X"}

    def get(self, url, params=None, headers=None):
        if "search" in url:
            res = [{"id": 1, "slug": "x", "name": self.name, "average_daily_users": 9,
                    "type": "extension"}] if self.results else []
            body = {"count": len(res), "results": res}
        else:
            body = {"count": len(self.ratings), "next": None, "results": self.ratings}
        return Response(url, 200, "application/json", json.dumps(body))


def rating(**over):
    r = {"id": 5, "addon": {"id": 1, "slug": "x"}, "body": "It breaks my tabs",
         "created": "2026-10-10T08:00:00Z", "score": 2, "user": {"id": 77},
         "version": {"id": 3, "version": "1.2"}, "reply": None,
         "is_developer_reply": False}
    r.update(over)
    return r


def run_fake(ratings, **kw):
    c = FirefoxAddons(max_items=10, categories=["tabs"], pool_depth=1,
                      addons_per_category=1, now=NOW)
    state = State({})
    return list(c.fetch(FakeHttp(ratings, **kw), state)), state


def test_fake_item_mapping():
    items, state = run_fake([rating(id=6, created="2026-10-11T00:00:00Z"), rating()])
    assert [it.source_id for it in items] == ["5", "6"]  # oldest first
    it = items[0]
    assert it.title == "X 1.2" and it.author == "77" and it.metrics == {"score": 2}
    assert it.created_at == "2026-10-10T08:00:00+00:00"
    assert state.get("since:1") == "2026-10-11T00:00:00+00:00|6"


def test_developer_replies_and_empty_bodies_skipped():
    items, state = run_fake([rating(id=7, is_developer_reply=True), rating(id=6, body=" "),
                             rating(id=5)])
    assert [it.source_id for it in items] == ["5"]
    assert state.get("since:1").endswith("|7")


def test_translated_name_fallback():
    items, _ = run_fake([rating(version=None)],
                        name={"en-US": None, "de": "Tabs", "_default": "de"})
    assert items[0].title == "Tabs" and items[0].extra["addon_version"] is None


@pytest.mark.parametrize("broken", [
    rating(created="2026-10-10T08:00:00"),          # naive timestamp
    {k: v for k, v in rating().items() if k != "body"},
    rating(score=5),                                # score filter ignored
    rating(addon={"id": 2, "slug": "y"}),           # addon filter ignored
])
def test_schema_drift_raises(broken):
    with pytest.raises(SchemaDrift):
        run_fake([broken])


def test_every_search_empty_is_schema_drift():
    with pytest.raises(SchemaDrift):
        run_fake([], results=False)
