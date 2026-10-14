"""Weekly reassessment (SPEC stage 8): measure, test the instruments, and brief the auditor.

`pipeline reassess` computes every registered metric and logs it, runs the mutation tests,
opens 'instrument' cards for metrics that missed their fault, opens 'revert' cards for
merged changes whose metric moved the wrong way, and writes a digest the auditor agent
reads. It decides nothing else: proposing improvement cards is the auditor's job, and
approving them is Edgar's.
"""

import json
import sqlite3
from pathlib import Path

from pipeline import cards, db, mutations, runs
from pipeline.metrics import REGISTRY, compute_all

DIGEST_DIR = db.ROOT / "data" / "reassess"
REGRESSION_ABS = 0.02            # a merged card's metric must move this far the wrong way ...
REGRESSION_REL = 0.10            # ... and by this share of its baseline, before a revert card opens
STAGE_KINDS = ("collect", "extract", "map", "themes", "curate")
STAGE_METRIC_CAP = 60


def _latest_run(conn, kind: str, before: int | None = None) -> int | None:
    row = conn.execute("SELECT id FROM run WHERE kind = ? AND status = 'ok'"
                       + (" AND id < ?" if before else "") + " ORDER BY id DESC LIMIT 1",
                       (kind, before) if before else (kind,)).fetchone()
    return row[0] if row else None


def log_metrics(conn: sqlite3.Connection, run_id: int, values: dict) -> None:
    with conn:
        conn.executemany(
            "INSERT INTO metric (run_id, layer, name, subject, value) VALUES (?, ?, ?, ?, ?)",
            [(run_id, layer, name, subject, v) for (layer, name, subject), v in values.items()])


# --- Instrument and regression cards -------------------------------------------------------

def open_instrument_cards(conn: sqlite3.Connection, results: list[mutations.Result]) -> list[int]:
    """One card per metric that missed its fault. Evaluation code is what needs fixing."""
    opened = []
    for r in results:
        if r.caught:
            continue
        subject = r.expect.subject
        try:
            opened.append(cards.add_card(conn, {
                "kind": "instrument", "touches": "eval", "size": "S", "value": 4,
                "title": f"Metric {r.expect.metric} missed the fault '{r.name}'",
                "observation": f"Mutation '{r.name}' should move {r.expect.metric}"
                               f"{' [' + subject + ']' if subject else ''} {r.expect.direction}, "
                               f"but it went from {r.baseline:.6g} to {r.mutated:.6g}.",
                "evidence": [{"metric": r.expect.metric, "subject": subject, "value": r.mutated,
                              "run_id": 0}],
                "hypothesis": "The metric does not read the data the fault changes, or the fault "
                              "does not reach it.",
                "change": f"Fix {r.expect.metric} in pipeline/metrics.py (or the mutation in "
                          "pipeline/mutations.py) so the fault registers; keep the other mutations passing.",
                "expected_effect": f"Mutation '{r.name}' is caught next week.",
                "expected_metric": "methodology.mutations_missed", "expected_direction": "down",
                "risk": "Low: evaluation code only, covered by tests/test_mutations.py.",
                "dedupe_key": f"instrument:{r.expect.metric}:{subject}:{r.name}",
            }, proposed_by="system"))
        except cards.CardError as e:
            print(f"reassess: no instrument card for {r.name}/{r.expect.metric}: {e}")
    return opened


def _regressed(baseline: float, now: float, direction: str) -> bool:
    worse = (now - baseline) if direction == "down" else (baseline - now)   # positive = wrong way
    return worse > max(REGRESSION_ABS, REGRESSION_REL * abs(baseline))


def open_revert_cards(conn: sqlite3.Connection) -> list[int]:
    """A merged card whose expected metric later moved the wrong way gets a revert card."""
    opened = []
    for c in conn.execute("SELECT * FROM improvement_card WHERE status = 'merged'"
                          " AND baseline_json IS NOT NULL AND kind != 'revert'"):
        base = json.loads(c["baseline_json"])
        layer, name = base["metric"].split(".", 1)
        row = conn.execute(
            "SELECT value, run_id FROM metric WHERE layer = ? AND name = ? AND subject = ?"
            " AND recorded_at > ? ORDER BY id DESC LIMIT 1",
            (layer, name, base["subject"], c["merged_at"])).fetchone()
        if row is None or not _regressed(base["value"], row["value"], base["direction"]):
            continue
        try:
            opened.append(cards.add_card(conn, {
                "kind": "revert", "touches": c["touches"], "size": "S", "value": 5,
                "title": f"Revert card {c['id']}: {c['title']}"[:120],
                "observation": f"{base['metric']} was {base['value']:.4g} when card {c['id']} merged "
                               f"and is {row['value']:.4g} now; the card expected it to go {base['direction']}.",
                "evidence": [{"metric": base["metric"], "subject": base["subject"],
                              "value": row["value"], "run_id": row["run_id"]}],
                "hypothesis": f"Card {c['id']} caused the regression, or did not help.",
                "change": f"git revert -m 1 {c['merged_sha']} on a card branch, then verify.",
                "expected_effect": f"{base['metric']} returns to about {base['value']:.4g}.",
                "expected_metric": base["metric"], "expected_subject": base["subject"],
                "expected_direction": base["direction"], "risk": "Low: undoes a reviewed change.",
                "dedupe_key": f"revert:{c['id']}",
            }, proposed_by="system", reverts_card_id=c["id"]))
        except cards.CardError as e:
            print(f"reassess: no revert card for {c['id']}: {e}")
    return opened


