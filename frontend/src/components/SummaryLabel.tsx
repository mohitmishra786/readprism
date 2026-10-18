// Labels who wrote a summary (#177): readers should know when it is AI text.
export function SummaryLabel({ source }: { source?: string | null }) {
  if (source !== "llm") return null;
  return (
    <span
      className="mr-2 inline-block rounded bg-stone-100 px-1.5 py-0.5 align-middle font-sans text-[10px] font-semibold uppercase tracking-wide not-italic text-stone-500 dark:bg-stone-800 dark:text-stone-400"
      title="Written by an AI model from the article. It can contain mistakes."
    >
      AI summary
    </span>
  );
}
