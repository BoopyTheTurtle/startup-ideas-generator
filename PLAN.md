# Build plan

Draft 1, 2026-10-13. Implements `SPEC.md`. Each phase ends with a demo and Edgar's
go-ahead before the next starts.

## Phase 0 — Skeleton

Set up the repo and prove the three layers talk to each other.

- Check the toolchain: Python, uv, Node, git, gh.
- `git init`, public GitHub repo, `.gitignore` covering `data/`, `.env`, and model caches.
- Project `CLAUDE.md` with commands and layout.
- `pipeline/` Python package with a CLI (`python -m pipeline ...`), `schema.sql`, and
  numbered migrations.
- `web/` Next.js app that reads one table and renders it.
- `metric` table and a `log_metric` helper, so every later phase reports from day one.

**Demo:** the CLI inserts a row; the app shows it.

**Shipped 2026-10-13.** Python 3.12 via uv, SQLite in WAL mode, Next.js 16.4 reading
through `node:sqlite` instead of better-sqlite3. A run written while the app was open
appeared on refresh.

## Phase 1 — Harvest

- Collector base class: fetch, normalize to `raw_item`, record health, check robots.txt,
  tag licence, country, and language.
- Phase 1a streams: Hacker News, Stack Exchange, App Store reviews (US, EEA, UK
  storefronts), CFPB, UK Parliament petitions, EU Have Your Say.
- Phase 1b streams: GOV.UK consultations and CMA cases, WordPress.org support feeds,
  Firefox Add-ons reviews, and the generic forum collector with Edgar's 5–10 seed forums.
- Schema checks for undocumented APIs.
- Recorded fixtures per collector, so tests run offline.
- `python -m pipeline collect` and a Task Scheduler entry for weekly runs.
- Source metrics: uptime, items, distinct authors, region, language.

**Sub-agents:** one builder per collector in parallel worktrees, from the base class
template; a reviewer checks each against the source's terms.
**Demo:** a full harvest run; row counts and health per source.

## Phase 2 — Extract and map

- Rule filters and the extraction prompt, behind one runtime interface (Claude Code
  first, API batch later).
- Local embeddings, centroid assignment, candidate clustering, merge queue, aliases.
- Weekly snapshots.
- Eval set v0: Edgar and Claude hand-label ~200 items; Edgar alone labels the ~100-item
  held-out set.
- Headless `claude -p "/weekly-run"` step in the weekly script, with a tool allowlist.
- Extraction and mapping metrics.

**Sub-agents:** `cluster-curator` defined and tried on real clusters.
**Demo:** first problem list with quotes; eval precision on the labeled set.

## Phase 3 — Steering UI

- Radar with sparklines, filters, and collector health banner.
- Problem detail: statement, quotes with links, snapshot chart, actions with reason codes.
- Merge queue, runs and cost page.

**Sub-agents:** frontend builder; accessibility and UX review at the end.
**Demo:** Edgar runs one weekly steering session in the app.

## Phase 4 — Reassess and improve

Runs on harvest, extract, and map, which by now have several weeks of data.

- Mutation tests for every metric built so far.
- `/reassess` skill and read-only `auditor`; improvement cards stored and shown in the app
  with approve and reject actions.
- `/improve` skill, `builder` in its own worktree, `reviewer`; eval diff gate with the
  held-out check.
- Guardrails: system-or-eval separation, two cards per week, revert cards on regression.
- Monthly blind-audit flow in the app.

**Demo:** one weekly cycle from metrics to a merged improvement.

## Phase 5 — Scoring

- Evidence table with levels E1–E4; confidence computed in Python.
- Rubric v1 file; `/score` skill and `scorer` subagent; pairwise ranking with order swap.
- Scorecard view showing confidence, cited evidence, and judge spread.

**Demo:** a scored and ranked shortlist of five promoted problems.

## Phase 6 — Ideas and dossier

- `idea-generator` with persona and pattern rotation and history dedup.
- `dossier-writer`, `red-team`, and the citation validator.
- Dossier and test-plan views.

**Demo:** one problem taken from radar to validated dossier. This meets the v1 success
criteria once four weekly runs have accumulated.

## Phase 7 — Widen

Ordered by value, each item separately approved:

- v2 streams, global: Bluesky, GitHub issues, Atlassian, Steam, JetBrains, VS Code.
- v2 streams, US: openFDA, NHTSA, Federal Register.
- v2 streams, UK and EEA: Financial Ombudsman decisions, written questions, Safety Gate,
  TED and Find a Tender, Adzuna.
- Lookups: Google Trends, FRED, EDGAR Form D, Eurostat, ONS, ECB, Companies House.
- Source proposals after promotion; `/add-source` skill.
- Forum discovery, feeding source cards into the weekly loop.
- Move extraction to the API batch endpoint if volume demands.
- Real-world test tooling: interview scripts, landing pages, result tracking.

## Throughout

- A code reviewer checks each phase's diff before the demo.
- The eval set grows from steering decisions.
- From Phase 4 on, each new stage registers its metrics and mutation tests with the loop.
- `PLAN.md` records what shipped and what changed.
