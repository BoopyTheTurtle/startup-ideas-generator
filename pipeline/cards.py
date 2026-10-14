"""Improvement cards: the stage 8 loop's unit of change (SPEC, "Improvement cards").

An auditor proposes a card; Edgar approves it in the app; a builder implements it on a
branch in its own worktree; `card-verify` checks the diff, the tests, and the eval diff;
a reviewer signs off; Edgar approves the merge; `card-merge` lands it on the base branch.

Edgar's three decisions (approve or reject a card, approve the merge, record the
held-out check) are database writes by the app. This module has no command for any of
them, and the status trigger in migration 007 refuses a build without an approval and a
merge without a merge approval and a cleared held-out check.

Guardrails enforced here, not left to agent instructions:
- a change touches the system or its evaluation, never both (classify_paths);
- no change touches the loop's own machinery (PROTECTED) or the held-out set;
- at most MAX_BUILDS_PER_WEEK builds start per ISO week (revert cards are exempt);
- a change to extraction needs a working-set eval with no regression, and Edgar's
  held-out check before it merges (agents never run or read the held-out eval).
"""

import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline import db, runs

KINDS = ("extraction", "mapping", "source", "coverage", "labeling", "instrument", "revert", "other")
TOUCHES = ("system", "eval")
SIZE_WEIGHT = {"S": 1, "M": 2, "L": 4}
OPEN = ("proposed", "approved", "building", "built", "ready")

MAX_BUILDS_PER_WEEK = 2
MAX_PROPOSALS_PER_WEEK = 5
REJECTED_COOLDOWN_DAYS = 28
EVAL_TOLERANCE = 0.01        # a candidate prompt may score this far below the base F1
TEST_TIMEOUT_S = 1800

# Path classes, tested in order against repo-relative POSIX paths.
PROTECTED = (                # the loop's own guardrails: a builder never edits these
    "pipeline/cards.py", "pipeline/migrations/", ".claude/", "CLAUDE.md", "scripts/",
    "tests/test_cards.py",
)
HELDOUT_MARK = "heldout"     # any path naming the held-out set
EVAL_PATHS = (               # the evaluation: labels, scoring, metrics, and their tests
    "evals/", "pipeline/evals.py", "pipeline/metrics.py", "pipeline/mutations.py",
    "pipeline/reassess.py", "pipeline/audit.py", "tests/test_evals.py", "tests/test_metrics.py",
    "tests/test_mutations.py", "tests/test_reassess.py", "tests/test_audit.py",
    "web/src/app/label/", "web/src/app/audit/", "web/src/lib/label", "web/src/lib/audit",
)
EXTRACTION_PATHS = ("pipeline/prompts/", "pipeline/extract.py", "pipeline/text.py", "pipeline/llm.py")


class CardError(RuntimeError):
    pass


def classify_paths(paths: list[str]) -> dict:
    """Sort changed paths into the guardrail classes."""
    protected = [p for p in paths if p.startswith(PROTECTED)]
    heldout = [p for p in paths if HELDOUT_MARK in p.lower()]
    evaluation = [p for p in paths if p.startswith(EVAL_PATHS)]
    system = [p for p in paths if p not in evaluation and p not in protected]
    return {"protected": protected, "heldout": heldout, "eval": evaluation, "system": system,
            "extraction": [p for p in paths if p.startswith(EXTRACTION_PATHS)]}


def iso_week(now: datetime | None = None) -> str:
    y, w, _ = (now or datetime.now(timezone.utc)).isocalendar()
    return f"{y}-W{w:02d}"


def _event(conn, card_id: int, actor: str, event: str, note: str | None = None) -> None:
    conn.execute("INSERT INTO card_event (card_id, actor, event, note) VALUES (?, ?, ?, ?)",
                 (card_id, actor, event, note))


def _slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n].strip("-") or "card"


def known_metrics(conn: sqlite3.Connection) -> set[str]:
    """'layer.name' for every metric logged so far or registered for computation."""
    from pipeline.metrics import REGISTRY  # lazy: metrics imports this module's neighbours
    seen = {f"{r[0]}.{r[1]}" for r in conn.execute("SELECT DISTINCT layer, name FROM metric")}
    return seen | {m.key for m in REGISTRY}


