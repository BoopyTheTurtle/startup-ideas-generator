"""Offline tests for the generic forum collector, using synthetic feeds."""

import pytest

from pipeline.collectors.base import SchemaDrift, State
from pipeline.collectors.forums import Forum, Forums, load_forums, parse_feed
from pipeline.http import Response

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel><title>Trades</title>
{items}
</channel></rss>"""

ITEM = """<item><title>{title}</title><link>https://f.example/t/{g}</link>
<guid>https://f.example/t/{g}</guid><pubDate>{date}</pubDate>
<dc:creator>{who}</dc:creator><description>&lt;p&gt;{body}&lt;/p&gt;</description></item>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>X</title>
<entry><id>tag:x,1</id><title>Quote tool &amp; invoices</title>
<link rel="alternate" href="https://x.example/threads/1"/>
<published>2026-10-10T08:00:00+02:00</published>
<author><name>bob</name></author><content type="html">&lt;p&gt;We still invoice by hand&lt;/p&gt;</content>
</entry></feed>"""


def rss(*items):
    return RSS.format(items="".join(ITEM.format(**i) for i in items))


def it(g, date, title="Q", who="amy", body="How do you track jobs?"):
    return {"g": g, "date": date, "title": title, "who": who, "body": body}


FORUM = Forum("trades", "Trades Forum", "https://f.example/latest.rss", "en", "GB",
              "trades", "posts (c) authors", "gray", "2026-10-13", "new")


class FakeHttp:
    mode = "replay"

    def __init__(self, feeds):
        self.feeds, self.calls = feeds, []

    def get(self, url, params=None, headers=None):
        self.calls.append(url)
        return Response(url, 200, "application/rss+xml", self.feeds[url])


def test_rss_maps_fields_and_overrides_terms():
    feed = rss(it("2", "Tue, 13 Oct 2026 09:00:00 +0000"), it("1", "Mon, 12 Oct 2026 09:00:00 +0000"))
    items = list(Forums(forums=[FORUM]).fetch(FakeHttp({FORUM.feed: feed}), State({})))
    assert [i.source_id for i in items] == ["trades:https://f.example/t/1", "trades:https://f.example/t/2"]
    first = items[0]
    assert first.author == "trades:amy" and first.lang == "en" and first.country == "GB"
    assert first.tos_class == "gray" and first.license == "posts (c) authors"
    assert first.body == "<p>How do you track jobs?</p>"
    assert first.created_at == "2026-10-12T09:00:00+00:00"


def test_cursor_skips_seen_and_keeps_ties():
    same = "Mon, 12 Oct 2026 09:00:00 +0000"
    feed = rss(it("a", same), it("b", same), it("c", same))
    http, state = FakeHttp({FORUM.feed: feed}), State({})
    first = list(Forums(max_items=2, forums=[FORUM]).fetch(http, state))
    second = list(Forums(max_items=2, forums=[FORUM]).fetch(http, state))
    # A cut of 2 keeps the newest two by (date, guid); the oldest is sampled away.
    assert [i.source_id[-1] for i in first] == ["b", "c"]
    assert second == []


def test_unapproved_and_restricted_forums_never_fetched():
    unapproved = Forum(**{**FORUM.__dict__, "id": "u", "feed": "https://u/x", "approved": None})
    restricted = Forum(**{**FORUM.__dict__, "id": "r", "feed": "https://r/x", "tos_class": "restricted"})
    http = FakeHttp({})
    assert list(Forums(forums=[unapproved, restricted]).fetch(http, State({}))) == []
    assert http.calls == []


def test_budget_shared_across_forums():
    other = Forum(**{**FORUM.__dict__, "id": "b", "feed": "https://b/x"})
    feed = rss(*[it(str(n), f"Mon, 12 Oct 2026 0{n}:00:00 +0000") for n in range(5)])
    items = list(Forums(max_items=4, forums=[FORUM, other]).fetch(
        FakeHttp({FORUM.feed: feed, other.feed: feed}), State({})))
    assert len(items) == 4
    assert {i.extra["forum"] for i in items} == {"trades", "b"}


def test_atom_parses():
    [e] = parse_feed(ATOM, "t")
    assert e.title == "Quote tool & invoices" and e.author == "bob"
    assert e.link == "https://x.example/threads/1"
    assert e.published.isoformat() == "2026-10-10T06:00:00+00:00"


@pytest.mark.parametrize("bad", [
    "not xml",
    "<html><body>blocked</body></html>",
    rss({"g": "1", "date": "", "title": "t", "who": "a", "body": "b"}),
    rss(it("1", "yesterday")),
])
def test_bad_feeds_raise_schema_drift(bad):
    with pytest.raises(SchemaDrift):
        parse_feed(bad, "t")


def test_config_file_loads():
    for f in load_forums():
        assert f.tos_class in ("clean", "gray", "restricted")


def test_strip_phpbb_session_ids():
    from pipeline.collectors.forums import _strip_sid
    assert _strip_sid("https://l.de/viewtopic.php?sid=ab12&t=5") == "https://l.de/viewtopic.php?t=5"
    assert _strip_sid("https://l.de/viewtopic.php?t=5&sid=ab12") == "https://l.de/viewtopic.php?t=5"
    assert _strip_sid("https://l.de/viewtopic.php?t=5&sid=ab12&p=9") == "https://l.de/viewtopic.php?t=5&p=9"


def test_latin1_feed_keeps_accents():
    import httpx

    from pipeline.http import _decode
    body = ('<?xml version="1.0" encoding="ISO-8859-1"?><rss version="2.0"><channel>'
            '<item><title>Chaudière froide</title><guid>g</guid>'
            '<pubDate>Mon, 12 Oct 2026 09:00:00 +0200</pubDate>'
            '<description>radiateurs</description></item></channel></rss>').encode("latin-1")
    r = httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=body)
    [e] = parse_feed(_decode(r), "t")
    assert e.title == "Chaudière froide"


def test_one_broken_forum_does_not_stop_the_rest():
    broken = Forum(**{**FORUM.__dict__, "id": "wall", "feed": "https://wall/x"})
    feed = rss(it("1", "Mon, 12 Oct 2026 09:00:00 +0000"))
    c = Forums(forums=[broken, FORUM])
    items = list(c.fetch(FakeHttp({broken.feed: "<html>challenge</html>", FORUM.feed: feed}),
                         State({})))
    assert [i.extra["forum"] for i in items] == ["trades"]
    assert len(c.warnings) == 1 and c.warnings[0].startswith("wall: SchemaDrift")


def test_active_feeds_leave_created_at_empty():
    active = Forum(**{**FORUM.__dict__, "order": "active"})
    feed = rss(it("1", "Mon, 12 Oct 2026 09:00:00 +0000"))
    [item] = Forums(forums=[active]).fetch(FakeHttp({active.feed: feed}), State({}))
    assert item.created_at is None and item.extra["feed_date"] == "2026-10-12T09:00:00+00:00"


def test_bodies_drop_quotes_and_phpbb_footer():
    from pipeline.collectors.forums import clean_body
    body = ('<blockquote data-quote="alice"><div>alice said:</div>old text</blockquote>'
            '<p>My own problem</p><p>Statistik: Verfasst von <a href="x">bauer hans</a>'
            ' — Di Okt 13</p><hr />')
    assert clean_body(body) == "<p>My own problem</p>"


def test_atom_ids_and_links_lose_phpbb_sids():
    atom = ATOM.replace("tag:x,1", "https://l.de/viewtopic.php?t=1&amp;p=2&amp;sid=abc123#p2").replace(
        "https://x.example/threads/1", "https://l.de/viewtopic.php?t=1&amp;p=2&amp;sid=abc123#p2")
    [e] = parse_feed(atom, "t")
    assert e.guid == e.link == "https://l.de/viewtopic.php?t=1&p=2#p2"
