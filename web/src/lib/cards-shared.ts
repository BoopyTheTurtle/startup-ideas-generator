// Constants and formatters for improvement cards, shared by server pages, server actions,
// and client forms. Nothing here touches the database. Mirrors pipeline/cards.py.

export const CARD_STATUSES = [
  "proposed",
  "approved",
  "building",
  "built",
  "ready",
  "merged",
  "reverted",
  "rejected",
  "abandoned",
] as const;
export type CardStatus = (typeof CARD_STATUSES)[number];

export function isCardStatus(v: unknown): v is CardStatus {
  return typeof v === "string" && (CARD_STATUSES as readonly string[]).includes(v);
}

// What each status means for Edgar, in plain words.
export const STATUS_INFO: Record<CardStatus, { title: string; blurb: string }> = {
  proposed: { title: "Proposed", blurb: "Waiting for your decision to approve or reject." },
  approved: { title: "Approved", blurb: "Approved by you; a builder has not started yet." },
  building: { title: "Building", blurb: "A builder is working on the card's branch." },
  built: { title: "Built", blurb: "The branch passed its checks; the reviewer has not signed off yet." },
  ready: { title: "Ready", blurb: "Reviewed and ready for your merge approval." },
  merged: { title: "Merged", blurb: "On the base branch. Its metric is watched for regressions." },
  reverted: { title: "Reverted", blurb: "Merged, then undone by a revert card." },
  rejected: { title: "Rejected", blurb: "You turned this card down." },
  abandoned: { title: "Abandoned", blurb: "Dropped while in flight." },
};

// Closed statuses: shown collapsed on the list.
export const TERMINAL_STATUSES: readonly CardStatus[] = ["merged", "reverted", "rejected", "abandoned"];

export const MAX_BUILDS_PER_WEEK = 2;

export function isHeldoutVerdict(v: unknown): v is "pass" | "fail" {
  return v === "pass" || v === "fail";
}

export const SIZE_NAMES: Record<string, string> = { S: "small", M: "medium", L: "large" };

// ISO week of a UTC instant, formatted like pipeline.cards.iso_week ('2026-W42').
export function isoWeek(now: Date = new Date()): string {
  const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const dayFromMonday = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() + 3 - dayFromMonday); // the Thursday of this ISO week
  const year = d.getUTCFullYear();
  const dayOfYear = Math.round((d.getTime() - Date.UTC(year, 0, 1)) / 86_400_000);
  const week = Math.floor(dayOfYear / 7) + 1;
  return `${year}-W${String(week).padStart(2, "0")}`;
}

export function fmtNumber(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  return Number.isInteger(v) ? String(v) : String(Number(v.toFixed(4)));
}
