// Eval-set labels live in JSON-lines files, not the database, so the held-out set stays
// outside everything agents query. pipeline/evals.py reads the same files.
//   evals/working/labels.jsonl   committed; agents may read it
//   evals/heldout/labels.jsonl   gitignored; Edgar only
// A later line for the same raw_item_id overrides an earlier one.
import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

export const EVAL_SETS = ["working", "heldout"] as const;
export type EvalSet = (typeof EVAL_SETS)[number];

export const LABELS = ["pain", "not_pain", "unsure"] as const;
export type Label = (typeof LABELS)[number];

export type LabelRecord = {
  raw_item_id: number;
  source: string;
  source_id: string;
  label: Label;
  note: string;
  labeled_at: string;
};

const EVALS_DIR = path.resolve(process.cwd(), "..", "evals");

export function isEvalSet(v: unknown): v is EvalSet {
  return typeof v === "string" && (EVAL_SETS as readonly string[]).includes(v);
}

export function isLabel(v: unknown): v is Label {
  return typeof v === "string" && (LABELS as readonly string[]).includes(v);
}

function labelsFile(set: EvalSet): string {
  return path.join(EVALS_DIR, set, "labels.jsonl");
}

export function readLabels(set: EvalSet): Map<number, LabelRecord> {
  const out = new Map<number, LabelRecord>();
  const file = labelsFile(set);
  // Labels are runtime files, not build inputs.
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

export function appendLabel(set: EvalSet, rec: LabelRecord): void {
  const file = labelsFile(set);
  mkdirSync(/*turbopackIgnore: true*/ path.dirname(file), { recursive: true });
  appendFileSync(/*turbopackIgnore: true*/ file, JSON.stringify(rec) + "\n", "utf8");
}
