"""Apple App Store customer reviews rated 3 stars or lower, across US, EEA, and UK storefronts.

Endpoints on https://itunes.apple.com (no key, JSON despite the "rss" path):
  charts   /{cc}/rss/topfreeapplications/limit={n}/genre={id}/json
  reviews  /{cc}/rss/customerreviews/page={p}/id={app}/sortby=mostrecent/json
The reviews feed serves the newest 500 reviews per app per storefront (10 pages of 50).
The newer chart feed at rss.marketingtools.apple.com ignores genre and timed out in tests on
2026-10-13, so app selection uses the legacy chart feed, which honours `genre`.

App selection: each run reads the top-free chart for every (country, genre) and takes
APPS_PER_GENRE apps from it, rotating through the top CHART_DEPTH across runs, so the
weekly sample moves past the same few incumbents. Only reviews rated 1-3 are kept: unhappy
reviews name what fails, and 4-5 star reviews rarely do.

Budget: max_items is shared round-robin across (country, app) pairs, so a capped run still
spreads over every storefront. A pair that does not finish within the budget leaves its
older unread reviews behind; the feed holds only the newest 500 anyway, so the collector
samples rather than archives.

Flaky origin: on 2026-10-13 most review URLs returned HTTP 200 with no `entry` key, and
Apple's server cached that empty answer per URL for hours. Equivalent spellings of the same
URL are independent draws, so each page tries URL_VARIANTS in turn. A storefront where an
app is not sold also returns no entries; the collector cannot tell the two apart. A run
where every pair comes back empty raises SchemaDrift.

Licence: none granted. Apple publishes these feeds for embedding lists in websites
(https://performance-partners.apple.com/tools) but attaches no terms to the review feed.
Apple's site terms forbid robots and spiders and the copying or republishing of content
without written consent (https://www.apple.com/legal/internet-services/terms/site.html),
and https://itunes.apple.com/robots.txt disallows `/*/rss/*` for every user agent, which
pipeline.robots enforces: a live run ends with status 'blocked'. Hence tos_class
'restricted': the runner skips it unless named with --only, and running it at all needs
Edgar's decision plus a change to the robots policy for this source.

Rate: Apple documents ~20 calls/minute for its Search API and nothing for these feeds;
min_interval keeps us at that pace. The feed carries no language field and the storefront
does not imply one (German storefronts carry English reviews), so lang stays None.
"""

import math
from collections.abc import Iterator
from datetime import datetime, timezone
from itertools import islice

from pipeline.collectors.base import Collector, Item, SchemaDrift, State, require
from pipeline.http import Http

BASE = "https://itunes.apple.com"

# US, plus the eight EEA/UK storefronts research report 05 recommends (the largest
# markets in each region), plus Ireland, the EU's English-language storefront.
COUNTRIES = ["us", "gb", "ie", "de", "fr", "es", "it", "nl", "pl", "se"]

# Genres whose top apps serve businesses or consumers with money, work, health, travel, and
# food: banks, payroll, patient portals, airlines, delivery. Utilities, Lifestyle,
# Education, and Health & Fitness stay out to keep a run small; add one if the sample
# shows a gap.
GENRES = {
    "6000": "Business",
    "6015": "Finance",
    "6007": "Productivity",
    "6020": "Medical",
    "6003": "Travel",
    "6023": "Food & Drink",
}
CHART_DEPTH = 10      # rotate through the top 10 of each chart
APPS_PER_GENRE = 2    # per run: 10 countries x 6 genres x 2 = 120 pairs
MAX_RATING = 3
PAGES = 10            # Apple serves pages 1-10, 50 reviews each
PAGE_SIZE = 50

# Equivalent spellings of the reviews URL; Apple caches each one separately.
URL_VARIANTS = [
    lambda cc, app, p: (f"{BASE}/{cc}/rss/customerreviews/page={p}/id={app}/sortby=mostrecent/json",
                        None),
    lambda cc, app, p: (f"{BASE}/{cc}/rss/customerreviews/id={app}/sortby=mostrecent/page={p}/json",
                        None),
    lambda cc, app, p: (f"{BASE}/rss/customerreviews/page={p}/id={app}/sortby=mostrecent/json",
                        {"cc": cc}),
    lambda cc, app, p: (f"{BASE}/{cc}/rss/customerreviews/id={app}/page={p}/sortby=mostrecent/json",
                        None),
]


def _entries(feed: dict) -> list[dict]:
    """The feed omits `entry` when empty and gives a bare object when it holds one."""
    entry = feed.get("entry")
    if entry is None:
        return []
    return entry if isinstance(entry, list) else [entry]


def _label(obj: dict, key: str, where: str) -> str:
    """Apple wraps every value as {"label": ...}."""
    require(obj[key], ["label"], f"{where} {key}")
    return obj[key]["label"]


def _utc(stamp: str) -> datetime:
    dt = datetime.fromisoformat(stamp)
    if dt.tzinfo is None:  # astimezone would silently assume the machine's local zone
        raise SchemaDrift(f"appstore: timestamp without offset: {stamp!r}")
    return dt.astimezone(timezone.utc)


