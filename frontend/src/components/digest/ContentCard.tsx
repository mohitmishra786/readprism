"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ContentItem } from "../../lib/types";
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
}: ContentCardProps) {
  const router = useRouter();
  const [showWhyTooltip, setShowWhyTooltip] = useState(false);
  const [summaryLevel, setSummaryLevel] = useState<"brief" | "detailed">("brief");

  // Explainability: rank the signals by their relative contribution. Each
  // signal contributes score * (1/total) of the unweighted signal strength — we
  // show its share as a percentage. This is honest about *which* signals drove
  // the ranking without leaking the per-user learned weights themselves.
  const signalEntries = signalBreakdown
    ? Object.entries(signalBreakdown)
        .filter(([k, v]) => !k.startsWith("_") && typeof v === "number")
        .sort(([, a], [, b]) => (b as number) - (a as number))
    : [];

  const totalSignalStrength = signalEntries.reduce(
    (sum, [, v]) => sum + (v as number),
    0,
  );

  const rankedSignals = signalEntries
    .slice(0, 3)
    .map(([k, v]) => ({
      key: k,
      label: SIGNAL_LABELS[k] || k,
      contribution:
        totalSignalStrength > 0
          ? Math.round(((v as number) / totalSignalStrength) * 100)
          : 0,
    }));

  // Plain-English one-liner built from the dominant signal, so the value is
  // legible even without opening the tooltip.
  const whySummary =
    rankedSignals.length > 0
      ? `Ranked because it ${rankedSignals[0].label}${
          rankedSignals[1] ? ` and ${rankedSignals[1].label}` : ""
        }`
      : null;

  // Route to the in-app reader, which captures genuine scroll-depth and active
  // time. The old wall-clock tab-switch heuristic is retired (see ReaderView).
  const handleRead = (e: React.MouseEvent) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey) return; // honor explicit new-tab/window
    e.preventDefault();
    router.push(`/read/${content.id}`);
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
          href={`/read/${content.id}`}
          onClick={handleRead}
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

      {whySummary && (
        <div style={{ position: "relative", display: "inline-block" }}>
          <button
            onClick={() => setShowWhyTooltip(!showWhyTooltip)}
            title={whySummary}
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
                padding: "10px 12px",
                fontSize: 12,
                zIndex: 10,
                marginBottom: 4,
                minWidth: 220,
                boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 6 }}>
                Why this is ranked here
              </div>
              {rankedSignals.map((s) => (
                <div
                  key={s.key}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 4,
                  }}
                >
                  <div
                    style={{
                      flex: 1,
                      height: 6,
                      background: "rgba(255,255,255,0.15)",
                      borderRadius: 3,
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        width: `${s.contribution}%`,
                        height: "100%",
                        background: "#60a5fa",
                      }}
                    />
                  </div>
                  <span style={{ width: 36, textAlign: "right", opacity: 0.8 }}>
                    {s.contribution}%
                  </span>
                  <span style={{ flex: "0 0 auto", opacity: 0.95 }}>
                    {s.label}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <FeedbackBar contentItemId={content.id} />
    </div>
  );
}
