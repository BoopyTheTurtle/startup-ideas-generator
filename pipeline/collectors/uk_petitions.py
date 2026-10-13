"""UK Parliament e-petitions: problems stated in citizens' words, with a signature count.

API: https://petition.parliament.uk/petitions.json (no key, JSON:API-style). Listing
pages carry every field we need (text, rejection, government response, debate,
departments), so the collector never fetches per-petition JSON.
Licence: Open Government Licence v3.0, stated in the site footer
(https://petition.parliament.uk/help).

Ordering, verified live 2026-10-13:
  state=recent    open petitions, newest opened_at first
  state=rejected  rejected petitions, newest created_at first; rejected_at trails
                  created_at by up to ~6 weeks (moderation backlog)
  other states    sorted by signature count, useless for finding new petitions
`count` sets the page size, up to 50; larger values fall back to 25.

Cursors:
  open_since      newest opened_at stored; page `recent` until a page ends at or below it
  rejected_since  newest rejected_at stored; page `rejected` back to REJECTION_LAG_DAYS
                  before it, so petitions created earlier but rejected since are found

Items go out oldest first and each cursor advances just before its item is yielded, so a
run cut short by max_items resumes where it stopped. Open petitions that close before
the next run (e.g. at a dissolution) are missed; closed petitions are not collected.

signature_count is recorded at fetch time. The runner stores an item once, at first
sight, so later growth is lost; tracking signature growth is a later enhancement.
Creator names are public in the API but deliberately not stored.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from pipeline.collectors.base import Collector, Item, State, require
from pipeline.http import Http

API = "https://petition.parliament.uk/petitions.json"
PETITION_URL = "https://petition.parliament.uk/petitions/{id}"
PAGE_SIZE = 50
MAX_PAGES = 100  # 5,000 petitions; open petitions number ~4,400 at most
FIRST_RUN_LOOKBACK = timedelta(days=7)
REJECTION_LAG_DAYS = 60

ATTRS = ["action", "background", "additional_details", "state", "signature_count",
         "created_at", "opened_at", "rejected_at", "rejection", "government_response",
         "debate", "departments", "topics"]


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _names(entries: list) -> list[str]:
    return [e.get("name") or e.get("acronym") if isinstance(e, dict) else str(e)
            for e in entries or []]


class UkPetitions(Collector):
    name = "uk_petitions"
    license = "OGL-3.0"
    tos_class = "clean"
    regions = ["GB"]
    min_interval = 1.0

    def fetch(self, http: Http, state: State) -> Iterator[Item]:
        http.check_robots(API)
        default = (datetime.now(timezone.utc) - FIRST_RUN_LOOKBACK).isoformat()
        open_since = _ts(state.get("open_since", default))
        rejected_since = _ts(state.get("rejected_since", default))
        horizon = rejected_since - timedelta(days=REJECTION_LAG_DAYS)

        opened = [p for p in self._scan(http, "recent", "opened_at", open_since)
                  if _ts(p["attributes"]["opened_at"]) > open_since]
        rejected = [p for p in self._scan(http, "rejected", "created_at", horizon)
                    if p["attributes"]["rejected_at"]
                    and _ts(p["attributes"]["rejected_at"]) > rejected_since]
        opened.sort(key=lambda p: _ts(p["attributes"]["opened_at"]))
        rejected.sort(key=lambda p: _ts(p["attributes"]["rejected_at"]))

        # Split the budget so neither stream starves the other.
        n_rejected = min(len(rejected), max(self.max_items // 2, self.max_items - len(opened)))
        n_opened = min(len(opened), self.max_items - n_rejected)

        for cursor, key, batch in (("open_since", "opened_at", opened[:n_opened]),
                                   ("rejected_since", "rejected_at", rejected[:n_rejected])):
            for p in batch:
                item = self._item(p)
                if item is None:
                    continue
                state.set(cursor, _ts(p["attributes"][key]).isoformat())
                yield item

    def _scan(self, http: Http, list_state: str, key: str, stop_at: datetime) -> list[dict]:
        """Page a listing sorted newest-first by `key` until it passes `stop_at`."""
        rows: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            resp = http.get(API, params={"state": list_state, "count": PAGE_SIZE, "page": page})
            resp.raise_for_status()
            data = resp.json()
            require(data, ["data", "links"], f"uk_petitions {list_state} page")
            for p in data["data"]:
                require(p, ["id", "attributes"], "uk_petitions petition")
                require(p["attributes"], ATTRS, "uk_petitions attributes")
                rows.append(p)
            if (not data["data"] or not data["links"].get("next")
                    or _ts(data["data"][-1]["attributes"][key]) <= stop_at):
                break
        return rows

    @staticmethod
    def _item(p: dict) -> Item | None:
        a = p["attributes"]
        body = "\n\n".join(t.replace("\r\n", "\n").strip()
                           for t in (a["background"], a["additional_details"]) if t and t.strip())
        if not body and not (a["action"] or "").strip():
            return None
        rejection = a["rejection"] or {}
        extra = {
            "state": a["state"],
            "government_response": 1 if a["government_response"] else 0,
            "debate": 1 if a["debate"] else 0,
            "departments": _names(a["departments"]),
            "topics": _names(a["topics"]),
        }
        if rejection:
            extra["rejection_code"] = rejection.get("code")
            extra["rejection_details"] = (rejection.get("details") or "").replace("\r\n", "\n")
        return Item(
            source_id=str(p["id"]),
            url=PETITION_URL.format(id=p["id"]),
            title=a["action"],
            body=body or a["action"],
            author=None,
            created_at=_ts(a["opened_at"] or a["created_at"]).isoformat(),
            lang="en",
            country="GB",
            metrics={"signature_count": a["signature_count"] or 0},
            extra=extra,
        )
