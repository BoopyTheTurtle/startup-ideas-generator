import Link from "next/link";
import { Suspense } from "react";
import { ItemView } from "../item-view";
import { itemAmong } from "@/lib/labeling";
import { RECHECK_TARGET, REVIEW_SOURCES, readLabels } from "@/lib/labels";

// Blind second pass over working items: the first label stays hidden, so agreement between
// the passes measures how consistently the labels can be given at all.
export default function RecheckPage() {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-10">
      <p className="text-sm">
        <Link href="/label" className="text-zinc-500 hover:underline">
          ← Label items
        </Link>
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Consistency check</h1>
      <p className="mt-2 text-sm text-zinc-500">
        You labeled these items before. Label them again by the same definition; your first answer
        stays hidden. {RECHECK_TARGET.review + RECHECK_TARGET.control} items in all.
      </p>
      <div className="mt-4 rounded border border-zinc-200 p-4 text-sm dark:border-zinc-800">
        <span className="font-medium">Pain:</span> a problem many people share that someone could
        build a business around, not one person&apos;s bug report.
      </div>
      <Suspense fallback={<p className="mt-6 text-sm text-zinc-500">Loading an item…</p>}>
        <Rechecker />
      </Suspense>
    </main>
  );
}

async function Rechecker() {
  const working = readLabels("working");
  const done = readLabels("recheck");
  const isReview = (source: string) => REVIEW_SOURCES.includes(source);
  let reviewDone = 0;
  for (const rec of done.values()) if (isReview(rec.source)) reviewDone += 1;
  const controlDone = done.size - reviewDone;

  const open = [...working.values()].filter((r) => r.label !== "unsure" && !done.has(r.raw_item_id));
  const reviewPool = open.filter((r) => isReview(r.source)).map((r) => r.raw_item_id);
  const controlPool = open.filter((r) => !isReview(r.source)).map((r) => r.raw_item_id);
  const pool =
    reviewDone < RECHECK_TARGET.review && reviewPool.length > 0
      ? reviewPool
      : controlDone < RECHECK_TARGET.control
        ? controlPool
        : [];
  const item = await itemAmong(pool);
  const total = RECHECK_TARGET.review + RECHECK_TARGET.control;

  return (
    <>
      <p className="mt-6 text-sm tabular-nums">
        {done.size} of {total} rechecked (reviews and support posts {reviewDone}/
        {RECHECK_TARGET.review}, other sources {controlDone}/{RECHECK_TARGET.control})
      </p>
      {item ? (
        <ItemView item={item} set="recheck" />
      ) : (
        <p className="mt-6 text-sm">
          Done. Tell Claude, which runs <code>pipeline eval-consistency</code> on the two passes.
        </p>
      )}
    </>
  );
}
