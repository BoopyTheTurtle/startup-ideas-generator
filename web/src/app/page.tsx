import { Suspense } from "react";
import { dbPath, recentRuns } from "@/lib/db";

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

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Startup ideas generator</h1>
      <p className="mt-1 text-sm text-zinc-500">Pipeline runs</p>
      <div className="mt-6 overflow-x-auto">
        <Suspense fallback={<p className="text-sm text-zinc-500">Loading runs…</p>}>
          <Runs />
        </Suspense>
      </div>
    </main>
  );
}
