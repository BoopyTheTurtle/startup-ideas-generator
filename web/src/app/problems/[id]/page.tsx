import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { Suspense } from "react";
import { problemDetail, problemTitles, resolveProblemId } from "@/lib/radar";
import { TREND_MIN_SNAPSHOTS, fmtDate, fmtDateTime, plural } from "@/lib/steering-shared";
import { QuoteList } from "@/components/quote-card";
import { SnapshotChart } from "@/components/snapshot-chart";
import { BackLink, ModelNamed, StatusBadge, card, muted } from "@/components/ui";
import { RenameForm, SteerForm } from "./steer-form";

const QUOTE_LIMIT = 100;

const TITLE_SOURCE: Record<string, string> = {
  auto: "automatic title, not yet curated",
  curator: "title written by the curator model",
  human: "title set by Edgar",
};

type Params = Promise<{ id: string }>;

// Streams with the page: the body defers to request time too (Cache Components).
export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { id: raw } = await params;
  const id = Number(raw);
  if (!/^\d+$/.test(raw) || !Number.isSafeInteger(id)) return { title: "Problem not found" };
  const target = (await resolveProblemId(id)) ?? id;
  const title = (await problemTitles([target])).get(target);
  return { title: title ? `${title} (problem ${target})` : "Problem not found" };
}

export default function ProblemPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-8">
      <BackLink href="/">Radar</BackLink>
      <Suspense fallback={<p className={`mt-4 text-sm ${muted}`}>Loading problem…</p>}>
        <Problem params={params} />
      </Suspense>
    </main>
  );
}

