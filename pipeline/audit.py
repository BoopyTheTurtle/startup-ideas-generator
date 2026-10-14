"""Monthly blind audit (SPEC, "Blind audit").

`audit-draw` picks 20 items for the month: half already carry a working-set label (their
disagreement with Edgar's fresh blind label measures label drift) and half are random
extracted items (disagreement with the model measures true error). The two halves are
shuffled together, and the pool of each item sits in key.json, which the app never reads,
so Edgar labels all 20 blind. `audit-score` compares the labels afterwards.

Files, under evals/blind/<YYYY-MM>/:
    sample.json   {"month", "seed", "drawn_at", "items": [{"raw_item_id", "source"}]}  (the app reads this)
    key.json      {"pools": {"<raw_item_id>": "drift" | "model"}}                        (scoring only)
    labels.jsonl  Edgar's labels, the working-set record shape (the app appends)

The draw skips items in the held-out set, so a blind label never lands on one; it reads
that set's item ids only, never its labels.
"""

import json
import random
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pipeline import db, evals, runs

PER_POOL = 10


def blind_dir(month: str) -> Path:
    return evals.EVALS_DIR / "blind" / month


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _spread(by_source: dict[str, list[int]], n: int, rng: random.Random) -> list[int]:
    """Up to n ids, taken round-robin across sources so one source cannot fill the half."""
    pools = {s: rng.sample(ids, len(ids)) for s, ids in sorted(by_source.items())}
    out: list[int] = []
    while len(out) < n and any(pools.values()):
        for s in list(pools):
            if pools[s] and len(out) < n:
                out.append(pools[s].pop())
    return out


def draw(conn: sqlite3.Connection, month: str, seed: int | None = None) -> dict:
    path = blind_dir(month) / "sample.json"
    if path.exists():
        raise SystemExit(f"{path} exists: a month's sample is drawn once, so it cannot be cherry-picked")
    seed = seed if seed is not None else secrets.randbits(32)     # recorded below; not guessable
    rng = random.Random(seed)
    prompt_id, _ = evals.current_prompt(conn)
    if prompt_id is None:
        raise SystemExit("no extractions under the current prompt yet; run extract first")
    working = evals.load_labels(evals.labels_path("working"))
    excluded = set(evals.load_labels(evals.labels_path("heldout")))       # ids only
    readable = {r[0]: r[1] for r in conn.execute(
        "SELECT id, source FROM raw_item WHERE retain_text = 1 AND text_discarded_at IS NULL AND body != ''")}

    drift_pool: dict[str, list[int]] = {}
    for item_id, rec in working.items():
        if rec["label"] != "unsure" and item_id in readable and item_id not in excluded:
            drift_pool.setdefault(readable[item_id], []).append(item_id)
    drift = _spread(drift_pool, PER_POOL, rng)

    model_pool: dict[str, list[int]] = {}
    for r in conn.execute("SELECT x.raw_item_id AS id FROM extraction x WHERE x.prompt_id = ? AND x.model != 'rule'",
                          (prompt_id,)):
        i = r["id"]
        if i in readable and i not in working and i not in excluded:
            model_pool.setdefault(readable[i], []).append(i)
    model = _spread(model_pool, PER_POOL, rng)

    items = [(i, "drift") for i in drift] + [(i, "model") for i in model]
    rng.shuffle(items)
    sample = {"month": month, "seed": seed,
              "drawn_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "items": [{"raw_item_id": i, "source": readable[i]} for i, _ in items]}
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "key.json").write_text(
        json.dumps({"pools": {str(i): pool for i, pool in items}}, indent=1), encoding="utf-8")
    path.write_text(json.dumps(sample, indent=1), encoding="utf-8")
    return {"path": path, "drift": len(drift), "model": len(model)}


def score(conn: sqlite3.Connection, month: str) -> dict:
    d = blind_dir(month)
    if not (d / "sample.json").exists():
        raise SystemExit(f"no sample for {month}: run `audit-draw` first")
    labels = evals.load_labels(d / "labels.jsonl")
    pools = json.loads((d / "key.json").read_text(encoding="utf-8"))["pools"]
    working = evals.load_labels(evals.labels_path("working"))
    prompt_id, _ = evals.current_prompt(conn)
    drift = [0, 0]
    model = [0, 0]
    for item_id, rec in labels.items():
        if rec["label"] == "unsure":
            continue
        truth = rec["label"] == "pain"
        if pools.get(str(item_id)) == "drift" and item_id in working and working[item_id]["label"] != "unsure":
            drift[1] += 1
            drift[0] += (working[item_id]["label"] == "pain") == truth
        # Model error is scored on the fresh half only: the working-set items tuned the prompt.
        row = conn.execute("SELECT is_pain FROM extraction WHERE raw_item_id = ? AND prompt_id = ?",
                           (item_id, prompt_id)).fetchone() if prompt_id and pools.get(str(item_id)) == "model" else None
        if row is not None:
            model[1] += 1
            model[0] += bool(row["is_pain"]) == truth
    out = {"labeled": len(labels), "drift": drift, "model": model}
    with runs.run(conn, "audit", note=month) as run_id:
        if drift[1]:
            runs.log_metric(conn, run_id, "methodology", "audit_label_drift_agreement",
                            round(drift[0] / drift[1], 4), month)
        if model[1]:
            runs.log_metric(conn, run_id, "methodology", "audit_model_agreement",
                            round(model[0] / model[1], 4), month)
        if labels:
            runs.log_metric(conn, run_id, "methodology", "audit_labeled", len(labels), month)
    return out


def cmd_draw(args) -> int:
    conn = db.connect()
    db.migrate(conn)
    r = draw(conn, args.month or current_month(), args.seed)
    print(f"drew {r['drift']} labeled + {r['model']} fresh items: {r['path']}")
    print("Edgar labels them at /audit, blind.")
    return 0


def cmd_score(args) -> int:
    conn = db.connect()
    db.migrate(conn)
    month = args.month or current_month()
    r = score(conn, month)
    (dh, dn), (mh, mn) = r["drift"], r["model"]
    print(f"{month}: {r['labeled']} labeled")
    print(f"label drift   : agreement with the working labels {dh}/{dn}" if dn else "label drift   : n/a")
    print(f"model error   : agreement with the model {mh}/{mn}" if mn else "model error   : n/a")
    return 0


def register_cli(sub) -> None:
    p = sub.add_parser("audit-draw", help="draw this month's 20-item blind audit sample")
    p.add_argument("--month", help="YYYY-MM (default: this month)")
    p.add_argument("--seed", type=int)
    p.set_defaults(fn=cmd_draw)
    p = sub.add_parser("audit-score", help="score a finished blind audit")
    p.add_argument("--month")
    p.set_defaults(fn=cmd_score)
