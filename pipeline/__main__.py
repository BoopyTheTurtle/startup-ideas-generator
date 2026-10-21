"""Command line: uv run python -m pipeline <command>."""

import argparse
import importlib
import sys

from pipeline import db, runs
from pipeline.lock import LockTimeout, single_instance


def cmd_migrate(args) -> int:
    conn = db.connect()
    applied = db.migrate(conn)
    print(f"{db.db_path()}: applied {applied or 'nothing'}")
    return 0


def cmd_smoke(args) -> int:
    """Write a run and a metric, proving the layers connect."""
    conn = db.connect()
    db.migrate(conn)
    with runs.run(conn, "smoke", note=args.note) as run_id:
        runs.log_metric(conn, run_id, "sources", "smoke_value", args.value)
    print(f"run {run_id} ok")
    return 0


def cmd_status(args) -> int:
    conn = db.connect()
    db.migrate(conn)
    rows = conn.execute(
        "SELECT id, kind, status, started_at FROM run ORDER BY id DESC LIMIT 10"
    ).fetchall()
    for r in rows:
        print(f"{r['id']:>4}  {r['kind']:<10} {r['status']:<8} {r['started_at']}")
    return 0


def cmd_collect(args) -> int:
    from pipeline.collect import collect
    conn = db.connect()
    db.migrate(conn)
    results = collect(conn, only=args.only, skip=args.skip, max_items=args.max_items)
    for r in results:
        line = f"{r.source:<16} {r.status:<13} fetched {r.fetched:>5}  new {r.new:>5}"
        print(line + (f"  {r.error.splitlines()[0]}" if r.error else ""))
    return 0 if all(r.status in ("ok", "partial") for r in results) else 1


def cmd_health(args) -> int:
    conn = db.connect()
    db.migrate(conn)
    rows = conn.execute("SELECT * FROM collector_health ORDER BY source").fetchall()
    for r in rows:
        print(f"{r['source']:<16} {r['last_status'] or '-':<13} "
              f"last ok {r['last_success_at'] or 'never':<25} "
              f"fails {r['consecutive_failures']}  items {r['items_last_run']}")
    return 0


# Modules exposing register_cli(subparsers). Add a module here once it exists.
PLUGINS: list[str] = ["extract", "evals", "embed", "mapping", "curate", "themes", "cards", "reassess", "audit"]

# Commands that only read run without the pipeline lock; every other command writes and
# waits for it, so two writers never overlap across processes.
READ_ONLY = {"status", "health", "problems", "eval-status", "themes-list", "cards", "card-show", "digest"}
LOCK_TIMEOUT_EXIT = 75  # EX_TEMPFAIL


def _sweep_stale_runs() -> None:
    """Fail run rows that a killed process left at 'running' (we hold the lock)."""
    conn = db.connect()
    try:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'run'").fetchone():
            n = runs.sweep_stale(conn)
            if n:
                print(f"marked {n} run(s) left 'running' by a killed process as failed", file=sys.stderr)
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipeline")
    p.add_argument("--lock-wait", type=float, default=60, metavar="MINUTES",
                   help="how long a writing command waits for another to finish (default 60)")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply pending migrations").set_defaults(fn=cmd_migrate)
    s = sub.add_parser("smoke", help="write a test run and metric")
    s.add_argument("--value", type=float, default=1.0)
    s.add_argument("--note")
    s.set_defaults(fn=cmd_smoke)
    sub.add_parser("status", help="list recent runs").set_defaults(fn=cmd_status)
    c = sub.add_parser("collect", help="run stream collectors")
    c.add_argument("--only", nargs="+", metavar="NAME", help="run only these collectors")
    c.add_argument("--skip", nargs="+", metavar="NAME", default=[],
                   help="leave out these collectors (e.g. forums, which polls daily)")
    c.add_argument("--max-items", type=int, default=500, help="cap per collector per run")
    c.set_defaults(fn=cmd_collect)
    sub.add_parser("health", help="collector health").set_defaults(fn=cmd_health)
    # Stage modules add their own commands, so parallel work never edits this file.
    for module in PLUGINS:
        importlib.import_module(f"pipeline.{module}").register_cli(sub)
    args = p.parse_args(argv)
    if args.command in READ_ONLY:
        return args.fn(args)
    try:
        with single_instance(timeout_s=args.lock_wait * 60):
            _sweep_stale_runs()
            return args.fn(args)
    except LockTimeout as e:
        print(f"pipeline {args.command}: not run: {e}", file=sys.stderr)
        return LOCK_TIMEOUT_EXIT


if __name__ == "__main__":
    sys.exit(main())
