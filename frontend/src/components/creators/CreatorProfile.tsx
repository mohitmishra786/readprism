"use client";
import { useState } from "react";
import type { Creator } from "../../lib/types";
import { api } from "../../lib/api";

const PLATFORM_ICONS: Record<string, string> = {
  substack: "📧",
  youtube: "▶",
  twitter: "🐦",
  medium: "M",
  linkedin: "in",
  podcast: "🎙",
  blog: "✍",
};

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
    <div
      style={{
        padding: 16,
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        marginBottom: 12,
        background: "#fff",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: "1rem" }}>{creator.display_name}</div>
          <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
            {creator.platforms.map((p) => (
              <a
                key={p.id}
                href={p.platform_url}
                target="_blank"
                rel="noopener noreferrer"
                title={p.platform}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  fontSize: 11,
                  background: "#f3f4f6",
                  padding: "2px 8px",
                  borderRadius: 10,
                  textDecoration: "none",
                  color: "#374151",
                }}
              >
                {PLATFORM_ICONS[p.platform] || "🔗"} {p.platform}
              </a>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={loadSummary}
            disabled={loadingSummary}
            style={{
              padding: "4px 12px",
              fontSize: 12,
              border: "1px solid #d1d5db",
              borderRadius: 6,
              cursor: "pointer",
              background: "#fff",
            }}
          >
            {loadingSummary ? "Loading..." : "This week"}
          </button>
          <button
            onClick={del}
            style={{
              padding: "4px 10px",
              fontSize: 12,
              border: "1px solid #fca5a5",
              color: "#dc2626",
              background: "#fff",
              borderRadius: 6,
              cursor: "pointer",
            }}
          >
            Remove
          </button>
        </div>
      </div>

      {summary && (
        <div
          style={{
            marginTop: 12,
            padding: "10px 14px",
            background: "#f0f9ff",
            borderRadius: 6,
            fontSize: "0.875rem",
            color: "#1e40af",
            lineHeight: 1.6,
          }}
        >
          <strong>This week: </strong>{summary}
        </div>
      )}
    </div>
  );
}
