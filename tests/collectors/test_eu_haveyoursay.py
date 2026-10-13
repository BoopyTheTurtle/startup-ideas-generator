"""Tests for the EU Have Your Say collector. Re-record the live fixtures with:
SIG_HTTP=record uv run pytest tests/collectors/test_eu_haveyoursay.py

The other tests replay small hand-built fixtures from a temp dir, so they never record.
"""

import json
import os

import pytest

from pipeline.collectors.base import SchemaDrift, State
from pipeline.collectors.eu_haveyoursay import (
    FEEDBACK, GROUP, SEARCH, EuHaveYourSay, brussels_to_utc, feedback_item, iso2,
)
from pipeline.http import FIXTURES, Http, _key

NAME = EuHaveYourSay.name
# Fixed cursor so recorded request params match on replay.
SINCE = "2026/10/12"


# Personal data the API returns that the collector never reads; blanked in fixtures so
# the repo holds no submitter or official names.
SCRUB = {"firstName", "surname", "login", "authorName", "authorSurname", "authorMail",
         "authorPhoneNumber", "surveyContactMail"}


def _blank(obj):
    if isinstance(obj, dict):
        return {k: ("" if k in SCRUB and obj[k] else _blank(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_blank(v) for v in obj]
    return obj


def scrub_fixtures():
    for path in (FIXTURES / NAME).glob("*.json"):
        d = json.loads(path.read_text(encoding="utf-8"))
        if not d["content_type"].startswith("application/json"):
            continue  # e.g. the search's plain-text 406 for an empty result
        d["text"] = json.dumps(_blank(json.loads(d["text"])), ensure_ascii=False)
        path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def fetch_live(max_items=5):
    mode = os.environ.get("SIG_HTTP", "replay")
    if mode == "replay" and not any((FIXTURES / NAME).glob("*.json")):
        # Submitters hold the rights to their text, so recordings stay local (gitignored).
        pytest.skip("Have Your Say fixtures are local-only; record them to run this test")
    http = Http(NAME, min_interval=0, mode=mode)
    state = State({"since": SINCE})
    try:
        return list(EuHaveYourSay(max_items=max_items).fetch(http, state)), state
    finally:
        http.close()
        if mode == "record":
            scrub_fixtures()


def test_recorded_items_have_required_fields():
    items, _ = fetch_live()
    assert items
    for it in items:
        assert it.source_id.isdigit() and it.body.strip() and it.title
        assert it.url.startswith(
            "https://ec.europa.eu/info/law/better-regulation/have-your-say/initiatives/")
        assert it.url.endswith(f"/F{it.source_id}_en")
        assert it.created_at.endswith("+00:00")
        assert it.lang and len(it.lang) == 2 and it.lang.islower()
        assert it.country is None or (len(it.country) == 2 and it.country.isupper())
        assert {"initiative_id", "initiative_reference", "user_type", "feedback_stage",
                "topic"} <= it.extra.keys()
        if it.extra["user_type"] in ("EU_CITIZEN", "NON_EU_CITIZEN"):
            assert it.author is None


def test_recorded_cap_and_unique_ids():
    items, _ = fetch_live(max_items=5)
    ids = [it.source_id for it in items]
    assert len(ids) == len(set(ids)) and len(ids) <= 5


def test_recorded_cursors_set():
    _, state = fetch_live()
    assert any(k.startswith("pub:") for k in state.values)
    assert state.get("since") >= SINCE


# --- hand-built fixtures ---------------------------------------------------------

def put(root, url, params, payload):
    d = root / NAME
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{_key('GET', url, params, None)}.json").write_text(json.dumps({
        "url": url, "status": 200, "content_type": "application/json",
        "text": json.dumps(payload),
    }), encoding="utf-8")


def search_params(since="2026/10/01"):
    return {"feedbackOpenDateFrom": since, "language": "EN", "page": 0, "size": 10}


def feedback_params(pub, size, page=0):
    return {"publicationId": pub, "keywords": "", "language": "EN", "page": page,
            "size": size, "sort": "dateFeedback,DESC"}


INIT = {
    "id": 1.0, "reference": "COM(2026)1", "shortTitle": "Original title ",
    "initiativeTranslations": [
        {"language": "EN", "field": "SHORT_TITLE", "value": "Widget rules – revision"}],
    "topics": [{"code": "GROW", "label": "Internal market"}],
    "currentStatuses": [{"receivingFeedbackStatus": "OPEN",
                         "feedbackEndDate": "2026/12/01 23:59:59"}],
}
PUB = {"id": 10, "type": "PROP_REG", "frontEndStage": "ADOPTION_WORKFLOW",
       "receivingFeedbackStatus": "OPEN", "totalFeedback": 4,
       "endDate": "2026/12/01 23:59:59"}


def fb(fid, when, **kw):
    base = {"id": fid, "dateFeedback": when, "language": "EN", "userType": "EU_CITIZEN",
            "country": "BEL", "status": "PUBLISHED", "attachments": [],
            "publicationId": 10, "firstName": "", "surname": "", "login": ""}
    base.update(kw)
    return base


