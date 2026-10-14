import { Suspense } from "react";
import { collectorHealth, dbPath, STALE_DAYS } from "@/lib/db";
import { runsWithCost } from "@/lib/radar";
import { fmtDateTime, fmtDuration, fmtUsd } from "@/lib/steering-shared";
import { NoDatabase, muted } from "@/components/ui";

export default function RunsPage() {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
      <section aria-labelledby="runs-heading" className="mt-6">
        <h2 id="runs-heading" className="text-lg font-medium">
          Pipeline runs
        </h2>
        <Suspense fallback={<p className={`mt-2 text-sm ${muted}`}>Loading runs…</p>}>
          <Runs />
        </Suspense>
      </section>
      <section aria-labelledby="health-heading" className="mt-10">
        <h2 id="health-heading" className="text-lg font-medium">
          Collector health
        </h2>
        <Suspense fallback={<p className={`mt-2 text-sm ${muted}`}>Loading health…</p>}>
          <Health />
        </Suspense>
      </section>
    </main>
  );
}

const STATUS_CLASS: Record<string, string> = {
  ok: "text-green-700 dark:text-green-400",
  failed: "font-medium text-red-700 dark:text-red-400",
};

async function Runs() {
  const data = await runsWithCost(50);
  if (data === null) return <NoDatabase path={dbPath()} />;
  const { runs, cost30d } = data;
  if (runs.length === 0) return <p className={`mt-2 text-sm ${muted}`}>No runs yet.</p>;
  return (
    <>
      <p className={`mt-1 text-sm ${muted}`}>
        Latest {runs.length} runs. LLM cost sums each run&apos;s <code>*cost_usd*</code> metrics:{" "}
        <span className="tabular-nums">{fmtUsd(cost30d)}</span> in the last 30 days (as reported by{" "}
        <code>claude -p</code>).
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className={muted}>
            <tr>
              <th scope="col" className="py-2 pr-4 font-medium">Run</th>
              <th scope="col" className="py-2 pr-4 font-medium">Kind</th>
              <th scope="col" className="py-2 pr-4 font-medium">Status</th>
              <th scope="col" className="py-2 pr-4 font-medium">Started (UTC)</th>
              <th scope="col" className="py-2 pr-4 text-right font-medium">Duration</th>
              <th scope="col" className="py-2 pr-4 text-right font-medium">LLM cost</th>
              <th scope="col" className="py-2 font-medium">Note</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} className="border-t border-zinc-200 align-top dark:border-zinc-800">
                <td className="py-2 pr-4 tabular-nums">{r.id}</td>
                <td className="py-2 pr-4">{r.kind}</td>
                <td className={`py-2 pr-4 ${STATUS_CLASS[r.status] ?? muted}`}>{r.status}</td>
                <td className="py-2 pr-4 whitespace-nowrap tabular-nums">{fmtDateTime(r.started_at)}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{fmtDuration(r.started_at, r.finished_at)}</td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {r.cost_usd === null ? "–" : fmtUsd(r.cost_usd)}
                </td>
                <td className={`py-2 break-words ${muted}`}>{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

async function Health() {
  const rows = await collectorHealth();
  if (!rows || rows.length === 0) {
    return <p className={`mt-2 text-sm ${muted}`}>No collector has run yet.</p>;
  }
  return (
    <>
      <p className={`mt-1 text-sm ${muted}`}>
        Stale means no successful run in {STALE_DAYS} days.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className={muted}>
            <tr>
              <th scope="col" className="py-2 pr-4 font-medium">Source</th>
              <th scope="col" className="py-2 pr-4 font-medium">Status</th>
              <th scope="col" className="py-2 pr-4 font-medium">Last success (UTC)</th>
              <th scope="col" className="py-2 pr-4 text-right font-medium">Failures in a row</th>
              <th scope="col" className="py-2 pr-4 text-right font-medium">New last run</th>
              <th scope="col" className="py-2 pr-4 text-right font-medium">Stored</th>
              <th scope="col" className="py-2 font-medium">Last error</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((h) => {
              const bad = h.last_status !== "ok" || h.stale === 1;
              return (
                <tr key={h.source} className="border-t border-zinc-200 align-top dark:border-zinc-800">
                  <td className="py-2 pr-4">{h.source}</td>
                  <td
                    className={`py-2 pr-4 ${bad ? "font-medium text-red-700 dark:text-red-400" : "text-green-700 dark:text-green-400"}`}
                  >
                    {h.stale === 1 && h.last_status === "ok" ? "stale" : h.last_status}
                  </td>
                  <td className="py-2 pr-4 whitespace-nowrap tabular-nums">
                    {h.last_success_at ? fmtDateTime(h.last_success_at) : "never"}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">{h.consecutive_failures}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{h.items_last_run}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{h.total_items}</td>
                  <td className={`py-2 break-words text-xs ${muted}`}>{h.last_error ?? ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
