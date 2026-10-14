// Improvement cards (SPEC stage 8): reads for /cards and the writes that are Edgar's alone.
// Python owns the schema and every other transition (migration 007, pipeline/cards.py).
// The app writes exactly four kinds of change, each in one BEGIN IMMEDIATE transaction that
// re-checks the card's status first, records a card_event as 'edgar', and leans on the
// status trigger as a backstop:
//   approve / reject      proposed -> approved | rejected
//   merge approval        sets (or withdraws) merge_approved_at on a ready card
//   held-out check        sets heldout_check to pass or fail, nothing else
// The held-out comparison itself happens outside the app; the app never reads the
// held-out set or any result from it.
import { connection } from "next/server";
import type { DatabaseSync } from "node:sqlite";
import { open } from "@/lib/db";
import { MAX_BUILDS_PER_WEEK, isoWeek } from "@/lib/cards-shared";
import { REASONS, type ReasonCode } from "@/lib/steering-shared";

export type CardResult = { ok: boolean; message: string };

const NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')";

export type CardRow = {
  id: number;
  created_run_id: number;
  week: string;
  kind: string;
  touches: string;
  title: string;
  observation: string;
  evidence_json: string;
  hypothesis: string;
  change: string;
  expected_effect: string;
  expected_metric: string | null;
  expected_subject: string;
  expected_direction: string | null;
  risk: string;
  size: string;
  value: number;
  rank_score: number;
  dedupe_key: string;
  reverts_card_id: number | null;
  proposed_by: string;
  status: string;
  decided_at: string | null;
  decision_reason: string | null;
  decision_note: string | null;
  build_week: string | null;
  branch: string | null;
  worktree_path: string | null;
  base_branch: string | null;
  base_sha: string | null;
  base_extract_version: string | null;
  head_sha: string | null;
  verify_json: string | null;
  needs_heldout: number;
  heldout_check: string;
  review_verdict: string | null;
  review_notes: string | null;
  merge_approved_at: string | null;
  merged_at: string | null;
  merged_sha: string | null;
  baseline_json: string | null;
  created_at: string;
  updated_at: string;
};

export type CardSummary = Pick<
  CardRow,
  | "id" | "title" | "status" | "kind" | "touches" | "size" | "value" | "rank_score" | "week"
  | "needs_heldout" | "heldout_check" | "review_verdict" | "merge_approved_at" | "reverts_card_id"
>;

export type CardEvent = { id: number; at: string; actor: string; event: string; note: string | null };

export type Evidence = { metric: string; subject: string; value: string; run_id: string };

export type Verify = {
  head?: string;
  changed?: string[];
  needs_heldout?: boolean;
  problems: string[];
  tests?: { passed: boolean; tail: string };
  eval_diff?: {
    base_version: string | null;
    base_f1: number | null;
    candidate_version: string | null;
    candidate_f1: number | null;
  };
};

export type Baseline = {
  metric: string;
  subject: string;
  value: number;
  run_id: number;
  direction: string | null;
};

export type CardDetail = {
  card: CardRow;
  evidence: Evidence[];
  verify: Verify | null;
  baseline: Baseline | null;
  events: CardEvent[];
  reverts: { id: number; title: string; status: string } | null;
  revertedBy: { id: number; title: string; status: string }[];
  buildsThisWeek: number;
  week: string;
};

export type CardCounters = {
  week: string;
  builds: number;
  max: number;
  awaitingDecision: number;
  awaitingHeldout: number;
  awaitingMerge: number;
};

export type MutationRow = {
  id: number;
  name: string;
  metric: string;
  subject: string;
  direction: string;
  baseline: number | null;
  mutated: number | null;
  caught: number;
  detail: string | null;
};

export type MutationRun = {
  run_id: number;
  started_at: string;
  status: string;
  rows: MutationRow[];
};

export type MetricCounts = { values: number; metrics: number; runs: number };

function conn(): DatabaseSync | null {
  return open();
}

