"use client";

import { useActionState, useEffect, useRef, useSyncExternalStore } from "react";
import { submitLabel, type LabelState } from "./actions";
import type { FormSet, Label } from "@/lib/labels";
import { muted } from "@/components/ui";

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

// Single-key shortcuts can be turned off (WCAG 2.1.4). The choice lives in localStorage,
// which may be unavailable (private mode, blocked storage): shortcuts then default to on.
const STORAGE_KEY = "label-shortcuts";
const listeners = new Set<() => void>();
let fallback = true; // the choice when storage cannot hold it

function snapshot(): boolean {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v === null ? fallback : v !== "off";
  } catch {
    return fallback;
  }
}

function writeShortcuts(on: boolean): void {
  fallback = on;
  try {
    window.localStorage.setItem(STORAGE_KEY, on ? "on" : "off");
  } catch {
    // not persisted; the toggle still applies until the page reloads
  }
  for (const l of listeners) l();
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  window.addEventListener("storage", l);
  return () => {
    listeners.delete(l);
    window.removeEventListener("storage", l);
  };
}

export function LabelForm({ itemId, set }: { itemId: number; set: FormSet }) {
  const [state, action, pending] = useActionState(submitLabel, initial);
  const shortcuts = useSyncExternalStore(subscribe, snapshot, () => true);
  const form = useRef<HTMLFormElement>(null);
  const buttons = useRef<Partial<Record<Label, HTMLButtonElement | null>>>({});
  const noteId = `label-note-${itemId}`;

  // p / n / s submit with the matching button while focus is inside this item (or on no
  // element at all, as after a page load), never from a text field or elsewhere on the page.
  useEffect(() => {
    if (!shortcuts) return;
    function onKey(e: KeyboardEvent) {
      if (e.ctrlKey || e.metaKey || e.altKey || e.repeat || pending) return;
      const target = e.target as HTMLElement | null;
      const scope = form.current?.closest("article");
      if (!target || !scope) return;
      if (target !== document.body && !scope.contains(target)) return;
      if (target.closest("input, textarea, select, [contenteditable]")) return;
      const label = KEYS[e.key.toLowerCase()];
      const button = label && buttons.current[label];
      if (!button || !form.current) return;
      e.preventDefault();
      form.current.requestSubmit(button);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending, shortcuts]);

  return (
    <form ref={form} action={action} className="mt-6 space-y-3">
      <input type="hidden" name="raw_item_id" value={itemId} />
      <input type="hidden" name="set" value={set} />
      <div>
        <label htmlFor={noteId} className="block text-sm font-medium">
          Note <span className={`font-normal ${muted}`}>(optional)</span>
        </label>
        <input
          id={noteId}
          key={itemId}
          type="text"
          name="note"
          maxLength={500}
          aria-describedby={`${noteId}-hint`}
          className="mt-1 w-full rounded border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700"
          onKeyDown={(e) => {
            // Enter would submit with the first button (Pain); make the choice explicit.
            if (e.key === "Enter") e.preventDefault();
            if (e.key === "Escape") e.currentTarget.blur();
          }}
        />
        <p id={`${noteId}-hint`} className={`mt-1 text-xs ${muted}`}>
          Enter does not submit; choose a label below. Esc leaves the field.
        </p>
      </div>
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
            aria-keyshortcuts={shortcuts ? b.key : undefined}
            className={`rounded px-4 py-2 text-sm font-medium disabled:opacity-50 ${b.className}`}
          >
            {b.text}
            {shortcuts && <kbd className="ml-1.5 font-mono text-xs" aria-hidden="true">{b.key}</kbd>}
          </button>
        ))}
      </div>
      <p className="text-sm">
        <button
          type="button"
          aria-pressed={shortcuts}
          onClick={() => writeShortcuts(!shortcuts)}
          className="rounded border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          Single-key shortcuts<span aria-hidden="true">: {shortcuts ? "on" : "off"}</span>
        </button>{" "}
        <span className={`text-xs ${muted}`}>
          {shortcuts ? "p, n and s label this item while focus is inside it." : "Single-key shortcuts are off."}
        </span>
      </p>
      <p
        aria-live="polite"
        className={`min-h-5 text-sm ${state.error ? "text-red-700 dark:text-red-400" : muted}`}
      >
        {pending ? "Saving…" : state.message}
      </p>
    </form>
  );
}
