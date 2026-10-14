// Monthly blind audit (SPEC stage 8, "Blind audit"): Edgar labels 20 random items without
// seeing model output or earlier labels. Python draws the sample and scores it; the app
// only shows the items and appends his labels. The contract:
//   evals/blind/<YYYY-MM>/sample.json   {"month","seed","drawn_at","items":[{"raw_item_id","source"}]}
//   evals/blind/<YYYY-MM>/labels.jsonl  one record per label, the same shape as the working
//                                       set (raw_item_id, source, source_id, label, note,
//                                       labeled_at); a later line for the same id wins
//   metric table                        methodology.audit_label_drift_agreement and
//                                       methodology.audit_model_agreement, from `audit-score`
// Nothing here reads extraction rows, earlier labels, or the held-out set.
import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { connection } from "next/server";
import { open } from "@/lib/db";
import { isLabel, type LabelRecord } from "@/lib/labels";
import { REPO_ROOT } from "@/lib/paths";

const BLIND_DIR = path.join(REPO_ROOT, "evals", "blind");

export const SCORE_METRICS = [
  { name: "audit_label_drift_agreement", label: "Agreement with the working-set labels (label drift)" },
  { name: "audit_model_agreement", label: "Agreement with the model (true error)" },
] as const;

export function isMonth(v: unknown): v is string {
  return typeof v === "string" && /^\d{4}-(0[1-9]|1[0-2])$/.test(v);
}

// Under Cache Components the clock is request-time data.
export async function currentMonth(): Promise<string> {
  await connection();
  return new Date().toISOString().slice(0, 7);
}

export type SampleItem = { raw_item_id: number; source: string };
export type Sample = { month: string; seed: string; drawn_at: string; items: SampleItem[] };

export type SampleResult =
  | { kind: "missing" }
  | { kind: "invalid"; reason: string }
  | { kind: "ok"; sample: Sample };

function dir(month: string): string {
  if (!isMonth(month)) throw new Error("bad month");
  return path.join(BLIND_DIR, month);
}

export function readSample(month: string): SampleResult {
  const file = path.join(dir(month), "sample.json");
  // Runtime files, not build inputs.
  if (!existsSync(/*turbopackIgnore: true*/ file)) return { kind: "missing" };
  let raw: unknown;
  try {
    raw = JSON.parse(readFileSync(/*turbopackIgnore: true*/ file, "utf8"));
  } catch {
    return { kind: "invalid", reason: "sample.json is not valid JSON" };
  }
  if (typeof raw !== "object" || raw === null) return { kind: "invalid", reason: "sample.json is not an object" };
  const r = raw as Record<string, unknown>;
  if (!Array.isArray(r.items) || r.items.length === 0) {
    return { kind: "invalid", reason: "sample.json has no items" };
  }
  const items: SampleItem[] = [];
  const seen = new Set<number>();
  for (const it of r.items) {
    const o = it as Record<string, unknown> | null;
    const id = o?.raw_item_id;
    if (typeof id !== "number" || !Number.isSafeInteger(id) || id <= 0 || typeof o?.source !== "string") {
      return { kind: "invalid", reason: "an item in sample.json lacks an integer raw_item_id or a source" };
    }
    if (seen.has(id)) return { kind: "invalid", reason: `item ${id} appears twice in sample.json` };
    seen.add(id);
    items.push({ raw_item_id: id, source: o.source });
  }
  return {
    kind: "ok",
    sample: { month, seed: String(r.seed ?? ""), drawn_at: String(r.drawn_at ?? ""), items },
  };
}

export function readAuditLabels(month: string): Map<number, LabelRecord> {
  const out = new Map<number, LabelRecord>();
  const file = path.join(dir(month), "labels.jsonl");
  if (!existsSync(/*turbopackIgnore: true*/ file)) return out;
  for (const line of readFileSync(/*turbopackIgnore: true*/ file, "utf8").split("\n")) {
    if (!line.trim()) continue;
    try {
      const rec = JSON.parse(line) as LabelRecord;
      if (Number.isInteger(rec.raw_item_id) && isLabel(rec.label)) out.set(rec.raw_item_id, rec);
    } catch {
      // A torn line from an interrupted write; the Python side reports it loudly.
    }
  }
  return out;
}

export function appendAuditLabel(month: string, rec: LabelRecord): void {
  const d = dir(month);
  mkdirSync(/*turbopackIgnore: true*/ d, { recursive: true });
  appendFileSync(/*turbopackIgnore: true*/ path.join(d, "labels.jsonl"), JSON.stringify(rec) + "\n", "utf8");
}

export type AuditScore = {
  name: string;
  label: string;
  value: number | null;
  run_id: number | null;
  recorded_at: string | null;
  subject: string;
};

// The latest logged value of each audit metric: a row for this month wins, else the newest
// row with no subject. The row's date and run show which audit it came from.
export async function auditScores(month: string): Promise<AuditScore[]> {
  await connection();
  const c = open();
  return SCORE_METRICS.map((m) => {
    const empty: AuditScore = { ...m, value: null, run_id: null, recorded_at: null, subject: "" };
    if (!c) return empty;
    const row = c
      .prepare(
        `SELECT value, run_id, recorded_at, subject FROM metric
          WHERE layer = 'methodology' AND name = ? AND subject IN (?, '')
          ORDER BY (subject = ?) DESC, id DESC LIMIT 1`,
      )
      .get(m.name, month, month) as
      | { value: number; run_id: number; recorded_at: string; subject: string }
      | undefined;
    return row ? { ...m, ...row } : empty;
  });
}
