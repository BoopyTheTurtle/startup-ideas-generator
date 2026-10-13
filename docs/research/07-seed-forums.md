# 07 — Seed forums for the generic forum collector

Stage 1 research, 2026-10-13. Extends Part A of
[06-forums-reviews-discovery.md](06-forums-reviews-discovery.md) and fills the SPEC's
"Coverage gap" with 5–10 hand-picked seeds. **Tested** means a request from our user
agent (`startup-ideas-generator/0.1`) between 14:55 and 15:35 UTC on 2026-10-13 returned
the result described. **[unverified]** marks claims we could not check.

## Summary

We probed 82 forum endpoints. Twenty-five passed the bar and appear in section 1; the
rest failed on access, activity, segment, or terms (section 3). Bot walls, not
robots.txt, stopped most of the failures: Cloudflare challenges,
VerticalScope's HTTP 409, and a `.stile` challenge page served with status 200. Our
user agent passed every robots.txt check it reached.

Terms of service, not access, narrow the field next. The stock Discourse terms forbid
"automated access" by any program "that is not a web browser", so every Discourse forum
we read (Fairphone, Victron, MS Society) classes as restricted unless its owner agrees in
writing. The cleanest sources run XenForo, WoltLab, or phpBB under short owner-written
terms that never mention scraping.

The recommended set below holds nine clean forums and one flagged gray one. It reaches
caregivers, patients, trades, trucking, farming, teachers, contractors, home owners, and
personal finance, in English, German, Italian, and French. Dutch, Polish, Spanish, and
Nordic forums all failed on access or terms; the gap stays open there.

---

## Method

1. **Candidates** came from report 06's leads, web search, the Discourse Discover
   directory (opted-in, but hobby- and game-heavy), and footer links on vetted sites.
2. **Probe.** A script in the scratchpad (not in the repo) called
   `Http.check_robots(feed_url)` from `pipeline/http.py`, so robots.txt went through our
   RFC 9309 matcher. It then fetched the feed once at 1.5 s spacing and parsed it. It
   also listed any AI crawler (GPTBot, ClaudeBot, CCBot, and 30 others) that a robots.txt
   group disallows from `/`, and any `Content-Signal` line.
3. **Terms.** One fetch of each terms page with our user agent, plus WebFetch where our
   agent was refused. Every relevant clause was read in full.
4. **Classes.** *Clean*: the terms say nothing against automated collection or AI use.
   *Gray*: limits on commercial use, reproduction, or "monetary" use; a named AI-bot
   block; or terms we could not read. *Restricted*: terms forbid robots, scraping,
   automated access, or AI use outright.

Nothing went to `data/ideas.db`. Each forum received one robots.txt fetch, one or two
feed fetches, and one or two terms fetches.

### Reading the activity column

Feeds cap their item count (10 to 50), so activity is shown as "N items within T". Two
orderings exist, and the column names which one applies:

- **active**: threads sorted by last post (XenForo, WoltLab, Vanilla, Forumactif). The
  count measures live threads, not new ones; old megathreads appear too.
- **new**: threads sorted by creation (vBulletin `external.php`, Discourse
  `?order=created`). The count measures new threads.
- **posts**: individual posts (phpBB).

"20 active in 13 h" means the newest 20 items spanned 13 hours, so the forum carries at
least that much traffic.

---

## 1. Vetted candidates

All 25 returned a parseable feed with items dated 2026-10-13 or earlier that week.
Robots.txt allowed our user agent for every feed URL listed. "AI blocks" lists crawlers
that robots.txt disallows from `/` by name; "—" means none.

