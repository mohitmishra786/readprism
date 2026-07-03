"use client";
/**
 * PlatformBadge — renders a platform chip with an honest tracking-tier marker.
 *
 * The tier comes from PLATFORM_CAPABILITIES on the backend:
 *   - fully_tracked: ✓ green    (reliable RSS; we ingest new posts)
 *   - best_effort:   ⚠ amber    (feed may exist but isn't guaranteed)
 *   - unsupported:   ✗ red      (closed platform; cannot auto-track)
 *
 * Surfacing this in the UI is part of the honesty layer — we set an explicit
 * expectation rather than silently failing to surface content for closed
 * platforms like Twitter/LinkedIn.
 */
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

const TIER_STYLES: Record<string, { bg: string; color: string; marker: string; title: string }> = {
  fully_tracked: {
    bg: "#dcfce7",
    color: "#166534",
    marker: "✓",
    title: "Reliably tracked — new posts ingested",
  },
  best_effort: {
    bg: "#fef3c7",
    color: "#92400e",
    marker: "⚠",
    title: "Best effort — a feed may exist but isn't guaranteed",
  },
  unsupported: {
    bg: "#fee2e2",
    color: "#991b1b",
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
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: 11,
        background: tierStyle.bg,
        color: tierStyle.color,
        padding: "2px 8px",
        borderRadius: 10,
        textDecoration: "none",
        fontWeight: 500,
      }}
    >
      <span aria-hidden>{icon}</span>
      <span>{label}</span>
      <span aria-hidden title={tierStyle.title}>
        {tierStyle.marker}
      </span>
    </a>
  );
}
