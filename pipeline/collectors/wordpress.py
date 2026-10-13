"""WordPress.org plugin support forums: new topics, where site owners say what breaks.

Small businesses, shops, and agencies run their sites on these plugins, and the support
threads describe failed checkouts, broken bookings, consent banners, backups, and the
workarounds people try. HN and Stack Exchange rarely reach this population.

Endpoints on https://wordpress.org, verified live 2026-10-13:
  /support/plugin/{slug}/feed/
      RSS 2.0 (bbPress), the 30 newest topics of one plugin's forum, newest first by
      creation date. Topic starts only, no replies. `?paged=` is ignored, so 30 is all a
      feed shows. Each <description> is the opening post as HTML, prefixed by a template
      paragraph `<p>Replies: N</p>`, which the collector moves into metrics. An unknown
      slug returns 404.
  /plugins/wp-json/plugins/v1/query-plugins?browse=popular&paged=N
      the plugin directory's REST route behind its "Popular" tab: 20 slugs per page.
  /plugins/wp-json/plugins/v1/plugin/{slug}?_fields=name,slug,active_installs
      name and install count. A removed plugin returns 400; a closed one omits
      active_installs.
The documented Plugins API (https://api.wordpress.org/plugins/info/1.2/) serves the same
data, but https://api.wordpress.org/robots.txt disallows `/` for every agent, so
pipeline.http blocks it. The two plugin-directory routes above are undocumented; every
response goes through require() and fails loudly when it changes shape.
https://wordpress.org/robots.txt allows /support/ and /plugins/wp-json/ and explicitly
allows GPTBot, ClaudeBot, anthropic-ai, and CCBot.

Plugin selection: the pool is the top POPULAR_PAGES x 20 popular plugins plus CURATED,
plugins in business categories (WooCommerce extensions and payments, bookings and events,
forms, membership and courses, invoicing and CRM, SEO, backups, multilingual, cookie
consent, email marketing). Each run visits PLUGINS_PER_RUN plugins from the pool,
starting at the `rotation` offset, which then advances, so the whole pool is covered
every few runs. The popular list drifts slowly, so the rotation is approximate.

Cursors: `since:{slug}` holds "ISO-UTC|guid" of the newest topic seen in that forum.
Topics newer than it, as (pubDate, guid) tuples so equal timestamps sort stably, are
new. A plugin first visited looks back FIRST_VISIT_LOOKBACK. max_items is shared across
the run's plugins with rollover: each gets remaining // plugins left. A forum with more
new topics than its share keeps the newest share and skips the older rest for good
(deliberate sampling, as in hn). The kept topics go out oldest first, and the cursor
moves to each one just before it is yielded, so a run cut short resumes exactly. A busy
forum (WooCommerce: ~30 topics in 2 weeks) can also outrun the 30-item feed between
visits; those topics are missed.

Not collected: resolved status (absent from the feed; the /unresolved/ view would cost a
second 70 KB request per plugin) and non-English forums, which live on
{locale}.wordpress.org. The English forums still carry some posts in other languages;
lang is 'en' for the forum, not detected per post.

Licence and terms, tos_class = gray:
- Posts belong to their authors. WordPress.org grants no licence for forum content and
  publishes no site terms of use for the forums; the privacy policy
  (https://wordpress.org/about/privacy/) and forum guidelines
  (https://wordpress.org/support/guidelines/) cover conduct and personal data only. The
  forum FAQ (https://wordpress.org/support/forum-user-guide/faq/) tells posters that
  posts stay public "forever" and are rarely deleted.
- Access is welcome: the RSS feeds exist for machine readers and robots.txt names AI
  crawlers as allowed. That supports private analysis, not republishing; quote sparingly.
- The plugin-directory routes are undocumented.
The recorded fixtures hold verbatim posts, so keep them out of a public repository.

Privacy: `author` is dc:creator, the poster's display name (often a username, sometimes
a real name); the runner hashes it and never stores it raw. Display names are not
unique, so two posters can share a hash. Posts can still contain names and site URLs.
"""

import html
import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree.ElementTree import Element, ParseError

from defusedxml import ElementTree

from pipeline.collectors.base import Collector, Item, SchemaDrift, State, require
from pipeline.http import Http

