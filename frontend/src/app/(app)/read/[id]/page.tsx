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
import { useEffect, useMemo, useRef, useState } from "react";

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
  // Typography/theme controls (UX-05), persisted per browser.
  const [fontStep, setFontStep] = useState(1); // 0 small · 1 normal · 2 large
  const [theme, setTheme] = useState<"light" | "sepia" | "dark">("light");
  const [savedQuick, setSavedQuick] = useState(false);
  const [ratedQuick, setRatedQuick] = useState<number | null>(null);
  // j/k navigation order from the latest digest.
  const digestOrderRef = useRef<string[]>([]);

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
    // Best-effort j/k order from the latest digest; failures just disable j/k.
    api.digest
      .latest()
      .then((d) => {
        digestOrderRef.current = d.items
          .slice()
          .sort((a, b) => a.position - b.position)
          .map((i) => i.content_item_id);
      })
      .catch(() => {});
  }, [id]);

  useEffect(() => {
    const storedFont = Number(window.localStorage.getItem("reader-font-step"));
    if (storedFont >= 0 && storedFont <= 2) setFontStep(storedFont);
    const storedTheme = window.localStorage.getItem("reader-theme");
    if (storedTheme === "sepia" || storedTheme === "dark") setTheme(storedTheme);
  }, []);

  const adjustFont = (step: number) => {
    const next = Math.max(0, Math.min(2, step));
    setFontStep(next);
    window.localStorage.setItem("reader-font-step", String(next));
  };

  const cycleTheme = () => {
    const order = ["light", "sepia", "dark"] as const;
    const next = order[(order.indexOf(theme) + 1) % order.length];
    setTheme(next);
    window.localStorage.setItem("reader-theme", next);
  };

  const quickSave = async () => {
    if (!item) return;
    setSavedQuick(true);
    await api.feedback.interaction({ content_item_id: item.id, saved: true }).catch(() => {});
  };

  const quickRate = async (rating: number) => {
    if (!item) return;
    setRatedQuick(rating);
    await api.feedback
      .interaction({ content_item_id: item.id, explicit_rating: rating })
      .catch(() => {});
  };

  const stepItem = (dir: 1 | -1) => {
    const order = digestOrderRef.current;
    const idx = order.indexOf(id);
    if (idx === -1) return;
    const next = order[idx + dir];
    if (next) router.push(`/read/${next}`);
  };

  // Keyboard shortcuts (UX-05): j/k next/prev digest item, o original,
  // s save, u 👍, d 👎. Skips when typing in a form control.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      switch (e.key) {
        case "j":
          stepItem(1);
          break;
        case "k":
          stepItem(-1);
          break;
        case "o":
          if (item) window.open(item.url, "_blank", "noopener,noreferrer");
          break;
        case "s":
          quickSave();
          break;
        case "u":
          quickRate(1);
          break;
        case "d":
          quickRate(-1);
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, item]);

  const progressPct = Math.round(snapshot.readingProgressPct * 100);

  // Scoped reading-surface styles per theme + font step (UX-05).
  const surface =
    theme === "dark"
      ? "bg-stone-900 text-stone-100"
      : theme === "sepia"
        ? "bg-[#f4ecd8] text-stone-800"
        : "";
  const fontSizes = ["text-[15px]", "text-[17px]", "text-[19px]"];

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
        className="mb-4 text-sm text-stone-500 transition-colors hover:text-stone-900"
      >
        ← Back
      </button>

      {/* Typography / theme controls (UX-05) */}
      <div className="mb-6 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-stone-400">Reading surface:</span>
        <button onClick={() => adjustFont(fontStep - 1)} className="btn-secondary px-2 py-1" aria-label="Smaller text">
          A−
        </button>
        <button onClick={() => adjustFont(fontStep + 1)} className="btn-secondary px-2 py-1" aria-label="Larger text">
          A+
        </button>
        <button onClick={cycleTheme} className="btn-secondary px-2.5 py-1 capitalize">
          {theme}
        </button>
        <span className="ml-auto hidden text-stone-400 sm:inline">
          j/k next·prev · o original · s save · u 👍 · d 👎
        </span>
      </div>

      {/* Article header */}
      <header className="mb-8 border-b border-stone-200 pb-6">
        <h1 className={`font-serif text-3xl font-bold leading-tight tracking-tight md:text-4xl ${fontSizes[fontStep] === fontSizes[0] ? "md:text-3xl" : ""}`}>
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
        className={`prose-reader ${surface} ${fontSizes[fontStep]} ${theme === "dark" ? "prose-dark" : ""} rounded-lg transition-colors`}
        style={theme === "sepia" ? { boxShadow: "0 0 0 8px rgba(244,236,216,0.6)" } : undefined}
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
          <FeedbackBar
            contentItemId={item.id}
            topics={item.topic_clusters}
          />
          {(savedQuick || ratedQuick !== null) && (
            <p className="mt-2 text-xs text-emerald-600" role="status">
              {savedQuick && ratedQuick === null && "Saved ✓"}
              {ratedQuick === 1 && "Rated 👍 — more like this"}
              {ratedQuick === -1 && "Rated 👎 — less like this"}
              {savedQuick && ratedQuick !== null && " · Saved ✓"}
            </p>
          )}
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
