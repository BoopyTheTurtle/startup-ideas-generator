"use client";

// Mentions and distinct authors per map run, on one count axis. Legend above, end
// labels where the lines separate, a crosshair tooltip on hover or arrow keys, and the
// table view beside it (rendered by the page) carries every value without hovering.
import { useEffect, useRef, useState } from "react";

export type ChartPoint = { run_id: number; date: string; mentions: number; authors: number };

const SERIES = [
  { key: "authors", label: "Distinct authors", color: "var(--series-1)" },
  { key: "mentions", label: "Mentions", color: "var(--series-2)" },
] as const;

const H = 200;
const M = { top: 12, right: 40, bottom: 28, left: 32 };

function niceMax(v: number): number {
  if (v <= 4) return 4;
  const step = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * step >= v) return m * step;
  return 10 * step;
}

export function SnapshotChart({ points }: { points: ChartPoint[] }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(240, entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (points.length === 0) {
    return <p className="text-sm text-zinc-600 dark:text-zinc-400">No snapshots yet.</p>;
  }

  const max = niceMax(Math.max(...points.map((p) => Math.max(p.mentions, p.authors))));
  const ticks = [0, max / 2, max];
  const innerW = width - M.left - M.right;
  const innerH = H - M.top - M.bottom;
  const x = (i: number) =>
    M.left + (points.length === 1 ? innerW / 2 : (i * innerW) / (points.length - 1));
  const y = (v: number) => M.top + innerH - (v / max) * innerH;
  const path = (key: "authors" | "mentions") =>
    points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join("");

  const last = points[points.length - 1];
  const lastI = points.length - 1;
  const endGap = Math.abs(y(last.authors) - y(last.mentions));
  const labelEnds = endGap >= 14;
  // Thin the x labels so they never collide (about 56px each).
  const every = Math.max(1, Math.ceil((points.length * 56) / innerW));

  function nearest(clientX: number, svg: SVGSVGElement) {
    const rect = svg.getBoundingClientRect();
    const px = clientX - rect.left;
    let best = 0;
    for (let i = 1; i < points.length; i++) if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i;
    return best;
  }

  const a = active === null ? null : points[active];
  const tipLeft = active === null ? 0 : Math.min(Math.max(x(active) - 70, 0), width - 150);

  return (
    <div>
      <ul className="flex flex-wrap gap-4 text-sm" aria-label="Legend">
        {SERIES.map((s) => (
          <li key={s.key} className="flex items-center gap-2">
            <svg width="16" height="8" aria-hidden="true">
              <line x1="0" x2="16" y1="4" y2="4" stroke={s.color} strokeWidth="2" strokeLinecap="round" />
            </svg>
            {s.label}
          </li>
        ))}
      </ul>
      {points.every((p) => p.mentions === p.authors) && (
        <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
          Every mention so far comes from a different author, so the two lines coincide.
        </p>
      )}
      <div ref={wrap} className="relative mt-2 w-full">
        <svg
          // Scales to the container until measured, then draws 1:1 at the measured width.
          width="100%"
          viewBox={`0 0 ${width} ${H}`}
          role="img"
          aria-label={`Mentions and distinct authors over ${points.length} map runs; latest ${last.mentions} mentions, ${last.authors} distinct authors. Use the left and right arrow keys to read each run.`}
          tabIndex={0}
          className="block touch-pan-y"
          onPointerMove={(e) => setActive(nearest(e.clientX, e.currentTarget))}
          onPointerLeave={() => setActive(null)}
          onFocus={() => setActive((v) => v ?? lastI)}
          onBlur={() => setActive(null)}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") setActive((v) => Math.max(0, (v ?? lastI) - 1));
            else if (e.key === "ArrowRight") setActive((v) => Math.min(lastI, (v ?? lastI) + 1));
            else return;
            e.preventDefault();
          }}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line
                x1={M.left}
                x2={width - M.right}
                y1={y(t)}
                y2={y(t)}
                stroke={t === 0 ? "var(--chart-axis)" : "var(--chart-grid)"}
                strokeWidth={1}
              />
              <text
                x={M.left - 6}
                y={y(t)}
                textAnchor="end"
                dominantBaseline="middle"
                fontSize="11"
                fill="var(--chart-ink-muted)"
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {Number.isInteger(t) ? t : t.toFixed(1)}
              </text>
            </g>
          ))}
          {points.map((p, i) =>
            i % every === 0 || i === lastI ? (
              <text
                key={p.run_id}
                x={x(i)}
                y={H - 8}
                textAnchor={points.length === 1 ? "middle" : i === 0 ? "start" : i === lastI ? "end" : "middle"}
                fontSize="11"
                fill="var(--chart-ink-muted)"
              >
                {p.date.slice(5, 10)}
              </text>
            ) : null,
          )}
          {active !== null && (
            <line
              x1={x(active)}
              x2={x(active)}
              y1={M.top}
              y2={M.top + innerH}
              stroke="var(--chart-axis)"
              strokeWidth={1}
            />
          )}
          {/* Mentions first, so authors (the measure that counts people) draws on top. */}
          {[...SERIES].reverse().map((s) => (
            <g key={s.key}>
              {points.length > 1 && (
                <path
                  d={path(s.key)}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              )}
              {(points.length === 1 || active !== null) && (
                <circle
                  cx={x(active ?? lastI)}
                  cy={y(points[active ?? lastI][s.key])}
                  r={4}
                  fill={s.color}
                  stroke="var(--background)"
                  strokeWidth={2}
                />
              )}
            </g>
          ))}
          {labelEnds &&
            SERIES.map((s) => (
              <text
                key={s.key}
                x={x(lastI) + 8}
                y={y(last[s.key])}
                dominantBaseline="middle"
                fontSize="12"
                fill="currentColor"
              >
                {last[s.key]}
              </text>
            ))}
        </svg>
        {a && (
          <div
            className="pointer-events-none absolute top-0 w-[150px] rounded border border-zinc-200 bg-white p-2 text-xs shadow-sm dark:border-zinc-700 dark:bg-zinc-900"
            style={{ left: tipLeft }}
            aria-live="polite"
          >
            <p className="text-zinc-600 dark:text-zinc-400">
              run {a.run_id} · {a.date.slice(0, 10)}
            </p>
            {SERIES.map((s) => (
              <p key={s.key} className="mt-1 flex items-center gap-2">
                <svg width="12" height="8" aria-hidden="true">
                  <line x1="0" x2="12" y1="4" y2="4" stroke={s.color} strokeWidth="2" />
                </svg>
                <span className="font-semibold tabular-nums">{a[s.key]}</span>
                <span className="text-zinc-600 dark:text-zinc-400">{s.label.toLowerCase()}</span>
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
