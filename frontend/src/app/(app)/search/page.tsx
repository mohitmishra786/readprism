"use client";
import { useState } from "react";
import { api } from "../../../lib/api";
import type { ContentItem } from "../../../lib/types";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await api.search.query(query.trim());
      setResults(data.hits);
      setSearched(true);
    } catch {
      setResults([]);
      setSearched(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: 20 }}>Search</h1>

      <form onSubmit={search} style={{ display: "flex", gap: 8, marginBottom: 24 }}>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search your reading archive..."
          style={{
            flex: 1,
            padding: "10px 14px",
            border: "1px solid #d1d5db",
            borderRadius: 6,
            fontSize: "1rem",
          }}
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          style={{
            padding: "10px 20px",
            background: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            cursor: loading ? "not-allowed" : "pointer",
            opacity: loading ? 0.7 : 1,
          }}
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </form>

      {searched && results.length === 0 && (
        <p style={{ color: "#6b7280" }}>No results found for &ldquo;{query}&rdquo;.</p>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {results.map((item) => (
          <div
            key={item.id}
            style={{
              padding: 16,
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              background: "#fff",
            }}
          >
            <h3 style={{ margin: "0 0 4px", fontSize: "1rem", fontWeight: 600 }}>
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "#1d4ed8", textDecoration: "none" }}
                dangerouslySetInnerHTML={{
                  __html: (item as unknown as Record<string, string>)["_formatted"]?.title || item.title,
                }}
              />
            </h3>
            {item.author && (
              <p style={{ margin: "0 0 6px", fontSize: 12, color: "#6b7280" }}>{item.author}</p>
            )}
            {item.summary_brief && (
              <p
                style={{ margin: 0, fontSize: "0.875rem", color: "#374151", lineHeight: 1.5 }}
                dangerouslySetInnerHTML={{
                  __html:
                    (item as unknown as Record<string, string>)["_formatted"]?.summary_brief ||
                    item.summary_brief,
                }}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