FEED = "https://wordpress.org/support/plugin/{slug}/feed/"
QUERY = "https://wordpress.org/plugins/wp-json/plugins/v1/query-plugins"
INFO = "https://wordpress.org/plugins/wp-json/plugins/v1/plugin/{slug}"
TOPIC_RE = re.compile(r"https://wordpress\.org/support/topic/([^/?#]+)/")
REPLIES_RE = re.compile(r"\A\s*<p>\s*Replies:\s*(\d+)\s*</p>\s*")
CHANNEL_NAME_RE = re.compile(r"\[(.+)\] Support\s*\Z")
DC = "{http://purl.org/dc/elements/1.1/}"

POPULAR_PAGES = 2          # 20 plugins per page
PLUGINS_PER_RUN = 35       # 2 requests each; the ~105-plugin pool turns over in 3 runs
FIRST_VISIT_LOOKBACK = timedelta(days=60)

# Business-relevant plugins, verified to exist on 2026-10-13. Top popular plugins
# (WooCommerce, Contact Form 7, Yoast, UpdraftPlus, ...) arrive through the API.
CURATED = [
    # WooCommerce extensions, payments, and other shops
    "woocommerce-gateway-stripe", "woocommerce-payments", "woocommerce-paypal-payments",
    "woocommerce-services", "flexible-shipping", "woo-variation-swatches",
    "yith-woocommerce-wishlist", "cartflows", "woo-checkout-field-editor-pro",
    "facebook-for-woocommerce", "google-listings-and-ads", "woo-product-feed-pro",
    "easy-digital-downloads", "stripe", "surecart",
    # Bookings, appointments, events
    "bookly-responsive-appointment-booking-tool", "ameliabooking",
    "simply-schedule-appointments", "fluent-booking", "easy-appointments", "booking",
    "the-events-calendar", "events-manager", "event-tickets", "restaurant-reservations",
    # Forms
    "wpforms-lite", "ninja-forms", "formidable", "fluentform", "forminator",
    # Membership and courses
    "ultimate-member", "simple-membership", "restrict-content", "members", "learnpress",
    "tutor", "sensei-lms",
    # Invoicing, CRM, donations, jobs, helpdesk, chat
    "woocommerce-pdf-invoices-packing-slips", "sliced-invoices", "invoicing", "zero-bs-crm",
    "fluent-crm", "leadin", "give", "wp-job-manager", "supportcandy", "tidio-live-chat",
    # SEO
    "wordpress-seo", "seo-by-rank-math", "all-in-one-seo-pack", "autodescription",
    "wp-seopress", "redirection",
    # Backups and migration
    "updraftplus", "backwpup", "duplicator", "wpvivid-backuprestore",
    "all-in-one-wp-migration",
    # Multilingual
    "polylang", "translatepress-multilingual", "weglot", "gtranslate", "loco-translate",
    # Cookie consent and GDPR
    "complianz-gdpr", "cookie-law-info", "cookie-notice", "gdpr-cookie-compliance",
    "cookiebot",
    # Email marketing and delivery
    "mailchimp-for-wp", "mailpoet", "newsletter", "email-subscribers", "post-smtp",
    "mailin", "klaviyo", "wp-mail-smtp",
]


def _pubdate(value: str, where: str) -> datetime:
    try:
        ts = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError) as e:
        raise SchemaDrift(f"{where}: unparseable pubDate {value!r}") from e
    if ts.tzinfo is None:
        raise SchemaDrift(f"{where}: pubDate without timezone {value!r}")
    return ts.astimezone(timezone.utc)


def _cursor(value: str | None, default: datetime) -> tuple[datetime, str]:
    if not value:
        return default, ""
    ts, _, guid = value.partition("|")
    return datetime.fromisoformat(ts), guid


def _fields(el: Element) -> dict[str, str]:
    """Child elements as {local tag: text}; dc:creator becomes 'creator'."""
    return {child.tag.replace(DC, ""): (child.text or "").strip() for child in el}


