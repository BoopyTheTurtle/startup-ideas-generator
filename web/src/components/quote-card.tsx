import type { Quote } from "@/lib/radar";
import { plainText, safeUrl } from "@/lib/plaintext";
import { EVIDENCE, fmtDate } from "@/lib/steering-shared";

// One pain as evidence: the quote as the source said it (or a labeled paraphrase), where
// and when it was said, with a link to the original. The model's reading of it (problem,
// who, workaround, cost) sits apart and is labeled as extracted, never as a quote.
export function QuoteCard({ q }: { q: Quote }) {
  const url = safeUrl(q.url);
  const ev = EVIDENCE[q.evidence_level];
  const meta = [
    q.created_at ? `posted ${fmtDate(q.created_at)}` : null,
    `fetched ${fmtDate(q.fetched_at)}`,
    q.country,
    q.lang,
  ].filter(Boolean);
  return (
    <article className="rounded border border-zinc-200 p-4 dark:border-zinc-800">
      <p className="text-xs text-zinc-600 dark:text-zinc-400">
        <span className="font-medium text-zinc-800 dark:text-zinc-200">{q.source}</span>
        {" · "}
        {meta.join(" · ")}
        {" · "}
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer" className="underline">
            original<span className="sr-only"> (item {q.raw_item_id}, opens in a new tab)</span>
          </a>
        ) : (
          <span>item {q.raw_item_id}, no link</span>
        )}
      </p>
      <figure className="mt-2">
        <figcaption className="text-xs font-medium uppercase tracking-wide text-zinc-600 dark:text-zinc-400">
          {q.quote_kind === "verbatim" ? "Verbatim quote" : "Paraphrase (the source keeps no text)"}
        </figcaption>
        <blockquote
          className={`mt-1 whitespace-pre-wrap break-words border-l-2 pl-3 text-sm leading-6 ${
            q.quote_kind === "verbatim"
              ? "border-zinc-400 dark:border-zinc-500"
              : "border-dashed border-zinc-300 italic dark:border-zinc-700"
          }`}
        >
          {plainText(q.quote)}
        </blockquote>
      </figure>
      <p className="mt-3 flex flex-wrap gap-2 text-xs">
        <span
          className="rounded bg-zinc-100 px-2 py-0.5 dark:bg-zinc-800"
          title={ev?.long}
        >
          <span className="font-medium">{q.evidence_level}</span> {ev?.short ?? "unknown"}
        </span>
        <span className="rounded bg-zinc-100 px-2 py-0.5 dark:bg-zinc-800">
          intensity <span className="font-medium tabular-nums">{q.intensity}</span>/5
        </span>
      </p>
      <p className="mt-3 text-xs font-medium uppercase tracking-wide text-zinc-600 dark:text-zinc-400">
        Model extraction, in English
      </p>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-zinc-600 dark:text-zinc-400">
        <dt className="font-medium">Problem</dt>
        <dd className="break-words">{q.problem}</dd>
        <dt className="font-medium">Who</dt>
        <dd className="break-words">{q.who}</dd>
        {q.workaround && (
          <>
            <dt className="font-medium">Workaround</dt>
            <dd className="break-words">{q.workaround}</dd>
          </>
        )}
        {q.cost_cue && (
          <>
            <dt className="font-medium">Cost</dt>
            <dd className="break-words">{q.cost_cue}</dd>
          </>
        )}
      </dl>
    </article>
  );
}

// A compact quote for lists of themes and merge pairs: the quote, its kind, source, date,
// evidence and intensity, and the link to the original.
export function QuoteSnippet({ q }: { q: Quote }) {
  const url = safeUrl(q.url);
  const ev = EVIDENCE[q.evidence_level];
  return (
    <figure className="text-sm">
      <blockquote
        className={`whitespace-pre-wrap break-words border-l-2 pl-3 leading-6 ${
          q.quote_kind === "verbatim"
            ? "border-zinc-400 dark:border-zinc-500"
            : "border-dashed border-zinc-300 italic dark:border-zinc-700"
        }`}
      >
        <span className="line-clamp-4">{plainText(q.quote)}</span>
      </blockquote>
      <figcaption className="mt-1 pl-3 text-xs text-zinc-600 dark:text-zinc-400">
        {q.quote_kind === "verbatim" ? "verbatim" : "paraphrase"} · {q.source} ·{" "}
        {fmtDate(q.created_at ?? q.fetched_at)} · <span title={ev?.long}>{q.evidence_level} {ev?.short}</span>{" "}
        · intensity {q.intensity}/5
        {url && (
          <>
            {" · "}
            <a href={url} target="_blank" rel="noopener noreferrer" className="underline">
              original<span className="sr-only"> (opens in a new tab)</span>
            </a>
          </>
        )}
      </figcaption>
    </figure>
  );
}

export function QuoteList({ quotes, total }: { quotes: Quote[]; total?: number }) {
  if (quotes.length === 0) {
    return <p className="text-sm text-zinc-600 dark:text-zinc-400">No quotes.</p>;
  }
  return (
    <>
      {total !== undefined && total > quotes.length && (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Showing {quotes.length} of {total}: verbatim first, then stronger evidence and higher
          intensity.
        </p>
      )}
      <ul className="mt-3 space-y-3">
        {quotes.map((q) => (
          <li key={q.pain_id}>
            <QuoteCard q={q} />
          </li>
        ))}
      </ul>
    </>
  );
}
