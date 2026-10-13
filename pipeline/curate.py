"""Cluster curator: names new problems in job + outcome form and writes a statement.

Mapping titles a new problem with one member's sentence. The curator reads up to
MAX_MEMBERS member pains and writes a solution-free title and a short statement. It also
says whether the members really share one problem; when they don't, the problem gets a
note in its statement for Edgar to split or archive. Titles Edgar sets (title_source
'human') are never touched.
"""

import hashlib
import json
import sqlite3

from pipeline import db, runs
from pipeline.llm import ClaudeCode, LLMError, Runtime

MODEL = "claude-sonnet-5-5"
MAX_MEMBERS = 8

SYSTEM = """You name problems for a researcher looking for problems worth solving.

Each input problem comes with member reports: what a person was trying to do, the obstacle,
who they are, and a quote (any language). For each problem, write:
- title: the job and the outcome blocked, in English, at most 12 words, free of product and
  solution words. Form: "<who, briefly> can't <job> because <obstacle>" or a noun phrase
  like "Unprompted tabs from browser add-on updates". Prefer the first form.
- statement: two or three sentences: who has the problem, in what situation, what they do
  today, and what it costs them. Use only what the reports say.
- coherent: true if the members describe the same underlying problem; false if they only
  share a topic.
Return every input problem exactly once, with its id."""

SCHEMA = {
    "type": "object",
    "properties": {"problems": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "title": {"type": "string"},
                       "statement": {"type": "string"}, "coherent": {"type": "boolean"}},
        "required": ["id", "title", "statement", "coherent"]}}},
    "required": ["problems"],
}


def _prompt_id(conn) -> tuple[int, str]:
    version = hashlib.sha256((SYSTEM + json.dumps(SCHEMA, sort_keys=True)).encode()).hexdigest()[:12]
    with conn:
        conn.execute("INSERT OR IGNORE INTO prompt (name, version, text) VALUES ('curate', ?, ?)",
                     (version, SYSTEM))
    return conn.execute("SELECT id FROM prompt WHERE name='curate' AND version=?",
                        (version,)).fetchone()[0], version


def curate(conn: sqlite3.Connection, runtime: Runtime | None = None, limit: int = 40,
           batch_size: int = 10, model: str = MODEL) -> dict:
    _, version = _prompt_id(conn)
    todo = conn.execute(
        "SELECT id FROM problem WHERE title_source = 'auto' AND status != 'merged'"
        " ORDER BY id LIMIT ?", (limit,)).fetchall()
    stats = {"named": 0, "incoherent": 0, "llm_failures": 0, "llm_cost_usd": 0.0}
    if not todo:
        return stats
    runtime = runtime or ClaudeCode()
    with runs.run(conn, "curate", note=f"prompt {version}") as run_id:
        for i in range(0, len(todo), batch_size):
            payload = []
            for (pid,) in todo[i:i + batch_size]:
                members = conn.execute(
                    "SELECT p.job, p.problem, p.who, p.quote FROM problem_member m"
                    " JOIN pain p ON p.id = m.pain_id WHERE m.problem_id = ?"
                    " ORDER BY m.similarity DESC LIMIT ?", (pid, MAX_MEMBERS)).fetchall()
                payload.append({"id": pid, "reports": [dict(m) for m in members]})
            try:
                res = runtime.run(SYSTEM, json.dumps(payload, ensure_ascii=False), SCHEMA, model)
            except LLMError as e:
                stats["llm_failures"] += 1
                print(f"curate: batch failed: {e}")
                continue
            stats["llm_cost_usd"] += res.cost_usd
            wanted = {p["id"] for p in payload}
            with conn:
                for a in res.data.get("problems", []):
                    if a.get("id") not in wanted or not str(a.get("title", "")).strip():
                        continue
                    statement = a["statement"].strip()
                    if not a.get("coherent", True):
                        statement += " [Curator: members share a topic, not one problem; split or archive.]"
                        stats["incoherent"] += 1
                    conn.execute(
                        "UPDATE problem SET title = ?, statement = ?, title_source = 'curator',"
                        " updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')"
                        " WHERE id = ? AND title_source = 'auto'",
                        (a["title"].strip(), statement, a["id"]))
                    stats["named"] += 1
        for name, value in stats.items():
            runs.log_metric(conn, run_id, "mapping", f"curate_{name}", round(value, 4), version)
    return stats


def cmd_curate(args) -> int:
    conn = db.connect()
    db.migrate(conn)
    print(json.dumps(curate(conn, limit=args.limit, model=args.model), indent=1))
    return 0


def register_cli(sub) -> None:
    p = sub.add_parser("curate", help="name new problems (title + statement) with an LLM")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--model", default=MODEL)
    p.set_defaults(fn=cmd_curate)
