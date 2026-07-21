# 10 — UX Audit (Full Journey)

*Evidence: OnboardingWizard, digest/reader/feedback components, api.ts, cold_start + digest services.*

## Status Snapshot

- The habit loop is coherently built end-to-end: register → 5-step onboarding → first digest generated synchronously on finish → in-app reader with telemetry → thumbs/save/tag feedback → nightly relearn. Few solo projects get this far.
- **The cold-start UX has a fatal first-run timing risk**: onboarding's final step calls `digest.generate()`, but content must first be *ingested* (30-min feed schedule) and *embedded* before ranking means anything. A brand-new user likely sees an empty or near-random first digest seconds after finishing setup — the exact moment the spec says must feel "noticeably smarter."
- Onboarding asks for interests, sample-article ratings, sources, and a creator — good signal extraction, but it's **5 steps of upfront work before any payoff**, which fights the spec's own "extract signal without burdening the user" goal.
- Feedback mechanisms are rich (thumbs, tagged reasons, save, telemetry) but discovery of the nuanced feedback (tag reasons, topic suppression) isn't obviously surfaced in the primary flow.
- Re-engagement depends entirely on the daily email; no push, no streaks, no "you have N unread" nudge, and the unsubscribe/preferences link is broken (localhost) — so the one retention channel has a broken control surface.

## Journey map & friction points

1. **Sign-up.** Email/password only; no OAuth, no magic link. Register returns a token immediately (auto-login — good). Password rules unspecified in UI. Friction: low, but no social proof / no "why give you my email" on the auth screen.
2. **Onboarding (5 steps).** Interests free-text (good — richer than categories, matches spec). Sample articles: **where do they come from?** `SampleArticles` needs a curated, embeddable set; if it's static/generic it under-delivers signal. Sources + creators steps add friction before value. **The "aha" is deferred to after all 5 steps + ingestion latency.**
3. **First digest.** Generated on finish. **Highest-risk moment.** If empty/thin (no ingested+embedded content yet), the user's first impression is "this is broken/generic" — and they leave before the engine can learn. There's no "we're gathering your first reads, check back in an hour" honest-state screen.
4. **Daily loop.** Digest sectioned; ContentCard shows why-ranked (great for trust). Reader captures real telemetry (excellent). Completion/scroll flow to ranking. This part is genuinely good once content exists.
5. **Feedback.** Thumbs/save inline; tagged reasons + topic suppression exist in API (`adjust-interests`, `explicit_rating_reason`) but surfacing in UI is unclear. The spec's "conversational feedback prompts" for new users are generated server-side (`_generate_feedback_prompts`) and fetchable — good, if the UI renders them.
6. **Settings/tuning.** Preferences page fetches interest graph + serendipity %. Exposing the interest graph is a strong trust/tuning feature (and the ICP-#1 hook). Temporary topic suppression (`suppressed_until`) is implemented — surface it prominently.
7. **Churn/re-engagement.** Single channel (email), broken preferences link, no re-activation logic for lapsed users, no "light user" accommodation despite the spec naming light users as an at-risk segment.

## The core UX tension (spec's own risk, now concrete)

The spec says the product is weakest for light/new users and strongest for daily readers — and the *build confirms it*: the whole loop needs (a) ingested+embedded content and (b) ≥5–20 interactions before signals activate (`MIN_HISTORY=5`, `MIN_INTERACTIONS_FOR_LEARNING=20`, `reading_depth` needs 5 completions). So the first-week experience is the thinnest, and that's when people decide to stay. **The UX must over-invest in the first-run honest-state + starter quality, not the steady-state loop (which is already good).**

## Checklist

- [ ] P0 | Fix first-digest timing: gate onboarding completion on a real "gathering your first reads" state; don't show an empty/random digest seconds after setup | This is the exact make-or-break moment the spec flags | OnboardingWizard `finish()` → `digest.generate()`; 30-min ingest schedule | M | eng
- [ ] P0 | Ensure sample articles are a curated, pre-embedded, genuinely diverse set that yields real signal | Onboarding signal quality gates day-1 ranking | `SampleArticles.tsx`, `onboarding.py` sample handling | M | founder+eng
- [ ] P1 | Cut onboarding to the minimum that yields signal; make sources/creators optional/skippable with strong defaults | 5 upfront steps fights the "low burden" goal | OnboardingWizard STEPS | S | design
- [ ] P1 | Surface the conversational feedback prompts + tagged-reason feedback + topic-suppression in the primary UI | Rich feedback exists in API but may be invisible → no high-quality labels | `digest.prompts`, `feedback.adjustInterests` | M | design/eng
- [ ] P1 | Fix the digest preferences/unsubscribe link and add re-engagement email logic for lapsed users | The only retention channel has a broken control + no win-back | `digest_email.html` localhost link | S | eng
- [ ] P1 | Add an explicit light-user path (weekly digest option, "we kept it short" framing) | Spec names light users as the at-risk churn segment | `digest_frequency` exists; no light-user UX | M | design
- [ ] P2 | Show the interest graph + "watch it learn" as a first-class page (ICP-#1 delight, trust for all) | Turns the invisible engine into a visible payoff | preferences interest-graph API | M | design/eng
- [ ] P2 | Add OAuth/magic-link sign-in to cut sign-up friction | Lowers top-of-funnel drop | `api/auth.py` | M | eng

## Top 5 if you only do 5 things

1. Fix the first-digest moment — honest "gathering" state instead of an empty/random digest.
2. Make sample articles a real, pre-embedded, diverse signal source.
3. Trim onboarding to the fewest high-signal steps; make the rest skippable.
4. Surface the nuanced feedback + topic-suppression controls users can't currently find.
5. Fix the broken preferences/unsubscribe link and add lapsed-user win-back.

**Revisit trigger:** re-run after the concierge cold-start test (artifact 01) — it will expose the real first-week friction.
