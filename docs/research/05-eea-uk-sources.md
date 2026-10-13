# 05 — EEA and UK data sources

Stage 0 research, round 2. Web searches and direct test requests ran on 2026-10-13; a
"tested" note means a live request on that date returned current data. Items marked
**[unverified]** come from memory or a single secondary source.

## Summary

The UK publishes the cleanest problem signal in Europe. Parliament's petitions API, the
Financial Ombudsman's 412,000 published decisions, and GOV.UK's search API all answered
keyless requests today, and most UK government data carries the Open Government Licence
(OGL). The EU contributes less consumer voice but one unusual asset: the Commission's
*Have Your Say* portal, whose undocumented JSON API returns the full text of feedback
from citizens and companies on every draft rule, in 24 languages. National consumer data
disappoints. France's SignalConso publishes 1.7M reports but only as category codes, and
the big forums (Mumsnet, gutefrage.net, Tweakers) block or forbid automated access.
Multilingual text costs little: the extraction LLM reads it natively, and a small
CPU embedding model covers clustering.

## How to read the tables

Same legend as [01-data-sources.md](01-data-sources.md): **P** = names a problem
directly; **T** = shows a trend or demand shift; **V** = validates or sizes something
found elsewhere. All sources below cost nothing unless the table says otherwise.

---

## 1. Complaints and ombudsmen

