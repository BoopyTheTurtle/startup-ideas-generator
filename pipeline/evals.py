"""Extraction eval: compare extraction.is_pain against Edgar's hand labels (SPEC stage 8).

Labels are JSON lines that the app's /label page appends, one file per set:

    evals/working/labels.jsonl   the working set; agents may read it and run `eval`
    evals/heldout/labels.jsonl   the held-out set; detects overfitting

AGENTS: never run `eval --set heldout`, and never open, read, grep, or list anything in
evals/heldout/. Only Edgar runs the held-out eval. Even its aggregate numbers, watched
while building a change, turn the held-out set into a second working set and defeat its
purpose. `eval-status` is safe: it prints label counts, never labels or items.

`eval --set heldout` prints its aggregates and appends them to evals/heldout/results.jsonl
(gitignored). It writes no run or metric rows: the database is shared with agents.

Each line: {"raw_item_id", "source", "source_id", "label": "pain"|"not_pain"|"unsure",
"note", "labeled_at"}. Blank lines are skipped; a later line for the same raw_item_id
overrides an earlier one. "unsure" labels count as labeled but never enter the metrics.
"""

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pipeline import db, embed, runs
from pipeline.text import find_quote, plain_text

EVALS_DIR = db.ROOT / "evals"
SETS = ("working", "heldout")
LABELS = ("pain", "not_pain", "unsure")
PROMPT_NAME = "extract"


def labels_path(set_name: str) -> Path:
    if set_name not in SETS:
        raise ValueError(f"unknown eval set {set_name!r}")
    return EVALS_DIR / set_name / "labels.jsonl"


def load_labels(path: Path) -> dict[int, dict]:
    """raw_item_id -> label record. Later lines win; blank lines are skipped."""
    out: dict[int, dict] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                item_id = int(rec["raw_item_id"])
                label = rec["label"]
            except (ValueError, KeyError, TypeError) as e:
                raise ValueError(f"{path.name} line {n}: {e}") from None
            if label not in LABELS:
                raise ValueError(f"{path.name} line {n}: unknown label {label!r}")
            out[item_id] = rec
    return out


def current_prompt(conn: sqlite3.Connection) -> tuple[int | None, str]:
    """(prompt id, version) of the extract prompt as pipeline/prompts/extract.md stands now.

    The id is None until an extraction has run under this version. The same definition
    picks a raw item's active pains (pipeline.embed.ACTIVE_PAIN_SQL).
    """
    version = embed.current_extract_version()
    row = conn.execute("SELECT id FROM prompt WHERE name = ? AND version = ?",
                       (PROMPT_NAME, version)).fetchone()
    return (row["id"] if row else None), version


def find_prompt(conn: sqlite3.Connection, version: str | None) -> tuple[int, str] | None:
    """The named prompt version, or the current one when version is None."""
    if version is None:
        pid, current = current_prompt(conn)
        return (pid, current) if pid is not None else None
    row = conn.execute("SELECT id, version FROM prompt WHERE name = ? AND version = ?",
                       (PROMPT_NAME, version)).fetchone()
    return (row["id"], row["version"]) if row else None


@dataclass
class Confusion:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def add(self, truth: bool, predicted: bool) -> None:
        if truth and predicted:
            self.tp += 1
        elif predicted:
            self.fp += 1
        elif truth:
            self.fn += 1
        else:
            self.tn += 1

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def precision(self) -> float | None:
        d = self.tp + self.fp
        return self.tp / d if d else None

    @property
    def recall(self) -> float | None:
        d = self.tp + self.fn
        return self.tp / d if d else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or p + r == 0:
            return None
        return 2 * p * r / (p + r)

    @property
    def accuracy(self) -> float | None:
        return (self.tp + self.tn) / self.n if self.n else None


