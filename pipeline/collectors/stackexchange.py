"""Stack Exchange questions where people describe problems with tools, work, money, and home.

API: Stack Exchange API 2.3, GET /questions per site (https://api.stackexchange.com/docs).
No key: the anonymous quota is ~300 requests/day per IP, shared with anything else on the
IP. The API also sets `backoff` (seconds to wait before calling the same method again)
and `quota_remaining`; the collector obeys the first and stops cleanly on the second.

Licence: questions are user content under CC BY-SA 4.0; reuse requires attribution (link,
author, licence). The API Terms of Use add only attribution and branding rules
(https://stackoverflow.com/legal/api-terms-of-use).

tos_class 'gray': the Acceptable Use Policy (https://stackoverflow.com/legal/acceptable-use-policy,
"Content Scraping/Bot Policy") bars automated collection from any Network "Service" for
"developing, building, training, testing, indexing, benchmarking, or improving any
generative AI, chatbot, large language, or machine learning tool, model, or platform".
Our pipeline reads questions with an LLM to extract pain records; that is inference, not
training, and the Public Network Terms (https://stackoverflow.com/legal/terms-of-service/public,
last updated 2025-11-13) exempt API content from their noncommercial-copy clause. But
"testing" and "benchmarking" are broad, and Stack Overflow now sells AI use of its content
(Stack Data Licensing). Keep this source's text out of eval sets and prompt-tuning data,
show attribution wherever a question is displayed, and let Edgar decide.
"""

import html
import time
from collections.abc import Iterator
from datetime import datetime, timezone

from pipeline.collectors.base import Collector, Item, State, require
from pipeline.http import Http

API = "https://api.stackexchange.com/2.3/questions"

# Sites whose questions describe a problem a product could solve, mostly outside
# programming, so they widen the developer-heavy v1 mix. All are English-language.
SITES = [
    "softwarerecs",  # "is there a tool that ..." requests: explicit unmet demand
    "webapps",       # people fighting Gmail, Sheets, Trello; workarounds for missing features
    "superuser",     # power users stuck on desktop software and devices; high volume
    "money",         # personal finance: taxes, budgeting, banks, pensions
    "workplace",     # problems with managers, hiring, remote work, HR process
    "freelancing",   # invoicing, clients, contracts, platform fees
    "pm",            # project management: tooling, planning, reporting pain
    "law",           # laypeople facing legal processes: tenancy, contracts, small claims
    "diy",           # home repair and improvement: trades, materials, inspections
    "parenting",     # childcare, schooling, sleep, screen time
    "travel",        # bookings, visas, airlines, refunds
    "expatriates",   # bureaucracy of moving countries: permits, banking, tax residency
    "academia",      # researchers' and students' process pain: grants, review, admin
    "opendata",      # requests for data that does not exist or cannot be found
    "pets",          # pet care: health, feeding, behaviour, products
]
FIRST_RUN_LOOKBACK_S = 7 * 24 * 3600
MAX_PAGE_SIZE = 100
QUOTA_FLOOR = 10  # stop before the daily quota runs out; leave room for manual checks


# Sites collected by default. Edgar's 2026-10-13 labels: 3 of 25 Stack Exchange items were
# pain, all from diy and webapps; the other sites scored 0 (STATUS.md source review).
ACTIVE_SITES = ["diy", "webapps"]


class StackExchange(Collector):
    name = "stackexchange"
    license = "CC-BY-SA-4.0"
    tos_class = "gray"
    regions = ["GLOBAL"]
    min_interval = 1.0

    def __init__(self, max_items: int = 500, sites: list[str] | None = None):
        super().__init__(max_items)
        self.sites = sites or ACTIVE_SITES

    def fetch(self, http: Http, state: State) -> Iterator[Item]:
        now = int(datetime.now(timezone.utc).timestamp())
        per_site = max(1, self.max_items // len(self.sites))
        page_size = min(MAX_PAGE_SIZE, per_site)  # constant per site: the API pages by offset
        yielded = 0
        backoff = 0.0
        state.set("stopped", "")  # set below when quota or throttling ends the run early
        for site in self.sites:
            key = f"fromdate:{site}"
            since = int(state.get(key, str(now - FIRST_RUN_LOOKBACK_S)))
            newest = since - 1
            got = 0
            page = 1
            while got < per_site:
                if backoff and http.mode != "replay":
                    time.sleep(backoff)
                resp = http.get(API, params={
                    "site": site,
                    "fromdate": since,  # inclusive
                    "sort": "creation",
                    "order": "desc",    # newest first: a busy site gets sampled, never backlogged
                    "filter": "withbody",
                    "pagesize": page_size,
                    "page": page,
                })
                if resp.status_code >= 400:
                    try:
                        err = resp.json()
                    except ValueError:
                        resp.raise_for_status()
                    if isinstance(err, dict) and err.get("error_name") == "throttle_violation":
                        state.set("stopped", f"throttle_violation at {site}")
                        return  # out of quota: this and later sites keep their cursors
                    resp.raise_for_status()
                data = resp.json()
                require(data, ["items", "has_more", "quota_remaining"], "stackexchange questions")
                backoff = float(data.get("backoff", 0))
                for q in data["items"]:
                    require(q, ["question_id", "title", "body", "link", "creation_date",
                                "score", "answer_count", "view_count", "is_answered", "tags"],
                            "stackexchange question")
                    newest = max(newest, q["creation_date"])
                # Advance the cursor before yielding: the runner may stop consuming at its
                # cap, and code after the last yield would then never run.
                state.set(key, str(newest + 1))
                for q in data["items"]:
                    if not q["body"].strip():
                        continue
                    owner = q.get("owner") or {}
                    author = owner.get("user_id") or owner.get("display_name")
                    got += 1
                    yielded += 1
                    yield Item(
                        source_id=f"{site}:{q['question_id']}",
                        url=q["link"],
                        title=html.unescape(q["title"]),
                        body=q["body"],
                        author=str(author) if author is not None else None,
                        created_at=datetime.fromtimestamp(
                            q["creation_date"], timezone.utc).isoformat(),
                        lang="en",
                        metrics={"score": q["score"], "answer_count": q["answer_count"],
                                 "view_count": q["view_count"],
                                 "is_answered": 1 if q["is_answered"] else 0},
                        extra={"site": site, "tags": q["tags"], "html": True},
                    )
                    if got >= per_site or yielded >= self.max_items:
                        break
                state.set("quota_remaining", str(data["quota_remaining"]))
                if data["quota_remaining"] <= QUOTA_FLOOR:
                    state.set("stopped", f"quota_remaining {data['quota_remaining']} at {site}")
                    return
                page += 1
                if not data["has_more"] or yielded >= self.max_items:
                    break
            if yielded >= self.max_items:
                return
