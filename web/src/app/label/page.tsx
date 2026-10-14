import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { ItemView } from "./item-view";
import { PainDefinition } from "@/components/pain-definition";
import { BackLink, muted } from "@/components/ui";
import { nextItem, remainingBySource } from "@/lib/labeling";
import { EVAL_SETS, readLabels, type EvalSet, type LabelRecord } from "@/lib/labels";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export const metadata: Metadata = { title: "Label items" };

const SET_NAMES: Record<EvalSet, string> = { working: "Working set", heldout: "Held-out set" };

export default function LabelPage({ searchParams }: { searchParams: SearchParams }) {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-10">
      <BackLink href="/">Radar</BackLink>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Label items</h1>
      <p className="mt-1 text-sm">
        <Link href="/label/recheck" className="underline">
          Consistency check
        </Link>{" "}
        <span className={muted}>(re-label 30 working items blind)</span>
      </p>
      <PainDefinition />
      <Suspense fallback={<p className={`mt-6 text-sm ${muted}`}>Loading an item…</p>}>
        <Labeler searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function Labeler({ searchParams }: { searchParams: SearchParams }) {
  const set: EvalSet = (await searchParams).set === "heldout" ? "heldout" : "working";
  const labels = { working: readLabels("working"), heldout: readLabels("heldout") };
  const labeled = [...labels.working.keys(), ...labels.heldout.keys()];
  const [item, remaining] = await Promise.all([nextItem(labeled), remainingBySource(labeled)]);

  return (
    <>
      <nav className="mt-6 flex gap-2 text-sm" aria-label="Eval set">
        {EVAL_SETS.map((s) => (
          <Link
            key={s}
            href={`/label?set=${s}`}
            aria-current={s === set ? "page" : undefined}
            className={`rounded px-3 py-1.5 ${
              s === set
                ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "border border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            }`}
          >
            {SET_NAMES[s]} ({labels[s].size})
          </Link>
        ))}
      </nav>
      {set === "heldout" && (
        <p className="mt-3 rounded bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          Held-out set: for Edgar only. Agents never read it; it exists to catch overfitting. This
          mode shows no model output.
        </p>
      )}
      {item ? (
        <ItemView item={item} set={set} />
      ) : (
        <p className={`mt-6 text-sm ${muted}`}>
          No unlabeled items with text left. Run the collectors, then come back.
        </p>
      )}
      <Counters labels={labels} remaining={remaining} />
    </>
  );
}

function Counters({
  labels,
  remaining,
}: {
  labels: Record<EvalSet, Map<number, LabelRecord>>;
  remaining: Map<string, number>;
}) {
  const sources = new Set<string>(remaining.keys());
  const bySource: Record<EvalSet, Map<string, number>> = { working: new Map(), heldout: new Map() };
  const byLabel: Record<EvalSet, Record<string, number>> = { working: {}, heldout: {} };
  for (const s of EVAL_SETS) {
    for (const rec of labels[s].values()) {
      sources.add(rec.source);
      bySource[s].set(rec.source, (bySource[s].get(rec.source) ?? 0) + 1);
      byLabel[s][rec.label] = (byLabel[s][rec.label] ?? 0) + 1;
    }
  }
  return (
    <section className="mt-10">
      <h2 className="text-lg font-medium">Progress</h2>
      <ul className="mt-2 text-sm">
        {EVAL_SETS.map((s) => (
          <li key={s}>
            {SET_NAMES[s]}: {labels[s].size} labeled (pain {byLabel[s].pain ?? 0}, not pain{" "}
            {byLabel[s].not_pain ?? 0}, unsure {byLabel[s].unsure ?? 0})
          </li>
        ))}
      </ul>
      <div className="mt-3 overflow-x-auto" tabIndex={0} role="region" aria-label="Labeling progress table">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Labels per source and set</caption>
          <thead className={muted}>
            <tr>
              <th scope="col" className="py-2 pr-4 font-medium">Source</th>
              <th scope="col" className="py-2 pr-4 font-medium">Working</th>
              <th scope="col" className="py-2 pr-4 font-medium">Held-out</th>
              <th scope="col" className="py-2 font-medium">Unlabeled</th>
            </tr>
          </thead>
          <tbody>
            {[...sources].sort().map((src) => (
              <tr key={src} className="border-t border-zinc-200 dark:border-zinc-800">
                <th scope="row" className="py-2 pr-4 font-normal">{src}</th>
                <td className="py-2 pr-4 tabular-nums">{bySource.working.get(src) ?? 0}</td>
                <td className="py-2 pr-4 tabular-nums">{bySource.heldout.get(src) ?? 0}</td>
                <td className="py-2 tabular-nums">{remaining.get(src) ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
