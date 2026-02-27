"use client";
import { useState } from "react";
import { api } from "../../lib/api";
import type { Creator } from "../../lib/types";

interface AddCreatorFormProps {
  onAdded: (creator: Creator) => void;
}

export function AddCreatorForm({ onAdded }: AddCreatorFormProps) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");

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

  return (
    <form onSubmit={handleSubmit} style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="https://simonwillison.substack.com or Simon Willison"
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
      {error && <p style={{ color: "#ef4444", fontSize: 14 }}>{error}</p>}
      {warning && <p style={{ color: "#d97706", fontSize: 14 }}>{warning}</p>}
    </form>
  );
}