# --- Proposing --------------------------------------------------------------------------

def _need(d: dict, key: str, maxlen: int = 2000) -> str:
    v = d.get(key)
    if not isinstance(v, str) or not v.strip():
        raise CardError(f"card field {key!r} is required and must be non-empty text")
    return v.strip()[:maxlen]


def add_card(conn: sqlite3.Connection, d: dict, proposed_by: str = "auditor",
             reverts_card_id: int | None = None, now: datetime | None = None) -> int:
    """Validate and store one card. Raises CardError for anything an agent got wrong."""
    kind, touches = d.get("kind"), d.get("touches")
    if kind not in KINDS:
        raise CardError(f"kind must be one of {KINDS}")
    if touches not in TOUCHES:
        raise CardError("touches must be 'system' or 'eval': a card changes one, never both")
    size, value = d.get("size"), d.get("value")
    if size not in SIZE_WEIGHT:
        raise CardError("size must be S, M, or L")
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
        raise CardError("value must be an integer 1-5 (expected benefit)")
    metric = d.get("expected_metric") or None
    direction = d.get("expected_direction") or None
    if (metric is None) != (direction is None):
        raise CardError("expected_metric and expected_direction go together")
    if metric is not None:
        if direction not in ("up", "down"):
            raise CardError("expected_direction must be 'up' or 'down'")
        if metric not in known_metrics(conn):
            raise CardError(f"expected_metric {metric!r} is not a logged or registered metric")
    elif kind not in ("labeling", "source"):
        raise CardError("name the expected_metric the change should move")
    evidence = d.get("evidence", [])
    if not isinstance(evidence, list) or not evidence:
        raise CardError("evidence must be a non-empty list of {metric, subject, value, run_id}")
    for e in evidence:
        if not isinstance(e, dict) or not e.get("metric") or "value" not in e:
            raise CardError("each evidence entry needs metric and value")
    subject = d.get("expected_subject") or ""
    key = d.get("dedupe_key") or f"{kind}:{metric or _slug(d.get('title', ''))}:{subject}"
    week = iso_week(now)
    with conn:
        run_id = conn.execute("INSERT INTO run (kind, note) VALUES ('cards', 'card-add')").lastrowid
    try:
        with conn:
            n = conn.execute("SELECT COUNT(*) FROM improvement_card WHERE week = ? AND proposed_by = ?"
                             " AND kind != 'revert'", (week, proposed_by)).fetchone()[0]
            if proposed_by != "system" and n >= MAX_PROPOSALS_PER_WEEK:
                raise CardError(f"{n} cards proposed this week already (max {MAX_PROPOSALS_PER_WEEK})")
            cool = conn.execute(
                "SELECT id FROM improvement_card WHERE dedupe_key = ? AND status = 'rejected'"
                " AND julianday(?) - julianday(updated_at) < ?",
                (key, (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 REJECTED_COOLDOWN_DAYS)).fetchone()
            if cool:
                raise CardError(f"Edgar rejected card {cool[0]} with this key under "
                                f"{REJECTED_COOLDOWN_DAYS} days ago; do not propose it again")
            try:
                card_id = conn.execute(
                    "INSERT INTO improvement_card (created_run_id, week, kind, touches, title,"
                    " observation, evidence_json, hypothesis, change, expected_effect,"
                    " expected_metric, expected_subject, expected_direction, risk, size, value,"
                    " rank_score, dedupe_key, reverts_card_id, proposed_by)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (run_id, week, kind, touches, _need(d, "title", 120), _need(d, "observation"),
                     json.dumps(evidence), _need(d, "hypothesis"), _need(d, "change"),
                     _need(d, "expected_effect"), metric, subject, direction, _need(d, "risk"),
                     size, value, value / SIZE_WEIGHT[size], key, reverts_card_id,
                     proposed_by)).lastrowid
            except sqlite3.IntegrityError as e:
                if "dedupe_key" in str(e):
                    raise CardError(f"an open card already has the key {key!r}") from None
                raise
            _event(conn, card_id, proposed_by, "proposed")
    except BaseException:
        with conn:
            conn.execute("UPDATE run SET status = 'failed', finished_at = strftime("
                         "'%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?", (run_id,))
        raise
    with conn:
        conn.execute("UPDATE run SET status = 'ok', finished_at = strftime("
                     "'%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?", (run_id,))
    return card_id


