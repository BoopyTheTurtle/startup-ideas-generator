# 01 — Data sources for problem and demand discovery

Stage 0 research. Status checked by web search on 2026-10-13. Items marked **[unverified]**
come from memory or a single secondary source and need a check before we build a collector.

## Summary

The sources that point most directly at a *problem* are places where people complain in
their own words: forums, Q&A sites, app reviews, and government complaint databases. Search
demand and macro data point at *trends*; they confirm that a problem is growing but rarely
name it. The best problem sources of 2023 have closed or turned expensive: Reddit now
requires approval for any API access, X charges per post read, and Pushshift is gone. The
free survivors — Hacker News, Stack Exchange, Bluesky, Apple's review feed, and US federal
complaint APIs — give a usable starter set at zero cost.

## How to read the tables

- **Signal**: what the source tells us. **P** = names a problem directly; **T** = shows a
  trend or demand shift; **V** = validates or sizes something found elsewhere.
- **Noise**: share of records useless for problem discovery (low / medium / high).
- **Latency**: how fresh the data is when we can fetch it.

---

## 1. Community pain

People describing frustrations unprompted. Highest signal per record for our purpose.

| Source | Signal | Access | Cost (2026) | Limits / ToS | Latency | Noise |
|---|---|---|---|---|---|---|
| **Hacker News** via Algolia API | P — "I'd pay for", "Ask HN", tooling complaints; skews developer/founder | REST, no key ([hn.algolia.com/api](https://hn.algolia.com/api)) | Free | Undocumented limit (~10k req/h per IP **[unverified]**); no restrictive ToS | Minutes. A test query on 2026-10-13 returned comments from the previous day | Medium |
| **Reddit** official API | P — the richest consumer and SMB complaint corpus | OAuth API | Non-commercial free tier, 100 QPM; commercial by negotiated contract, no public rate card ([socialcrawl](https://www.socialcrawl.dev/blog/reddit-api-key-limits-alternatives-2026), [xpoz](https://www.xpoz.ai/blog/guides/reddit-api-pricing-tiers-and-alternatives/)) | Since Nov 2025 the **Responsible Builder Policy** closed self-service; every new app needs approval, researchers file a ticket ([r/redditdev announcement](https://r.datuan.dev/r/redditdev/comments/1oug31u/introducing_the_responsible_builder_policy_new/npy0o5w/?context=3)). Personal scripts reportedly rarely approved | Real time | Medium–high |
| **Reddit archives**: Arctic Shift, PullPush, Academic Torrents dumps | P — historical Reddit | Keyless API and monthly dumps ([redditapis.com](https://www.redditapis.com/blogs/best-pushshift-alternatives-2026)) | Free | Third-party copies of Reddit content; Reddit's terms do not license this use. **Legal gray zone** — fine for private research reading, risky for anything we publish or sell. Coverage gaps | Weeks to months | Medium–high |
| **Pushshift** | — | Moderators only since May 2023 ([xpoz](https://www.xpoz.ai/blog/tutorials/how-to-get-historical-reddit-data-after-pushshift/)) | — | Closed to us | — | — |
| **Stack Exchange** API | P — what practitioners cannot do with current tools; 170+ sites beyond programming (DIY, cooking, money, parenting) | REST, free key | Free | ~10k req/day with key **[unverified]**. Data dump sits behind login since July 2024, LLM-training use forbidden ([devclass](https://devclass.com/2024/07/30/stack-exchange-restricts-access-to-dump-of-user-contributed-data-as-critics-complain-license-permits-reuse-for-any-purpose)); our use (analysis, not training) appears allowed, but read the terms | Minutes | Low–medium |
| **Bluesky** | P/T — public posts, smaller and tech/media-heavy audience | Public search at `api.bsky.app`, no auth; Jetstream firehose, no auth ([scrapecreators](https://scrapecreators.com/blog/bluesky-scrapers)) | Free | Open protocol, permissive. Jetstream is live only; we keep what we capture | Real time | High |
| **X (Twitter)** | P/T — large, but bot-heavy | Pay-per-use API since Feb 6, 2026; free tier effectively ended ([Open Terms Archive](https://opentermsarchive.org/en/memos/x-replaces-its-dollar200-entry-level-api-plan-with-a-pay-per-use-model/)) | ~$0.005 per post read ([opentweet](https://opentweet.io/x-api-pricing)); 10k posts ≈ $50 | Scraping prohibited by ToS and actively litigated | Real time | High |
| **GitHub Issues/Discussions** | P — feature requests and workarounds in open-source tools | REST/GraphQL, free token | Free | 5,000 req/h authenticated **[unverified]** | Minutes | Medium |
| **Niche forums** (trade forums, Discourse sites, Indie Hackers) | P — vertical pain (trucking, dental offices, landlords) | Discourse sites expose `.json` endpoints; others require scraping | Free | Check each site's robots.txt and ToS; scrape slowly and only public pages | Varies | Low–medium |

## 2. Reviews and complaints

Complaints tied to a named product or company. The government databases are free, legally
clean, and structured — an underrated combination.

| Source | Signal | Access | Cost | Limits / ToS | Latency | Noise |
|---|---|---|---|---|---|---|
| **CFPB Consumer Complaint Database** | P — 18.4M financial-product complaints with narratives (credit reports, debt collection, banking, crypto) | REST + bulk CSV ([API](https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/)) | Free | Public domain. A live query on 2026-10-13 returned a complaint received 2026-10-12, so the database still updates despite 2025 cuts at the agency | Daily | Low |
| **openFDA** (MAUDE device events, drug and food adverse events, recalls) | P — product failures in health and food | REST + bulk ([auth page](https://open.fda.gov/apis/authentication)) | Free | 240 req/min; 1,000/day without key, 120,000/day with key | Weekly–quarterly | Medium (clinical jargon) |
| **NHTSA complaints** | P — vehicle defects in owners' words | REST + bulk flat files ([data.gov](https://catalog.data.gov/dataset/nhtsas-office-of-defects-investigation-odi-complaints-nhtsa-api)) | Free | No published limit; pace politely | Daily–weekly | Low |
| **Apple App Store reviews** | P — users of a specific app describe what fails | Public RSS: `itunes.apple.com/{cc}/rss/customerreviews/id={id}/json` | Free | Latest 500 reviews per app per country only, so we must poll and store ([ScrapingBee](https://www.scrapingbee.com/blog/how-to-scrape-app-store-data/)) | Hours | Medium |
| **Google Play reviews** | P — same, Android | No public feed; the official API serves only apps you own. Third-party scrapers exist (`google-play-scraper`) | Free (scraper) | **Scraping conflicts with Google's ToS** ([Apify note](https://apify.com/pikoulas/google-play)). Low-volume private use is common, but it is a ToS breach | Hours | Medium |
| **G2 / Capterra** | P — B2B software gaps, "what I dislike" sections | G2 API requires a paid vendor subscription with add-on ([Peerbound](https://help.peerbound.com/articles/5436908716)) | Paid, unpublished | Scraping forbidden by ToS; aggressive bot protection | Days | Low |
| **Trustpilot** | P — consumer service failures | Official API tied to business plans; resellers (DataForSEO, Apify) sell scraped reviews at ~$0.50/1k ([DataForSEO](https://dataforseo.com/pricing/business-data/business-data-api-trustpilot-reviews-pricing)) | Paid | Resold data inherits the ToS problem | Days | Medium (fake and incentivized reviews) |
| **Amazon reviews** | P — product shortcomings | PA-API 5 retired in 2026; the replacement Creators API requires an active Associate with sales and exposes no review text ([Amazon](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/paapiv5-deprecation)) | — | Scraping forbidden and technically hard. Academic snapshots (McAuley Amazon Reviews '23) suit offline study **[unverified license]** | — | Medium |

## 3. Search demand

Search data shows *how many* people want something and whether that number grows. It
validates; it seldom discovers, because you must already know what term to query.

| Source | Signal | Access | Cost | Limits / ToS | Latency | Noise |
|---|---|---|---|---|---|---|
| **Google Trends** (official API) | T — relative interest, 5-year window, regional | Alpha since July 2025, approved testers only, still alpha as of Aug–Sep 2026; no pricing or GA date ([konabayev](https://konabayev.com/blog/google-trends-api-landscape-2026/), [Google](https://developers.google.com/search/blog/2025/07/trends-api)) | Free (alpha) | Apply; access rolling and limited | Daily | Low |
| **Google Trends** (unofficial) | T | `pytrends` archived April 2025; `trendspy` and similar maintained forks scrape the web endpoints ([apiserpent](https://apiserpent.com/blog/pytrends-dead-google-trends-data-2026)) | Free | Unofficial, breaks without notice, 429s common; against Google's ToS | Daily | Low |
| **DataForSEO** | V — absolute Google Ads volumes, keyword ideas, Trends proxy | Pay-as-you-go API, $50 minimum deposit ([costbench](https://www.costbench.com/software/seo-tools/dataforseo/)) | ~$0.05 per 1,000 keywords (standard queue); Trends ~$0.00225/task. Rates rose ~20% on July 1, 2026 ([DataForSEO](https://dataforseo.com/update/pricing-update-in-dataforseo-apis)) | Licensed resale; clean | Monthly volumes | Low |
| **Glimpse** | V — absolute volumes on top of Trends | API only on Enterprise, quote-only ([outlierkit](https://outlierkit.com/resources/glimpse-pricing/)) | $99+/mo UI; API unpublished | — | Weekly | Low |
| **Exploding Topics** | T — curated rising topics | API add-on to $249/mo Business plan ([vendor](https://explodingtopics.com/feature/et-api)) | $249/mo + API | Commercial use needs custom deal | Weekly | Low, but pre-digested: everyone sees the same list |
| **Wikipedia pageviews** | T — attention shifts on any topic, all languages | REST (Wikimedia), no key | Free | Polite User-Agent required **[unverified limits]** | Daily | Low |

## 4. Labor market

Job postings reveal what organizations struggle to do in-house and are willing to pay for.
A spike in postings for a role ("prior authorization specialist") marks a workflow ripe for
software.

| Source | Signal | Access | Cost | Limits / ToS | Latency | Noise |
|---|---|---|---|---|---|---|
| **Indeed Hiring Lab** | T — postings index by country and sector | CSV on [GitHub](https://github.com/hiring-lab/job_postings_tracker), refreshed weekly; also on FRED | Free | GitHub data CC BY 4.0; FRED marks it pre-approval for redistribution — conflicting | Weekly | Low |
| **Adzuna API** | P/T — individual postings, 16+ countries | REST, free key | Free | 250 hits/day, 2,500/month; personal research allowed with attribution ([terms](https://developer.adzuna.com/docs/terms_of_service)) | Daily | Medium |
| **USAJobs, HN "Who is hiring"** | P/T — narrow slices | Free APIs | Free | Clean | Daily / monthly | Low |
| **BLS (JOLTS, OES, projections)** | T — occupation growth, wages | API v2, free key | Free | ~500 queries/day **[unverified]** | Monthly–annual | Low |
| **O\*NET** | V — tasks per occupation; maps "who does this job, what do they do all day" | Web services + bulk download | Free | Attribution (CC BY 4.0) | Quarterly | Low |
| **Lightcast, Revelio, TheirStack** | T — full posting corpora with skills | Sales-led ([signalbase](https://www.trysignalbase.com/best-job-posting-data-providers)) | Thousands/yr | Contract | Daily | Low |

## 5. Regulation and policy

New rules create forced demand: every compliance deadline makes someone buy something. The
public comment record also contains businesses explaining, in detail, what a rule will cost
them.

| Source | Signal | Access | Cost | Limits / ToS | Latency | Noise |
|---|---|---|---|---|---|---|
| **Federal Register API** | T/P — proposed and final US rules, effective dates | REST, no key | Free | Public domain **[unverified limits]** | Daily | Medium |
| **Regulations.gov API v4** | P — public comments, often from affected businesses | REST, free api.data.gov key | Free | 1,000 req/h; comment text fetched one at a time; no bulk download ([vaquill](https://www.vaquill.ai/blog/regulations-gov-api-guide-rulemaking-data), [willjobs](https://github.com/willjobs/public-comments-project/blob/main/blogposts/post2/README.md)) | Daily | Medium |
| **EUR-Lex / EU "Have your say"** | T — EU regulation pipeline | SPARQL/REST, RSS **[unverified details]** | Free | Clean | Daily | Medium |
| **State legislatures (LegiScan)** | T | API, free tier **[unverified]** | Free–paid | — | Daily | High |

## 6. Funding and startups

These show where capital and founders already flow. Use them to check crowding, never to
find problems — by the time a round is announced, the problem is known.

| Source | Signal | Access | Cost | Limits / ToS | Latency | Noise |
|---|---|---|---|---|---|---|
| **SEC EDGAR Form D** | T — private raises by US companies, with industry codes, often pre-announcement | Full-text search, JSON APIs, quarterly Form D datasets | Free | 10 req/s, declared User-Agent required **[from SEC fair-access policy, not rechecked]** | Daily | Medium (funds, real estate) |
| **YC directory** (yc-oss) | T — what YC funds, by batch and tag | Static JSON, updated daily from YC's Algolia index ([skills.sh](https://skills.sh/himself65/finance-skills/yc-reader)) | Free | Unofficial mirror | Daily | Low |
| **Product Hunt API v2** | T — launches, upvotes, comments asking for features | GraphQL, token | Free | **Non-commercial only**; scraping banned by ToS ([docs](https://www.producthunt.com/v2/docs)) | Daily | High (launch hype) |
| **Crunchbase** | T | Free API tier retired; full API ~$30k+/yr ([crustdata](https://crustdata.com/blog/crunchbase-alternatives)) | Expensive | Contract | Daily | Low |
| **Dealroom, Harmonic, Tracxn** | T | Sales-led | Expensive | Contract | Daily | Low |

## 7. Patents and research

Research shows capabilities becoming possible, which supplies the "why now" half of an idea.
It never shows what anyone wants.

| Source | Signal | Access | Cost | Limits / ToS | Latency | Noise |
|---|---|---|---|---|---|---|
| **OpenAlex** | T — research output by topic, citations | API now needs a key and meters usage (~$1/day free allowance) since Feb 2026; bulk snapshot remains free ([CASRAI](https://casrai.org/news/openalex-api-keys-mandatory-usage-based-pricing-2026)) | Free tier | CC0 data | Weekly | Medium |
| **arXiv API** | T — preprints, fastest for AI/CS | REST/OAI-PMH | Free | 1 request per 3 s **[unverified]** | Daily | Medium |
| **USPTO Open Data Portal / PatentsView** | T — filings by technology class | API + bulk; migrated to data.uspto.gov in 2025 **[unverified]** | Free | Key required | Weekly | High |
| **Google Patents** | T | BigQuery public dataset | BigQuery free tier (1 TB/mo queries) **[unverified]** | Clean | Monthly | High |

## 8. Macro, trade, and shipping

These describe economies, not people. They earn a place only as context.

| Source | Signal | Access | Cost | Limits / ToS | Latency |
|---|---|---|---|---|---|
| **FRED** | T — 800k+ series (prices, spending, rates); hosts Indeed and other private series | REST, free key | Free | ~120 req/min **[unverified]** | Daily–quarterly |
| **World Bank, OECD, Eurostat, IMF** | T — cross-country development and price data | REST (SDMX) | Free | Clean | Monthly–annual |
| **UN Comtrade** | T — goods trade by HS code and country | REST; free key gives 500 calls/day, up to 100k records/call ([comtradr](https://github.com/ropensci/comtradr/blob/HEAD/vignettes/comtradr.Rmd)) | Free | Figures conflict across sources | Monthly, 2–6 month lag |
| **US Census trade (USA Trade)** | T — US imports/exports by HS code | REST | Free | Clean | Monthly, ~5 week lag |
| **Freight indices** (Drewry WCI, Freightos FBX) | T — container rates | Headline values free on web; history paid **[unverified]** | Free–paid | ToS varies | Weekly |
| **AIS vessel tracking** (aisstream.io etc.) | T — ship movements | WebSocket | Free tiers **[unverified]** | — | Real time |

**Where macro data helps and where it misleads.** Macro and cargo data tell us that
conditions changed — tariffs rose on a product class, freight costs doubled, a country's
imports of solar panels tripled. That supports two uses: it explains *why now* for a problem
already found elsewhere, and it identifies B2B sectors under stress (importers squeezed by a
tariff need sourcing, compliance, and landed-cost tools). It fails as a discovery source
for three reasons. First, it carries no voice: a falling HS code shows no person and no
frustration. Second, it lags by months. Third, every consultant reads the same series, so
any insight is already priced in. Blog posts list AIS and port data because the maps look
impressive; for consumer problems they add nothing. Keep FRED and Comtrade as on-demand
lookups the dossier agent can call, not weekly collectors.

## 9. E-commerce

| Source | Signal | Access | Cost | Notes |
|---|---|---|---|---|
| **Amazon Best Sellers / Movers & Shakers** | T — rising product categories | Scrape only | Free | Forbidden by ToS, heavily defended. Skip |
| **Etsy Open API v3** | T — handmade/niche demand | REST, key + app approval **[unverified]** | Free | Listings, not reviews; weak problem signal |
| **Shopify app store reviews** | P — merchant pain | Scrape | Free | Small, high-signal for SMB e-commerce; ToS unclear **[unverified]** |

---

## Ranking

### Starter set (phase 1, all free, all API-clean)

1. **Hacker News (Algolia).** Free, keyless, current, and full of explicit wants ("Ask HN:
   what tool do you wish existed"). Skews technical, so it seeds developer and founder
   problems first.
2. **Stack Exchange API.** Covers dozens of non-tech domains with questions phrased as
   problems; votes and "unanswered" status measure pain intensity.
3. **US complaint databases: CFPB, openFDA, NHTSA.** Structured, free, legally clean, and
   tagged by product and company. They reach consumers in finance, health, and autos —
   people HN never hears from.
4. **Apple App Store reviews.** Poll the RSS feed for a curated app list per category;
   one-star and two-star reviews name exact failures of incumbents.
5. **Bluesky search and Jetstream.** The only free, permissive, real-time social firehose
   left. Noisy, but it fills the "general public" gap Reddit used to fill.
6. **Federal Register + Regulations.gov.** A weekly diff of new rules with compliance dates
   produces forced-demand candidates, and the comments show who is affected.

### Next wave (after phase 1 works)

- **Reddit, by the legitimate route.** File the researcher access ticket now; approval takes
  weeks. Reddit remains the best single pain source, and losing it is our largest gap.
- **DataForSEO** (~$50 deposit lasts months at our volume) to put absolute search volume on
  shortlisted problems. Apply to the **Google Trends API alpha** in parallel.
- **Adzuna + Indeed Hiring Lab + O\*NET** for B2B workflow pain.
- **GitHub Issues** for developer-tool gaps; **niche Discourse forums** chosen per sector
  once the human steers toward one.
- **EDGAR Form D + YC directory** as a crowding check in the dossier stage.
- **FRED, Comtrade, OpenAlex** as on-demand lookups for the dossier's "why now" section.

### Skip, and why

| Source | Reason |
|---|---|
| X API | Pay-per-read (~$50 per 10k posts), bot-heavy, scraping litigated. Bluesky covers the same function free |
| Pushshift | Closed to non-moderators |
| Arctic Shift / PullPush as a primary feed | Unlicensed Reddit copies; acceptable for one-off exploratory reading, not for a durable pipeline |
| G2, Capterra, Trustpilot, Amazon, Google Play scraping | ToS breaches, bot defenses, maintenance burden. Revisit only through a licensed reseller if a sector demands it |
| Crunchbase, PitchBook, Dealroom | $30k+/yr for data that answers "is this crowded?" — EDGAR and YC answer that well enough |
| Exploding Topics, Glimpse | Paid, and they show the same pre-digested trends to every subscriber |
| AIS, port, and freight data as collectors | Far from any person's problem; months of lag; valuable only as context |
| Product Hunt as a problem source | Measures launch marketing, not pain; commercial use banned |

## Implications for our design

1. **Collectors split into two kinds.** *Streams* (HN, Stack Exchange, Bluesky, app reviews,
   complaint databases, Federal Register) run weekly and append raw text. *Lookups* (Trends,
   DataForSEO, FRED, Comtrade, EDGAR, OpenAlex) run on demand when an agent investigates a
   candidate. The SQLite schema should model both: a `documents` table for stream records and
   a cached `lookups` table keyed by query.
2. **Store everything raw, including what we cannot re-fetch.** Apple caps reviews at 500,
   Jetstream keeps nothing, and APIs close without warning (Reddit 2023 and 2025, Pushshift,
   PA-API 2026). Each weekly run is our only copy.
3. **Record provenance and license per row.** A `source`, `license`, and `tos_class`
   (clean / gray / restricted) column lets the dossier cite evidence and lets us drop gray
   sources if the project ever goes commercial.
4. **Normalize toward "complaint" records.** Every stream source reduces to: text, author
   type if known, product or company mentioned, date, engagement score, and URL. The
   synthesis agents then cluster complaints across sources; agreement between, say, CFPB
   narratives and Bluesky posts is stronger evidence than volume in one.
5. **The human steering step must pick sources, not only problems.** Once Edgar narrows to
   a person type, the system should propose sector-specific sources (a trade forum, a
   subreddit, a list of competitor apps) and add them as new collectors.
6. **Expect breakage.** Unofficial endpoints (Trends forks, yc-oss) and rate limits change
   often. Each collector needs a health check and a "last success" timestamp the Next.js app
   shows prominently.
7. **Budget.** Phase 1 costs $0. The first paid step is a ~$50 DataForSEO deposit; the
   first decision with real money is Reddit commercial access, which matters only if the
   project becomes a product.
