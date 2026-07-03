"use client";
import type { Source } from "../../lib/types";
import { api } from "../../lib/api";

interface SourceListProps {
  sources: Source[];
  onUpdated: (source: Source) => void;
  onDeleted: (id: string) => void;
}

export function SourceList({ sources, onUpdated, onDeleted }: SourceListProps) {
  const toggle = async (source: Source) => {
    const updated = await api.sources.update(source.id, { is_active: !source.is_active });
    onUpdated(updated);
  };

  const del = async (id: string) => {
    if (!confirm("Remove this source?")) return;
    await api.sources.delete(id);
    onDeleted(id);
  };

  if (sources.length === 0) {
    return <p className="text-sm text-stone-500">No sources added yet.</p>;
  }

  return (
    <div className="space-y-2.5">
      {sources.map((s) => (
        <div
          key={s.id}
          className={`card p-4 ${s.is_active ? "" : "opacity-60"}`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium text-stone-900">
                {s.name || s.url}
              </div>
              <div className="mt-0.5 text-xs text-stone-500">
                <span className="font-mono uppercase tracking-wide">{s.source_type}</span>
                {" · "}
                {s.last_fetched_at
                  ? `Fetched ${new Date(s.last_fetched_at).toLocaleDateString()}`
                  : "Not yet fetched"}
                {" · "}
                Relevance {Math.round(s.trust_weight * 100)}%
              </div>
              {/* Trust-weight bar */}
              <div className="mt-2.5 h-1 w-24 overflow-hidden rounded-full bg-stone-200">
                <div
                  className="reading-progress h-full rounded-full"
                  style={{ width: `${s.trust_weight * 100}%` }}
                />
              </div>
            </div>
            <div className="flex shrink-0 gap-1.5">
              <button
                onClick={() => toggle(s)}
                className="btn-ghost border border-stone-200 px-2.5 py-1 text-xs"
              >
                {s.is_active ? "Pause" : "Resume"}
              </button>
              <button
                onClick={() => del(s.id)}
                className="border border-rose-200 px-2.5 py-1 text-xs text-rose-600 transition-colors hover:bg-rose-50"
              >
                Remove
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
