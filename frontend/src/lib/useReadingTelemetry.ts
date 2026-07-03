"use client";
/**
 * useReadingTelemetry — real reading-behavior capture.
 *
 * Replaces the old wall-clock tab-switch heuristic in ContentCard with genuine
 * scroll-depth, active-time, reached-end, and bounce signals. These feed the
 * `reading_depth`, `temporal_context`, `suggestion`, and `novelty` ranking
 * signals, so the quality of this capture directly determines the quality of
 * the personalization.
 *
 * Design notes:
 * - All mutable counters live in refs; state is only used to expose a snapshot
 *   for rendering (e.g. a progress bar). This avoids re-rendering on every
 *   scroll event.
 * - Active time ACCUMULATES only while the page is visible and focused, and
 *   pauses after IDLE_TIMEOUT_MS of no input/scroll/mousemove. A user who
 *   opens the tab and walks away therefore accrues near-zero active time,
 *   instead of being credited ~100% completion as the old heuristic did.
 * - read_completion_pct is a COMPOSITE: 70% scroll-depth + 30% active-time
 *   relative to estimated reading time, floored to 0.95 when reachedEnd.
 *   Scroll is the stronger signal of genuine reading; time is a guard against
 *   fast-scrolling past content.
 * - flush() is called periodically, on visibility-hidden, and on unmount, so
 *   telemetry is not lost when the reader closes the tab.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "./api";

/** Below this much active time, the open is treated as a bounce. */
const BOUNCE_MS = 5_000;
/** Pause the active timer after this much inactivity. */
const IDLE_TIMEOUT_MS = 60_000;
/** How often to flush an updated snapshot, if it changed. */
const FLUSH_INTERVAL_MS = 20_000;
/** Throttle scroll handling to one frame. */
const SCROLL_DEPTH_MIN_DELTA = 0.01;

export interface ReadingSnapshot {
  /** 0..1 — furthest scroll position reached, (scrollTop + viewportH) / scrollH. */
  scrollDepthPct: number;
  /** Accumulated active time in ms (paused on hidden/idle). */
  activeTimeMs: number;
  /** True once the bottom sentinel has been intersected. */
  reachedEnd: boolean;
  /** True when activeTimeMs < BOUNCE_MS at flush time. */
  bounced: boolean;
  /** 0..1 composite completion used to set read_completion_pct. */
  readingProgressPct: number;
}

export interface UseReadingTelemetryOptions {
  contentItemId: string;
  /** Estimated reading time; when absent we fall back to active-time only. */
  readingTimeMinutes?: number | null;
  /** Optional callback invoked after every successful flush. */
  onFlushed?: (snapshot: ReadingSnapshot) => void;
}

interface InternalState {
  scrollDepthPct: number;
  activeTimeMs: number;
  reachedEnd: boolean;
  lastActiveAt: number;
  intervalStartedAt: number | null;
  lastFlushedProgress: number;
}

function computeComposite(
  scrollDepthPct: number,
  activeTimeMs: number,
  reachedEnd: boolean,
  readingTimeMs: number | null,
): number {
  const scroll = Math.min(1, Math.max(0, scrollDepthPct));
  let timeComponent = 0;
  if (readingTimeMs && readingTimeMs > 0) {
    timeComponent = Math.min(1, activeTimeMs / readingTimeMs);
  }
  // 70% scroll depth, 30% active time. Scroll is the dominant signal of
  // genuine reading; time guards against fast-scrolling past content.
  let composite = 0.7 * scroll + 0.3 * timeComponent;
  if (reachedEnd) composite = Math.max(composite, 0.95);
  return Math.min(1, composite);
}

