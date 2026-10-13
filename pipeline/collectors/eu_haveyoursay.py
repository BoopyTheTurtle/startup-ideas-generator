"""Feedback on European Commission initiatives from the "Have Your Say" portal.

Portal: https://ec.europa.eu/info/law/better-regulation/have-your-say
Citizens, companies, NGOs, trade bodies, and public authorities comment on calls for
evidence, draft acts, and proposals, in 24 languages. Companies often state what a rule
will cost them, which makes the text a strong problem and "why now" signal.

API: undocumented. The portal's Angular frontend (main-*.js and its lazy chunks) calls
these endpoints, verified live on 2026-10-13:
  brpapi/searchInitiatives?feedbackOpenDateFrom=YYYY/MM/DD&language=EN&page=N&size=N
      initiatives whose feedback window reaches the given date or later (open ones
      plus those closed since), newest feedback start first
  brpapi/groupInitiatives/{initiativeId}
      the initiative with its publications (call for evidence, draft act, ...); each
      publication carries its own feedback window and totalFeedback
  api/allFeedback?publicationId=N&keywords=&language=EN&page=N&size=N&sort=dateFeedback,DESC
      feedback items, newest first; `feedback` holds the text as submitted and
      `feedbackTextUserLanguage` a machine translation into `language` when the two differ
Every response, list, and item goes through require(), so a changed shape raises
SchemaDrift. Timestamps are Brussels local time ("midnight Brussels time" per the
portal's feedback rules); the collector converts them to UTC. robots.txt at
https://ec.europa.eu/robots.txt allows these paths.

Discovery and cursors:
  since          global cursor, a Brussels date. Each run asks for initiatives whose
                 feedback window reaches `since`, so a window that closed between runs
                 still gets a last sweep. It advances to the date of the newest feedback
                 seen. When max_items cuts discovery short, an extra search for closed
                 initiatives holds it at the earliest closing day among those not
                 visited, so none drops out before its sweep.
  pub:{id}       per-publication cursor "YYYY/MM/DD HH:MM:SS|feedbackId" of the newest
                 item seen; paging stops at it. A new publication starts at `since`.
The budget (max_items) is shared across initiatives with rollover: each gets
max(MIN_SHARE, remaining // initiatives left). A publication with more new feedback than
its share keeps its newest items and skips the older rest: the cursor moves to the
newest, so the skipped items are not fetched later.

Skipped: public-consultation questionnaires (publication type OPC_LAUNCHED; their items
carry no free text here), items with no text (attachment-only), and unpublished items.

Licence and terms, tos_class = gray:
- Commission content (initiative titles, metadata) is CC BY 4.0 under the reuse policy,
  Decision 2011/833/EU: https://commission.europa.eu/legal-notice_en and
  https://eur-lex.europa.eu/eli/dec/2011/833/oj
- Feedback text belongs to its authors, not the EU. The legal notice says content not
  owned by the EU may need the rightholder's permission. Submitters agree to publication
  (https://ec.europa.eu/info/law/better-regulation/specific-privacy-statement), which
  supports private analysis but grants no reuse licence. Quote sparingly.
- The endpoints are undocumented and have no published terms or rate limit.
Either point alone would justify 'gray'.

Privacy: the API returns names (`firstName`, `surname`) for individuals who opted in.
The collector never reads them. `author` is the organisation name for organisations
(always public by the portal's rules, and hashed by the runner anyway) and None for
EU_CITIZEN and NON_EU_CITIZEN. Free text can still contain names the submitter wrote.
"""

import re
import unicodedata
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from pipeline.collectors.base import Collector, Item, SchemaDrift, State, require
from pipeline.http import Http

SITE = "https://ec.europa.eu/info/law/better-regulation"
SEARCH = f"{SITE}/brpapi/searchInitiatives"
GROUP = f"{SITE}/brpapi/groupInitiatives/"
FEEDBACK = f"{SITE}/api/allFeedback"

