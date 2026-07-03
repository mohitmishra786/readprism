"use client";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";

interface FeedbackBarProps {
  contentItemId: string;
  onFeedback?: () => void;
}

const REASONS = [
  { value: "too_basic", label: "Too basic" },
  { value: "already_knew", label: "Already knew this" },
  { value: "too_tangential", label: "Not relevant" },
  { value: "wrong_depth", label: "Wrong depth" },
];

export function FeedbackBar({ contentItemId, onFeedback }: FeedbackBarProps) {
  const [rated, setRated] = useState<number | null>(null);
  const [showReasons, setShowReasons] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.feedback
      .getInteraction(contentItemId)
      .then((interaction) => {
        if (interaction) {
          setSaved(interaction.saved);
          if (interaction.explicit_rating !== null) setRated(interaction.explicit_rating);
        }
      })
      .catch(() => {});
  }, [contentItemId]);

  const rate = async (rating: number) => {
    setRated(rating);
    if (rating === -1) setShowReasons(true);
    await api.feedback.interaction({ content_item_id: contentItemId, explicit_rating: rating });
    onFeedback?.();
  };

  const rateWithReason = async (reason: string) => {
    setShowReasons(false);
    await api.feedback.interaction({
      content_item_id: contentItemId,
      explicit_rating: -1,
      explicit_rating_reason: reason,
    });
  };

  const save = async () => {
    setSaved(true);
    await api.feedback.interaction({ content_item_id: contentItemId, saved: true });
  };

  return (
    <div className="flex items-center gap-1.5">
      <button
        onClick={() => rate(1)}
        title="Helpful"
        className={`flex h-8 w-8 items-center justify-center rounded-md border text-sm transition-colors ${
          rated === 1
            ? "border-emerald-200 bg-emerald-50"
            : "border-stone-200 hover:bg-stone-50"
        }`}
      >
        👍
      </button>
      <button
        onClick={() => rate(-1)}
        title="Not helpful"
        className={`flex h-8 w-8 items-center justify-center rounded-md border text-sm transition-colors ${
          rated === -1
            ? "border-rose-200 bg-rose-50"
            : "border-stone-200 hover:bg-stone-50"
        }`}
      >
        👎
      </button>
      <button
        onClick={save}
        title="Save for later"
        className={`flex h-8 items-center gap-1 rounded-md border px-2.5 text-xs font-medium transition-colors ${
          saved
            ? "border-prism-200 bg-prism-50 text-prism-700"
            : "border-stone-200 text-stone-600 hover:bg-stone-50"
        }`}
      >
        {saved ? "✓ Saved" : "Save"}
      </button>

      {showReasons && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-stone-500">Why?</span>
          {REASONS.map((r) => (
            <button
              key={r.value}
              onClick={() => rateWithReason(r.value)}
              className="rounded-full border border-stone-200 bg-stone-50 px-2.5 py-1 text-xs transition-colors hover:border-stone-300"
            >
              {r.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
