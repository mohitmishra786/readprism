"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ContentItem } from "../../lib/types";
import { FeedbackBar } from "./FeedbackBar";

const SIGNAL_LABELS: Record<string, string> = {
  semantic: "matches your interests",
  reading_depth: "matches your reading depth",
  suggestion: "similar to content you discovered",
  explicit_feedback: "aligns with your ratings",
  source_trust: "from a trusted source",
  content_quality: "high quality content",
  temporal_context: "matches your current focus",
  novelty: "expands your reading",
};

// Section accent colors — the prism splits content into ranked bands.
const SECTION_ACCENTS: Record<string, string> = {
  lead: "from-prism-600 to-prism-400",
  creator: "from-spectrum-violet to-prism-500",
  deep_reads: "from-spectrum-cyan to-prism-500",
  discovery: "from-spectrum-amber to-spectrum-rose",
};

interface ContentCardProps {
  content: ContentItem;
  prsScore?: number | null;
  signalBreakdown?: Record<string, number>;
  isDiscovery?: boolean;
  section?: string;
  position?: number;
}

export function ContentCard({
  content,
  prsScore,
  signalBreakdown,
  isDiscovery,
  section,
}: ContentCardProps) {
  const router = useRouter();
  const [showWhyTooltip, setShowWhyTooltip] = useState(false);
  const [summaryLevel, setSummaryLevel] = useState<"brief" | "detailed">("brief");

  // Explainability: rank signals by relative contribution.
  const signalEntries = signalBreakdown
    ? Object.entries(signalBreakdown)
        .filter(([k, v]) => !k.startsWith("_") && typeof v === "number")
        .sort(([, a], [, b]) => (b as number) - (a as number))
    : [];

  const totalSignalStrength = signalEntries.reduce(
    (sum, [, v]) => sum + (v as number),
    0,
  );

  const rankedSignals = signalEntries.slice(0, 3).map(([k, v]) => ({
    key: k,
    label: SIGNAL_LABELS[k] || k,
    contribution:
      totalSignalStrength > 0
        ? Math.round(((v as number) / totalSignalStrength) * 100)
        : 0,
  }));

  const whySummary =
    rankedSignals.length > 0
      ? `Ranked because it ${rankedSignals[0].label}${
          rankedSignals[1] ? ` and ${rankedSignals[1].label}` : ""
        }`
      : null;

  const accent = section ? SECTION_ACCENTS[section] : "from-prism-600 to-prism-400";

  const handleRead = (e: React.MouseEvent) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    router.push(`/read/${content.id}`);
  };

  const hasSummary = !!(content.summary_brief || content.summary_detailed);

  return (
    <article className="card card-hover group relative overflow-hidden p-5">
      {/* Left accent stripe — visual marker for the section/rank band */}
      <div
        className={`absolute left-0 top-0 h-full w-1 bg-gradient-to-b ${accent}`}
        aria-hidden
      />

      {isDiscovery && (
        <span className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 ring-1 ring-amber-200">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
          Outside your usual sources — based on your interests
        </span>
      )}

      <div className="flex items-start justify-between gap-3">
        <h3 className="flex-1 font-serif text-lg font-semibold leading-snug">
          <a
            href={`/read/${content.id}`}
            onClick={handleRead}
            className="text-stone-900 transition-colors hover:text-prism-700"
          >
            {content.title}
          </a>
        </h3>
        {prsScore != null && (
          <span
            className="shrink-0 font-mono text-xs font-medium text-stone-400"
            title="Personalized Relevance Score"
          >
            {prsScore.toFixed(2)}
          </span>
        )}
      </div>

      {/* Metadata row */}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-stone-500">
        {content.author && (
          <span className="font-medium text-stone-600">{content.author}</span>
        )}
        {content.reading_time_minutes && (
          <span>{content.reading_time_minutes} min read</span>
        )}
        {content.published_at && (
          <span>{new Date(content.published_at).toLocaleDateString()}</span>
        )}
      </div>

      {/* Summary */}
      {content.summary_headline && (
        <p className="mt-3 font-serif text-sm italic text-stone-500">
          {content.summary_headline}
        </p>
      )}

      {summaryLevel === "brief" && content.summary_brief && (
        <p className="mt-2 text-sm leading-relaxed text-stone-700">
          {content.summary_brief}
        </p>
      )}
      {summaryLevel === "detailed" && (content.summary_detailed || content.summary_brief) && (
        <p className="mt-2 text-[0.95rem] leading-relaxed text-stone-700">
          {content.summary_detailed || content.summary_brief}
        </p>
      )}

      {hasSummary && (
        <button
          onClick={() =>
            setSummaryLevel(summaryLevel === "brief" ? "detailed" : "brief")
          }
          className="mt-2 text-xs font-medium text-stone-500 underline-offset-2 transition-colors hover:text-prism-600 hover:underline"
        >
          {summaryLevel === "brief" ? "Show detailed takeaway" : "Show brief summary"}
        </button>
      )}

      {/* Footer: why-this + feedback */}
      <div className="mt-4 flex items-center justify-between border-t border-stone-100 pt-3">
        {whySummary ? (
          <div className="relative">
            <button
              onClick={() => setShowWhyTooltip(!showWhyTooltip)}
              title={whySummary}
              className="inline-flex items-center gap-1.5 rounded-md border border-stone-200 px-2 py-1 text-xs text-stone-500 transition-colors hover:border-stone-300 hover:bg-stone-50"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-gradient-to-r from-prism-500 to-spectrum-violet" />
              Why this?
            </button>
            {showWhyTooltip && (
              <div className="absolute bottom-full left-0 z-20 mb-2 w-64 rounded-lg bg-stone-900 p-3 text-xs text-white shadow-xl">
                <div className="mb-2 font-semibold">Why this is ranked here</div>
                {rankedSignals.map((s) => (
                  <div key={s.key} className="mb-1.5 flex items-center gap-2">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/20">
                      <div
                        className="h-full rounded-full bg-prism-400"
                        style={{ width: `${s.contribution}%` }}
                      />
                    </div>
                    <span className="w-8 text-right opacity-70">
                      {s.contribution}%
                    </span>
                    <span className="shrink-0 opacity-95">{s.label}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <span />
        )}
        <FeedbackBar contentItemId={content.id} />
      </div>
    </article>
  );
}
