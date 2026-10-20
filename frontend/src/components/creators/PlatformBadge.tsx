"use client";
import type { ComponentType } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Check,
  AlertTriangle,
  X,
  Mail,
  Mic,
  PenLine,
  Link as LinkIcon,
  MessageSquare,
  Cloud,
  Share2,
} from "lucide-react";
import type { CreatorPlatform } from "../../lib/types";

const PLATFORM_ICONS: Record<string, ComponentType<{ className?: string }> | string> = {
  substack: Mail,
  youtube: "▶",
  twitter: "X",
  medium: "M",
  linkedin: "in",
  podcast: Mic,
  reddit: MessageSquare,
  bluesky: Cloud,
  mastodon: Share2,
  github: "⌥",
  blog: PenLine,
};

const TIER_STYLES: Record<
  string,
  { className: string; marker: LucideIcon; title: string }
> = {
  fully_tracked: {
    className: "bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300",
    marker: Check,
    title: "Reliably tracked: new posts ingested",
  },
  best_effort: {
    className: "bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300",
    marker: AlertTriangle,
    title: "Best effort: a feed may exist but isn't guaranteed",
  },
  unsupported: {
    className: "bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-950/40 dark:text-rose-300",
    marker: X,
    title: "Not supported: this platform has no public feed",
  },
};

export function PlatformBadge({ platform }: { platform: CreatorPlatform }) {
  const tier = platform.tracking_tier || "best_effort";
  const tierStyle = TIER_STYLES[tier] || TIER_STYLES.best_effort;
  const label = platform.display_label || platform.platform;
  const Icon = PLATFORM_ICONS[platform.platform] || LinkIcon;
  const Marker = tierStyle.marker;

  return (
    <a
      href={platform.platform_url}
      target="_blank"
      rel="noopener noreferrer"
      title={`${label}: ${tierStyle.title}`}
      className={`chip ring-1 ${tierStyle.className} hover:opacity-80`}
    >
      <span aria-hidden className="inline-flex items-center">
        {typeof Icon === "string" ? Icon : <Icon className="h-3.5 w-3.5" aria-hidden="true" />}
      </span>
      <span>{label}</span>
      <span aria-hidden title={tierStyle.title} className="inline-flex items-center">
        <Marker className="h-3 w-3" aria-hidden="true" />
      </span>
    </a>
  );
}
