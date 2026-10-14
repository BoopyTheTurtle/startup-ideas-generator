import { isCardStatus } from "@/lib/cards-shared";

// The status is spelled out, so colour is never the only signal.
const STYLE: Record<string, string> = {
  proposed: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
  approved: "bg-indigo-100 text-indigo-900 dark:bg-indigo-950 dark:text-indigo-200",
  building: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  built: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  ready: "bg-green-100 text-green-900 dark:bg-green-950 dark:text-green-200",
  merged: "bg-zinc-200 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200",
  reverted: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
  rejected: "bg-zinc-200 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200",
  abandoned: "bg-zinc-200 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200",
};

export function CardStatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
        isCardStatus(status) ? STYLE[status] : STYLE.abandoned
      }`}
    >
      {status}
    </span>
  );
}

// A short chip such as "touches: system"; the word carries the meaning.
export function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-block rounded border border-zinc-300 px-1.5 py-0.5 text-xs dark:border-zinc-700">
      {children}
    </span>
  );
}
