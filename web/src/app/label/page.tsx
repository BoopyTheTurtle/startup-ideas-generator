import Link from "next/link";
import { Suspense } from "react";
import { LabelForm } from "./label-form";
import { nextItem, remainingBySource, type LabelItem } from "@/lib/labeling";
import { EVAL_SETS, readLabels, type EvalSet, type LabelRecord } from "@/lib/labels";
import { plainText, safeUrl } from "@/lib/plaintext";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

const SET_NAMES: Record<EvalSet, string> = { working: "Working set", heldout: "Held-out set" };

export default function LabelPage({ searchParams }: { searchParams: SearchParams }) {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-10">
      <p className="text-sm">
        <Link href="/" className="text-zinc-500 hover:underline">
          ← Home
        </Link>
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Label items</h1>
      <Definition />
      <Suspense fallback={<p className="mt-6 text-sm text-zinc-500">Loading an item…</p>}>
        <Labeler searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

function Definition() {
  return (
    <div className="mt-4 rounded border border-zinc-200 p-4 text-sm dark:border-zinc-800">
      <p>
        <span className="font-medium">Pain:</span> a problem many people share that someone
        could build a business around. Petitions and demands count when a group suffers the
        problem behind them.
      </p>
      <p className="mt-2">
        <span className="font-medium">Not pain:</span> one person&apos;s bug report or support
        question; a single product decision users can avoid; news, opinions, praise, jokes, spam.
      </p>
    </div>
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
        <p className="mt-6 text-sm text-zinc-500">
          No unlabeled items with text left. Run the collectors, then come back.
        </p>
      )}
      <Counters labels={labels} remaining={remaining} />
    </>
  );
}

async function ItemView({ item, set }: { item: LabelItem; set: EvalSet }) {
  const url = safeUrl(item.url);
  const body = plainText(item.body);
  const meta = [
    item.lang && `language ${item.lang}`,
    item.country && `country ${item.country}`,
    item.created_at && `posted ${item.created_at.slice(0, 10)}`,
  ].filter(Boolean);
  return (
    <article className="mt-6 rounded border border-zinc-200 p-4 dark:border-zinc-800">
      <p className="text-xs text-zinc-500">
        <span className="font-medium text-zinc-700 dark:text-zinc-300">{item.source}</span>
        {" · "}item {item.id}
        {meta.length > 0 && ` · ${meta.join(" · ")}`}
        {url && (
          <>
            {" · "}
            <a href={url} target="_blank" rel="noopener noreferrer" className="underline">
              original
            </a>
          </>
        )}
      </p>
      {item.title && <h2 className="mt-2 text-lg font-medium">{plainText(item.title)}</h2>}
      <p className="mt-3 max-h-[28rem] overflow-y-auto whitespace-pre-wrap break-words text-sm leading-6">
        {body || <span className="text-zinc-500">(no body)</span>}
      </p>
      {/* No model output in either set: labels are what the model is scored against. */}
      <LabelForm itemId={item.id} set={set} />
    </article>
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
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-zinc-500">
            <tr>
              <th className="py-2 pr-4 font-medium">Source</th>
              <th className="py-2 pr-4 font-medium">Working</th>
              <th className="py-2 pr-4 font-medium">Held-out</th>
              <th className="py-2 font-medium">Unlabeled</th>
            </tr>
          </thead>
          <tbody>
            {[...sources].sort().map((src) => (
              <tr key={src} className="border-t border-zinc-200 dark:border-zinc-800">
                <td className="py-2 pr-4">{src}</td>
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
