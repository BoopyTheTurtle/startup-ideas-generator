# CLAUDE.md

Startup ideas generator: a weekly pipeline that mines public complaint data for problems,
plus a local Next.js app where Edgar steers the narrowing from problems to a validated
idea. `SPEC.md` defines the system; `PLAN.md` tracks the build phases; `docs/research/`
holds the research behind both. Read SPEC.md before changing behavior.

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
| `evals/heldout/` | Edgar's held-out eval set, gitignored. Agents never read or edit it. |

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
npm --prefix web run dev                 # app on http://localhost:3000
npm --prefix web run lint
```

`SIG_DB` overrides the database path for both Python and the app.

## Rules

- Python owns all writes except steering decisions, which the app writes.
- Agents write to the database only through `python -m pipeline` commands, never raw SQL.
- Every derived row records the run that produced it; LLM-derived rows also record the
  prompt version and model.
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
