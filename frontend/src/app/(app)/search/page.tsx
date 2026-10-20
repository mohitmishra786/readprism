"use client";
import { useEffect, useState } from "react";
import { api } from "../../../lib/api";
import { sanitizeHtml } from "../../../lib/sanitize";
import type { ContentItem } from "../../../lib/types";
import { WhyNotSeen } from "../../../components/WhyNotSeen";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const run = async (q: string) => {
    if (!q.trim()) return;
    setLoading(true);
    try {
      const data = await api.search.query(q.trim());
      setResults(data.hits);
      setSearched(true);
    } catch {
      setResults([]);
      setSearched(true);
    } finally {
      setLoading(false);
    }
  };

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    await run(query);
  };

  // Links such as the Emerging topics card open /search?q=<topic> (#218).
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      queueMicrotask(() => {
        setQuery(q);
        void run(q);
      });
    }
  }, []);

  return (
    <div>
      <header className="mb-6">
        <div className="eyebrow text-prism-700 dark:text-prism-300">Archive</div>
        <h1 className="mt-1 font-playfair text-3xl font-bold tracking-tight">Search</h1>
        <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">
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
            <p className="py-8 text-center text-sm text-stone-500 dark:text-stone-400">
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
                    className="text-stone-900 dark:text-stone-100 hover:text-prism-700 dark:hover:text-prism-200"
                    dangerouslySetInnerHTML={{
                      __html: sanitizeHtml(
                        (item as unknown as { _formatted?: Record<string, string> })._formatted
                          ?.title || item.title,
                      ),
                    }}
                  />
                </h3>
                {item.author && (
                  <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">{item.author}</p>
                )}
                {item.summary_brief && (
                  <p
                    className="mt-2 text-sm leading-relaxed text-stone-600 dark:text-stone-300"
                    dangerouslySetInnerHTML={{
                      __html: sanitizeHtml(
                        (item as unknown as { _formatted?: Record<string, string> })._formatted
                          ?.summary_brief || item.summary_brief,
                      ),
                    }}
                  />
                )}
                <WhyNotSeen contentId={item.id} />
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
