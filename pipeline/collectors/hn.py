"""Hacker News comments and Ask HN posts that describe pain, via the Algolia search API.

API: https://hn.algolia.com/api (no key; documented limit 10,000 requests/hour per IP).
Content: user posts on news.ycombinator.com; HN's API terms allow reuse with attribution.

HN carries ~10k comments a day, nearly all off-topic for us, so the collector asks Algolia
for phrases people use when describing a problem, and pages forward from a cursor.
"""

from collections.abc import Iterator
from datetime import datetime, timezone

from pipeline.collectors.base import Collector, Item, State, require
from pipeline.http import Http

API = "https://hn.algolia.com/api/v1/search_by_date"

# Phrases that tend to introduce a problem, a workaround, or unmet demand.
PAIN_QUERIES = [
    '"is there a tool"',
    '"I wish there was"',
    '"how do you deal with"',
    '"we ended up building"',
    '"so frustrating"',
    '"pain in the"',
    '"why is it so hard"',
    '"we still use spreadsheets"',
    '"would pay for"',
    '"manual process"',
]
FIRST_RUN_LOOKBACK_S = 7 * 24 * 3600
HITS_PER_PAGE = 100


class HackerNews(Collector):
    name = "hn"
    license = "HN API terms (attribution)"
    tos_class = "clean"
    regions = ["GLOBAL"]
    min_interval = 0.5

    def fetch(self, http: Http, state: State) -> Iterator[Item]:
        now = int(datetime.now(timezone.utc).timestamp())
        since = int(state.get("since", str(now - FIRST_RUN_LOOKBACK_S)))
        newest = since
        seen: set[str] = set()
        yielded = 0
        per_query = max(1, self.max_items // len(PAIN_QUERIES))
        for query in PAIN_QUERIES:
            got = 0
            page = 0
            page_size = min(HITS_PER_PAGE, per_query)  # constant per query: Algolia pages by offset
            while got < per_query:
                data = http.get(API, params={
                    "query": query,
                    "tags": "(comment,ask_hn)",
                    "numericFilters": f"created_at_i>{since}",
                    "hitsPerPage": page_size,
                    "page": page,
                }).json()
                require(data, ["hits", "nbPages"], "hn search")
                for hit in data["hits"]:
                    require(hit, ["objectID", "created_at_i"], "hn hit")
                    oid = hit["objectID"]
                    body = hit.get("comment_text") or hit.get("story_text") or ""
                    if oid in seen or not body.strip():
                        continue
                    seen.add(oid)
                    newest = max(newest, hit["created_at_i"])
                    got += 1
                    yielded += 1
                    yield Item(
                        source_id=oid,
                        url=f"https://news.ycombinator.com/item?id={oid}",
                        title=hit.get("title") or hit.get("story_title"),
                        body=body,
                        author=hit.get("author"),
                        created_at=datetime.fromtimestamp(
                            hit["created_at_i"], timezone.utc).isoformat(),
                        lang="en",
                        metrics={"points": hit.get("points") or 0,
                                 "num_comments": hit.get("num_comments") or 0},
                        extra={"query": query, "story_id": hit.get("story_id"),
                               "parent_id": hit.get("parent_id"), "html": True},
                    )
                    if got >= per_query or yielded >= self.max_items:
                        break
                page += 1
                if page >= data["nbPages"] or yielded >= self.max_items:
                    break
            if yielded >= self.max_items:
                break
        state.set("since", str(newest))
