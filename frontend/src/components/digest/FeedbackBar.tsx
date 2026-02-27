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

  // Load current interaction state from server on mount
  useEffect(() => {
    api.feedback.getInteraction(contentItemId).then((interaction) => {
      if (interaction) {
        setSaved(interaction.saved);
        if (interaction.explicit_rating !== null) {
          setRated(interaction.explicit_rating);
        }
      }
    }).catch(() => {});
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
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
      <button
        onClick={() => rate(1)}
        title="Helpful"
        style={{
          background: rated === 1 ? "#d1fae5" : "none",
          border: "1px solid #d1d5db",
          borderRadius: 4,
          padding: "4px 8px",
          cursor: "pointer",
          fontSize: 16,
        }}
      >
        👍
      </button>
      <button
        onClick={() => rate(-1)}
        title="Not helpful"
        style={{
          background: rated === -1 ? "#fee2e2" : "none",
          border: "1px solid #d1d5db",
          borderRadius: 4,
          padding: "4px 8px",
          cursor: "pointer",
          fontSize: 16,
        }}
      >
        👎
      </button>
      <button
        onClick={save}
        title="Save for later"
        style={{
          background: saved ? "#dbeafe" : "none",
          border: "1px solid #d1d5db",
          borderRadius: 4,
          padding: "4px 8px",
          cursor: "pointer",
          fontSize: 16,
        }}
      >
        {saved ? "✓ Saved" : "Save"}
      </button>

      {showReasons && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Why?</span>
          {REASONS.map((r) => (
            <button
              key={r.value}
              onClick={() => rateWithReason(r.value)}
              style={{
                fontSize: 11,
                padding: "2px 8px",
                border: "1px solid #e5e7eb",
                borderRadius: 12,
                cursor: "pointer",
                background: "#f9fafb",
              }}
            >
              {r.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
