"use client";
import type { DigestItem } from "../../lib/types";
import { ContentCard } from "./ContentCard";

const SECTION_META: Record<string, { title: string; eyebrow: string; accent: string }> = {
  lead: {
    title: "Top Reads",
    eyebrow: "What matters most today",
    accent: "text-prism-700",
  },
  creator: {
    title: "From Your Creators",
    eyebrow: "People you follow",
    accent: "text-spectrum-violet",
  },
  deep_reads: {
    title: "Deep Reads",
    eyebrow: "Worth your full attention",
    accent: "text-spectrum-cyan",
  },
  discovery: {
    title: "Discover",
    eyebrow: "Outside your usual sources",
    accent: "text-spectrum-amber",
  },
};

interface DigestSectionProps {
  name: string;
  items: DigestItem[];
}

export function DigestSection({ name, items }: DigestSectionProps) {
  if (items.length === 0) return null;
  const meta = SECTION_META[name] || { title: name, eyebrow: "", accent: "text-stone-700" };

  return (
    <section className="mb-10 animate-slide-up">
      <div className="mb-4 border-b border-stone-200 pb-2">
        <div className={`eyebrow ${meta.accent}`}>{meta.eyebrow}</div>
        <h2 className="mt-0.5 font-serif text-xl font-bold text-stone-900">
          {meta.title}
        </h2>
      </div>
      <div className="space-y-3">
        {items.map(
          (item) =>
            item.content && (
              <ContentCard
                key={item.id}
                content={item.content}
                prsScore={item.prs_score}
                signalBreakdown={item.signal_breakdown}
                isDiscovery={name === "discovery"}
                section={name}
                position={item.position}
              />
            ),
        )}
      </div>
    </section>
  );
}
