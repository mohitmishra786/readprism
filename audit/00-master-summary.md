# 00 — Master Summary

*ReadPrism (PCIP) cross-functional audit, 2026-07-21. 17 artifacts in this folder (01–17). Read this page first.*

## Grounding: where the project actually is

**Roadmap phase (code vs spec).** The repo is best described as **Phase 3-built, Phase 0-validated.** The code has raced ahead of the roadmap's timeline: Phases 1–3 features exist in source (RSS/scrape/newsletter ingestion; full 8-signal PRS; per-user gradient-descent meta-weights; 3-scale temporal model; interest graph + decay; creator resolution; collaborative warmup; feedback prompts; teams; integrations/export) and even Phase 4 pieces (browser extension, PWA manifest/SW). CI is green, 27 test files, Dependabot active. **But** the product is pre-everything that matters commercially: **1 GitHub star, 0 users, no deployed instance, no billing, no analytics, no privacy policy, no demo.** The only human commits are two bursts (Feb 2026 gap-close, early Jul 2026 roadmap implementation); everything since is Dependabot. So: impressive engineering artifact, completely unvalidated product.

**Spec-vs-reality gaps to carry into every decision:**
- "Full 8-signal ranking engine" — **built and real.** Genuinely implemented, not vaporware.
- "Per-user gradient-descent meta-weights" — **built**, but the learning target partly predicts its own inputs (completion/rating leak into both signals and target); unvalidated on held-out data.
- "Interest graph with transitive relevance" — graph is **built and decayed**, but *transitive/2-hop relevance is not actually computed*; scoring uses a single averaged interest vector that collapses multi-interest users. The headline capability is functionally missing.
- "Cold-start collaborative warmup" — **built but inert** at low user counts and mislabeled (no real similarity ranking; depends on warm Redis vectors). Cannot be a day-1 pillar.
- "Graceful degradation with user notification" — degradation **yes**, user notification **no**.
- Spec competitor claims are **stale** (Inoreader now has AI; NewsBlur — the closest analog — is omitted; Mailbrew is a free zombie).
- Unit economics ($0.31/$0.95, 8k-Pro profitability) are **optimistic** and hinge on a summary-cache hit rate the niche-reader ICP structurally undermines.

## The one-month "if you do nothing else" list — top P0 per category

- **Strategy:** Run the 10-person concierge cold-start test. The spec names day-1 quality as the existential risk and nothing measures it. Everything else is downstream of this. *(artifact 01)*
- **Technical:** Fix the ranking core's two silent quality killers — the averaged-interest-vector collapse and the meta-learning target/input circularity — and build a held-out ranking-eval harness so "it learns" is falsifiable. *(artifact 05)*
- **Security/Legal:** Close the launch-blockers: authenticate the newsletter webhook + SSRF-guard server-side fetches; ship account deletion/export; and resolve the **MIT-vs-AGPL contradiction** (LICENSE says MIT, LAUNCH.md tells the world AGPL) with a CLA — cheapest to fix now at zero outside contributors. *(artifacts 06, 08)*
- **Design/UX:** Fix the first-digest moment — an empty/near-random digest seconds after onboarding, at the exact make-or-break instant. Gate on an honest "gathering your first reads" state. *(artifact 10)*
- **Growth:** Fill in GitHub topics/description/homepage + README visuals, and retire the "PCIP / Personalized Content Intelligence Platform" tagline for the plain "ranks by how you actually read." Near-zero effort, currently all undone. *(artifacts 11, 12)*
- **Measurement:** Build the event pipeline + cold-start funnel/cohort dashboard **before** launch, with suggestion-driven-read rate as the North Star. Launching without it wastes the one traffic spike. *(artifact 17)*

## How to read the rest

- **Blocking sequence:** artifact 14 (pre-launch) aggregates every P0 gate. Do not share a public link until its list is clear — especially the concierge test (01), the security/legal P0s (06/08), a working demo + verified install, and cold-start analytics (17).
- **The wedge is real but narrower than the spec claims.** Behavioral + explainable + self-hostable ranking is genuinely differentiated (vs Feedly keyword-Leo, vs black-box feeds). "No one does this" is false (NewsBlur, Particle). Market the true, provable version.
- **The moat is a future, not a present.** At N=0 with an MIT license, there is no data moat and the algorithm is forkable. The moat only exists hosted, with users, over time — which makes cold-start survival the whole game.
- **Biggest single risk, restated:** the product is thinnest in exactly the first 14 days when users decide to stay, because every behavioral signal needs 5–20 interactions to activate. Over-invest in first-run quality; the steady-state loop is already good.

## Artifact index

| # | Artifact | Top P0 |
|---|---|---|
| 01 | Product-Market Fit & Vision | Concierge cold-start test |
| 02 | Competitive Landscape (Jul 2026) | Fix Inoreader/NewsBlur in comparisons |
| 03 | Target User & ICP | Declare self-hosting-dev as ICP #1 |
| 04 | Architecture & Codebase | Fix serendipity candidate selection |
| 05 | AI/ML Ranking Engine | Held-out ranking-eval harness |
| 06 | Security & Privacy | Authenticate newsletter webhook |
| 07 | Infra, Reliability & Scale | Error monitoring across runtimes |
| 08 | Legal & Compliance | Resolve MIT-vs-AGPL + CLA |
| 09 | UI | Add dark mode to the app |
| 10 | UX | Fix the first-digest moment |
| 11 | SEO & Discoverability | GitHub topics/description/homepage |
| 12 | Marketing & Positioning | Retire the "PCIP" tagline |
| 13 | Monetization & Pricing | Align paywall with variable cost |
| 14 | Pre-Launch Checklist | Run concierge test before launch |
| 15 | Launch Checklist | Load-test + rate-limit the demo |
| 16 | Post-Launch & Retention | Instrument cohort retention |
| 17 | KPI & Metrics Framework | Build the event pipeline |

*All time-sensitive competitive, pricing, API-policy, and legal claims are cited inline in the relevant artifacts (web search, July 2026). Treat "spec says / code shows / market shows" as three distinct evidence types throughout.*
