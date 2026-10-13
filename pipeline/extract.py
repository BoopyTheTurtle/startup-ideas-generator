"""Stage 2: turn raw items into pain records with verbatim quotes.

Each item gets one `extraction` row per prompt version (its pain verdict) and 0-3 `pain`
rows. Every pain's quote is checked against the item's plain text; a quote that is not
in the text is dropped as ungrounded (metric quote_miss). Items from sources that keep no
text (retain_text = 0) store a paraphrase instead of the quote, and `scrub` blanks their
body once extracted.
"""

import hashlib
import json
import sqlite3
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline import db, runs
from pipeline.llm import DEFAULT_MODEL, ClaudeCode, LLMError, Runtime
from pipeline.text import find_quote, plain_text

PROMPT_FILE = Path(__file__).with_name("prompts") / "extract.md"
MIN_CHARS = 40          # shorter items cannot describe a problem; filtered by rule
MAX_CHARS = 4000        # longer bodies (CMA case files) are truncated for the model
SCRUB_AFTER_HOURS = 48  # no-retain items are blanked by then even if extraction failed

PROBLEM_SCHEMA = {
    "type": "object",
    "properties": {
        "job": {"type": "string"},
        "problem": {"type": "string"},
        "who": {"type": "string"},
        "workaround": {"type": ["string", "null"]},
        "cost_cue": {"type": ["string", "null"]},
        "intensity": {"type": "integer", "minimum": 1, "maximum": 5},
        "evidence_level": {"type": "string", "enum": ["E1", "E2", "E3"]},
        "quote": {"type": "string"},
        "paraphrase": {"type": "string"},
    },
    "required": ["job", "problem", "who", "workaround", "cost_cue", "intensity",
                 "evidence_level", "quote", "paraphrase"],
}
SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "is_pain": {"type": "boolean"},
                    "problems": {"type": "array", "maxItems": 3, "items": PROBLEM_SCHEMA},
                },
                "required": ["id", "is_pain", "problems"],
            },
        }
    },
    "required": ["items"],
}


def prompt_row(conn: sqlite3.Connection) -> tuple[int, str, str]:
    """Register the current prompt (text + schema) and return (id, version, text)."""
    text = PROMPT_FILE.read_text(encoding="utf-8")
    version = hashlib.sha256((text + json.dumps(SCHEMA, sort_keys=True)).encode()).hexdigest()[:12]
    with conn:
        conn.execute("INSERT OR IGNORE INTO prompt (name, version, text) VALUES ('extract', ?, ?)",
                     (version, text))
    pid = conn.execute("SELECT id FROM prompt WHERE name = 'extract' AND version = ?",
                       (version,)).fetchone()[0]
    return pid, version, text


def _candidates(conn, prompt_id: int, limit: int, sources: list[str] | None) -> list[sqlite3.Row]:
    """Unextracted items: no-retain ones first (they must be processed before scrubbing),
    then round-robin across sources, newest first within each."""
    q = ("SELECT r.id, r.source, r.title, r.body, r.retain_text FROM raw_item r"
         " WHERE r.text_discarded_at IS NULL AND NOT EXISTS ("
         "  SELECT 1 FROM extraction e WHERE e.raw_item_id = r.id AND e.prompt_id = ?)")
    args: list = [prompt_id]
    if sources:
        q += f" AND r.source IN ({','.join('?' * len(sources))})"
        args += sources
    q += " ORDER BY r.retain_text ASC, COALESCE(r.created_at, r.fetched_at) DESC"
    rows = conn.execute(q, args).fetchall()
    urgent = [r for r in rows if not r["retain_text"]]
    by_source: dict[str, list] = defaultdict(list)
    for r in rows:
        if r["retain_text"]:
            by_source[r["source"]].append(r)
    mixed, queues = [], list(by_source.values())
    while queues and len(urgent) + len(mixed) < limit:
        queues = [q for q in queues if q]
        for q in queues:
            if q:
                mixed.append(q.pop(0))
    return (urgent + mixed)[:limit]


def _validate(problem: dict, text: str, retain: bool) -> tuple[dict | None, str | None]:
    """Clean one model problem; return (row fields, reason dropped)."""
    for k in ("job", "problem", "who", "quote", "paraphrase"):
        if not isinstance(problem.get(k), str) or not problem[k].strip():
            return None, f"missing {k}"
    if problem.get("evidence_level") not in ("E1", "E2", "E3"):
        return None, "bad evidence_level"
    try:
        intensity = int(problem["intensity"])
    except (KeyError, TypeError, ValueError):
        return None, "bad intensity"
    if not 1 <= intensity <= 5:
        return None, "bad intensity"
    span = find_quote(text, problem["quote"])
    if span is None:
        return None, "quote_miss"
    opt = lambda k: (problem.get(k) or "").strip() or None  # noqa: E731
    row = {"job": problem["job"].strip(), "problem": problem["problem"].strip(),
           "who": problem["who"].strip(), "workaround": opt("workaround"),
           "cost_cue": opt("cost_cue"), "intensity": intensity,
           "evidence_level": problem["evidence_level"]}
    if retain:
        row.update(quote=text[span[0]:span[1]], quote_kind="verbatim",
                   quote_start=span[0], quote_end=span[1])
    else:
        # The source forbids reproduction: keep the grounded meaning, not the words.
        row.update(quote=problem["paraphrase"].strip(), quote_kind="paraphrase",
                   quote_start=None, quote_end=None)
    return row, None