FIRST_RUN_LOOKBACK_DAYS = 7
SEARCH_PAGE_SIZE = 10        # each initiative carries 24 title translations (~3.5 KB)
FEEDBACK_PAGE_SIZE = 100
MIN_SHARE = 10
CITIZEN_TYPES = {"EU_CITIZEN", "NON_EU_CITIZEN"}
SKIP_PUBLICATION_TYPES = {"OPC_LAUNCHED"}   # questionnaires: no free text in allFeedback
FEEDBACK_STATUSES = {"OPEN", "CLOSED"}

SEARCH_KEYS = ["id", "reference", "shortTitle", "currentStatuses"]
STATUS_KEYS = ["receivingFeedbackStatus", "feedbackEndDate"]
GROUP_KEYS = ["id", "publications"]
PUBLICATION_KEYS = ["id", "type", "frontEndStage", "receivingFeedbackStatus",
                    "totalFeedback", "endDate"]
FEEDBACK_KEYS = ["id", "dateFeedback", "language", "userType", "country", "status",
                 "attachments", "publicationId"]

_ISO3 = dict(pair.split(":") for pair in """
AFG:AF ALA:AX ALB:AL DZA:DZ ASM:AS AND:AD AGO:AO AIA:AI ATA:AQ ATG:AG ARG:AR ARM:AM
ABW:AW AUS:AU AUT:AT AZE:AZ BHS:BS BHR:BH BGD:BD BRB:BB BLR:BY BEL:BE BLZ:BZ BEN:BJ
BMU:BM BTN:BT BOL:BO BES:BQ BIH:BA BWA:BW BVT:BV BRA:BR IOT:IO BRN:BN BGR:BG BFA:BF
BDI:BI CPV:CV KHM:KH CMR:CM CAN:CA CYM:KY CAF:CF TCD:TD CHL:CL CHN:CN CXR:CX CCK:CC
COL:CO COM:KM COG:CG COD:CD COK:CK CRI:CR CIV:CI HRV:HR CUB:CU CUW:CW CYP:CY CZE:CZ
DNK:DK DJI:DJ DMA:DM DOM:DO ECU:EC EGY:EG SLV:SV GNQ:GQ ERI:ER EST:EE SWZ:SZ ETH:ET
FLK:FK FRO:FO FJI:FJ FIN:FI FRA:FR GUF:GF PYF:PF ATF:TF GAB:GA GMB:GM GEO:GE DEU:DE
GHA:GH GIB:GI GRC:GR GRL:GL GRD:GD GLP:GP GUM:GU GTM:GT GGY:GG GIN:GN GNB:GW GUY:GY
HTI:HT HMD:HM VAT:VA HND:HN HKG:HK HUN:HU ISL:IS IND:IN IDN:ID IRN:IR IRQ:IQ IRL:IE
IMN:IM ISR:IL ITA:IT JAM:JM JPN:JP JEY:JE JOR:JO KAZ:KZ KEN:KE KIR:KI PRK:KP KOR:KR
KWT:KW KGZ:KG LAO:LA LVA:LV LBN:LB LSO:LS LBR:LR LBY:LY LIE:LI LTU:LT LUX:LU MAC:MO
MDG:MG MWI:MW MYS:MY MDV:MV MLI:ML MLT:MT MHL:MH MTQ:MQ MRT:MR MUS:MU MYT:YT MEX:MX
FSM:FM MDA:MD MCO:MC MNG:MN MNE:ME MSR:MS MAR:MA MOZ:MZ MMR:MM NAM:NA NRU:NR NPL:NP
NLD:NL NCL:NC NZL:NZ NIC:NI NER:NE NGA:NG NIU:NU NFK:NF MKD:MK MNP:MP NOR:NO OMN:OM
PAK:PK PLW:PW PSE:PS PAN:PA PNG:PG PRY:PY PER:PE PHL:PH PCN:PN POL:PL PRT:PT PRI:PR
QAT:QA REU:RE ROU:RO RUS:RU RWA:RW BLM:BL SHN:SH KNA:KN LCA:LC MAF:MF SPM:PM VCT:VC
WSM:WS SMR:SM STP:ST SAU:SA SEN:SN SRB:RS SYC:SC SLE:SL SGP:SG SXM:SX SVK:SK SVN:SI
SLB:SB SOM:SO ZAF:ZA SGS:GS SSD:SS ESP:ES LKA:LK SDN:SD SUR:SR SJM:SJ SWE:SE CHE:CH
SYR:SY TWN:TW TJK:TJ TZA:TZ THA:TH TLS:TL TGO:TG TKL:TK TON:TO TTO:TT TUN:TN TUR:TR
TKM:TM TCA:TC TUV:TV UGA:UG UKR:UA ARE:AE GBR:GB USA:US UMI:UM URY:UY UZB:UZ VUT:VU
VEN:VE VNM:VN VGB:VG VIR:VI WLF:WF ESH:EH YEM:YE ZMB:ZM ZWE:ZW XKX:XK
""".split())