@dataclass
class EvalResult:
    set_name: str
    prompt_version: str
    overall: Confusion = field(default_factory=Confusion)
    by_source: dict[str, Confusion] = field(default_factory=dict)
    unsure: int = 0
    missing: int = 0                      # labeled (pain/not_pain) but no extraction row
    quotes_checked: int = 0               # verbatim pain rows with text to check against
    quotes_found: int = 0
    errors: list[tuple[int, str, str, str]] = field(default_factory=list)  # id, source, label, title

    @property
    def quote_share(self) -> float | None:
        return self.quotes_found / self.quotes_checked if self.quotes_checked else None


def evaluate(conn: sqlite3.Connection, labels: dict[int, dict], prompt_id: int,
             set_name: str, prompt_version: str) -> EvalResult:
    res = EvalResult(set_name, prompt_version)
    for item_id, rec in sorted(labels.items()):
        if rec["label"] == "unsure":
            res.unsure += 1
            continue
        row = conn.execute(
            "SELECT r.source, r.title, r.body, r.text_discarded_at, e.id AS extraction_id, e.is_pain"
            "  FROM raw_item r LEFT JOIN extraction e"
            "    ON e.raw_item_id = r.id AND e.prompt_id = ?"
            " WHERE r.id = ?", (prompt_id, item_id)).fetchone()
        if row is None or row["extraction_id"] is None:
            res.missing += 1
            continue
        truth, predicted = rec["label"] == "pain", bool(row["is_pain"])
        res.overall.add(truth, predicted)
        res.by_source.setdefault(row["source"], Confusion()).add(truth, predicted)
        if truth != predicted:
            res.errors.append((item_id, row["source"], rec["label"], row["title"] or ""))
        quotes = conn.execute("SELECT quote FROM pain WHERE extraction_id = ? AND quote_kind = 'verbatim'",
                              (row["extraction_id"],)).fetchall()
        if quotes and row["text_discarded_at"] is None and row["body"]:
            text = plain_text(row["body"])
            for q in quotes:
                res.quotes_checked += 1
                res.quotes_found += find_quote(text, q["quote"]) is not None
    return res


def _fmt(x: float | None) -> str:
    return "  -  " if x is None else f"{x:.3f}"


def _log(conn, run_id: int, res: EvalResult) -> None:
    """Working-set metrics, overall and per source. Never called for the held-out set."""
    def log(c: Confusion, subject: str) -> None:
        runs.log_metric(conn, run_id, "extraction", "eval_n", c.n, subject)
        for name in ("precision", "recall", "f1", "accuracy"):
            v = getattr(c, name)
            if v is not None:
                runs.log_metric(conn, run_id, "extraction", f"eval_{name}", v, subject)

    subject = f"{res.set_name}:{res.prompt_version}"
    log(res.overall, subject)
    runs.log_metric(conn, run_id, "extraction", "eval_missing", res.missing, subject)
    if res.quote_share is not None:
        runs.log_metric(conn, run_id, "extraction", "eval_quote_verbatim_found",
                        res.quote_share, subject)
    for source, c in res.by_source.items():
        log(c, f"{subject}:{source}")


