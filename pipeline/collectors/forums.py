"""Topic starts from approved forums, read through their RSS or Atom feeds.

Forums are configuration, not code: each one is an entry in forums.toml, approved by
Edgar (SPEC stage 1). One parser covers the common forum software, all of which publish
feeds: Discourse (/latest.rss, /c/<category>.rss), XenForo (/forums/-/index.rss),
phpBB (/feed.php, /app.php/feed), and vBulletin (external.php?type=RSS2).

Each forum carries its own licence and tos_class, stored per item. Only entries with an
`approved` date run, and restricted ones never run. Http checks robots.txt for every
feed URL. Each forum is guarded: one forum's bot wall, block, or outage becomes a warning
(run status 'partial', with a per-forum failure streak); the run fails only when every
forum fails.

Feed order: XenForo and WoltLab sort by last post and date items by it ('active'), so
created_at is left empty and the feed date goes to extra.feed_date. vBulletin and phpBB
topic feeds list new threads ('new'), so their date is the creation date.

Bodies drop quoted posts and phpBB's footer, both of which name other users.

Feeds hold a fixed window of recent topics (often 20-50), so a busy forum can outrun a
weekly run; the per-forum metrics show how often a run consumes the whole window.

Cursor per forum: since:<id> = "UTC ISO|guid" of the newest topic yielded. Topics are
yielded oldest first and the cursor is set before each yield. (timestamp, guid) order
keeps ties at a budget cut from being lost.
"""

import html
import re
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
    order: str = "active"   # 'active': feed sorted by last post, dates = last activity; 'new'


def load_forums(path: Path = CONFIG) -> list[Forum]:
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    forums = []
    for f in data.get("forum", []):
        missing = [k for k in ("id", "name", "feed", "segment", "license", "tos_class") if k not in f]
        if missing:
            raise ValueError(f"forums.toml: entry {f.get('id', '?')} missing {missing}")
        if f["tos_class"] not in TOS_CLASSES:
            raise ValueError(f"forums.toml: {f['id']}: bad tos_class {f['tos_class']!r}")
        order = f.get("order", "active")
        if order not in ("active", "new"):
            raise ValueError(f"forums.toml: {f['id']}: order must be 'active' or 'new'")
        forums.append(Forum(f["id"], f["name"], f["feed"], f.get("lang"), f.get("country"),
                            f["segment"], f["license"], f["tos_class"], f.get("approved") or None,
                            order))
    ids = [f.id for f in forums]
    if len(ids) != len(set(ids)):
        raise ValueError("forums.toml: duplicate ids")
    return forums


def _utc(dt: datetime, raw: str) -> datetime:
    if dt.tzinfo is None:
        raise SchemaDrift(f"forums: date without offset: {raw!r}")
    return dt.astimezone(timezone.utc)


def _strip_sid(url: str) -> str:
    """phpBB adds a per-visit session id (sid=...) to links; without stripping, the same
    post gets a new guid on every fetch."""
    url = re.sub(r"[?&]sid=[0-9a-f]+(?=#|$)", "", url)            # last parameter
    return re.sub(r"([?&])sid=[0-9a-f]+&", lambda m: m.group(1), url)  # middle parameter


# Text that names other people: quoted posts ("<name> said:") and phpBB's per-post
# footer ("Statistik: Verfasst von <name>"). Stripped so no username reaches the body.
_QUOTE = re.compile(r"<blockquote\b.*?</blockquote>", re.S | re.I)
_PHPBB_FOOTER = re.compile(r"<p>\s*(?:Statistik|Statistics):.*?</p>\s*(?:<hr\s*/?>)?", re.S | re.I)


def clean_body(body: str) -> str:
    return _PHPBB_FOOTER.sub("", _QUOTE.sub("", body)).strip()


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
    # The text is already decoded (pipeline.http honours the XML declaration), so drop the
    # declaration: re-encoding while it still names another charset garbles accents.
    xml = re.sub(r"^\s*<\?xml[^>]*\?>", "", xml, count=1)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise SchemaDrift(f"{where}: not XML ({e})") from e
    entries: list[Entry] = []
    if root.tag == "rss":
        channel = root.find("channel")
        if channel is None:
            raise SchemaDrift(f"{where}: rss without channel")
        for it in channel.findall("item"):
            guid = _strip_sid(_text(it.find("guid")) or _text(it.find("link")))
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
                                 _strip_sid(_text(it.find("link"))) or None, body, author,
                                 published))
    elif root.tag == f"{{{NS['atom']}}}feed":
        for it in root.findall("atom:entry", NS):
            guid = _strip_sid(_text(it.find("atom:id", NS)))
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
                    link = _strip_sid(ln.get("href") or "") or None
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
            # One forum's bot wall or outage must not cost the others their run.
            for item in self.guarded(forum.id, self._forum(http, state, forum, share)):
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
                        if clean_body(e.body) and (cursor is None or (e.published, e.guid) > cursor)),
                       key=lambda e: (e.published, e.guid))
        # Keep the newest `share`; older overflow is sampled away, as in other collectors.
        for e in fresh[-share:] if share < len(fresh) else fresh:
            state.set(key, f"{e.published.isoformat()}|{e.guid}")
            yield Item(
                source_id=f"{forum.id}:{e.guid}",
                url=e.link,
                title=e.title or None,
                body=clean_body(e.body),
                # Prefixed so the same username on two forums hashes differently.
                author=f"{forum.id}:{e.author}" if e.author else None,
                # In 'active' feeds the date is the thread's last post, not its creation.
                created_at=e.published.isoformat() if forum.order == "new" else None,
                lang=forum.lang,
                country=forum.country,
                extra={"forum": forum.id, "segment": forum.segment, "html": True,
                       "feed_order": forum.order, "feed_date": e.published.isoformat(),
                       "feed_window": len(entries), "window_all_new": len(fresh) == len(entries)},
                license=forum.license,
                tos_class=forum.tos_class,
            )
