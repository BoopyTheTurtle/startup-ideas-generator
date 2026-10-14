"use client";

import { useActionForm } from "@/components/use-action-form";
import { decideMerge, type MergeState } from "./actions";
import { NoImplicitSubmit, ReasonFields, buttonPrimary, buttonSecondary, muted } from "@/components/ui";
import { STATUS_RANK } from "@/lib/steering-shared";

const initial: MergeState = { message: "", error: false };

type Side = { id: number; title: string; status: string };

const name = (s: Side) => `"${s.title}" (problem ${s.id})`;

function mergeQuestion(keep: Side, drop: Side): string {
  const lines = [
    `Merge ${name(drop)} into ${name(keep)}?`,
    `Its members move to problem ${keep.id}; problem ${drop.id} becomes an alias.`,
  ];
  if ((STATUS_RANK[drop.status] ?? -1) > (STATUS_RANK[keep.status] ?? -1)) {
    lines.push(
      `Problem ${drop.id} is ${drop.status}, which outranks ${keep.status}: its status will carry over to problem ${keep.id}.`,
    );
  }
  return lines.join("\n\n");
}

export function MergeForm({ a, b, defaultKeep }: { a: Side; b: Side; defaultKeep: "a" | "b" }) {
  const { state, pending, action, ref, onSubmit } = useActionForm(decideMerge, initial);
  const prefix = `m-${a.id}-${b.id}`;
  return (
    <form ref={ref} action={action} onSubmit={onSubmit} className="space-y-3">
      <NoImplicitSubmit />
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
            <label key={key} className="flex min-w-0 items-start gap-2">
              <input
                type="radio"
                name="keep"
                value={key}
                defaultChecked={defaultKeep === key}
                className="mt-1"
              />
              <span className="break-words">
                {side.title} <span className={muted}>(problem {side.id}; the other one folds into it)</span>
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
          aria-disabled={pending || undefined}
          className={buttonPrimary}
          onClick={(e) => {
            if (pending) {
              e.preventDefault();
              return;
            }
            const form = e.currentTarget.form;
            const keep = form ? new FormData(form).get("keep") : null;
            const [k, d] = keep === "b" ? [b, a] : [a, b];
            if (!window.confirm(mergeQuestion(k, d))) e.preventDefault();
          }}
        >
          Approve merge
        </button>
        <button
          type="submit"
          name="decision"
          value="reject"
          aria-disabled={pending || undefined}
          className={buttonSecondary}
          onClick={(e) => {
            if (pending) {
              e.preventDefault();
              return;
            }
            if (!window.confirm(`Keep ${name(a)} and ${name(b)} apart? The pair leaves the merge queue.`)) {
              e.preventDefault();
            }
          }}
        >
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
