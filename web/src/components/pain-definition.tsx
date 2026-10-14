// The labeling definition, worded once for /label and /audit.
export function PainDefinition() {
  return (
    <div className="mt-4 rounded border border-zinc-200 p-4 text-sm dark:border-zinc-800">
      <p>
        <span className="font-medium">Pain:</span> a problem many people share that someone
        could build a business around. Petitions and demands count when a group suffers the
        problem behind them.
      </p>
      <p className="mt-2">
        <span className="font-medium">Not pain:</span> one person&apos;s bug report or support
        question; a single product decision users can avoid; news, opinions, praise, jokes, spam.
      </p>
    </div>
  );
}
