// Queries behind /label: stratified sampling of unlabeled raw items. Model output is
// never shown while labeling, because labels are what the model is scored against.
import { connection } from "next/server";
import { open } from "@/lib/db";

export type LabelItem = {
  id: number;
  source: string;
  source_id: string;
  url: string | null;
  title: string | null;
  body: string;
  lang: string | null;
  country: string | null;
  created_at: string | null;
};

// Items with no text to judge never enter the pool. text_discarded_at arrives with
// migration 003; before that every item still has its text.
function poolFilter(conn: NonNullable<ReturnType<typeof open>>): string {
  const cols = conn.prepare("PRAGMA table_info(raw_item)").all() as { name: string }[];
  const discarded = cols.some((c) => c.name === "text_discarded_at")
    ? "AND text_discarded_at IS NULL"
    : "";
  return `(body <> '' OR COALESCE(title, '') <> '') ${discarded}
          AND id NOT IN (SELECT value FROM json_each(?))`;
}

// Pick a source uniformly among sources that still have unlabeled items, then a random
// item from it, so small sources appear as often as large ones.
export async function nextItem(exclude: number[]): Promise<LabelItem | null> {
  await connection();
  const conn = open();
  if (!conn) return null;
  const filter = poolFilter(conn);
  const ex = JSON.stringify(exclude);
  const row = conn
    .prepare(
      `WITH pool AS (SELECT id, source FROM raw_item WHERE ${filter}),
            pick AS (SELECT source FROM (SELECT DISTINCT source FROM pool) ORDER BY random() LIMIT 1)
       SELECT id, source, source_id, url, title, body, lang, country, created_at
         FROM raw_item
        WHERE id = (SELECT id FROM pool WHERE source = (SELECT source FROM pick)
                     ORDER BY random() LIMIT 1)`,
    )
    .get(ex);
  return (row as LabelItem | undefined) ?? null;
}

// Unlabeled items left per source.
export async function remainingBySource(exclude: number[]): Promise<Map<string, number>> {
  await connection();
  const conn = open();
  const out = new Map<string, number>();
  if (!conn) return out;
  const rows = conn
    .prepare(`SELECT source, COUNT(*) AS n FROM raw_item WHERE ${poolFilter(conn)} GROUP BY source`)
    .all(JSON.stringify(exclude)) as { source: string; n: number }[];
  for (const r of rows) out.set(r.source, r.n);
  return out;
}

// Re-read from the database inside the server action: the client names the item, the
// server supplies its source and id.
export function labelableItem(id: number): { id: number; source: string; source_id: string } | null {
  const conn = open();
  if (!conn) return null;
  const row = conn
    .prepare(`SELECT id, source, source_id FROM raw_item WHERE id = ? AND ${poolFilter(conn)}`)
    .get(id, "[]");
  return (row as { id: number; source: string; source_id: string } | undefined) ?? null;
}
