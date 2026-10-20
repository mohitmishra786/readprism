"use client";
import { useState } from "react";
import { api } from "../lib/api";
import { SIGNAL_LABELS } from "../lib/signals";
import type { WhyNotSeen as Why } from "../lib/types";

export function sharePercent(contribution: number, score: number): number {
  return score > 0 ? Math.round((contribution / score) * 100) : 0;
}

// "Why didn't I see this?" (#267): the item's live score for you, what each
// signal contributed (the digest's own wording), and what would raise it.
export function WhyNotSeen({ contentId }: { contentId: string }) {
  const [open, setOpen] = useState(false);
  const [why, setWhy] = useState<Why | null>(null);
  const [error, setError] = useState("");

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && !why) {
      try {
        setWhy(await api.search.why(contentId));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Couldn't explain this item.");
      }
    }
  };

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="text-xs font-medium text-stone-500 underline-offset-2 hover:underline dark:text-stone-400"
      >
        Why didn&apos;t I see this?
      </button>
      {open && (
        <div className="mt-2 rounded-lg border border-stone-200 p-3 text-sm dark:border-stone-700">
          {error && <p className="text-red-600 dark:text-red-300">{error}</p>}
          {!why && !error && <p className="text-stone-500 dark:text-stone-400">Scoring it for you…</p>}
          {why && (
            <>
              <p>{why.message}</p>
              <p className="mt-1 text-stone-600 dark:text-stone-300">
                Score {why.score.toFixed(2)} · {why.explanation}
              </p>
              <ul className="mt-2 space-y-1" aria-label="Signal contributions">
                {why.contributions
                  .filter((c) => c.contribution > 0.0005)
                  .map((c) => (
                    <li key={c.signal} className="flex items-center gap-2 text-xs">
                      <span className="w-40 shrink-0">{SIGNAL_LABELS[c.signal] ?? c.signal}</span>
                      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-700">
                        <span
                          className="block h-full rounded-full bg-prism-500"
                          style={{ width: `${sharePercent(c.contribution, why.score)}%` }}
                        />
                      </span>
                      <span className="w-10 text-right">{sharePercent(c.contribution, why.score)}%</span>
                    </li>
                  ))}
              </ul>
              {why.raise_it.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs font-medium">To see more like this:</p>
                  <ul className="list-disc pl-5 text-xs text-stone-600 dark:text-stone-300">
                    {why.raise_it.map((r) => (
                      <li key={r.signal}>{r.how}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
