"use client";
/**
 * In-app Reader view.
 *
 * Why this exists: the ranking engine's behavioral half (reading_depth,
 * temporal_context, suggestion, novelty) depends on *real* reading telemetry.
 * Foreign tabs give us no scroll/visibility signal — so when the full text is
 * available we render it in-app where we can capture genuine scroll depth and
 * active time.
 *
 * Content rendering: full_text from trafilatura may be plain text OR contain
 * inline HTML (links, emphasis, figures). We render it safely inside a
 * .prose-reader container styled by globals.css. The container is scoped so
 * only article HTML is affected, never the app chrome.
 */
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useReadingTelemetry } from "../../../../lib/useReadingTelemetry";
import { api } from "../../../../lib/api";
import { sanitizeHtml } from "../../../../lib/sanitize";
import type { ContentItemFull } from "../../../../lib/types";
import { FeedbackBar } from "../../../../components/digest/FeedbackBar";

export default function ReaderPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [item, setItem] = useState<ContentItemFull | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { snapshot, sentinelRef } = useReadingTelemetry({
    contentItemId: id,
    readingTimeMinutes: item?.reading_time_minutes ?? null,
  });

  useEffect(() => {
    if (!id) return;
    api.content
      .get(id)
      .then(setItem)
      .catch((e) => setError(e.message || "Failed to load article"));
  }, [id]);

  const progressPct = Math.round(snapshot.readingProgressPct * 100);

  // Prepare the article body. full_text may be HTML or plain text; wrap plain
  // text in <p> tags so the prose-reader styles apply consistently.
  const articleHtml = useMemo(() => {
    if (!item?.full_text) return "";
    const text = item.full_text.trim();
    let html: string;
    // If it already contains HTML block tags, render as-is.
    if (/<(?:p|div|h[1-6]|ul|ol|blockquote|figure|pre|table)\b/i.test(text)) {
      html = text;
    } else {
      // Otherwise treat as plain text: split on blank lines into paragraphs.
      html = text
        .split(/\n{2,}/)
        .map((p) => `<p>${p.trim().replace(/\n/g, "<br/>")}</p>`)
        .join("");
    }
    // Sanitize before it reaches dangerouslySetInnerHTML (audit 06-7): ingested
    // article HTML can carry <script>/onerror/javascript: payloads.
    return sanitizeHtml(html);
  }, [item?.full_text]);

  if (error) {
    return (
      <div className="py-16 text-center">
        <p className="text-red-600">{error}</p>
        <button
          onClick={() => router.back()}
          className="btn-secondary mt-4"
        >
          ← Back
        </button>
      </div>
    );
  }

  if (!item) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="skeleton h-6 w-32 rounded" />
      </div>
    );
  }

  // If we have no extracted body, offer the original.
  if (!item.full_text) {
    return (
      <div className="mx-auto max-w-prose py-12">
        <h1 className="text-3xl font-bold leading-tight">{item.title}</h1>
        <p className="mt-4 text-stone-500">
          The full article text isn’t available for in-app reading.
        </p>
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-primary mt-6"
        >
          Open original at {safeHostname(item.url)} →
        </a>
        <div className="mt-8">
          <FeedbackBar contentItemId={item.id} />
        </div>
      </div>
    );
  }

  return (
    <article className="mx-auto max-w-reading pb-32 pt-8">
      {/* Sticky reading-progress bar — prism gradient reflects genuine progress */}
      <div className="fixed left-0 right-0 top-0 z-50 h-1 bg-transparent">
        <div
          className="reading-progress h-full transition-all duration-300"
          style={{ width: `${progressPct}%` }}
        />
      </div>

      <button
        onClick={() => router.back()}
        className="mb-6 text-sm text-stone-500 transition-colors hover:text-stone-900"
      >
        ← Back
      </button>

      {/* Article header */}
      <header className="mb-8 border-b border-stone-200 pb-6">
        <h1 className="font-serif text-3xl font-bold leading-tight tracking-tight md:text-4xl">
          {item.title}
        </h1>

        <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-stone-500">
          {item.author && (
            <span className="font-medium text-stone-700">{item.author}</span>
          )}
          {item.reading_time_minutes && (
            <>
              {item.author && <span className="text-stone-300">·</span>}
              <span>{item.reading_time_minutes} min read</span>
            </>
          )}
          {item.published_at && (
            <>
              <span className="text-stone-300">·</span>
              <span>{new Date(item.published_at).toLocaleDateString()}</span>
            </>
          )}
        </div>

        {/* AI summary deck — the editorial "standfirst" */}
        {item.summary_detailed && (
          <p className="deck mt-5 border-l-2 border-prism-600 pl-4 font-serif text-lg italic leading-relaxed text-stone-600">
            {item.summary_detailed}
          </p>
        )}
      </header>

      {/* Article body — rendered HTML in a scoped, typographically-styled container */}
      <div
        className="prose-reader"
        dangerouslySetInnerHTML={{ __html: articleHtml }}
      />

      {/* Reached-end sentinel — intersecting floors completion at 0.95 */}
      <div ref={sentinelRef} aria-hidden style={{ height: 1 }} />

      {/* Footer */}
      <footer className="mt-12 border-t border-stone-200 pt-6">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm font-medium text-prism-600 hover:text-prism-700"
        >
          View original at {safeHostname(item.url)} →
        </a>
        <div className="mt-6">
          <FeedbackBar contentItemId={item.id} />
        </div>
      </footer>
    </article>
  );
}

function safeHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return "source";
  }
}
