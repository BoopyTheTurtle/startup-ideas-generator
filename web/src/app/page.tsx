import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { collectorHealth, dbPath } from "@/lib/db";
import {
  STATUS_FILTERS,
  currentThemes,
  problemSources,
  radarProblems,
  type RadarFilter,
  type ThemeWithDetail,
} from "@/lib/radar";
import { TREND_MIN_SNAPSHOTS, fmtDate, fmtDateTime, plural } from "@/lib/steering-shared";
import { QuoteSnippet } from "@/components/quote-card";
import { Sparkline } from "@/components/sparkline";
import { ModelNamed, NoDatabase, StatusBadge, buttonSecondary, card, input, muted } from "@/components/ui";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

// The layout's title template applies to child segments only, not to this page.
export const metadata: Metadata = { title: { absolute: "Radar · Startup ideas generator" } };

export default function Radar({ searchParams }: { searchParams: SearchParams }) {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Radar</h1>
      <p className={`mt-1 text-sm ${muted}`}>
        Browse broad themes, drill into problems and the quotes behind them, then steer. Labeling
        for the eval set lives at <Link href="/label" className="underline">/label</Link>.
      </p>
      <Suspense fallback={null}>
        <HealthBanner />
      </Suspense>
      <section aria-labelledby="themes-heading" className="mt-8">
        <h2 id="themes-heading" className="text-lg font-medium">
          Themes
        </h2>
        <Suspense fallback={<p className={`mt-2 text-sm ${muted}`}>Loading themes…</p>}>
          <Themes />
        </Suspense>
      </section>
      <section aria-labelledby="problems-heading" className="mt-10">
        <h2 id="problems-heading" className="text-lg font-medium">
          Problems
        </h2>
        <Suspense fallback={<p className={`mt-2 text-sm ${muted}`}>Loading problems…</p>}>
          <Problems searchParams={searchParams} />
        </Suspense>
      </section>
    </main>
  );
}