class AppStore(Collector):
    name = "appstore"
    license = "Apple RSS feeds (no licence granted)"
    tos_class = "restricted"
    regions = [c.upper() for c in COUNTRIES]
    min_interval = 3.0

    def __init__(self, max_items: int = 500, countries: list[str] | None = None,
                 genres: dict[str, str] | None = None, apps_per_genre: int = APPS_PER_GENRE,
                 chart_depth: int = CHART_DEPTH):
        super().__init__(max_items)
        self.countries = countries or COUNTRIES
        self.genres = genres or GENRES
        self.apps_per_genre = apps_per_genre
        self.chart_depth = chart_depth

    def fetch(self, http: Http, state: State) -> Iterator[Item]:
        http.check_robots(f"{BASE}/us/rss/customerreviews/page=1/id=1/sortby=mostrecent/json")
        # State is written eagerly: the runner stops pulling at max_items, so code after
        # the last yield may never run.
        rotation = int(state.get("rotation", "0"))
        state.set("rotation", str(rotation + 1))
        pairs = self._pick_apps(http, rotation)

        reached: set[str] = set()   # pairs where some page returned entries
        streams = [self._reviews(http, state, app, reached) for app in pairs]
        remaining = self.max_items
        while streams and remaining > 0:
            share = max(1, math.ceil(remaining / len(streams)))
            still = []
            for stream in streams:
                quota = min(share, remaining)
                took = 0
                for item in islice(stream, quota):
                    took += 1
                    yield item
                remaining -= took
                if took == quota:
                    still.append(stream)   # filled its quota, so it may hold more
                if remaining <= 0:
                    break
            streams = still

        if len(pairs) >= 3 and not reached:
            raise SchemaDrift(f"appstore: all {len(pairs)} review feeds came back empty")

    def _pick_apps(self, http: Http, rotation: int) -> list[dict]:
        """Chart apps for this run, ordered rank-major so any cap spreads over countries."""
        slices = max(1, self.chart_depth // self.apps_per_genre)
        start = (rotation % slices) * self.apps_per_genre
        charts: dict[tuple[str, str], list[dict]] = {}
        any_entries = False
        for gid in self.genres:
            for cc in self.countries:
                url = (f"{BASE}/{cc}/rss/topfreeapplications/limit={self.chart_depth}"
                       f"/genre={gid}/json")
                resp = http.get(url)
                resp.raise_for_status()
                data = resp.json()
                require(data, ["feed"], "appstore chart")
                apps = []
                for e in _entries(data["feed"]):
                    w = "appstore chart entry"
                    require(e, ["id", "im:name"], w)
                    require(e["id"], ["label", "attributes"], f"{w} id")
                    require(e["id"]["attributes"], ["im:id"], f"{w} id attributes")
                    apps.append({
                        "cc": cc, "genre": self.genres[gid],
                        "app_id": e["id"]["attributes"]["im:id"],
                        "app_name": _label(e, "im:name", w),
                        "url": e["id"]["label"].split("?")[0],
                    })
                any_entries = any_entries or bool(apps)
                charts[(gid, cc)] = apps[start:start + self.apps_per_genre]
        if charts and not any_entries:
            raise SchemaDrift("appstore: every top chart came back empty")
        pairs, seen = [], set()
        for rank in range(self.apps_per_genre):
            for gid in self.genres:
                for cc in self.countries:
                    apps = charts[(gid, cc)]
                    if rank < len(apps) and (cc, apps[rank]["app_id"]) not in seen:
                        seen.add((cc, apps[rank]["app_id"]))
                        pairs.append(apps[rank])
        return pairs

    def _page(self, http: Http, cc: str, app_id: str, page: int) -> list[dict]:
        for variant in URL_VARIANTS:
            url, params = variant(cc, app_id, page)
            resp = http.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            require(data, ["feed"], "appstore reviews")
            entries = _entries(data["feed"])
            if entries:
                return entries
        return []

    def _reviews(self, http: Http, state: State, app: dict, reached: set[str]) -> Iterator[Item]:
        """Low-rated reviews of one app in one storefront, newest first, down to the cursor.

        The cursor is the newest `updated` stamp seen, at any rating. An edited old review
        moves to the top with a new stamp; its source_id is unchanged, so the runner's
        dedup ignores it.
        """
        cc, app_id = app["cc"], app["app_id"]
        key = f"since:{cc}:{app_id}"
        since = state.get(key)
        since_dt = _utc(since) if since else None
        newest = since_dt
        for page in range(1, PAGES + 1):
            entries = self._page(http, cc, app_id, page)
            if not entries:
                return
            reached.add(key)
            for e in entries:
                w = "appstore review"
                require(e, ["id", "author", "updated", "im:rating", "title", "content",
                            "im:version"], w)
                require(e["author"], ["name", "uri"], f"{w} author")
                storefront = _label(e["author"], "uri", w).split("/")[3]
                if storefront != cc:
                    raise SchemaDrift(f"appstore: asked for {cc}, got a {storefront} review")
                updated = _utc(_label(e, "updated", w))
                if newest is None or updated > newest:
                    newest = updated
                    state.set(key, newest.isoformat())
                if since_dt and updated <= since_dt:
                    return
                rating = int(_label(e, "im:rating", w))
                body = _label(e, "content", w)
                if rating > MAX_RATING or not body.strip():
                    continue
                metrics = {"rating": rating}
                for field, name in (("im:voteSum", "vote_sum"), ("im:voteCount", "vote_count")):
                    if field in e:
                        metrics[name] = int(_label(e, field, w))
                yield Item(
                    source_id=f"{cc}:{app_id}:{_label(e, 'id', w)}",
                    url=app["url"],
                    title=_label(e, "title", w),
                    body=body,
                    author=_label(e["author"], "name", w),
                    created_at=updated.isoformat(),
                    lang=None,
                    country=cc.upper(),
                    metrics=metrics,
                    extra={"app_id": app_id, "app_name": app["app_name"],
                           "genre": app["genre"], "app_version": _label(e, "im:version", w)},
                )
            if len(entries) < PAGE_SIZE:
                return
