"use client";
import type { CreatorPlatform } from "../../lib/types";

const PLATFORM_ICONS: Record<string, string> = {
  substack: "📧",
  youtube: "▶",
  twitter: "🐦",
  medium: "M",
  linkedin: "in",
  podcast: "🎙",
  reddit: "🔴",
  blog: "✍",
};

const TIER_STYLES: Record<
  string,
  { className: string; marker: string; title: string }
> = {
  fully_tracked: {
    className: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    marker: "✓",
    title: "Reliably tracked — new posts ingested",
  },
  best_effort: {
    className: "bg-amber-50 text-amber-700 ring-amber-200",
    marker: "⚠",
    title: "Best effort — a feed may exist but isn't guaranteed",
  },
  unsupported: {
    className: "bg-rose-50 text-rose-700 ring-rose-200",
    marker: "✗",
    title: "Not supported — this platform has no public feed",
  },
};

export function PlatformBadge({ platform }: { platform: CreatorPlatform }) {
  const tier = platform.tracking_tier || "best_effort";
  const tierStyle = TIER_STYLES[tier] || TIER_STYLES.best_effort;
  const label = platform.display_label || platform.platform;
  const icon = PLATFORM_ICONS[platform.platform] || "🔗";

  return (
    <a
      href={platform.platform_url}
      target="_blank"
      rel="noopener noreferrer"
      title={`${label} — ${tierStyle.title}`}
      className={`chip ring-1 ${tierStyle.className} hover:opacity-80`}
    >
      <span aria-hidden>{icon}</span>
      <span>{label}</span>
      <span aria-hidden title={tierStyle.title}>
        {tierStyle.marker}
      </span>
    </a>
  );
}
