// The per-item "Why" bar (#185): each signal's share of the item's score,
// from the contributions the ranker stored (they sum to the score). Signals
// without data sit at a neutral prior; they are shown as one "no data yet"
// segment, never as a reason.

export const SHORT_LABELS: Record<string, string> = {
  semantic: "Topic match",
  reading_depth: "Depth you finish",
  suggestion: "Discovery track record",
  explicit_feedback: "Your ratings",
  source_trust: "Source you trust",
  content_quality: "Substantial read",
  temporal_context: "Fresh",
  novelty: "New angle",
};

export interface WhySegment {
  key: string;
  label: string;
  pct: number;
  noData?: boolean;
}

/** Integer percentages that sum to exactly 100 (largest remainder). */
export function roundTo100(values: number[]): number[] {
  const total = values.reduce((a, b) => a + b, 0);
  if (total <= 0) return values.map(() => 0);
  const exact = values.map((v) => (v / total) * 100);
  const floors = exact.map(Math.floor);
  let left = 100 - floors.reduce((a, b) => a + b, 0);
  const order = exact.map((v, i) => [v - Math.floor(v), i]).sort((a, b) => b[0] - a[0]);
  for (const [, i] of order) {
    if (left <= 0) break;
    floors[i] += 1;
    left -= 1;
  }
  return floors;
}

export function whySegments(breakdown: Record<string, unknown> | undefined, topic?: string | null): WhySegment[] {
  const contributions = (breakdown?.contributions ?? null) as Record<string, number> | null;
  if (!contributions) return [];
  const noData = new Set((breakdown?.no_data as string[] | undefined) ?? []);
  const withData = Object.entries(contributions)
    .filter(([k, v]) => !noData.has(k) && v > 0)
    .sort((a, b) => b[1] - a[1]);
  const top = withData.slice(0, 3);
  const otherValue = withData.slice(3).reduce((sum, [, v]) => sum + v, 0);
  const neutralValue = Object.entries(contributions)
    .filter(([k]) => noData.has(k))
    .reduce((sum, [, v]) => sum + v, 0);

  const raw: { key: string; label: string; value: number; noData?: boolean }[] = top.map(([key, value]) => ({
    key,
    label: key === "semantic" && topic ? `Topic match: ${topic}` : (SHORT_LABELS[key] ?? key),
    value,
  }));
  if (otherValue > 0) raw.push({ key: "other", label: "Other signals", value: otherValue });
  if (neutralValue > 0) raw.push({ key: "no_data", label: "No data yet (neutral)", value: neutralValue, noData: true });
  const pcts = roundTo100(raw.map((r) => r.value));
  return raw.map((r, i) => ({ key: r.key, label: r.label, pct: pcts[i], noData: r.noData }));
}

/** The topic named in "matches your interest in X", if any. */
export function topicFromWhy(whyTopics: unknown): string | null {
  if (typeof whyTopics !== "string") return null;
  const m = whyTopics.match(/interest in (.+?)(?: and |$)/i);
  return m ? m[1] : null;
}
