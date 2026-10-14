"use client";

import { steerProblem, type SteerState } from "../actions";
import { useActionForm } from "@/components/use-action-form";
import { ReasonFields, buttonPrimary, buttonSecondary, input, muted } from "@/components/ui";
import { TITLE_MAX, TITLE_MIN } from "@/lib/steering-shared";

const initial: SteerState = { message: "", error: false };

const STATUS_BUTTONS = [
  { action: "watch", label: "Watch", sets: "watching" },
  { action: "promote", label: "Promote", sets: "promoted" },
  { action: "archive", label: "Archive", sets: "archived" },
] as const;

function Message({ state, pending }: { state: SteerState; pending: boolean }) {
  return (
    <p
      role="status"
      aria-live="polite"
      className={`min-h-5 text-sm ${state.error ? "text-red-700 dark:text-red-400" : muted}`}
    >
      {pending ? "Saving…" : state.message}
    </p>
  );
}

export function SteerForm({ problemId, status }: { problemId: number; status: string }) {
  const { state, pending, action, ref, onSubmit } = useActionForm(steerProblem, initial);
  return (
    <form ref={ref} action={action} onSubmit={onSubmit} className="space-y-3" aria-describedby={`steer-help-${problemId}`}>
      <input type="hidden" name="problem_id" value={problemId} />
      <p id={`steer-help-${problemId}`} className={`text-sm ${muted}`}>
        Every action records a decision with its reason. Add note saves the note without changing
        the status.
      </p>
      <ReasonFields idPrefix="steer" />
      <div className="flex flex-wrap gap-2">
        {STATUS_BUTTONS.map((b) => (
          <button
            key={b.action}
            type="submit"
            name="action"
            value={b.action}
            disabled={pending || status === b.sets}
            className={buttonPrimary}
          >
            {b.label}
            {status === b.sets && <span className="sr-only"> (current status)</span>}
          </button>
        ))}
        <button type="submit" name="action" value="note" disabled={pending} className={buttonSecondary}>
          Add note
        </button>
      </div>
      <Message state={state} pending={pending} />
    </form>
  );
}

export function RenameForm({ problemId, title }: { problemId: number; title: string }) {
  const { state, pending, action, ref, onSubmit } = useActionForm(steerProblem, initial);
  return (
    <form ref={ref} action={action} onSubmit={onSubmit} className="space-y-3">
      <input type="hidden" name="problem_id" value={problemId} />
      <input type="hidden" name="action" value="rename" />
      <div>
        <label htmlFor="rename-title" className="block text-sm font-medium">
          New title <span className={`font-normal ${muted}`}>(job + outcome, no solution words)</span>
        </label>
        <input
          id="rename-title"
          name="title"
          type="text"
          required
          minLength={TITLE_MIN}
          maxLength={TITLE_MAX}
          defaultValue={title}
          key={title}
          className={`mt-1 ${input}`}
        />
      </div>
      <ReasonFields idPrefix="rename" />
      <button type="submit" disabled={pending} className={buttonSecondary}>
        Rename
      </button>
      <Message state={state} pending={pending} />
    </form>
  );
}