export function useReadingTelemetry({
  contentItemId,
  readingTimeMinutes,
  onFlushed,
}: UseReadingTelemetryOptions) {
  const stateRef = useRef<InternalState>({
    scrollDepthPct: 0,
    activeTimeMs: 0,
    reachedEnd: false,
    lastActiveAt: Date.now(),
    intervalStartedAt: null,
    lastFlushedProgress: 0,
  });
  // For sentinel detection — set by the reader view.
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const [snapshot, setSnapshot] = useState<ReadingSnapshot>({
    scrollDepthPct: 0,
    activeTimeMs: 0,
    reachedEnd: false,
    bounced: true,
    readingProgressPct: 0,
  });

  const readingTimeMs = readingTimeMinutes ? readingTimeMinutes * 60_000 : null;

  // Keep the latest readingTimeMs in a ref so the setup effect (which runs once)
  // and the memoized buildSnapshot/flush always see the current value, instead
  // of closing over the initial null (before content fetch resolves). Without
  // this, the active-time half of the composite score is permanently zeroed.
  const readingTimeMsRef = useRef(readingTimeMs);
  readingTimeMsRef.current = readingTimeMs;

  const buildSnapshot = useCallback((): ReadingSnapshot => {
    const s = stateRef.current;
    const progress = computeComposite(
      s.scrollDepthPct,
      s.activeTimeMs,
      s.reachedEnd,
      readingTimeMsRef.current,
    );
    return {
      scrollDepthPct: s.scrollDepthPct,
      activeTimeMs: s.activeTimeMs,
      reachedEnd: s.reachedEnd,
      bounced: s.activeTimeMs < BOUNCE_MS,
      readingProgressPct: progress,
    };
  }, [readingTimeMs]);

  const flush = useCallback(async () => {
    const snap = buildSnapshot();
    // Don't send a no-op flush (nothing changed since last send).
    if (
      snap.readingProgressPct === stateRef.current.lastFlushedProgress &&
      snap.activeTimeMs === 0
    ) {
      return;
    }
    stateRef.current.lastFlushedProgress = snap.readingProgressPct;
    try {
      await api.feedback.interaction({
        content_item_id: contentItemId,
        read_completion_pct: Number(snap.readingProgressPct.toFixed(3)),
        time_on_page_seconds: Math.round(snap.activeTimeMs / 1000),
        scroll_depth_pct: Number(snap.scrollDepthPct.toFixed(3)),
        active_time_seconds: Math.round(snap.activeTimeMs / 1000),
        reached_end: snap.reachedEnd,
        skipped: snap.bounced,
      });
      onFlushed?.(snap);
    } catch {
      // Swallow — telemetry must never break the reading experience.
    }
  }, [buildSnapshot, contentItemId, onFlushed]);

  // --- Activity tick: accumulate active time while visible & not idle -------
  const tickActive = useCallback(() => {
    const s = stateRef.current;
    if (typeof document !== "undefined" && document.hidden) return;
    if (s.intervalStartedAt === null) {
      s.intervalStartedAt = Date.now();
      return;
    }
    const now = Date.now();
    // If the user has been idle past the idle window, freeze accumulation
    // until the next activity event resets lastActiveAt.
    if (now - s.lastActiveAt > IDLE_TIMEOUT_MS) {
      s.intervalStartedAt = now;
      return;
    }
    const delta = now - s.intervalStartedAt;
    if (delta > 0) {
      s.activeTimeMs += delta;
      s.intervalStartedAt = now;
    }
  }, []);

  const markActive = useCallback(() => {
    const s = stateRef.current;
    s.lastActiveAt = Date.now();
    if (s.intervalStartedAt === null) s.intervalStartedAt = s.lastActiveAt;
  }, []);

  // --- Scroll depth tracking ------------------------------------------------
  const handleScroll = useCallback(() => {
    if (typeof window === "undefined") return;
    const s = stateRef.current;
    const scrollTop = window.scrollY || document.documentElement.scrollTop;
    const viewportH = window.innerHeight;
    const scrollH =
      document.documentElement.scrollHeight || document.body.scrollHeight;
    if (scrollH <= viewportH) {
      // Whole document fits in viewport — count as fully seen.
      if (s.scrollDepthPct < 1) s.scrollDepthPct = 1;
      return;
    }
    const depth = Math.min(1, (scrollTop + viewportH) / scrollH);
    if (depth - s.scrollDepthPct > SCROLL_DEPTH_MIN_DELTA) {
      s.scrollDepthPct = depth;
    }
  }, []);

  // rAF-throttled scroll handler.
  const rafRef = useRef<number | null>(null);
  const onScrollRaf = useCallback(() => {
    if (rafRef.current !== null) return;
    rafRef.current = window.requestAnimationFrame(() => {
      rafRef.current = null;
      handleScroll();
      markActive();
      setSnapshot(buildSnapshot());
    });
  }, [handleScroll, markActive, buildSnapshot]);

  // --- Set up all listeners -------------------------------------------------
  useEffect(() => {
    markActive();
    handleScroll();

    window.addEventListener("scroll", onScrollRaf, { passive: true });
    window.addEventListener("resize", onScrollRaf);
    window.addEventListener("mousemove", markActive, { passive: true });
    window.addEventListener("keydown", markActive);
    window.addEventListener("touchstart", markActive, { passive: true });
    document.addEventListener("visibilitychange", tickActive);

    const flushOnHidden = () => {
      if (typeof document !== "undefined" && document.hidden) flush();
    };
    document.addEventListener("visibilitychange", flushOnHidden);

    const interval = window.setInterval(() => {
      tickActive();
      setSnapshot(buildSnapshot());
    }, 5_000);
    const flushInterval = window.setInterval(flush, FLUSH_INTERVAL_MS);

    const onPageHide = () => flush();
    window.addEventListener("pagehide", onPageHide);

    return () => {
      window.removeEventListener("scroll", onScrollRaf);
      window.removeEventListener("resize", onScrollRaf);
      window.removeEventListener("mousemove", markActive);
      window.removeEventListener("keydown", markActive);
      window.removeEventListener("touchstart", markActive);
      document.removeEventListener("visibilitychange", tickActive);
      document.removeEventListener("visibilitychange", flushOnHidden);
      window.removeEventListener("pagehide", onPageHide);
      window.clearInterval(interval);
      window.clearInterval(flushInterval);
      if (rafRef.current !== null) window.cancelAnimationFrame(rafRef.current);
      // Best-effort final flush. pagehide already covers most navigation;
      // this covers in-app route changes.
      flush();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Reached-end sentinel via IntersectionObserver ------------------------
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            stateRef.current.reachedEnd = true;
            markActive();
            setSnapshot(buildSnapshot());
          }
        }
      },
      // Trigger when the sentinel is within ~1 viewport of the bottom.
      { rootMargin: "0px 0px 100px 0px", threshold: 0 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [markActive, buildSnapshot]);

  return { snapshot, flush, sentinelRef };
}
