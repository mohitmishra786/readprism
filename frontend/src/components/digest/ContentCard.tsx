"use client";
import { useRef, useState } from "react";
import type { ContentItem } from "../../lib/types";
import { api } from "../../lib/api";
import { FeedbackBar } from "./FeedbackBar";

const SIGNAL_LABELS: Record<string, string> = {
  semantic: "matches your interests",
  reading_depth: "matches your reading depth",
  suggestion: "similar to content you discovered",
  explicit_feedback: "aligns with your ratings",
  source_trust: "from a trusted source",
  content_quality: "high quality content",
  temporal_context: "matches your current focus",
  novelty: "expands your reading",
};

interface ContentCardProps {
  content: ContentItem;
  prsScore?: number | null;
  signalBreakdown?: Record<string, number>;
  isDiscovery?: boolean;
  section?: string;
  position?: number;
}

export function ContentCard({
  content,
  prsScore,
  signalBreakdown,
  isDiscovery,
  section,
  position,
}: ContentCardProps) {
  const openedAt = useRef<number | null>(null);
  const [showWhyTooltip, setShowWhyTooltip] = useState(false);
  const [summaryLevel, setSummaryLevel] = useState<"brief" | "detailed">("brief");

  const topSignals = signalBreakdown
    ? Object.entries(signalBreakdown)
        .filter(([k]) => !k.startsWith("_"))
        .sort(([, a], [, b]) => b - a)
        .slice(0, 2)
        .map(([k]) => SIGNAL_LABELS[k] || k)
    : [];

  const handleClick = () => {
    openedAt.current = Date.now();

    // Use visibilitychange — fires when the user returns to this tab,
    // which is the correct signal that they have come back from reading.
    const handleVisibility = async () => {
      if (document.visibilityState !== "visible") return;
      document.removeEventListener("visibilitychange", handleVisibility);
      if (!openedAt.current) return;
      const elapsed = Math.floor((Date.now() - openedAt.current) / 1000);
      // Anything under 5 seconds is a bounce — treat as a skip
      if (elapsed < 5) {
        openedAt.current = null;
        return;
      }
      const readingTime = (content.reading_time_minutes || 5) * 60;
      const pct = Math.min(1.0, elapsed / readingTime);
      openedAt.current = null;
      try {
        await api.feedback.interaction({
          content_item_id: content.id,
          time_on_page_seconds: elapsed,
          read_completion_pct: pct,
          skipped: elapsed < 10,
        });
      } catch {}
    };

    document.addEventListener("visibilitychange", handleVisibility);
  };

  return (
    <div
      style={{
        padding: 16,
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        marginBottom: 12,
        background: isDiscovery ? "#f0f9ff" : "#fff",
      }}
    >
      {isDiscovery && (
        <span
          style={{
            display: "inline-block",
            fontSize: 11,
            background: "#bfdbfe",
            color: "#1e40af",
            padding: "2px 8px",
            borderRadius: 12,
            marginBottom: 8,
          }}
        >
          Outside your usual sources — based on your interests
        </span>
      )}

      <h3 style={{ margin: "0 0 6px", fontSize: "1rem", fontWeight: 600 }}>
        <a
          href={content.url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={handleClick}
          style={{ color: "#1d4ed8", textDecoration: "none" }}
        >
          {content.title}
        </a>
      </h3>

      <div style={{ display: "flex", gap: 12, fontSize: 12, color: "#6b7280", marginBottom: 8 }}>
        {content.author && <span>{content.author}</span>}
        {content.reading_time_minutes && <span>{content.reading_time_minutes} min read</span>}
        {content.published_at && (
          <span>{new Date(content.published_at).toLocaleDateString()}</span>
        )}
      </div>

      {content.summary_headline && (
        <p style={{ margin: "0 0 4px", fontSize: "0.8rem", fontStyle: "italic", color: "#6b7280" }}>
          {content.summary_headline}
        </p>
      )}

      {summaryLevel === "brief" && content.summary_brief && (
        <p style={{ margin: "0 0 6px", fontSize: "0.9rem", color: "#374151", lineHeight: 1.5 }}>
          {content.summary_brief}
        </p>
      )}
      {summaryLevel === "detailed" && (content.summary_detailed || content.summary_brief) && (
        <p style={{ margin: "0 0 6px", fontSize: "0.9rem", color: "#374151", lineHeight: 1.6 }}>
          {content.summary_detailed || content.summary_brief}
        </p>
      )}

      {(content.summary_brief || content.summary_detailed) && (
        <button
          onClick={() => setSummaryLevel(summaryLevel === "brief" ? "detailed" : "brief")}
          style={{
            fontSize: 11,
            color: "#6b7280",
            background: "none",
            border: "none",
            padding: 0,
            cursor: "pointer",
            marginBottom: 6,
            textDecoration: "underline",
          }}
        >
          {summaryLevel === "brief" ? "Show detailed takeaway" : "Show brief summary"}
        </button>
      )}

      {topSignals.length > 0 && (
        <div style={{ position: "relative", display: "inline-block" }}>
          <button
            onClick={() => setShowWhyTooltip(!showWhyTooltip)}
            style={{
              fontSize: 11,
              color: "#6b7280",
              background: "none",
              border: "1px solid #e5e7eb",
              borderRadius: 4,
              padding: "2px 6px",
              cursor: "pointer",
            }}
          >
            Why this?
          </button>
          {showWhyTooltip && (
            <div
              style={{
                position: "absolute",
                bottom: "100%",
                left: 0,
                background: "#1f2937",
                color: "#fff",
                borderRadius: 6,
                padding: "8px 12px",
                fontSize: 12,
                whiteSpace: "nowrap",
                zIndex: 10,
                marginBottom: 4,
              }}
            >
              Ranked because: {topSignals.join(", ")}
            </div>
          )}
        </div>
      )}

      <FeedbackBar contentItemId={content.id} />
    </div>
  );
}
