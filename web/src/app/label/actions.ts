"use server";

import { refresh } from "next/cache";
import { appendLabel, isEvalSet, isLabel, readLabels } from "@/lib/labels";
import { labelableItem } from "@/lib/labeling";

export type LabelState = { message: string; error: boolean };

const NOTE_MAX = 500;

// The app runs on localhost for one user, so there is no session to check (SPEC v1
// non-goal). Everything from the form is still treated as untrusted input.
export async function submitLabel(_prev: LabelState, formData: FormData): Promise<LabelState> {
  const set = formData.get("set");
  const label = formData.get("label");
  const id = Number(formData.get("raw_item_id"));
  if (!isEvalSet(set) || !isLabel(label) || !Number.isSafeInteger(id) || id <= 0) {
    return { message: "Rejected: malformed submission.", error: true };
  }
  const item = labelableItem(id);
  if (!item) return { message: `Item ${id} is gone or has no text.`, error: true };

  // One label per item across both sets; a double submit is a no-op.
  if (readLabels("working").has(id) || readLabels("heldout").has(id)) {
    refresh();
    return { message: `Item ${id} was already labeled.`, error: false };
  }

  const note = String(formData.get("note") ?? "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, NOTE_MAX);
  appendLabel(set, {
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