// Only collectors that need attention; the full table lives on /runs.
async function HealthBanner() {
  const rows = await collectorHealth();
  if (!rows || rows.length === 0) return null;
  const bad = rows.filter((h) => h.last_status !== "ok" || h.stale === 1);
  if (bad.length === 0) {
    return (
      <p className={`mt-4 text-sm ${muted}`}>
        All {rows.length} collectors healthy.{" "}
        <Link href="/runs" className="underline">
          Collector health
        </Link>
      </p>
    );
  }
  return (
    <div
      role="status"
      className="mt-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
    >
      <p className="font-medium">
        {bad.length} of {rows.length} collectors need attention.{" "}
        <Link href="/runs" className="underline">
          Full health table
        </Link>
      </p>
      <ul className="mt-1 space-y-0.5">
        {bad.map((h) => (
          <li key={h.source} className="break-words">
            <span className="font-medium">{h.source}</span>:{" "}
            {h.last_status === "ok" ? "stale" : (h.last_status ?? "never run")}
            {h.consecutive_failures > 0 && `, ${h.consecutive_failures} failures in a row`}, last
            success {h.last_success_at ? fmtDateTime(h.last_success_at) : "never"}
            {h.last_error && <span className="block text-xs opacity-90">{h.last_error.slice(0, 200)}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

async function Themes() {
  const { run, themes } = await currentThemes();
  if (!run) {
    return (
      <p className={`mt-2 text-sm ${muted}`}>
        No themes yet: <code>uv run python -m pipeline themes</code> has not completed a run.
        Problems below still work.
      </p>
    );
  }
  if (themes.length === 0) {
    return (
      <p className={`mt-2 text-sm ${muted}`}>
        Themes run {run.id} ({fmtDate(run.started_at)}) found no themes.
      </p>
    );
  }
  return (
    <>
      <p className={`mt-1 text-sm ${muted}`}>
        {themes.length} loose topic clusters from themes run {run.id} ({fmtDate(run.started_at)}),
        largest audience first. Themes are a browsing aid, recomputed every run; problems are the
        stable entities.
      </p>
      <ThemeGrid themes={themes.slice(0, THEMES_SHOWN)} />
      {themes.length > THEMES_SHOWN && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-medium">
            Show {themes.length - THEMES_SHOWN} more themes
          </summary>
          <ThemeGrid themes={themes.slice(THEMES_SHOWN)} />
        </details>
      )}
    </>
  );
}

const THEMES_SHOWN = 6;

function ThemeGrid({ themes }: { themes: ThemeWithDetail[] }) {
  return (
    <ul className="mt-3 grid gap-3 md:grid-cols-2">
      {themes.map((t) => (
        <li key={t.id}>
          <ThemeCard t={t} />
        </li>
      ))}
    </ul>
  );
}



function ThemeCard({ t }: { t: ThemeWithDetail }) {
  return (
    <article className={`${card} h-full`}>
      <h3 className="font-medium">
        <Link href={`/themes/${t.id}`} className="underline-offset-2 hover:underline">
          {t.title}
        </Link>
        <ModelNamed source={t.title_source} />
      </h3>
      <p className={`mt-1 text-xs tabular-nums ${muted}`}>
        {plural(t.distinct_authors, "author")} · {plural(t.size, "pain")} ·{" "}
        {plural(t.sources, "source")}
        {t.source_names ? ` (${t.source_names})` : ""} · {plural(t.countries, "country", "countries")}
      </p>
      {t.statement && (
        <p className="mt-2 text-sm">
          <span className={`text-xs ${muted}`}>Model summary: </span>
          {t.statement}
        </p>
      )}
      {t.samples.length > 0 && (
        <div className="mt-3 space-y-3">
          {t.samples.map((q) => (
            <QuoteSnippet key={q.pain_id} q={q} />
          ))}
        </div>
      )}
      {t.problems.length > 0 && (
        <div className="mt-3 text-sm">
          <p className={`text-xs ${muted}`}>Problems mostly inside this theme:</p>
          <ul className="mt-1 list-disc pl-5">
            {t.problems.map((p) => (
              <li key={p.problem_id}>
                <Link href={`/problems/${p.problem_id}`} className="underline">
                  {p.title}
                </Link>{" "}
                <span className={`text-xs ${muted}`}>
                  ({p.n} of {p.total} active members, {p.status})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}

function first(v: string | string[] | undefined): string {
  return Array.isArray(v) ? (v[0] ?? "") : (v ?? "");
}

async function Problems({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams;
  const sources = await problemSources();
  const status = (STATUS_FILTERS as readonly string[]).includes(first(sp.status)) ? first(sp.status) : "open";
  const source = sources.includes(first(sp.source)) ? first(sp.source) : "";
  const sort: RadarFilter["sort"] = first(sp.sort) === "growth" ? "growth" : "authors";
  const data = await radarProblems({ status, source, sort });
  if (data === null) return <NoDatabase path={dbPath()} />;
  const { problems, snapshotRuns, latestRun } = data;

  return (
    <>
      <form method="get" className="mt-3 flex flex-wrap items-end gap-3" aria-label="Filter problems">
        <div>
          <label htmlFor="f-status" className="block text-xs font-medium">
            Status
          </label>
          <select id="f-status" name="status" defaultValue={status} className={`mt-1 ${input} w-40 dark:bg-zinc-950`}>
            {STATUS_FILTERS.map((s) => (
              <option key={s} value={s}>
                {s === "open" ? "open (not archived)" : s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="f-source" className="block text-xs font-medium">
            Source
          </label>
          <select id="f-source" name="source" defaultValue={source} className={`mt-1 ${input} w-44 dark:bg-zinc-950`}>
            <option value="">all sources</option>
            {sources.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="f-sort" className="block text-xs font-medium">
            Sort by
          </label>
          <select id="f-sort" name="sort" defaultValue={sort} className={`mt-1 ${input} w-48 dark:bg-zinc-950`}>
            <option value="authors">distinct authors</option>
            <option value="growth">recent growth</option>
          </select>
        </div>
        <button type="submit" className={buttonSecondary}>
          Apply
        </button>
      </form>
      <p className={`mt-3 text-sm ${muted}`}>
        {snapshotRuns} snapshot run{snapshotRuns === 1 ? "" : "s"} so far
        {snapshotRuns < TREND_MIN_SNAPSHOTS
          ? `; trend flags need ${TREND_MIN_SNAPSHOTS}, so sparklines show history only.`
          : "."}{" "}
        Authors, members and sources are live counts over active pains; sparklines and
        &ldquo;new&rdquo; come from map run snapshots (latest: run {latestRun ?? "–"}), so a
        sparkline&apos;s end value can differ from the live count.
      </p>
      {problems.length === 0 ? (
        <p className={`mt-3 text-sm ${muted}`}>No problems match these filters.</p>
      ) : (
        <div className="mt-3 overflow-x-auto" tabIndex={0} role="region" aria-label="Problems table">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <caption className="sr-only">Problems, {sort === "growth" ? "by recent growth" : "by distinct authors"}</caption>
            <thead className={muted}>
              <tr>
                <th scope="col" className="py-2 pr-4 font-medium">Problem</th>
                <th scope="col" className="py-2 pr-4 font-medium">Status</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Authors <span className="block text-xs font-normal">live</span></th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Members <span className="block text-xs font-normal">live</span></th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Sources <span className="block text-xs font-normal">live</span></th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">New <span className="block text-xs font-normal">run {latestRun ?? "–"}</span></th>
                <th scope="col" className="py-2 font-medium">Authors per map run</th>
              </tr>
            </thead>
            <tbody>
              {problems.map((p) => (
                <tr key={p.id} className="border-t border-zinc-200 align-top dark:border-zinc-800">
                  <td className="py-2 pr-4">
                    <Link href={`/problems/${p.id}`} className="underline-offset-2 hover:underline">
                      {p.title}
                    </Link>
                    <ModelNamed source={p.title_source} />
                  </td>
                  <td className="py-2 pr-4">
                    <StatusBadge status={p.status} />
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">{p.distinct_authors}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{p.mentions}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{p.sources}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{p.new_mentions ?? "–"}</td>
                  <td className="py-2">
                    <Sparkline
                      label="Distinct authors"
                      live={p.distinct_authors}
                      points={p.history.map((h) => ({ run_id: h.run_id, value: h.distinct_authors }))}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
