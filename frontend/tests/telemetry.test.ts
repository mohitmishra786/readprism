import { describe, expect, it } from "vitest";

import {
  buildTelemetryPayload,
  computeComposite,
  type ReadingSnapshot,
} from "../src/lib/useReadingTelemetry";

describe("computeComposite (UX-05 depth math)", () => {
  const tenMin = 10 * 60_000;

  it("weights scroll 70% and active time 30%", () => {
    // Full scroll, no time -> 0.7. Full time, no scroll -> 0.3.
    expect(computeComposite(1, 0, false, tenMin)).toBeCloseTo(0.7, 5);
    expect(computeComposite(0, tenMin, false, tenMin)).toBeCloseTo(0.3, 5);
  });

  it("caps the time component at the estimated reading time", () => {
    const slow = computeComposite(0.5, tenMin * 5, false, tenMin);
    const exact = computeComposite(0.5, tenMin, false, tenMin);
    expect(slow).toBeCloseTo(exact, 5);
  });

  it("floors completion at 0.95 when the end sentinel fired", () => {
    // Fast scroller: tiny active time, but reached the end.
    const fast = computeComposite(1, 500, true, tenMin);
    expect(fast).toBeGreaterThanOrEqual(0.95);
    expect(fast).toBeLessThanOrEqual(1);
  });

  it("clamps inputs and never exceeds 1", () => {
    expect(computeComposite(2, tenMin * 3, true, tenMin)).toBeLessThanOrEqual(1);
    expect(computeComposite(-1, -5, false, tenMin)).toBeGreaterThanOrEqual(0);
  });

  it("falls back to scroll-only when no reading time is known", () => {
    expect(computeComposite(0.8, 12345, false, null)).toBeCloseTo(0.7 * 0.8, 5);
  });
});

describe("buildTelemetryPayload", () => {
  it("rounds and maps the snapshot onto the API body", () => {
    const snap: ReadingSnapshot = {
      scrollDepthPct: 0.81234,
      activeTimeMs: 65_400,
      reachedEnd: true,
      bounced: false,
      readingProgressPct: 0.95123,
    };
    const body = buildTelemetryPayload("item-1", snap) as Record<string, number | boolean | string>;
    expect(body.content_item_id).toBe("item-1");
    expect(body.read_completion_pct).toBe(0.951);
    expect(body.scroll_depth_pct).toBe(0.812);
    expect(body.time_on_page_seconds).toBe(65);
    expect(body.active_time_seconds).toBe(65);
    expect(body.reached_end).toBe(true);
    expect(body.skipped).toBe(false);
  });
});
