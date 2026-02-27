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

  const loadMore = () => {
    const next = page + 1;
    setPage(next);
    loadItems(next);
  };

  return (
    <div>
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: 24 }}>Full Feed</h1>
      {items.map((item) => (
        <ContentCard
          key={item.content.id}
          content={item.content}
          prsScore={item.prs_score}
          signalBreakdown={item.signal_breakdown}
        />
      ))}
      {loading && <p style={{ color: "#6b7280", textAlign: "center" }}>Loading...</p>}
      {!loading && hasMore && (
        <div style={{ textAlign: "center", marginTop: 24 }}>
          <button
            onClick={loadMore}
            style={{
              padding: "10px 24px",
              border: "1px solid #d1d5db",
              borderRadius: 6,
              cursor: "pointer",
              background: "#fff",
            }}
          >
            Load more
          </button>
        </div>
      )}
    </div>
  );
}
