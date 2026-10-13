# Startup ideas generator — spec

Draft 1, 2026-10-13. Status: awaiting Edgar's review.

## Purpose

The tool finds a startup for Edgar to build. It reads public complaint data every week,
infers the problems people describe, and tracks how those problems rise and fall. Edgar
steers the narrowing: from hundreds of broad problems, to one problem and person type,
to a specific idea with an evidence dossier and a test plan he runs himself.

The tool judges market merit only. Edgar judges founder fit.

The research behind every decision here lives in `docs/research/`:

| Report | Covers |
|---|---|
| `01-data-sources.md` | Which sources carry problem signal, access, cost, terms |
| `02-ideation-methods.md` | Ideation methods, LLM failure modes, funnel, data model |
| `03-scoring-and-validation.md` | Problem statements, rubric, dossier, test plans |
| `04-prior-art-and-pipeline.md` | Existing tools, clustering, stack, agent layout |
| `05-eea-uk-sources.md` | EEA and UK complaint, petition, and policy sources; languages |
| `06-forums-reviews-discovery.md` | Forums beyond Reddit, review marketplaces, forum discovery |

## Principles

1. **The problem is the core entity.** Ideas exist only under a problem and segment.
   This blocks solutions looking for problems by construction.
2. **Every claim traces to a source.** The chain runs raw item → verbatim quote →
   canonical problem → score → dossier citation. A validator rejects any score or
   dossier sentence without an evidence ID. No commercial tool offers this chain; it is
   the tool's main value.
3. **Automation buys breadth; Edgar supplies judgment.** LLMs extract and cluster well
   and judge poorly. They pre-sort; Edgar cuts.
4. **Behavior outweighs words.** Count distinct people, not posts. Weight workarounds,
   money spent, and hours lost above wishes.
5. **Trends explain timing; they never create a problem alone.** Macro, trade, and
   search data annotate a problem found elsewhere.
6. **History is permanent.** Raw items, extractions, and weekly snapshots are never
   deleted. Problems merge and split; they never vanish.
7. **Everything is versioned.** Each derived row records the run, prompt version, and
   model that produced it, so a ranking change traces to the world or to the pipeline.

## The funnel

| Stage | Name | Runs | Input → output |
|---|---|---|---|
| 0 | Methods | Once, revisited | Research → `docs/research/` (done) |
| 1 | Harvest | Weekly, automatic | Sources → raw items |
| 2 | Extract | Weekly, automatic | Raw items → pain records with verbatim quotes |
| 3 | Map | Weekly, automatic + merge approval | Pain records → canonical problems + weekly snapshots |
| 4 | Steer | Edgar, weekly | Radar → watch, promote, kill, merge; pick problem + segment |
| 5 | Score | On demand | Problem + segment → rubric scorecard, pairwise ranking |
| 6 | Ideate | On demand | Problem + segment → diverse ideas, deduplicated against history |
| 7 | Dossier | On demand | Idea → evidence dossier + test plan + kill criteria |
| 8 | Reassess and improve | Weekly, after stage 3 | System metrics → improvement cards → approved changes built and merged |

Stage 4 carries the most weight: opportunity depends on who looks at it, so Edgar's picks
there shape everything downstream.

### Stage 1 — Harvest

Collectors come in two kinds. **Streams** run weekly and append raw text. **Lookups** run
on demand when an agent investigates a candidate, and cache by query.

| Phase | Region | Streams | Lookups |
|---|---|---|---|
| v1 | Global | Hacker News (Algolia), Stack Exchange, WordPress.org plugin support feeds, Firefox Add-ons reviews | — |
| v1 | US, EEA, UK | Apple App Store reviews, looped over storefronts | — |
| v1 | UK | UK Parliament petitions, GOV.UK consultations and CMA cases | — |
| v1 | EEA | EU Have Your Say feedback (24 languages) | — |
| v1 | Any | Generic forum collector (Discourse and XenForo RSS), seeded with 5–10 forums Edgar approves | — |
| v2 | Global | Bluesky, GitHub issues, Atlassian, Steam, JetBrains, and VS Code marketplace reviews | Google Trends, SEC EDGAR Form D |
| v2 | US | openFDA, NHTSA, Federal Register | FRED, CFPB complaint counts |
| v2 | UK, EEA | UK Financial Ombudsman decisions, UK written questions, EU Safety Gate, TED and Find a Tender, Adzuna | Eurostat, ONS, ECB, FCA complaint data, Companies House |
| Later | Any | Reddit (if research access is granted), forums found by discovery, sector sources Edgar picks | DataForSEO (~$50 deposit), UN Comtrade |

