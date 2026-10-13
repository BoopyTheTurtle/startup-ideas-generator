"""Firefox Add-ons (AMO) ratings scored 1-3 that carry review text.

API: AMO API v5, documented at https://mozilla.github.io/addons-server/topics/api/ (no
key). The docs warn that v5 "can change at any time without warning", so every response
and rating goes through require(). Endpoints, verified live on 2026-10-13:
  search   /api/v5/addons/search/?type=extension&sort=users&category=C&app=firefox
           top extensions in a category by average daily users
  ratings  /api/v5/ratings/rating/?addon=ID&score=1,2,3&filter=without_empty_body
           the latest rating per user, newest `created` first; `score` takes a
           comma-separated list, and `without_empty_body` drops star-only ratings
`lang=en-US` makes translated fields (add-on names) return one language, which keeps
responses small. Pages hold up to 50 results. robots.txt
(https://addons.mozilla.org/robots.txt) allows /api/ for every user agent.

Add-on selection: each run reads the top POOL_DEPTH extensions in every category of
CATEGORIES and takes ADDONS_PER_CATEGORY of them, rotating through the pool across runs
with the `rotation` counter. The categories cover privacy, tab and bookmark management,
downloads, search, shopping, social, news, language, media, and alerts: consumer tools
whose low ratings name a broken workflow. Left out: web-development (HN and Stack
Exchange cover developers), appearance and games-entertainment (little problem signal).
An add-on listed in several categories is taken once, under the first.

Cursors: `since:{addon_id}` holds "created|rating_id" of the newest rating handled. A
visit pages newest first down to the cursor, or to MAX_AGE before now, whichever is
later, and reads at most MAX_PAGES pages. It then yields oldest first and moves the
cursor just before each yield, so a run cut short by max_items resumes where it stopped.
An add-on with more new ratings than MAX_PAGES holds loses the oldest of them, and
ratings older than MAX_AGE are never read: the collector samples rather than archives.
max_items is shared round-robin across the add-ons, as in appstore.

Ratings carry no language field, so lang is None; AMO serves users worldwide, so country
is None too. Developer replies arrive nested under `reply` and are not collected; a
top-level rating marked is_developer_reply is skipped.

Licence and terms, tos_class = gray:
- Ratings are user Submissions under Mozilla's Websites & Communications Terms of Use
  (https://www.mozilla.org/en-US/about/legal/terms/mozilla/, section 4): authors license
  them to Mozilla only. No open licence covers them, so they support private analysis
  but not republishing. Quote sparingly.
- The AMO Policies (https://www.mozilla.org/en-US/about/legal/amo-policies/) add no
  API terms. The Acceptable Use Policy
  (https://www.mozilla.org/en-US/about/legal/acceptable-use/) forbids harvesting
  personally identifiable information, "including account names". The collector passes
  only the numeric user id as `author`, which the runner hashes; it never reads
  `user.name` or `user.username`.
- No term forbids automated access to the public, documented API, and robots.txt
  allows it.
"""

import math
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from itertools import islice

from pipeline.collectors.base import Collector, Item, SchemaDrift, State, require
from pipeline.http import Http

BASE = "https://addons.mozilla.org"
SEARCH = f"{BASE}/api/v5/addons/search/"
RATINGS = f"{BASE}/api/v5/ratings/rating/"
REVIEW_URL = BASE + "/en-US/firefox/addon/{slug}/reviews/{id}/"
LANG = "en-US"

CATEGORIES = [
    "privacy-security",
    "tabs",
    "bookmarks",
    "download-management",
    "search-tools",
    "shopping",
    "social-communication",
    "feeds-news-blogging",
    "language-support",
    "photos-music-videos",
    "alerts-updates",
    "other",
]
POOL_DEPTH = 10           # rotate through the top 10 of each category
ADDONS_PER_CATEGORY = 2   # per run: 12 categories x 2 = 24 add-ons
MAX_SCORE = 3
PAGE_SIZE = 50            # the API maximum
MAX_PAGES = 4
MAX_AGE = timedelta(days=180)


def _utc(stamp: str) -> datetime:
    dt = datetime.fromisoformat(stamp)
    if dt.tzinfo is None:  # astimezone would silently assume the machine's local zone
        raise SchemaDrift(f"firefox_addons: timestamp without offset: {stamp!r}")
    return dt.astimezone(timezone.utc)


def _text(field) -> str | None:
    """A translated field: {"en-US": "..."} or, without en-US, a `_default` fallback."""
    if field is None or isinstance(field, str):
        return field
    if not isinstance(field, dict):
        raise SchemaDrift(f"firefox_addons: translated field is {type(field).__name__}")
    if field.get(LANG):
        return field[LANG]
    if field.get("_default") and field.get(field["_default"]):
        return field[field["_default"]]
    return next((v for v in field.values() if isinstance(v, str) and v), None)


def _parse_cursor(value: str | None) -> tuple[datetime, int] | None:
    if not value:
        return None
    stamp, _, rid = value.partition("|")
    return _utc(stamp), int(rid or 0)


