# Cold-Start Contingency Plan

*Pre-written so a weak week-1 doesn't cause decision paralysis (audit 16-8). The
cold-start problem is the product's top risk: every behavioural signal needs
5–20 interactions to activate, so the first week is the thinnest exactly when
users decide to stay.*

## Trigger

Run this plan if, after the fixes already shipped, the concierge test (or the
launch cohort) shows: **suggestion-driven-read rate ≈ 0 by day 7 for the
majority of users**, or the `/metrics/cold-start-funnel` activation rate is low.

## Response ladder (cheapest first)

1. **Expand + human-curate starter packs.** Grow `starter_sources` and curate a
   high-quality set per interest cluster, so day-1 ranking has strong seeds even
   before behavioural signal exists.
2. **Set expectations honestly in-product.** Show the "gathering your first
   reads" state (already built) and a "not fully personalized yet — improving as
   you read" banner for the first N days. This buys patience instead of a
   "it's just a random feed" verdict.
3. **Editorial week-1 digest.** For the first week, hand-curate or lightly
   editorialize the digest (concierge-style) while the model warms, then hand off
   to the engine. Expensive in founder time; only if 1–2 aren't enough.
4. **Re-examine the ranking core.** If suggestion-read rate stays ~0 after the
   above, re-check the semantic per-cluster/bridge scoring (05-2/05-4) and the
   serendipity selection (04-1) with the ranking-eval harness
   (`scripts/ranking_eval.py`) before concluding the wedge itself is wrong.

## What NOT to do

- Don't market to the knowledge-worker/revenue ICP during a weak cold start —
  every bounce burns a scarce paid-segment user.
- Don't add more onboarding steps to "collect more signal"; that fights the
  low-burden goal. Improve seed quality instead.

## Measure the recovery

Track week-over-week on `/metrics/north-star` (suggestion-read rate) and
`/metrics/cohort-retention` (D7). The goal is suggestion-read rate > 0 for ≥50%
of a cohort by day 7, rising thereafter.