| # | Forum | Software | Feed URL tested | Lang | Region | Segment | Activity (feed) | AI blocks | ToS class — reason | Sample titles with problem signal |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | [Terry Love Plumbing & Remodel](https://terrylove.com/forums/) | XenForo | `https://terrylove.com/forums/forums/-/index.rss` | en | US | Home owners, plumbers | 20 active in 22 h | — | **Clean** — terms cover only posters' licence ([terms](https://terrylove.com/forums/index.php?help/terms/)) | "Fleck 5600 SXT too much water in brine tank"; "Groundwater leaking into basement ejector/grinder pit around inlet pipe" |
| 2 | [TheTruckersReport](https://www.thetruckersreport.com/truckingindustryforum/) | XenForo | `https://www.thetruckersreport.com/truckingindustryforum/forums/-/index.rss` | en | US | Truck drivers, owner-operators | 20 active in 13 h | — | **Clean** — stock XenForo terms, no automation clause ([terms](https://www.thetruckersreport.com/truckingindustryforum/help/terms/)) | "Who will ROB me the least? Load boards or Dispatchers"; "Expunged Criminal record question" |
| 3 | [TractorByNet](https://www.tractorbynet.com/forums/) | XenForo | `https://www.tractorbynet.com/forums/forums/-/index.rss` | en | US | Small farms, rural land owners | 50 active in 13 h | — | **Gray** — terms unreadable: `/help/terms/` gave 404 to our agent and 402 to WebFetch **[unverified]** | "NH EHSS Controller failure … would you buy a repro if one existed?"; "Water softener in a low use situation" |
| 4 | [Practical Machinist](https://www.practicalmachinist.com/forum/) | XenForo | `https://www.practicalmachinist.com/forum/forums/-/index.rss` | en | US | Machinists, job shops | 40 active in 14 h | 14, incl. ClaudeBot, GPTBot, CCBot, Google-Extended | **Gray** — named AI blocks; terms returned 403 **[unverified]**. Its robots.txt matches Arboristsite's, whose terms ban AI use | "Beware of NNG Industries!"; "motor undercurrent protection (shutoff after loss of load)" |
| 5 | [BackYardChickens](https://www.backyardchickens.com/) | XenForo | `https://www.backyardchickens.com/forums/-/index.rss` | en | US | Backyard poultry keepers | 50 active in 6 h | — | **Gray** — terms returned 403 to us and WebFetch **[unverified]** | "Advanced fly strike"; "HELP SHELL EGG STUCK IN HER VENT" |
| 6 | [Early-Retirement.org](https://www.early-retirement.org/) | XenForo | `https://www.early-retirement.org/forums/-/index.rss` | en | US | Retirees, personal finance | 25 active in 2 h | — (robots.txt returns 403; RFC 9309 reads that as allow) | **Gray** — terms returned 403 **[unverified]** | "Looking for Desktop tax software after 25+ yrs with Turbo tax"; "Strategies for HSA money usage" |
| 7 | [Diabetes UK forum](https://forum.diabetes.org.uk/boards/) | XenForo | `https://forum.diabetes.org.uk/boards/forums/-/index.rss` | en | UK | Patients, carers (chronic illness) | 20 active in 17 h | — (robots.txt 404) | **Clean** — bans only posters' advertising; Diabetes UK holds a licence to posts ([terms](https://forum.diabetes.org.uk/boards/help/terms/)) | "Medication unavailable/shortages"; "Would an insulin pump help me, could I self-fund, and could I manage DIY?" |
| 8 | [Diabetes.co.uk forum](https://www.diabetes.co.uk/forum/) | XenForo | `https://www.diabetes.co.uk/forum/forums/-/index.rss` | en | UK | Patients (chronic illness) | 20 active in 43 h | — | **Restricted** — "domestic and private use only … not … for any commercial or business purposes" ([terms](https://www.diabetes.co.uk/disclaimer.html)) | "Steel cannulas for T:Slim"; "Smart watch with omnipod 5 freestyle Libre +2" |
| 9 | [Dementia Support Forum](https://forum.alzheimers.org.uk/) (Alzheimer's Society) | XenForo | `https://forum.alzheimers.org.uk/forums/-/index.rss` | en | UK | Family caregivers | 20 active in 5 h | — | **Clean** — rules govern posters only ([terms](https://forum.alzheimers.org.uk/help/termsandconditions/)) | "I am struggling to find a good care agency in St. Helens Merseyside"; "Dad admitted to hospital with Delerium … hospital are trying to discharge him home" |
| 10 | [MS Society forum](https://forum.mssociety.org.uk/) | Discourse | `https://forum.mssociety.org.uk/latest.json?order=created` | en | UK | Patients (disability) | 13 new in 7 d | — | **Restricted** — "automate access to the forum, or monitor the forum, such as with a web crawler" is prohibited ([tos](https://forum.mssociety.org.uk/tos)) | "Car insurance for car owners who can no longer drive"; "Feeling unsupported (JSA related)" |
| 11 | [Scope online community](https://forum.scope.org.uk/) | Vanilla | `https://community.scope.org.uk/discussions/feed.rss` | en | UK | Disabled people, benefits claimants | 30 active; 14 created in 7 d | — | **Gray** — house rules found ([rules](https://www.scope.org.uk/community-house-rules/)); full T&C link returned 404 **[unverified]** | "Waiting 8 months to hear about PIP renewal forms"; "What reasonable adjustments have you requested?" |
| 12 | [Phoenix Rising](https://forums.phoenixrising.me/) | XenForo | `https://forums.phoenixrising.me/forums/-/index.rss` | en | US/intl | ME/CFS patients | 20 active in 65 h | — | **Gray** — "Posts … cannot be used outside the forums for monetary purposes without the consent of the poster" ([rules](https://forums.phoenixrising.me/resources/forum-rules.5/)) | "Does anyone crash after eating?"; "Sudden new side effects from MB12 injections" |
| 13 | [Monzo Community](https://community.monzo.com/) | Discourse | `https://community.monzo.com/latest.json?order=created` | en | UK | Bank customers | 14 new in 7 d | — | **Gray** — "use the Forum for personal purposes … mustn't use it for any commercial or business purposes" ([terms](https://community.monzo.com/t/community-code-of-conduct/31411)) | "Unexpected price increase"; "Feature Request: Ability to set specific times for scheduled payments" |
| 14 | [Contractor UK](https://forums.contractoruk.com/) | vBulletin 5 | `https://forums.contractoruk.com/external?type=rss2` | en | UK | Contractors, freelancers (tax, IR35, umbrella pay) | 10 new in 7 d | Amazonbot, Bytespider | **Clean** — no automation clause; site asserts copyright on posts ([T&Cs](http://www.contractoruk.com/about/bulletin_board.html)) | "PayStream's hidden 'Less Employer Pension Saving' fee is costing me £5,588 a year"; "Self-Employed Courier Driving - Tax, NI & Real-World Take-Home Advice" |
| 15 | [Fairphone forum](https://forum.fairphone.com/) | Discourse | `https://forum.fairphone.com/latest.rss` | en, de, fr, nl | NL / EEA | Phone owners (consumers) | 30 new in 4.7 d | — | **Restricted** — forbids "scrape, crawl, harvest, or otherwise collect data … by automated means" except search engines ([tos](https://forum.fairphone.com/tos)) | "I thought the Fairphone was supposed to be repairable?"; "WhatsApp fails to update since last system update" |
| 16 | [Victron Energy community](https://community.victronenergy.com/) | Discourse | `https://community.victronenergy.com/latest.json?order=created` | en, de, fr, nl | NL / global | Solar installers, boat and RV owners | 30 new in 28 h | — | **Restricted** — stock Discourse clause against automated access ([tos](https://community.victronenergy.com/tos)) | "EVCS NS: 'Session cost' vs 'Session savings' wrong when charger is upstream"; "Kein Solarertrag mit Shelly als PV Zähler" |
| 17 | [Futura-Sciences forums](https://forums.futura-sciences.com/) | vBulletin 4 | `https://forums.futura-sciences.com/external.php?type=RSS2` | fr | FR | Home owners (heating, appliances), science hobbyists | 30 new in 4.8 d | — | **Gray** — "La reproduction de tout ou partie de ce site sur un support électronique … est formellement interdite"; no robots or AI clause ([mentions légales](https://www.futura-sciences.com/mentions-legales/)) | "Chaudière INOA 25 CF - radiateurs froid"; "Rénovation cellier/buanderie. Questions équilibrage chauffage, amiante" |
| 18 | [Neoprofs](https://www.neoprofs.org/) | Forumactif | `https://www.neoprofs.org/rss` | fr | FR | Teachers | 50 active in 4.8 d | CCBot, Bytespider, Meta-ExternalAgent, ImagesiftBot, Scrapy | **Gray** — named AI blocks; host Forumactif's CGU not located **[unverified]** | "Devenir professeur des écoles contractuel sur Paris, besoin de conseils"; "Le pacte : mise en oeuvre dans les EPLE" |
| 19 | [lehrerforen.de](https://www.lehrerforen.de/) | WoltLab Suite | `https://www.lehrerforen.de/thread-list-rss-feed/` | de | DE | Teachers, school leaders | 20 active in 3 d | — | **Clean** — rules govern posters only ([Nutzungsbedingungen](https://www.lehrerforen.de/wcf/nutzungsbedingungen/)) | "Kostenübernahme Beihilfe XFG Corona-Impfung"; "Frage zum Ausgleich für Tag der offenen Tür" |
| 20 | [Finanztip Community](https://www.finanztip.de/community/forum/) | WoltLab Suite | `https://www.finanztip.de/community/forum/thread-list-rss-feed/` | de | DE | Personal finance consumers | 20 active in 5.5 h | — | **Clean** — no third-party clause; Finanztip itself summarises threads with OpenAI ([AGB](https://www.finanztip.de/community/forum/thema/46955-agb-der-finanztip-community/)) | "AV-Depot / Riester / BAV bei Schwerbehinderung"; "DVAG Beratungstermin bei einem Verein" |
| 21 | [Photovoltaikforum](https://www.photovoltaikforum.com/) | WoltLab Suite | `https://www.photovoltaikforum.com/thread-list-rss-feed/` | de | DE / AT / CH | Home owners and installers (solar, heat pumps) | 20 active in 15 min | — | **Gray** — no terms page linked; only an [Impressum](https://www.photovoltaikforum.com/core/legal-notice/) **[unverified]** | "Umzug auf ennexOS Portal: Vermisse Auswertungen"; "Tripower ohne SMA Cloud auslesen" |
| 22 | [Landtreff](https://www.landtreff.de/) | phpBB 3 | `https://www.landtreff.de/feed.php` | de | DE | Farmers, foresters | 10 posts in 1.4 h | — | **Clean** — 2018 terms govern posters only ([Nutzungsbedingungen](https://www.landtreff.de/ucp.php?mode=terms)) | "Landtechnikforum • Re: Gebrauchtschlepper kauf IHC 633"; "Computer und Internet • Re: Agrar Apps" |
| 23 | [Energeticambiente](https://www.energeticambiente.it/) | XenForo | `https://www.energeticambiente.it/forums/-/index.rss` | it | IT | Home owners (energy, heating, solar) | 20 active in 6 d | — | **Clean** — stock XenForo terms; contact at tomshw.it ([terms](https://www.energeticambiente.it/help/terms/)) | "Radiatori in ghisa preesistenti, tenere o cambiare?"; "pratica GSE per nuovo impianto" |
| 24 | [Bouwinfo bouwforum](https://www.bouwinfo.be/bouwforum/) | XenForo | `https://www.bouwinfo.be/bouwforum/forums/-/index.rss` | nl | BE | Home owners, renovators, trades | 20 active in 2.1 d | — | **Restricted** — forbids "robots, spiders, offline readers" except search engines, and storing content in any database ([voorwaarden](https://www.bouwinfo.be/algemene-voorwaarden)) | "Zonnepaneel bekabeling in de garage (AREI) regels en best practices"; "Verbouwwijsheden: contractor of zelf doen?" |
| 25 | [Foros de Electrónica](https://www.forosdeelectronica.com/) | XenForo | `https://www.forosdeelectronica.com/forums/-/index.rss` | es | ES + Latin America | Electronics repair technicians | 20 active in 5.7 d | PetalBot | **Gray** — posts licensed CC BY-NC-SA ([rules](https://www.forosdeelectronica.com/help/terms/)) | "TV LG no enciende (Error de destellos en LED de Standby…)"; "Frigorifico Teka dejó de funcionar." |

Two notes on the table. First, Arboristsite (rejected below) and Practical Machinist
share a robots.txt template that blocks 14–20 AI crawlers and, on Arboristsite, adds
`Content-Signal: search=yes,ai-train=no`. Second, no XenForo or WoltLab feed shows new
threads per week, because it sorts by last post; the collector's own counts will supply
that figure after a few weeks.

---

## 2. Recommended seed set

Ten forums: nine clean, one gray (flagged). The set covers four gap segments twice and
spans US, UK, Germany, Italy, and France.

| Seed | Segment | Lang | Region | ToS class | Why |
|---|---|---|---|---|---|
| Dementia Support Forum | Family caregivers | en | UK | Clean | Detailed care-system pain (agencies, discharge, power of attorney); charity-run |
| Diabetes UK forum | Patients, chronic illness | en | UK | Clean | Shortages, devices, self-funding questions; charity-run |
| Contractor UK | Contractors, tax and accounting | en | UK | Clean | Costed pain about umbrella fees, IR35, accountants; low volume (≈10 new threads/week) |
| Terry Love | Home owners, plumbers | en | US | Clean | Equipment-level faults and workarounds, by name and model |
| TheTruckersReport | Trucking | en | US | Clean | Dispatch, load boards, pay, regulation |
| lehrerforen.de | Teachers | de | DE | Clean | Administrative and benefits pain unique to civil-servant teachers |
| Finanztip Community | Personal finance | de | DE | Clean | 20 threads active within 5.5 hours; pension reform (Altersvorsorgedepot) questions in bulk |
| Landtreff | Farming, forestry | de | DE | Clean | Machinery, markets, farm software; feed carries every post |
| Energeticambiente | Home owners, energy | it | IT | Clean | Grid-connection paperwork (GSE, Gaudì), heating retrofits |
| **Futura-Sciences** ⚑ | Home owners, French | fr | FR | **Gray** | The only working French home-and-repair source; its legal notice forbids electronic reproduction. Store derived problem statements, not post text, or ask SARL Futura-Sciences first |

**Alternates, pending a human read of their terms:** TractorByNet, BackYardChickens,
Early-Retirement.org, Photovoltaikforum, and Scope. Each passed robots.txt and returned
a rich feed, but their terms pages refused our agent or could not be found. Edgar can
open each terms link in a browser and promote any that read clean. Photovoltaikforum
and Scope fill the most gap.

**Ask the owner:** Fairphone, Victron, MS Society, and Bouwinfo forbid automated access
in their terms yet publish feeds. A short email naming the user agent, the request rate,
and the purpose may earn written permission.

---

## 3. Rejected candidates

| Forum | URL tried | Reason |
|---|---|---|
| ContractorTalk, ElectricianTalk, DIY Chatroom, Homesteading Today, PetForums UK, ChefTalk | `/forums/-/index.rss` | HTTP 409 to our agent (VerticalScope bot wall); robots.txt allowed |
| Mike Holt Forum | `forums.mikeholt.com/forums/-/index.rss` | 403 |
| DIYnot, PlumbersForums, ElectriciansForums, Byggahus.se, Student Doctor Network, Bogleheads, FinanzaOnline, Infojardín, Burbuja.info, Forum Prawne (PL) | XenForo, phpBB, or vBulletin feeds | Cloudflare "Just a moment" challenge (403) |
| Forum Muratora (PL) | `forum.muratordom.pl/external.php?type=RSS2` | Cloudflare 403; robots.txt blocks 14 AI crawlers |
| The Farming Forum (UK) | `index.php?forums/-/index.rss` | 403, as in report 06 |
| UK Business Forums, Horse & Hound forum | `/forums/-/index.rss` | Redirect to a `.stile/challenge` HTML page served with status 200 |
| AppleVis, PPRuNe, Edugeek, The Student Room, TaxProTalk, Trouble Free Pool, Forum Macchine (IT), Rika Tillsammans (SE) | various | 403 (Edugeek also blocks GPTBot, CCBot, Claude-SearchBot) |
| Wizaz (PL) | `/forums/-/index.rss` | 401 |
| TruckNetUK, InspectionNews, Pflegeboard (DE) | various | robots.txt unreachable; our matcher treats that as disallow |
| Octopus Energy forum | `/latest.json` | robots.txt disallows the URL for our agent |
| Arboristsite | `/forums/-/index.rss` (works) | **Restricted**: terms ban "data mining, robots" and any use "for the purpose of training computer models … or optimizing artificial intelligence"; robots.txt blocks 20 AI crawlers ([tos](https://arboristsite.com/tos)) |
| A to Z Teacher Stuff | `/forums/-/index.rss` | Feed empty for guests; robots.txt blocks 18 AI crawlers |
| HearingTracker forum | `/latest.json` | 410 Gone |
| TuDiabetes, Wrong Planet | Discourse JSON, phpBB feed | Returned HTML instead of a feed |
| tado community, Freetrade community | `/latest.json` | Redirect to a marketing site; forum gone or moved |
| EMTLife | XenForo feed (works) | Dead: 1 thread active in 7 days |
| Trading 212 Community | Discourse JSON (works) | 6 new threads in 7 days; overlaps Monzo |
| wer-weiss-was (DE) | Discourse JSON (works) | 13 new threads in 7 days, mostly trivia |
| Homey community (NL) | Discourse JSON (works) | Smart-home hobbyists and app developers; outside the gap |
| Garage Journal | XenForo feed (works) | Terms returned 403; hobby garage content overlaps Terry Love |
| Legal Beagles, PropertyTribes, LandlordZONE, Radar forum (NL), Carers UK, TaxationWeb, Square Seller Community, Byggebolig (NO), Hjemmeautomasjon (NO), Hausgarten.net | guessed vBulletin, phpBB, Vanilla, Discourse, or SMF paths | No feed found (404) |
| Rankia (ES), Agrofoto (PL) | — | Custom software or Invision with no public feed link |
| forum.ubuntu-fr.org | `extern.php` | Malformed XML; developer segment anyway |
| Mumsnet, MoneySavingExpert | — | Excluded in report 06 (terms and robots.txt) |

The gap segments left unserved: legal practice, landlords (UK landlord forums expose no
feed), hospitality and small retail (ChefTalk blocked), parents, and nursing (allnurses
and Pflegeboard blocked).

---

## 4. Notes for the collector builder

**Per software.** Each row records what the tested feeds did on 2026-10-13.

| Software | Endpoint | Order and dates | Body | Limits and quirks |
|---|---|---|---|---|
| XenForo 2 | `/forums/-/index.rss`, or `/index.php?forums/-/index.rss` without friendly URLs; per-forum `/forums/<slug>.<id>/index.rss` | Threads by last post. `pubDate` is the **last post** time (a 2021 megathread showed today's date), RFC 822 with `+0000` | `content:encoded` holds the thread's **first post** in full HTML (`<div class="bbWrapper">`) | Admin sets the cap: 20, 25, 40, and 50 seen. No pagination. `guid` = thread id. `<author>` is the placeholder `invalid@example.com`; read `dc:creator`. `slash:comments` = reply count |
| WoltLab Suite 6 | `<forum path>/thread-list-rss-feed/` (old `board-feed/` returned 404) | Threads by last post; `pubDate` moved forward between two fetches, so it marks the last post | `content:encoded` = first post | 20 items. Forum path varies (`/community/forum/` on Finanztip) |
| vBulletin 4 | `external.php?type=RSS2` | **New threads** by creation; `pubDate` in GMT | `description` = ~200-character excerpt; `content:encoded` = full first post | Declares ISO-8859-1 in header and XML prolog (see encoding below). 30 items. `Cache-Control: max-age=1791904318` is bogus; ignore it |
| vBulletin 5 | `external?type=rss2` (no `.php`) | New threads by creation | Full first post in `content:encoded` | 15 items. Titles carry double-escaped entities (`&amp;quot;`); unescape twice |
| Discourse | `/latest.json?order=created`; `/latest.rss` | JSON: 30 topics per page, `more_topics_url` adds `&page=N`; `created_at` ISO 8601 with milliseconds and `Z`. Plain `/latest.json` sorts by bump and mixes in pinned topics from years ago; filter `pinned` | JSON carries **no post text**; fetch `/t/{id}.json` per topic, or use `/latest.rss`, whose `description` holds the full first post plus a "N posts - N participants" footer | `latest.rss` returned 30 items that look creation-ordered **[unverified]** |
| phpBB 3.2+ | `/feed.php` (some installs: `/app.php/feed`) | **Posts**, not threads, site-wide; Atom with local offsets (`+01:00`) | Full post HTML, with a "Statistik: Verfasst von …" footer to strip | 10 items by default, so a busy board overruns them within hours. Links carry a `sid=` session id; strip it before deduplication. `feed.php?mode=topics` should list new topics **[unverified]** |
| Vanilla | `/discussions/feed.rss` | Discussions by last activity, but `pubDate` is the **creation** date (2020 items appear), so a date filter drops live old threads | Full first post HTML with embedded JSON blobs | 30 items |
| Forumactif | `/rss` | Topics by recent activity | `description` truncated near 500 characters with "…"; the full text needs HTML pages, which our feed-only rule excludes | 50 items |

**Encoding.** `Response.text` in `pipeline/http.py` is already decoded. Re-encoding it to
UTF-8 and handing it to ElementTree garbled every accented character on Futura-Sciences,
because the prolog still declared ISO-8859-1. Either strip the XML declaration before
parsing or expose raw bytes on `Response` and parse those.

**Bot walls fail softly.** VerticalScope answers 409; Cloudflare answers 403 with a
"Just a moment" HTML page; the `.stile` challenge answers **200** with HTML. The health
check must treat any non-XML or non-JSON content type as a failure, not as a parse
error or an empty feed.

**Robots.txt edge cases.** Early-Retirement.org returns 403 and Diabetes UK 404 for
robots.txt; our matcher reads both as "no restrictions", as RFC 9309 says. Three hosts
timed out or returned 5xx, which the matcher treats as full disallow. Arboristsite
publishes `Content-Signal: search=yes,ai-train=no`, which our matcher ignores; store the
line in `forum_source` so a change to it pauses the source.

**Volume and polling.** Feed caps truncate busy forums: TractorByNet filled 50 items in
13 hours, Photovoltaikforum 20 in 15 minutes. A weekly run catches a small slice. Poll
the site feed every few hours, or poll per-subforum feeds chosen for problem density.
Deduplicate on `guid`. XenForo, WoltLab, and Vanilla feeds re-emit a thread whenever
someone replies, so store the first post once and update only the reply count.

**First posts only.** Every feed above carries the opening post and no replies. Replies
hold the workarounds and tool names, but fetching them means thread pages: HTML for
XenForo and WoltLab, `/t/{id}.json` for Discourse. Decide per source after approval.

**Politeness.** Our user agent and contact URL were accepted everywhere a feed answered.
One request every 5 seconds per host, as report 06 proposes, fits every site here.