CFPB complaint narratives left the v1 set: the CFPB stopped publishing them in August
2026 (ccdb5-api PR #256), so only structured counts remain, which suit a lookup.

Excluded: X (paid per read), Amazon, G2, Trustpilot, Google Play, Capterra, Glassdoor,
and kununu reviews (paid, closed, or scraping against terms); Mumsnet (terms forbid
scraping); Yelp, Google Places, and Tripadvisor (3–5 reviews per business); Mastodon
(no search without login, consent norms); trust tools such as ScamAdviser (no problem
signal); Crunchbase (~$30k/yr).

Forums are rows in a `forum_source` table, not code per site. Every source row carries
`source`, `license`, `tos_class` (clean, gray, restricted), `country`, and `lang`. Sites
that block AI crawlers by name get `gray`, and Edgar decides each one. Collectors
re-check robots.txt every run. Undocumented APIs, such as Have Your Say, get a schema
check that fails loudly when the response shape changes.

**Coverage gap.** The clean v1 sources over-represent developers, small businesses, and
policy-engaged citizens, and reach general consumers and regulated professions weakly.
The app shows each problem's source mix, and stage 8 tracks the gap.

**Forum discovery (later).** A loop finds forums where niche issues get discussed in
growing detail: seed queries through a search API (Brave or Exa, under $3 a month),
the Discourse Discover directory, a monthly Common Crawl query, and outbound links in
collected posts. Each candidate goes through software detection, a robots.txt and terms
check, a quarantined sample, and a detail score (distinct-author growth, thread depth,
jargon density, specificity, unanswered questions). Edgar approves it through a source
card in stage 8, and it is re-scored quarterly.

Every collector reports a health check and a last-success timestamp. The app shows
stale collectors prominently, because APIs change without warning.

### Stage 2 — Extract

Rule filters drop obvious noise. An LLM then turns each surviving item into one pain
record: job, outcome sought, who (segment hint), current workaround, spend or time cue,
intensity, and a verbatim quote with character offsets. Fields are written in English;
the quote stays in its original language with a language code. Items with no pain get
`is_pain = false` and stay stored. Extraction caches on `(content_hash, prompt_id)`, so
unchanged items never re-run.

### Stage 3 — Map

The pipeline embeds the normalized `problem + who` string locally with a multilingual
model (`multilingual-e5-small` on CPU) and assigns each record
to the nearest canonical problem above a similarity threshold (start at cosine 0.88).
Unassigned records join a candidate pool that HDBSCAN clusters weekly; clusters of three
or more distinct authors become new problems. Pairs in the 0.80–0.88 band enter a merge
queue Edgar approves. An alias table keeps old problem IDs resolvable.

Each run writes one snapshot row per problem: mentions, distinct authors, source count,
and engagement. The app shows "insufficient data" for trends until eight weeks accumulate,
then flags anomalies with a median/MAD z-score.

Problem titles follow job + outcome form and must admit several solutions.

### Stage 4 — Steer

The radar lists problems with trend sparkline, distinct authors, source count, and status
(new, watching, promoted, archived, merged). Edgar watches, promotes, kills, merges, or
splits problems, and attaches a segment to promoted ones. Every action records a reason
code and optional note. Promoting a problem can also propose new sector sources to collect.

### Stage 5 — Score

Scoring uses the rubric from report 03, versioned in the repo:

| Criterion | Weight | Gate |
|---|---|---|
| Pain intensity | 20% | ≥ 3 at Medium confidence |
| Willingness to pay | 20% | ≥ 3 at Medium confidence |
| Underserved | 15% | |
| Frequency | 10% | |
| Reachability | 10% | |
| Why now | 10% | |
| Segment size (bottom-up) | 10% | |
| Risk (inverted) | 5% | |

Each criterion scores 1–5 against written anchors and cites evidence IDs. Evidence items
carry a level: E1 said, E2 described past behavior, E3 observed spend, E4 commitment to
us. Confidence derives from the evidence, never from the model: High needs two
independent E3 items. Uncited criteria score 2, Low. The weights are a starting guess.

Evidence extraction and scoring run as separate passes. The shortlist gets a pairwise
ranking, run in both orders to cancel position bias. Several independent scorer runs
flag spreads of two points or more instead of averaging them away.

### Stage 6 — Ideate

Generation seeds from concrete evidence, rotates personas and patterns (unbundle,
vertical tool, service-first, marketplace), and deduplicates each idea against all past
ideas by embedding. Each idea lists its assumptions and a kill condition.

### Stage 7 — Dossier

The dossier follows report 03's 14-section outline: structured problem statement and
falsifiable hypothesis, scorecard, demand evidence, workarounds and spend, competitors and
their reviews, pricing, bottom-up size, reachability, why now, risks, assumption map, test
plan, kill criteria with dates, and an evidence appendix. A read-only red-team agent
attacks each dossier before Edgar sees it. Real-world test tooling (scripts, landing
pages, result tracking) comes after v1.

### Stage 8 — Reassess and improve

The tool audits itself weekly and improves through a fixed loop: measure, diagnose,
propose, approve, build, verify, integrate, record. Python computes the metrics; an
auditor agent reads them and writes improvement cards; Edgar approves cards in the app;
a builder agent implements each approved card on its own branch.

**What it measures.** Each layer has metrics, logged per run to a `metric` table:

| Layer | Metrics |
|---|---|
| Sources | Uptime, pain yield per 100 raw items, unique problems contributed, distinct authors, overlap with other sources, cost, terms status |
| Coverage | Problems and items by region (US, EEA, UK), language, and segment; gaps against targets |
| Extraction | Precision and recall against the eval set |
| Mapping | Cluster churn week to week, merge and split rates, duplicate rate, trend false alarms |
| Judgment | Scorer re-run variance, judge spread, agreement between the radar's ranking and Edgar's promotions and kills |
| Methodology | Which rubric criteria predict Edgar's decisions and, later, test outcomes; recurring red-team findings; kill-reason distribution |

**Evaluating the evaluation.** Metrics can drift, overfit, or measure the wrong thing,
so the loop checks its own instruments:

- **Held-out set.** Edgar labels a set no agent sees while building improvements. Gains
  on the working eval set that fail to appear on the held-out set mean overfitting.
- **Blind audit.** Each month Edgar labels 20 random items without seeing model output.
  Disagreement with the eval set's labels measures label drift; disagreement with the
  model measures true error.
- **Mutation tests.** The loop injects known faults each week: a problem disguised as a
  solution, fabricated demand, a duplicate problem, a dead collector, an uncited score.
  A metric that misses its fault is broken and gets a card of its own.
- **Coverage of the eval set.** A new source, language, or segment with too few labeled
  items triggers a labeling card.
- **Metric usefulness.** A metric whose movements never match Edgar's judgment gets
  retired.

**Improvement cards.** Each card states the observation with its metric and evidence, a
hypothesis, the proposed change, the expected metric effect, risk, and size. The auditor
ranks cards by expected value over effort. Cards also cover sources: proposals to add a
discovered forum or regional source, or to drop a low-yield one.

**Guardrails.**

- A change touches the system or its evaluation, never both. This stops the tool from
  grading its own homework.
- Agents never read or edit the held-out set.
- Every build runs on a branch, passes tests and an eval diff with no regression on the
  held-out set, gets a reviewer agent's check, and merges only with Edgar's approval.
- Without approval, the loop may only take reversible actions: pause a failing collector,
  retry, alert.
- At most two cards get built per week, so changes stay attributable.
- A metric that regresses after a merge triggers a revert card.

## Architecture

```
Task Scheduler (weekly)         Claude Code (on demand)
        │                               │
  Python pipeline ──writes──▶  SQLite (WAL)  ◀──reads / writes via pipeline CLI── agents
                                    ▲
                                    │ reads; writes steering decisions only
                              Next.js app (localhost)
```

- **Python pipeline** owns all deterministic work: collect, filter, embed, cluster,
  snapshot, validate. Libraries: httpx, feedparser, pydantic, sentence-transformers (CPU, multilingual),
  scikit-learn HDBSCAN, UMAP, statsmodels. Managed with uv.
- **SQLite** in WAL mode is the single store, with sqlite-vec (version pinned) for
  vectors. The database file stays out of git.
- **Next.js** is the viewing and steering layer. It reads everything and writes only
  steering decisions and statuses. Node 24's built-in `node:sqlite` for access, so
  no native driver builds on Windows.
- **Claude agents** do judgment work. They write only through pipeline CLI commands
  that validate JSON with pydantic and tag rows with run and prompt; they never run raw
  SQL writes.

### Core tables

`raw_item`, `run`, `prompt`, `extraction`, `embedding`, `problem`, `problem_member`,
`problem_alias`, `snapshot`, `segment`, `problem_segment`, `evidence`, `score`, `idea`,
`dossier`, `decision`, `collector_health`, `lookup_cache`, `metric`, `mutation`,
`improvement_card`. Report 04 sketches the columns.

### Agents and skills

| Name | Kind | Job |
|---|---|---|
| `/weekly-run` | Skill | Run the pipeline, then extraction (if run in Claude Code), curation, and a radar summary |
| `cluster-curator` | Subagent | Name new problems, propose merges and splits |
| `/score` + `scorer` | Skill + subagent | Gather evidence, score against the rubric, rank pairwise |
| `idea-generator` | Subagent | Generate diverse ideas under a problem + segment |
| `dossier-writer` | Subagent | Write the dossier and test plan |
| `red-team` | Subagent, read-only | Attack scores and dossiers |
| `/eval` | Skill | Run the eval set and diff results against the last prompt version |
| `/add-source` | Skill | Scaffold a new collector from a template |
| `/reassess` + `auditor` | Skill + subagent, read-only | Diagnose weekly metrics and mutation results, write improvement cards |
| `/improve` + `builder` | Skill + subagent | Build one approved card on a branch in its own worktree |
| `reviewer` | Subagent, read-only | Check a card's diff, tests, and eval diff before Edgar merges |

## Automation

Python and Windows Task Scheduler run everything deterministic without a session:
collect, filter, embed, cluster, snapshot, compute metrics, run mutation tests, and
queue work for Claude. The weekly script then calls Claude Code headless
(`claude -p "/weekly-run"`) with a narrow tool allowlist, so extraction and the audit run
unattended under Edgar's subscription. If a headless run fails, the queue waits for the
next interactive session and the app shows the backlog. All LLM work sits behind one
runtime interface, so moving bulk extraction to the Claude API later changes config, not
code.

The interface also admits a second provider, Mistral, for three jobs: OCR of PDF sources
to Markdown (from the Financial Ombudsman decisions in v2), a second judge from a
different model family in stage 5, and a second idea generator in stage 6. Model families
share biases, so a cross-family jury and pooled generation reduce them. Extraction of
non-English text stays with Claude unless stage 8 shows it lagging English. Each
row records its provider and model.

## Eval set

- The working eval set starts with ~200 hand-labeled items (pain or not) and 30–50
  known-good and known-bad problems, and grows from steering decisions.
- The held-out set starts at ~100 items, labeled by Edgar and stored where agents cannot
  read it.
- Prompts and the rubric are versioned by content hash. No prompt or rubric change ships
  without an eval diff.

## Non-goals for v1

Founder-fit scoring, real-world test execution, deployment, authentication, multiple
users, paid data sources.

## Success criteria for v1

1. Four consecutive weekly runs complete unattended for the harvest stage.
2. The weekly audit produces cards, at least one card is built and merged through the
   loop, and every mutation test is caught.
3. The radar shows at least 50 canonical problems, each with linked verbatim quotes.
4. Edgar takes one problem from radar to dossier inside the app and Claude Code.
5. The citation validator passes on that dossier: every claim cites an evidence item.
6. v1 costs $0 beyond Edgar's existing Claude subscription.

## Decisions

1. **LLM runtime:** Claude Code, run headless from the weekly script where possible.
2. **Geography:** the US, the EEA, and the UK, all required from v1. Sources in other
   languages need multilingual extraction and a multilingual embedding model.
3. **Reddit:** Edgar files a non-commercial research access request. Other forums and
   review sites replace Trustpilot's role; a forum-discovery loop comes later and feeds
   source cards into stage 8.
4. **Name:** `startup-ideas-generator`.
5. **Gray sources** (Stack Exchange, EU Have Your Say) run by default, decided
   2026-10-13: private analysis only, no training, no republishing of their text.
6. **Weekly run:** Mondays at 10:00 via Task Scheduler; forums poll daily at 09:00,
   because their feeds turn over within hours. The 9 seed forums are confirmed.
8. **Source review, 2026-10-13** (Edgar's labels): GOV.UK and EU Have Your Say stop as
   streams and serve on-demand "why now" lookups; Stack Exchange narrows to diy and
   webapps. Stage 1's table lists what was built; `default_on` decides what runs.
7. **Sources whose terms forbid reproduction** (e.g. Futura-Sciences) may run with
   `retain_text = false`: extraction runs in the same pass and only derived fields plus
   the URL are stored. Their evidence counts as paraphrase, weaker than a verbatim quote.

## Discovery costs

Forum discovery adds the first recurring paid item, a search API under $3 a month.
It arrives in Phase 7 and needs Edgar's approval.
