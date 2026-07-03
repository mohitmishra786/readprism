"use client";
/**
 * In-app Reader view.
 *
 * Why this exists: the ranking engine's behavioral half (reading_depth,
 * temporal_context, suggestion, novelty) depends on *real* reading telemetry.
 * Foreign tabs give us no scroll/visibility signal — so when the full text is
 * available we render it in-app where we can capture genuine scroll depth and
 * active time. The original-source link is still offered for users who want
 * the publisher's layout, images, or context.
 */
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useReadingTelemetry } from "../../../../lib/useReadingTelemetry";
import { api } from "../../../../lib/api";
import type { ContentItemFull } from "../../../../lib/types";
import { FeedbackBar } from "../../../../components/digest/FeedbackBar";

export default function ReaderPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [item, setItem] = useState<ContentItemFull | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showOriginal, setShowOriginal] = useState(false);

  const { snapshot, sentinelRef } = useReadingTelemetry({
    contentItemId: id,
    readingTimeMinutes: item?.reading_time_minutes ?? null,
  });

  useEffect(() => {
    if (!id) return;
    api.content
      .get(id)
      .then(setItem)
      .catch((e) => setError(e.message || "Failed to load article"));
  }, [id]);

  if (error) {
    return (
      <div style={{ padding: 24 }}>
        <p style={{ color: "#dc2626" }}>{error}</p>
        <button onClick={() => router.back()} style={{ marginTop: 12 }}>
          ← Back
        </button>
      </div>
    );
  }

  if (!item) {
    return <div style={{ padding: 24, color: "#6b7280" }}>Loading…</div>;
  }

  // If we have no extracted body, fall back to opening the original in a new
  // tab (foreign-tab heuristic still applies there).
  if (!item.full_text && !showOriginal) {
    return (
      <div style={{ padding: 24 }}>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: 12 }}>
          {item.title}
        </h1>
        <p style={{ color: "#6b7280", marginBottom: 16 }}>
          The full article text isn’t available for in-app reading.
        </p>
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "#1d4ed8", textDecoration: "none" }}
        >
          Open original at {new URL(item.url).hostname} →
        </a>
        <div style={{ marginTop: 24 }}>
          <FeedbackBar contentItemId={item.id} />
        </div>
      </div>
    );
  }

  const paragraphs = (item.full_text || "")
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);

  const progressPct = Math.round(snapshot.readingProgressPct * 100);

  return (
    <article style={{ maxWidth: 720, margin: "0 auto", padding: "24px 16px 120px" }}>
      {/* Sticky progress bar reflects genuine reading progress (scroll + active time). */}
      <div
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: "#e5e7eb",
          zIndex: 50,
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${progressPct}%`,
            background: "#2563eb",
            transition: "width 0.3s ease",
          }}
        />
      </div>

      <button
        onClick={() => router.back()}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "#6b7280",
          padding: 0,
          marginBottom: 16,
          fontSize: 13,
        }}
      >
        ← Back
      </button>

      <h1 style={{ fontSize: "1.8rem", fontWeight: 700, lineHeight: 1.25, marginBottom: 12 }}>
        {item.title}
      </h1>

      <div
        style={{
          display: "flex",
          gap: 12,
          fontSize: 13,
          color: "#6b7280",
          marginBottom: 8,
          flexWrap: "wrap",
        }}
      >
        {item.author && <span>{item.author}</span>}
        {item.reading_time_minutes && <span>{item.reading_time_minutes} min read</span>}
        {item.published_at && (
          <span>{new Date(item.published_at).toLocaleDateString()}</span>
        )}
      </div>

      {item.summary_detailed && (
        <p
          style={{
            fontSize: "1.05rem",
            lineHeight: 1.6,
            color: "#374151",
            background: "#f9fafb",
            padding: 16,
            borderRadius: 8,
            marginBottom: 24,
            borderLeft: "3px solid #2563eb",
          }}
        >
          {item.summary_detailed}
        </p>
      )}

      <div style={{ fontSize: "1.05rem", lineHeight: 1.75, color: "#1f2937" }}>
        {paragraphs.map((p, i) => (
          <p key={i} style={{ marginBottom: 16 }}>
            {p}
          </p>
        ))}
        {/* Reached-end sentinel. Intersecting this flips reachedEnd=true,
            which floors completion at 0.95. */}
        <div ref={sentinelRef} style={{ height: 1 }} aria-hidden />
      </div>

      <div
        style={{
          marginTop: 32,
          paddingTop: 16,
          borderTop: "1px solid #e5e7eb",
          fontSize: 12,
          color: "#6b7280",
        }}
      >
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "#1d4ed8", textDecoration: "none" }}
        >
          View original at {new URL(item.url).hostname} →
        </a>
      </div>

      <div style={{ marginTop: 24 }}>
        <FeedbackBar contentItemId={item.id} />
      </div>
    </article>
  );
}
