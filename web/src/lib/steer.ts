// Steering writes: the only rows the app writes to the database. Each call records one
// `decision` row and, for status changes and renames, updates problem.status or
// problem.title (title_source = 'human'). Server only; called from server actions after
// they validate the form. Merges themselves run through the Python CLI (merge-cli.ts).
import type { DatabaseSync } from "node:sqlite";
import { open } from "@/lib/db";
import { STATUS_ACTIONS, type ReasonCode, type StatusAction } from "@/lib/steering-shared";

export type SteerResult = { ok: boolean; message: string };

const NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')";

function tx<T>(conn: DatabaseSync, fn: () => T): T {
  conn.exec("BEGIN IMMEDIATE");
  try {
    const out = fn();
    conn.exec("COMMIT");
    return out;
  } catch (e) {
    conn.exec("ROLLBACK");
    throw e;
  }
}

type ProblemState = { id: number; title: string; status: string };

function liveProblem(conn: DatabaseSync, id: number): ProblemState | null {
  const row = conn.prepare("SELECT id, title, status FROM problem WHERE id = ?").get(id) as
    | ProblemState
    | undefined;
  return row ?? null;
}

function insertDecision(
  conn: DatabaseSync,
  problemId: number,
  action: string,
  reason: ReasonCode,
  note: string,
): void {
  conn
    .prepare("INSERT INTO decision (problem_id, action, reason, note) VALUES (?, ?, ?, ?)")
    .run(problemId, action, reason, note || null);
}

function db(): DatabaseSync {
  const conn = open();
  if (!conn) throw new Error("no database");
  return conn;
}

export function setStatus(
  problemId: number,
  action: StatusAction,
  reason: ReasonCode,
  note: string,
): SteerResult {
  const conn = db();
  const status = STATUS_ACTIONS[action];
  return tx(conn, () => {
    const p = liveProblem(conn, problemId);
    if (!p) return { ok: false, message: `Problem ${problemId} does not exist.` };
    if (p.status === "merged") return { ok: false, message: `Problem ${problemId} was merged.` };
    if (p.status === status) return { ok: false, message: `Problem ${problemId} is already ${status}.` };
    conn
      .prepare(`UPDATE problem SET status = ?, updated_at = ${NOW} WHERE id = ?`)
      .run(status, problemId);
    insertDecision(conn, problemId, action, reason, note);
    return { ok: true, message: `Problem ${problemId}: ${p.status} → ${status}.` };
  });
}

export function rename(problemId: number, title: string, reason: ReasonCode, note: string): SteerResult {
  const conn = db();
  return tx(conn, () => {
    const p = liveProblem(conn, problemId);
    if (!p) return { ok: false, message: `Problem ${problemId} does not exist.` };
    if (p.status === "merged") return { ok: false, message: `Problem ${problemId} was merged.` };
    if (p.title === title) return { ok: false, message: "The title is unchanged." };
    conn
      .prepare(`UPDATE problem SET title = ?, title_source = 'human', updated_at = ${NOW} WHERE id = ?`)
      .run(title, problemId);
    // Keep the old title in the history; the problem row only holds the new one.
    const record = `was "${p.title}"${note ? ` | ${note}` : ""}`;
    insertDecision(conn, problemId, "rename", reason, record);
    return { ok: true, message: `Renamed problem ${problemId}.` };
  });
}

export function addNote(problemId: number, reason: ReasonCode, note: string): SteerResult {
  const conn = db();
  return tx(conn, () => {
    const p = liveProblem(conn, problemId);
    if (!p) return { ok: false, message: `Problem ${problemId} does not exist.` };
    insertDecision(conn, problemId, "note", reason, note);
    return { ok: true, message: `Note saved on problem ${problemId}.` };
  });
}

export type Candidate = { a_id: number; b_id: number; status: string };

export function mergeCandidate(aId: number, bId: number): Candidate | null {
  const row = db()
    .prepare("SELECT a_id, b_id, status FROM merge_candidate WHERE a_id = ? AND b_id = ?")
    .get(aId, bId) as Candidate | undefined;
  return row ?? null;
}

// Keeps the pair apart: the candidate closes as rejected and one decision row (on the
// lower id, which owns the pair) records it. Both problem pages list the pair itself.
export function rejectMerge(aId: number, bId: number, reason: ReasonCode, note: string): SteerResult {
  const conn = db();
  return tx(conn, () => {
    const res = conn
      .prepare(
        "UPDATE merge_candidate SET status = 'rejected' WHERE a_id = ? AND b_id = ? AND status = 'open'",
      )
      .run(aId, bId);
    if (res.changes !== 1) {
      return { ok: false, message: `Merge candidate ${aId}/${bId} is no longer open.` };
    }
    const record = `kept apart from problem ${bId}${note ? ` | ${note}` : ""}`;
    insertDecision(conn, aId, "merge-reject", reason, record);
    return { ok: true, message: `Kept problems ${aId} and ${bId} apart.` };
  });
}
