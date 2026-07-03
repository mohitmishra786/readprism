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
    <form onSubmit={handleSubmit} className="mb-6">
      <div className="flex gap-2">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/blog"
          required
          className="input flex-1"
        />
        <button type="submit" disabled={loading} className="btn-primary whitespace-nowrap">
          {loading ? "Adding…" : "Add Source"}
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
    </form>
  );
}
