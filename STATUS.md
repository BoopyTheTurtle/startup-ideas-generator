# Status

The handoff log. Read this first when picking up work; update it before you stop.
`PLAN.md` holds the phases; this file holds where work stands right now. Newest entry
on top. Keep "Current state" accurate; append to "Log".

## Current state (2026-10-13)

**Phase:** 1b done pending Edgar's answers below. Next: Phase 2 (extract and map).

**Running weekly:** Task Scheduler task `startup-ideas-generator weekly`, Mondays 10:00,
runs `scripts/weekly.ps1` (collect + health). First scheduled run: 2026-10-19.

**Collectors**

| Name | State | tos_class | Notes |
|---|---|---|---|
| hn | live | clean | ~44 items/week from pain phrases; too thin, a stage 8 target |
| stackexchange | live | gray | 15 non-programming sites; 300 requests/day keyless quota |
| uk_petitions | live | clean | open + rejected petitions |
| eu_haveyoursay | live | gray | undocumented API; fixtures local-only |
| appstore | built, off | restricted | robots.txt and Apple terms forbid it; runs only with `--only` |
| govuk | live | clean | consultations + CMA cases; one item per stage (CMA: per case_state) |
| wordpress | live | gray | 105-plugin pool, 35 per run; plugins API blocked by robots.txt, uses directory REST routes; fixtures local-only |
| firefox_addons | live | gray | AMO ratings ≤ 3 stars; fixtures local-only; few hundred items/run max |
| forums (generic) | live, 9 forums | per forum | 170 items; every feed returned its full window, so weekly runs miss most posts; Futura-Sciences (gray) off |

**Waiting on Edgar**

1. Confirm the 9 forum seeds approved on his behalf (`forums.toml`), incl. Contractor UK
   now gray (named AI-bot block in robots.txt).
2. Daily forum polling: add a second scheduled task running `collect --only forums`?
   Feeds hold 15-20 threads and turn over in hours.
3. Futura-Sciences (gray; its notice forbids electronic reproduction): enable or skip.

**Next steps**

1. Phase 2: extraction and mapping (SPEC stages 2-3, PLAN Phase 2).
2. Stage 8 backlog (from reviews): HN volume; Stack Exchange partial runs should use
   `warnings`; GOV.UK per-document isolation; content-hash dedup for identical stage
   bodies; robots `Content-Signal` lines (e.g. ai-train=no) recorded per source.

**Decisions made** (also in SPEC "Decisions")

- Gray sources run by default; private analysis only, no training, no republishing.
- Restricted sources never run by default.
- Fixtures for non-clean sources stay out of the public repo.
- Edgar wants no founder-fit scoring; market merit only.

**Gotchas**

- Paths contain spaces. PowerShell 5.1 has no `&&`.
- `next dev` is Next.js 16: read `web/node_modules/next/dist/docs/` before writing app code.
- The Stack Exchange quota is 300 requests/day per IP; avoid re-recording it often.
- Officials' names and contact details appear in some GOV.UK CMA bodies; extraction
  should drop contact details.

## Log

### 2026-10-13

- Phase 1b review fixes: `Collector.guarded()` isolates units (forums, plugins, add-ons)
  with per-unit failure streaks; a run where every unit fails is 'failed'; forum bodies
  drop quotes and phpBB footers (usernames); phpBB sids stripped in Atom; 'active' feeds
  leave created_at empty; CMA ids include case_state; GOV.UK fixture emails redacted.
  Purged and re-collected forums and govuk rows. Database: 1,566 items.

- Forum seeds vetted (report 07: 82 endpoints probed, 9 clean seeds approved by
  delegation). Added XML-declaration decoding, a 'partial' run status, per-forum failure
  isolation, phpBB sid stripping. Forums first run: 170 items.
- Phase 1b: govuk, wordpress, firefox_addons collectors (wordpress and firefox gray,
  fixtures local-only); generic forums collector with TOML config; fixed a
  clock-dependent Stack Exchange test.

- Interviewed Edgar; wrote SPEC.md and PLAN.md; six Stage 0 research reports.
- Phase 0: skeleton (uv, SQLite WAL, Next.js 16 with `node:sqlite`), public repo
  https://github.com/BoopyTheTurtle/startup-ideas-generator.
- Phase 1a: collector base, HTTP record/replay, RFC 9309 robots matcher, runner, five
  collectors. First harvest: 479 items. CFPB dropped (narratives unpublished since
  2026-08). Code review fixes applied.
- Registered the weekly task (10:00 Mondays). Started Phase 1b.
