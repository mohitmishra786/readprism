# 01 — Product-Market Fit & Vision Audit

*Audit date: 2026-07-21. Evidence types: **spec says** (spec/PCIP_Proposal_V2.md), **code shows** (github.com/mohitmishra786/readprism@main), **market shows** (cited web search, July 2026).*

## Status Snapshot

- **Code shows** a genuinely implemented ranking engine (8 signals, per-user gradient-descent meta-weights, interest graph with decay) — the wedge is *built*, which is rare for pre-launch projects. It is not vaporware.
- **Product reality**: 0 users, 1 star, no deployed instance, no waitlist, no analytics. Every retention/moat claim in the spec is untested against a single real reading session.
- **Spec says** the moat is accumulated behavioral data + non-portable interest graphs. For a project with zero users, this is a *future* moat description, not a present defensibility argument. Today the only defensible asset is speed of iteration and the open-source codebase itself — which, being MIT-licensed, is trivially forkable (see 08).
- **Market shows** the "personalized reading" graveyard is real: Artifact (Instagram founders, excellent personalization) shut down in early 2024; Apricot shut Dec 2025 ([Readless aggregator roundup](https://www.readless.app/blog/best-ai-news-aggregators-2026)). Behavioral ranking alone has not saved products with far more distribution than ReadPrism has.
- The single closest existing analog to the wedge is **NewsBlur's trainable Intelligence** (transparent, behavior-adjacent, $36/yr) — the LAUNCH.md correctly identifies this; the spec's competitor table omits NewsBlur entirely.

## The single biggest assumption

**"The first digest a new user receives must already feel noticeably smarter than a generic feed" (spec, Risks section — the spec's own words).** Everything else — data moat, 30/90/365-day flywheel, suggestion-signal loop — is downstream of surviving days 1–14. Code shows the mitigations exist (starter-source seeding at trust 0.45, collaborative warmup, feedback prompts), but:

- Collaborative warmup is mathematically inert at 0 users (and **code shows** it silently no-ops unless *other* users' interest vectors happen to be warm in Redis — `cold_start/collaborative.py` reads `interest_vec:{uid}` from cache only).
- Day-1 ranking therefore reduces to: onboarding free-text → Groq topic extraction → embedding similarity against a handful of seeded nodes. That is a *keyword-ish semantic filter* on day 1 — closer to Feedly Leo than the spec admits.

**Cheapest de-risk:** before any launch, run a 10-person concierge test. Have 10 real people (not the founder) complete onboarding, receive 7 daily digests, and rate each digest item "would have found this myself / glad it surfaced / noise." If suggestion-driven reads (the spec's "purest signal") aren't happening by day 7 for at least half of them, the cold-start story needs redesign before marketing spend of any kind. Cost: ~0 dollars, 2 weeks.

## Stress-testing the moat claims

| Spec claim | Reality check |
|---|---|
| "Data moat compounds; 18-month graph not portable" | True *if* users reach 18 months. Irrelevant at N=0. Also weakened by self-hosting: a self-hosted user's graph is in *their* Postgres — portable by design. The moat argument applies only to a future hosted service. |
| "Competitor must build algorithm *and* wait for data" | The algorithm is MIT-licensed in this repo. A competitor doesn't need to build it; they can fork it. The data half stands; the algorithm half is given away (deliberate trade-off — but the spec never acknowledges it). |
| "Switching cost = loss of a model that knows you" | Symmetric problem: it's also the *acquisition* cost. Every user must invest weeks before the product is better than Feedly. The moat and the cold-start risk are the same mechanism. |
| "No existing consumer tool does this" | Mostly still true for the full 8-signal behavioral design (**market shows** Feedly Leo remains keyword/topic-rule based, [Feedly pricing/features](https://socialrails.com/blog/blog/feedly-pricing)); but NewsBlur does trainable per-user ranking, and 2025–26 entrants (Particle, TheReader.AI, LetMeKnow.News) do embedding-based personalization on the aggregator side. The claim needs narrowing to "reading-telemetry-driven, explainable, self-hostable." |

## Checklist

- [ ] P0 | Run the 10-user concierge cold-start test | The spec itself names cold start as the existential risk; nothing in the repo measures it | spec Risks §1; no analytics code in repo | M | founder
- [ ] P0 | Define the wedge in one falsifiable sentence (e.g. "by day 14, ≥30% of opened items are ones the user wouldn't have found") | "Behavioral ranking" is a mechanism, not a testable value prop | spec §Signal Dim 3 | S | founder
- [ ] P0 | Decide hosted-first vs self-host-first — the moat argument only works hosted | Self-hosted users generate no collaborative data and have portable graphs | code: docker-compose.yml is single-tenant | S | founder
- [ ] P1 | Instrument suggestion-driven-read rate from day one (spec's "purest signal") as *the* PMF metric | Without it you cannot tell if the flywheel spins | code: `was_suggested` column exists; no aggregate metric endpoint | M | eng
- [ ] P1 | Narrow the positioning claim to what's uniquely true (telemetry + explainability + self-hosting) vs NewsBlur/Particle | Overbroad "no one does this" claims get destroyed in HN comments | LAUNCH.md already gestures at this | S | founder
- [ ] P1 | Write down the kill criteria (e.g. "if day-30 retention of concierge cohort < X, pivot the wedge") | Solo projects drift; pre-registered criteria prevent sunk-cost drift | commit history shows 4-month gap Mar–Jun 2026 | S | founder
- [ ] P2 | Explore the "explainable ranking" angle as the *marketable* wedge (why-ranked labels already in code) | Explainability is demo-able on day 1; data moats aren't | code: `delivery.py::_top_signals`, `why_ranked` | M | founder
- [ ] P2 | Revisit whether the graph/meta-weights should be exportable as a user-facing feature ("your model, yours to take") | Turns the anti-moat of self-hosting into a trust-based differentiator | integrations/export.py exists | M | eng

## Top 5 if you only do 5 things

1. Concierge cold-start test with 10 real users before any public launch.
2. Pick one falsifiable PMF sentence and instrument the one metric that tests it (suggestion-driven read rate).
3. Decide hosted-first vs self-host-first; the business logic differs completely.
4. Narrow the differentiation claim so it survives contact with NewsBlur/Particle-aware commenters.
5. Pre-register kill/pivot criteria with dates.

**Revisit trigger:** re-run this artifact after the concierge test concludes, or at 100 signed-up users — whichever comes first.
