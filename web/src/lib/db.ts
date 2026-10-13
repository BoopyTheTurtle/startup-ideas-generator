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

export function open(): DatabaseSync | null {
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

export type Health = {
  source: string;
  last_status: string | null;
  last_success_at: string | null;
  last_error: string | null;
  consecutive_failures: number;
  items_last_run: number;
  total_items: number;
  stale: number; // 1 when the last success is older than STALE_DAYS, or never happened
};

export const STALE_DAYS = 8;

export async function collectorHealth(): Promise<Health[] | null> {
  await connection();
  const conn = open();
  if (!conn) return null;
  const hasTable = conn
    .prepare("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'collector_health'")
    .get();
  if (!hasTable) return [];
  return conn
    .prepare(
      `SELECT h.*,
              (SELECT COUNT(*) FROM raw_item r WHERE r.source = h.source) AS total_items,
              COALESCE(julianday('now') - julianday(h.last_success_at) > ?, 1) AS stale
         FROM collector_health h ORDER BY h.source`,
    )
    .all(STALE_DAYS) as Health[];
}

export function dbPath(): string {
  return DB_PATH;
}
