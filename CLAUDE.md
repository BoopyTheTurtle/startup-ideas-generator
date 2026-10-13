# CLAUDE.md

Startup ideas generator: a weekly pipeline that mines public complaint data for problems,
plus a local Next.js app where Edgar steers the narrowing from problems to a validated
idea. `SPEC.md` defines the system; `PLAN.md` tracks the build phases; `docs/research/`
holds the research behind both. Read SPEC.md before changing behavior.

**`STATUS.md` is the handoff log.** Read it first. Before you stop, or after any
meaningful step, update its "Current state" and add a dated line to its "Log", so
another session can pick up the work cold.

This is a normal build project. The tutor rules from `Projects\Learning to code` do not
apply here.

## Layout

| Path | Contents |
|---|---|
| `pipeline/` | Python package: CLI, DB access, collectors, extraction, mapping, metrics |
| `pipeline/migrations/` | Numbered `.sql` files, applied in order; never edit one that has shipped |
| `tests/` | pytest suite; runs offline |
| `web/` | Next.js app (App Router), reads SQLite through `node:sqlite` |
| `data/ideas.db` | SQLite database, WAL mode, gitignored |
| `evals/working/` | Working eval labels (JSONL), written by the app's /label page |
| `evals/heldout/` | Edgar's held-out eval set, gitignored. Agents never read or edit it, and never run `eval --set heldout`. |
| `pipeline/prompts/` | Prompt texts; versioned by hash in the `prompt` table |

## Commands

```bash
uv sync                                  # Python env (3.12, pinned)
uv run pytest -q                         # Python tests
uv run python -m pipeline migrate        # apply migrations
uv run python -m pipeline smoke          # write a test run + metric
uv run python -m pipeline status         # recent runs
uv run python -m pipeline collect        # all non-restricted collectors (--only NAME ...)
uv run python -m pipeline health         # collector health
SIG_HTTP=record uv run pytest tests/collectors/test_NAME.py   # re-record fixtures
uv run python -m pipeline extract        # stage 2 via headless `claude -p` (--max-items N);
                                         # new items only; --reextract after a prompt change
uv run python -m pipeline scrub          # blank text of no-retain items once extracted
uv run python -m pipeline map            # stage 3: embed, assign, cluster, snapshot
uv run python -m pipeline curate         # name new problems (LLM)
uv run python -m pipeline problems       # top problems
uv run python -m pipeline merge KEEP DROP --reason TEXT
uv run python -m pipeline eval-status    # label counts (safe for agents)
uv run python -m pipeline eval           # working-set scores; --set heldout is Edgar's only
npm --prefix web run dev                 # app on http://localhost:3000
npm --prefix web run lint
```

`SIG_DB` overrides the database path for both Python and the app; `SIG_ROOT` overrides the
repo root the app uses to find `evals/`.

Write commands take a cross-process lock (`data/.pipeline.lock`) so scheduled tasks never
overlap; they wait up to `--lock-wait` minutes (default 60), then exit 75. Read-only
commands (status, health, problems, eval-status) skip it.

`extract`, `curate`, and `--reextract` spend Edgar's Claude subscription: run them only
when the task needs it, with a `--max-items` cap.

## Rules

- Python owns all writes except steering decisions and eval labels, which the app writes.
- LLM calls go through `pipeline.llm` (a Runtime); never call a model directly.
- Agents write to the database only through `python -m pipeline` commands, never raw SQL.
- Every derived row records the run that produced it; LLM-derived rows also record the
  prompt version and model.
- "Active" pains: an item's extraction under the current prompt, else its latest
  (`embed.ACTIVE_PAIN_SQL`). Re-extracted pains carry their problem membership.
- Migrations run atomically; never put BEGIN/COMMIT in a migration file.
- Log metrics with `pipeline.runs.log_metric` for every new stage (SPEC stage 8).
- A change touches the system or its evaluation, never both.
- Paths contain spaces; quote them in shell commands.

## Collectors

- One module per source in `pipeline/collectors/`, discovered automatically. Copy
  `hn.py` and `tests/collectors/test_hn.py`.
- Honor `max_items`; save cursors in `State` before yielding where possible.
- Never store or read personal names: `author` is hashed by the runner; citizens get None.
- Call `require()` on every response and item; undocumented APIs must fail loudly.
- Set `tos_class` honestly. `restricted` sources run only with `--only`. `Http` checks
  robots.txt (RFC 9309, `pipeline/robots.py`) for every live URL.
- Replay tests use fixed cursors. Fixtures go in `tests/fixtures/<name>/`; gitignore them
  when the source's terms forbid republishing (appstore, eu_haveyoursay).
