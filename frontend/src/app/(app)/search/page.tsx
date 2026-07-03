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
      <header className="mb-6">
        <div className="eyebrow text-prism-700">Archive</div>
        <h1 className="mt-1 font-serif text-3xl font-bold tracking-tight">Search</h1>
        <p className="mt-1 text-sm text-stone-500">
          Full-text search across your reading archive.
        </p>
      </header>

      <form onSubmit={search} className="mb-6 flex gap-2">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search your reading archive..."
          className="input flex-1"
        />
        <button type="submit" disabled={loading} className="btn-primary">
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {searched && (
        <div className="space-y-3">
          {results.length === 0 ? (
            <p className="py-8 text-center text-sm text-stone-500">
              No results for “{query}”.
            </p>
          ) : (
            results.map((item) => (
              <div key={item.id} className="card card-hover p-4">
                <h3 className="font-serif text-base font-semibold">
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-stone-900 hover:text-prism-700"
                    dangerouslySetInnerHTML={{
                      __html:
                        (item as unknown as { _formatted?: Record<string, string> })._formatted?.title ||
                        item.title,
                    }}
                  />
                </h3>
                {item.author && (
                  <p className="mt-1 text-xs text-stone-500">{item.author}</p>
                )}
                {item.summary_brief && (
                  <p
                    className="mt-2 text-sm leading-relaxed text-stone-600"
                    dangerouslySetInnerHTML={{
                      __html:
                        (item as unknown as { _formatted?: Record<string, string> })._formatted
                          ?.summary_brief || item.summary_brief,
                    }}
                  />
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
