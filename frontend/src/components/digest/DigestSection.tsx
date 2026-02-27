"use client";
import type { DigestItem } from "../../lib/types";
import { ContentCard } from "./ContentCard";

const SECTION_TITLES: Record<string, string> = {
  lead: "Top Reads",
  creator: "From Your Creators",
  deep_reads: "Deep Reads",
  discovery: "Discover",
};

interface DigestSectionProps {
  name: string;
  items: DigestItem[];
}

export function DigestSection({ name, items }: DigestSectionProps) {
  if (items.length === 0) return null;

  return (
    <section style={{ marginBottom: 32 }}>
      <h2
        style={{
          fontSize: "1.1rem",
          fontWeight: 600,
          color: "#111827",
          marginBottom: 16,
          paddingBottom: 8,
          borderBottom: "2px solid #e5e7eb",
        }}
      >
        {SECTION_TITLES[name] || name}
      </h2>
      {items.map((item, i) => (
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
        )
      ))}
    </section>
  );
}
