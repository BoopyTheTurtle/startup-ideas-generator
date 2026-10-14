import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { dbPath } from "@/lib/db";
import {
  cardOverview,
  latestMutationRun,
  metricCounts,
  type CardSummary,
  type MutationRun,
} from "@/lib/cards";
import {
  CARD_STATUSES,
  STATUS_INFO,
  TERMINAL_STATUSES,
  fmtNumber,
  type CardStatus,
} from "@/lib/cards-shared";
import { fmtDateTime, plural } from "@/lib/steering-shared";
import { NoDatabase, muted } from "@/components/ui";

export const metadata: Metadata = { title: "Improvement cards" };

export default function CardsPage() {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Improvement cards</h1>
      <p className={`mt-1 text-sm ${muted}`}>
        The weekly audit proposes changes to the tool; you approve or reject each one. A builder
        implements an approved card on its own branch, and nothing merges without your approval.
      </p>
      <Suspense fallback={<p className={`mt-4 text-sm ${muted}`}>Loading cards…</p>}>
        <Cards />
      </Suspense>
      <section aria-labelledby="instruments-heading" className="mt-12">
        <h2 id="instruments-heading" className="text-lg font-medium">
          Instrument checks
        </h2>
        <Suspense fallback={<p className={`mt-2 text-sm ${muted}`}>Loading checks…</p>}>
          <Instruments />
        </Suspense>
      </section>
    </main>
  );
}

// What Edgar owes this card, in words.
function needsYou(c: CardSummary): string[] {
  const out: string[] = [];
  if (c.status === "proposed") out.push("Decide: approve or reject");
  if ((c.status === "built" || c.status === "ready") && c.needs_heldout === 1 && c.heldout_check === "pending") {
    out.push("Record held-out check");
  }
  if (c.status === "ready" && c.review_verdict === "approve") {
    out.push(c.merge_approved_at ? "Merge approved; run the merge command" : "Approve merge");
  }
  return out;
}

async function Cards() {
  const data = await cardOverview();
  if (data === null) return <div className="mt-4"><NoDatabase path={dbPath()} /></div>;
  if (data === "no-tables") {
    return (
      <p className={`mt-4 text-sm ${muted}`}>
        This database predates the improvement-card tables. Run{" "}
        <code>uv run python -m pipeline migrate</code> from the repo root.
      </p>
    );
  }
  const { cards, counters } = data;
  const full = counters.builds >= counters.max;
  const byStatus = new Map<CardStatus, CardSummary[]>();
  for (const s of CARD_STATUSES) byStatus.set(s, []);
  for (const c of cards) byStatus.get(c.status as CardStatus)?.push(c);
  // Closed cards read newest first; open ones keep their rank order.
  for (const s of TERMINAL_STATUSES) byStatus.get(s)?.sort((a, b) => b.id - a.id);

  return (
    <>
      <section aria-labelledby="counters-heading" className="mt-6">
        <h2 id="counters-heading" className="sr-only">
          This week
        </h2>
        <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <Counter
            label={`Builds started in ${counters.week}`}
            value={`${counters.builds} of ${counters.max}`}
            note={full ? "Cap reached: the next approved card waits until next week." : "Revert cards do not count."}
            alert={full}
          />
          <Counter label="Awaiting your decision" value={String(counters.awaitingDecision)} />
          <Counter label="Awaiting a held-out check" value={String(counters.awaitingHeldout)} />
          <Counter label="Awaiting merge approval" value={String(counters.awaitingMerge)} />
        </dl>
      </section>
      {cards.length === 0 ? (
        <p className={`mt-8 text-sm ${muted}`}>
          No cards yet. The weekly audit writes them with <code>pipeline card-add</code>; they
          appear here as proposed.
        </p>
      ) : (
        <>
          {CARD_STATUSES.filter((s) => !TERMINAL_STATUSES.includes(s)).map((s) => {
            const rows = byStatus.get(s) ?? [];
            if (rows.length === 0) return null;
            return (
              <section key={s} aria-labelledby={`g-${s}`} className="mt-8">
                <h2 id={`g-${s}`} className="text-lg font-medium">
                  {STATUS_INFO[s].title} <span className={`font-normal ${muted}`}>({rows.length})</span>
                </h2>
                <p className={`text-sm ${muted}`}>{STATUS_INFO[s].blurb}</p>
                <CardTable status={s} rows={rows} />
              </section>
            );
          })}
          <section aria-labelledby="g-closed" className="mt-10">
            <h2 id="g-closed" className="text-lg font-medium">
              Closed cards
            </h2>
            <div className="mt-2 space-y-3">
              {TERMINAL_STATUSES.map((s) => {
                const rows = byStatus.get(s) ?? [];
                if (rows.length === 0) return null;
                return (
                  <details key={s} className="rounded border border-zinc-200 p-3 dark:border-zinc-800">
                    <summary className="cursor-pointer text-sm font-medium">
                      {STATUS_INFO[s].title} ({rows.length})
                    </summary>
                    <p className={`mt-2 text-sm ${muted}`}>{STATUS_INFO[s].blurb}</p>
                    <CardTable status={s} rows={rows} />
                  </details>
                );
              })}
              {TERMINAL_STATUSES.every((s) => (byStatus.get(s) ?? []).length === 0) && (
                <p className={`text-sm ${muted}`}>None yet.</p>
              )}
            </div>
          </section>
        </>
      )}
    </>
  );
}