# --- Reading ----------------------------------------------------------------------------

def get_card(conn: sqlite3.Connection, card_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM improvement_card WHERE id = ?", (card_id,)).fetchone()
    if row is None:
        raise CardError(f"no card {card_id}")
    return row


# --- Building ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Path, check: bool = True) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if check and p.returncode != 0:
        raise CardError(f"git {' '.join(args)}: {(p.stderr or p.stdout).strip()[:400]}")
    return p.stdout.strip()


def builds_this_week(conn: sqlite3.Connection, week: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM improvement_card WHERE build_week = ?"
                        " AND kind != 'revert'", (week,)).fetchone()[0]


def start_build(conn: sqlite3.Connection, card_id: int, base: str = "dev",
                now: datetime | None = None) -> Path:
    """Approved card -> building: a branch and a worktree off the base branch."""
    card = get_card(conn, card_id)
    if card["status"] != "approved":
        raise CardError(f"card {card_id} is {card['status']}; only an approved card builds")
    week = iso_week(now)
    if card["kind"] != "revert" and builds_this_week(conn, week) >= MAX_BUILDS_PER_WEEK:
        raise CardError(f"{MAX_BUILDS_PER_WEEK} builds already started in {week}; "
                        "changes stay attributable, so this card waits for next week")
    root = db.ROOT
    if _git(["rev-parse", "--verify", base], root, check=False) == "":
        raise CardError(f"base branch {base!r} does not exist")
    branch = f"card/{card_id}-{_slug(card['title'])}"
    path = root.parent / "sig-worktrees" / f"card-{card_id}"
    path.parent.mkdir(parents=True, exist_ok=True)
    base_sha = _git(["rev-parse", base], root)
    from pipeline.embed import current_extract_version
    base_version = current_extract_version()  # the main checkout's prompt: the eval baseline
    _git(["worktree", "add", "-b", branch, str(path), base], root)
    with conn:
        conn.execute(
            "UPDATE improvement_card SET status = 'building', build_week = ?, branch = ?,"
            " worktree_path = ?, base_branch = ?, base_sha = ?, base_extract_version = ?,"
            " updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
            (week, branch, str(path), base, base_sha, base_version, card_id))
        _event(conn, card_id, "builder", "build started", f"{branch} at {base_sha[:8]}")
    return path


def _eval_f1(conn: sqlite3.Connection, version: str) -> float | None:
    row = conn.execute("SELECT value FROM metric WHERE layer = 'extraction' AND name = 'eval_f1'"
                       " AND subject = ? ORDER BY id DESC LIMIT 1", (f"working:{version}",)).fetchone()
    return row[0] if row else None


def _worktree_prompt_version(path: Path) -> str:
    out = subprocess.run(
        ["uv", "run", "python", "-c",
         "from pipeline.embed import current_extract_version as v; print(v())"],
        cwd=path, capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise CardError(f"could not read the prompt version in the worktree: {out.stderr.strip()[-300:]}")
    return out.stdout.strip().splitlines()[-1]


def verify(conn: sqlite3.Connection, card_id: int, run_tests: bool = True) -> dict:
    """Check a building card's branch. Moves it to 'built' when every check passes."""
    card = get_card(conn, card_id)
    if card["status"] != "building":
        raise CardError(f"card {card_id} is {card['status']}; verify runs on a building card")
    path = Path(card["worktree_path"] or "")
    if not path.is_dir():
        raise CardError(f"worktree {path} is missing")
    if _git(["status", "--porcelain"], path):
        raise CardError("the worktree has uncommitted changes; commit them first")
    head = _git(["rev-parse", "HEAD"], path)
    base = _git(["merge-base", card["base_branch"], "HEAD"], path)
    changed = [p for p in _git(["diff", "--name-only", f"{base}..HEAD"], path).splitlines() if p]
    cls = classify_paths(changed)
    problems: list[str] = []
    if not changed:
        problems.append("the branch has no changes")
    if cls["protected"]:
        problems.append(f"touches protected loop files: {cls['protected']}")
    if cls["heldout"]:
        problems.append(f"touches the held-out set: {cls['heldout']}")
    if cls["eval"] and cls["system"]:
        problems.append("touches both the system and its evaluation: "
                        f"system {cls['system'][:5]}, eval {cls['eval'][:5]}")
    elif changed and cls["eval"] and card["touches"] != "eval":
        problems.append("the card says it touches the system, but the diff changes the evaluation")
    elif changed and cls["system"] and card["touches"] != "system":
        problems.append("the card says it touches the evaluation, but the diff changes the system")
    needs_heldout = bool(cls["extraction"]) and card["touches"] == "system"
    result: dict = {"head": head, "changed": changed, "needs_heldout": needs_heldout, "problems": problems}

    if needs_heldout:
        cand = _worktree_prompt_version(path)
        base_f1 = _eval_f1(conn, card["base_extract_version"] or "")
        cand_f1 = _eval_f1(conn, cand)
        result["eval_diff"] = {"base_version": card["base_extract_version"], "base_f1": base_f1,
                               "candidate_version": cand, "candidate_f1": cand_f1}
        if base_f1 is None:
            problems.append("no working-set eval for the base prompt; run `eval` on main first")
        elif cand_f1 is None:
            problems.append("no working-set eval for the candidate prompt; in the worktree run "
                            "`extract --labeled working --reextract` then `eval` "
                            "(both spend subscription: cap them)")
        elif cand_f1 < base_f1 - EVAL_TOLERANCE:
            problems.append(f"working-set F1 regressed: {base_f1:.3f} -> {cand_f1:.3f}")
    if run_tests and not problems:
        t = subprocess.run(["uv", "run", "pytest", "-q", "-x"], cwd=path, capture_output=True,
                           text=True, timeout=TEST_TIMEOUT_S)
        result["tests"] = {"passed": t.returncode == 0, "tail": t.stdout.strip()[-300:]}
        if t.returncode != 0:
            problems.append("tests failed")
    ok = not problems
    with conn:
        conn.execute(
            "UPDATE improvement_card SET verify_json = ?, needs_heldout = ?,"
            " heldout_check = CASE WHEN NOT ? THEN 'not_needed'"
            "   WHEN head_sha IS ? AND heldout_check != 'not_needed' THEN heldout_check"
            "   ELSE 'pending' END,"
            " merge_approved_at = CASE WHEN head_sha IS ? THEN merge_approved_at END,"
            " head_sha = ?, status = CASE WHEN ? THEN 'built' ELSE status END,"
            " updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
            (json.dumps(result), int(needs_heldout), needs_heldout, head, head, head, ok, card_id))
        _event(conn, card_id, "system", "verified" if ok else "verify failed",
               "; ".join(problems) or None)
    result["ok"] = ok
    return result


def review(conn: sqlite3.Connection, card_id: int, verdict: str, notes: str) -> str:
    """The reviewer's verdict on a built card: approve -> ready, changes -> building."""
    if verdict not in ("approve", "changes"):
        raise CardError("verdict must be approve or changes")
    card = get_card(conn, card_id)
    if card["status"] != "built":
        raise CardError(f"card {card_id} is {card['status']}; review a built card")
    if not notes.strip():
        raise CardError("give review notes")
    new = "ready" if verdict == "approve" else "building"
    with conn:
        conn.execute("UPDATE improvement_card SET review_verdict = ?, review_notes = ?,"
                     " status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                     (verdict, notes.strip(), new, card_id))
        _event(conn, card_id, "reviewer", f"review: {verdict}", notes.strip()[:500])
    return new


def abandon(conn: sqlite3.Connection, card_id: int, reason: str, actor: str = "builder") -> None:
    card = get_card(conn, card_id)
    with conn:
        conn.execute("UPDATE improvement_card SET status = 'abandoned', updated_at ="
                     " strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?", (card_id,))
        _event(conn, card_id, actor, "abandoned", reason)
    wt = Path(card["worktree_path"] or "")
    if wt.is_dir():
        _git(["worktree", "remove", "--force", str(wt)], db.ROOT, check=False)


def baseline_for(conn: sqlite3.Connection, card: sqlite3.Row) -> dict | None:
    """The latest logged value of the card's expected metric, for later regression checks."""
    if not card["expected_metric"]:
        return None
    layer, name = card["expected_metric"].split(".", 1)
    row = conn.execute("SELECT value, run_id FROM metric WHERE layer = ? AND name = ? AND subject = ?"
                       " ORDER BY id DESC LIMIT 1", (layer, name, card["expected_subject"])).fetchone()
    if row is None:
        return None
    return {"metric": card["expected_metric"], "subject": card["expected_subject"],
            "value": row[0], "run_id": row[1], "direction": card["expected_direction"]}


def merge(conn: sqlite3.Connection, card_id: int) -> str:
    """Merge a ready, merge-approved card into its base branch (in the main checkout)."""
    card = get_card(conn, card_id)
    if card["status"] != "ready":
        raise CardError(f"card {card_id} is {card['status']}; only a ready card merges")
    if not card["merge_approved_at"]:
        raise CardError("Edgar has not approved the merge (card page in the app)")
    if card["heldout_check"] not in ("pass", "not_needed"):
        raise CardError(f"held-out check is {card['heldout_check']}; Edgar records it in the app")
    root, base = db.ROOT, card["base_branch"]
    if _git(["rev-parse", "--abbrev-ref", "HEAD"], root) != base:
        raise CardError(f"check out {base} in the main checkout first")
    if _git(["status", "--porcelain", "--untracked-files=no"], root):
        raise CardError("the main checkout has uncommitted changes")
    wt = Path(card["worktree_path"] or "")
    if wt.is_dir():
        head = _git(["rev-parse", "HEAD"], wt)
        if head != card["head_sha"]:
            raise CardError("the branch moved since verify; rerun card-verify and card-review")
    msg = f"Card {card_id}: {card['title']}\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
    p = subprocess.run(["git", "merge", "--no-ff", "--no-commit", card["branch"]], cwd=root,
                       capture_output=True, text=True)
    try:
        if p.returncode != 0:
            raise CardError(f"merge conflict or failure: {(p.stdout + p.stderr).strip()[-300:]}")
        t = subprocess.run(["uv", "run", "pytest", "-q", "-x"], cwd=root, capture_output=True,
                           text=True, timeout=TEST_TIMEOUT_S)
        if t.returncode != 0:
            raise CardError(f"tests fail on the merge result: {t.stdout.strip()[-300:]}")
    except BaseException:
        subprocess.run(["git", "merge", "--abort"], cwd=root, capture_output=True)
        raise
    _git(["commit", "-m", msg], root)
    sha = _git(["rev-parse", "HEAD"], root)
    baseline = baseline_for(conn, card)
    with conn:
        conn.execute("UPDATE improvement_card SET status = 'merged', merged_at ="
                     " strftime('%Y-%m-%dT%H:%M:%fZ','now'), merged_sha = ?, baseline_json = ?,"
                     " updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                     (sha, json.dumps(baseline) if baseline else None, card_id))
        _event(conn, card_id, "system", "merged", sha[:8])
        if card["reverts_card_id"]:
            conn.execute("UPDATE improvement_card SET status = 'reverted', updated_at ="
                         " strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ? AND status = 'merged'",
                         (card["reverts_card_id"],))
            _event(conn, card["reverts_card_id"], "system", "reverted", f"by card {card_id}")
    if wt.is_dir():
        _git(["worktree", "remove", "--force", str(wt)], root, check=False)
    return sha


# --- CLI --------------------------------------------------------------------------------

def _fmt_row(r) -> str:
    return (f"{r['id']:>4}  {r['status']:<9} {r['kind']:<10} {r['touches']:<6} "
            f"rank {r['rank_score']:.2f}  {r['week']}  {r['title'][:70]}")


def cmd_cards(args) -> int:
    conn = db.connect()
    db.migrate(conn)
    q, params = "SELECT * FROM improvement_card", []
    if args.status:
        q += f" WHERE status IN ({','.join('?' * len(args.status))})"
        params = list(args.status)
    for r in conn.execute(q + " ORDER BY id DESC LIMIT ?", (*params, args.limit)):
        print(_fmt_row(r))
    return 0


def cmd_card_show(args) -> int:
    conn = db.connect()
    db.migrate(conn)
    card = get_card(conn, args.id)
    for k in card.keys():
        if card[k] is not None and k not in ("created_run_id",):
            print(f"{k}: {card[k]}")
    print("\nevents:")
    for e in conn.execute("SELECT * FROM card_event WHERE card_id = ? ORDER BY id", (args.id,)):
        print(f"  {e['at']}  {e['actor']:<9} {e['event']}  {e['note'] or ''}")
    return 0


def _run(fn) -> int:
    try:
        return fn()
    except CardError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


def cmd_card_add(args) -> int:
    raw = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"error: not valid JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(d, dict):
        print("error: expected one JSON object", file=sys.stderr)
        return 2
    conn = db.connect()
    db.migrate(conn)

    def go():
        print(f"card {add_card(conn, d, proposed_by=args.by)} proposed")
        return 0
    return _run(go)


def cmd_card_start(args) -> int:
    conn = db.connect()
    db.migrate(conn)

    def go():
        print(start_build(conn, args.id, base=args.base))
        return 0
    return _run(go)


def cmd_card_verify(args) -> int:
    conn = db.connect()
    db.migrate(conn)

    def go():
        res = verify(conn, args.id, run_tests=not args.no_tests)
        print(json.dumps({k: v for k, v in res.items() if k != "changed"}, indent=2))
        print(f"{len(res['changed'])} files changed")
        return 0 if res["ok"] else 1
    return _run(go)


def cmd_card_review(args) -> int:
    conn = db.connect()
    db.migrate(conn)

    def go():
        print(f"card {args.id} -> {review(conn, args.id, args.verdict, args.notes)}")
        return 0
    return _run(go)


def cmd_card_abandon(args) -> int:
    conn = db.connect()
    db.migrate(conn)

    def go():
        abandon(conn, args.id, args.reason)
        print(f"card {args.id} abandoned")
        return 0
    return _run(go)


def cmd_card_merge(args) -> int:
    conn = db.connect()
    db.migrate(conn)

    def go():
        print(f"merged at {merge(conn, args.id)}")
        return 0
    return _run(go)


def register_cli(sub) -> None:
    p = sub.add_parser("cards", help="list improvement cards")
    p.add_argument("--status", nargs="+")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(fn=cmd_cards)
    p = sub.add_parser("card-show", help="one card with its history")
    p.add_argument("id", type=int)
    p.set_defaults(fn=cmd_card_show)
    p = sub.add_parser("card-add", help="propose a card from JSON on stdin (or --file)")
    p.add_argument("--file")
    p.add_argument("--by", default="auditor", choices=["auditor", "system"])
    p.set_defaults(fn=cmd_card_add)
    p = sub.add_parser("card-start", help="branch and worktree for an approved card")
    p.add_argument("id", type=int)
    p.add_argument("--base", default="dev")
    p.set_defaults(fn=cmd_card_start)
    p = sub.add_parser("card-verify", help="check a building card's branch")
    p.add_argument("id", type=int)
    p.add_argument("--no-tests", action="store_true")
    p.set_defaults(fn=cmd_card_verify)
    p = sub.add_parser("card-review", help="record the reviewer's verdict")
    p.add_argument("id", type=int)
    p.add_argument("--verdict", required=True, choices=["approve", "changes"])
    p.add_argument("--notes", required=True)
    p.set_defaults(fn=cmd_card_review)
    p = sub.add_parser("card-abandon", help="give up on a card in flight")
    p.add_argument("id", type=int)
    p.add_argument("--reason", required=True)
    p.set_defaults(fn=cmd_card_abandon)
    p = sub.add_parser("card-merge", help="merge a ready, merge-approved card")
    p.add_argument("id", type=int)
    p.set_defaults(fn=cmd_card_merge)
