"use client";
import { useState } from "react";
import type { Creator } from "../../lib/types";
import { api } from "../../lib/api";
import { PlatformBadge } from "./PlatformBadge";

interface CreatorProfileProps {
  creator: Creator;
  onDeleted: (id: string) => void;
}

export function CreatorProfile({ creator, onDeleted }: CreatorProfileProps) {
  const [summary, setSummary] = useState("");
  const [loadingSummary, setLoadingSummary] = useState(false);

  const loadSummary = async () => {
    setLoadingSummary(true);
    try {
      const result = await api.creators.summary(creator.id);
      setSummary(result.summary);
    } catch {}
    setLoadingSummary(false);
  };

  const del = async () => {
    if (!confirm(`Remove ${creator.display_name}?`)) return;
    await api.creators.delete(creator.id);
    onDeleted(creator.id);
  };

  return (
    <div className="card card-hover p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="font-serif text-base font-semibold text-stone-900">
            {creator.display_name}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {creator.platforms.map((p) => (
              <PlatformBadge key={p.id} platform={p} />
            ))}
          </div>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <button
            onClick={loadSummary}
            disabled={loadingSummary}
            className="btn-ghost border border-stone-200 px-2.5 py-1 text-xs"
          >
            {loadingSummary ? "Loading…" : "This week"}
          </button>
          <button
            onClick={del}
            className="border border-rose-200 px-2.5 py-1 text-xs text-rose-600 transition-colors hover:bg-rose-50"
          >
            Remove
          </button>
        </div>
      </div>

      {summary && (
        <div className="mt-3 rounded-lg bg-prism-50 px-4 py-3 text-sm leading-relaxed text-prism-900">
          <strong className="font-semibold">This week: </strong>
          {summary}
        </div>
      )}
    </div>
  );
}
