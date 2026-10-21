# Status

The handoff log. Read this first when picking up work; update it before you stop.
`PLAN.md` holds the phases; this file holds where work stands right now. Newest entry
on top. Keep "Current state" accurate; append to "Log".

## Current state (2026-10-21)

**Incident, found 2026-10-21:** the scheduled tasks were being killed with exit code
`3221225786` (0xC000013A, a closed console window or logoff). Forum runs died on 14, 19, and
21 Oct; the weekly run on 19 Oct never completed; nothing but forums collected between 13 and
21 Oct, and `reassess` did not run. Fix on `fix/scheduled-task-window` (PR into `dev`): the
tasks launch through `conhost --headless` (no window to close), the trigger is pinned to local
time (it was fixed to UTC+3, so 10:00 would have become 09:00 after DST ends on 25 Oct), and
any writing command now fails run rows left at `running` by a killed process
(`runs.sweep_stale`, under the pipeline lock). Edgar approved the fix; tasks re-registered
from the branch on 2026-10-21. After the PR merges: `git checkout dev && git pull`.
Done by hand the same day: `collect --skip forums` (1,095 new items; 2,101 items still
unextracted, which spends Edgar's subscription, so his call). Confirm tomorrow that
`data/logs/forums-2026-10-22.log` ends with `scrub`, and Monday's `weekly-2026-10-26.log`
reaches `reassess`.

**Fix verified (2026-10-21 evening):** the daily task, started through Task Scheduler with the
headless action, ran to the end (result 0) and the stale rows 35 and 36 were failed by the
sweep. **New blocker:** the headless `claude` login has an expired OAuth token (`401 ... OAuth
access token has expired`, also from an interactive shell), so every extraction call failed
(149 items, no data lost: they stay unextracted). Only Edgar can fix it: run `claude auth login`
in a terminal, then `uv run python -m pipeline extract --max-items 20` to confirm. Until then
the weekly run collects but cannot extract, name themes, or curate. Weakness found: an
`extract` run whose every LLM call fails still records status `ok` and the scripts ignore its
exit code; it should fail the run and show on the radar/health, and a failed login should
raise a card (stage 8 backlog).

**Cards (2026-10-21, evening):** at http://localhost:3000/cards. Card 2 (three more US forums,
marked `clean` on Edgar's chat instruction of 2026-10-18) is merged into `dev` (403f1c3); watch
`coverage.region_gap` for US over the next weekly cycles. Card 1 (looser cluster cohesion
floor) was cut back at Edgar's decision: the floor stays at 0.93 and the card ships only the
two new counters `clusters_rejected_trim` and `clusters_rejected_authors` (trim caused 38 of 40
rejections). Trial at 0.92 / 0.91 gave 1 / 3 new problems but tripped `duplicate_rate` (a
Wordfence problem sat at 0.92 cosine to the live Firefox extension problem) and `pool_share`
stayed at 0.933 / 0.912. The reviewer approved; card 1 is `ready`, branch
`card/1-trial-a-looser-cluster-cohesion-floor-so` (de0cb19), waiting for Edgar's merge approval
in the app.

(The 2026-10-14 notes below are still accurate for everything not mentioned here.)

## Current state (2026-10-14, end of day)

**Phase:** 4 built and under review (reassess-and-improve loop). Phase 3 demo (Edgar's
first steering session) and the consistency check (/label/recheck) are still pending.

**Reminders for Edgar** (a session that reads this on or after the date raises the item
first thing, then marks it done here)

- **Due 2026-11-02, then monthly:** blind audit. Run `uv run python -m pipeline audit-draw`,
  label the 20 items at /audit without looking at model output, then run
  `uv run python -m pipeline audit-score`. Claude cannot run the draw (denied).
- **Due after Monday 2026-10-26's weekly run** (two scheduled `reassess` runs on record):
  decide whether to set `SIG_HEADLESS_AUDIT=1` on the weekly task so the auditor runs
  unattended on his subscription. Off until he says so. Check first that `reassess` ran
  cleanly in `data/logs/weekly-*.log` and that any cards from cards 1 and 2 behaved.

**Phase 4 state (2026-10-14)**

- Five stacked PRs on GitHub, base `dev` (which equals `main`): #1 cards and state, #2
  metrics and mutations, #3 agents and skills, #4 review fixes, #5 Cards and Audit pages.
  Merge them in order after review. The permission check blocked Claude from merging #1
  without review, so nothing has landed on `dev`.
- Git workflow: `main` = finished phases, `dev` = integration, `phase-N/<piece>` and
  `fix/<topic>` branches into `dev` by PR. The checkout sits on `fix/phase-4-review`
  (Python and agents, no new pages). The scheduled tasks run from this folder, so keep it on
  a tested branch. To see the new pages before merging: `git checkout phase-4/web-cards-audit`.
- Live data: `reassess` run 29 logged 53 metric values and 22 mutation checks; none
  missed. The auditor proposed card 1 (looser cluster-cohesion floor: map run 28 rejected
  40 of 40 candidate clusters, `pool_share` 0.96) and card 2 (vet more US forums: US share
  8% against a 20% target). Both wait for Edgar at /cards.
- Edgar's to-do for the loop: PRs #1-#5 merged 2026-10-14, but #2-#5 merged into their stacked
  base branches, so `dev` has only #1. PR #6 (fix/phase-4-review -> dev) lands the rest: merge
  it, then `main` follows at phase end. Cards 1 and 2 decided at /cards. Reminders below.
- Known limits: the metrics' thresholds are placeholders (region targets 20% each, stale
  after 8 days); one reading is weak evidence while data is young; the extraction eval gate
  compares working-set scores only and cannot tell apart a code change that leaves the
  prompt text unchanged (the held-out check covers that case); run 21 is a stale 'running'
  extract row.

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

**Phase 3 state (2026-10-14)**

- Built, reviewed (code + accessibility), fixed, committed: themes layer, migration 006
  (`pipeline_state.active_extract_prompt_id`, theme provenance), steering UI (radar,
  themes, problems with steering actions, merges via `pipeline merge --reason --note`,
  runs), label/recheck fixes. App bound to 127.0.0.1. 222 tests.
- Next: Phase 3 demo = Edgar's first steering session (radar → themes → problems →
  watch/promote/archive with reason codes; resolve the 3 open merge candidates). Then
  Phase 4 (reassess-and-improve loop).
- Still pending from Edgar: the consistency check at /label/recheck.

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
- Lookup groups from report 01 (search demand, labor market, regulation, funding,
  patents/research, macro/trade/shipping, e-commerce) stay as planned: scoring inputs in
  Phase 5, lookups in Phase 7. Edgar confirmed 2026-10-14 after asking about them.

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

- Edgar merged PRs #1-#5 (stacked, so dev still lacks #2-#5; PR #6 fixes that) and decided cards 1 and 2. Logged two reminders (monthly
  blind audit from 2026-11-02; headless-auditor decision after 2026-10-26).

- Phase 4 built: cards and guardrails, 22 mutation-tested metrics, `reassess`, blind
  audit, auditor/builder/reviewer agents, /cards and /audit pages. An independent review
  found three guardrail bypasses (rename, case, moved branch ref) and others; fixed. First
  live reassess and audit: two cards proposed. 281 tests.

- Phase 3 review fixes landed (300e349 Python, d1fe66f web).

- Phase 3 started: migration 005; agents on themes (Python) and steering UI (web).

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
