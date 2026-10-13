"""Replay tests for the HN collector. Re-record with:
SIG_HTTP=record uv run pytest tests/collectors/test_hn.py
"""

import os

from pipeline.collectors.base import State
from pipeline.collectors.hn import HackerNews
from pipeline.http import Http

# Fixed cursor so recorded request params match on replay.
SINCE = "1759708800"  # 2025-10-06


def fetch(max_items=20):
    http = Http("hn", min_interval=0, mode=os.environ.get("SIG_HTTP", "replay"))
    state = State({"since": SINCE})
    try:
        return list(HackerNews(max_items=max_items).fetch(http, state)), state
    finally:
        http.close()


def test_items_have_required_fields():
    items, _ = fetch()
    assert items
    for it in items:
        assert it.source_id and it.body.strip() and it.url.startswith("https://news.ycombinator.com/")
        assert it.created_at and it.lang == "en" and it.author


def test_no_duplicate_ids_and_cap_respected():
    items, _ = fetch(max_items=20)
    ids = [it.source_id for it in items]
    assert len(ids) == len(set(ids)) and len(ids) <= 20


def test_cursor_advances():
    _, state = fetch()
    assert int(state.get("since")) > int(SINCE)
