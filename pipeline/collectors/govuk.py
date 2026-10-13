"""GOV.UK consultations and Competition and Markets Authority (CMA) cases.

Consultations name problems the government wants to fix and the people they affect;
CMA cases name markets the regulator thinks fail consumers or businesses. Both carry
the "why now" behind a problem.

APIs (no key), verified live 2026-10-13:
  Search   https://www.gov.uk/api/search.json   lists documents, newest first by
           public_timestamp. Filters used:
             filter_content_store_document_type = open_consultation, closed_consultation,
               consultation_outcome (repeated parameter = OR)
             filter_format = cma_case
             filter_public_timestamp = from:YYYY-MM-DD (inclusive, UTC day)
           `fields` must name real index fields; an unknown one (e.g. opening_date)
           returns an HTML error page, not JSON.
  Content  https://www.gov.uk/api/content/<base_path>   one document with its HTML
           body; consultation dates live in `details`, CMA facets in
           `details.metadata`.
Licence: Open Government Licence v3.0, stated in every GOV.UK page footer
(https://www.gov.uk/help/terms-conditions,
https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

public_timestamp moves on every major update: a consultation that closes and later
gets a government response, or a CMA case that publishes a decision, reappears ahead of
the cursor. source_id is "<content_id>:<document_type>", so each stage of a document
(open, closed, outcome) is stored once: a consultation first seen open gains its outcome
text later. CMA cases add their case_state (open, closed), so a decision is stored too.
Re-fetching an update within the same stage adds nothing.

Cursors, one pair per stream (consultations, cma):
  <stream>_since    public_timestamp of the last item yielded (UTC ISO)
  <stream>_last_id  its content_id; (timestamp, content_id) orders items, so documents
                    sharing a timestamp at a budget cut are neither lost nor repeated
Each stream is read in full back to its cursor, then yielded oldest first; the cursor
moves just before each item, so a run cut short resumes where it stopped.

Bodies keep GOV.UK's HTML. Contact details from `ways_to_respond` (emails, postal
addresses) are deliberately not stored; author is the publishing organisation, a public
body, so distinct-organisation counts work.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from pipeline.collectors.base import Collector, Item, SchemaDrift, State, require
from pipeline.http import Http

SEARCH = "https://www.gov.uk/api/search.json"
CONTENT = "https://www.gov.uk/api/content"
SITE = "https://www.gov.uk"
PAGE_SIZE = 100
MAX_PAGES = 20
FIRST_RUN_LOOKBACK = timedelta(days=30)
FIELDS = ",".join(["content_id", "link", "title", "description", "public_timestamp",
                   "content_store_document_type", "format", "organisations"])
CONSULTATION_TYPES = ["open_consultation", "closed_consultation", "consultation_outcome"]
STREAMS = {
    "consultations": {"filter_content_store_document_type": CONSULTATION_TYPES},
    "cma": {"filter_format": "cma_case"},
}
# HTML fields appended to the description, in this order, when present.
BODY_FIELDS = ["body", "public_feedback_detail", "final_outcome_detail"]
CMA_META = ["case_type", "case_state", "market_sector", "opened_date", "closed_date",
            "outcome_type"]


def _ts(value: str, where: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError) as e:
        raise SchemaDrift(f"{where}: bad timestamp {value!r}") from e
    if dt.tzinfo is None:
        raise SchemaDrift(f"{where}: naive timestamp {value!r}")
    return dt.astimezone(timezone.utc)


def _key(r: dict) -> tuple[datetime, str]:
    return _ts(r["public_timestamp"], "govuk search result"), r["content_id"]


class GovUk(Collector):
    name = "govuk"
    license = "OGL-3.0"
    tos_class = "clean"
    regions = ["GB"]
    min_interval = 0.5

    def fetch(self, http: Http, state: State) -> Iterator[Item]:
        default = (datetime.now(timezone.utc) - FIRST_RUN_LOOKBACK).isoformat()
        found: dict[str, list[dict]] = {}
        for stream, filters in STREAMS.items():
            cursor = (_ts(state.get(f"{stream}_since", default), f"govuk {stream} cursor"),
                      state.get(f"{stream}_last_id", ""))
            rows = [r for r in self._scan(http, stream, filters, cursor[0])
                    if _key(r) > cursor]
            rows.sort(key=_key)
            found[stream] = rows

        # Split the budget so neither stream starves the other.
        cons, cma = found["consultations"], found["cma"]
        n_cma = min(len(cma), max(self.max_items // 2, self.max_items - len(cons)))
        n_cons = min(len(cons), self.max_items - n_cma)

        for stream, batch in (("consultations", cons[:n_cons]), ("cma", cma[:n_cma])):
            for r in batch:
                item = self._item(http, r)
                ts, cid = _key(r)
                state.set(f"{stream}_since", ts.isoformat())
                state.set(f"{stream}_last_id", cid)
                if item is not None:
                    yield item

    def _scan(self, http: Http, stream: str, filters: dict,
              since: datetime) -> list[dict]:
        """Page the search newest first until results reach `since`."""
        # Day-granular filter, one day early: the exact cut happens on (timestamp, id).
        start_day = (since - timedelta(days=1)).date().isoformat()
        rows: list[dict] = []
        seen: set[str] = set()
        for page in range(MAX_PAGES):
            resp = http.get(SEARCH, params={
                **filters,
                "filter_public_timestamp": f"from:{start_day}",
                "order": "-public_timestamp",
                "fields": FIELDS,
                "count": PAGE_SIZE,
                "start": page * PAGE_SIZE,
            })
            resp.raise_for_status()
            data = resp.json()
            require(data, ["results", "total"], f"govuk {stream} search")
            for r in data["results"]:
                require(r, ["content_id", "link", "title", "public_timestamp",
                            "content_store_document_type"], f"govuk {stream} result")
                if r["content_id"] not in seen:  # offset paging can repeat a row
                    seen.add(r["content_id"])
                    rows.append(r)
            if (len(data["results"]) < PAGE_SIZE
                    or (page + 1) * PAGE_SIZE >= data["total"]
                    or _key(data["results"][-1])[0] < since):
                break
        return rows

    @staticmethod
    def _item(http: Http, r: dict) -> Item | None:
        link = r["link"]
        if not link.startswith("/"):
            return None  # external link; nothing to fetch from the content store
        resp = http.get(CONTENT + link)
        if resp.status_code in (404, 410):
            return None  # unpublished between search and fetch
        resp.raise_for_status()
        doc = resp.json()
        require(doc, ["content_id", "base_path", "document_type", "title", "details",
                      "links", "locale"], "govuk content")
        details = doc["details"]
        require(details, ["body"], "govuk content details")

        parts = [doc.get("description") or r.get("description") or ""]
        parts += [details[f] for f in BODY_FIELDS if isinstance(details.get(f), str)]
        body = "\n\n".join(p for p in parts if p and p.strip())
        if not body:
            return None

        orgs = r.get("organisations") or []
        extra: dict = {
            "document_type": doc["document_type"],
            "organisations": [o["slug"] for o in orgs if isinstance(o, dict) and o.get("slug")],
            "html": True,
        }
        if doc["document_type"] in CONSULTATION_TYPES:
            for f in ("opening_date", "closing_date"):
                if details.get(f):
                    extra[f] = _ts(details[f], f"govuk {f}").isoformat()
        if doc["document_type"] == "cma_case":
            meta = details.get("metadata")
            require(meta, ["case_type", "case_state"], "govuk cma metadata")
            extra.update({k: meta[k] for k in CMA_META if k in meta})
        if doc.get("withdrawn_notice"):
            extra["withdrawn"] = True

        # A stage per stored version: consultations move open -> closed -> outcome; CMA
        # cases keep one document type, so their case_state marks the stage instead.
        stage = doc["document_type"]
        if stage == "cma_case":
            stage = f"cma_case:{extra['case_state']}"

        primary = doc["links"].get("primary_publishing_organisation") or []
        author = (primary[0].get("title") if primary and isinstance(primary[0], dict)
                  else None) or next((o.get("title") for o in orgs
                                      if isinstance(o, dict) and o.get("title")), None)
        return Item(
            source_id=f"{r['content_id']}:{stage}",
            url=SITE + doc["base_path"],
            title=doc["title"],
            body=body,
            author=author,
            created_at=_ts(r["public_timestamp"], "govuk public_timestamp").isoformat(),
            lang=doc["locale"] or "en",
            country="GB",
            metrics={},
            extra=extra,
        )
