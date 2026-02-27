"use client";
import { useState } from "react";
import { api } from "../../lib/api";
import type { Source } from "../../lib/types";

interface AddSourceFormProps {
  onAdded: (source: Source) => void;
}

export function AddSourceForm({ onAdded }: AddSourceFormProps) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const source = await api.sources.add(url.trim());
      onAdded(source);
      setUrl("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add source");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8, marginBottom: 24 }}>
      <input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://example.com/blog"
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
        {loading ? "Adding..." : "Add Source"}
      </button>
      {error && <span style={{ color: "#ef4444", fontSize: 14 }}>{error}</span>}
    </form>
  );
}
