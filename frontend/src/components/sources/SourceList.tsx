"use client";
import type { Source } from "../../lib/types";
import { api } from "../../lib/api";

interface SourceListProps {
  sources: Source[];
  onUpdated: (source: Source) => void;
  onDeleted: (id: string) => void;
}

export function SourceList({ sources, onUpdated, onDeleted }: SourceListProps) {
  const toggle = async (source: Source) => {
    const updated = await api.sources.update(source.id, { is_active: !source.is_active });
    onUpdated(updated);
  };

  const del = async (id: string) => {
    if (!confirm("Remove this source?")) return;
    await api.sources.delete(id);
    onDeleted(id);
  };

  if (sources.length === 0) {
    return <p style={{ color: "#6b7280" }}>No sources added yet.</p>;
  }

  return (
    <div>
      {sources.map((s) => (
        <div
          key={s.id}
          style={{
            padding: 16,
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            marginBottom: 10,
            background: s.is_active ? "#fff" : "#f9fafb",
            opacity: s.is_active ? 1 : 0.7,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 500 }}>{s.name || s.url}</div>
              <div style={{ fontSize: 12, color: "#6b7280" }}>
                {s.source_type.toUpperCase()} ·{" "}
                {s.last_fetched_at
                  ? `Last fetched ${new Date(s.last_fetched_at).toLocaleDateString()}`
                  : "Not yet fetched"}{" "}
                · Relevance: {Math.round(s.trust_weight * 100)}%
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={() => toggle(s)}
                style={{
                  padding: "4px 10px",
                  fontSize: 12,
                  border: "1px solid #d1d5db",
                  borderRadius: 6,
                  cursor: "pointer",
                  background: s.is_active ? "#fff" : "#f3f4f6",
                }}
              >
                {s.is_active ? "Pause" : "Resume"}
              </button>
              <button
                onClick={() => del(s.id)}
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
          <div
            style={{
              height: 4,
              background: "#e5e7eb",
              borderRadius: 2,
              marginTop: 10,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${s.trust_weight * 100}%`,
                background: "#2563eb",
                borderRadius: 2,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