async function Problem({ params }: { params: Promise<{ id: string }> }) {
  const { id: raw } = await params;
  const id = Number(raw);
  if (!/^\d+$/.test(raw) || !Number.isSafeInteger(id)) notFound();
  // Old ids keep resolving after merges.
  const target = await resolveProblemId(id);
  if (target === null) notFound();
  if (target !== id) redirect(`/problems/${target}`);
  const detail = await problemDetail(id, QUOTE_LIMIT);
  if (!detail) notFound();
  const { problem: p, quotes, decisions, pairs, aliases, themes, snapshotRuns } = detail;
  const curatorFlag = p.statement?.includes("[Curator:") ?? false;
  const openPairs = pairs.filter((x) => x.status === "open");

  return (
    <>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight break-words">
        {p.title}
        <ModelNamed source={p.title_source} />
      </h1>
      <p className={`mt-2 flex flex-wrap items-center gap-2 text-sm ${muted}`}>
        <StatusBadge status={p.status} />
        <span>
          Problem {p.id} · {TITLE_SOURCE[p.title_source] ?? p.title_source} · created in run{" "}
          {p.created_run_id} · updated {fmtDate(p.updated_at)}
        </span>
      </p>
      <p className="mt-2 text-sm tabular-nums">
        <span className={muted}>Live: </span>
        {plural(p.distinct_authors, "distinct author")} · {plural(p.mentions, "member pain")} ·{" "}
        {plural(p.sources, "source")} · {plural(p.countries, "country", "countries")}
        {p.new_mentions !== null && p.history.length > 0 &&
          ` · ${p.new_mentions} new in map run ${p.history[p.history.length - 1].run_id}`}
      </p>
      {themes.length > 0 && (
        <p className="mt-1 text-sm break-words">
          <span className={muted}>Themes: </span>
          {themes.map((t, i) => (
            <span key={t.theme_id}>
              {i > 0 && "; "}
              <Link href={`/themes/${t.theme_id}`} className="underline">
                {t.title}
              </Link>{" "}
              <span className={`text-xs ${muted}`}>
                ({t.n} of {t.total} members)
              </span>
            </span>
          ))}
        </p>
      )}
      {aliases.length > 0 && (
        <p className={`mt-1 text-sm ${muted}`}>
          Absorbed: {aliases.map((a) => `problem ${a.old_id}`).join(", ")}.
        </p>
      )}
      {openPairs.length > 0 && (
        <p className="mt-2 text-sm">
          <Link href="/merges" className="underline">
            {openPairs.length} open merge candidate{openPairs.length === 1 ? "" : "s"}
          </Link>{" "}
          involve this problem.
        </p>
      )}

      {p.statement && (
        <div className={`mt-4 ${card} text-sm`}>
          <p className={`text-xs font-medium uppercase tracking-wide ${muted}`}>
            Statement (model-written from the quotes below)
          </p>
          {curatorFlag && (
            <p className="mt-2 rounded bg-amber-50 p-2 text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              <span className="font-medium">Curator flag:</span> the curator model doubts these
              members form one problem. Read the quotes before acting.
            </p>
          )}
          <p className="mt-2 whitespace-pre-wrap break-words">{p.statement}</p>
        </div>
      )}

      <section aria-labelledby="steer-heading" className={`mt-6 ${card}`}>
        <h2 id="steer-heading" className="text-lg font-medium">
          Steer
        </h2>
        {p.status === "merged" ? (
          <p className={`mt-2 text-sm ${muted}`}>Merged problems cannot be steered.</p>
        ) : (
          <div className="mt-3 space-y-6">
            <SteerForm problemId={p.id} status={p.status} title={p.title} />
            <details>
              <summary className="cursor-pointer text-sm font-medium">Rename</summary>
              <div className="mt-3">
                <RenameForm problemId={p.id} title={p.title} />
              </div>
            </details>
          </div>
        )}
      </section>

      <section aria-labelledby="history-heading" className="mt-8">
        <h2 id="history-heading" className="text-lg font-medium">
          Snapshots
        </h2>
        <p className={`mt-1 text-sm ${muted}`}>
          One point per map run, as counted in that run; the live counts above can differ.{" "}
          {snapshotRuns < TREND_MIN_SNAPSHOTS
            ? `Trend: insufficient data (${p.history.length} of ${TREND_MIN_SNAPSHOTS} runs needed).`
            : ""}
        </p>
        <div className="mt-3">
          <SnapshotChart
            points={p.history.map((h) => ({
              run_id: h.run_id,
              date: h.run_started_at,
              mentions: h.mentions,
              authors: h.distinct_authors,
            }))}
          />
        </div>
        {p.history.length > 0 && (
          <details className="mt-3">
            <summary className="cursor-pointer text-sm font-medium">Table view</summary>
            <div className="mt-2 overflow-x-auto" tabIndex={0} role="region" aria-label="Snapshots table">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Snapshot counts per map run</caption>
                <thead className={muted}>
                  <tr>
                    <th scope="col" className="py-1 pr-4 font-medium">Run</th>
                    <th scope="col" className="py-1 pr-4 font-medium">Date (UTC)</th>
                    <th scope="col" className="py-1 pr-4 text-right font-medium">Mentions</th>
                    <th scope="col" className="py-1 pr-4 text-right font-medium">Distinct authors</th>
                    <th scope="col" className="py-1 pr-4 text-right font-medium">Sources</th>
                    <th scope="col" className="py-1 text-right font-medium">New</th>
                  </tr>
                </thead>
                <tbody>
                  {p.history.map((h) => (
                    <tr key={h.run_id} className="border-t border-zinc-200 dark:border-zinc-800">
                      <td className="py-1 pr-4 tabular-nums">{h.run_id}</td>
                      <td className="py-1 pr-4 tabular-nums">{fmtDateTime(h.run_started_at)}</td>
                      <td className="py-1 pr-4 text-right tabular-nums">{h.mentions}</td>
                      <td className="py-1 pr-4 text-right tabular-nums">{h.distinct_authors}</td>
                      <td className="py-1 pr-4 text-right tabular-nums">{h.sources}</td>
                      <td className="py-1 text-right tabular-nums">{h.new_mentions}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
      </section>

      <section aria-labelledby="quotes-heading" className="mt-8">
        <h2 id="quotes-heading" className="text-lg font-medium">
          Evidence
        </h2>
        <QuoteList quotes={quotes} total={p.mentions} />
      </section>

      <section aria-labelledby="decisions-heading" className="mt-8">
        <h2 id="decisions-heading" className="text-lg font-medium">
          Decision history
        </h2>
        {decisions.length === 0 ? (
          <p className={`mt-2 text-sm ${muted}`}>No decisions yet.</p>
        ) : (
          <ol className="mt-2 space-y-2 text-sm">
            {decisions.map((d) => (
              <li key={d.id} className="border-l-2 border-zinc-300 pl-3 dark:border-zinc-700">
                <span className="font-medium">{d.action}</span>
                {d.reason && <span className={muted}> · {d.reason}</span>}
                <span className={`tabular-nums ${muted}`}> · {fmtDateTime(d.created_at)}</span>
                {d.note && <p className="mt-0.5 break-words">{d.note}</p>}
              </li>
            ))}
          </ol>
        )}
        {pairs.length > 0 && (
          <>
            <h3 className="mt-4 text-sm font-medium">Merge candidates</h3>
            <ul className="mt-1 space-y-1 text-sm">
              {pairs.map((x) => (
                <li key={`${x.a_id}-${x.b_id}`}>
                  <Link href={`/problems/${x.other_id}`} className="underline">
                    {x.other_title}
                  </Link>{" "}
                  <span className={`text-xs ${muted}`}>
                    similarity {x.similarity.toFixed(3)} · {x.status}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </>
  );
}