def iso2(code: Any) -> str | None:
    """ISO 3166-1 alpha-3 (the API's form) or alpha-2 to upper-case alpha-2."""
    if not isinstance(code, str):
        return None
    code = code.strip().upper()
    if len(code) == 2 and code.isalpha():
        return code
    return _ISO3.get(code)


def _last_sunday(year: int, month: int) -> date:
    d = date(year, month, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def brussels_to_utc(stamp: str) -> str:
    """'YYYY/MM/DD HH:MM:SS' in Brussels local time to UTC ISO 8601.

    EU summer time runs from the last Sunday of March, 02:00 local, to the last Sunday
    of October, 03:00 local. Done by hand because Windows Python lacks a tz database.
    """
    local = datetime.strptime(stamp, "%Y/%m/%d %H:%M:%S")
    start = datetime.combine(_last_sunday(local.year, 3), datetime.min.time()) + timedelta(hours=2)
    end = datetime.combine(_last_sunday(local.year, 10), datetime.min.time()) + timedelta(hours=3)
    offset = 2 if start <= local < end else 1
    return (local - timedelta(hours=offset)).replace(tzinfo=timezone.utc).isoformat()


def initiative_path(initiative_id: int, short_title: str) -> str:
    """The URL slug the portal's frontend builds: '<id>-<Title-With-Dashes>'."""
    s = re.sub(r"[ \\!()<|>/_—–]+", "-", short_title)
    s = re.sub(r"[º\"‘’'.,;:*„“”&«»]+", "", s)
    s = re.sub(r"-+", "-", s)
    s = unicodedata.normalize("NFD", f"{initiative_id}-{s}")
    s = re.sub(r"[\u0300-\u036f]", "", s)
    return quote(s, safe="-")


def english_title(init: dict) -> str:
    for t in init.get("initiativeTranslations") or []:
        if (isinstance(t, dict) and t.get("language") == "EN"
                and t.get("field") == "SHORT_TITLE" and (t.get("value") or "").strip()):
            return t["value"].strip()
    return (init["shortTitle"] or "").strip()


def feedback_item(f: dict, init: dict, pub: dict) -> Item | None:
    """Map one allFeedback entry to an Item; None when it carries no usable text.

    Never reads firstName, surname, or login: individuals stay anonymous.
    """
    require(f, FEEDBACK_KEYS, "hys feedback")
    if f["status"] != "PUBLISHED":
        return None
    body = f.get("feedback") or ""
    if not body.strip():
        return None
    user_type = f["userType"]
    author = None
    if user_type not in CITIZEN_TYPES:
        require(f, ["organization"], f"hys feedback ({user_type})")
        author = (f["organization"] or "").strip() or None
    lang_raw = f["language"]
    lang = lang_raw.lower() if isinstance(lang_raw, str) and re.fullmatch(r"[A-Za-z]{2}", lang_raw) else None
    init_id = int(init["id"])
    fid = int(f["id"])
    extra: dict[str, Any] = {
        "initiative_id": init_id,
        "initiative_reference": init["reference"],
        "publication_id": int(pub["id"]),
        "feedback_stage": pub["type"],
        "stage": pub["frontEndStage"],
        "feedback_window": pub["receivingFeedbackStatus"],
        "user_type": user_type,
        "topic": [t.get("label") for t in init.get("topics") or [] if isinstance(t, dict)],
        "country_raw": f["country"],
    }
    for src, dst in (("companySize", "organisation_size"), ("scope", "organisation_scope"),
                     ("governanceLevel", "governance_level"), ("trNumber", "transparency_register")):
        if f.get(src):
            extra[dst] = f[src]
    translated = f.get("feedbackTextUserLanguage")
    if translated and lang != "en":
        extra["text_en_machine"] = translated
    return Item(
        source_id=str(fid),
        url=f"{SITE}/have-your-say/initiatives/"
            f"{initiative_path(init_id, init['shortTitle'] or '')}/F{fid}_en",
        title=english_title(init),
        body=body,
        author=author,
        created_at=brussels_to_utc(f["dateFeedback"]),
        lang=lang,
        country=iso2(f["country"]),
        metrics={"attachments": len(f["attachments"] or [])},
        extra=extra,
    )


class EuHaveYourSay(Collector):
    name = "eu_haveyoursay"
    license = "Feedback (c) submitters, published with consent; EC metadata CC BY 4.0 (2011/833/EU)"
    tos_class = "gray"
    regions = ["EU"]
    min_interval = 1.0

    def fetch(self, http: Http, state: State) -> Iterator[Item]:
        self._state = state
        http.check_robots(SEARCH)
        since = state.get("since") or (
            datetime.now(timezone.utc) - timedelta(days=FIRST_RUN_LOOKBACK_DAYS)
        ).strftime("%Y/%m/%d")
        state.set("since", since)   # pin the first-run default
        remaining = self.max_items
        newest_day = since
        visited: set[int] = set()
        page = 0
        while True:
            res = self._search(http, {"feedbackOpenDateFrom": since}, page)
            total = res["totalElements"]
            for i, init in enumerate(res["content"]):
                require(init, SEARCH_KEYS, "hys initiative")
                share = min(remaining, max(MIN_SHARE, remaining // max(1, total - len(visited))))
                items, newest = self._initiative(http, state, init, since, share)
                visited.add(int(init["id"]))
                remaining -= len(items)
                if newest:
                    newest_day = max(newest_day, newest[:10])
                finished = res["last"] and i == len(res["content"]) - 1
                if finished or remaining <= 0:
                    # Set before yielding: the runner stops at max_items and never resumes.
                    state.set("since", self._next_since(
                        http, since, newest_day, None if finished else visited))
                    yield from items
                    return
                yield from items
            if res["last"] or not res["content"]:
                return
            page += 1

    def _search(self, http: Http, filters: dict, page: int) -> dict:
        resp = http.get(SEARCH, params={
            **filters, "language": "EN", "page": page, "size": SEARCH_PAGE_SIZE})
        if resp.status_code == 406:
            # The search answers an empty result with 406 "The feedback is mandatory".
            return {"content": [], "totalElements": 0, "last": True}
        resp.raise_for_status()
        data = resp.json()
        require(data, ["initiativeResultDtoPage"], "hys search")
        res = data["initiativeResultDtoPage"]
        require(res, ["content", "totalElements", "last"], "hys search page")
        if not isinstance(res["content"], list):
            raise SchemaDrift("hys search page: content is not a list")
        return res

    def _next_since(self, http: Http, since: str, newest_day: str,
                    visited: set[int] | None) -> str:
        """Advance discovery to the newest feedback day, but never past the closing day
        of a closed initiative this run left unvisited (open ones close after today).

        `visited` is None when the run visited every discovered initiative.
        """
        nxt = newest_day
        if visited is not None:
            self._pin_unvisited_floors(http, since, visited)
        page = 0
        while visited is not None:
            res = self._search(http, {"feedbackStatus": "CLOSED",
                                      "feedbackOpenDateFrom": since}, page)
            for init in res["content"]:
                require(init, SEARCH_KEYS, "hys initiative")
                if int(init["id"]) in visited:
                    continue
                for s in init["currentStatuses"]:
                    require(s, STATUS_KEYS, "hys initiative status")
                    if s["feedbackEndDate"] and s["feedbackEndDate"][:10] >= since:
                        nxt = min(nxt, s["feedbackEndDate"][:10])
            if res["last"] or not res["content"]:
                break
            page += 1
        return max(since, nxt)

    def _pin_unvisited_floors(self, http: Http, since: str, visited: set[int]) -> None:
        """Remember the current `since` for initiatives this run never reached, so their
        first visit starts there rather than at a later `since` (which would skip feedback
        posted in between)."""
        page = 0
        while True:
            res = self._search(http, {"feedbackOpenDateFrom": since}, page)
            for init in res["content"]:
                require(init, SEARCH_KEYS, "hys initiative")
                iid = int(init["id"])
                if iid not in visited and self._state.get(f"floor:{iid}") is None:
                    self._state.set(f"floor:{iid}", since)
            if res["last"] or not res["content"]:
                return
            page += 1

    def _initiative(self, http: Http, state: State, init: dict, since: str,
                    share: int) -> tuple[list[Item], str | None]:
        statuses = init["currentStatuses"]
        if not isinstance(statuses, list):
            raise SchemaDrift("hys initiative: currentStatuses is not a list")
        for s in statuses:
            require(s, STATUS_KEYS, "hys initiative status")
        if not any(s["receivingFeedbackStatus"] in FEEDBACK_STATUSES for s in statuses):
            return [], None   # upcoming or disabled: nothing to read yet
        resp = http.get(f"{GROUP}{int(init['id'])}")
        resp.raise_for_status()
        group = resp.json()
        require(group, GROUP_KEYS, "hys group")
        if not isinstance(group["publications"], list):
            raise SchemaDrift("hys group: publications is not a list")
        pubs = []
        for p in group["publications"]:
            require(p, PUBLICATION_KEYS, "hys publication")
            if (p["type"] not in SKIP_PUBLICATION_TYPES
                    and p["receivingFeedbackStatus"] in FEEDBACK_STATUSES
                    and (p["totalFeedback"] or 0) > 0
                    and (p["endDate"] is None or p["endDate"][:10] >= since)):
                pubs.append(p)
        items: list[Item] = []
        newest: str | None = None
        for n, pub in enumerate(pubs):
            left = share - len(items)
            if left <= 0:
                break
            got, pub_newest = self._publication(
                http, state, init, pub, since, max(1, left // (len(pubs) - n)))
            items += got
            if pub_newest and (newest is None or pub_newest > newest):
                newest = pub_newest
        return items, newest

    def _publication(self, http: Http, state: State, init: dict, pub: dict, since: str,
                     share: int) -> tuple[list[Item], str | None]:
        key = f"pub:{int(pub['id'])}"
        floor = state.get(f"floor:{int(init['id'])}") or since
        cur_date, cur_id = (state.get(key) or f"{floor} 00:00:00|0").split("|")
        cursor = (cur_date, int(cur_id))
        size = min(FEEDBACK_PAGE_SIZE, share)  # constant per publication: pages are offsets
        out: list[Item] = []
        newest: tuple[str, int] | None = None
        page = 0
        while len(out) < share:
            resp = http.get(FEEDBACK, params={
                "publicationId": int(pub["id"]), "keywords": "", "language": "EN",
                "page": page, "size": size, "sort": "dateFeedback,DESC",
            })
            resp.raise_for_status()
            data = resp.json()
            require(data, ["content", "last"], "hys feedback page")
            content = data["content"]
            if not isinstance(content, list):
                raise SchemaDrift("hys feedback page: content is not a list")
            # Attachment-only items lack `feedback`; a page where none has it means a rename.
            if len(content) >= 5 and not any(isinstance(f, dict) and "feedback" in f for f in content):
                raise SchemaDrift("hys feedback page: no item has a 'feedback' field")
            stop = False
            for f in content:
                require(f, FEEDBACK_KEYS, "hys feedback")
                stamp = (f["dateFeedback"], int(f["id"]))
                if stamp[0] < cursor[0]:
                    stop = True
                    break
                if stamp <= cursor:
                    continue
                if f["status"] != "PUBLISHED":
                    continue  # not yet visible: leave the cursor behind it so a later run sees it
                newest = max(newest, stamp) if newest else stamp
                item = feedback_item(f, init, pub)
                if item is not None:
                    out.append(item)
                    if len(out) >= share:
                        break
            if stop or data["last"] or not content:
                break
            page += 1
        if newest:
            state.set(key, f"{newest[0]}|{newest[1]}")
        return out, newest[0] if newest else None
