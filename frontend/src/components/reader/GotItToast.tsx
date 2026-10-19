"use client";
import { useState } from "react";
import { api } from "../../lib/api";

export function finishedPhrase(activeTimeMs: number): string {
  const minutes = Math.max(1, Math.round(activeTimeMs / 60_000));
  return `You finished this in ${minutes} min`;
}

// After a full read, make the learning visible (#228): "more of this topic?"
// with a one-tap correction. Shown once per read: dismissing or answering
// hides it for the rest of the visit.
export function GotItToast({
  topic,
  activeTimeMs,
  onClose,
}: {
  topic: string;
  activeTimeMs: number;
  onClose: () => void;
}) {
  const [done, setDone] = useState<string | null>(null);

  const adjust = (action: "boost" | "suppress", label: string) => {
    setDone(label);
    api.feedback.adjustInterests(topic, action).catch(() => {});
    setTimeout(onClose, 2500);
  };

  return (
    <div
      role="status"
      className="fixed bottom-6 left-1/2 z-50 w-[min(92vw,28rem)] -translate-x-1/2 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm shadow-lg dark:border-stone-700 dark:bg-stone-900"
    >
      {done ? (
        <p>{done}</p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <p className="flex-1">
            {finishedPhrase(activeTimeMs)}. More <em>{topic}</em>?
          </p>
          <button
            type="button"
            onClick={() => adjust("boost", `Got it: more ${topic}.`)}
            className="rounded bg-stone-900 px-3 py-1 text-white dark:bg-stone-100 dark:text-stone-900"
          >
            More
          </button>
          <button
            type="button"
            onClick={() => adjust("suppress", `Got it: less ${topic}.`)}
            className="rounded border border-stone-300 px-3 py-1"
          >
            Less
          </button>
          <button type="button" onClick={onClose} aria-label="Dismiss" className="px-1 text-stone-400">
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
