# Status

The handoff log. Read this first when picking up work; update it before you stop.
`PLAN.md` holds the phases; this file holds where work stands right now. Newest entry
on top. Keep "Current state" accurate; append to "Log".

## Current state (2026-10-13, end of day)

**Phase:** 2 done except its eval demo; mid-way through the first stage-8-style loop
(source review + extraction prompt tightening). Phase 3 (themes layer + radar) is next.

**Scheduled (Task Scheduler, current user):**
- `startup-ideas-generator forums daily`: 09:00 daily, `scripts/daily-forums.ps1`
  (collect forums, extract forums ≤150, scrub). 90-min limit. First run 2026-10-14.
- `startup-ideas-generator weekly`: Mondays 10:00, `scripts/weekly.ps1` (collect all
  default-on sources except forums, extract ≤600, scrub, map, curate, health).
  First run 2026-10-19. Caps agreed with Edgar: ~1,650 items/week.

**Default-on streams:** hn, stackexchange (diy + webapps only), uk_petitions, wordpress,
firefox_addons, forums (10 forums incl. Futura-Sciences with retain_text = false).
Off by default (run with `collect --only`): govuk, eu_haveyoursay (labels showed noise),
appstore (restricted).

**Data:** 1,600 raw items; ~520 extracted; ~370 pains; 3 problems (all Firefox add-ons).

**Eval:** Edgar labeled 239 working items (76 pain, 146 not, 17 unsure) and is now
labeling the held-out set. Agents never read the held-out set (`.claude/settings.json`
deny rules; `eval-status` shows only its total). Current prompt 5f6ac038f30e on the
working set: precision ~0.49, recall ~0.77. The model calls too much pain, and misses
petitions phrased as solutions.

**Prompt v3 (3f6fc1251c6e, 2026-10-14)** uses Edgar's definition: "a problem many people
share that someone could build a business around, not one person's bug report."
Working set: precision 0.49 -> 0.63, recall 0.77 -> 0.50, accuracy 0.62 -> 0.73;
petitions 0.86/0.86. Recall fell on wordpress (1/12) and firefox_addons (5/17), where
Edgar's labels are inconsistent: near-identical bug reports and data-collection
complaints carry opposite labels. Kept v3 (precision first, matches his definition).
Edgar's held-out run of v3 (2026-10-14): precision 0.24, recall 0.22, F1 0.23 (n 94)
against working F1 0.56. Either v3 overfits the working labels, the held-out mix differs,
or labels are inconsistent; agents can't inspect the held-out set to tell. Next: the
consistency check.

**Next steps**

1. Edgar runs the held-out check on v3 (his commands: `extract --labeled <set> --reextract
   --max-items 150`, then `eval --set <set>`); compare with working-set F1 0.56.
2. Consistency check BUILT: Edgar re-labels 30 working items blind at /label/recheck
   (20 wordpress/firefox_addons, 10 control); then run `pipeline eval-consistency`
   (agreement + Cohen's kappa per group, changed labels). If review kappa is low: sharper
   rule or drop reviews as pain sources; if control kappa is also low, the definition
   itself needs examples.
2. Non-English forums: Edgar marks them "unsure"; suggest browser translate on /label, or
   add an English rendering (costs usage).
3. Phase 3: themes layer (mean-centred e5 topic clusters per run, curator-named), radar,
   problem detail, merge queue, steering actions (PLAN.md).
4. Stage 8 backlog: HN volume; Stack Exchange partial runs should use `warnings`;
   GOV.UK per-document isolation; content-hash dedup of identical stage bodies; robots
   `Content-Signal` lines; embedding model upgrade (embeddinggemma-300m) or LLM-checked
   clustering, since e5-small groups by domain more than by problem.

**Decisions made** (also in SPEC "Decisions")

- Gray sources run by default; private analysis only, no training, no republishing.
- Restricted sources never run by default; `default_on = False` sources only on demand.
- Fixtures for non-clean sources stay out of the public repo.
- No founder-fit scoring; market merit only.
- Extraction via headless `claude -p` on Edgar's subscription (no API key set).
- Themes layer opens Phase 3.

**Gotchas**

- Paths contain spaces. PowerShell 5.1 has no `&&`.
- Any shell command containing the held-out folder's name is denied by project settings;
  write "held-out" in commit messages.
- `next dev` is Next.js 16: read `web/node_modules/next/dist/docs/` before app code.
- Stack Exchange keyless quota: 300 requests/day per IP.
- `extract`, `curate`, `--reextract` spend Edgar's subscription; always cap them.
- Python heredocs in Bash can turn ``/`` into control characters; prefer the Edit tool
  for regex-bearing lines.

## Log

### 2026-10-14

- Held-out F1 0.23 vs working 0.56 on v3. Built /label/recheck + `eval-consistency`.

- Extract prompt v3 from Edgar's pain definition; /label shows the same definition.
  Working-set scores above. Found inconsistent labels on reviews/support posts.

### 2026-10-13

- Source review from Edgar's 239 working labels: govuk and eu_haveyoursay off by
  default (`Collector.default_on`), Stack Exchange cut to diy + webapps. Added
  `extract --labeled`; extracted the labeled items; precision ~0.49. Prompt v3 waits on
  Edgar's pain definition. `eval-status` now hides held-out composition.

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
