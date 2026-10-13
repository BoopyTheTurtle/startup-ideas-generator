# 06 — Forums, reviews, and forum discovery

Stage 0 research, round 2, 2026-10-13. Extends [01-data-sources.md](01-data-sources.md)
and [04-prior-art-and-pipeline.md](04-prior-art-and-pipeline.md). EEA and UK government
and ombudsman sources belong to a separate report. **Tested** means a direct request on
2026-10-13 returned the result described. **[unverified]** marks claims from memory or a
single secondary source.

## Summary

Reddit's closure leaves no single replacement; a portfolio of smaller, cleaner sources
must cover it. Three groups survive scrutiny. First, **marketplace reviews with official
or tolerated JSON**: Firefox Add-ons, WordPress.org plugin support forums, Steam,
Atlassian, JetBrains, and VS Code. Each serves a narrow segment, and all returned data
in tests today. Second, **vertical forums on XenForo, vBulletin, and Discourse**, which
expose RSS or JSON and carry detailed trade pain (contractors, truckers, landscapers).
Their owners increasingly block AI crawlers by name, so each needs a human-approved
licence check. Third, **Lemmy and Stack Exchange's long tail**, both open but thin
outside tech. The big UK consumer forums, Mumsnet and MoneySavingExpert, carry rich
pain but forbid or discourage automated access. Most review sites (Yelp, Google,
Tripadvisor, Capterra, Glassdoor, kununu, BBB) cap, sell, or block their data.

---

## Part A — Forums beyond Reddit

**Signal** rates problem detail per record: high, medium, or low.