function hasCardTables(c: DatabaseSync): boolean {
  const row = c
    .prepare("SELECT COUNT(*) AS n FROM sqlite_master WHERE type = 'table' AND name IN ('improvement_card', 'card_event')")
    .get() as { n: number };
  return row.n === 2;
}

function hasTable(c: DatabaseSync, name: string): boolean {
  return Boolean(c.prepare("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?").get(name));
}

function parseJson<T>(text: string | null): T | null {
  if (!text) return null;
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

// Evidence entries come from an agent: coerce every field to text before display.
function parseEvidence(text: string): Evidence[] {
  const raw = parseJson<unknown>(text);
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((e): e is Record<string, unknown> => typeof e === "object" && e !== null)
    .map((e) => ({
      metric: String(e.metric ?? ""),
      subject: String(e.subject ?? ""),
      value: e.value === undefined || e.value === null ? "" : String(e.value),
      run_id: e.run_id === undefined || e.run_id === null ? "" : String(e.run_id),
    }));
}

function parseVerify(text: string | null): Verify | null {
  const v = parseJson<Record<string, unknown>>(text);
  if (!v || typeof v !== "object") return null;
  const problems = Array.isArray(v.problems) ? v.problems.map(String) : [];
  const out: Verify = { problems };
  if (typeof v.head === "string") out.head = v.head;
  if (Array.isArray(v.changed)) out.changed = v.changed.map(String);
  if (typeof v.needs_heldout === "boolean") out.needs_heldout = v.needs_heldout;
  const t = v.tests as { passed?: unknown; tail?: unknown } | undefined;
  if (t && typeof t === "object") out.tests = { passed: t.passed === true, tail: String(t.tail ?? "") };
  const d = v.eval_diff as Record<string, unknown> | undefined;
  if (d && typeof d === "object") {
    const num = (x: unknown) => (typeof x === "number" ? x : null);
    out.eval_diff = {
      base_version: d.base_version == null ? null : String(d.base_version),
      base_f1: num(d.base_f1),
      candidate_version: d.candidate_version == null ? null : String(d.candidate_version),
      candidate_f1: num(d.candidate_f1),
    };
  }
  return out;
}

// --- Reads (the driver is synchronous, so connection() keeps them out of prerendering) ----

// null: no database. undefined cards: the database predates migration 007.
export async function cardOverview(): Promise<{
  cards: CardSummary[];
  counters: CardCounters;
} | null | "no-tables"> {
  await connection();
  const c = conn();
  if (!c) return null;
  if (!hasCardTables(c)) return "no-tables";
  const cards = c
    .prepare(
      `SELECT id, title, status, kind, touches, size, value, rank_score, week, needs_heldout,
              heldout_check, review_verdict, merge_approved_at, reverts_card_id
         FROM improvement_card ORDER BY rank_score DESC, id DESC`,
    )
    .all() as CardSummary[];
  const week = isoWeek();
  const builds = (
    c
      .prepare("SELECT COUNT(*) AS n FROM improvement_card WHERE build_week = ? AND kind != 'revert'")
      .get(week) as { n: number }
  ).n;
  const heldoutOpen = (x: CardSummary) =>
    x.needs_heldout === 1 && x.heldout_check === "pending" && (x.status === "built" || x.status === "ready");
  return {
    cards,
    counters: {
      week,
      builds,
      max: MAX_BUILDS_PER_WEEK,
      awaitingDecision: cards.filter((x) => x.status === "proposed").length,
      awaitingHeldout: cards.filter(heldoutOpen).length,
      awaitingMerge: cards.filter(
        (x) => x.status === "ready" && x.review_verdict === "approve" && !x.merge_approved_at,
      ).length,
    },
  };
}

export async function cardDetail(id: number): Promise<CardDetail | null> {
  await connection();
  const c = conn();
  if (!c || !hasCardTables(c)) return null;
  const card = c.prepare("SELECT * FROM improvement_card WHERE id = ?").get(id) as CardRow | undefined;
  if (!card) return null;
  const events = c
    .prepare("SELECT id, at, actor, event, note FROM card_event WHERE card_id = ? ORDER BY id")
    .all(id) as CardEvent[];
  const reverts = card.reverts_card_id
    ? ((c
        .prepare("SELECT id, title, status FROM improvement_card WHERE id = ?")
        .get(card.reverts_card_id) as { id: number; title: string; status: string } | undefined) ?? null)
    : null;
  const revertedBy = c
    .prepare("SELECT id, title, status FROM improvement_card WHERE reverts_card_id = ? ORDER BY id")
    .all(id) as { id: number; title: string; status: string }[];
  const week = isoWeek();
  const buildsThisWeek = (
    c
      .prepare("SELECT COUNT(*) AS n FROM improvement_card WHERE build_week = ? AND kind != 'revert'")
      .get(week) as { n: number }
  ).n;
  return {
    card,
    evidence: parseEvidence(card.evidence_json),
    verify: parseVerify(card.verify_json),
    baseline: parseJson<Baseline>(card.baseline_json),
    events,
    reverts,
    revertedBy,
    buildsThisWeek,
    week,
  };
}

// The newest run that logged mutation rows.
export async function latestMutationRun(): Promise<MutationRun | null> {
  await connection();
  const c = conn();
  if (!c || !hasTable(c, "mutation")) return null;
  const run = c
    .prepare(
      `SELECT r.id AS run_id, r.started_at, r.status
         FROM mutation m JOIN run r ON r.id = m.run_id
        GROUP BY r.id ORDER BY r.id DESC LIMIT 1`,
    )
    .get() as { run_id: number; started_at: string; status: string } | undefined;
  if (!run) return null;
  const rows = c
    .prepare(
      `SELECT id, name, metric, subject, direction, baseline, mutated, caught, detail
         FROM mutation WHERE run_id = ? ORDER BY caught, id`,
    )
    .all(run.run_id) as MutationRow[];
  return { ...run, rows };
}

export async function metricCounts(): Promise<MetricCounts | null> {
  await connection();
  const c = conn();
  if (!c) return null;
  if (!hasTable(c, "metric")) return { values: 0, metrics: 0, runs: 0 };
  const row = c
    .prepare(
      `SELECT COUNT(*) AS values_, COUNT(DISTINCT layer || '.' || name) AS metrics,
              COUNT(DISTINCT run_id) AS runs FROM metric`,
    )
    .get() as { values_: number; metrics: number; runs: number };
  return { values: row.values_, metrics: row.metrics, runs: row.runs };
}

// --- Writes ---------------------------------------------------------------------------------

function tx<T>(c: DatabaseSync, fn: () => T): T {
  c.exec("BEGIN IMMEDIATE");
  try {
    const out = fn();
    c.exec("COMMIT");
    return out;
  } catch (e) {
    c.exec("ROLLBACK");
    throw e;
  }
}

// The status trigger's messages are written for Python callers; translate the ones a stale
// page can reach into plain words.
function friendly(e: unknown): string {
  const text = e instanceof Error ? e.message : String(e);
  if (/illegal improvement_card status change/.test(text)) {
    return "The database refused that status change; the card has moved on. Reload the page.";
  }
  if (/merge needs Edgar/.test(text)) {
    return "The database refused it: a merge needs your merge approval and a cleared held-out check.";
  }
  if (/never approved/.test(text)) return "The database refused it: the card was never approved.";
  if (/ready needs a review verdict/.test(text)) return "The database refused it: the review verdict is not approve.";
  if (/locked|busy/i.test(text)) return "The database is busy (a pipeline command holds it). Try again in a moment.";
  return `Not saved: ${text}`;
}

function guard(fn: (c: DatabaseSync) => CardResult): CardResult {
  const c = conn();
  if (!c) return { ok: false, message: "No database." };
  try {
    return tx(c, () => fn(c));
  } catch (e) {
    return { ok: false, message: friendly(e) };
  }
}

function event(c: DatabaseSync, id: number, name: string, note: string | null): void {
  c.prepare("INSERT INTO card_event (card_id, actor, event, note) VALUES (?, 'edgar', ?, ?)").run(
    id,
    name,
    note,
  );
}

type Current = {
  id: number;
  status: string;
  review_verdict: string | null;
  merge_approved_at: string | null;
  needs_heldout: number;
  heldout_check: string;
};

function current(c: DatabaseSync, id: number): Current | null {
  return (
    (c
      .prepare(
        "SELECT id, status, review_verdict, merge_approved_at, needs_heldout, heldout_check FROM improvement_card WHERE id = ?",
      )
      .get(id) as Current | undefined) ?? null
  );
}

const missing = (id: number): CardResult => ({ ok: false, message: `Card ${id} does not exist.` });

export function decideCard(
  id: number,
  decision: "approve" | "reject",
  reason: ReasonCode,
  note: string,
): CardResult {
  return guard((c) => {
    const card = current(c, id);
    if (!card) return missing(id);
    if (card.status !== "proposed") {
      return { ok: false, message: `Card ${id} is ${card.status}, not proposed; nothing changed.` };
    }
    const status = decision === "approve" ? "approved" : "rejected";
    // updated_at matters on a rejection: the auditor's cooldown counts days from it.
    c.prepare(
      `UPDATE improvement_card SET status = ?, decided_at = ${NOW}, decision_reason = ?,
              decision_note = ?, updated_at = ${NOW} WHERE id = ? AND status = 'proposed'`,
    ).run(status, reason, note || null, id);
    const label = REASONS.find((r) => r.code === reason)?.label ?? reason;
    event(c, id, status, note ? `${label} | ${note}` : label);
    return { ok: true, message: `Card ${id} ${status}.` };
  });
}

export function setMergeApproval(id: number, approved: boolean): CardResult {
  return guard((c) => {
    const card = current(c, id);
    if (!card) return missing(id);
    if (card.status !== "ready") {
      return { ok: false, message: `Card ${id} is ${card.status}, not ready; nothing changed.` };
    }
    if (approved) {
      if (card.review_verdict !== "approve") {
        return { ok: false, message: `Card ${id} has no approving review; nothing changed.` };
      }
      if (card.merge_approved_at) {
        return { ok: false, message: `The merge of card ${id} is already approved.` };
      }
      c.prepare(
        `UPDATE improvement_card SET merge_approved_at = ${NOW}, updated_at = ${NOW}
          WHERE id = ? AND status = 'ready'`,
      ).run(id);
      event(c, id, "merge approved", null);
      return { ok: true, message: `Merge of card ${id} approved.` };
    }
    if (!card.merge_approved_at) {
      return { ok: false, message: `The merge of card ${id} is not approved; nothing to withdraw.` };
    }
    c.prepare(
      `UPDATE improvement_card SET merge_approved_at = NULL, updated_at = ${NOW}
        WHERE id = ? AND status = 'ready'`,
    ).run(id);
    event(c, id, "merge approval withdrawn", null);
    return { ok: true, message: `Merge approval for card ${id} withdrawn.` };
  });
}

// Records Edgar's verdict from a comparison he ran himself. Touches heldout_check only.
export function recordHeldoutCheck(id: number, verdict: "pass" | "fail"): CardResult {
  return guard((c) => {
    const card = current(c, id);
    if (!card) return missing(id);
    if (card.needs_heldout !== 1) {
      return { ok: false, message: `Card ${id} does not need a held-out check; nothing changed.` };
    }
    if (card.status !== "built" && card.status !== "ready") {
      return { ok: false, message: `Card ${id} is ${card.status}; the check is recorded on a built or ready card.` };
    }
    if (card.heldout_check === verdict) {
      return { ok: false, message: `The held-out check on card ${id} is already ${verdict}.` };
    }
    c.prepare("UPDATE improvement_card SET heldout_check = ? WHERE id = ? AND status IN ('built', 'ready')").run(
      verdict,
      id,
    );
    event(c, id, `held-out check: ${verdict}`, null);
    return { ok: true, message: `Held-out check on card ${id} recorded as ${verdict}.` };
  });
}
