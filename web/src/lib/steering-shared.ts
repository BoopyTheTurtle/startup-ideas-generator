// Constants and formatters shared by server pages, server actions, and client forms.
// Nothing here touches the database, so client components may import it.

export const REASONS = [
  { code: "strong-evidence", label: "Strong evidence" },
  { code: "weak-evidence", label: "Weak evidence" },
  { code: "too-broad", label: "Too broad" },
  { code: "too-narrow", label: "Too narrow" },
  { code: "duplicate", label: "Duplicate" },
  { code: "not-a-business", label: "Not a business" },
  { code: "out-of-scope", label: "Out of scope" },
  { code: "other", label: "Other" },
] as const;

export type ReasonCode = (typeof REASONS)[number]["code"];

export function isReasonCode(v: unknown): v is ReasonCode {
  return typeof v === "string" && REASONS.some((r) => r.code === v);
}

export const NOTE_MAX = 500;
export const TITLE_MIN = 5;
export const TITLE_MAX = 200;

// Status-changing actions and the status each one sets.
export const STATUS_ACTIONS = {
  watch: "watching",
  promote: "promoted",
  archive: "archived",
} as const;
export type StatusAction = keyof typeof STATUS_ACTIONS;

export const PROBLEM_STATUSES = ["new", "watching", "promoted", "archived", "merged"] as const;
export type ProblemStatus = (typeof PROBLEM_STATUSES)[number];

// Merges keep the higher of the two statuses (pipeline.mapping.STATUS_RANK).
export const STATUS_RANK: Record<string, number> = { archived: 0, new: 1, watching: 2, promoted: 3 };

export const EVIDENCE: Record<string, { short: string; desc: string; long: string }> = {
  E1: { short: "said", desc: "a complaint or wish", long: "E1 said: a complaint or wish" },
  E2: { short: "did", desc: "past behavior, a workaround or time lost", long: "E2 did: past behavior, a workaround or time lost" },
  E3: { short: "paid", desc: "money spent on the problem", long: "E3 paid: money spent on the problem" },
};

// Trend flags need this many snapshot runs (SPEC stage 3).
export const TREND_MIN_SNAPSHOTS = 8;

// Collapse whitespace and control characters; cap the length.
export function cleanText(v: FormDataEntryValue | null, max: number): string {
  return String(v ?? "")
    .replace(/[\u0000-\u001f\u007f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max);
}

export function fmtDate(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 10) : "unknown";
}

export function fmtDateTime(iso: string | null | undefined): string {
  return iso ? iso.replace("T", " ").slice(0, 16) : "unknown";
}

export function fmtDuration(start: string, end: string | null): string {
  if (!end) return "running";
  const ms = Date.parse(end) - Date.parse(start);
  if (!Number.isFinite(ms) || ms < 0) return "?";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function fmtUsd(v: number): string {
  return `$${v.toFixed(v < 1 ? 3 : 2)}`;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
