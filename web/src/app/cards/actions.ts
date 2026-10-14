"use server";

import { redirect } from "next/navigation";
import { decideCard, recordHeldoutCheck, setMergeApproval, type CardResult } from "@/lib/cards";
import { isHeldoutVerdict } from "@/lib/cards-shared";
import { NOTE_MAX, cleanText, isReasonCode } from "@/lib/steering-shared";

export type CardState = { message: string; error: boolean };

const ACTIONS = ["approve", "reject", "merge-approve", "merge-withdraw", "heldout"] as const;
type Action = (typeof ACTIONS)[number];

function isAction(v: unknown): v is Action {
  return typeof v === "string" && (ACTIONS as readonly string[]).includes(v);
}

// Localhost, one user, no session (SPEC v1 non-goal); the form is still untrusted input.
// The client names the card and the decision; the server re-reads the card's state inside
// the write. A success redirects to the card page with a short outcome code: the form that
// started the action usually leaves the page, so the page announces the result instead.
export async function decideOnCard(_prev: CardState, formData: FormData): Promise<CardState> {
  const action = formData.get("action");
  const id = Number(formData.get("card_id"));
  if (!isAction(action) || !Number.isSafeInteger(id) || id <= 0) {
    return { message: "Rejected: malformed submission.", error: true };
  }

  let result: CardResult;
  let done: string;
  try {
    if (action === "approve" || action === "reject") {
      const reason = formData.get("reason");
      if (!isReasonCode(reason)) return { message: "Choose a reason.", error: true };
      const note = cleanText(formData.get("note"), NOTE_MAX);
      result = decideCard(id, action, reason, note);
      done = action === "approve" ? "approved" : "rejected";
    } else if (action === "merge-approve" || action === "merge-withdraw") {
      result = setMergeApproval(id, action === "merge-approve");
      done = action === "merge-approve" ? "merge-approved" : "merge-withdrawn";
    } else {
      const verdict = formData.get("verdict");
      if (!isHeldoutVerdict(verdict)) return { message: "Choose pass or fail.", error: true };
      result = recordHeldoutCheck(id, verdict);
      done = `heldout-${verdict}`;
    }
  } catch (e) {
    return { message: `Not saved: ${e instanceof Error ? e.message : String(e)}`, error: true };
  }
  if (!result.ok) {
    // No refresh: the form (and this message) would unmount if the card has moved on.
    return { message: `${result.message} Reload the page to see the card's current state.`, error: true };
  }
  redirect(`/cards/${id}?done=${done}`);
}
