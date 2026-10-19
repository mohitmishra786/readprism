"use client";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { StarterPack } from "../../lib/types";

const ICONS: Record<string, string> = {
  "academic-computing": "🎓",
  "ai-machine-learning": "🤖",
  "biotech-health": "🧬",
  "climate-energy": "🌱",
  "crypto-web3": "⛓️",
  "databases-data": "🗄️",
  "design-ux": "🎨",
  "devops-cloud": "☁️",
  gamedev: "🎮",
  "hardware-electronics": "🔌",
  "mobile-development": "📱",
  "open-source-devtools": "🛠️",
  "programming-languages": "🔤",
  "quant-finance": "📈",
  "robotics-automation": "🦾",
  "science-research": "🔬",
  "security-privacy": "🔐",
  "space-astronomy": "🚀",
  "startups-business": "💼",
  "systems-programming": "⚙️",
  "web-development": "🌐",
};

/** Subscribe to the selected packs; returns how many new feeds were added. */
export async function subscribePacks(ids: string[]): Promise<number> {
  let added = 0;
  for (const id of ids) {
    const result = await api.sources.subscribePack(id).catch(() => null);
    added += result?.subscribed ?? 0;
  }
  return added;
}

export function packSummary(packs: StarterPack[], selected: string[]): string {
  const chosen = packs.filter((p) => selected.includes(p.id));
  const feeds = chosen.reduce((n, p) => n + p.feed_count, 0);
  return `${chosen.length} pack${chosen.length === 1 ? "" : "s"} · ${feeds} sources`;
}

// Grid of starter packs with multi-select (#152). Controlled: the parent owns
// the selection so the onboarding wizard can subscribe when the user moves on.
export function StarterPackPicker({
  topics = [],
  selected,
  onChange,
  footer,
}: {
  topics?: string[];
  selected: string[];
  onChange: (ids: string[]) => void;
  footer?: React.ReactNode;
}) {
  const [packs, setPacks] = useState<StarterPack[] | null>(null);
  const topicKey = topics.join(",");

  useEffect(() => {
    let cancelled = false;
    api.sources
      .starterPacks(topicKey ? topicKey.split(",") : [])
      .then((list) => {
        if (cancelled) return;
        setPacks(list);
        // Pre-select packs that match the user's topics, once.
        const suggested = list.filter((p) => p.suggested && p.subscribed === 0).map((p) => p.id);
        if (suggested.length && selected.length === 0) onChange(suggested);
      })
      .catch(() => setPacks([]));
    return () => {
      cancelled = true;
    };
    // Load once per topic set; selection changes must not refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicKey]);

  if (packs === null) return <p className="text-sm text-stone-500">Loading starter packs…</p>;
  if (packs.length === 0) return <p className="text-sm text-stone-500">No starter packs available.</p>;

  const toggle = (id: string) =>
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);

  return (
    <div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {packs.map((p) => {
          const on = selected.includes(p.id);
          const following = p.subscribed > 0 && p.subscribed >= p.feed_count;
          return (
            <button
              key={p.id}
              type="button"
              aria-pressed={on}
              disabled={following}
              onClick={() => toggle(p.id)}
              className={`rounded-lg border p-3 text-left transition-colors ${
                on ? "border-prism-600 bg-prism-50 ring-1 ring-prism-600" : "border-stone-200 hover:border-stone-400"
              } ${following ? "opacity-60" : ""}`}
            >
              <div className="flex items-center gap-2 font-medium">
                <span aria-hidden>{ICONS[p.id] ?? "📚"}</span>
                {p.title}
                {p.suggested && !following && (
                  <span className="ml-auto rounded bg-amber-50 px-1.5 text-[10px] font-semibold uppercase text-amber-700">
                    For you
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-stone-500">
                {following
                  ? "Already following"
                  : `${p.feed_count} sources · ${p.feeds.slice(0, 3).map((f) => f.name).join(", ")}`}
              </p>
            </button>
          );
        })}
      </div>
      <div className="sticky bottom-0 mt-4 flex items-center justify-between border-t border-stone-200 bg-white/95 py-3 text-sm backdrop-blur dark:bg-stone-950/95">
        <span>{packSummary(packs, selected)}</span>
        {footer}
      </div>
    </div>
  );
}
