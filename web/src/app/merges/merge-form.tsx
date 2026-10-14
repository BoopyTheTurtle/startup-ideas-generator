"use client";

import { useActionForm } from "@/components/use-action-form";
import { decideMerge, type MergeState } from "./actions";
import { ReasonFields, buttonPrimary, buttonSecondary, muted } from "@/components/ui";

const initial: MergeState = { message: "", error: false };

type Side = { id: number; title: string };

export function MergeForm({ a, b, defaultKeep }: { a: Side; b: Side; defaultKeep: "a" | "b" }) {
  const { state, pending, action, ref, onSubmit } = useActionForm(decideMerge, initial);
  const prefix = `m-${a.id}-${b.id}`;
  return (
    <form ref={ref} action={action} onSubmit={onSubmit} className="space-y-3">
      <input type="hidden" name="a_id" value={a.id} />
      <input type="hidden" name="b_id" value={b.id} />
      <fieldset>
        <legend className="text-sm font-medium">If merged, keep</legend>
        <div className="mt-1 flex flex-col gap-1 text-sm sm:flex-row sm:gap-6">
          {(
            [
              ["a", a],
              ["b", b],
            ] as const
          ).map(([key, side]) => (
            <label key={key} className="flex items-start gap-2">
              <input
                type="radio"
                name="keep"
                value={key}
                defaultChecked={defaultKeep === key}
                className="mt-1"
              />
              <span>
                problem {side.id}{" "}
                <span className={muted}>(the other one folds into it)</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <ReasonFields idPrefix={prefix} />
      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          name="decision"
          value="approve"
          disabled={pending}
          className={buttonPrimary}
          onClick={(e) => {
            const form = e.currentTarget.form;
            const keep = form ? new FormData(form).get("keep") : null;
            const [k, d] = keep === "b" ? [b, a] : [a, b];
            if (!window.confirm(`Merge problem ${d.id} into problem ${k.id}? Members move to ${k.id}; ${d.id} becomes an alias.`)) {
              e.preventDefault();
            }
          }}
        >
          Approve merge
        </button>
        <button type="submit" name="decision" value="reject" disabled={pending} className={buttonSecondary}>
          Keep apart
        </button>
      </div>
      <p
        role="status"
        aria-live="polite"
        className={`min-h-5 whitespace-pre-wrap break-words text-sm ${state.error ? "text-red-700 dark:text-red-400" : muted}`}
      >
        {pending ? "Working… a merge runs the pipeline CLI and can take a few seconds." : state.message}
      </p>
    </form>
  );
}