def _store(conn, run_id, prompt_id, model, item, verdict: bool, problems: list[dict],
           note: str | None) -> None:
    cur = conn.execute(
        "INSERT OR IGNORE INTO extraction (raw_item_id, run_id, prompt_id, model, is_pain, note)"
        " VALUES (?, ?, ?, ?, ?, ?)", (item["id"], run_id, prompt_id, model, int(verdict), note))
    if not cur.rowcount:
        return  # another run got there first
    for idx, p in enumerate(problems):
        conn.execute(
            "INSERT INTO pain (extraction_id, idx, job, problem, who, workaround, cost_cue,"
            " intensity, evidence_level, quote, quote_kind, quote_start, quote_end)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cur.lastrowid, idx, p["job"], p["problem"], p["who"], p["workaround"],
             p["cost_cue"], p["intensity"], p["evidence_level"], p["quote"], p["quote_kind"],
             p["quote_start"], p["quote_end"]))


def extract(conn: sqlite3.Connection, runtime: Runtime | None = None, max_items: int = 400,
            batch_size: int = 20, workers: int = 3, sources: list[str] | None = None,
            model: str = DEFAULT_MODEL) -> dict:
    prompt_id, version, system = prompt_row(conn)
    items = _candidates(conn, prompt_id, max_items, sources)
    stats = defaultdict(float)
    with runs.run(conn, "extract", note=f"prompt {version}, {len(items)} items") as run_id:
        texts = {r["id"]: plain_text(r["body"]) for r in items}
        llm_items = []
        with conn:
            for r in items:
                if len(texts[r["id"]]) < MIN_CHARS:
                    _store(conn, run_id, prompt_id, "rule", r, False, [], f"under {MIN_CHARS} chars")
                    stats["rule_filtered"] += 1
                else:
                    llm_items.append(r)
        batches = [llm_items[i:i + batch_size] for i in range(0, len(llm_items), batch_size)]
        runtime = runtime or ClaudeCode()

        def call(batch):
            payload = [{"id": r["id"], "source": r["source"], "title": r["title"] or "",
                        "text": texts[r["id"]][:MAX_CHARS]} for r in batch]
            t0 = time.monotonic()
            res = runtime.run(system, json.dumps(payload, ensure_ascii=False), SCHEMA, model)
            return batch, res, time.monotonic() - t0

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(call, b) for b in batches]
            for fut in as_completed(futures):
                try:
                    batch, res, secs = fut.result()
                except LLMError as e:
                    stats["llm_failures"] += 1
                    print(f"extract: batch failed: {e}")
                    continue
                stats["llm_calls"] += 1
                stats["llm_cost_usd"] += res.cost_usd
                stats["llm_seconds"] += secs
                answers = {a.get("id"): a for a in res.data.get("items", [])
                           if isinstance(a, dict)}
                with conn:  # main thread only: sqlite connections are not shared
                    for r in batch:
                        a = answers.get(r["id"])
                        if a is None:
                            stats["items_missing"] += 1   # retried next run
                            continue
                        rows, misses = [], []
                        for p in (a.get("problems") or [])[:3]:
                            row, why = _validate(p, texts[r["id"]], bool(r["retain_text"]))
                            if row:
                                rows.append(row)
                            else:
                                misses.append(why)
                        stats["problems_dropped"] += len(misses)
                        stats["quote_miss"] += misses.count("quote_miss")
                        stats["problems_kept"] += len(rows)
                        verdict = bool(a.get("is_pain")) and bool(rows or misses)
                        stats["items_pain"] += int(verdict)
                        stats["items_extracted"] += 1
                        _store(conn, run_id, prompt_id, res.model, r, verdict, rows,
                               "; ".join(misses) or None)
        for name, value in stats.items():
            runs.log_metric(conn, run_id, "extraction", name, round(value, 4), version)
        kept, dropped = stats["problems_kept"], stats["problems_dropped"]
        if kept + dropped:
            runs.log_metric(conn, run_id, "extraction", "quote_miss_rate",
                            round(stats["quote_miss"] / (kept + dropped), 4), version)
    stats["prompt_version"] = version  # type: ignore[assignment]
    return dict(stats)


def scrub(conn: sqlite3.Connection) -> int:
    """Blank the body of no-retain items once extracted, or after SCRUB_AFTER_HOURS anyway."""
    with conn:
        n = conn.execute(
            "UPDATE raw_item SET body = '', text_discarded_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')"
            " WHERE retain_text = 0 AND text_discarded_at IS NULL AND ("
            "  EXISTS (SELECT 1 FROM extraction e WHERE e.raw_item_id = raw_item.id)"
            "  OR julianday('now') - julianday(fetched_at) > ? / 24.0)",
            (SCRUB_AFTER_HOURS,)).rowcount
    return n


def cmd_extract(args) -> int:
    conn = db.connect()
    db.migrate(conn)
    stats = extract(conn, max_items=args.max_items, batch_size=args.batch_size,
                    workers=args.workers, sources=args.source, model=args.model)
    print(json.dumps(stats, indent=1))
    scrubbed = scrub(conn)
    if scrubbed:
        print(f"scrubbed text of {scrubbed} no-retain items")
    return 0 if not stats.get("llm_failures") else 1


def cmd_scrub(args) -> int:
    conn = db.connect()
    db.migrate(conn)
    print(f"scrubbed {scrub(conn)} items")
    return 0


def register_cli(sub) -> None:
    p = sub.add_parser("extract", help="extract pains from unextracted items (stage 2)")
    p.add_argument("--max-items", type=int, default=400)
    p.add_argument("--batch-size", type=int, default=20)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--source", nargs="+", help="only these sources")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.set_defaults(fn=cmd_extract)
    sub.add_parser("scrub", help="blank text of no-retain items once extracted").set_defaults(
        fn=cmd_scrub)
