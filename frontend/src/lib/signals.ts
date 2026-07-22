// Human labels for the 8 PRS signals (audit 09-6).
//
// Single frontend source of truth. This intentionally mirrors the backend copy
// in backend/app/services/digest/delivery.py::SIGNAL_LABELS (used for the email
// digest); keep the two in sync. They can't share one file across the
// Python/TypeScript boundary without codegen, which isn't worth it for eight
// static strings.
export const SIGNAL_LABELS: Record<string, string> = {
  semantic: "matches your interests",
  reading_depth: "matches your reading depth",
  suggestion: "similar to content you discovered",
  explicit_feedback: "aligns with your ratings",
  source_trust: "from a trusted source",
  content_quality: "high quality content",
  temporal_context: "matches your current focus",
  novelty: "expands your reading",
};