class WordPressSupport(Collector):
    name = "wordpress"
    license = "Posts (c) their authors; no licence granted (WordPress.org forums)"
    tos_class = "gray"
    regions = ["GLOBAL"]
    min_interval = 1.0

    def __init__(self, max_items: int = 500, plugins: list[str] | None = None,
                 popular_pages: int = POPULAR_PAGES, plugins_per_run: int = PLUGINS_PER_RUN):
        super().__init__(max_items)
        self.curated = CURATED if plugins is None else plugins
        self.popular_pages = popular_pages
        self.plugins_per_run = plugins_per_run

    def fetch(self, http: Http, state: State) -> Iterator[Item]:
        pool = list(dict.fromkeys(self._popular(http) + self.curated))
        if not pool:
            return
        start = int(state.get("rotation", "0")) % len(pool)
        count = min(self.plugins_per_run, len(pool), self.max_items)
        chosen = [pool[(start + i) % len(pool)] for i in range(count)]
        state.set("rotation", str((start + count) % len(pool)))

        default = datetime.now(timezone.utc) - FIRST_VISIT_LOOKBACK
        remaining = self.max_items
        for i, slug in enumerate(chosen):
            share = remaining // (len(chosen) - i)
            if share <= 0:
                continue
            got = 0
            for item in self.guarded(slug, self._plugin(http, state, slug, share, default)):
                got += 1
                yield item
            remaining -= got

    def _popular(self, http: Http) -> list[str]:
        slugs: list[str] = []
        for page in range(1, self.popular_pages + 1):
            resp = http.get(QUERY, params={"browse": "popular", "paged": page})
            resp.raise_for_status()
            data = resp.json()
            require(data, ["info", "plugins"], "wordpress query-plugins")
            if not isinstance(data["plugins"], list) or not all(
                    isinstance(s, str) for s in data["plugins"]):
                raise SchemaDrift("wordpress query-plugins: plugins is not a list of slugs")
            slugs += data["plugins"]
            if not data["plugins"]:
                break
        return slugs

    def _plugin(self, http: Http, state: State, slug: str, share: int,
                default: datetime) -> Iterator[Item]:
        resp = http.get(FEED.format(slug=slug))
        if resp.status_code == 404:
            return  # plugin removed or renamed
        resp.raise_for_status()
        channel, rows = self._parse(resp.text, slug)

        key = f"since:{slug}"
        since = _cursor(state.get(key), default)
        new = sorted((r for r in rows if (r["ts"], r["guid"]) > since),
                     key=lambda r: (r["ts"], r["guid"]))[-share:]
        if not new:
            return

        info = self._info(http, slug)
        name = info.get("name") or channel
        installs = info.get("active_installs")
        for r in new:
            state.set(key, f"{r['ts'].isoformat()}|{r['guid']}")
            if not r["body"]:
                continue
            yield Item(
                source_id=r["topic"],
                url=r["link"],
                title=r["title"],
                body=r["body"],
                author=r["creator"] or None,
                created_at=r["ts"].isoformat(),
                lang="en",
                country=None,
                metrics={"replies": r["replies"]},
                extra={"plugin_slug": slug, "plugin_name": name,
                       "active_installs": installs, "html": True},
            )

    @staticmethod
    def _parse(text: str, slug: str) -> tuple[str | None, list[dict]]:
        where = f"wordpress feed {slug}"
        try:
            root = ElementTree.fromstring(text)  # already decoded by pipeline.http
        except ParseError as e:
            raise SchemaDrift(f"{where}: not XML ({e})") from e
        channel = root.find("channel")
        if root.tag != "rss" or channel is None:
            raise SchemaDrift(f"{where}: no rss/channel")
        require(_fields(channel), ["title", "link"], f"{where} channel")
        m = CHANNEL_NAME_RE.search(html.unescape(channel.findtext("title") or ""))
        rows = []
        for el in channel.findall("item"):
            f = _fields(el)
            require(f, ["guid", "title", "link", "pubDate", "creator", "description"],
                    f"{where} item")
            topic = TOPIC_RE.fullmatch(f["guid"])
            if not topic:
                raise SchemaDrift(f"{where}: guid is not a topic URL: {f['guid']!r}")
            replies = REPLIES_RE.match(f["description"])
            if not replies:
                raise SchemaDrift(f"{where}: description lacks the Replies paragraph")
            rows.append({
                "guid": f["guid"],
                "topic": topic.group(1),
                "link": f["link"],
                "title": html.unescape(f["title"]),
                "creator": f["creator"],
                "ts": _pubdate(f["pubDate"], where),
                "replies": int(replies.group(1)),
                "body": f["description"][replies.end():].strip(),
            })
        return (m.group(1) if m else None), rows

    @staticmethod
    def _info(http: Http, slug: str) -> dict:
        resp = http.get(INFO.format(slug=slug),
                        params={"_fields": "name,slug,active_installs"})
        if resp.status_code in (400, 404):
            return {}  # removed from the directory; its forum can outlive it
        resp.raise_for_status()
        data = resp.json()
        require(data, ["name", "slug"], f"wordpress plugin info {slug}")
        return {"name": html.unescape(data["name"]),
                "active_installs": data.get("active_installs")}