# --- The digest ----------------------------------------------------------------------------

def _prior_values(conn, run_id: int) -> dict:
    prev = _latest_run(conn, "reassess", before=run_id)
    if prev is None:
        return {}
    keys = {(m.layer, m.name) for m in REGISTRY}
    return {(r["layer"], r["name"], r["subject"]): r["value"] for r in conn.execute(
        "SELECT layer, name, subject, value FROM metric WHERE run_id = ?", (prev,))
        if (r["layer"], r["name"]) in keys}


def build_digest(conn: sqlite3.Connection, run_id: int, current: dict, results: list[mutations.Result],
                 opened: dict[str, list[int]]) -> dict:
    prior = _prior_values(conn, run_id)
    metrics = [{"metric": f"{layer}.{name}", "subject": subject, "value": round(v, 4),
                "previous": round(prior[(layer, name, subject)], 4) if (layer, name, subject) in prior else None}
               for (layer, name, subject), v in sorted(current.items())]
    stage = {}
    for kind in STAGE_KINDS:
        rid = _latest_run(conn, kind)
        if rid is None:
            continue
        rows = conn.execute("SELECT layer, name, subject, value FROM metric WHERE run_id = ?"
                            " ORDER BY layer, name, subject LIMIT ?", (rid, STAGE_METRIC_CAP)).fetchall()
        stage[kind] = {"run_id": rid, "metrics": [
            {"metric": f"{r['layer']}.{r['name']}", "subject": r["subject"], "value": r["value"]} for r in rows]}
    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "run_id": run_id,
        "data": {
            "raw_items": one("SELECT COUNT(*) FROM raw_item"),
            "extracted_items": one("SELECT COUNT(DISTINCT raw_item_id) FROM extraction"),
            "live_problems": one("SELECT COUNT(*) FROM problem WHERE status != 'merged'"),
            "collect_runs": one("SELECT COUNT(*) FROM run WHERE kind = 'collect' AND status = 'ok'"),
            "weeks_of_snapshots": one("SELECT COUNT(DISTINCT run_id) FROM snapshot"),
            "note": "Trend and false-alarm metrics need 8 weekly snapshots (SPEC stage 3). Weigh "
                    "a single reading lightly while data is young.",
        },
        "metrics": metrics,
        "stage_metrics": stage,
        "mutations": {"run": len(results), "missed": [
            {"mutation": r.name, "metric": r.expect.metric, "subject": r.expect.subject, "detail": r.detail}
            for r in results if not r.caught]},
        "opened_by_system": opened,
        "cards": [dict(r) for r in conn.execute(
            "SELECT id, status, kind, touches, title, expected_metric, expected_direction, week"
            " FROM improvement_card WHERE status IN ('proposed','approved','building','built','ready')"
            " ORDER BY id")],
        "recent_decisions": [dict(r) for r in conn.execute(
            "SELECT id, status, title, dedupe_key, decision_reason, decision_note FROM improvement_card"
            " WHERE status IN ('rejected','merged','reverted','abandoned') ORDER BY updated_at DESC LIMIT 15")],
    }


def digest_path(run_id: int) -> Path:
    return DIGEST_DIR / f"digest-{run_id}.json"


def reassess(conn: sqlite3.Connection, with_mutations: bool = True) -> dict:
    with runs.run(conn, "reassess") as run_id:
        current = compute_all(conn)
        log_metrics(conn, run_id, current)
        results: list[mutations.Result] = []
        opened: dict[str, list[int]] = {"instrument": [], "revert": []}
        if with_mutations:
            results = mutations.run_all(conn)
            mutations.record(conn, run_id, results)
            opened["instrument"] = open_instrument_cards(conn, results)
        opened["revert"] = open_revert_cards(conn)
        digest = build_digest(conn, run_id, current, results, opened)
        DIGEST_DIR.mkdir(parents=True, exist_ok=True)
        digest_path(run_id).write_text(json.dumps(digest, indent=1, default=str), encoding="utf-8")
    return {"run_id": run_id, "metrics": len(current), "mutations": len(results),
            "missed": sum(not r.caught for r in results), "opened": opened,
            "digest": str(digest_path(run_id))}


# --- CLI -----------------------------------------------------------------------------------

def cmd_reassess(args) -> int:
    conn = db.connect()
    db.migrate(conn)
    r = reassess(conn, with_mutations=not args.no_mutations)
    print(f"reassess run {r['run_id']}: {r['metrics']} metric values, {r['mutations']} mutation checks, "
          f"{r['missed']} missed")
    for kind, ids in r["opened"].items():
        if ids:
            print(f"  opened {kind} cards: {ids}")
    print(f"digest: {r['digest']}")
    return 0


def cmd_digest(args) -> int:
    run_id = args.run or _latest_run(db.connect(), "reassess")
    if run_id is None or not digest_path(run_id).exists():
        print("no digest yet: run `pipeline reassess`")
        return 1
    print(digest_path(run_id).read_text(encoding="utf-8"))
    return 0


def register_cli(sub) -> None:
    p = sub.add_parser("reassess", help="weekly: metrics, mutation tests, revert and instrument cards, digest")
    p.add_argument("--no-mutations", action="store_true")
    p.set_defaults(fn=cmd_reassess)
    p = sub.add_parser("digest", help="print the latest reassess digest (read-only)")
    p.add_argument("--run", type=int)
    p.set_defaults(fn=cmd_digest)
