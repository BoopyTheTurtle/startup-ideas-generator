// A single-series sparkline drawn on the server: one 2px line in series-1, an end dot
// with a surface ring, and the latest value as text in ink beside it. Each point carries
// a native tooltip; the problem page has the full table.
import { TREND_MIN_SNAPSHOTS } from "@/lib/steering-shared";

type Point = { run_id: number; value: number };

const W = 88;
const H = 28;
const PAD = 5; // room for the end dot and its ring

export function Sparkline({ points, label }: { points: Point[]; label: string }) {
  if (points.length === 0) {
    return <span className="text-xs text-zinc-600 dark:text-zinc-400">no snapshots</span>;
  }
  const max = Math.max(1, ...points.map((p) => p.value));
  const x = (i: number) =>
    points.length === 1 ? W - PAD : PAD + (i * (W - 2 * PAD)) / (points.length - 1);
  const y = (v: number) => H - PAD - (v / max) * (H - 2 * PAD);
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
  const last = points[points.length - 1];
  const summary = `${label}: ${points.map((p) => `run ${p.run_id} ${p.value}`).join(", ")}`;
  const slot = (W - 2 * PAD) / Math.max(1, points.length - 1);
  return (
    <span className="inline-flex items-center gap-2">
      <svg
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={summary}
        className="shrink-0 overflow-visible"
      >
        <line x1={PAD} x2={W - PAD} y1={H - PAD} y2={H - PAD} stroke="var(--chart-axis)" strokeWidth={1} />
        {points.length > 1 && (
          <path d={d} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        )}
        <circle
          cx={x(points.length - 1)}
          cy={y(last.value)}
          r={4}
          fill="var(--series-1)"
          stroke="var(--background)"
          strokeWidth={2}
        />
        {points.map((p, i) => (
          <rect
            key={p.run_id}
            x={x(i) - slot / 2}
            y={0}
            width={points.length === 1 ? 2 * PAD : slot}
            height={H}
            fill="transparent"
          >
            <title>{`run ${p.run_id}: ${p.value} ${label.toLowerCase()}`}</title>
          </rect>
        ))}
      </svg>
      <span className="text-sm tabular-nums">{last.value}</span>
      {points.length < TREND_MIN_SNAPSHOTS && (
        <span className="text-xs text-zinc-600 dark:text-zinc-400">
          insufficient data ({points.length}/{TREND_MIN_SNAPSHOTS})
        </span>
      )}
    </span>
  );
}
