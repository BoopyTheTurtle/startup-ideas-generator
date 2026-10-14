import type { Metadata } from "next";
import { Suspense } from "react";
import { ItemView } from "../item-view";
import { itemAmong, withText } from "@/lib/labeling";
import { RECHECK_TARGET, REVIEW_SOURCES, readLabels } from "@/lib/labels";
import { BackLink, muted } from "@/components/ui";

export const metadata: Metadata = { title: "Consistency check" };

// Blind second pass over working items: the first label stays hidden, so agreement between
// the passes measures how consistently the labels can be given at all.
export default function RecheckPage() {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-10">
      <BackLink href="/label">Label items</BackLink>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Consistency check</h1>
      <p className={`mt-2 text-sm ${muted}`}>
        You labeled these items before. Label them again by the same definition; your first answer
        stays hidden. {RECHECK_TARGET.review + RECHECK_TARGET.control} compared items in all.
        &ldquo;Unsure&rdquo; answers don&apos;t count toward the comparison, so each one brings up
        another item.
      </p>
      <div className="mt-4 rounded border border-zinc-200 p-4 text-sm dark:border-zinc-800">
        <span className="font-medium">Pain:</span> a problem many people share that someone could
        build a business around, not one person&apos;s bug report.
      </div>
      <Suspense fallback={<p className={`mt-6 text-sm ${muted}`}>Loading an item…</p>}>
        <Rechecker />
      </Suspense>
    </main>
  );
}

async function Rechecker() {
  const working = readLabels("working");
  const done = readLabels("recheck");
  const isReview = (source: string) => REVIEW_SOURCES.includes(source);
  // pipeline eval-consistency skips pairs where either answer is unsure, so only sure
  // answers fill the quotas.
  let reviewDone = 0;
  let controlDone = 0;
  let unsure = 0;
  for (const rec of done.values()) {
    if (rec.label === "unsure") unsure += 1;
    else if (isReview(rec.source)) reviewDone += 1;
    else controlDone += 1;
  }

  const open = [...working.values()].filter((r) => r.label !== "unsure" && !done.has(r.raw_item_id));
  // Items whose text was discarded since the first pass cannot be judged again.
  const judgeable = await withText(open.map((r) => r.raw_item_id));
  const ids = (review: boolean) =>
    open.filter((r) => isReview(r.source) === review && judgeable.has(r.raw_item_id)).map((r) => r.raw_item_id);
  const pools = [
    { name: "review", need: reviewDone < RECHECK_TARGET.review, ids: ids(true) },
    { name: "control", need: controlDone < RECHECK_TARGET.control, ids: ids(false) },
  ];
  // The first pool that still needs items and yields one; a dry pool falls through.
  let item = null;
  for (const pool of pools) {
    if (!pool.need) continue;
    item = await itemAmong(pool.ids);
    if (item) break;
  }
  const dry = pools.filter((p) => p.need && p.ids.length === 0).map((p) => p.name);
  const total = RECHECK_TARGET.review + RECHECK_TARGET.control;

  return (
    <>
      <p className="mt-6 text-sm tabular-nums">
        {reviewDone + controlDone} of {total} compared (reviews and support posts {reviewDone}/
        {RECHECK_TARGET.review}, other sources {controlDone}/{RECHECK_TARGET.control})
        {unsure > 0 && (
          <span className={muted}>
            {" "}
            · {unsure} answered unsure, not counted
          </span>
        )}
      </p>
      {item ? (
        <ItemView item={item} set="recheck" />
      ) : (
        <p className="mt-6 text-sm">
          {dry.length > 0
            ? `No judgeable items left in the ${dry.join(" and ")} pool${dry.length > 1 ? "s" : ""}. `
            : ""}
          Done. Tell Claude, which runs <code>pipeline eval-consistency</code> on the two passes.
        </p>
      )}
    </>
  );
}
