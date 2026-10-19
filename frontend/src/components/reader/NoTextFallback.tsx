"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import type { ContentItemFull } from "../../lib/types";
import { FeedbackBar } from "../digest/FeedbackBar";
import { SummaryLabel } from "../SummaryLabel";

// Away at least this long counts as "went and read it".
const RETURN_PROMPT_AFTER_MS = 15_000;

const ANSWERS: { label: string; completion: number; reachedEnd: boolean }[] = [
  { label: "Yes, all of it", completion: 1, reachedEnd: true },
  { label: "About half", completion: 0.5, reachedEnd: false },
  { label: "Not really", completion: 0.15, reachedEnd: false },
];

export function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "the original site";
  }
}

// Reader view for items without in-app text: extraction failed, the item is
// paywalled, or the hosted display policy withholds it (#157, #177). Keeps the
// reader here with the summary and rating controls, records the outbound
// click, and asks how far they got when they come back.
export function NoTextFallback({ item }: { item: ContentItemFull }) {
  const summary = item.summary_detailed || item.summary_brief;
  const host = hostnameOf(item.url);
  const leftAt = useRef<number | null>(null);
  const [asking, setAsking] = useState(false);
  const [answered, setAnswered] = useState<string | null>(null);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== "visible" || leftAt.current === null) return;
      if (Date.now() - leftAt.current >= RETURN_PROMPT_AFTER_MS) setAsking(true);
      leftAt.current = null;
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  const openOriginal = () => {
    leftAt.current = Date.now();
    // Records the open only; nothing is learned until the reader answers.
    api.feedback
      .interaction({ content_item_id: item.id, opened_externally: true })
      .catch(() => {});
  };

  const answer = (a: (typeof ANSWERS)[number]) => {
    setAsking(false);
    setAnswered(a.label);
    api.feedback
      .interaction({
        content_item_id: item.id,
        read_completion_pct: a.completion,
        reached_end: a.reachedEnd,
      })
      .catch(() => {});
  };

  return (
    <div className="mx-auto max-w-prose py-12">
      {item.paywalled && (
        <span className="mb-3 inline-block rounded bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-600">
          Paywalled
        </span>
      )}
      <h1 className="text-3xl font-bold leading-tight">{item.title}</h1>
      {summary && (
        <p className="mt-5 border-l-2 border-prism-600 pl-4 font-serif text-lg leading-relaxed text-stone-600">
          <SummaryLabel source={item.summary_source} />
          {summary}
        </p>
      )}
      <p className="mt-4 text-stone-500">
        {item.full_text_withheld
          ? `Read the full article on ${host}.`
          : item.paywalled
            ? `This article is behind a paywall on ${host}.`
            : "The full article text isn’t available for in-app reading."}
      </p>
      <a
        href={item.url}
        target="_blank"
        rel="noopener noreferrer"
        onClick={openOriginal}
        className="btn-primary mt-6"
      >
        Open original at {host} →
      </a>

      {asking && (
        <div role="dialog" aria-label="Did you finish it?" className="mt-6 rounded-lg border border-stone-200 p-4">
          <p className="text-sm font-medium">Welcome back. Did you finish it?</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {ANSWERS.map((a) => (
              <button
                key={a.label}
                type="button"
                onClick={() => answer(a)}
                className="rounded border border-stone-300 px-3 py-1 text-sm hover:bg-stone-100"
              >
                {a.label}
              </button>
            ))}
          </div>
        </div>
      )}
      {answered && <p className="mt-4 text-sm text-stone-500">Thanks, noted: {answered.toLowerCase()}.</p>}

      <div className="mt-8">
        <p className="mb-2 text-sm text-stone-500">
          {item.paywalled ? "Rate the premise:" : "Rate it:"}
        </p>
        <FeedbackBar contentItemId={item.id} />
      </div>
    </div>
  );
}
