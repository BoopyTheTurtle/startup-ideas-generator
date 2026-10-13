"""Replay tests for the WordPress.org support-forum collector. Re-record with:
SIG_HTTP=record uv run pytest tests/collectors/test_wordpress.py

The recorded fixtures hold verbatim forum posts, which their authors own, so they may be
kept local; the replay tests skip on a clone without them. The fake-HTTP tests always run.
"""

import os
import re

import pytest

from pipeline.collectors.base import SchemaDrift, State
from pipeline.collectors.wordpress import FEED, INFO, QUERY, WordPressSupport
from pipeline.http import FIXTURES as ALL_FIXTURES, Http, Response

# A fixed plan (no popular query) and fixed cursors so replay is deterministic.
PLUGINS = ["sliced-invoices", "easy-appointments", "cookie-notice"]
SINCE = "2026-01-01T00:00:00+00:00|"
FIXTURES = ALL_FIXTURES / "wordpress"


def cursors():
    return {f"since:{slug}": SINCE for slug in PLUGINS}


def fetch(max_items=30, values=None, take=None):
    mode = os.environ.get("SIG_HTTP", "replay")
    if mode == "replay" and not any(FIXTURES.glob("*.json")):
        pytest.skip("WordPress fixtures are local-only; record them to run this test")
    http = Http("wordpress", min_interval=0, mode=mode)
    state = State(values if values is not None else {**cursors(), "rotation": "0"})
    try:
        gen = WordPressSupport(max_items=max_items, plugins=PLUGINS,
                               popular_pages=0).fetch(http, state)
        items = []
        for it in gen:
            items.append(it)
            if take and len(items) >= take:
                gen.close()
                break
        return items, state
    finally:
        http.close()


def test_items_have_required_fields():
    items, _ = fetch()
    assert items
    for it in items:
        assert re.fullmatch(r"[^/\s]+", it.source_id)
        assert it.url == f"https://wordpress.org/support/topic/{it.source_id}/"
        assert it.title and it.body.strip() and it.author
        assert it.created_at.endswith("+00:00") and it.created_at > SINCE.rstrip("|")
        assert it.lang == "en" and it.country is None
        assert it.metrics["replies"] >= 0 and "Replies:" not in it.body[:40]
        assert it.extra["plugin_slug"] in PLUGINS and it.extra["plugin_name"]
        assert isinstance(it.extra["active_installs"], int) and it.extra["html"] is True


def test_no_duplicate_ids_cap_respected_and_spread():
    items, _ = fetch(max_items=9)
    ids = [it.source_id for it in items]
    assert len(ids) == len(set(ids)) and len(ids) <= 9
    assert {it.extra["plugin_slug"] for it in items} == set(PLUGINS)


def test_cursors_advance_and_second_run_finds_nothing():
    items, state = fetch()
    assert state.get("rotation") == "0"  # 3 plugins, 3 per run: back to the start
    saved = {k: v for k, v in state.values.items() if k.startswith("since:")}
    for slug in PLUGINS:
        newest = max(it.created_at for it in items if it.extra["plugin_slug"] == slug)
        assert saved[f"since:{slug}"].startswith(newest + "|")
    again, _ = fetch(values={**saved, "rotation": "0"})
    assert again == []


def test_cut_short_run_resumes_at_last_item():
    items, state = fetch(take=2)
    first = items[0].extra["plugin_slug"]
    assert {it.extra["plugin_slug"] for it in items} == {first}
    assert items[0].created_at < items[1].created_at  # oldest first
    assert state.get(f"since:{first}").startswith(items[-1].created_at + "|")


def test_popular_pool():
    mode = os.environ.get("SIG_HTTP", "replay")
    if mode == "replay" and not any(FIXTURES.glob("*.json")):
        pytest.skip("WordPress fixtures are local-only; record them to run this test")
    http = Http("wordpress", min_interval=0, mode=mode)
    try:
        slugs = WordPressSupport(popular_pages=1)._popular(http)
    finally:
        http.close()
    assert len(slugs) == 20 and "woocommerce" in slugs


# --- Fake HTTP: ties, rotation, removed plugins, and schema drift ---------------------

def rss(items: str, name: str = "Demo") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>'
        f"<title>WordPress.org Forums &#187; [{name}] Support</title>"
        "<link>https://wordpress.org/support/plugin/demo/feed/</link>"
        f"{items}</channel></rss>"
    )


