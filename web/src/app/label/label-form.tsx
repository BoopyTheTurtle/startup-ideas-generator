"use client";

import { useActionState, useEffect, useRef } from "react";
import { submitLabel, type LabelState } from "./actions";
import type { FormSet, Label } from "@/lib/labels";

const KEYS: Record<string, Label> = { p: "pain", n: "not_pain", s: "unsure" };

const BUTTONS: { label: Label; text: string; key: string; className: string }[] = [
  { label: "pain", text: "Pain", key: "p", className: "bg-red-700 text-white hover:bg-red-800" },
  {
    label: "not_pain",
    text: "Not pain",
    key: "n",
    className: "bg-zinc-800 text-white hover:bg-zinc-900 dark:bg-zinc-200 dark:text-zinc-900",
  },
  {
    label: "unsure",
    text: "Unsure (skip)",
    key: "s",
    className: "border border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800",
  },
];

const initial: LabelState = { message: "", error: false };

export function LabelForm({ itemId, set }: { itemId: number; set: FormSet }) {
  const [state, action, pending] = useActionState(submitLabel, initial);
  const form = useRef<HTMLFormElement>(null);
  const buttons = useRef<Partial<Record<Label, HTMLButtonElement | null>>>({});

  // p / n / s submit with the matching button, unless focus is in a text field.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.ctrlKey || e.metaKey || e.altKey || e.repeat || pending) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable]")) return;
      const label = KEYS[e.key.toLowerCase()];
      const button = label && buttons.current[label];
      if (!button || !form.current) return;
      e.preventDefault();
      form.current.requestSubmit(button);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending]);

  return (
    <form ref={form} action={action} className="mt-6 space-y-3">
      <input type="hidden" name="raw_item_id" value={itemId} />
      <input type="hidden" name="set" value={set} />
      <input
        key={itemId}
        type="text"
        name="note"
        maxLength={500}
        placeholder="Optional note (Esc to leave the field)"
        className="w-full rounded border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700"
        onKeyDown={(e) => {
          // Enter would submit with the first button (Pain); make the choice explicit.
          if (e.key === "Enter") e.preventDefault();
          if (e.key === "Escape") e.currentTarget.blur();
        }}
      />
      <div className="flex flex-wrap gap-2">
        {BUTTONS.map((b) => (
          <button
            key={b.label}
            ref={(el) => {
              buttons.current[b.label] = el;
            }}
            type="submit"
            name="label"
            value={b.label}
            disabled={pending}
            className={`rounded px-4 py-2 text-sm font-medium disabled:opacity-50 ${b.className}`}
          >
            {b.text} <kbd className="ml-1 font-mono text-xs opacity-70">{b.key}</kbd>
          </button>
        ))}
      </div>
      <p
        aria-live="polite"
        className={`min-h-5 text-sm ${state.error ? "text-red-700 dark:text-red-400" : "text-zinc-500"}`}
      >
        {pending ? "Saving…" : state.message}
      </p>
    </form>
  );
}
