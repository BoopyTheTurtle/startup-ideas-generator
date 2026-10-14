import { LabelForm } from "./label-form";
import type { LabelItem } from "@/lib/labeling";
import type { FormSet } from "@/lib/labels";
import { plainText, safeUrl } from "@/lib/plaintext";
import { muted } from "@/components/ui";

// One item to label: source line, title, plain-text body, and the label form. Never shows
// model output or an earlier label.
export function ItemView({ item, set }: { item: LabelItem; set: FormSet }) {
  const url = safeUrl(item.url);
  const body = plainText(item.body);
  const meta = [
    item.lang && `language ${item.lang}`,
    item.country && `country ${item.country}`,
    item.created_at && `posted ${item.created_at.slice(0, 10)}`,
  ].filter(Boolean);
  return (
    <article className="mt-6 rounded border border-zinc-200 p-4 dark:border-zinc-800">
      <p className={`text-xs ${muted}`}>
        <span className="font-medium text-zinc-700 dark:text-zinc-300">{item.source}</span>
        {" · "}item {item.id}
        {meta.length > 0 && ` · ${meta.join(" · ")}`}
        {url && (
          <>
            {" · "}
            <a href={url} target="_blank" rel="noopener noreferrer" className="underline">
              original<span className="sr-only"> (opens in a new tab)</span>
            </a>
          </>
        )}
      </p>
      {item.title && <h2 className="mt-2 text-lg font-medium">{plainText(item.title)}</h2>}
      <div
        tabIndex={0}
        role="region"
        aria-label={`Text of item ${item.id}`}
        className="mt-3 max-h-[28rem] overflow-y-auto whitespace-pre-wrap break-words text-sm leading-6"
      >
        {body || <span className={muted}>(no body)</span>}
      </div>
      {/* No model output in either set: labels are what the model is scored against. */}
      <LabelForm itemId={item.id} set={set} />
    </article>
  );
}