def build_world(root):
    put(root, SEARCH, search_params(), {"initiativeResultDtoPage": {
        "content": [INIT], "totalElements": 1, "last": True}})
    put(root, f"{GROUP}1", None, {"id": 1, "publications": [
        PUB,
        {**PUB, "id": 11, "type": "OPC_LAUNCHED"},
        {**PUB, "id": 12, "receivingFeedbackStatus": "CLOSED",
         "endDate": "2025/03/01 23:59:59"},
    ]})
    put(root, FEEDBACK, feedback_params(10, 50), {"last": False, "content": [
        fb(105, "2026/10/05 10:00:00", language="FR", country="FRA",
           publication="WITHINFO", firstName="Jane", surname="Doe",
           feedback="Les règles coûtent trop cher.",
           feedbackTextUserLanguage="The rules cost too much."),
        fb(104, "2026/10/04 09:00:00", userType="COMPANY", country="DEU",
           organization="Acme GmbH", companySize="SMALL", trNumber="123-45",
           feedback="Compliance takes us 200 hours a year.", attachments=[{"id": 1}]),
        fb(103, "2026/10/03 08:00:00"),  # attachment-only: no 'feedback' key
        fb(90, "2026/09/20 08:00:00", feedback="Older than the cursor."),
    ]})


def run(root, state, max_items=50):
    http = Http(NAME, min_interval=0, mode="replay", fixtures=root)
    try:
        return list(EuHaveYourSay(max_items=max_items).fetch(http, state))
    finally:
        http.close()


def test_mapping_privacy_and_cursors(tmp_path):
    build_world(tmp_path)
    state = State({"since": "2026/10/01"})
    items = run(tmp_path, state)
    assert [it.source_id for it in items] == ["105", "104"]
    citizen, company = items
    assert citizen.author is None
    assert "Jane" not in repr(citizen) and "Doe" not in repr(citizen)
    assert citizen.lang == "fr" and citizen.country == "FR"
    assert citizen.body == "Les règles coûtent trop cher."
    assert citizen.extra["text_en_machine"] == "The rules cost too much."
    assert citizen.created_at == "2026-10-05T08:00:00+00:00"
    assert citizen.title == "Widget rules – revision"
    assert citizen.url == ("https://ec.europa.eu/info/law/better-regulation/have-your-say/"
                           "initiatives/1-Original-title-/F105_en")
    assert company.author == "Acme GmbH" and company.country == "DE"
    assert company.metrics == {"attachments": 1}
    assert company.extra["organisation_size"] == "SMALL"
    assert company.extra["user_type"] == "COMPANY"
    assert company.extra["topic"] == ["Internal market"]
    assert state.get("pub:10") == "2026/10/05 10:00:00|105"
    assert state.get("pub:11") is None and state.get("pub:12") is None
    assert state.get("since") == "2026/10/05"

    # A second run from the same discovery date skips everything already seen.
    state.set("since", "2026/10/01")
    assert run(tmp_path, state) == []


def test_budget_cut_holds_since_at_unvisited_closed_initiative(tmp_path):
    closed = {**INIT, "id": 2.0, "currentStatuses": [
        {"receivingFeedbackStatus": "CLOSED", "feedbackEndDate": "2026/10/03 23:59:59"}]}
    put(tmp_path, SEARCH, search_params(), {"initiativeResultDtoPage": {
        "content": [INIT, closed], "totalElements": 2, "last": True}})
    put(tmp_path, f"{GROUP}1", None, {"id": 1, "publications": [PUB]})
    put(tmp_path, FEEDBACK, feedback_params(10, 1), {"last": False, "content": [
        fb(105, "2026/10/05 10:00:00", feedback="Newest.")]})
    put(tmp_path, SEARCH, {"feedbackStatus": "CLOSED", **search_params()},
        {"initiativeResultDtoPage": {"content": [closed], "totalElements": 1, "last": True}})
    state = State({"since": "2026/10/01"})
    items = run(tmp_path, state, max_items=1)
    assert [it.source_id for it in items] == ["105"]
    assert state.get("since") == "2026/10/03"   # not 10/05: initiative 2 still needs a sweep


def test_search_missing_field_raises_schema_drift(tmp_path):
    put(tmp_path, SEARCH, search_params(), {"results": []})
    with pytest.raises(SchemaDrift):
        run(tmp_path, State({"since": "2026/10/01"}))


def test_feedback_item_missing_field_raises_schema_drift():
    item = fb(1, "2026/10/05 10:00:00", feedback="text")
    del item["userType"]
    with pytest.raises(SchemaDrift):
        feedback_item(item, INIT, PUB)
    org = fb(2, "2026/10/05 10:00:00", feedback="text", userType="NGO")
    with pytest.raises(SchemaDrift):
        feedback_item(org, INIT, PUB)  # an organisation without 'organization'


def test_brussels_time_and_country_codes():
    assert brussels_to_utc("2026/10/13 15:49:38") == "2026-10-13T13:49:38+00:00"
    assert brussels_to_utc("2026/01/15 11:00:00") == "2026-01-15T10:00:00+00:00"
    assert brussels_to_utc("2026/03/29 03:00:00") == "2026-03-29T01:00:00+00:00"
    assert brussels_to_utc("2026/10/25 03:00:00") == "2026-10-25T02:00:00+00:00"
    assert (iso2("SWE"), iso2("GBR"), iso2("de"), iso2("ZZZ"), iso2(None)) == (
        "SE", "GB", "DE", None, None)
