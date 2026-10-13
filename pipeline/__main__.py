"""Command line: uv run python -m pipeline <command>."""

import argparse
import sys

from pipeline import db, runs


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
    results = collect(conn, only=args.only, max_items=args.max_items)
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipeline")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply pending migrations").set_defaults(fn=cmd_migrate)
    s = sub.add_parser("smoke", help="write a test run and metric")
    s.add_argument("--value", type=float, default=1.0)
    s.add_argument("--note")
    s.set_defaults(fn=cmd_smoke)
    sub.add_parser("status", help="list recent runs").set_defaults(fn=cmd_status)
    c = sub.add_parser("collect", help="run stream collectors")
    c.add_argument("--only", nargs="+", metavar="NAME", help="run only these collectors")
    c.add_argument("--max-items", type=int, default=500, help="cap per collector per run")
    c.set_defaults(fn=cmd_collect)
    sub.add_parser("health", help="collector health").set_defaults(fn=cmd_health)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
