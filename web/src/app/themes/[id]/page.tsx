import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { themeDetail } from "@/lib/radar";
import { fmtDate, plural } from "@/lib/steering-shared";
import { QuoteList } from "@/components/quote-card";
import { BackLink, StatusBadge, card, muted } from "@/components/ui";

const QUOTE_LIMIT = 100;

export default function ThemePage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-8">
      <BackLink href="/">Radar</BackLink>
      <Suspense fallback={<p className={`mt-4 text-sm ${muted}`}>Loading theme…</p>}>
        <Theme params={params} />
      </Suspense>
    </main>
  );
}

async function Theme({ params }: { params: Promise<{ id: string }> }) {
  const { id: raw } = await params;
  const id = Number(raw);
  if (!/^\d+$/.test(raw) || !Number.isSafeInteger(id)) notFound();
  const detail = await themeDetail(id, QUOTE_LIMIT);
  if (!detail) notFound();
  const { theme: t, run, currentRunId, quotes, problems } = detail;

  return (
    <>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">{t.title}</h1>
      <p className={`mt-1 text-sm tabular-nums ${muted}`}>
        Theme {t.id} · themes run {t.run_id}
        {run && ` (${fmtDate(run.started_at)})`} · {plural(t.distinct_authors, "author")} ·{" "}
        {plural(t.size, "pain")} · {plural(t.sources, "source")}
        {t.source_names ? ` (${t.source_names})` : ""} · {plural(t.countries, "country", "countries")}
        {t.cohesion !== null && ` · cohesion ${t.cohesion.toFixed(2)}`} · title {t.title_source}
      </p>
      {currentRunId !== null && currentRunId !== t.run_id && (
        <p className="mt-3 rounded bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          This theme comes from an older themes run. The radar shows run {currentRunId}.
        </p>
      )}
      {t.statement && (
        <div className={`mt-4 ${card} text-sm`}>
          <p className={`text-xs font-medium uppercase tracking-wide ${muted}`}>Model summary</p>
          <p className="mt-1">{t.statement}</p>
        </div>
      )}

      <section aria-labelledby="theme-problems" className="mt-8">
        <h2 id="theme-problems" className="text-lg font-medium">
          Problems inside
        </h2>
        {problems.length === 0 ? (
          <p className={`mt-2 text-sm ${muted}`}>
            No problem has most of its members in this theme.
          </p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm">
            {problems.map((p) => (
              <li key={p.problem_id} className="flex flex-wrap items-center gap-2">
                <StatusBadge status={p.status} />
                <Link href={`/problems/${p.problem_id}`} className="underline">
                  {p.title}
                </Link>
                <span className={`text-xs ${muted}`}>
                  {p.n} of {p.total} members here
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="theme-quotes" className="mt-8">
        <h2 id="theme-quotes" className="text-lg font-medium">
          Member pains
        </h2>
        <QuoteList quotes={quotes} total={t.size} />
      </section>
    </>
  );
}
