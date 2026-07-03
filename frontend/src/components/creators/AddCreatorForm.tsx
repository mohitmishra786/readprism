"use client";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { Creator, PlatformCapabilities } from "../../lib/types";

interface AddCreatorFormProps {
  onAdded: (creator: Creator) => void;
}

const TIER_LEGEND: Record<string, { label: string; className: string }> = {
  fully_tracked: { label: "fully tracked", className: "text-emerald-700" },
  best_effort: { label: "best effort", className: "text-amber-700" },
  unsupported: { label: "not supported", className: "text-rose-700" },
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

  const grouped = capabilities
    ? (["fully_tracked", "best_effort", "unsupported"] as const).map((tier) => ({
        tier,
        labels: Object.entries(capabilities)
          .filter(([, c]) => c.tracking_tier === tier)
          .map(([, c]) => c.display_label),
      }))
    : [];

  return (
    <form onSubmit={handleSubmit} className="mb-6">
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="https://simonwillison.substack.com, https://reddit.com/user/..., or a name"
          required
          className="input flex-1"
        />
        <button type="submit" disabled={loading} className="btn-primary whitespace-nowrap">
          {loading ? "Resolving…" : "Add Creator"}
        </button>
      </div>

      {grouped.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-500">
          {grouped.map((g) => (
            <span key={g.tier}>
              <span className={`font-semibold ${TIER_LEGEND[g.tier].className}`}>
                {TIER_LEGEND[g.tier].label}:
              </span>{" "}
              {g.labels.join(", ")}
            </span>
          ))}
        </div>
      )}

      {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
      {warning && <p className="mt-2 text-sm text-amber-600">{warning}</p>}
    </form>
  );
}
