"use server";

import { refresh } from "next/cache";
import { appendAuditLabel, isMonth, readAuditLabels, readSample } from "@/lib/audit";
import { labelableItem } from "@/lib/labeling";
import { isLabel } from "@/lib/labels";

export type AuditState = { message: string; error: boolean };

const NOTE_MAX = 500;

// Localhost, one user, no session (SPEC v1 non-goal); the form is still untrusted input.
// The client names the month, the item and the label; the server checks the item belongs to
// that month's sample and takes its source and source_id from the database.
export async function submitAuditLabel(_prev: AuditState, formData: FormData): Promise<AuditState> {
  const month = formData.get("month");
  const label = formData.get("label");
  const id = Number(formData.get("raw_item_id"));
  if (!isMonth(month) || !isLabel(label) || !Number.isSafeInteger(id) || id <= 0) {
    return { message: "Rejected: malformed submission.", error: true };
  }
  const sample = readSample(month);
  if (sample.kind !== "ok") return { message: `There is no valid sample for ${month}.`, error: true };
  if (!sample.sample.items.some((i) => i.raw_item_id === id)) {
    return { message: `Item ${id} is not in the ${month} sample.`, error: true };
  }
  if (readAuditLabels(month).has(id)) {
    // One label per item; a double submit is a no-op.
    refresh();
    return { message: `Item ${id} was already labeled.`, error: false };
  }
  const item = labelableItem(id);
  if (!item) return { message: `Item ${id} is gone or has no text.`, error: true };

  const note = String(formData.get("note") ?? "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, NOTE_MAX);
  appendAuditLabel(month, {
    raw_item_id: item.id,
    source: item.source,
    source_id: item.source_id,
    label,
    note,
    labeled_at: new Date().toISOString(),
  });
  refresh();
  return { message: `Saved item ${id} as ${label.replace("_", " ")}.`, error: false };
}