def topic(slug: str, date: str = "Tue, 13 Oct 2026 05:25:14 +0000", replies: int = 2,
          body: str = "<p>It broke &amp; I need help.</p>") -> str:
    url = f"https://wordpress.org/support/topic/{slug}/"
    return (f"<item><guid>{url}</guid><title>Title {slug}</title><link>{url}</link>"
            f"<pubDate>{date}</pubDate><dc:creator>someone</dc:creator>"
            f"<description><![CDATA[ <p>\n Replies: {replies}\t</p>\n{body} ]]></description>"
            "</item>")


class FakeHttp:
    def __init__(self, routes: dict[str, tuple[int, str]]):
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url, params=None, headers=None):
        self.calls.append(url)
        status, text = self.routes.get(url, (404, ""))
        return Response(url, status, "application/rss+xml", text)

    def check_robots(self, url):
        pass


def fake(feed: str, slug: str = "demo") -> FakeHttp:
    return FakeHttp({
        FEED.format(slug=slug): (200, feed),
        INFO.format(slug=slug): (200, '{"name": "Demo &amp; Co", "slug": "demo",'
                                      ' "active_installs": 1000}'),
    })


def run(http, values=None, max_items=10, take=None, plugins=("demo",), per_run=35):
    state = State(values or {"since:demo": "2026-10-01T00:00:00+00:00|"})
    gen = WordPressSupport(max_items=max_items, plugins=list(plugins), popular_pages=0,
                           plugins_per_run=per_run).fetch(http, state)
    items = []
    for it in gen:
        items.append(it)
        if take and len(items) >= take:
            gen.close()
            break
    return items, state


def test_item_mapping():
    items, state = run(fake(rss(topic("b-topic"))))
    [it] = items
    assert it.source_id == "b-topic" and it.title == "Title b-topic"
    assert it.body == "<p>It broke &amp; I need help.</p>"  # HTML kept as-is
    assert it.created_at == "2026-10-13T05:25:14+00:00" and it.metrics == {"replies": 2}
    assert it.extra == {"plugin_slug": "demo", "plugin_name": "Demo & Co",
                        "active_installs": 1000, "html": True}
    assert state.get("since:demo") == (
        "2026-10-13T05:25:14+00:00|https://wordpress.org/support/topic/b-topic/")


def test_equal_timestamps_survive_a_cut():
    http = fake(rss(topic("b-topic") + topic("a-topic")))
    first, state = run(http, take=1)
    assert [it.source_id for it in first] == ["a-topic"]
    second, _ = run(http, values=state.values)
    assert [it.source_id for it in second] == ["b-topic"]


def test_share_keeps_newest_and_no_info_call_without_new_topics():
    feed = rss(topic("new", "Tue, 13 Oct 2026 05:00:00 +0000")
               + topic("mid", "Mon, 12 Oct 2026 05:00:00 +0000")
               + topic("old", "Sun, 11 Oct 2026 05:00:00 +0000"))
    items, state = run(fake(feed), max_items=2)
    assert [it.source_id for it in items] == ["mid", "new"]
    http = fake(feed)
    assert run(http, values=state.values)[0] == []
    assert http.calls == [FEED.format(slug="demo")]


def test_rotation_and_removed_plugin():
    http = fake(rss(topic("t")))  # "gone" has no route: its feed returns 404
    items, state = run(http, values={"rotation": "1",
                                     "since:demo": "2026-10-01T00:00:00+00:00|"},
                       plugins=("x", "gone", "demo"), per_run=2)
    assert state.get("rotation") == "0"
    assert http.calls[0] == FEED.format(slug="gone") and len(items) == 1


@pytest.mark.parametrize("feed", [
    "<html>not a feed</html>",
    "<rss><channel><title>t</title><link>l</link><item><guid>g</guid></item></channel></rss>",
    rss(topic("t", date="Tue, 13 Oct 2026 05:25:14 -0000")),  # naive
    rss(topic("t", date="yesterday")),
    rss(topic("t").replace("Replies:", "Antworten:")),
    rss(topic("t").replace("/support/topic/", "/support/forum/")),
])
def test_schema_drift_in_one_plugin_becomes_a_warning(feed):
    # Each plugin is guarded; drift in one becomes a warning instead of failing the run.
    c = WordPressSupport(max_items=10, plugins=["demo"], popular_pages=0)
    state = State({"since:demo": "2026-10-01T00:00:00+00:00|"})
    assert list(c.fetch(fake(feed), state)) == []
    assert c.units_failed == ["demo"] and "SchemaDrift" in c.warnings[0]


def test_popular_schema_drift():
    http = FakeHttp({QUERY: (200, '{"plugins": "elementor"}')})
    with pytest.raises(SchemaDrift):
        list(WordPressSupport(popular_pages=1).fetch(http, State({})))
