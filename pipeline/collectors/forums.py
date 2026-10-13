"""Topic starts from approved forums, read through their RSS or Atom feeds.

Forums are configuration, not code: each one is an entry in forums.toml, approved by
Edgar (SPEC stage 1). One parser covers the common forum software, all of which publish
feeds: Discourse (/latest.rss, /c/<category>.rss), XenForo (/forums/-/index.rss),
phpBB (/feed.php, /app.php/feed), and vBulletin (external.php?type=RSS2).

Each forum carries its own licence and tos_class, stored per item. Only entries with an
`approved` date run, and restricted ones never run. Http checks robots.txt for every
feed URL, so a forum that later blocks us ends the run with status 'blocked'.

Feeds hold a fixed window of recent topics (often 20-50), so a busy forum can outrun a
weekly run; the per-forum metrics show how often a run consumes the whole window.

Cursor per forum: since:<id> = "UTC ISO|guid" of the newest topic yielded. Topics are
yielded oldest first and the cursor is set before each yield. (timestamp, guid) order
keeps ties at a budget cut from being lost.
"""

import html
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import defusedxml.ElementTree as ET

from pipeline.collectors.base import Collector, Item, SchemaDrift, State
from pipeline.http import Http

CONFIG = Path(__file__).with_name("forums.toml")

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "atom": "http://www.w3.org/2005/Atom",
}
TOS_CLASSES = ("clean", "gray", "restricted")


@dataclass(frozen=True)
class Forum:
    id: str
    name: str
    feed: str
    lang: str | None
    country: str | None
    segment: str
    license: str
    tos_class: str
    approved: str | None


def load_forums(path: Path = CONFIG) -> list[Forum]:
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    forums = []
    for f in data.get("forum", []):
        missing = [k for k in ("id", "name", "feed", "segment", "license", "tos_class") if k not in f]
        if missing:
            raise ValueError(f"forums.toml: entry {f.get('id', '?')} missing {missing}")
        if f["tos_class"] not in TOS_CLASSES:
            raise ValueError(f"forums.toml: {f['id']}: bad tos_class {f['tos_class']!r}")
        forums.append(Forum(f["id"], f["name"], f["feed"], f.get("lang"), f.get("country"),
                            f["segment"], f["license"], f["tos_class"], f.get("approved") or None))
    ids = [f.id for f in forums]
    if len(ids) != len(set(ids)):
        raise ValueError("forums.toml: duplicate ids")
    return forums


def _utc(dt: datetime, raw: str) -> datetime:
    if dt.tzinfo is None:
        raise SchemaDrift(f"forums: date without offset: {raw!r}")
    return dt.astimezone(timezone.utc)


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


@dataclass
class Entry:
    guid: str
    title: str
    link: str | None
    body: str
    author: str | None
    published: datetime


def parse_feed(xml: str, where: str) -> list[Entry]:
    """Parse RSS 2.0 or Atom into entries. Raises SchemaDrift on anything else."""
    try:
        root = ET.fromstring(xml.encode("utf-8"))
    except ET.ParseError as e:
        raise SchemaDrift(f"{where}: not XML ({e})") from e
    entries: list[Entry] = []
    if root.tag == "rss":
        channel = root.find("channel")
        if channel is None:
            raise SchemaDrift(f"{where}: rss without channel")
        for it in channel.findall("item"):
            guid = _text(it.find("guid")) or _text(it.find("link"))
            raw_date = _text(it.find("pubDate"))
            if not guid or not raw_date:
                raise SchemaDrift(f"{where}: item missing guid/link or pubDate")
            try:
                published = _utc(parsedate_to_datetime(raw_date), raw_date)
            except (TypeError, ValueError) as e:
                raise SchemaDrift(f"{where}: bad pubDate {raw_date!r}") from e
            body = _text(it.find("content:encoded", NS)) or _text(it.find("description"))
            author = _text(it.find("dc:creator", NS)) or _text(it.find("author")) or None
            entries.append(Entry(guid, html.unescape(_text(it.find("title"))),
                                 _text(it.find("link")) or None, body, author, published))
    elif root.tag == f"{{{NS['atom']}}}feed":
        for it in root.findall("atom:entry", NS):
            guid = _text(it.find("atom:id", NS))
            raw_date = _text(it.find("atom:published", NS)) or _text(it.find("atom:updated", NS))
            if not guid or not raw_date:
                raise SchemaDrift(f"{where}: entry missing id or date")
            try:
                published = _utc(datetime.fromisoformat(raw_date), raw_date)
            except ValueError as e:
                raise SchemaDrift(f"{where}: bad date {raw_date!r}") from e
            link = None
            for ln in it.findall("atom:link", NS):
                if ln.get("rel", "alternate") == "alternate":
                    link = ln.get("href")
                    break
            body = _text(it.find("atom:content", NS)) or _text(it.find("atom:summary", NS))
            author = _text(it.find("atom:author/atom:name", NS)) or None
            entries.append(Entry(guid, html.unescape(_text(it.find("atom:title", NS))),
                                 link, body, author, published))
    else:
        raise SchemaDrift(f"{where}: unknown feed root {root.tag!r}")
    return entries


class Forums(Collector):
    name = "forums"
    license = "per forum (see forums.toml)"
    tos_class = "gray"          # class default; each item carries its forum's own class
    regions = ["GLOBAL"]
    min_interval = 1.0

    def __init__(self, max_items: int = 500, forums: list[Forum] | None = None):
        super().__init__(max_items)
        self.forums = forums if forums is not None else load_forums()

    def fetch(self, http: Http, state: State) -> Iterator[Item]:
        active = [f for f in self.forums if f.approved and f.tos_class != "restricted"]
        remaining = self.max_items
        for n, forum in enumerate(active):
            share = remaining // (len(active) - n)
            if share <= 0:
                continue
            got = 0
            for item in self._forum(http, state, forum, share):
                got += 1
                yield item
            remaining -= got

    def _forum(self, http: Http, state: State, forum: Forum, share: int) -> Iterator[Item]:
        resp = http.get(forum.feed)
        resp.raise_for_status()
        entries = parse_feed(resp.text, f"forums:{forum.id}")
        key = f"since:{forum.id}"
        cur = state.get(key)
        cursor = None
        if cur:
            ts, guid = cur.split("|", 1)
            cursor = (datetime.fromisoformat(ts), guid)
        fresh = sorted((e for e in entries
                        if e.body.strip() and (cursor is None or (e.published, e.guid) > cursor)),
                       key=lambda e: (e.published, e.guid))
        # Keep the newest `share`; older overflow is sampled away, as in other collectors.
        for e in fresh[-share:] if share < len(fresh) else fresh:
            state.set(key, f"{e.published.isoformat()}|{e.guid}")
            yield Item(
                source_id=f"{forum.id}:{e.guid}",
                url=e.link,
                title=e.title or None,
                body=e.body,
                # Prefixed so the same username on two forums hashes differently.
                author=f"{forum.id}:{e.author}" if e.author else None,
                created_at=e.published.isoformat(),
                lang=forum.lang,
                country=forum.country,
                extra={"forum": forum.id, "segment": forum.segment, "html": True,
                       "feed_window": len(entries), "window_all_new": len(fresh) == len(entries)},
                license=forum.license,
                tos_class=forum.tos_class,
            )
