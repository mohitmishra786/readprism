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
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: 24 }}>Creators</h1>
      <AddCreatorForm onAdded={(c) => setCreators((prev) => [c, ...prev])} />
      {loading ? (
        <p style={{ color: "#6b7280" }}>Loading creators...</p>
      ) : creators.length === 0 ? (
        <p style={{ color: "#6b7280" }}>No creators added yet.</p>
      ) : (
        creators.map((c) => (
          <CreatorProfile
            key={c.id}
            creator={c}
            onDeleted={(id) => setCreators((prev) => prev.filter((x) => x.id !== id))}
          />
        ))
      )}
    </div>
  );
}
