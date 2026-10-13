# Status

The handoff log. Read this first when picking up work; update it before you stop.
`PLAN.md` holds the phases; this file holds where work stands right now. Newest entry
on top. Keep "Current state" accurate; append to "Log".

## Current state (2026-10-13)

**Phase:** 1b, Harvest (second half). Phases 0 and 1a shipped.

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
| govuk | built, uncommitted | clean | consultations + CMA cases; integrate next (see below) |
| wordpress | in progress | ? | plugin support feeds |
| firefox_addons | in progress | ? | AMO ratings ≤ 3 stars |
| forums (generic) | not started | per forum | waits for `docs/research/07-seed-forums.md` |

**In progress**

- Collector agents building `wordpress` and `firefox_addons`; a research agent vetting
  seed forums into `docs/research/07-seed-forums.md`. If those files are missing or
  incomplete, redo the work from the briefs implied by SPEC stage 1 and CLAUDE.md
  "Collectors".

**Next steps**

1. Integrate `govuk`: change `source_id` to `<content_id>:<document_type>` so each
   consultation stage (open, closed, outcome) is stored; re-record its fixtures; review.
2. Integrate `wordpress` and `firefox_addons`; gitignore fixtures if their terms are not
   clean.
3. Build the generic forum collector from report 07; Edgar approves the seed set.
4. Code review of Phase 1b, then commit, push, update this file and `PLAN.md`.
5. Phase 2: extraction and mapping.

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

- Interviewed Edgar; wrote SPEC.md and PLAN.md; six Stage 0 research reports.
- Phase 0: skeleton (uv, SQLite WAL, Next.js 16 with `node:sqlite`), public repo
  https://github.com/BoopyTheTurtle/startup-ideas-generator.
- Phase 1a: collector base, HTTP record/replay, RFC 9309 robots matcher, runner, five
  collectors. First harvest: 479 items. CFPB dropped (narratives unpublished since
  2026-08). Code review fixes applied.
- Registered the weekly task (10:00 Mondays). Started Phase 1b.
