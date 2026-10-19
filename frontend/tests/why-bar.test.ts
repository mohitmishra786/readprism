import { describe, expect, it } from "vitest";
import { roundTo100, topicFromWhy, whySegments } from "../src/lib/why";

const breakdown = {
  no_data: ["suggestion"],
  why_topics: "matches your interest in compilers",
  contributions: {
    novelty: 0.028, semantic: 0.112, suggestion: 0.1, source_trust: 0.068,
    reading_depth: 0.107, content_quality: 0.022, temporal_context: 0.048, explicit_feedback: 0.093,
  },
};

describe("Why bar (#185)", () => {
  it("rounds shares to exactly 100", () => {
    expect(roundTo100([1, 1, 1]).reduce((a, b) => a + b)).toBe(100);
    expect(roundTo100([0.112, 0.107, 0.093, 0.166, 0.1])).toEqual([19, 19, 16, 29, 17]);
    expect(roundTo100([0, 0])).toEqual([0, 0]);
  });

  it("shows the top 3 signals with data, the rest, and the no-data share; sums to 100", () => {
    const segs = whySegments(breakdown, topicFromWhy(breakdown.why_topics));
    expect(segs.map((s) => s.label)).toEqual([
      "Topic match: compilers",
      "Depth you finish",
      "Your ratings",
      "Other signals",
      "No data yet (neutral)",
    ]);
    expect(segs.reduce((sum, s) => sum + s.pct, 0)).toBe(100);
    expect(segs.find((s) => s.key === "suggestion")).toBeUndefined(); // never a reason
    expect(segs.at(-1)?.noData).toBe(true);
  });

  it("is empty for breakdowns without contributions (older digests)", () => {
    expect(whySegments({ semantic: 0.5 })).toEqual([]);
  });

  it("reads the topic from the why line", () => {
    expect(topicFromWhy("matches your interest in rust and compilers")).toBe("rust");
    expect(topicFromWhy(undefined)).toBeNull();
  });
});
