"use client";
import { useState } from "react";
import { api } from "../../lib/api";

// "How many of today's top 5 did you want?" (#131): the self-reported
// top-5 precision input metric. One tap, once per digest.
export function Top5Question({ digestId }: { digestId: string }) {
  const [answered, setAnswered] = useState(false);
  if (answered) {
    return (
      <p role="status" className="mb-6 text-sm text-stone-500">
        Thanks, that helps us tune your ranking.
      </p>
    );
  }
  return (
    <div className="mb-6 rounded-lg border border-stone-200 px-4 py-3 text-sm">
      <p className="mb-2 text-stone-700">How many of today&apos;s top 5 did you want to read?</p>
      <div className="flex gap-2" role="group" aria-label="How many of the top 5 you wanted">
        {[0, 1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            className="h-8 w-8 rounded-md border border-stone-200 hover:bg-stone-50"
            onClick={() => {
              setAnswered(true);
              api.digest.top5(digestId, n).catch(() => {});
            }}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}