class FirefoxAddons(Collector):
    name = "firefox_addons"
    license = "Ratings (c) their authors; Mozilla Websites Terms of Use"
    tos_class = "gray"
    regions = ["GLOBAL"]
    min_interval = 1.0

    def __init__(self, max_items: int = 500, categories: list[str] | None = None,
                 pool_depth: int = POOL_DEPTH, addons_per_category: int = ADDONS_PER_CATEGORY,
                 page_size: int = PAGE_SIZE, now: datetime | None = None):
        super().__init__(max_items)
        self.categories = categories or CATEGORIES
        self.pool_depth = pool_depth
        self.addons_per_category = addons_per_category
        self.page_size = page_size
        self.now = now

    def fetch(self, http: Http, state: State) -> Iterator[Item]:
        # State is written eagerly: the runner stops pulling at max_items, so code after
        # the last yield may never run.
        rotation = int(state.get("rotation", "0"))
        state.set("rotation", str(rotation + 1))
        floor = (self.now or datetime.now(timezone.utc)) - MAX_AGE
        addons = self._pick_addons(http, rotation)

        streams = [self._ratings(http, state, a, floor) for a in addons]
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

    def _pick_addons(self, http: Http, rotation: int) -> list[dict]:
        """This run's add-ons, ordered rank-major so any cap spreads over categories."""
        slices = max(1, self.pool_depth // self.addons_per_category)
        start = (rotation % slices) * self.addons_per_category
        picks: dict[str, list[dict]] = {}
        any_results = False
        for category in self.categories:
            resp = http.get(SEARCH, params={
                "type": "extension", "sort": "users", "category": category,
                "app": "firefox", "page_size": self.pool_depth, "lang": LANG,
            })
            resp.raise_for_status()
            data = resp.json()
            require(data, ["results", "count"], "firefox_addons search")
            pool = []
            for a in data["results"]:
                require(a, ["id", "slug", "name", "average_daily_users", "type"],
                        "firefox_addons add-on")
                if a["type"] != "extension":
                    raise SchemaDrift(f"firefox_addons: search returned a {a['type']!r}")
                pool.append({"id": a["id"], "slug": a["slug"], "name": _text(a["name"]),
                             "users": a["average_daily_users"], "category": category})
            any_results = any_results or bool(pool)
            picks[category] = pool[start:start + self.addons_per_category]
        if self.categories and not any_results:
            raise SchemaDrift("firefox_addons: every category search came back empty")
        addons, seen = [], set()
        for rank in range(self.addons_per_category):
            for category in self.categories:
                pool = picks[category]
                if rank < len(pool) and pool[rank]["id"] not in seen:
                    seen.add(pool[rank]["id"])
                    addons.append(pool[rank])
        return addons

    def _ratings(self, http: Http, state: State, addon: dict,
                 floor: datetime) -> Iterator[Item]:
        """New low ratings of one add-on, oldest first, each moving the cursor."""
        key = f"since:{addon['id']}"
        cursor = _parse_cursor(state.get(key))
        since = max(cursor, (floor, 0)) if cursor else (floor, 0)

        fresh: list[tuple[tuple[datetime, int], dict]] = []
        for page in range(1, MAX_PAGES + 1):
            resp = http.get(RATINGS, params={
                "addon": addon["id"], "score": ",".join(map(str, range(1, MAX_SCORE + 1))),
                "filter": "without_empty_body", "page_size": self.page_size, "page": page,
                "lang": LANG,
            })
            resp.raise_for_status()
            data = resp.json()
            require(data, ["results", "next"], "firefox_addons ratings")
            last = None
            for r in data["results"]:
                w = "firefox_addons rating"
                require(r, ["id", "addon", "body", "created", "score", "user", "version",
                            "reply", "is_developer_reply"], w)
                require(r["addon"], ["id", "slug"], f"{w} addon")
                if r["addon"]["id"] != addon["id"]:
                    raise SchemaDrift(f"firefox_addons: asked for add-on {addon['id']},"
                                      f" got {r['addon']['id']}")
                if not 1 <= r["score"] <= MAX_SCORE:
                    raise SchemaDrift(f"firefox_addons: score filter ignored ({r['score']})")
                last = (_utc(r["created"]), int(r["id"]))
                if last > since:
                    fresh.append((last, r))
            if not data["next"] or last is None or last <= since:
                break

        fresh.sort(key=lambda pair: pair[0])
        for (created, rid), r in fresh:
            state.set(key, f"{created.isoformat()}|{rid}")
            body = (r["body"] or "").strip()
            if r["is_developer_reply"] or not body:
                continue
            user = r["user"]
            if user is not None:
                require(user, ["id"], "firefox_addons rating user")
            version = r["version"]
            if version is not None:
                require(version, ["version"], "firefox_addons rating version")
            version_str = version["version"] if version else None
            title = f"{addon['name']} {version_str}" if version_str else addon["name"]
            yield Item(
                source_id=str(rid),
                url=REVIEW_URL.format(slug=r["addon"]["slug"], id=rid),
                title=title,
                body=body,
                author=str(user["id"]) if user else None,
                created_at=created.isoformat(),
                lang=None,
                country=None,
                metrics={"score": r["score"]},
                extra={
                    "addon_id": addon["id"],
                    "addon_slug": addon["slug"],
                    "addon_users": addon["users"],
                    "category": addon["category"],
                    "addon_version": version_str,
                    "has_developer_reply": r["reply"] is not None,
                },
            )
