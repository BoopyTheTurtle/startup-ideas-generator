import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { cardDetail, type CardDetail } from "@/lib/cards";
import { MAX_BUILDS_PER_WEEK, SIZE_NAMES, STATUS_INFO, fmtNumber, isCardStatus } from "@/lib/cards-shared";
import { fmtDateTime, REASONS } from "@/lib/steering-shared";
import { CardStatusBadge, Chip } from "@/components/card-status";
import { FocusOnMount } from "@/components/focus-on-mount";
import { BackLink, card as panel, muted } from "@/components/ui";
import { DecisionForm, HeldoutForm, MergeApprovalForm } from "../card-forms";

type Params = Promise<{ id: string }>;
type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function parseId(raw: string): number | null {
  const id = Number(raw);
  return /^\d{1,9}$/.test(raw) && Number.isSafeInteger(id) && id > 0 ? id : null;
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const id = parseId((await params).id);
  const detail = id === null ? null : await cardDetail(id);
  return { title: detail ? `${detail.card.title} (card ${detail.card.id})` : "Card not found" };
}

export default function CardPage({ params, searchParams }: { params: Params; searchParams: SearchParams }) {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-8">
      <BackLink href="/cards">Cards</BackLink>
      <Suspense fallback={<p className={`mt-4 text-sm ${muted}`}>Loading card…</p>}>
        <Card params={params} searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

function Cmd({ children }: { children: string }) {
  return (
    <code className="rounded bg-zinc-100 px-1 py-0.5 text-[13px] break-all dark:bg-zinc-800">{children}</code>
  );
}

const startCmds = (id: number) => (
  <>
    tell Claude to run <Cmd>{`/improve ${id}`}</Cmd>, or run <Cmd>{`uv run python -m pipeline card-start ${id}`}</Cmd>
  </>
);

// What each completed action tells Edgar to do next. Codes arrive in the URL; no free text does.
function outcomeText(code: string, d: CardDetail): React.ReactNode {
  const { id, base_branch } = d.card;
  switch (code) {
    case "approved":
      return <>Card {id} approved. Next: {startCmds(id)}.</>;
    case "rejected":
      return <>Card {id} rejected. It is closed.</>;
    case "merge-approved":
      return (
        <>
          Merge of card {id} approved. Next: from the main checkout, with <Cmd>{base_branch ?? "dev"}</Cmd>{" "}
          checked out, run <Cmd>{`uv run python -m pipeline card-merge ${id}`}</Cmd>.
        </>
      );
    case "merge-withdrawn":
      return <>Merge approval for card {id} withdrawn. The merge command refuses until you approve again.</>;
    case "heldout-pass":
      return <>Held-out check on card {id} recorded as pass.</>;
    case "heldout-fail":
      return (
        <>
          Held-out check on card {id} recorded as fail. The merge is blocked. Tell Claude to rework the
          card or abandon it.
        </>
      );
    default:
      return null;
  }
}

async function Card({ params, searchParams }: { params: Params; searchParams: SearchParams }) {
  const id = parseId((await params).id);
  if (id === null) notFound();
  const d = await cardDetail(id);
  if (!d) notFound();
  const { card: c } = d;
  const done = (await searchParams).done;
  const outcome = typeof done === "string" ? outcomeText(done, d) : null;
  const status = isCardStatus(c.status) ? c.status : null;

  return (
    <>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight break-words">{c.title}</h1>
      <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <CardStatusBadge status={c.status} />
        <Chip>kind: {c.kind}</Chip>
        <Chip>touches: {c.touches}</Chip>
        <Chip>size: {c.size} ({SIZE_NAMES[c.size] ?? c.size})</Chip>
        <Chip>value: {c.value} of 5</Chip>
        <Chip>rank: {c.rank_score.toFixed(2)}</Chip>
        <span className={muted}>
          Card {c.id} · proposed by {c.proposed_by} in {c.week}
        </span>
      </p>
      {status && <p className={`mt-1 text-sm ${muted}`}>{STATUS_INFO[status].blurb}</p>}
      {outcome && (
        <FocusOnMount
          key={String(done)}
          className="mt-4 rounded bg-green-50 p-3 text-sm break-words text-green-900 outline-none focus-visible:outline-2 dark:bg-green-950 dark:text-green-200"
        >
          {outcome}
        </FocusOnMount>
      )}
      {c.reverts_card_id !== null && (
        <p className="mt-3 text-sm">
          This card reverts{" "}
          <Link href={`/cards/${c.reverts_card_id}`} className="underline">
            card {c.reverts_card_id}
            {d.reverts ? `: ${d.reverts.title}` : ""}
          </Link>
          .
        </p>
      )}
      {d.revertedBy.length > 0 && (
        <p className="mt-3 text-sm">
          Reverted by{" "}
          {d.revertedBy.map((r, i) => (
            <span key={r.id}>
              {i > 0 && ", "}
              <Link href={`/cards/${r.id}`} className="underline">
                card {r.id}: {r.title}
              </Link>{" "}
              ({r.status})
            </span>
          ))}
          .
        </p>
      )}

      <NextStep d={d} />
      <Proposal d={d} />
      <Build d={d} />
      <Timeline d={d} />
    </>
  );
}

function NextStep({ d }: { d: CardDetail }) {
  const { card: c } = d;
  const capFull = d.buildsThisWeek >= MAX_BUILDS_PER_WEEK && c.kind !== "revert";
  const capNote =
    c.kind === "revert"
      ? "Revert cards do not count toward the weekly build cap."
      : `Builds started in ${d.week}: ${d.buildsThisWeek} of ${MAX_BUILDS_PER_WEEK}.${
          capFull ? " The cap is reached, so this card waits until next week to build." : ""
        }`;
  const needsHeldout = c.needs_heldout === 1 && (c.status === "built" || c.status === "ready");
  const mergeReady = c.status === "ready" && c.review_verdict === "approve";

  let body: React.ReactNode = null;
  switch (c.status) {
    case "proposed":
      body = (
        <>
          <p className="text-sm">
            {capNote}
          </p>
          <div className="mt-3">
            <DecisionForm cardId={c.id} title={c.title} />
          </div>
        </>
      );
      break;
    case "approved":
      body = (
        <p className="text-sm">
          Approved {fmtDateTime(c.decided_at)} UTC. Next: {startCmds(c.id)}.{" "}
          {capNote}
        </p>
      );
      break;
    case "building":
      body = (
        <p className="text-sm">
          A builder is working on branch <Cmd>{c.branch ?? "(not recorded)"}</Cmd>. Nothing for you to do until
          it passes <Cmd>{`uv run python -m pipeline card-verify ${c.id}`}</Cmd>.
        </p>
      );
      break;
    case "built":
      body = (
        <p className="text-sm">
          The branch passed its checks. Next the reviewer signs off (
          <Cmd>{`card-review ${c.id}`}</Cmd>); you are asked for a merge approval once it does.
          {needsHeldout && " You can record the held-out check now."}
        </p>
      );
      break;
    case "ready":
      body = (
        <p className="text-sm">
          The reviewer {c.review_verdict === "approve" ? "approved" : "has not approved"} this branch.
          {c.merge_approved_at ? (
            <>
              {" "}
              You approved the merge {fmtDateTime(c.merge_approved_at)} UTC. Next: from the main checkout,
              with <Cmd>{c.base_branch ?? "dev"}</Cmd> checked out, run{" "}
              <Cmd>{`uv run python -m pipeline card-merge ${c.id}`}</Cmd>.
            </>
          ) : (
            " Approve the merge below when you are ready for it to land."
          )}
        </p>
      );
      break;
    case "merged":
      body = (
        <p className="text-sm">
          Merged {fmtDateTime(c.merged_at)} UTC at <Cmd>{c.merged_sha?.slice(0, 12) ?? "unknown"}</Cmd>.
          {d.baseline ? (
            <>
              {" "}
              Baseline at merge: <Cmd>{d.baseline.metric}</Cmd>
              {d.baseline.subject && <> ({d.baseline.subject})</>} was {fmtNumber(d.baseline.value)} in run{" "}
              {d.baseline.run_id}; the card expected it to go {d.baseline.direction ?? "(no direction)"}. A
              regression opens a revert card.
            </>
          ) : (
            " No baseline was recorded, so no regression check runs."
          )}
        </p>
      );
      break;
  }
  const decided = c.decided_at && (
    <p className={`mt-2 text-sm ${muted}`}>
      Decision {fmtDateTime(c.decided_at)} UTC:{" "}
      {REASONS.find((r) => r.code === c.decision_reason)?.label ?? c.decision_reason ?? "no reason recorded"}
      {c.decision_note ? ` | ${c.decision_note}` : ""}
    </p>
  );
  if (c.status === "rejected") {
    body = <p className="text-sm">Rejected. Nothing more to do.</p>;
  } else if (c.status === "abandoned") {
    body = <p className="text-sm">Abandoned while in flight; the reason is in the timeline below.</p>;
  } else if (c.status === "reverted") {
    body = <p className="text-sm">Merged, then reverted by a later card (see above).</p>;
  }

  return (
    <section aria-labelledby="next-heading" className={`mt-6 ${panel}`}>
      <h2 id="next-heading" className="text-lg font-medium">
        {c.status === "proposed" ? "Your decision" : "Where this stands"}
      </h2>
      <div className="mt-2">{body}</div>
      {c.status !== "proposed" && decided}
      {needsHeldout && (
        <div className="mt-5 border-t border-zinc-200 pt-4 dark:border-zinc-800">
          <h3 className="font-medium">Held-out check</h3>
          <p className="mt-1 text-sm">
            This card changes extraction, so a gain on the working set could be overfitting. Run the
            comparison yourself, outside the app:
          </p>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
            <li>
              In the card&apos;s worktree{c.worktree_path && <> (<Cmd>{c.worktree_path}</Cmd>)</>} with branch{" "}
              <Cmd>{c.branch ?? "(not recorded)"}</Cmd> checked out, run{" "}
              <Cmd>uv run python -m pipeline extract --labeled &lt;held-out set&gt; --reextract --max-items 150</Cmd>.
            </li>
            <li>
              Then run <Cmd>uv run python -m pipeline eval --set &lt;held-out set&gt;</Cmd>.
            </li>
            <li>
              Compare that score with the base prompt&apos;s score on the same set
              {c.base_extract_version && <> (base prompt version <Cmd>{c.base_extract_version}</Cmd>)</>}. Score the base
              first if you have not.
            </li>
            <li>Record pass or fail here. Anything but a pass blocks the merge.</li>
          </ol>
          <p className={`mt-2 text-sm ${muted}`}>
            &lt;held-out set&gt; is the name of your held-out set, the one behind the Held-out tab on the Label
            page. The extract step spends your Claude subscription; the item cap bounds it.
          </p>
          <div className="mt-3">
            <HeldoutForm cardId={c.id} check={c.heldout_check} />
          </div>
        </div>
      )}
      {mergeReady && (
        <div className="mt-5 border-t border-zinc-200 pt-4 dark:border-zinc-800">
          <h3 className="font-medium">Merge approval</h3>
          <p className="mt-1 text-sm">
            Approval covers branch head <Cmd>{c.head_sha?.slice(0, 12) ?? "unknown"}</Cmd>. If the builder changes
            the branch, verifying again clears your approval.
          </p>
          <div className="mt-3">
            <MergeApprovalForm
              cardId={c.id}
              approved={Boolean(c.merge_approved_at)}
              heldoutPending={c.needs_heldout === 1 && c.heldout_check !== "pass"}
            />
          </div>
        </div>
      )}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-sm font-medium">{label}</dt>
      <dd className="mt-0.5 text-sm break-words whitespace-pre-wrap">{children}</dd>
    </div>
  );
}

function Proposal({ d }: { d: CardDetail }) {
  const { card: c } = d;
  return (
    <section aria-labelledby="proposal-heading" className="mt-8">
      <h2 id="proposal-heading" className="text-lg font-medium">
        The proposal
      </h2>
      <dl className="mt-3 space-y-4">
        <Field label="Observation">{c.observation}</Field>
      </dl>
      <h3 className="mt-5 text-sm font-medium">Evidence</h3>
      {d.evidence.length === 0 ? (
        <p className={`mt-1 text-sm ${muted}`}>No evidence recorded.</p>
      ) : (
        <div className="mt-1 overflow-x-auto" tabIndex={0} role="region" aria-label="Evidence table">
          <table className="w-full min-w-[30rem] text-left text-sm">
            <caption className="sr-only">Metric values behind the observation</caption>
            <thead className={muted}>
              <tr>
                <th scope="col" className="py-2 pr-4 font-medium">Metric</th>
                <th scope="col" className="py-2 pr-4 font-medium">Subject</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Value</th>
                <th scope="col" className="py-2 text-right font-medium">Run</th>
              </tr>
            </thead>
            <tbody>
              {d.evidence.map((e, i) => (
                <tr key={i} className="border-t border-zinc-200 align-top dark:border-zinc-800">
                  <th scope="row" className="py-2 pr-4 font-normal break-words">{e.metric}</th>
                  <td className="py-2 pr-4 break-words">{e.subject || <span className={muted}>–</span>}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{e.value}</td>
                  <td className="py-2 text-right tabular-nums">{e.run_id || "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <dl className="mt-5 space-y-4">
        <Field label="Hypothesis">{c.hypothesis}</Field>
        <Field label="Proposed change">{c.change}</Field>
        <Field label="Expected effect">
          {c.expected_effect}
          {c.expected_metric && (
            <span className="mt-1 block">
              <span className={muted}>Metric: </span>
              <Cmd>{c.expected_metric}</Cmd>
              {c.expected_subject && <> ({c.expected_subject})</>}
              {c.expected_direction && <> should go {c.expected_direction}</>}
            </span>
          )}
        </Field>
        <Field label="Risk">{c.risk}</Field>
      </dl>
    </section>
  );
}

function Build({ d }: { d: CardDetail }) {
  const { card: c, verify: v } = d;
  if (!c.branch && !c.verify_json && !c.review_verdict) return null;
  return (
    <section aria-labelledby="build-heading" className="mt-8">
      <h2 id="build-heading" className="text-lg font-medium">
        Build, checks and review
      </h2>
      <dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2">
        <Field label="Branch">{c.branch ? <Cmd>{c.branch}</Cmd> : "(not recorded)"}</Field>
        <Field label="Base">
          {c.base_branch ? (
            <>
              <Cmd>{c.base_branch}</Cmd> at <Cmd>{c.base_sha?.slice(0, 12) ?? "unknown"}</Cmd>
            </>
          ) : (
            "(not recorded)"
          )}
        </Field>
        <Field label="Head">{c.head_sha ? <Cmd>{c.head_sha.slice(0, 12)}</Cmd> : "(not verified yet)"}</Field>
        <Field label="Build started">{c.build_week ?? "(not started)"}</Field>
        {c.needs_heldout === 1 && <Field label="Held-out check">{c.heldout_check}</Field>}
      </dl>

      <h3 className="mt-5 text-sm font-medium">Verification</h3>
      {v === null ? (
        <p className={`mt-1 text-sm ${muted}`}>Not verified yet.</p>
      ) : (
        <div className="mt-1 space-y-2 text-sm">
          {v.problems.length === 0 ? (
            <p>
              <span aria-hidden="true">✓ </span>No problems found.
            </p>
          ) : (
            <div>
              <p className="font-medium text-red-700 dark:text-red-400">
                <span aria-hidden="true">✗ </span>
                {v.problems.length} {v.problems.length === 1 ? "problem" : "problems"}:
              </p>
              <ul className="list-disc pl-5">
                {v.problems.map((p, i) => (
                  <li key={i} className="break-words">{p}</li>
                ))}
              </ul>
            </div>
          )}
          {v.tests && (
            <p className="break-words">
              Tests: {v.tests.passed ? "passed" : "failed"}
              {v.tests.tail && <span className={`block font-mono text-xs whitespace-pre-wrap ${muted}`}>{v.tests.tail}</span>}
            </p>
          )}
          {v.eval_diff && (
            <p className="tabular-nums">
              Working-set F1: base {fmtNumber(v.eval_diff.base_f1)} ({v.eval_diff.base_version ?? "?"}) to
              candidate {fmtNumber(v.eval_diff.candidate_f1)} ({v.eval_diff.candidate_version ?? "?"}).
            </p>
          )}
          {v.changed && (
            <details>
              <summary className="cursor-pointer">{v.changed.length} files changed</summary>
              <ul className="mt-1 list-disc pl-5 font-mono text-xs break-all">
                {v.changed.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      <h3 className="mt-5 text-sm font-medium">Review</h3>
      {c.review_verdict === null ? (
        <p className={`mt-1 text-sm ${muted}`}>No review yet.</p>
      ) : (
        <p className="mt-1 text-sm break-words whitespace-pre-wrap">
          <span className="font-medium">Verdict: {c.review_verdict}.</span> {c.review_notes}
        </p>
      )}
    </section>
  );
}

function Timeline({ d }: { d: CardDetail }) {
  return (
    <section aria-labelledby="timeline-heading" className="mt-8">
      <h2 id="timeline-heading" className="text-lg font-medium">
        Timeline
      </h2>
      {d.events.length === 0 ? (
        <p className={`mt-1 text-sm ${muted}`}>No events recorded.</p>
      ) : (
        <ol className="mt-2 space-y-2 text-sm">
          {d.events.map((e) => (
            <li key={e.id} className="border-l-2 border-zinc-300 pl-3 dark:border-zinc-700">
              <span className={`tabular-nums ${muted}`}>{fmtDateTime(e.at)} UTC</span>{" "}
              <span className="font-medium">{e.actor}</span>: {e.event}
              {e.note && <span className={`block break-words ${muted}`}>{e.note}</span>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
