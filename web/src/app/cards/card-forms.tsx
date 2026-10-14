"use client";

import { decideOnCard, type CardState } from "./actions";
import { useActionForm } from "@/components/use-action-form";
import {
  NoImplicitSubmit,
  ReasonFields,
  buttonDanger,
  buttonPrimary,
  buttonSecondary,
  muted,
} from "@/components/ui";

const initial: CardState = { message: "", error: false };

function Message({ state, pending }: { state: CardState; pending: boolean }) {
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

// aria-disabled, not disabled: a button keeps focus while a save is pending.
function guarded(pending: boolean, question: string) {
  return (e: React.MouseEvent<HTMLButtonElement>) => {
    if (pending || !window.confirm(question)) e.preventDefault();
  };
}

export function DecisionForm({ cardId, title }: { cardId: number; title: string }) {
  const { state, pending, action, ref, onSubmit } = useActionForm(decideOnCard, initial);
  return (
    <form ref={ref} action={action} onSubmit={onSubmit} className="space-y-3" aria-describedby="decision-help">
      <NoImplicitSubmit />
      <input type="hidden" name="card_id" value={cardId} />
      <div id="decision-help" className={`space-y-1 text-sm ${muted}`}>
        <p>
          <strong className="font-medium text-zinc-900 dark:text-zinc-100">Approve</strong> lets a
          builder implement this card on its own branch. Nothing merges without your later merge
          approval.
        </p>
        <p>
          <strong className="font-medium text-zinc-900 dark:text-zinc-100">Reject</strong> closes the
          card. The auditor may not propose the same change again for 28 days.
        </p>
      </div>
      <ReasonFields idPrefix="card-decision" />
      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          name="action"
          value="approve"
          aria-disabled={pending || undefined}
          className={buttonPrimary}
          onClick={guarded(pending, `Approve card ${cardId}, "${title}"? A builder may then implement it.`)}
        >
          Approve card
        </button>
        <button
          type="submit"
          name="action"
          value="reject"
          aria-disabled={pending || undefined}
          className={buttonDanger}
          onClick={guarded(pending, `Reject card ${cardId}, "${title}"? It closes.`)}
        >
          Reject card
        </button>
      </div>
      <Message state={state} pending={pending} />
    </form>
  );
}

export function MergeApprovalForm({
  cardId,
  approved,
  heldoutPending,
}: {
  cardId: number;
  approved: boolean;
  heldoutPending: boolean;
}) {
  const { state, pending, action, ref, onSubmit } = useActionForm(decideOnCard, initial);
  return (
    <form ref={ref} action={action} onSubmit={onSubmit} className="space-y-3" aria-describedby="merge-help">
      <input type="hidden" name="card_id" value={cardId} />
      <div id="merge-help" className={`space-y-1 text-sm ${muted}`}>
        {approved ? (
          <p>
            <strong className="font-medium text-zinc-900 dark:text-zinc-100">Withdraw approval</strong>{" "}
            clears your merge approval. The merge command then refuses until you approve again.
          </p>
        ) : (
          <p>
            <strong className="font-medium text-zinc-900 dark:text-zinc-100">Approve merge</strong>{" "}
            allows the merge command to land this branch on its base branch. The app does not merge:
            you or Claude run the command afterwards.
          </p>
        )}
        {!approved && heldoutPending && (
          <p>The merge also needs a passing held-out check, recorded above.</p>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {approved ? (
          <button
            type="submit"
            name="action"
            value="merge-withdraw"
            aria-disabled={pending || undefined}
            className={buttonSecondary}
            onClick={guarded(pending, `Withdraw the merge approval for card ${cardId}?`)}
          >
            Withdraw merge approval
          </button>
        ) : (
          <button
            type="submit"
            name="action"
            value="merge-approve"
            aria-disabled={pending || undefined}
            className={buttonPrimary}
            onClick={guarded(
              pending,
              `Approve merging card ${cardId}? The branch can then land on its base branch.`,
            )}
          >
            Approve merge
          </button>
        )}
      </div>
      <Message state={state} pending={pending} />
    </form>
  );
}

export function HeldoutForm({ cardId, check }: { cardId: number; check: string }) {
  const { state, pending, action, ref, onSubmit } = useActionForm(decideOnCard, initial);
  return (
    <form ref={ref} action={action} onSubmit={onSubmit} className="space-y-3" aria-describedby="heldout-help">
      <input type="hidden" name="card_id" value={cardId} />
      <input type="hidden" name="action" value="heldout" />
      <p id="heldout-help" className={`text-sm ${muted}`}>
        The app records your verdict only. It never reads the held-out set or its results. Currently:{" "}
        <strong className="font-medium text-zinc-900 dark:text-zinc-100">{check}</strong>.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          name="verdict"
          value="pass"
          aria-disabled={pending || check === "pass" || undefined}
          className={buttonPrimary}
          onClick={(e) => {
            if (check === "pass") e.preventDefault();
            else guarded(pending, `Record the held-out check on card ${cardId} as PASS?`)(e);
          }}
        >
          Record pass
          {check === "pass" && <span className="sr-only"> (current)</span>}
        </button>
        <button
          type="submit"
          name="verdict"
          value="fail"
          aria-disabled={pending || check === "fail" || undefined}
          className={buttonDanger}
          onClick={(e) => {
            if (check === "fail") e.preventDefault();
            else guarded(pending, `Record the held-out check on card ${cardId} as FAIL?`)(e);
          }}
        >
          Record fail
          {check === "fail" && <span className="sr-only"> (current)</span>}
        </button>
      </div>
      <Message state={state} pending={pending} />
    </form>
  );
}
