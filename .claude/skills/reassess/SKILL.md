---
name: reassess
description: Weekly reassessment of the startup-ideas-generator pipeline. Runs `pipeline reassess` (metrics, mutation tests, revert and instrument cards, digest), then the read-only auditor to propose improvement cards for Edgar to approve in the app. Use when Edgar says "reassess", after a weekly run, or from the weekly script.
---

# /reassess

The loop's measure, diagnose, and propose steps (SPEC stage 8). Approving, building, and
merging come later and belong to Edgar and /improve.

1. From the repo root run `uv run python -m pipeline reassess`. It logs the metrics, runs
   the mutation tests on a scratch copy of the database, opens `instrument` cards for any
   metric that missed its fault and `revert` cards for merged changes that regressed, and
   writes a digest. If it fails, report the error and stop.
2. Start the `auditor` subagent. Tell it only: "Run the weekly audit. Digest is
   `pipeline digest`." Do not paste metrics into its prompt; it reads them itself.
3. When it returns, run `uv run python -m pipeline cards --status proposed approved` and
   give Edgar a short summary: this week's cards by rank (id, title, touches, size, value),
   any instrument or revert cards the system opened, and the number of mutations missed.
4. Say where to act: the app's Cards page (`npm --prefix web run dev`, then /cards)
   approves or rejects cards. Edgar's decisions are the only way a card reaches /improve.

Do not approve, reject, or build cards here. Do not run `extract`, `curate`, or `eval`.
