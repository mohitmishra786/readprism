"use client";
import { useEffect, useState } from "react";
import { api } from "../../../lib/api";
import type { Source } from "../../../lib/types";
import { AddSourceForm } from "../../../components/sources/AddSourceForm";
import { SourceList } from "../../../components/sources/SourceList";

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.sources.list().then((s) => { setSources(s); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: 24 }}>Sources</h1>
      <AddSourceForm onAdded={(s) => setSources((prev) => [s, ...prev])} />
      {loading ? (
        <p style={{ color: "#6b7280" }}>Loading sources...</p>
      ) : (
        <SourceList
          sources={sources}
          onUpdated={(s) => setSources((prev) => prev.map((x) => (x.id === s.id ? s : x)))}
          onDeleted={(id) => setSources((prev) => prev.filter((x) => x.id !== id))}
        />
      )}
    </div>
  );
}
