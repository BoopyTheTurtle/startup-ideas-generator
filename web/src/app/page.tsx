import { Suspense } from "react";
import { collectorHealth, dbPath, recentRuns } from "@/lib/db";

async function Runs() {
  const runs = await recentRuns();
  if (runs === null) {
    return (
      <p className="text-sm text-zinc-500">
        No database at <code>{dbPath()}</code>. Run{" "}
        <code>uv run python -m pipeline smoke</code> from the repo root.
      </p>
    );
  }
  if (runs.length === 0) {
    return <p className="text-sm text-zinc-500">No runs yet.</p>;
  }
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-zinc-500">
        <tr>
          <th className="py-2 pr-4 font-medium">Run</th>
          <th className="py-2 pr-4 font-medium">Kind</th>
          <th className="py-2 pr-4 font-medium">Status</th>
          <th className="py-2 pr-4 font-medium">Started (UTC)</th>
          <th className="py-2 pr-4 font-medium">Metrics</th>
          <th className="py-2 font-medium">Note</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((r) => (
          <tr key={r.id} className="border-t border-zinc-200 dark:border-zinc-800">
            <td className="py-2 pr-4 tabular-nums">{r.id}</td>
            <td className="py-2 pr-4">{r.kind}</td>
            <td className="py-2 pr-4">
              <span
                className={
                  r.status === "ok"
                    ? "text-green-700 dark:text-green-400"
                    : r.status === "failed"
                      ? "text-red-700 dark:text-red-400"
                      : "text-zinc-500"
                }
              >
                {r.status}
              </span>
            </td>
            <td className="py-2 pr-4 tabular-nums">{r.started_at.replace("T", " ").slice(0, 19)}</td>
            <td className="py-2 pr-4 tabular-nums">{r.metric_count}</td>
            <td className="py-2 text-zinc-500">{r.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

async function Health() {
  const rows = await collectorHealth();
  if (!rows || rows.length === 0) {
    return <p className="text-sm text-zinc-500">No collector has run yet.</p>;
  }
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-zinc-500">
        <tr>
          <th className="py-2 pr-4 font-medium">Source</th>
          <th className="py-2 pr-4 font-medium">Status</th>
          <th className="py-2 pr-4 font-medium">Last success (UTC)</th>
          <th className="py-2 pr-4 font-medium">Failures in a row</th>
          <th className="py-2 pr-4 font-medium">New last run</th>
          <th className="py-2 font-medium">Stored</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((h) => {
          const bad = h.last_status !== "ok" || h.stale === 1;
          return (
            <tr key={h.source} className="border-t border-zinc-200 dark:border-zinc-800">
              <td className="py-2 pr-4">{h.source}</td>
              <td
                className={`py-2 pr-4 ${bad ? "font-medium text-red-700 dark:text-red-400" : "text-green-700 dark:text-green-400"}`}
                title={h.last_error ?? undefined}
              >
                {h.stale === 1 && h.last_status === "ok" ? "stale" : h.last_status}
              </td>
              <td className="py-2 pr-4 tabular-nums">
                {h.last_success_at?.replace("T", " ").slice(0, 16) ?? "never"}
              </td>
              <td className="py-2 pr-4 tabular-nums">{h.consecutive_failures}</td>
              <td className="py-2 pr-4 tabular-nums">{h.items_last_run}</td>
              <td className="py-2 tabular-nums">{h.total_items}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Startup ideas generator</h1>
      <h2 className="mt-8 text-lg font-medium">Collector health</h2>
      <div className="mt-2 overflow-x-auto">
        <Suspense fallback={<p className="text-sm text-zinc-500">Loading health…</p>}>
          <Health />
        </Suspense>
      </div>
      <h2 className="mt-8 text-lg font-medium">Pipeline runs</h2>
      <div className="mt-2 overflow-x-auto">
        <Suspense fallback={<p className="text-sm text-zinc-500">Loading runs…</p>}>
          <Runs />
        </Suspense>
      </div>
    </main>
  );
}
