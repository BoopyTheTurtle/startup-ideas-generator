import Link from "next/link";
import { Suspense } from "react";
import { dbPath } from "@/lib/db";
import { openMerges, type MergeSide } from "@/lib/radar";
import { plural } from "@/lib/steering-shared";
import { QuoteSnippet } from "@/components/quote-card";
import { NoDatabase, StatusBadge, card, muted } from "@/components/ui";
import { MergeForm } from "./merge-form";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default function MergesPage({ searchParams }: { searchParams: SearchParams }) {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Merge queue</h1>
      <p className={`mt-1 text-sm ${muted}`}>
        Problem pairs whose centroids sit close together. Approve folds one problem into the
        other through <code>pipeline merge</code>; keep apart closes the pair.
      </p>
      <Suspense fallback={null}>
        <Outcome searchParams={searchParams} />
      </Suspense>
      <Suspense fallback={<p className={`mt-4 text-sm ${muted}`}>Loading candidates…</p>}>
        <Queue />
      </Suspense>
    </main>
  );
}

// The last decision, carried in the URL by the action's redirect: ids only.
async function Outcome({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams;
  const pair = (v: string | string[] | undefined) => {
    const m = typeof v === "string" ? /^(\d{1,9})-(\d{1,9})$/.exec(v) : null;
    return m ? [Number(m[1]), Number(m[2])] : null;
  };
  const merged = pair(sp.merged);
  const kept = pair(sp.kept);
  const text = merged
    ? `Merged problem ${merged[0]} into problem ${merged[1]}.`
    : kept
      ? `Kept problems ${kept[0]} and ${kept[1]} apart.`
      : null;
  if (!text) return null;
  return (
    <p role="status" className="mt-4 rounded bg-green-50 p-3 text-sm text-green-900 dark:bg-green-950 dark:text-green-200">
      {text}{" "}
      {merged && (
        <Link href={`/problems/${merged[1]}`} className="underline">
          Open problem {merged[1]}
        </Link>
      )}
    </p>
  );
}

async function Queue() {
  const pairs = await openMerges();
  if (pairs === null) return <div className="mt-4"><NoDatabase path={dbPath()} /></div>;
  if (pairs.length === 0) {
    return <p className={`mt-4 text-sm ${muted}`}>No open merge candidates.</p>;
  }
  return (
    <ol className="mt-6 space-y-8">
      {pairs.map(({ a, b, similarity, run_id }) => (
        <li key={`${a.id}-${b.id}`} className={card}>
          <h2 className="text-base font-medium">
            Problems {a.id} and {b.id}{" "}
            <span className={`text-sm font-normal tabular-nums ${muted}`}>
              · similarity {similarity.toFixed(3)} · found in map run {run_id}
            </span>
          </h2>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <Side side={a} letter="A" />
            <Side side={b} letter="B" />
          </div>
          <div className="mt-4 border-t border-zinc-200 pt-4 dark:border-zinc-800">
            <MergeForm
              a={{ id: a.id, title: a.title }}
              b={{ id: b.id, title: b.title }}
              defaultKeep={b.distinct_authors > a.distinct_authors ? "b" : "a"}
            />
          </div>
        </li>
      ))}
    </ol>
  );
}

function Side({ side, letter }: { side: MergeSide; letter: string }) {
  return (
    <section aria-label={`Problem ${side.id}`} className="min-w-0">
      <p className={`text-xs ${muted}`}>
        {letter} · problem {side.id} <StatusBadge status={side.status} />
      </p>
      <h3 className="mt-1 font-medium break-words">
        <Link href={`/problems/${side.id}`} className="underline-offset-2 hover:underline">
          {side.title}
        </Link>
      </h3>
      <p className={`mt-1 text-xs tabular-nums ${muted}`}>
        {plural(side.distinct_authors, "author")} · {plural(side.mentions, "member")} ·{" "}
        {plural(side.sources, "source")}
      </p>
      {side.statement && (
        <p className="mt-2 text-sm break-words">
          <span className={`text-xs ${muted}`}>Model statement: </span>
          {side.statement}
        </p>
      )}
      <div className="mt-3 space-y-3">
        {side.quotes.length === 0 ? (
          <p className={`text-sm ${muted}`}>No active quotes.</p>
        ) : (
          side.quotes.map((q) => <QuoteSnippet key={q.pain_id} q={q} />)
        )}
      </div>
    </section>
  );
}
