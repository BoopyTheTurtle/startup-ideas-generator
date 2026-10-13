// Server-only access to the pipeline's SQLite database via Node's built-in driver.
// Python owns the schema and nearly all writes; the app reads, and later writes
// steering decisions.
import { DatabaseSync } from "node:sqlite";
import { existsSync } from "node:fs";
import path from "node:path";
import { connection } from "next/server";

const DB_PATH =
  process.env.SIG_DB ?? path.resolve(process.cwd(), "..", "data", "ideas.db");

let db: DatabaseSync | null = null;

function open(): DatabaseSync | null {
  if (db) return db;
  // The DB is a local runtime file, not a build input.
  if (!existsSync(/*turbopackIgnore: true*/ DB_PATH)) return null;
  db = new DatabaseSync(/*turbopackIgnore: true*/ DB_PATH);
  db.exec("PRAGMA busy_timeout = 5000");
  return db;
}

export type Run = {
  id: number;
  kind: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  note: string | null;
  metric_count: number;
};

// The driver is synchronous, so connection() keeps these reads out of prerendering.
export async function recentRuns(limit = 20): Promise<Run[] | null> {
  await connection();
  const conn = open();
  if (!conn) return null;
  return conn
    .prepare(
      `SELECT r.id, r.kind, r.status, r.started_at, r.finished_at, r.note,
              (SELECT COUNT(*) FROM metric m WHERE m.run_id = r.id) AS metric_count
         FROM run r ORDER BY r.id DESC LIMIT ?`,
    )
    .all(limit) as Run[];
}

export function dbPath(): string {
  return DB_PATH;
}
