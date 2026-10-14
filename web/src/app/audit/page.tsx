import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { ItemView } from "../label/item-view";
import { submitAuditLabel } from "./actions";
import {
  auditScores,
  currentMonth,
  isMonth,
  readAuditLabels,
  readSample,
  type AuditScore,
} from "@/lib/audit";
import { dbPath, open } from "@/lib/db";
import { itemAmong, withText } from "@/lib/labeling";
import { fmtDateTime } from "@/lib/steering-shared";
import { FocusOnMount } from "@/components/focus-on-mount";
import { PainDefinition } from "@/components/pain-definition";
import { NoDatabase, muted } from "@/components/ui";

export const metadata: Metadata = { title: "Blind audit" };

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

// Twenty random items a month, labeled without any model output or earlier label in view.
// Disagreement with the working labels measures label drift; disagreement with the model
// measures true error. Modeled on /label/recheck.
export default function AuditPage({ searchParams }: { searchParams: SearchParams }) {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Monthly blind audit</h1>
      <p className={`mt-2 text-sm ${muted}`}>
        Label each sampled item by the definition below. You see no model output and none of your
        earlier labels, so your answers can be compared with both: disagreement with the working
        set measures label drift, and disagreement with the model measures true error.
      </p>
      <PainDefinition />
      <Suspense fallback={<p className={`mt-6 text-sm ${muted}`}>Loading the audit…</p>}>
        <Audit searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function Audit({ searchParams }: { searchParams: SearchParams }) {
  const now = await currentMonth(); // also marks the page as request-time data
  if (!open()) return <div className="mt-6"><NoDatabase path={dbPath()} /></div>;
  const requested = (await searchParams).month;
  const month = isMonth(requested) ? requested : now;

  const header = (
    <p className="mt-6 text-sm">
      <span className="font-medium">Audit month: {month}</span>
      {month !== now && (
        <>
          {" "}
          <Link href="/audit" className="underline">
            Back to {now}
          </Link>
        </>
      )}
    </p>
  );

  const result = readSample(month);
  if (result.kind === "missing") {
    return (
      <>
        {header}
        <section aria-labelledby="draw-heading" className="mt-4 rounded border border-zinc-200 p-4 text-sm dark:border-zinc-800">
          <h2 id="draw-heading" className="font-medium">
            No sample drawn for {month}
          </h2>
          <p className="mt-1">
            Draw the month&apos;s 20 items from the repo root, then reload this page:
          </p>
          <p className="mt-2">
            <code className="rounded bg-zinc-100 px-1 py-0.5 break-all dark:bg-zinc-800">
              uv run python -m pipeline audit-draw
            </code>
          </p>
        </section>
      </>
    );
  }
  if (result.kind === "invalid") {
    return (
      <>
        {header}
        <p className="mt-4 text-sm text-red-700 dark:text-red-400" role="alert">
          The {month} sample is unusable: {result.reason}. Fix or redraw it with{" "}
          <code>uv run python -m pipeline audit-draw</code>.
        </p>
      </>
    );
  }

  const { sample } = result;
  const labels = readAuditLabels(month);
  const ids = sample.items.map((i) => i.raw_item_id);
  const total = ids.length;
  const labeled = ids.filter((id) => labels.has(id)).length;
  // Items whose text was discarded since the draw cannot be judged.
  const judgeable = await withText(ids);
  const unjudgeable = ids.filter((id) => !labels.has(id) && !judgeable.has(id)).length;
  const nextId = ids.find((id) => !labels.has(id) && judgeable.has(id));
  const item = nextId === undefined ? null : await itemAmong([nextId]);
  const done = item === null && nextId === undefined;

  return (
    <>
      {header}
      <p className="mt-1 text-sm tabular-nums">
        {labeled} of {total} labeled
        {sample.drawn_at && <span className={muted}> · sample drawn {fmtDateTime(sample.drawn_at)} UTC</span>}
        {unjudgeable > 0 && (
          <span className={muted}>
            {" "}
            · {unjudgeable} no longer {unjudgeable === 1 ? "has" : "have"} stored text and can&apos;t be
            judged
          </span>
        )}
      </p>
      <div
        role="progressbar"
        aria-label="Audit progress"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={labeled}
        aria-valuetext={`${labeled} of ${total} labeled`}
        className="mt-2 h-2 w-full overflow-hidden rounded bg-zinc-200 dark:bg-zinc-800"
      >
        <div className="h-full bg-zinc-900 dark:bg-zinc-100" style={{ width: `${(labeled / total) * 100}%` }} />
      </div>
      {item ? (
        <ItemView item={item} submit={submitAuditLabel} hidden={{ month }} />
      ) : done ? (
        <Done month={month} scores={await auditScores(month)} total={total} labeled={labeled} />
      ) : (
        <p className={`mt-6 text-sm ${muted}`}>Could not load the next item. Reload the page.</p>
      )}
    </>
  );
}

function pct(v: number): string {
  return v >= 0 && v <= 1 ? `${(v * 100).toFixed(0)}%` : String(Number(v.toFixed(4)));
}

function Done({ month, scores, total, labeled }: { month: string; scores: AuditScore[]; total: number; labeled: number }) {
  return (
    <section aria-labelledby="done-heading" className="mt-6">
      {/* Takes focus when the last label lands: the form that held it has just left the page. */}
      <FocusOnMount className="outline-none focus-visible:outline-2">
        <h2 id="done-heading" className="text-lg font-medium">
          Done
        </h2>
        <p className="mt-1 text-sm">
          {labeled === total ? `All ${total} items are labeled.` : `Every item with stored text is labeled (${labeled} of ${total}).`}{" "}
          <span className={muted}>Your labels for {month} are saved.</span>
        </p>
      </FocusOnMount>
      <h3 className="mt-5 text-sm font-medium">Scores</h3>
      <ul className="mt-1 space-y-2 text-sm">
        {scores.map((s) => (
          <li key={s.name}>
            {s.label}:{" "}
            {s.value === null ? (
              <span className={muted}>
                not scored yet: run <code>uv run python -m pipeline audit-score</code>
              </span>
            ) : (
              <>
                <span className="font-medium tabular-nums">{pct(s.value)}</span>{" "}
                <span className={`text-xs ${muted}`}>
                  (<code>methodology.{s.name}</code>, run {s.run_id}
                  {s.recorded_at && `, ${fmtDateTime(s.recorded_at)} UTC`}
                  {s.subject === "" ? "" : `, ${s.subject}`})
                </span>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
