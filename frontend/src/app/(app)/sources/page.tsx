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
      <header className="mb-6">
        <div className="eyebrow text-prism-700">Ingestion</div>
        <h1 className="mt-1 font-serif text-3xl font-bold tracking-tight">Sources</h1>
        <p className="mt-1 text-sm text-stone-500">
          Websites, blogs, and feeds you follow. RSS is detected automatically.
        </p>
      </header>
      <AddSourceForm onAdded={(s) => setSources((prev) => [s, ...prev])} />
      {loading ? (
        <div className="space-y-2.5">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card p-4">
              <div className="skeleton mb-2 h-4 w-2/3 rounded" />
              <div className="skeleton h-3 w-1/3 rounded" />
            </div>
          ))}
        </div>
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
