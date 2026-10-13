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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipeline")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply pending migrations").set_defaults(fn=cmd_migrate)
    s = sub.add_parser("smoke", help="write a test run and metric")
    s.add_argument("--value", type=float, default=1.0)
    s.add_argument("--note")
    s.set_defaults(fn=cmd_smoke)
    sub.add_parser("status", help="list recent runs").set_defaults(fn=cmd_status)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