| Source | Access (tested 2026-10-13) | ToS / robots | Cost | Signal | Verdict |
|---|---|---|---|---|---|
| **Discourse forums** (any) | `/latest.json`, `/c/{slug}.json`, `/t/{id}.json`, plus RSS. `meta.discourse.org/latest.json` returned 200 without auth. Tested | No platform-wide ToS; each site's owner sets terms. Default robots.txt allows `/`. Discourse throttles anonymous IPs (about 200 req/min **[unverified]**) | Free | High on product and hobby forums (Home Assistant, Obsidian, Anki); varies | **Use**, per site, after a ToS check |
| **Lemmy** | `/api/v3/post/list`, `/api/v3/search`. lemmy.ml returned 200; lemmy.world returned 503 on two tries. Tested | Per-instance rules; fediverse norms frown on bulk collection | Free | Low–medium: tech, privacy, politics; few vertical communities | v2, a few communities only |
| **Mastodon** | Hashtag timelines public (`/api/v1/timelines/tag/{tag}` returned 200). Full-text status search returned nothing unauthenticated, because Mastodon indexes only opted-in posts. Tested | mastodon.social barred AI training in June 2025, then rewrote its terms, effective August 31, 2026 ([TechCrunch](https://techcrunch.com/2025/06/17/mastodon-updates-its-terms-to-prohibit-ai-model-training/), [Mastodon blog](https://blog.joinmastodon.org/2026/07/announcing-new-terms-of-service-for-our-servers/)). Researchers find users expect consent ([PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC10801199)) | Free | Low | **Skip**. Bluesky covers the same ground with permissive terms |
| **Stack Exchange long tail** | API v2.3; `/sites` lists 365 sites including metas. Tested | Covered in 01 | Free | High on niche sites: Personal Finance, Home Improvement, Law, Academia, Workplace, Freelancing, Parenting, Pets | Already in v1; **widen the site list** |
| **Hacker News** | Algolia and Firebase APIs. Tested | Clean | Free | Covered in 01 | In v1 |
| **Lobsters** | `/newest.json` returned 200. Tested | Small invite-only community | Free | Low volume | Skip |
| **Indie Hackers** | No official API or feed; `/feed.xml` returned 404. Tested | robots.txt disallows `/api/` for all and blocks ClaudeBot, GPTBot, and 20 other AI agents site-wide | Free | Medium; founder-centric, duplicates HN | **Skip** |
| **Product Hunt** API v2 | GraphQL with token | "Must not be used for commercial purposes" ([docs](https://www.producthunt.com/v2/docs)) | Free | Low: launch hype; comments sometimes ask for missing features | Skip (as in 01) |
| **GitHub Discussions** | GraphQL; 5,000 points/hour per user ([GitHub](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api)) | Clean | Free | Medium: feature requests for open-source tools | v2, beside GitHub Issues |
| **Quora** | No public API | robots.txt forbids any use for "AI models or similar machine learning systems". Tested | — | Medium | **Skip** |
| **Discord** | Bot API only in servers that invite the bot | Developer policy bans mining or scraping; Discord banned Spy.pet accounts in 2024 ([policy](https://support-dev.discord.com/hc/articles/25280499088279), [Gigazine](https://gigazine.net/gsc_news/en/20250522-discord-scrape-publish-2-billion-message)) | — | High, but private | **Skip** |
| **Telegram** | Public channels readable via MTProto client or `t.me/s/` | Channels broadcast; groups are private **[unverified ToS detail]** | — | Low | Skip |
| **Facebook groups** | Groups API deprecated in 2024 **[unverified date]** | Scraping prohibited | — | High, unreachable | **Skip** |
| **Mumsnet** (UK) | No RSS found (404). Tested | Terms forbid scraping "for any purpose" without approval; Mumsnet sued OpenAI over it ([Mumsnet](https://mumsnet.com/talk/site_stuff/5122770-why-were-taking-legal-action-against-open-ai-and-other-scrapers)) | — | High: UK parents, household, schools, employment | **Skip** unless licensed |
| **MoneySavingExpert forums** (UK) | `/discussions/feed.rss` returned 20 items, ~3,000 characters each. Tested | robots.txt disallows `/*.rss$` for generic agents; terms grant "personal and non-commercial use only" ([T&Cs](https://moneysavingexpert.com/site/terms-conditions/)) | — | High: UK consumer finance, energy, disputes | **Skip** the feed; robots.txt forbids it. Ask MSE for permission if UK finance matters |
| **XenForo / vBulletin trade forums** | XenForo exposes `/forums/-/index.rss`. ContractorTalk (35 items, five days), TheTruckersReport, and LawnSite returned 200; The Farming Forum returned 403. Tested | ContractorTalk allows `*` but blocks ClaudeBot, GPTBot, and others by name | Free | High: trades, trucking, landscaping, farming | **Use**, per site, with human approval |
| **Professional forums** | Dentaltown's robots.txt disallows `/MessageBoard/`; allnurses serves a Cloudflare challenge; AccountingWEB shows no feed. Tested | Closed or defended | — | High, unreachable | Skip these three; others case by case |

**A caveat governs the whole list.** Forum owners now block AI crawlers by name in
robots.txt, as ContractorTalk and Indie Hackers do, while leaving generic agents
allowed. Our collector neither trains models nor builds a search index, but it does feed
text to an LLM. Treat a named AI-bot block as the owner's stated intent: classify the
site `tos_class = gray`, read the human-written terms, and let Edgar decide. Never spoof
a browser user agent to get around a block.

---

## Part B — Forum discovery

### Search APIs in October 2026

Web search is the main discovery tool, and its market changed sharply in 2025–2026.

| API | Status and price | Fit for discovery |
|---|---|---|
| **Bing Web Search** | Retired August 11, 2025 ([Microsoft](https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement)). Successor "Grounding with Bing" feeds an Azure agent and returns no raw result list; reported $35/1,000 calls ([dev.to](https://dev.to/tonywangca/best-bing-search-api-alternatives-in-2026-after-the-retirement-kdi)) | None |
| **Google Custom Search JSON** | Closed to new customers in 2025; shuts down January 1, 2027 ([Brave summary](https://brave.com/learn/google-api-shutdown/)) | None |
| **Brave Search API** | $5/1,000 queries after a May 2026 price cut, with about $5 of monthly credit ([CostBench](https://costbench.com/changelog/brave-search-api-price-decrease-2026-05/)); free-tier reports conflict. Keeping results needs a separate "storage rights" plan ([Brave help](https://api-docs.search.brave.software/resources/help)) | Good: independent index, supports `site:` and operators. Store only domains we keep, and confirm with Brave that this counts as permitted use |
| **Exa** | $7/1,000 searches with page text; $10 free credit monthly ([Exa changelog](https://exa.ai/docs/changelog/pricing-update)) | Best for semantic queries ("forum where dental office managers discuss billing software"); find-similar on a known forum URL **[unverified endpoint name]** |
| **Tavily** | 1,000 free credits/month; $0.008/credit pay-as-you-go; acquired by Nebius in February 2026 ([CostBench](https://www.costbench.com/software/web-scraping/tavily/), [usagepricing](https://usagepricing.com/blueprint/activity/tavily-2026-02-10-nebius-acquisition)) | Adequate; tuned for agent answers, not result lists |
| **SerpAPI** | 250 free/month; $25 for 1,000; no pay-as-you-go ([CostBench](https://costbench.com/software/web-scraping/serpapi/)) | Google results, legally gray (it scrapes Google) |

At our scale, 200 discovery queries a month, Brave and Exa together cost under $3, much
of it inside free credits.

### Other discovery channels

- **Directories.** [Discourse Discover](https://discover.discourse.com) lists opted-in
  public communities ([Discourse Meta](https://meta.discourse.org/t/including-your-site-in-discourse-discover/314909)).
  Opt-in matters: an owner who lists a site there wants visitors. The lemmyverse dataset
  (`data.lemmyverse.net`) listed 497 Lemmy instances when tested.
- **Common Crawl.** The columnar index (Parquet, queryable in DuckDB) filters URLs by
  path, so patterns such as `/forums/-/index.rss`, `/t/*/` plus `/latest.json`, and
  `viewtopic.php` find XenForo, Discourse, and phpBB hosts without touching their
  servers ([community wiki](https://moltchat-agent-commons.onrender.com/wiki/Common_Crawl_index_query_by_URL),
  [Host Index](https://blog.commoncrawl.org/blog/introducing-the-host-index)). Discourse
  pages also carry `<meta name="generator" content="Discourse …">`
  ([Discourse Meta](https://meta.discourse.org/t/need-web-clipper-for-discourse-post/45105)),
  but matching on it needs a WARC scan, which costs more. Run this monthly at most.
- **BuiltWith counts** suggest regional skew: Discourse leads in the UK and France,
  XenForo in Canada and Turkey ([BuiltWith](https://trends.builtwith.com/cms/forum-software/country/United-Kingdom)).
  The fingerprint queries must cover all major engines.
- **Link graphs.** Outbound links in collected posts ("ask on the X forum") point to
  communities our users already trust. Count distinct domains linked from collected
  text; a forum cited by several independent authors becomes a candidate.

### Measuring "increasing detail"

Edgar wants forums where a niche issue is discussed in more and more detail. Each metric
below comes from data the collector already stores, per forum and per canonical problem,
on a 12-week window against the prior 12 weeks.

| Metric | Computation | What it detects |
|---|---|---|
| Distinct-author growth | Unique author hashes per week, slope | A widening community, not one loud poster |
| Post depth | Median words per post; share of posts over 300 words | Practitioners explaining workflows |
| Thread depth | Median replies per thread; share of threads over 10 replies | Unresolved problems that draw discussion |
| Jargon density | Share of tokens absent from a general English frequency list, after stop-words | Specialization of the audience |
| Specificity markers | Rate of numbers, currency, tool names, and error codes per 1,000 words | Concrete, costed pain |
| Structural growth | New subforums, categories, or tags in the site map | Owners splitting a topic because volume demands it |
| Answer gap | Share of threads with no accepted answer or no reply after 7 days | Demand that the community itself cannot meet |

Jargon density and specificity both rise when a topic moves from curiosity to practice;
combined with distinct-author growth, they mark the shift we want. Post length alone
misleads, because rants run long.

### The discovery-and-scoring loop

1. **Seed.** When Edgar steers toward a person type ("independent dental practices"),
   an agent drafts 10–20 queries: `"{role}" forum`, `"{tool} alternatives" forum`,
   `inurl:forums "{jargon term}"`. It runs them through Brave and Exa, then adds
   candidates from Discourse Discover, link-graph mentions, and Common Crawl fingerprints.
2. **Fingerprint.** For each candidate domain, fetch the home page once and detect the
   engine (generator tag, URL patterns, `/latest.json` response). Record the engine and
   the cheapest machine-readable endpoint: Discourse JSON, XenForo RSS, phpBB
   `feed.php`, or none.
3. **Gate.** Fetch robots.txt and the terms page. A script flags disallowed paths,
   named AI-bot blocks, and keywords ("scrape," "automated," "personal use," "AI").
   Sites behind Cloudflare challenges or login walls drop out here.
4. **Sample.** Pull up to 50 recent threads via the feed, at one request every 5
   seconds, and store them in a quarantine table, never in `raw_item`.
5. **Score.** Compute the detail metrics above on the sample, plus a cheap Haiku pass:
   the share of posts that contain a pain statement, and the share that match the
   steered person type. A candidate needs enough volume (≥ 20 new threads a month),
   a pain share above about 15%, and audience fit.
6. **Approve.** The UI shows Edgar a card: engine, endpoint, robots summary, terms
   excerpt, metrics, and five sample pain quotes. He approves, rejects with a reason, or
   marks "ask the owner." Every action writes a `decision` row.
7. **Promote.** An approved forum becomes a row in a `forum_source` table driving one
   generic collector per engine (RSS, Discourse JSON). Nobody writes new code per forum.
   The collector honours robots.txt on every run, caps requests per site, sends a
   descriptive user agent with a contact address, and stops on 403, 429, or a changed
   robots.txt, flagging the source for review.
8. **Retire.** Re-score quarterly. Forums whose pain share or volume falls below the
   bar, or whose terms change, return to the approval queue.

---

## Part C — Review sites and trust proxies

| Source | Access (tested 2026-10-13 where noted) | ToS | Cost | Pain it reveals | Verdict |
|---|---|---|---|---|---|
| **Firefox Add-ons (AMO)** | `api/v5/ratings/rating/?addon=` returned uBlock Origin's 22,201 ratings with text, no key. Tested | Mozilla Terms of Use; no API-specific licence found ([AMO policies](https://www.mozilla.org/en-US/about/legal/amo-policies/)) | Free | Browser users: privacy, productivity, broken workflows | **v1 candidate**; stands in for the closed Chrome store |
| **WordPress.org plugins** | Plugin info API and per-plugin support RSS (`/support/plugin/{slug}/feed/`): 30 threads, ~2,100 characters each. Tested | Public support forums; terms not located **[unverified]** | Free | Small-business site owners, e-commerce merchants (WooCommerce), agencies | **v1 candidate** — detailed SMB pain, a vast catalogue |
| **Steam** | Official `appreviews` endpoint, cursor paging, 100 per page ([Steamworks](https://partner.steamgames.com/doc/store/getreviews)). Tested | Documented by Valve for this use | Free | Gamers; also creative tools sold on Steam | v2; narrow segment |
| **VS Code Marketplace** | `_apis/public/gallery/.../reviews` returned review text (Prettier: 492 reviews). Tested | Undocumented endpoint **[unverified ToS]** | Free | Developers; overlaps HN | v2 |
| **JetBrains Marketplace** | `/api/plugins/{id}/comments` returned rated comments. Tested | Public API **[unverified terms]** | Free | Developers | v2 |
| **Atlassian Marketplace** | REST v2 `/addons/{key}/reviews` returned 200. Tested | Public API **[unverified terms]** | Free | Teams running Jira and Confluence: admin, compliance, reporting | **v2, high value for B2B** |
| **Shopify App Store** | No API. robots.txt permits `/reviews` pages for all agents. Tested | Shopify terms not checked **[unverified]** | Free (HTML) | E-commerce merchants: high-signal SMB pain | v2, gray; HTML parsing, low rate |
| **Salesforce AppExchange** | No public review API found; robots.txt blocks search pages | — | — | Enterprise CRM admins | Skip |
| **Chrome Web Store** | No official review API ([docs](https://developer.chrome.com/docs/webstore/api)). robots.txt disallows `/detail/*/reviews`. Tested | Blocked | — | Browser users | **Skip**; use AMO |
| **F-Droid** | `index-v2.json` (19.5 MB) lists apps and metadata. Tested | Open | Free | None: F-Droid has no user reviews **[unverified absence]**; pain sits in each app's issue tracker | Skip as a review source |
| **Capterra / GetApp / Software Advice** | No public API | Terms forbid "any automated means" ([Capterra](https://capterra.com/legal/general-user-terms_lessprioritymarkets/)) | — | B2B software buyers | Skip |
| **TrustRadius** | Vendor-portal API key ([API Evangelist](https://providers.apievangelist.com/providers/trustradius/)) | Vendors only | Paid | B2B | Skip |
| **Yelp Fusion** | 3 excerpts of ~160 characters per business; free tier ended 2024; reported from $229/month ([Supergood](https://supergood.ai/api-report-card/yelp)) | Restrictive | Paid | Local services | **Skip**: too thin to read |
| **Google Places** | Max 5 reviews per place, storage restricted, reviews raise the SKU price ([JustReview](https://justreview.co/blog/google-reviews-api-what-is-allowed/)) | Restrictive | ~$40/1,000 calls **[secondary]** | Local services | Skip |
| **Tripadvisor Content API** | 5 reviews per location; ~5,000 free calls/month; being replaced by "Terra" ([ReadMe](https://tripadvisor-content-api.readme.io/), [Supergood](https://supergood.ai/api-report-card/tripadvisor)) | Non-commercial, no scraping | Free tier | Travel and hospitality | Skip |
| **Reviews.io, Feefo** | APIs serve a merchant's own reviews; Feefo warns against bulk retrieval ([Feefo](https://support.feefo.com/support/solutions/articles/8000112938)) | Merchant-oriented | — | UK e-commerce | Skip |
| **Sitejabber** (now SmartCustomer) | API documented at [apidocs.sitejabber.com](https://apidocs.sitejabber.com); public-review access unconfirmed | Unknown | Unknown | US e-commerce | Ask; low priority |
| **BBB** | Developer API for approved uses; bans bulk redistribution ([terms](https://developer.bbb.org/terms-of-use)). bbb.org returned a Cloudflare 403. Tested | Restrictive | Free with approval | US small-business disputes | v2 only if approval is easy; the CFPB already covers finance |
| **Which?** (UK) | No API or data licence found | Membership content | — | UK consumers | Skip |
| **Resolver** (UK) | Sells complaint intelligence; publishes sector counts twice a year ([Resolver](https://news.resolver.co.uk/?p=5037)) | Commercial | Paid | UK consumer complaints by sector | Read the free reports as trend input |
| **Glassdoor** | Public API retired 2021–22 ([Zuplo](https://zuplo.com/blog/2024/09/30/what-is-glassdoor-api)) | Scraping forbidden | — | Employee pain, a B2B proxy | Skip |
| **kununu** (DACH) | No API; site served a "Human Verification" page. Tested | — | — | German-speaking employee pain | Skip |
| **National review sites** | Trusted Shops (DE), Avis Vérifiés (FR), Feedaty (IT), Kiyoh (NL) host merchant-collected reviews ([wmtips](https://www.wmtips.com/technologies/customer-reviews/country/de)) | Merchant-owned widgets; no open APIs found | — | Shop service failures, mostly delivery and returns | Skip: low problem novelty |

### Trust-evaluation tools carry almost no problem signal

ScamAdviser, Google Safe Browsing, and Trustpilot's Trust Report measure whether a site
is fraudulent, not what a customer needs. Safe Browsing is free but non-commercial and
returns only threat labels ([Google](https://developers.google.com/safe-browsing/terms));
ScamAdviser publishes no API price. Trustpilot removed 4.5 million fake reviews in 2024,
7.4% of submissions ([Trust Report 2025](https://press.trustpilot.com/trust-report-2025)).
That figure matters to us only as a discount: any open review corpus carries a few
percent of fakes, and our deduplication and author-diversity counts must absorb them.
Skip all three as sources.

### Which segments the usable sources reach

| Segment | Sources that work |
|---|---|
| Small-business website owners, e-commerce merchants | WordPress.org support, Shopify App Store (gray) |
| Teams on Jira and Confluence | Atlassian Marketplace |
| Developers | VS Code, JetBrains, GitHub, HN, Stack Overflow |
| Browser and privacy-minded consumers | AMO |
| Gamers and creative-tool users | Steam |
| Trades, trucking, landscaping, farming | XenForo and vBulletin forums via RSS |
| Hobbyist and home-automation users | Discourse forums |
| UK consumers | Mumsnet and MSE (closed), Resolver reports, the other agent's ombudsman data |

The gap is clear: general consumers and regulated professions (health, law, accounting)
remain hard to reach without Reddit or licensed data.

---

## Recommendations

### v1 additions (three)

1. **WordPress.org plugin support forums.** One RSS URL per plugin, no key, threads
   averaging 2,000 characters, and a population of small businesses that HN never
   reaches. Start with the top 200 plugins by active installs.
2. **Firefox Add-ons ratings.** A clean JSON API with text; seeds consumer productivity
   and privacy problems.
3. **A generic Discourse + XenForo RSS collector**, seeded by hand with five to ten
   approved forums. Building it now gives the later discovery stage a ready target.

### v2

Atlassian Marketplace; Steam; VS Code and JetBrains; GitHub Discussions; a widened
Stack Exchange site list; Shopify App Store reviews at a low rate after a terms check;
selected Lemmy communities; BBB if approval is quick. Write to MSE and Mumsnet asking
for permission; a yes would fill the UK consumer gap.

### Forum-discovery stage

Build it after the generic collector has run for two months, so the scoring thresholds
rest on real data. Use Brave and Exa within free credits, Discourse Discover, a monthly
Common Crawl path query, and link-graph mining. Every new forum passes the gate in step 3
and Edgar's approval in step 6 before it reaches `raw_item`.

## Implications for our design

1. **Model forums as data, not code.** A `forum_source` table (domain, engine, endpoint,
   robots hash, terms URL, `tos_class`, approval decision, last health check) drives one
   collector per engine. Discovery inserts rows; Edgar approves them.
2. **Add a quarantine stage.** Discovery samples live in a `candidate_item` table and
   reach `raw_item` only after approval, so unvetted text never enters clustering.
3. **Re-check robots.txt every run** and store its hash; a change pauses the source.
   Treat named AI-bot blocks as `gray` and require a human decision.
4. **Prefer feeds over pages.** RSS and JSON endpoints cut load on small forums, survive
   redesigns, and signal that the owner expects machine readers.
5. **Store per-forum metrics weekly** (authors, words per post, replies, jargon,
   specificity, answer gap) in a `forum_metric_weekly` table; discovery scoring and
   retirement read from it.
6. **Expect thin segments.** Marketplace reviews reach developers, merchants, and
   site owners well; general consumers and regulated professions stay underserved
   until Reddit access or a licence arrives. The scorer should report source coverage
   so a problem seen only in developer sources is not mistaken for a mass-market one.
7. **Budget.** Everything recommended here costs $0 except discovery search, which fits
   inside Brave's and Exa's monthly credits at our volume.
