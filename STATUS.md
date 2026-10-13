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

**Phase 2 state**

- Built, reviewed, fixed, committed: extraction (headless `claude -p`, claude-haiku-5-5,
  settings/hooks/MCP off, Unicode-safe quote grounding, opt-in re-extraction, batch
  splitting), extract-and-discard (titles blanked too, copied-text checks, secure_delete),
  mapping (e5-small; 0.94/0.91 thresholds; membership carried across re-extraction;
  migration 004; clusters computed outside the write txn), curator (claude-sonnet-5-5),
  /label + `eval` (held-out results never touch the DB), cross-process lock, atomic
  migrations. 192 tests.
- Live: 1,600 raw items, 380 extracted (prompt 0c6c40f4e6c5), 266 pains, 3 problems.
  The extract prompt is now 5f6ac038f30e (untrusted-data rule); new items use it,
  old ones keep theirs unless `extract --reextract`.
- Waiting on Edgar: label ~200 working + ~100 held-out items at /label (needed for the
  Phase 2 eval demo); decide on a `.claude/settings.json` deny rule for evals/heldout/.
- Edgar, labeling: "mostly noise, will have to re-evaluate sources". Once labels exist,
  run `eval-status` and `eval --prompt-version 0c6c40f4e6c5` for per-source pain rates
  and precision, and bring a source review (keep / narrow / drop) to Edgar.
- Decided: Phase 3 starts with a themes layer (loose topic clusters recomputed each run,
  never stored as problems) as the radar's broad entry point.

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

- Phase 2 review: 13 findings fixed by two agents (extraction side, mapping side);
  migration 004 applied live; map rerun idempotent.

- Phase 2: mapping, curator, /label, eval commands built and committed (70c3fd4).
  Experiment: mean-centred e5 vectors form topic neighbourhoods, not same-problem groups;
  basis for a proposed themes layer.

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