def _record_heldout(res: EvalResult) -> None:
    """Append the held-out aggregates to evals/heldout/results.jsonl (append only)."""
    o = res.overall
    rec = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "prompt_version": res.prompt_version, **asdict(o),
           **{k: getattr(o, k) for k in ("precision", "recall", "f1", "accuracy")},
           "unsure": res.unsure, "missing": res.missing, "quote_share": res.quote_share}
    path = EVALS_DIR / "heldout" / "results.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def cmd_eval(args) -> int:
    conn = db.connect()
    db.migrate(conn)
    prompt = find_prompt(conn, args.prompt_version)
    if prompt is None:
        what = args.prompt_version or f"{current_prompt(conn)[1]} (current)"
        print(f"no extractions under '{PROMPT_NAME}' prompt {what}; run extract first,"
              " or pass --prompt-version")
        return 1
    prompt_id, version = prompt
    labels = load_labels(labels_path(args.set))
    if not labels:
        print(f"no labels in the {args.set} set yet; label items at /label")
        return 1
    res = evaluate(conn, labels, prompt_id, args.set, version)
    heldout = args.set == "heldout"
    if heldout:
        # Nothing reaches the shared database, so agents never see held-out numbers.
        _record_heldout(res)
        header = f"{args.set} set, prompt {version}, not logged (see heldout/results.jsonl)"
    else:
        with runs.run(conn, "eval", note=f"{args.set} set, prompt {version}") as run_id:
            _log(conn, run_id, res)
        header = f"{args.set} set, prompt {version}, run {run_id}"

    o = res.overall
    print(header)
    print(f"n {o.n}  (unsure {res.unsure}, no extraction {res.missing})")
    print(f"precision {_fmt(o.precision)}  recall {_fmt(o.recall)}  "
          f"f1 {_fmt(o.f1)}  accuracy {_fmt(o.accuracy)}")
    print(f"verbatim quotes found in text: {_fmt(res.quote_share)} of {res.quotes_checked}")
    if heldout:
        return 0  # aggregates only, so no breakdown narrows down which items it holds
    print()
    print(f"{'source':<16} {'n':>4} {'tp':>4} {'fp':>4} {'fn':>4} {'tn':>4}  "
          f"{'prec':>5}  {'rec':>5}  {'f1':>5}  {'acc':>5}")
    for source, c in sorted(res.by_source.items()):
        print(f"{source:<16} {c.n:>4} {c.tp:>4} {c.fp:>4} {c.fn:>4} {c.tn:>4}  "
              f"{_fmt(c.precision)}  {_fmt(c.recall)}  {_fmt(c.f1)}  {_fmt(c.accuracy)}")
    if res.errors:
        print("\ndisagreements (raw_item_id, source, label):")
        for item_id, source, label, title in res.errors:
            print(f"  {item_id:>6}  {source:<16} {label:<9} {title[:60]}")
    return 0


def cmd_eval_status(args) -> int:
    conn = db.connect()
    db.migrate(conn)
    prompt_id, version = current_prompt(conn)
    print(f"current {PROMPT_NAME} prompt: {version}"
          + ("" if prompt_id is not None else " (no extractions yet)"))
    for set_name in SETS:
        labels = load_labels(labels_path(set_name))
        if set_name != "working":
            # Agents run this command, so the held-out set shows only its size: label mix
            # or per-source counts would leak what it contains.
            print(f"\n{set_name}: {len(labels)} labeled")
            continue
        counts = {k: 0 for k in LABELS}
        per_source: dict[str, int] = {}
        missing = 0
        for item_id, rec in labels.items():
            counts[rec["label"]] += 1
            per_source[rec.get("source") or "?"] = per_source.get(rec.get("source") or "?", 0) + 1
            if rec["label"] != "unsure" and (prompt_id is None or conn.execute(
                    "SELECT 1 FROM extraction WHERE raw_item_id = ? AND prompt_id = ?",
                    (item_id, prompt_id)).fetchone() is None):
                missing += 1
        print(f"\n{set_name}: {len(labels)} labeled  (pain {counts['pain']}, "
              f"not_pain {counts['not_pain']}, unsure {counts['unsure']}); "
              f"{missing} lack an extraction for the current prompt")
        for source, n in sorted(per_source.items()):
            print(f"  {source:<16} {n:>4}")
    return 0


def register_cli(sub) -> None:
    p = sub.add_parser("eval", help="score extraction against hand labels (agents: working set only)")
    p.add_argument("--set", choices=SETS, default="working")
    p.add_argument("--prompt-version", help="prompt version hash (default: the current prompt file's)")
    p.set_defaults(fn=cmd_eval)
    sub.add_parser("eval-status", help="label counts per set and source").set_defaults(
        fn=cmd_eval_status)
