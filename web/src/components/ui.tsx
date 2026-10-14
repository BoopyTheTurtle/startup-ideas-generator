import Link from "next/link";
import type { ReactNode } from "react";
import { REASONS, NOTE_MAX } from "@/lib/steering-shared";

export const muted = "text-zinc-600 dark:text-zinc-400";
export const card = "rounded border border-zinc-200 p-4 dark:border-zinc-800";
export const input =
  "w-full rounded border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700";
// aria-disabled buttons stay focusable (focus is not lost when one becomes unavailable);
// their click handlers ignore the click.
const inert = "disabled:opacity-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50";
export const buttonPrimary =
  `rounded bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300 ${inert}`;
export const buttonSecondary =
  `rounded border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800 ${inert}`;
export const buttonDanger =
  `rounded border border-red-700 px-4 py-2 text-sm font-medium text-red-800 hover:bg-red-50 dark:border-red-400 dark:text-red-300 dark:hover:bg-red-950 ${inert}`;

// The first submit button in tree order is the form's default button; a disabled one
// makes Enter in a text field do nothing, so a choice among several buttons stays explicit.
export function NoImplicitSubmit() {
  return <button type="submit" disabled hidden aria-hidden="true" tabIndex={-1} />;
}

// Marks a title the pipeline wrote (automatic or by the curator model), not Edgar.
export function ModelNamed({ source }: { source: string }) {
  if (source !== "auto" && source !== "curator") return null;
  return (
    <span
      className={`ml-1.5 inline-block rounded border border-zinc-300 px-1 align-middle text-[11px] font-normal leading-4 dark:border-zinc-700 ${muted}`}
      title={source === "auto" ? "Automatic title, not yet curated" : "Title written by the curator model"}
    >
      model-named
    </span>
  );
}

const STATUS_STYLE: Record<string, string> = {
  new: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
  watching: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  promoted: "bg-green-100 text-green-900 dark:bg-green-950 dark:text-green-200",
  archived: "bg-zinc-200 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200",
  merged: "bg-zinc-200 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[status] ?? STATUS_STYLE.archived}`}>
      {status}
    </span>
  );
}

// Reason code + optional note, shared by every steering form. `idPrefix` keeps label
// ids unique when several forms share a page.
export function ReasonFields({ idPrefix, noteRequired = false }: { idPrefix: string; noteRequired?: boolean }) {
  return (
    <div className="grid gap-3 sm:grid-cols-[14rem_1fr]">
      <div>
        <label htmlFor={`${idPrefix}-reason`} className="block text-sm font-medium">
          Reason
        </label>
        <select
          id={`${idPrefix}-reason`}
          name="reason"
          required
          defaultValue=""
          className={`mt-1 ${input} dark:bg-zinc-950`}
        >
          <option value="" disabled>
            Choose a reason
          </option>
          {REASONS.map((r) => (
            <option key={r.code} value={r.code}>
              {r.label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor={`${idPrefix}-note`} className="block text-sm font-medium">
          Note {noteRequired ? "" : <span className={`font-normal ${muted}`}>(optional)</span>}
        </label>
        <input
          id={`${idPrefix}-note`}
          type="text"
          name="note"
          maxLength={NOTE_MAX}
          className={`mt-1 ${input}`}
        />
      </div>
    </div>
  );
}

export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <p className="text-sm">
      <Link href={href} className={`${muted} hover:underline`}>
        ← {children}
      </Link>
    </p>
  );
}

export function NoDatabase({ path }: { path: string }) {
  return (
    <p className={`text-sm ${muted}`}>
      No database at <code className="break-all">{path}</code>. Run{" "}
      <code>uv run python -m pipeline smoke</code> from the repo root.
    </p>
  );
}
