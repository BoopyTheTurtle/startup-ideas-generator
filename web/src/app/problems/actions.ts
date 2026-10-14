"use server";

import { refresh } from "next/cache";
import { addNote, rename, setStatus, type SteerResult } from "@/lib/steer";
import {
  NOTE_MAX,
  STATUS_ACTIONS,
  TITLE_MAX,
  TITLE_MIN,
  cleanText,
  isReasonCode,
  type StatusAction,
} from "@/lib/steering-shared";

export type SteerState = { message: string; error: boolean };

const ACTIONS = ["watch", "promote", "archive", "note", "rename"] as const;
type Action = (typeof ACTIONS)[number];

function isAction(v: unknown): v is Action {
  return typeof v === "string" && (ACTIONS as readonly string[]).includes(v);
}

function isStatusAction(a: Action): a is StatusAction {
  return a in STATUS_ACTIONS;
}

// Localhost, one user, no session (SPEC v1 non-goal); the form is still untrusted input.
// The client names the problem and the change; the server re-reads the problem's state.
export async function steerProblem(_prev: SteerState, formData: FormData): Promise<SteerState> {
  const action = formData.get("action");
  const reason = formData.get("reason");
  const id = Number(formData.get("problem_id"));
  if (!isAction(action) || !Number.isSafeInteger(id) || id <= 0) {
    return { message: "Rejected: malformed submission.", error: true };
  }
  if (!isReasonCode(reason)) return { message: "Choose a reason.", error: true };
  const note = cleanText(formData.get("note"), NOTE_MAX);

  let result: SteerResult;
  try {
    if (isStatusAction(action)) {
      result = setStatus(id, action, reason, note);
    } else if (action === "note") {
      if (!note) return { message: "Write a note first.", error: true };
      result = addNote(id, reason, note);
    } else {
      const title = cleanText(formData.get("title"), TITLE_MAX + 1);
      if (title.length < TITLE_MIN || title.length > TITLE_MAX) {
        return { message: `A title needs ${TITLE_MIN} to ${TITLE_MAX} characters.`, error: true };
      }
      result = rename(id, title, reason, note);
    }
  } catch (e) {
    return { message: `Not saved: ${e instanceof Error ? e.message : String(e)}`, error: true };
  }
  if (result.ok) refresh();
  return { message: result.message, error: !result.ok };
}
