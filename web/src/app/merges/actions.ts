"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { runMerge } from "@/lib/merge-cli";
import { mergeCandidate, rejectMerge } from "@/lib/steer";
import { NOTE_MAX, cleanText, isReasonCode } from "@/lib/steering-shared";

export type MergeState = { message: string; error: boolean };

const REASON_ARG_MAX = 300;

// The client names the pair, which side to keep, and the decision; the server checks
// the pair is still open before acting on it.
export async function decideMerge(_prev: MergeState, formData: FormData): Promise<MergeState> {
  const aId = Number(formData.get("a_id"));
  const bId = Number(formData.get("b_id"));
  const decision = formData.get("decision");
  const keepSide = formData.get("keep");
  const reason = formData.get("reason");
  if (
    !Number.isSafeInteger(aId) ||
    !Number.isSafeInteger(bId) ||
    aId <= 0 ||
    bId <= 0 ||
    (decision !== "approve" && decision !== "reject")
  ) {
    return { message: "Rejected: malformed submission.", error: true };
  }
  if (!isReasonCode(reason)) return { message: "Choose a reason.", error: true };
  const note = cleanText(formData.get("note"), NOTE_MAX);

  let candidate;
  try {
    candidate = mergeCandidate(aId, bId);
  } catch (e) {
    return { message: `Not saved: ${e instanceof Error ? e.message : String(e)}`, error: true };
  }
  if (!candidate) return { message: `No merge candidate ${aId}/${bId}.`, error: true };
  if (candidate.status !== "open") {
    refresh();
    return { message: `Merge candidate ${aId}/${bId} is already ${candidate.status}.`, error: true };
  }

  if (decision === "reject") {
    let res;
    try {
      res = rejectMerge(aId, bId, reason, note);
    } catch (e) {
      return { message: `Not saved: ${e instanceof Error ? e.message : String(e)}`, error: true };
    }
    if (!res.ok) return { message: res.message, error: true };
    // The pair leaves the queue, and its form with it, so the outcome travels in the URL.
    redirect(`/merges?kept=${aId}-${bId}`);
  }

  if (keepSide !== "a" && keepSide !== "b") {
    return { message: "Choose which problem to keep.", error: true };
  }
  const [keep, drop] = keepSide === "a" ? [aId, bId] : [bId, aId];
  const reasonArg = (note ? `${reason}: ${note}` : reason).slice(0, REASON_ARG_MAX);
  const res = await runMerge(keep, drop, reasonArg);
  if (!res.ok) return { message: res.message, error: true };
  redirect(`/merges?merged=${drop}-${keep}`);
}
