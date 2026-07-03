"use client";
import { useEffect, useState } from "react";
import { api } from "../../../lib/api";
import type { Creator } from "../../../lib/types";
import { AddCreatorForm } from "../../../components/creators/AddCreatorForm";
import { CreatorProfile } from "../../../components/creators/CreatorProfile";

export default function CreatorsPage() {
  const [creators, setCreators] = useState<Creator[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.creators.list().then((c) => { setCreators(c); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  return (
    <div>
      <header className="mb-6">
        <div className="eyebrow text-prism-700">People</div>
        <h1 className="mt-1 font-serif text-3xl font-bold tracking-tight">Creators</h1>
        <p className="mt-1 text-sm text-stone-500">
          Track individuals across Substack, YouTube, Medium, Reddit, and more.
        </p>
      </header>
      <AddCreatorForm onAdded={(c) => setCreators((prev) => [c, ...prev])} />
      {loading ? (
        <div className="space-y-2.5">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card p-4">
              <div className="skeleton mb-2 h-4 w-1/2 rounded" />
              <div className="skeleton h-5 w-24 rounded-full" />
            </div>
          ))}
        </div>
      ) : creators.length === 0 ? (
        <p className="text-sm text-stone-500">No creators added yet.</p>
      ) : (
        <div className="space-y-2.5">
          {creators.map((c) => (
            <CreatorProfile
              key={c.id}
              creator={c}
              onDeleted={(id) => setCreators((prev) => prev.filter((x) => x.id !== id))}
            />
          ))}
        </div>
      )}
    </div>
  );
}
