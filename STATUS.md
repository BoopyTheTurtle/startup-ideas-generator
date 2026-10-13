# Status

The handoff log. Read this first when picking up work; update it before you stop.
`PLAN.md` holds the phases; this file holds where work stands right now. Newest entry
on top. Keep "Current state" accurate; append to "Log".

## Current state (2026-10-13)

**Phase:** 2, Extract and map (in progress).

**Scheduled (Task Scheduler, current user):**
- `startup-ideas-generator weekly`: Mondays 10:00, `scripts/weekly.ps1` (all collectors
  except forums, then health). First run 2026-10-19.
- `startup-ideas-generator forums daily`: 09:00 daily, `scripts/daily-forums.ps1`. First
  run 2026-10-14.

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

**In progress (Phase 2)**

- Done: schema (migration 003), `pipeline.llm` (headless `claude -p`, model
  claude-haiku-5-5), `pipeline.extract` + `scrub` (quotes verified against plain text;
  no-retain sources keep paraphrases only), extraction wired into both scripts with caps.
  Futura-Sciences enabled with retain_text = false. Live: 0 quote misses in 77 items;
  cost ~$0.01 of API-equivalent per item (subscription usage).
- Agents building in parallel: embeddings + mapping (`pipeline/embed.py`, `mapping.py`)
  and labeling page `/label` + `pipeline/evals.py`. Their files are uncommitted until
  reviewed. `pipeline/__main__.py` PLUGINS must list extract, evals, and the mapping
  modules once they exist; the daily task (09:00) runs from the working tree.
- Then: integrate, add `map` to weekly.ps1, curator naming, review, commit, demo.

**Next steps**

1. Phase 2: extraction and mapping (SPEC stages 2-3, PLAN Phase 2). Include a per-source
   `retain_text = false` mode: extract in the same run, store derived fields + URL only,
   never the post text. Then enable Futura-Sciences with it (Edgar's call, 2026-10-13).
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

- Stage 3 (map) built: `pipeline/embed.py` (multilingual-e5-small, CPU) and
  `pipeline/mapping.py`; CLI `embed`, `map`, `problems`, `merge`. Thresholds raised from
  SPEC's 0.88 / 0.80 to 0.94 assign, 0.93 cluster cohesion, 0.91 merge floor: e5 crowds
  cosines high, and 0.88 put 260 of 266 real pains into 14 mostly unrelated problems.
  First live map (runs 11-12): 266 pains, 3 problems, 253 pooled, 3 merge candidates.

- Phase 2 started: schema, extraction via headless Claude Code, extract-and-discard
  for Futura-Sciences; agents on mapping and on labeling/eval tooling.

- Edgar confirmed the 9 forum seeds and daily forum polling; registered the daily task
  (09:00) and made the weekly run skip forums (`collect --skip`). Futura-Sciences waits
  for a retain_text=false mode in Phase 2.

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