function Counter({ label, value, note, alert }: { label: string; value: string; note?: string; alert?: boolean }) {
  return (
    <div className={`rounded border p-3 ${alert ? "border-amber-600 dark:border-amber-400" : "border-zinc-200 dark:border-zinc-800"}`}>
      <dt className={muted}>{label}</dt>
      <dd className="mt-1 text-xl font-semibold tabular-nums">{value}</dd>
      {note && <dd className={`mt-1 text-xs ${muted}`}>{note}</dd>}
    </div>
  );
}

function CardTable({ status, rows }: { status: CardStatus; rows: CardSummary[] }) {
  const title = STATUS_INFO[status].title;
  return (
    <div className="mt-2 overflow-x-auto" tabIndex={0} role="region" aria-label={`${title} cards table`}>
      <table className="w-full min-w-[44rem] text-left text-sm">
        <caption className="sr-only">
          {title} cards{" "}
          {TERMINAL_STATUSES.includes(status) ? "newest first" : "by rank, highest first"}
        </caption>
        <thead className={muted}>
          <tr>
            <th scope="col" className="py-2 pr-4 font-medium">Card</th>
            <th scope="col" className="py-2 pr-4 font-medium">Kind</th>
            <th scope="col" className="py-2 pr-4 font-medium">Touches</th>
            <th scope="col" className="py-2 pr-4 text-right font-medium">Size</th>
            <th scope="col" className="py-2 pr-4 text-right font-medium">Value</th>
            <th scope="col" className="py-2 pr-4 text-right font-medium">Rank</th>
            <th scope="col" className="py-2 pr-4 font-medium">Week</th>
            <th scope="col" className="py-2 font-medium">Needs you</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => {
            const need = needsYou(c);
            return (
              <tr key={c.id} className="border-t border-zinc-200 align-top dark:border-zinc-800">
                <th scope="row" className="py-2 pr-4 font-normal">
                  <Link href={`/cards/${c.id}`} className="font-medium underline-offset-2 hover:underline">
                    {c.title}
                  </Link>{" "}
                  <span className={`text-xs tabular-nums ${muted}`}>card {c.id}</span>
                  {c.reverts_card_id && (
                    <span className={`block text-xs ${muted}`}>reverts card {c.reverts_card_id}</span>
                  )}
                </th>
                <td className="py-2 pr-4">{c.kind}</td>
                <td className="py-2 pr-4">{c.touches}</td>
                <td className="py-2 pr-4 text-right">{c.size}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{c.value}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{c.rank_score.toFixed(2)}</td>
                <td className="py-2 pr-4 whitespace-nowrap tabular-nums">{c.week}</td>
                <td className="py-2 break-words">
                  {need.length === 0 ? <span className={muted}>–</span> : need.map((n) => <span key={n} className="block font-medium">{n}</span>)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

async function Instruments() {
  const [run, counts] = await Promise.all([latestMutationRun(), metricCounts()]);
  return (
    <>
      {counts && (
        <p className={`mt-1 text-sm ${muted}`}>
          The metrics table holds {plural(counts.values, "value")} for {plural(counts.metrics, "metric")}{" "}
          across {plural(counts.runs, "run")}.
        </p>
      )}
      {run === null ? (
        <p className={`mt-2 text-sm ${muted}`}>
          No mutation run yet. Each weekly audit injects known faults and checks that the metric
          meant to notice each one does. Results appear here after the first run.
        </p>
      ) : (
        <MutationResults run={run} />
      )}
    </>
  );
}

function MutationResults({ run }: { run: MutationRun }) {
  const missed = run.rows.filter((r) => r.caught === 0);
  return (
    <>
      <p className="mt-2 text-sm">
        <span className={missed.length > 0 ? "font-semibold text-red-700 dark:text-red-400" : "font-medium"}>
          {missed.length > 0
            ? `Warning: ${missed.length} of ${run.rows.length} injected faults went unnoticed.`
            : `All ${run.rows.length} injected faults were caught.`}
        </span>{" "}
        <span className={muted}>
          Run {run.run_id}, {fmtDateTime(run.started_at)} UTC. A metric that misses its fault is
          broken and gets a card of its own.
        </span>
      </p>
      <div className="mt-2 overflow-x-auto" tabIndex={0} role="region" aria-label="Instrument checks table">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <caption className="sr-only">
            Faults injected in mutation run {run.run_id}, missed faults first
          </caption>
          <thead className={muted}>
            <tr>
              <th scope="col" className="py-2 pr-4 font-medium">Fault</th>
              <th scope="col" className="py-2 pr-4 font-medium">Metric</th>
              <th scope="col" className="py-2 pr-4 font-medium">Should move</th>
              <th scope="col" className="py-2 pr-4 font-medium">Baseline to mutated</th>
              <th scope="col" className="py-2 font-medium">Caught</th>
            </tr>
          </thead>
          <tbody>
            {run.rows.map((r) => {
              const miss = r.caught === 0;
              return (
                <tr
                  key={r.id}
                  className={`border-t align-top ${
                    miss
                      ? "border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40"
                      : "border-zinc-200 dark:border-zinc-800"
                  }`}
                >
                  <th scope="row" className="py-2 pr-4 font-normal break-words">
                    <span className={miss ? "font-semibold" : ""}>{r.name}</span>
                    {r.detail && <span className={`block text-xs ${muted}`}>{r.detail}</span>}
                  </th>
                  <td className="py-2 pr-4 break-words">
                    {r.metric}
                    {r.subject && <span className={`block text-xs ${muted}`}>{r.subject}</span>}
                  </td>
                  <td className="py-2 pr-4">{r.direction}</td>
                  <td className="py-2 pr-4 whitespace-nowrap tabular-nums">
                    {fmtNumber(r.baseline)} → {fmtNumber(r.mutated)}
                  </td>
                  <td className="py-2">
                    {miss ? (
                      <span className="font-semibold text-red-800 dark:text-red-300">
                        <span aria-hidden="true">✗ </span>MISSED
                      </span>
                    ) : (
                      <span className="text-green-800 dark:text-green-300">
                        <span aria-hidden="true">✓ </span>yes
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