| Source | Signal | Access | Licence / ToS | Update | Languages | Status |
|---|---|---|---|---|---|---|
| **UK Financial Ombudsman Service (FOS) decisions** | P — full-text final decisions on complaints against banks, insurers, lenders, and payment firms; each states the complaint, the firm's answer, and the outcome | HTML search plus one PDF per decision (`DRN-` IDs); no API or bulk export ([search](https://www.financial-ombudsman.org.uk/businesses/resolving-complaint/ombudsman-decisions)) | Website licence unstated; FOS reports use OGL v3 ([annual report](https://www.financial-ombudsman.org.uk/files/324642/Financial-Ombudsman-Service-Annual-Report-and-Accounts-2024-25.pdf)). robots.txt blocks only a few PDFs. Personal analysis looks safe; republishing text **[unverified]** | Weekly | EN | Tested: search returned 412,765 decisions, newest dated September 2026 |
| **FCA complaints data** | T/V — complaint counts by product and by firm (firms with 500+ complaints per half-year) | Spreadsheets on [fca.org.uk](https://www.fca.org.uk/data/complaints-data) and [data.gov.uk](https://www.data.gov.uk/dataset/d2861273-d9ba-497f-ae72-4bed851db171/fca-firm-complaints-data-2025-h2-1-july-to-31-december-2025) | OGL | Half-yearly; next release October 22, 2026 | EN | Search-verified. 2025 H2: 1.87M complaints |
| **Ofcom telecoms complaints** | T — complaints per 100,000 customers by provider and service | PDF and web report ([Ofcom](https://www.ofcom.org.uk/research-and-data/multi-sector-research/telecoms-complaints-data)) | OGL **[unverified]** | Quarterly, moving to half-yearly in 2027 ([proposal](https://www.ofcom.org.uk/siteassets/resources/documents/research-and-data/data/statistics/2025/affordability-of-communication-services/proposed-changes-to-the-quarterly-telecoms-and-tv-complaints-report.pdf)) | EN | No CSV found |
| **Ofgem, Ofwat/CCW, Energy Ombudsman** | T — supplier complaint ratios | Periodic reports **[unverified format]** | OGL **[unverified]** | Quarterly–annual | EN | Not tested |
| **CMA cases** | T — markets under investigation, mergers, consumer enforcement | GOV.UK search API, `filter_format=cma_case` ([test URL](https://www.gov.uk/api/search.json?filter_format=cma_case&count=10&order=-public_timestamp)) | OGL | Daily | EN | Tested: newest case dated 2026-10-12 |
| **Citizens Advice** | P/T — what people seek advice on, by issue | Cost-of-living dashboard; scattered local reports on [data.gov.uk](https://ckan.publishing.service.gov.uk/dataset/citizens-advice) with no licence stated | Unclear | Monthly | EN | No national open feed found |
| **EU Safety Gate (ex-RAPEX)** | P — dangerous non-food products withdrawn from the EU market, with hazard, product category, and origin | Weekly XML reports since 2005 ([index](https://ec.europa.eu/safety-gate-alerts/api/download/weeklyReport/list/xml/en)); undocumented JSON search used by scrapers ([Apify](https://apify.com/studio-amba/safety-gate-scraper)) | Commission reuse decision 2011/833/EU **[unverified for this dataset]** | Weekly (Fridays) | EN plus product names in original language | Tested: XML index answered |
| **France SignalConso** | T — 1.73M consumer reports by category, sub-category, and département | Opendatasoft API on [data.economie.gouv.fr](https://data.economie.gouv.fr/explore/dataset/signalconso/) | Licence Ouverte (Etalab) | Last refresh May 10, 2026 — five months stale | FR codes | Tested: records carry category paths (`AchatInternet > Le_site_internet_en_luimeme`) but **no free text** |
| **EU ODR platform** | — | Closed July 20, 2025; data deleted ([Regulation 2024/3228](https://eur-lex.europa.eu/eli/reg/2024/3228/oj/eng), [Taylor Wessing](https://www.taylorwessing.com/en/insights-and-events/insights/2025/01/abolition-of-the-odr-platform)) | — | — | — | Gone |
| **ECC-Net, EBA/ESMA/EIOPA consumer-trends reports** | T — cross-border complaint themes; annual top consumer issues in banking, investments, insurance | PDF reports **[unverified]** | 2011/833/EU-style reuse **[unverified]** | Annual | EN | Read by hand, not collected |
| **Germany Verbraucherzentrale, Netherlands ACM/ConsuWijzer** | T — complaint themes | Press releases and annual reports; no open complaint data found **[unverified]** | — | Irregular | DE, NL | Skip as collectors |

FOS decisions match CFPB narratives in kind and exceed them in depth: each runs one to
four pages and quotes both sides. Their weakness is access. Collecting them means paging
an HTML search and downloading PDFs, a scraper we must maintain.

## 2. Petitions, consultations, and the policy pipeline

Petitions state public problems in the petitioner's own words and attach a vote count.
Consultation feedback does the same for businesses facing a new rule.

| Source | Signal | Access | Licence / ToS | Update | Languages | Status |
|---|---|---|---|---|---|---|
| **UK Parliament petitions** | P — "action" plus "background" text, signature count, government response, rejection reason | Keyless JSON: `petition.parliament.uk/petitions.json?state=open&page=N`, 50 per page; per-petition JSON adds signatures by constituency | OGL v3 (stated on the [help page](https://petition.parliament.uk/help)) | Live | EN | Tested: 88 pages (~4,400 open petitions); also `state=closed` and `rejected` |
| **EU Have Your Say** | P — feedback from citizens, companies, NGOs, and trade bodies on Commission initiatives; companies often state costs and compliance burdens | Undocumented JSON: `brpapi/searchInitiatives` lists initiatives, `brpapi/groupInitiatives/{id}` lists publications, `api/allFeedback?publicationId=N` returns paged feedback with `userType`, `country`, `language` | Commission content under [2011/833/EU](https://eur-lex.europa.eu/eli/dec/2011/833/oj); feedback text belongs to its authors and contains names. Fine for private analysis; quote sparingly **[unverified terms]** | Live | 24 EU languages, mostly EN | Tested: 3,571 closed initiatives; feedback posted 2026-10-13 returned within minutes. No documented rate limit; pace politely |
| **GOV.UK consultations** | T/P — open consultations name the problem government wants to fix | GOV.UK search API: `filter_content_store_document_type=open_consultation`; Content API for full text | OGL | Daily | EN | Tested: newest dated 2026-10-12 |
| **UK Parliament written questions** | P/T — MPs relay constituents' problems to ministers | Keyless REST ([questions-statements-api](https://questions-statements-api.parliament.uk/api/writtenquestions/questions?take=20)) | Open Parliament Licence **[unverified]** | Daily | EN | Tested: 4,042 questions tabled since October 1 |
| **legislation.gov.uk** | T — new UK laws and statutory instruments | Atom feeds and XML API ([new legislation feed](https://www.legislation.gov.uk/new/data.feed)) | OGL | Daily | EN | Tested: feed answered |
| **EUR-Lex / CELLAR** | T — EU acts and application dates | SPARQL endpoint and REST **[unverified details]** | 2011/833/EU | Daily | 24 | Not tested; *Have Your Say* covers the pipeline earlier |
| **European Citizens' Initiative** | P — citizen-proposed EU laws with supporter counts | Keyless JSON ([register API](https://register.eci.ec.europa.eu/core/api/register/search/ALL/EN/0/50)) | 2011/833/EU | Live | 24 | Tested: only 136 registered initiatives ever. Too few to collect weekly |
| **European Parliament open data** | T — questions, votes, documents | API v2 ([data.europarl.europa.eu](https://data.europarl.europa.eu/)) | Reuse allowed **[unverified]** | Daily | 24 | Tested: questions endpoint returned HTTP 500 |
| **National petition sites** (Bundestag ePetitionen, Scottish and Welsh parliaments) | P | No public API found **[unverified]** | — | — | DE, EN, CY | Skip for now |

## 3. App reviews in European storefronts

Apple's review RSS, already in the v1 set, handles Europe by swapping the country code:
`itunes.apple.com/{cc}/rss/customerreviews/page=N/id={id}/sortby=mostrecent/json`. A test
on 2026-10-13 returned 50 current reviews from `gb` and 50 from `de`; the German reviews
arrived in German. Each storefront holds its own 500-review window, so the collector loops
over (app, country) pairs and stores a `country` column. The feed carries no language
field; detect language at ingest (a library such as `lingua` or the LLM itself). Codes for
the EEA and UK: `gb`, the 27 EU codes, `no`, `is`, and `li` (Liechtenstein storefront
**[unverified]**). Polling all 31 storefronts multiplies requests by 31, so start with
`gb`, `de`, `fr`, `nl`, `es`, `it`, `pl`, and `se`.

## 4. Forums and communities

| Source | Signal | Access | ToS | Verdict |
|---|---|---|---|---|
| **MoneySavingExpert forums** (UK) | P — household finance, energy, consumer disputes; high pain density | Public Vanilla API: `forums.moneysavingexpert.com/api/v2/discussions` returned JSON with full post bodies, tested 2026-10-13 | Terms allow "personal, non-commercial use only" ([MSE terms](https://moneysavingexpert.com/site/terms-conditions/), updated May 22, 2026); robots.txt blocks search and profiles, not discussions | **Gray.** Acceptable for private research at low volume; drop if the project turns commercial |
| **Mumsnet** (UK) | P — parenting, family, work, housing | HTML only | Terms forbid scraping "for any purpose without express approval"; Mumsnet pursues legal action against OpenAI over scraping ([TechRadar](https://www.techradar.com/pro/mumsnet-is-launching-a-lawsuit-against-openai-for-scraping-its-content)) | Skip |
| **HotUKDeals** | T/P — what UK shoppers want cheaper; complaint threads about retailers | HTML; robots.txt blocks `/graphql` | Scraping clauses unread **[unverified]** | Skip for v1 |
| **gutefrage.net** (DE) | P — German Q&A, huge volume | Cloudflare challenge blocked even robots.txt on 2026-10-13 | [AGB](https://gutefrage.net/agb) clauses on automation unread | Skip |
| **Tweakers** (NL) | P — Dutch tech and consumer electronics | No official API; unofficial wrappers only ([PyPI](https://www.pypi.org/project/tweakers/0.2.1/)) | Unread **[unverified]** | Skip |
| **Reddit country subs** (r/unitedkingdom, r/AskUK, r/de, r/thenetherlands, r/france) | P | Same Reddit API gate described in 01 | Responsible Builder Policy | Include in the pending Reddit application |

## 5. Macro, procurement, companies, and research ("why now")

These sources explain timing and size markets; none names a person's problem. Treat them
as on-demand lookups, as 01 recommends for FRED.

| Source | Signal | Access | Licence | Update | Status |
|---|---|---|---|---|---|
| **Eurostat** | T — prices, household spending, business demography, digital uptake for every EEA country | Keyless JSON-stat and SDMX ([API](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr)) | CC BY 4.0 **[unverified]** | Monthly–annual | Tested |
| **ONS** | T — UK statistics | Keyless REST ([api.beta.ons.gov.uk](https://api.beta.ons.gov.uk/v1/datasets)); many series only as spreadsheets | OGL | Weekly–annual | Tested |
| **ECB Data Portal** | T — rates, lending, payments | Keyless SDMX/CSV ([data-api.ecb.europa.eu](https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?lastNObservations=1&format=csvdata)) | Free reuse with attribution **[unverified]** | Daily | Tested: rate for 2026-10-12 |
| **TED (EU tenders)** | P/T — what public buyers across the EEA pay for; each notice describes a need, a budget, and a deadline | Anonymous search: `POST api.ted.europa.eu/v3/notices/search` | 2011/833/EU | Daily | Tested: notice 674225-2026 returned |
| **UK Find a Tender and Contracts Finder** | P/T — UK public-sector buying | Keyless OCDS JSON ([Find a Tender](https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages), [Contracts Finder](https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search)) | OGL | Daily | Both tested |
| **Companies House** | V — incorporations by SIC code, a crowding and new-entrant signal | REST with free key (HTTP 401 without one, tested); free monthly bulk snapshot | OGL | Daily | Rate limit 600 requests per 5 minutes **[unverified]** |
| **OpenCorporates** | V | API needs a paid plan for most uses **[unverified]** | Share-alike / commercial | Daily | Skip; Companies House suffices for the UK |
| **CORDIS** | T — EU-funded research projects by topic | Bulk downloads and API on data.europa.eu **[unverified]** | 2011/833/EU | Monthly | Not tested |
| **EPO OPS, EUIPO** | T — patents and trademarks | OPS: free registration, weekly data quota **[unverified]** | EPO terms | Weekly | Not tested; low priority, as with USPTO in 01 |

## 6. Job postings

| Source | Signal | Access | Licence | Status |
|---|---|---|---|---|
| **Adzuna API** | P/T — individual postings | Same free key as 01; country path segment covers `gb`, `de`, `fr`, `nl`, `at`, `be`, `it`, `es`, `pl`, `ch` per third-party lists ([Apify listing](https://apify.com/thirdwatch/adzuna-jobs-scraper)) **[unverified against official docs]** | 250 calls/day shared across countries | Extend in v2 |
| **ONS online job adverts (Textkernel)** | T — UK new adverts by occupation and region | Spreadsheets ([ONS](https://www.ons.gov.uk/economy/economicoutputandproductivity/output/datasets/textkernelnewonlinejobadverts)) | OGL | Monthly lookup |
| **Indeed Hiring Lab** | T — postings index for UK, DE, FR, NL, IE, IT, ES, and more | Covered in 01 | CC BY 4.0 | Already in v2 |
| **EURES** | T | No public jobs API found **[unverified]** | — | Skip |

## 7. Multilingual extraction

The extraction LLM needs no translation step. Current frontier and mid-size models read
all 24 EU languages plus Norwegian and Icelandic; instruct them to write the problem
statement in English, keep the original quote verbatim, and record an ISO 639-1
`lang` code. Clustering then runs on English statements, which keeps canonical problems
language-neutral and lets a German review and a British petition land in one cluster.
Two costs remain. Non-Latin scripts (Greek, Bulgarian) consume more tokens per word, and
small or local LLMs extract worse in minor languages, so log extraction confidence per
language and spot-check.

Embeddings still matter for deduplicating raw text and for searching original quotes.
Pick a multilingual model that runs on CPU:

| Model | Size | Dimensions | Licence | Use |
|---|---|---|---|---|
| **`intfloat/multilingual-e5-small`** | 118M parameters | 384 | MIT | **Default.** Fast on CPU, 100+ languages; requires `query:` / `passage:` prefixes ([model card summary](https://www.promptlayer.com/models/multilingual-e5-small)) |
| **`google/embeddinggemma-300m`** | 308M parameters, <200 MB RAM quantized | 768, truncatable | Gemma terms (permissive with use restrictions) | Upgrade if clusters look poor; Google reports it leads open multilingual models under 500M on MTEB ([HF blog](https://huggingface.co/blog/embeddinggemma), [paper](https://arxiv.org/pdf/2509.20354)) |
| `BAAI/bge-m3` | 568M | 1024 | MIT | Strong but slow on CPU; reserve for a GPU or a one-off backfill **[unverified CPU speed]** |

Benchmark the first two on a few hundred of our own records before committing; the
choice changes the vector column width in SQLite.

---

## Recommendations

### v1 additions (free, clean, keyless or near-keyless)

1. **UK Parliament petitions.** Direct problem statements with a built-in demand count
   and a government response, under the OGL, through a JSON API that needs no key.
   Collect open, closed, and rejected petitions; the rejection reasons often hide the
   sharpest grievances.
2. **EU Have Your Say feedback.** The only EU-wide source where businesses describe, in
   writing, what a coming rule will cost them. It replaces Regulations.gov's role for the
   EEA. The API is undocumented, so wrap it in a health check.
3. **Apple App Store reviews, EEA and UK storefronts.** No new collector: add a
   `country` loop to the existing one and start with eight storefronts.
4. **GOV.UK search API (consultations and CMA cases).** One cheap collector supplies the
   UK's policy pipeline and the markets the competition regulator considers broken.

### v2

- **FOS decisions**: the richest European complaint text, worth a careful scraper once v1
  runs. Confirm reuse terms with FOS first.
- **MoneySavingExpert forums** via the Vanilla API, at low volume, flagged `tos_class =
  gray`.
- **UK written questions** and **legislation.gov.uk** as extra policy streams.
- **EU Safety Gate** weekly XML, for product-safety and compliance demand.
- **TED and Find a Tender** as a B2G stream, filtered by CPV codes once Edgar picks a
  sector.
- **Adzuna** across European countries, sharing the 250-call daily budget.
- **Lookups**: Eurostat, ONS, ECB, FCA complaints data, Ofcom complaints, SignalConso
  category counts, Companies House.

### Skip

| Source | Reason |
|---|---|
| EU ODR platform | Closed July 20, 2025; data deleted |
| Mumsnet, gutefrage.net, Tweakers, HotUKDeals | Scraping forbidden, Cloudflare-blocked, or no API; Mumsnet litigates |
| SignalConso as a text source | Category codes only, five months stale |
| Citizens Advice, ECC-Net, EBA/ESMA/EIOPA, Verbraucherzentrale, ACM | Annual PDFs or dashboards; read by hand when a sector demands it |
| European Citizens' Initiative | 136 initiatives in total; too few to collect |
| European Parliament open data | Endpoint failed on test; Have Your Say covers the policy pipeline earlier |
| OpenCorporates, EURES | Paid or no public API |

## Implications for our design

1. **Add `country` and `lang` columns to `documents`.** Country comes from the source
   (storefront, petition constituency, Have Your Say `country` field); language comes
   from the source when given and from detection otherwise. Problem clusters then report
   which markets mention them, which the scoring stage needs.
2. **Extract to English; keep the original.** Store the verbatim quote, its language,
   and the English problem statement side by side. Cluster on the English statement;
   embed the original with `multilingual-e5-small` for deduplication and search.
3. **Treat vote counts as a first-class field.** Petition signatures, Have Your Say
   feedback counts, and review ratings all measure intensity. Normalize them into an
   `engagement` column per source so the tracker can compare growth across sources.
4. **Model the policy pipeline as events with dates.** Consultation closing dates,
   legislation in-force dates, and CMA case milestones mark forced-demand deadlines. A
   small `policy_events` table keyed by jurisdiction lets the "why now" agent cite them.
5. **Expect undocumented APIs to break.** Have Your Say and Safety Gate expose JSON the
   Commission never documented. Their collectors need the health check and
   "last success" timestamp from 01, plus a schema check that fails loudly when fields
   change.
6. **Record licence per row, including OGL and 2011/833/EU.** Nearly every v1 addition
   is OGL or Commission-reusable, which keeps a future commercial path open. MSE and FOS
   enter as `gray` until their terms are confirmed.
7. **Budget stays at $0.** Every recommended source is free. The main cost of EEA
   coverage falls on LLM tokens: more storefronts and multilingual text raise extraction
   volume, so cap records per source per run and sample before scaling.
