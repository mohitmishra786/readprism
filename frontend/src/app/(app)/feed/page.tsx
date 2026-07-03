"use client";
import { useEffect, useState, useCallback } from "react";
import { api } from "../../../lib/api";
import type { FeedItem } from "../../../lib/types";
import { ContentCard } from "../../../components/digest/ContentCard";

export default function FeedPage() {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);

  const loadItems = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const newItems = await api.content.feed(p, 20);
      if (newItems.length < 20) setHasMore(false);
      setItems((prev) => (p === 1 ? newItems : [...prev, ...newItems]));
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    loadItems(1);
  }, [loadItems]);

  return (
    <div>
      <header className="mb-6">
        <div className="eyebrow text-prism-700">Everything</div>
        <h1 className="mt-1 font-serif text-3xl font-bold tracking-tight">Full Feed</h1>
        <p className="mt-1 text-sm text-stone-500">
          All ingested items, ranked by personal relevance.
        </p>
      </header>

      <div className="space-y-3">
        {items.map((item) => (
          <ContentCard
            key={item.content.id}
            content={item.content}
            prsScore={item.prs_score}
            signalBreakdown={item.signal_breakdown}
          />
        ))}
      </div>

      {loading && (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="card p-5">
              <div className="skeleton mb-3 h-5 w-3/4 rounded" />
              <div className="skeleton h-3 w-full rounded" />
            </div>
          ))}
        </div>
      )}

      {!loading && hasMore && (
        <div className="mt-6 text-center">
          <button onClick={() => { const n = page + 1; setPage(n); loadItems(n); }} className="btn-secondary">
            Load more
          </button>
        </div>
      )}
    </div>
  );
}
