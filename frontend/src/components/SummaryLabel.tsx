// Labels who wrote a summary: readers should know when it is AI text (#177),
// and when it is a quick excerpt because no model ran (#261).
const LABELS: Record<string, { text: string; title: string }> = {
  llm: { text: "AI summary", title: "Written by an AI model from the article. It can contain mistakes." },
  extractive: {
    text: "Quick summary",
    title: "Sentences taken from the article itself (the ones closest to its title), picked without an AI model.",
  },
};

export function SummaryLabel({ source, fromTranscript = false }: { source?: string | null; fromTranscript?: boolean }) {
  const base = source ? LABELS[source] : undefined;
  if (!base) return null;
  // Episodes summarized from their own published transcript (#252).
  const label = fromTranscript
    ? { text: `${base.text} · transcript`, title: `${base.title} Based on the episode's published transcript.` }
    : base;
  return (
    <span
      className="mr-2 inline-block rounded bg-stone-100 px-1.5 py-0.5 align-middle font-sans text-[10px] font-semibold uppercase tracking-wide not-italic text-stone-500 dark:bg-stone-800 dark:text-stone-400"
      title={label.title}
    >
      {label.text}
    </span>
  );
}
