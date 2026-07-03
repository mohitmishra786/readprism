"use client";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { Creator, PlatformCapabilities } from "../../lib/types";

interface AddCreatorFormProps {
  onAdded: (creator: Creator) => void;
}

const TIER_LEGEND: Record<string, { label: string; color: string }> = {
  fully_tracked: { label: "fully tracked", color: "#166534" },
  best_effort: { label: "best effort", color: "#92400e" },
  unsupported: { label: "not supported", color: "#991b1b" },
};

export function AddCreatorForm({ onAdded }: AddCreatorFormProps) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [capabilities, setCapabilities] = useState<PlatformCapabilities | null>(null);

  useEffect(() => {
    api.creators.capabilities().then(setCapabilities).catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setWarning("");
    try {
      const result = await api.creators.add(input.trim());
      if (result.warning) setWarning(result.warning);
      onAdded(result.creator);
      setInput("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add creator");
    } finally {
      setLoading(false);
    }
  };

  // Build a compact legend grouped by tier so users know what works upfront.
  const grouped = capabilities
    ? (["fully_tracked", "best_effort", "unsupported"] as const).map((tier) => ({
        tier,
        labels: Object.entries(capabilities)
          .filter(([, c]) => c.tracking_tier === tier)
          .map(([, c]) => c.display_label),
      }))
    : [];

  return (
    <form onSubmit={handleSubmit} style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="https://simonwillison.substack.com, https://reddit.com/user/..., or a name"
          required
          style={{ flex: 1, padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6 }}
        />
        <button
          type="submit"
          disabled={loading}
          style={{
            padding: "8px 20px",
            background: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            cursor: loading ? "not-allowed" : "pointer",
            opacity: loading ? 0.7 : 1,
          }}
        >
          {loading ? "Resolving..." : "Add Creator"}
        </button>
      </div>
      {grouped.length > 0 && (
        <div
          style={{
            display: "flex",
            gap: 12,
            flexWrap: "wrap",
            fontSize: 11,
            color: "#6b7280",
            marginBottom: 8,
          }}
        >
          {grouped.map((g) => (
            <span key={g.tier}>
              <span style={{ color: TIER_LEGEND[g.tier].color, fontWeight: 600 }}>
                {TIER_LEGEND[g.tier].label}:
              </span>{" "}
              {g.labels.join(", ")}
            </span>
          ))}
        </div>
      )}
      {error && <p style={{ color: "#ef4444", fontSize: 14 }}>{error}</p>}
      {warning && <p style={{ color: "#d97706", fontSize: 14 }}>{warning}</p>}
    </form>
  );
}
